# nanowallet/wallets/key_based.py
from typing import Optional, Protocol, Dict, Any, List
from decimal import Decimal
import asyncio
import time
import logging

from ..libs.account_helper import AccountHelper
from ..libs.block import NanoWalletBlock
from ..models import WalletConfig, Receivable, Transaction, ReceivedBlock
from ..utils.conversion import _raw_to_nano, _nano_to_raw
from ..utils.validation import validate_nano_amount
from ..utils.decorators import handle_errors, reload_after

from ..errors import (
    account_not_found,
    BlockNotFoundError,
    InsufficientBalanceError,
    InvalidAccountError,
    TimeoutException,
    RpcError,
    InvalidAmountError,
    NanoException,
)
from .read_only import NanoWalletReadOnly, NanoWalletReadOnlyProtocol
from ..libs.rpc import NanoWalletRpc
from ..utils.decorators import NanoResult

# Configure logging
logger = logging.getLogger(__name__)

# Constants
ZERO_HASH = "0" * 64
DEFAULT_THRESHOLD_RAW = 10**24

# Messages indicating retryable concurrency errors
RETRYABLE_ERROR_MESSAGES = [
    "Fork",  # Explicit fork detected by the node
    "gap previous",  # The 'previous' block specified isn't the frontier (stale state)
    "old block",  # Another potential message for stale state
    # Add any other specific error strings that indicate temporary concurrency issues
]


