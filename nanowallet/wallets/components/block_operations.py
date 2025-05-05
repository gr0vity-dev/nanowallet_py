import asyncio
import time
import logging
from typing import Optional, Dict, Any
from decimal import Decimal

from .rpc_component import RpcComponent
from .state_manager import StateManager
from ...libs.block import NanoWalletBlock
from ...libs.account_helper import AccountHelper
from ...models import (
    WalletConfig,
    ReceivedBlock,
)
from ...errors import (
    BlockNotFoundError,
    InsufficientBalanceError,
    InvalidAccountError,
    TimeoutException,
    RpcError,
    InvalidAmountError,
    NanoException,
    account_not_found,
    no_error,
    try_raise_error,
)
from ...utils.conversion import raw_to_nano, nano_to_raw
from ...utils.validation import validate_nano_amount

logger = logging.getLogger(__name__)

ZERO_HASH = "0" * 64
RETRYABLE_ERROR_MESSAGES = ["Fork", "gap previous", "old block"]


class BlockOperations:
    """Handles authenticated operations like sending, receiving, sweeping."""

    def __init__(
        self,
        account: str,
        private_key: str,
        config: WalletConfig,
        rpc_component: RpcComponent,
        state_manager: StateManager,
    ):
        self.account = account
        self.private_key = private_key
        self.config = config
        self._rpc_component = rpc_component
        self._state_manager = state_manager
        logger.debug("BlockOperations initialized for account: %s", self.account)

    # --- Internal Helper Methods ---

    async def _get_block_params(self) -> Dict[str, Any]:
        """Gets parameters needed to build the next block (previous, balance, representative)."""
        logger.debug("BlockOperations: Getting block parameters for %s", self.account)
        try:
            # Use RpcComponent to fetch live info, ignore local state_manager state here
            # as this needs the absolute latest frontier/representative from the node.
            account_info_response = await self._rpc_component.fetch_account_info(
                self.account
            )

            if account_not_found(account_info_response):
                # Check receivable state via state_manager
                has_receivables = bool(self._state_manager.receivable_blocks)
                if has_receivables:
                    logger.debug(
                        "BlockOperations: Account %s not found but has receivables",
                        self.account,
                    )
                    # Open block case
                    return {
                        "previous": ZERO_HASH,
                        "balance": 0,
                        "representative": self.config.default_representative,
                    }
                else:
                    # Account truly unopened or empty
                    logger.debug(
                        "BlockOperations: Account %s not found and no receivables",
                        self.account,
                    )
                    return {
                        "previous": ZERO_HASH,
                        "balance": 0,
                        "representative": self.config.default_representative,
                    }
            elif no_error(account_info_response):
                logger.debug(
                    "BlockOperations: Retrieved block params: balance=%s, frontier=%s...",
                    account_info_response["balance"],
                    account_info_response["frontier"][:10],
                )
                return {
                    "previous": account_info_response["frontier"],
                    "balance": int(account_info_response["balance"]),
                    "representative": account_info_response["representative"],
                }
            else:
                # Handle RPC errors
                logger.error(
                    "BlockOperations: Failed to get block params: %s",
                    account_info_response.get("error"),
                )
                try_raise_error(account_info_response)
                # Should not be reached if try_raise_error works
                raise NanoException(
                    "Unknown error fetching block params", "PARAMS_ERROR"
                )
        except Exception as e:
            logger.exception(
                "BlockOperations: Failed to get block parameters for %s", self.account
            )
            if isinstance(e, NanoException):
                raise
            raise NanoException(
                f"Failed to get block parameters: {e}", "PARAMS_ERROR"
            ) from e

    async def _build_block(
        self,
        previous: str,
        representative: str,
        balance: int,
        source_hash: Optional[str] = None,
        destination_account: Optional[str] = None,
    ) -> NanoWalletBlock:
        """Build a new block with the given parameters."""
        logger.debug(
            "Building block: prev=%s, rep=%s, bal=%d, src=%s, dest=%s",
            previous[:10] + "...",
            representative[:10] + "...",
            balance,
            source_hash,
            destination_account,
        )

        block = NanoWalletBlock(
            account=self.account,
            previous=previous,
            representative=representative,
            balance=balance,
            source_hash=source_hash,
            destination_account=destination_account,
        )

        block.sign(self.private_key)
        logger.debug("Block signed. Work block hash: %s...", block.work_block_hash[:10])

        work = await self._rpc_component.generate_work(
            block.work_block_hash, use_peers=self.config.use_work_peers
        )
        block.set_work(work)
        logger.debug("Work generated and set: %s", work)

        return block

    async def _process_block(self, block: NanoWalletBlock, operation_desc: str) -> str:
        """Processes a prepared block via RPC."""
        logger.debug(
            "BlockOperations: Processing block for operation: %s", operation_desc
        )
        block_dict = block.to_dict()
        # Process block using RpcComponent
        block_hash = await self._rpc_component.process_block(block_dict)
        logger.debug(
            "BlockOperations: Successfully processed %s, hash: %s",
            operation_desc,
            block_hash,
        )
        return block_hash

    async def _wait_for_confirmation(
        self, block_hash: str, timeout: int = 30, raise_on_timeout: bool = False
    ) -> bool:
        """Waits for a block to be confirmed by the network."""
        start_time = time.time()
        delay = 0.5
        max_delay = 5
        attempt = 1
        logger.debug(
            "BlockOperations: Starting confirmation wait for %s with timeout=%s",
            block_hash,
            timeout,
        )
        while time.time() - start_time < timeout:
            try:
                # Check block info using RpcComponent
                block_info = await self._rpc_component.block_info(block_hash)
                confirmed = block_info.get("confirmed", "false") == "true"
                elapsed = time.time() - start_time
                logger.debug(
                    "BlockOperations: Confirmation check attempt %d: hash=%s confirmed=%s, elapsed=%.2fs",
                    attempt,
                    block_hash[:10] + "...",
                    confirmed,
                    elapsed,
                )
                if confirmed:
                    logger.info(
                        "BlockOperations: Block %s confirmed after %.2fs",
                        block_hash,
                        elapsed,
                    )
                    return True
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                attempt += 1
            except BlockNotFoundError:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(
                        "BlockOperations: Block %s not found and timeout reached",
                        block_hash,
                    )
                    break
                logger.debug(
                    "BlockOperations: Block %s not found on attempt %d, retrying after %.2f seconds",
                    block_hash[:10] + "...",
                    attempt,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                attempt += 1
            except Exception as e:  # Catch broader exceptions during check
                logger.exception(
                    "BlockOperations: Error during confirmation check for %s: %s",
                    block_hash,
                    e,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                attempt += 1

        elapsed = time.time() - start_time
        logger.warning(
            "BlockOperations: Confirmation wait timed out after %.2fs for %s",
            elapsed,
            block_hash,
        )
        if raise_on_timeout:
            raise TimeoutException(
                f"Block {block_hash} not confirmed within {timeout} seconds"
            )
        return False

    # --- Public Authenticated Operations ---

    async def send_raw(
        self,
        destination_account: str,
        amount_raw: int | str,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """Sends an amount in raw units."""
        try:
            amount_val = int(amount_raw)
        except ValueError as e:
            raise InvalidAmountError(f"Invalid raw amount format: {amount_raw}") from e

        logger.debug(
            "BlockOperations: Attempting to send %s raw to %s",
            amount_val,
            destination_account,
        )

        if amount_val <= 0:
            raise InvalidAmountError("Send amount must be positive.")
        if amount_val < self.config.min_send_amount_raw:
            min_req = self.config.min_send_amount_raw
            min_nano = raw_to_nano(min_req)
            sent_nano = raw_to_nano(amount_val)
            msg = (
                f"Send amount {sent_nano} Nano ({amount_val} raw) is below the minimum "
                f"configured amount {min_nano} Nano ({min_req} raw). "
                f"Please configure the min_send_amount_raw in your WalletConfig."
            )
            raise InvalidAmountError(msg)

        if not destination_account:
            logger.error("BlockOperations: Invalid destination account: None")
            raise InvalidAccountError("Destination can't be None")
        if not AccountHelper.validate_account(destination_account):
            logger.error(
                "BlockOperations: Invalid destination account format: %s",
                destination_account,
            )
            raise InvalidAccountError("Invalid destination account format")

        # Get latest block parameters (includes current balance)
        params = await self._get_block_params()
        current_balance_raw = params["balance"]
        new_balance = current_balance_raw - amount_val

        if current_balance_raw == 0 or new_balance < 0:
            msg = (
                f"Insufficient balance for send! Current balance: {current_balance_raw} raw, "
                f"trying to send: {amount_val} raw"
            )
            logger.error("BlockOperations: %s", msg)
            raise InsufficientBalanceError(msg)

        # Build, process, and potentially wait for confirmation
        block = await self._build_block(
            previous=params["previous"],
            representative=params["representative"],
            balance=new_balance,
            destination_account=destination_account,
        )
        operation_desc = f"send of {amount_val} raw to {destination_account}"
        block_hash = await self._process_block(block, operation_desc)

        if wait_confirmation:
            logger.info(
                "BlockOperations: Send block %s processed, waiting for confirmation (timeout=%ds)...",
                block_hash,
                timeout,
            )
            confirmed = await self._wait_for_confirmation(
                block_hash, timeout=timeout, raise_on_timeout=True
            )
            # raise_on_timeout=True means we don't need to check 'confirmed' variable here
            logger.info("BlockOperations: Send block %s confirmed.", block_hash)
        else:
            logger.info(
                "BlockOperations: Send block %s processed. Confirmation not requested.",
                block_hash,
            )

        return block_hash

    async def send(
        self,
        destination_account: str,
        amount: Decimal | str | int,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """Sends an amount in Nano units."""
        amount_decimal = validate_nano_amount(amount)
        amount_raw = nano_to_raw(amount_decimal)
        if amount_raw == 0 and amount_decimal > 0:
            raise InvalidAmountError(
                f"Amount {amount_decimal} Nano is too small (less than 1 raw)"
            )
        # Delegate to raw version
        return await self.send_raw(
            destination_account, amount_raw, wait_confirmation, timeout
        )

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
        """Sends raw amount with retry logic for specific RPC errors."""
        try:
            amount_val = int(amount_raw)
            if amount_val <= 0:
                raise InvalidAmountError("Send amount must be positive")
        except ValueError:
            raise InvalidAmountError(f"Invalid raw amount format: {amount_raw}")

        retries = 0
        last_error: Optional[Exception] = None
        while retries <= max_retries:
            attempt = retries + 1
            logger.debug(
                "BlockOperations: Send attempt %s/%s for %s raw to %s",
                attempt,
                max_retries + 1,
                amount_val,
                destination_account,
            )
            try:
                # Directly call send_raw (which includes checks and block building)
                block_hash = await self.send_raw(
                    destination_account, amount_val, wait_confirmation, timeout
                )
                logger.info(
                    "BlockOperations: Send attempt %s SUCCEEDED. Hash: %s",
                    attempt,
                    block_hash,
                )
                return block_hash
            except RpcError as e:
                last_error = e
                is_retryable = any(
                    phrase in e.message for phrase in RETRYABLE_ERROR_MESSAGES
                )
                if is_retryable and retries < max_retries:
                    retries += 1
                    delay = retry_delay_base * (retry_delay_backoff ** (retries - 1))
                    logger.warning(
                        "BlockOperations: Send attempt %s failed with retryable RPC error ('%s'). "
                        "Retrying (%s/%s) after %.2fs...",
                        attempt,
                        e.message,
                        retries,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    # NOTE: We don't manually reload state here. send_raw calls _get_block_params
                    # which fetches live data, effectively retrying with fresh info.
                    continue
                else:
                    logger.error(
                        "BlockOperations: Send attempt %s failed with RPC error ('%s') and "
                        "will not retry (retryable=%s, retries=%s).",
                        attempt,
                        e.message,
                        is_retryable,
                        retries,
                    )
                    raise e  # Re-raise the non-retryable or max-retries-exceeded error
            except (
                InsufficientBalanceError,
                InvalidAccountError,
                InvalidAmountError,
            ) as e:
                # Non-retryable errors specific to the operation logic
                last_error = e
                logger.error(
                    "BlockOperations: Send attempt %s failed with non-retryable error: %s",
                    attempt,
                    e,
                )
                raise e
            except TimeoutException as e:
                # Confirmation timeout is also not typically retryable in the same way
                last_error = e
                logger.error(
                    "BlockOperations: Send attempt %s failed due to confirmation timeout: %s",
                    attempt,
                    e,
                )
                raise e
            except Exception as e:
                # Catch unexpected errors
                last_error = e
                logger.error(
                    "BlockOperations: Send attempt %s failed with unexpected error: %s",
                    attempt,
                    e,
                    exc_info=True,
                )
                if not isinstance(e, NanoException):
                    # Wrap unexpected errors
                    raise NanoException(
                        f"Unexpected error during send attempt: {e}",
                        "UNEXPECTED_SEND_ERROR",
                    ) from e
                else:
                    raise e  # Re-raise existing NanoExceptions

        # Should only be reached if loop finishes without success (e.g., max retries exceeded on retryable error)
        logger.error(
            "BlockOperations: Send failed after %s attempts. Last error: %s",
            max_retries + 1,
            last_error,
        )
        if last_error:
            # Should have already been raised inside the loop, but as a fallback:
            raise last_error
        else:
            # Should be impossible to reach here without an error, but for completeness:
            raise NanoException(
                f"Send failed after {max_retries + 1} attempts.", "MAX_RETRIES_EXCEEDED"
            )

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
        """Sends an amount in Nano units with retry logic."""
        amount_decimal = validate_nano_amount(amount)
        amount_raw = nano_to_raw(amount_decimal)
        if amount_raw == 0 and amount_decimal > 0:
            raise InvalidAmountError(
                f"Amount {amount_decimal} Nano is too small (less than 1 raw)"
            )
        # Delegate to raw version with retry
        return await self.send_raw_with_retry(
            destination_account,
            amount_raw,
            max_retries,
            retry_delay_base,
            retry_delay_backoff,
            wait_confirmation,
            timeout,
        )

    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> ReceivedBlock:
        """Receives a specific block hash."""
        logger.debug(
            "BlockOperations: Starting receive_by_hash for block %s, wait_confirmation=%s, timeout=%s",
            block_hash,
            wait_confirmation,
            timeout,
        )
        try:
            # Get info about the send block we want to receive
            send_block_info = await self._rpc_component.block_info(block_hash)
            amount_raw = int(send_block_info["amount"])
            source_account = send_block_info[
                "block_account"
            ]  # Account that sent the block
            logger.debug(
                "BlockOperations: Block %s is a send of %s raw from %s",
                block_hash,
                amount_raw,
                source_account,
            )

            # Get our current parameters to build the receive block
            params = await self._get_block_params()
            new_balance = params["balance"] + amount_raw
            logger.debug(
                "BlockOperations: Building receive block with new_balance=%s",
                new_balance,
            )

            # Build and process the receive block
            block = await self._build_block(
                previous=params["previous"],
                representative=params[
                    "representative"
                ],  # Could use config default or existing if open block? Using existing.
                balance=new_balance,
                source_hash=block_hash,  # Link to the send block
            )
            operation_desc = f"receive of {amount_raw} raw from block {block_hash}"
            received_hash = await self._process_block(block, operation_desc)
            logger.debug(
                "BlockOperations: Receive block processed with hash %s", received_hash
            )

            confirmed = False
            if wait_confirmation:
                logger.info(
                    "BlockOperations: Receive block %s processed, waiting for confirmation (timeout=%ds)...",
                    received_hash,
                    timeout,
                )
                await self._wait_for_confirmation(
                    received_hash, timeout=timeout, raise_on_timeout=True
                )
                # If it didn't raise TimeoutException, it's confirmed
                confirmed = True
                logger.info(
                    "BlockOperations: Receive block %s confirmed.", received_hash
                )

            return ReceivedBlock(
                block_hash=received_hash,
                amount_raw=amount_raw,
                source=source_account,
                confirmed=confirmed,
            )
        except BlockNotFoundError as e:
            logger.error(
                "BlockOperations: Failed to receive block %s: Send block not found",
                block_hash,
            )
            raise e  # Re-raise specific error
        except Exception as e:
            logger.exception(
                "BlockOperations: Exception during receive_by_hash for block %s",
                block_hash,
            )
            if isinstance(e, NanoException):
                raise
            raise NanoException(
                f"Failed receive_by_hash for {block_hash}: {e}", "RECEIVE_ERROR"
            ) from e
