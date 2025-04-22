import asyncio
import logging
from typing import Optional, List, Dict
from decimal import Decimal

from ..libs.account_helper import AccountHelper
from ..libs.rpc import INanoRpc
from ..models import (
    WalletConfig,
    WalletBalance,
    AccountInfo,
    Receivable,
    Transaction,
    ReceivedBlock,
    RefundDetail,
    RefundStatus,
)
from ..utils.conversion import raw_to_nano, nano_to_raw
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

# Import mixins and protocol
from .protocols import IAuthenticatedWallet, IReadOnlyWallet
from .mixins import StateManagementMixin, BlockOperationsMixin

# Configure logging
logger = logging.getLogger(__name__)

# Constants
RETRYABLE_ERROR_MESSAGES = [
    "Fork",  # Explicit fork detected by the node
    "gap previous",  # The 'previous' block specified isn't the frontier
    "old block",  # Another potential message for stale state
]


class NanoWalletAuthenticated(
    StateManagementMixin,
    BlockOperationsMixin,
    IAuthenticatedWallet,
    IReadOnlyWallet,
):
    """Authenticated wallet implementation using composition and mixins"""

    def __init__(
        self,
        rpc: INanoRpc,
        private_key: str,
        config: Optional[WalletConfig] = None,
    ):
        """
        Initialize authenticated wallet with a private key.

        Args:
            rpc: RPC client for blockchain interaction
            private_key: Private key for signing transactions
            config: Optional wallet configuration
        """
        try:
            self.account = AccountHelper.get_account_address(private_key)
        except Exception as e:
            logger.error("Failed to derive account address from private key: %s", e)
            raise ValueError(f"Invalid private key provided: {e}") from e

        self.rpc = rpc
        self.config = config or WalletConfig()
        self.private_key = private_key

        # Initialize state
        self._init_account_state()
        logger.info("Initialized NanoWalletAuthenticated for account: %s", self.account)

    #
    # IReadOnlyWallet methods
    #

    @handle_errors
    async def reload(self) -> None:
        """Reload wallet state from the network."""
        await super().reload()

    @handle_errors
    async def account_history(
        self, count: Optional[int] = -1, head: Optional[str] = None
    ) -> List[Transaction]:
        """
        Get block history for the wallet's account.

        Args:
            count: Number of blocks to retrieve, -1 for all blocks (default)
            head: Start from specific block hash instead of latest

        Returns:
            List of blocks with their details
        """
        logger.debug("Fetching account history: count=%s, head=%s", count, head)
        try:
            response = await self.rpc.account_history(
                account=self.account, count=count, raw=True, head=head
            )

            if account_not_found(response):
                return []

            # Check for other errors
            from ..errors import try_raise_error

            try_raise_error(response)

            # Parse the history list
            history = response.get("history", [])
            transactions = []
            for block in history:
                transactions.append(
                    Transaction(
                        block_hash=block["hash"],
                        type=block["type"],
                        subtype=block.get("subtype"),
                        account=block["account"],
                        previous=block["previous"],
                        representative=block["representative"],
                        amount_raw=int(block["amount"]),
                        balance_raw=int(block["balance"]),
                        timestamp=int(block["local_timestamp"]),
                        height=int(block["height"]),
                        confirmed=block["confirmed"] == "true",
                        link=block["link"],
                        signature=block["signature"],
                        work=block["work"],
                    )
                )

            return transactions

        except Exception as e:
            logger.error("Error retrieving account history: %s", str(e), exc_info=True)
            raise

    @handle_errors
    async def has_balance(self) -> bool:
        """
        Check if the account has available balance or receivable balance.

        Returns:
            True if balance or receivable balance is greater than zero
        """

        await self.reload()
        return (self._balance_info.balance_raw > 0) or (
            self._balance_info.receivable_raw > 0
        )

    @handle_errors
    async def balance_info(self) -> WalletBalance:
        """
        Get detailed balance information for the account.

        Returns:
            WalletBalance object containing current and receivable balances
        """
        await self.reload()
        return self._balance_info

    @handle_errors
    async def account_info(self) -> AccountInfo:
        """
        Get detailed account information.

        Returns:
            AccountInfo object containing account metadata
        """
        logger.debug("Fetching account info for account: %s", self.account)
        await self.reload()
        return self._account_info

    @handle_errors
    async def list_receivables(
        self, threshold_raw: Optional[int] = None
    ) -> List[Receivable]:
        """
        List receivable blocks sorted by descending amount.

        Args:
            threshold_raw: Minimum amount to consider (in raw). If None, uses config.min_receive_threshold_raw.

        Returns:
            List of Receivable objects containing block hashes and amounts
        """
        await self.reload()
        if not self.receivable_blocks:
            return []

        # Determine the threshold to use
        effective_threshold = (
            threshold_raw
            if threshold_raw is not None
            else self.config.min_receive_threshold_raw
        )
        logger.debug(
            "Listing receivables with effective threshold: %d raw", effective_threshold
        )

        receivables = [
            Receivable(block_hash=block, amount_raw=int(amount))
            for block, amount in self.receivable_blocks.items()
            # Use effective_threshold here
            if int(amount) >= effective_threshold
        ]
        return sorted(receivables, key=lambda x: x.amount_raw, reverse=True)

    #
    # IAuthenticatedWallet methods
    #

    async def _internal_send_raw(
        self,
        destination_account: str,
        amount_raw: int,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """
        Internal helper for sending raw amount (used by public methods).

        Args:
            destination_account: Destination account address
            amount_raw: Amount to send in raw units
            wait_confirmation: Whether to wait for block confirmation
            timeout: Maximum time to wait for confirmation in seconds

        Returns:
            Hash of the processed send block

        Raises:
            InvalidAccountError: If destination account is invalid
            InsufficientBalanceError: If account has insufficient balance
            InvalidAmountError: If amount is not positive or below minimum required
            RpcError: If node returns error during processing
            TimeoutException: If confirmation times out
        """
        logger.debug(
            "(Internal) Attempting to send %s raw to %s",
            amount_raw,
            destination_account,
        )

        # Guard clause: Ensure amount is positive
        if amount_raw <= 0:
            raise InvalidAmountError("Send amount must be positive.")

        # Guard clause: Check against minimum send amount configured
        if amount_raw < self.config.min_send_amount_raw:
            min_req = self.config.min_send_amount_raw
            # Attempt to provide clearer error message with Nano conversion

            min_nano = raw_to_nano(min_req)
            sent_nano = raw_to_nano(amount_raw)
            msg = (
                f"Send amount {sent_nano} Nano ({amount_raw} raw) is below the minimum configured amount "
                f"{min_nano} Nano ({min_req} raw)."
                f"Please configure the min_send_amount_raw in your WalletConfig."
            )

            raise InvalidAmountError(msg)

        # Validate destination
        if not destination_account:
            logger.error("Invalid destination account: None")
            raise InvalidAccountError("Destination can't be None")
        if not AccountHelper.validate_account(destination_account):
            logger.error("Invalid destination account format: %s", destination_account)
            raise InvalidAccountError("Invalid destination account format")

        # Get latest block parameters
        params = await self._get_block_params()

        # Calculate new balance and validate
        new_balance = params["balance"] - amount_raw
        if params["balance"] == 0 or new_balance < 0:
            msg = f"Insufficient balance for send! balance: {params['balance']} send_amount: {amount_raw}"
            logger.error(msg)
            raise InsufficientBalanceError(msg)

        # Build the block
        block = await self._build_block(
            previous=params["previous"],
            representative=params["representative"],
            balance=new_balance,
            destination_account=destination_account,
        )

        # Process the block
        block_hash = await self._process_block(
            block, f"send of {amount_raw} raw to {destination_account}"
        )

        # Wait for confirmation if requested
        if wait_confirmation:
            logger.info(
                "Send block %s processed, waiting for confirmation (timeout=%ds)...",
                block_hash,
                timeout,
            )
            confirmed = await self._wait_for_confirmation(
                block_hash, timeout=timeout, raise_on_timeout=True
            )
            if not confirmed:  # Should not happen if raise_on_timeout=True
                logger.warning("Block %s processed but confirmation failed", block_hash)
        else:
            logger.info(
                "Send block %s processed. Confirmation not requested.", block_hash
            )

        return block_hash

    @reload_after
    @handle_errors
    async def send_raw(
        self,
        destination_account: str,
        amount_raw: int | str,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """
        Send raw amount to destination account.

        Args:
            destination_account: Destination account address
            amount_raw: Amount to send in raw units
            wait_confirmation: Whether to wait for block confirmation
            timeout: Maximum time to wait for confirmation

        Returns:
            Hash of the processed send block
        """
        try:
            amount_val = int(amount_raw)
            if amount_val <= 0:
                raise InvalidAmountError("Send amount must be positive")
        except ValueError as e:
            raise InvalidAmountError(f"Invalid raw amount format: {amount_raw}") from e

        return await self._internal_send_raw(
            destination_account, amount_val, wait_confirmation, timeout
        )

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
        Send amount in NANO units to destination account.

        Args:
            destination_account: Destination account address
            amount: Amount to send in NANO units
            wait_confirmation: Whether to wait for block confirmation
            timeout: Maximum time to wait for confirmation

        Returns:
            Hash of the processed send block
        """
        # Validate and convert amount
        amount_decimal = validate_nano_amount(amount)
        amount_raw = nano_to_raw(amount_decimal)

        if amount_raw == 0 and amount_decimal > 0:
            raise InvalidAmountError(
                f"Amount {amount_decimal} Nano is too small (less than 1 raw)"
            )

        return await self._internal_send_raw(
            destination_account, amount_raw, wait_confirmation, timeout
        )

    @reload_after
    @handle_errors
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
        """
        Send raw amount with automatic retries on concurrency errors.

        Args:
            destination_account: Destination account address
            amount_raw: Amount to send in raw units
            max_retries: Maximum number of retry attempts
            retry_delay_base: Initial delay between retries in seconds
            retry_delay_backoff: Multiplier for delay between retries
            wait_confirmation: Whether to wait for block confirmation
            timeout: Maximum time to wait for confirmation

        Returns:
            Hash of the processed send block
        """
        # Validate amount
        try:
            amount_val = int(amount_raw)
            if amount_val <= 0:
                raise InvalidAmountError("Send amount must be positive")
        except ValueError:
            raise InvalidAmountError(f"Invalid raw amount format: {amount_raw}")

        retries = 0
        last_error = None

        while retries <= max_retries:
            attempt = retries + 1
            logger.debug(
                "Send attempt %s/%s for %s raw to %s",
                attempt,
                max_retries + 1,
                amount_val,
                destination_account,
            )

            try:
                # Reload state before each attempt to get latest state
                await super().reload()

                # Try to send
                block_hash = await self._internal_send_raw(
                    destination_account, amount_val, wait_confirmation, timeout
                )

                logger.info(
                    "Send attempt %s SUCCEEDED. Hash: %s",
                    attempt,
                    block_hash,
                )
                return block_hash  # Success

            except RpcError as e:
                last_error = e
                # Check if error is retryable
                is_retryable = any(
                    phrase in e.message for phrase in RETRYABLE_ERROR_MESSAGES
                )

                if is_retryable and retries < max_retries:
                    retries += 1
                    delay = retry_delay_base * (retry_delay_backoff ** (retries - 1))
                    logger.warning(
                        "Send attempt %s failed with retryable RPC error ('%s'). "
                        "Retrying (%s/%s) after %.2fs...",
                        attempt,
                        e.message,
                        retries,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue  # Try again
                else:
                    logger.error(
                        "Send attempt %s failed with RPC error ('%s') "
                        "and will not retry (retryable=%s, retries=%s).",
                        attempt,
                        e.message,
                        is_retryable,
                        retries,
                    )
                    raise e  # Fail permanently

            except (
                InsufficientBalanceError,
                InvalidAccountError,
                InvalidAmountError,
            ) as e:
                # Non-retryable errors
                last_error = e
                logger.error(
                    "Send attempt %s failed with non-retryable error: %s",
                    attempt,
                    e,
                )
                raise e  # Fail permanently

            except TimeoutException as e:
                # Confirmation timeout
                last_error = e
                logger.error(
                    "Send attempt %s failed due to confirmation timeout: %s",
                    attempt,
                    e,
                )
                raise e  # Fail permanently

            except Exception as e:
                # Unexpected errors
                last_error = e
                logger.error(
                    "Send attempt %s failed with unexpected error: %s",
                    attempt,
                    e,
                )

                if not isinstance(e, NanoException):
                    raise NanoException(
                        f"Unexpected error during send attempt: {e}",
                        "UNEXPECTED_SEND_ERROR",
                    ) from e
                else:
                    raise e  # Re-raise if already a NanoException

        # If we get here, all retries failed
        logger.error(
            "Send failed after %s attempts. Last error: %s",
            max_retries + 1,
            last_error,
        )

        if last_error:
            raise last_error  # Re-raise the last error
        else:
            # Should not reach here if we made at least one attempt
            raise NanoException(
                f"Send failed after {max_retries+1} attempts.", "MAX_RETRIES_EXCEEDED"
            ) from e

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
        Send amount in NANO units with automatic retries on concurrency errors.

        Args:
            destination_account: Destination account address
            amount: Amount to send in NANO units
            max_retries: Maximum number of retry attempts
            retry_delay_base: Initial delay between retries in seconds
            retry_delay_backoff: Multiplier for delay between retries
            wait_confirmation: Whether to wait for block confirmation
            timeout: Maximum time to wait for confirmation

        Returns:
            Hash of the processed send block
        """
        # Validate and convert amount
        amount_decimal = validate_nano_amount(amount)
        amount_raw = nano_to_raw(amount_decimal)

        if amount_raw == 0 and amount_decimal > 0:
            raise InvalidAmountError(
                f"Amount {amount_decimal} Nano is too small (less than 1 raw)"
            )

        # Call the raw retry version
        result = await self.send_raw_with_retry(
            destination_account,
            amount_raw,
            max_retries=max_retries,
            retry_delay_base=retry_delay_base,
            retry_delay_backoff=retry_delay_backoff,
            wait_confirmation=wait_confirmation,
            timeout=timeout,
        )

        return result  # The result is unwrapped by the handle_errors decorator

    @reload_after
    @handle_errors
    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> ReceivedBlock:
        """
        Receive a specific pending block by its hash.

        Args:
            block_hash: Hash of the pending block to receive
            wait_confirmation: Whether to wait for block confirmation
            timeout: Maximum time to wait for confirmation

        Returns:
            ReceivedBlock object with details of the received block
        """
        logger.debug(
            "Starting receive_by_hash for block %s, wait_confirmation=%s, timeout=%s",
            block_hash,
            wait_confirmation,
            timeout,
        )

        try:
            # Get info about the send block
            send_block_info = await self._block_info(block_hash)
            amount_raw = int(send_block_info["amount"])
            source_account = send_block_info["block_account"]
            logger.debug(
                "Block %s is a send of %s raw from %s",
                block_hash,
                amount_raw,
                source_account,
            )

            # Get parameters for the receive block
            params = await self._get_block_params()
            new_balance = params["balance"] + amount_raw
            logger.debug("Building receive block with new_balance=%s", new_balance)

            # Build and process the receive block
            block = await self._build_block(
                previous=params["previous"],
                representative=params["representative"],
                balance=new_balance,
                source_hash=block_hash,
            )

            received_hash = await self._process_block(
                block, f"receive of {amount_raw} raw from block {block_hash}"
            )

            logger.debug("Receive block processed with hash %s", received_hash)

            # Wait for confirmation if requested
            confirmed = False
            if wait_confirmation:
                logger.info(
                    "Receive block %s processed, waiting for confirmation (timeout=%ds)...",
                    received_hash,
                    timeout,
                )
                confirmed = await self._wait_for_confirmation(
                    received_hash, timeout=timeout, raise_on_timeout=True
                )
                logger.info("Receive block %s confirmed: %s", received_hash, confirmed)

            # Return the result
            return ReceivedBlock(
                block_hash=received_hash,
                amount_raw=amount_raw,
                source=source_account,
                confirmed=confirmed,
            )

        except BlockNotFoundError as e:
            logger.error("Failed to receive block %s: Send block not found", block_hash)
            raise e
        except Exception as e:
            logger.exception(
                "Exception during receive_by_hash for block %s", block_hash
            )
            raise e

    @reload_after
    @handle_errors
    async def receive_all(
        self,
        threshold_raw: Optional[int] = None,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> List[ReceivedBlock]:
        """
        Receive all pending blocks above the threshold.

        Args:
            threshold_raw: Minimum amount to receive in raw units
            wait_confirmation: Whether to wait for block confirmations
            timeout: Maximum time to wait for each block confirmation

        Returns:
            List of ReceivedBlock objects with details of all received blocks
        """
        # Determine threshold description for logging
        threshold_desc = (
            f"{threshold_raw} raw"
            if threshold_raw is not None
            else f"config default ({self.config.min_receive_threshold_raw} raw)"
        )
        logger.info(
            "Starting receive_all (threshold=%s, wait_confirmation=%s)",
            threshold_desc,
            wait_confirmation,
        )

        # Pass threshold_raw (which might be None) to list_receivables
        receivables_result = await self.list_receivables(threshold_raw=threshold_raw)
        receivables = receivables_result.unwrap()

        if not receivables:
            logger.info("No receivable blocks found matching criteria.")
            return []

        logger.info("Found %s receivable blocks to process.", len(receivables))
        processed_blocks = []

        # Process each receivable block
        for receivable in receivables:
            logger.debug(
                "Attempting to receive block %s (%s raw)",
                receivable.block_hash,
                receivable.amount_raw,
            )

            try:
                receive_result = await self.receive_by_hash(
                    receivable.block_hash,
                    wait_confirmation=wait_confirmation,
                    timeout=timeout,
                )

                processed_block = (
                    receive_result.unwrap()
                )  # Explicitly unwrap the result
                logger.info(
                    "Successfully received block %s -> new block %s",
                    receivable.block_hash,
                    processed_block.block_hash,
                )
                processed_blocks.append(processed_block)

            except Exception as e:
                # Log error but continue with other blocks
                logger.error(
                    "Failed to receive block %s: %s", receivable.block_hash, str(e)
                )
                # Option: Could re-raise here to stop on first error
                raise NanoException(str(e), "RECEIVE_BLOCK_ERROR") from e

        logger.info(
            "Receive_all finished. Successfully processed %s blocks.",
            len(processed_blocks),
        )
        return processed_blocks

    @reload_after
    @handle_errors
    async def sweep(
        self,
        destination_account: str,
        sweep_pending: bool = True,
        threshold_raw: Optional[int] = None,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> str:
        """
        Receive all pending funds and send all balance to destination account.

        Args:
            destination_account: Account to send funds to
            sweep_pending: Whether to receive pending blocks first
            threshold_raw: Minimum amount to consider for receiving (in raw). If None, uses config.min_receive_threshold_raw.
            wait_confirmation: Whether to wait for block confirmation
            timeout: Maximum time to wait for confirmation

        Returns:
            Hash of the send block
        """
        # Determine threshold description for logging
        threshold_desc = (
            f"{threshold_raw} raw"
            if threshold_raw is not None
            else f"config default ({self.config.min_receive_threshold_raw} raw)"
        )
        logger.info(
            "Starting sweep to %s (sweep_pending=%s, threshold=%s)",
            destination_account,
            sweep_pending,
            threshold_desc,
        )

        if not AccountHelper.validate_account(destination_account):
            raise InvalidAccountError("Invalid destination account for sweep")

        if sweep_pending:
            logger.info("Sweep: Attempting to receive pending blocks first.")
            try:
                # Pass threshold_raw (which might be None) to receive_all
                await self.receive_all(
                    threshold_raw=threshold_raw,
                    wait_confirmation=False,
                    timeout=timeout,
                )
                logger.info(
                    "Sweep: Pending blocks received successfully (or none to receive)."
                )
                await super().reload()  # Reload state after potentially receiving blocks
            except Exception as e:
                logger.warning("Sweep: Error receiving some pending blocks: %s", str(e))
                # Continue with sweeping the existing balance

        # Get current balance
        current_balance_raw = self._balance_info.balance_raw
        if current_balance_raw <= 0:
            logger.warning(
                "Sweep: No balance to sweep (Balance: %d raw).", current_balance_raw
            )
            raise InsufficientBalanceError("No balance to sweep.")

        logger.info(
            "Sweep: Sending balance of %d raw to %s",
            current_balance_raw,
            destination_account,
        )

        # Send the entire balance
        try:
            send_result = await self.send_raw_with_retry(
                destination_account=destination_account,
                amount_raw=current_balance_raw,
                wait_confirmation=wait_confirmation,
                timeout=timeout,
            )
            final_hash = send_result.unwrap()  # Explicitly unwrap the result

            logger.info("Sweep successful. Sent block hash: %s", final_hash)
            return final_hash

        except Exception as e:
            logger.error("Sweep failed: Error during send: %s", str(e))
            if isinstance(e, NanoException):
                raise
            raise NanoException(
                f"Sweep failed during send: {e}", "SWEEP_SEND_ERROR"
            ) from e

    @handle_errors
    async def refund_first_sender(self, wait_confirmation: bool = False) -> str:
        """
        Send all funds back to the account that sent the first receivable.

        Args:
            wait_confirmation: Whether to wait for block confirmation

        Returns:
            Hash of the processed send block
        """
        # Ensure we have up-to-date state
        await super().reload()

        # Check if we have balance
        if (
            self._balance_info.balance_raw <= 0
            and self._balance_info.receivable_raw <= 0
        ):
            raise InsufficientBalanceError("No funds available to refund.")

        refund_account = None

        # Try to get the sender from the open block
        if self._account_info and self._account_info.open_block:
            try:
                open_block_info = await self._block_info(self._account_info.open_block)
                refund_account = open_block_info.get("source_account")
            except Exception as e:
                logger.warning(
                    "Could not determine refund account from open block: %s", str(e)
                )

        # If we couldn't get it from the open block, try the first receivable
        if not refund_account:
            try:
                receivables_result = await self.list_receivables()
                receivables = receivables_result.unwrap()

                if receivables:
                    first_receivable = receivables[0]
                    block_info = await self._block_info(first_receivable.block_hash)
                    refund_account = block_info.get("block_account")
            except Exception as e:
                logger.warning(
                    "Could not determine refund account from receivables: %s", str(e)
                )

        # If we still don't have a refund account, we can't proceed
        if not AccountHelper.validate_account(refund_account):
            raise InvalidAccountError(
                f"Determined refund account is invalid: {refund_account}"
            )

        # Sweep funds to the refund account
        logger.info("Refunding all funds to %s", refund_account)
        sweep_result = await self.sweep(
            destination_account=refund_account,
            sweep_pending=True,
            wait_confirmation=wait_confirmation,
        )

        # Unwrap the result
        refund_hash = sweep_result.unwrap()
        logger.info("Refund successful. Block hash: %s", refund_hash)
        return refund_hash

    def to_string(self) -> str:
        """
        Generate a human-readable representation of the wallet state.

        Returns:
            Detailed string representation of the wallet
        """
        balance_nano = raw_to_nano(self._balance_info.balance_raw)
        receivable_nano = raw_to_nano(self._balance_info.receivable_raw)
        weight_nano = (
            raw_to_nano(self._account_info.weight_raw) if self._account_info else "N/A"
        )
        rep = self._account_info.representative if self._account_info else "N/A"
        conf_height = (
            self._account_info.confirmation_height if self._account_info else "N/A"
        )
        block_count = self._account_info.block_count if self._account_info else "N/A"

        return (
            f"NanoWalletAuthenticated:\n"
            f"  Account: {self.account}\n"
            f"  Balance: {balance_nano} Nano ({self._balance_info.balance_raw} raw)\n"
            f"  Receivable: {receivable_nano} Nano ({self._balance_info.receivable_raw} raw)\n"
            f"  Voting Weight: {weight_nano} Nano ({getattr(self._account_info, 'weight_raw', 'N/A')} raw)\n"
            f"  Representative: {rep}\n"
            f"  Confirmation Height: {conf_height}\n"
            f"  Block Count: {block_count}"
        )

    def __str__(self) -> str:
        """
        Generate a simplified string representation of the wallet.

        Returns:
            Simple string representation of the wallet
        """
        return (
            f"NanoWalletAuthenticated: Account={self.account}, "
            f"BalanceRaw={self._balance_info.balance_raw}, "
            f"ReceivableRaw={self._balance_info.receivable_raw}"
        )

    async def _internal_refund_receivable(
        self, receivable_hash: str, wait_confirmation: bool, timeout: int
    ) -> RefundDetail:
        """Internal logic to refund a single receivable block hash (simplified)."""
        logger.debug(
            "Simplified internal refund processing for receivable: %s", receivable_hash
        )
        receive_hash: Optional[str] = None
        refund_hash: Optional[str] = None
        source_account: Optional[str] = None
        amount_raw: int = 0
        status: RefundStatus = RefundStatus.INITIATED
        error_message: Optional[str] = None
        received_block: Optional[ReceivedBlock] = None  # Keep track if receive succeeds

        try:
            # Step 1: Receive the block. This internally handles getting block info first.
            logger.debug("Attempting receive for refund: %s", receivable_hash)
            receive_result = await self.receive_by_hash(
                receivable_hash,
                wait_confirmation=wait_confirmation,  # Pass confirmation flag
                timeout=timeout,
            )
            # If receive_by_hash failed internally (e.g., block not found, RPC error), unwrap will raise
            received_block = receive_result.unwrap()

            # If receive succeeded:
            receive_hash = received_block.block_hash
            amount_raw = received_block.amount_raw
            source_account = received_block.source  # Get sender from the result
            if source_account == self.account:
                logger.info(
                    "Received block %s -> new block %s. Source: %s, Amount: %s raw",
                    receivable_hash,
                    receive_hash,
                    source_account,
                    amount_raw,
                )
                return RefundDetail(
                    receivable_hash=receivable_hash,
                    amount_raw=amount_raw,
                    source_account=source_account,
                    status=RefundStatus.SKIPPED,
                    error_message="Refunding to self",
                )

            logger.info(
                "Received block %s -> new block %s. Source: %s, Amount: %s raw",
                receivable_hash,
                receive_hash,
                source_account,
                amount_raw,
            )

            # Basic validation after receive (optional, but good practice)
            if not source_account or not AccountHelper.validate_account(source_account):
                raise InvalidAccountError(
                    f"Invalid source account obtained after receive: {source_account}"
                )
            if amount_raw <= 0:
                raise InvalidAmountError(
                    f"Non-positive amount obtained after receive: {amount_raw}"
                )

            # Step 2: Send the refund using info from the received block
            logger.debug(
                "Attempting refund send to %s for %s raw", source_account, amount_raw
            )
            send_result = await self.send_raw(
                destination_account=source_account,
                amount_raw=amount_raw,
                wait_confirmation=wait_confirmation,  # Pass confirmation flag
                timeout=timeout,
            )
            # If send failed, unwrap will raise
            refund_hash = send_result.unwrap()
            status = RefundStatus.SUCCESS
            logger.info(
                "Successfully refunded %s raw to %s. Refund block hash: %s",
                amount_raw,
                source_account,
                refund_hash,
            )

        except (
            BlockNotFoundError,
            InvalidAccountError,
            InvalidAmountError,
            InsufficientBalanceError,
            RpcError,
            TimeoutException,
            NanoException,
        ) as e:
            # Determine status based on whether receive succeeded
            if (
                received_block is None
            ):  # Failed during receive_by_hash or validation right after
                status = RefundStatus.RECEIVE_FAILED
                error_message = (
                    f"Failed to receive block or invalid data retrieved: {e.message}"
                )
                logger.error("%s (receivable_hash: %s)", error_message, receivable_hash)
                # Try to populate amount/source for the report if possible (best effort)
                if (
                    isinstance(e, (InvalidAccountError, InvalidAmountError))
                    and source_account
                ):
                    # source_account might be set but invalid
                    pass
                elif status == RefundStatus.RECEIVE_FAILED and amount_raw == 0:
                    # Attempt to get info directly if receive failed early
                    try:
                        logger.debug(
                            "Attempting block info lookup after receive failure: %s",
                            receivable_hash,
                        )
                        block_info = await self._block_info(receivable_hash)
                        amount_raw = int(block_info.get("amount", 0))
                        source_account = block_info.get("block_account")
                    except Exception as info_e:
                        logger.warning(
                            "Could not retrieve block info after receive failure for %s: %s",
                            receivable_hash,
                            info_e,
                        )
            else:  # Failed during send_raw
                status = RefundStatus.SEND_FAILED
                error_message = f"Failed to send refund: {e.message}"
                logger.error(
                    "%s (dest: %s, amount: %s)",
                    error_message,
                    source_account,
                    amount_raw,
                )

            # Add error code if available
            if hasattr(e, "code") and e.code:
                error_message = f"[{e.code}] {error_message}"

        except Exception as e:
            # Catch any other unexpected errors
            status = RefundStatus.UNEXPECTED_ERROR
            error_message = (
                f"Unexpected error processing refund for {receivable_hash}: {e}"
            )
            logger.exception(error_message)  # Log with stack trace

        # Return final detail for this receivable
        return RefundDetail(
            receivable_hash=receivable_hash,
            amount_raw=amount_raw,  # Best effort
            source_account=source_account,  # Best effort
            status=status,
            receive_hash=receive_hash,  # Populated if receive step succeeded
            refund_hash=refund_hash,  # Populated if send step succeeded
            error_message=error_message,
        )

    @reload_after
    @handle_errors
    async def refund_receivable_by_hash(
        self, receivable_hash: str, wait_confirmation: bool = False, timeout: int = 30
    ) -> RefundDetail:
        """
        Receives a specific pending block and immediately refunds the amount to the sender.

        Args:
            receivable_hash: The hash of the send block to receive and refund.
            wait_confirmation: Whether to wait for network confirmation for receive and send blocks.
            timeout: Timeout in seconds for waiting for confirmation.

        Returns:
            A RefundDetail object detailing the refund attempt.
        """
        logger.info("Starting refund_receivable_by_hash for block %s", receivable_hash)

        # Call the internal method that contains the core logic
        result_detail = await self._internal_refund_receivable(
            receivable_hash=receivable_hash,
            wait_confirmation=wait_confirmation,
            timeout=timeout,
        )
        return result_detail

    @handle_errors
    async def refund_all_receivables(
        self,
        threshold_raw: Optional[int] = None,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> List[RefundDetail]:
        """
        Receives all pending blocks above a threshold and immediately refunds each amount to its sender.

        Args:
            threshold_raw: The minimum amount in raw units to be considered for refund.
            wait_confirmation: Whether to wait for network confirmation for receive and send blocks.
            timeout: Timeout in seconds for waiting for confirmation.

        Returns:
            List of refund details with status
        """
        # Determine threshold description for logging
        threshold_desc = (
            f"{threshold_raw} raw"
            if threshold_raw is not None
            else f"config default ({self.config.min_receive_threshold_raw} raw)"
        )
        logger.info(
            "Starting refund_all_receivables (threshold=%s, wait_confirmation=%s)",
            threshold_desc,
            wait_confirmation,
        )

        # Pass threshold_raw (which might be None) to list_receivables
        list_result = await self.list_receivables(threshold_raw=threshold_raw)
        receivables = list_result.unwrap()

        if not receivables:
            logger.info("No receivable blocks found matching criteria for refund.")
            return []

        logger.info("Found %s receivable blocks to attempt refund.", len(receivables))
        refund_results: List[RefundDetail] = []

        for receivable in receivables:
            # Call the internal refund logic for each receivable hash
            # Note: This processes refunds sequentially. Reloading state between each refund
            # might be necessary if subsequent sends depend on the state change from the previous receive/send cycle.
            detail = await self._internal_refund_receivable(
                receivable_hash=receivable.block_hash,
                wait_confirmation=wait_confirmation,
                timeout=timeout,
            )
            refund_results.append(detail)
            # Optional: Add a small delay between refunds if needed
            # await asyncio.sleep(0.1)

        logger.info(
            "refund_all_receivables finished. Processed %s blocks.", len(receivables)
        )
        return refund_results