class NanoWalletKeyProtocol(NanoWalletReadOnlyProtocol, Protocol):
    """Protocol defining key operations for a Nano wallet"""

    private_key: str  # The private key for signing transactions

    async def send(self, destination_account: str, amount: Decimal | str | int) -> str:
        """Sends Nano to a destination account"""

    async def send_raw(self, destination_account: str, amount: int) -> str:
        """Sends Nano to a destination account"""

    async def send_with_retry(
        self,
        destination_account: str,
        amount: Decimal | str | int,
        max_retries: int = 5,
        retry_delay_base: float = 0.1,
        retry_delay_backoff: float = 1.5,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """Sends Nano with automatic retries on concurrency errors"""

    async def send_raw_with_retry(
        self,
        destination_account: str,
        amount_raw: int | str,
        max_retries: int = 5,
        retry_delay_base: float = 0.1,
        retry_delay_backoff: float = 1.5,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """Sends raw Nano amount with automatic retries on concurrency errors"""

    async def sweep(
        self,
        destination_account: str,
        sweep_pending: bool = True,
        threshold_raw: int = DEFAULT_THRESHOLD_RAW,
    ) -> str:
        """Transfers all funds from the current account to the destination account"""

    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> ReceivedBlock:
        """Receives a specific block by its hash"""

    async def receive_all(
        self,
        threshold_raw: float = DEFAULT_THRESHOLD_RAW,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> List[ReceivedBlock]:
        """Receives all pending receivable blocks"""

    async def refund_first_sender(self) -> str:
        """Sends remaining funds to the account opener"""


class NanoWalletKey(NanoWalletReadOnly, NanoWalletKeyProtocol):
    """Key operations implementation of NanoWallet"""

    def __init__(
        self,
        rpc: NanoWalletRpc,
        private_key: str,
        config: Optional[WalletConfig] = None,
    ):
        """
        Initialize wallet with a private key.

        :param rpc: RPC client
        :param private_key: Private key for signing transactions
        :param config: Optional wallet configuration
        """
        # First get the account from the private key
        account = AccountHelper.get_account_address(private_key)
        super().__init__(rpc, account, config)
        self.private_key = private_key

    async def _build_block(
        self,
        previous: str,
        representative: str,
        balance: int,
        source_hash: Optional[str] = None,
        destination_account: Optional[str] = None,
    ) -> NanoWalletBlock:
        """
        Builds a state block with the given parameters.

        :param previous: Previous block hash or zeros for first block
        :param representative: Representative account
        :param balance: Account balance after this block
        :param source_hash: Hash of send block to receive (for receive blocks)
        :param destination_account: Destination account (for send blocks)
        :return: Block instance
        :raises ValueError: If parameters are invalid
        """

        block = NanoWalletBlock(
            account=self.account,
            previous=previous,
            representative=representative,
            balance=balance,
            source_hash=source_hash,
            destination_account=destination_account,
        )

        block.sign(self.private_key)
        work = await self._generate_work(block.work_block_hash)
        block.set_work(work)
        return block

    async def _generate_work(self, pow_hash: str) -> str:
        """
        Generate proof of work for a block.

        :param pow_hash: The hash to generate work for
        :return: The generated work value
        :raises ValueError: If work generation fails
        """
        response = await self.rpc.work_generate(
            pow_hash, use_peers=self.config.use_work_peers
        )
        return response["work"]

    async def _wait_for_confirmation(
        self, block_hash: str, timeout: int = 300, raise_on_timeout: bool = False
    ) -> bool:
        """
        Wait for block confirmation with exponential backoff.

        Args:
            block_hash: Hash of the block to confirm
            timeout: Maximum time to wait in seconds
            raise_on_timeout: If True, raises TimeoutException when confirmation times out

        Returns:
            bool: True if confirmed, False if not confirmed and raise_on_timeout is False

        Raises:
            TimeoutException: If confirmation times out and raise_on_timeout is True
        """
        start_time = time.time()
        delay = 0.5  # Start with 500ms
        max_delay = 32  # Cap maximum delay
        attempt = 1

        logger.debug(
            "Starting confirmation wait for %s with timeout=%s", block_hash, timeout
        )

        while (time.time() - start_time) < timeout:
            try:
                block_info = await self._block_info(block_hash)
                confirmed = block_info.get("confirmed", "false") == "true"

                logger.debug(
                    "Confirmation check attempt %s: confirmed=%s, elapsed=%s",
                    attempt,
                    confirmed,
                    time.time() - start_time,
                )

                if confirmed:
                    return True

                # Exponential backoff with cap
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                attempt += 1

            except BlockNotFoundError:
                logger.debug(
                    "Block not found on attempt %s, retrying after %s seconds",
                    attempt,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                attempt += 1
                continue

        elapsed = time.time() - start_time
        logger.debug("Confirmation wait timed out after %s seconds", elapsed)

        if raise_on_timeout:
            raise TimeoutException(
                f"Block {block_hash} not confirmed within {timeout} seconds"
            )

        return False

    async def _process_block(self, block: NanoWalletBlock, operation: str) -> str:
        """
        Process a block and handle errors consistently.

        :param block: The block to process
        :param operation: Description of the operation (for logging)
        :return: Hash of the processed block
        :raises ValueError: If block processing fails
        """
        response = await self.rpc.process(block.json())

        block_hash = response["hash"]
        logger.debug("Successfully processed %s, hash: %s", operation, block_hash)
        return block_hash

    async def _get_block_params(self) -> Dict[str, Any]:
        """
        Get common parameters for block creation.

        :return: Dictionary with previous block hash, balance, and representative
        :raises ValueError: If account info cannot be retrieved
        """
        account_info = await self._fetch_account_info()
        if account_not_found(account_info):
            logger.debug("Account %s not found, using default parameters", self.account)
            return {
                "previous": ZERO_HASH,
                "balance": 0,
                "representative": self.config.default_representative,
            }

        logger.debug(
            "Retrieved block params for %s: balance=%s",
            self.account,
            account_info["balance"],
        )
        return {
            "previous": account_info["frontier"],
            "balance": int(account_info["balance"]),
            "representative": account_info["representative"],
        }

    @reload_after
    @handle_errors
    async def send(
        self,
        destination_account: str,
        amount: Decimal | str | int,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """
        Sends Nano to a destination account.

        Args:
            destination_account: The destination account
            amount: The amount in Nano (as Decimal, string, or int)
            wait_confirmation: If True, wait for network confirmation before returning
            timeout: Max seconds to wait for confirmation

        Returns:
            str: The hash of the sent block

        Raises:
            TypeError: If amount is float or invalid type
            ValueError: If amount is negative or invalid format
            InvalidAccountError: If destination account is invalid
            InsufficientBalanceError: If insufficient balance
            TimeoutException: If confirmation times out
        """
        amount_decimal = validate_nano_amount(amount)
        amount_raw = _nano_to_raw(amount_decimal)
        response = await self.send_raw(
            destination_account,
            amount_raw,
            wait_confirmation=wait_confirmation,
            timeout=timeout,
        )
        return response.unwrap()

    async def _attempt_send_raw_internal(
        self,
        destination_account: str,
        amount_raw: int,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """
        Internal helper to attempt sending without decorators. Raises exceptions on failure.

        Args:
            destination_account: The recipient account address
            amount_raw: The amount to send in raw units
            wait_confirmation: Whether to wait for confirmation
            timeout: Timeout in seconds for the confirmation wait

        Returns:
            The block hash of the successfully sent transaction

        Raises:
            Various NanoException subclasses on failure
        """
        logger.debug(
            "(Internal) Attempting to send %s raw to %s",
            amount_raw,
            destination_account,
        )

        if not destination_account:
            logger.error("Invalid destination account: %s", destination_account)
            raise InvalidAccountError("Destination can't be None")
        if not AccountHelper.validate_account(destination_account):
            logger.error("Invalid destination account: %s", destination_account)
            raise InvalidAccountError("Invalid destination account.")

        # Fetch current state *just before* building the block
        params = await self._get_block_params()
        new_balance = params["balance"] - int(amount_raw)

        if params["balance"] == 0 or new_balance < 0:
            msg = f"Insufficient balance for send! balance:{params['balance']} send_amount:{amount_raw}"
            logger.error(msg)
            raise InsufficientBalanceError(msg)

        # Build and process
        block = await self._build_block(
            previous=params["previous"],
            representative=params["representative"],
            balance=new_balance,
            destination_account=destination_account,
        )
        block_hash = await self._process_block(
            block, f"send of {amount_raw} raw to {destination_account}"
        )

        # Handle confirmation *after* successful processing
        if wait_confirmation:
            confirmed = await self._wait_for_confirmation(
                block_hash, timeout=timeout, raise_on_timeout=True
            )
            if (
                not confirmed
            ):  # Should have raised TimeoutException, but defensive check
                logger.warning(
                    "Block %s processed but confirmation timed out/failed.", block_hash
                )

        return block_hash

    # Modify existing send_raw to use the internal helper
    @reload_after  # Reloads state *after* successful send
    @handle_errors  # Wraps final result/exceptions in NanoResult
    async def send_raw(
        self,
        destination_account: str,
        amount_raw: int | str,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """
        Sends Nano to a destination account.

        Args:
            destination_account: The destination account
            amount_raw: The amount in raw
            wait_confirmation: If True, wait for network confirmation
            timeout: Max seconds to wait for confirmation

        Returns:
            The hash of the sent block

        Raises:
            This method performs a single send attempt. Use send_raw_with_retry for concurrency.
            Exceptions are caught by @handle_errors and wrapped in NanoResult.
        """
        # Basic validation before trying internal logic
        try:
            amount_val = int(amount_raw)
            if amount_val <= 0:
                raise InvalidAmountError("Send amount must be positive.")
        except ValueError:
            raise InvalidAmountError(f"Invalid raw amount format: {amount_raw}")

        # Call the internal logic that raises exceptions
        # @handle_errors will catch exceptions from here
        return await self._attempt_send_raw_internal(
            destination_account, amount_val, wait_confirmation, timeout
        )

    # NEW METHOD
    @reload_after  # Reload after the *entire* successful retry operation
    @handle_errors  # Handle final success or failure/exception
    async def send_raw_with_retry(
        self,
        destination_account: str,
        amount_raw: int | str,
        max_retries: int = 5,
        retry_delay_base: float = 0.1,  # seconds
        retry_delay_backoff: float = 1.5,  # exponential backoff factor
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """
        Attempts to send Nano (raw amount), automatically reloading state and retrying
        on specific concurrency errors (Fork, gap previous).

        Args:
            destination_account: The recipient account address.
            amount_raw: The amount to send in raw units.
            max_retries: Maximum number of retry attempts (default: 5).
            retry_delay_base: Initial delay in seconds before the first retry (default: 0.1).
            retry_delay_backoff: Multiplies the delay for subsequent retries (default: 1.5).
            wait_confirmation: Whether to wait for confirmation after the *successful* send.
            timeout: Timeout in seconds for the confirmation wait.

        Returns:
            The block hash of the successfully sent transaction.

        Raises:
            Catches internal exceptions and returns NanoResult via @handle_errors.
            Will raise NanoException via unwrap() if used like: (await wallet.send_raw_with_retry(...)).unwrap()
        """
        try:
            amount_val = int(amount_raw)
            if amount_val <= 0:
                raise InvalidAmountError("Send amount must be positive.")
        except ValueError:
            raise InvalidAmountError(f"Invalid raw amount format: {amount_raw}")

        retries = 0
        last_error = None

        while retries <= max_retries:
            attempt = retries + 1
            logger.debug(
                f"Send attempt {attempt}/{max_retries + 1} for {amount_val} raw to {destination_account}"
            )
            try:
                # *** Crucial: Reload state *before* each attempt ***
                await self.reload()  # Fetch latest frontier etc. directly

                # Call the internal, non-decorated send logic
                block_hash = await self._attempt_send_raw_internal(
                    destination_account, amount_val, wait_confirmation, timeout
                )
                # If it succeeded without raising exception:
                logger.debug(f"Send attempt {attempt} SUCCEEDED. Hash: {block_hash}")
                return block_hash  # Success! Return hash (@handle_errors will wrap it)

            except RpcError as e:
                last_error = e
                # Check if the error message indicates a retryable condition
                is_retryable = any(
                    phrase in e.message for phrase in RETRYABLE_ERROR_MESSAGES
                )

                if is_retryable and retries < max_retries:
                    retries += 1
                    delay = retry_delay_base * (retry_delay_backoff ** (retries - 1))
                    logger.warning(
                        f"Send attempt {attempt} failed with retryable RPC error ('{e.message}'). "
                        f"Retrying ({retries}/{max_retries}) after {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue  # Go to next iteration of the while loop
                else:
                    # Error is not retryable OR max retries reached
                    logger.error(
                        f"Send attempt {attempt} failed with RPC error ('{e.message}') and will not retry."
                    )
                    raise e  # Re-raise the exception (@handle_errors will catch it)

            except (
                InsufficientBalanceError,
                InvalidAccountError,
                InvalidAmountError,
            ) as e:
                # Non-retryable errors - fail immediately
                last_error = e
                logger.error(
                    f"Send attempt {attempt} failed with non-retryable error: {e}"
                )
                raise e  # Re-raise the exception (@handle_errors will catch it)

            except Exception as e:
                # Catch any other unexpected errors during the attempt
                last_error = e
                logger.error(
                    f"Send attempt {attempt} failed with unexpected error: {e}",
                    exc_info=True,
                )
                # Treat unexpected errors as non-retryable for safety
                raise NanoException(
                    f"Unexpected error during send attempt: {e}",
                    "UNEXPECTED_SEND_ERROR",
                ) from e

        # Should only be reached if loop finishes due to max_retries exceeded after a retryable error
        logger.error(
            f"Send failed after {max_retries + 1} attempts. Last error: {last_error}"
        )
        if last_error:
            raise last_error  # Re-raise the last encountered error
        else:
            # Should not happen if loop logic is correct, but as fallback:
            raise NanoException(
                f"Send failed after {max_retries + 1} attempts.", "MAX_RETRIES_EXCEEDED"
            )

    # Add a convenience wrapper for Decimal amounts
    @reload_after
    @handle_errors
    async def send_with_retry(
        self,
        destination_account: str,
        amount: Decimal | str | int,
        max_retries: int = 5,
        retry_delay_base: float = 0.1,
        retry_delay_backoff: float = 1.5,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """
        Attempts to send Nano (Decimal amount), automatically reloading state and retrying
        on specific concurrency errors (Fork, gap previous). See send_raw_with_retry for details.

        Args:
            destination_account: The recipient account address.
            amount: The amount to send as Decimal, string, or int.
            max_retries: Maximum number of retry attempts (default: 5).
            retry_delay_base: Initial delay in seconds before the first retry (default: 0.1).
            retry_delay_backoff: Multiplies the delay for subsequent retries (default: 1.5).
            wait_confirmation: Whether to wait for confirmation after the *successful* send.
            timeout: Timeout in seconds for the confirmation wait.

        Returns:
            The block hash of the successfully sent transaction.
        """
        amount_decimal = validate_nano_amount(amount)
        amount_raw = _nano_to_raw(amount_decimal)
        # Call the decorated send_raw_with_retry
        result = await self.send_raw_with_retry(
            destination_account,
            amount_raw,
            max_retries=max_retries,
            retry_delay_base=retry_delay_base,
            retry_delay_backoff=retry_delay_backoff,
            wait_confirmation=wait_confirmation,
            timeout=timeout,
        )
        # Need to unwrap/rewrap because send_raw_with_retry returns NanoResult
        return result.unwrap()

    @reload_after
    @handle_errors
    async def sweep(
        self,
        destination_account: str,
        sweep_pending: bool = True,
        threshold_raw: int = DEFAULT_THRESHOLD_RAW,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> str:
        """
        Transfers all funds from the current account to the destination account.
        :param destination_account: The account to receive the funds.
        :param sweep_pending: Whether to receive pending blocks before sending.
        :param threshold_raw: Minimum amount to consider for receiving pending blocks (in raw).
        :param wait_confirmation: If True, wait for confirmation
        :param timeout: Max seconds to wait for confirmation
        :return: The hash of the sent block.
        :raises ValueError: If the destination account is invalid or insufficient balance.
        """
        if not AccountHelper.validate_account(destination_account):
            raise InvalidAccountError("Invalid destination account.")

        if sweep_pending:
            receive_result: NanoResult[List[ReceivedBlock]] = await self.receive_all(
                threshold_raw=threshold_raw,
                wait_confirmation=False,
            )
            if not receive_result:
                logger.debug(
                    "Sweep failed: Error during receive_all: %s", receive_result.error
                )
                # Propagate the error result
                raise NanoException(receive_result.error, receive_result.error_code)
            logger.debug(
                "Sweep: Pending blocks received successfully (or none to receive)."
            )

        send_result: NanoResult[str] = await self.send_raw(
            destination_account,
            self._balance_info.balance_raw,
            wait_confirmation=wait_confirmation,
            timeout=timeout,
        )

        if not send_result:
            logger.error("Sweep failed: Error during send_raw: %s", send_result.error)
            raise NanoException(send_result.error, send_result.error_code)

        final_hash = send_result.unwrap()
        logger.debug("Sweep successful. Sent block hash: %s", final_hash)
        return final_hash  # @handle_errors will wrap this in NanoResult

    @reload_after
    @handle_errors
    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> ReceivedBlock:
        """
        Receives a specific block by its hash.

        Args:
            block_hash: Hash of the block to receive
            wait_confirmation: If True, wait for block confirmation
            timeout: Max seconds to wait for confirmation
        Returns:
            ReceivedBlock object with details about the received block

        Raises:
            BlockNotFoundError: If block not found
            TimeoutException: If confirmation times out
        """
        logger.debug(
            "Starting receive_by_hash for block %s, wait_confirmation=%s, timeout=%s",
            block_hash,
            wait_confirmation,
            timeout,
        )

        try:
            send_block_info = await self._block_info(block_hash)
            amount_raw = int(send_block_info["amount"])
            logger.debug("Block %s contains %s raw", block_hash, amount_raw)

            params = await self._get_block_params()
            new_balance = params["balance"] + amount_raw
            logger.debug("Building block with new_balance=%s", new_balance)

            block = await self._build_block(
                previous=params["previous"],
                representative=params["representative"],
                balance=new_balance,
                source_hash=block_hash,
            )

            received_hash = await self._process_block(
                block, f"receive of {amount_raw} raw from block {block_hash}"
            )
            logger.debug("Block processed with hash %s", received_hash)

            confirmed = False
            if wait_confirmation:
                confirmed = await self._wait_for_confirmation(
                    received_hash, timeout=timeout, raise_on_timeout=True
                )

            return ReceivedBlock(
                block_hash=received_hash,
                amount_raw=amount_raw,
                source=send_block_info["block_account"],
                confirmed=confirmed if wait_confirmation else False,
            )

        except Exception as e:
            logger.debug(
                "Exception in receive_by_hash: %s: %s", type(e).__name__, str(e)
            )
            raise

    @reload_after
    @handle_errors
    async def receive_all(
        self,
        threshold_raw: float = DEFAULT_THRESHOLD_RAW,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> List[ReceivedBlock]:
        """
        Receives all pending receivable blocks.

        Args:
            threshold_raw: Minimum amount to receive
            wait_confirmation: If True, wait for block confirmations
            timeout: Max seconds to wait for each confirmation

        Returns:
            List of ReceivedBlock objects with details about each received block
        """
        block_results = []
        response = await self.list_receivables(threshold_raw=threshold_raw)
        receivables = response.unwrap()

        receivable: Receivable
        for receivable in receivables:
            received_block = await self.receive_by_hash(
                receivable.block_hash,
                wait_confirmation=wait_confirmation,
                timeout=timeout,
            )
            block_results.append(received_block.unwrap())

        return block_results

    @handle_errors
    async def refund_first_sender(self) -> str:
        """
        Sends remaining funds to the account opener.

        :return: The hash of the sent block.
        :raises ValueError: If no funds are available or the refund account cannot be determined.
        """
        has_balance = await self.has_balance()
        if not has_balance.unwrap():
            raise InsufficientBalanceError(
                "Insufficient balance. No funds available to refund."
            )
        if self._account_info.open_block:
            block_info = await self._block_info(self._account_info.open_block)
            refund_account = block_info["source_account"]
        elif self.receivable_blocks:
            first_receivable_hash = next(iter(self.receivable_blocks))
            block_info = await self._block_info(first_receivable_hash)
            refund_account = block_info["block_account"]
        else:
            raise ValueError("Cannot determine refund account.")

        response = await self.sweep(refund_account)
        return response.unwrap()
