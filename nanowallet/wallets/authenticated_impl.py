import logging
from typing import Optional, List
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
from ..utils.conversion import raw_to_nano
from ..utils.decorators import handle_errors, reload_after
from ..errors import (
    BlockNotFoundError,
    InsufficientBalanceError,
    InvalidAccountError,
    TimeoutException,
    RpcError,
    InvalidAmountError,
    NanoException,
)

from .protocols import IAuthenticatedWallet, IReadOnlyWallet
from .components import RpcComponent, StateManager, QueryOperations, BlockOperations

# Configure logging
logger = logging.getLogger(__name__)

# Constants
RETRYABLE_ERROR_MESSAGES = [
    "Fork",  # Explicit fork detected by the node
    "gap previous",  # The 'previous' block specified isn't the frontier
    "old block",  # Another potential message for stale state
]


class NanoWalletAuthenticated(IAuthenticatedWallet, IReadOnlyWallet):
    """Authenticated wallet implementation using composition"""

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
            # Derive account first
            account = AccountHelper.get_account_address(private_key)
        except Exception as e:
            logger.error("Failed to derive account address from private key: %s", e)
            raise ValueError(f"Invalid private key provided: {e}") from e

        self.account = account
        self.private_key = private_key
        self.config = config or WalletConfig()

        # Instantiate Components
        self._rpc_component = RpcComponent(rpc)
        self._state_manager = StateManager(self.account, self._rpc_component)
        self._query_operations = QueryOperations(
            account=self.account,
            config=self.config,
            rpc_component=self._rpc_component,
            state_manager=self._state_manager,
        )
        self._block_operations = BlockOperations(
            account=self.account,
            private_key=self.private_key,
            config=self.config,
            rpc_component=self._rpc_component,
            state_manager=self._state_manager,
        )

        logger.info("Initialized NanoWalletAuthenticated for account: %s", self.account)

    # --- Delegate Read-Only Methods ---

    @handle_errors
    async def reload(self) -> None:
        """Reload wallet state using the StateManager component."""
        await self._state_manager.reload()

    @handle_errors
    async def has_balance(self) -> bool:
        """Check balance using the QueryOperations component."""
        await self.reload()  # Reload state first
        return await self._query_operations.has_balance()

    @handle_errors
    async def balance_info(self) -> WalletBalance:
        """Get balance info using the QueryOperations component."""
        await self.reload()
        return await self._query_operations.balance_info()

    @handle_errors
    async def account_info(self) -> AccountInfo:
        """Get account info using the QueryOperations component."""
        await self.reload()
        return await self._query_operations.account_info()

    @handle_errors
    async def list_receivables(
        self, threshold_raw: Optional[int] = None
    ) -> List[Receivable]:
        """List receivables using the QueryOperations component."""
        await self.reload()
        return await self._query_operations.list_receivables(
            threshold_raw=threshold_raw
        )

    @handle_errors
    async def account_history(
        self, count: Optional[int] = -1, head: Optional[str] = None
    ) -> List[Transaction]:
        """Get account history using the QueryOperations component."""
        return await self._query_operations.account_history(count=count, head=head)

    # --- Delegate Authenticated Methods ---

    @reload_after
    @handle_errors
    async def send_raw(
        self,
        destination_account: str,
        amount_raw: int | str,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """Delegate send_raw to BlockOperations."""
        return await self._block_operations.send_raw(
            destination_account, amount_raw, wait_confirmation, timeout
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
        """Delegate send to BlockOperations."""
        return await self._block_operations.send(
            destination_account, amount, wait_confirmation, timeout
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
        """Delegate send_raw_with_retry to BlockOperations."""
        return await self._block_operations.send_raw_with_retry(
            destination_account,
            amount_raw,
            max_retries,
            retry_delay_base,
            retry_delay_backoff,
            wait_confirmation,
            timeout,
        )

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
        """Delegate send_with_retry to BlockOperations."""
        return await self._block_operations.send_with_retry(
            destination_account,
            amount,
            max_retries,
            retry_delay_base,
            retry_delay_backoff,
            wait_confirmation,
            timeout,
        )

    @reload_after
    @handle_errors
    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> ReceivedBlock:
        """Delegate receive_by_hash to BlockOperations."""
        return await self._block_operations.receive_by_hash(
            block_hash, wait_confirmation, timeout
        )

    # --- Implement Orchestration Methods ---

    @reload_after
    @handle_errors
    async def receive_all(
        self,
        threshold_raw: Optional[int] = None,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> List[ReceivedBlock]:
        """Receive all pending blocks above the threshold."""
        threshold_desc = (
            f"{threshold_raw} raw"
            if threshold_raw is not None
            else f"config default ({self.config.min_receive_threshold_raw} raw)"
        )
        logger.info(
            "NanoWalletAuthenticated: Starting receive_all (threshold=%s, wait_confirmation=%s)",
            threshold_desc,
            wait_confirmation,
        )

        # 1. List receivables
        try:
            await self.reload()  # Ensure state is fresh before listing
            receivables = await self._query_operations.list_receivables(
                threshold_raw=threshold_raw
            )
        except Exception as e:
            logger.error(
                "NanoWalletAuthenticated: Failed to list receivables during receive_all: %s",
                e,
            )
            raise NanoException(
                f"Failed to list receivables for receive_all: {e}",
                "LIST_RECEIVABLES_ERROR",
            ) from e

        if not receivables:
            logger.info(
                "NanoWalletAuthenticated: No receivable blocks found matching criteria."
            )
            return []

        logger.info(
            "NanoWalletAuthenticated: Found %s receivable blocks to process.",
            len(receivables),
        )
        processed_blocks: List[ReceivedBlock] = []
        errors_encountered = []

        # 2. Iterate and call receive_by_hash for each
        for receivable in receivables:
            logger.debug(
                "NanoWalletAuthenticated: Attempting to receive block %s (%s raw)",
                receivable.block_hash,
                receivable.amount_raw,
            )
            try:
                processed_block = await self._block_operations.receive_by_hash(
                    receivable.block_hash,
                    wait_confirmation=wait_confirmation,
                    timeout=timeout,
                )
                logger.info(
                    "NanoWalletAuthenticated: Successfully received block %s -> new block %s",
                    receivable.block_hash,
                    processed_block.block_hash,
                )
                processed_blocks.append(processed_block)
            except Exception as e:
                # Log error but continue processing others
                logger.error(
                    "NanoWalletAuthenticated: Failed to receive block %s during receive_all: %s",
                    receivable.block_hash,
                    str(e),
                )
                errors_encountered.append(f"Hash {receivable.block_hash}: {str(e)}")

        if errors_encountered:
            # TODO, add warnings instead of raising exceptions when len(processed_blocks) > 0:
            raise NanoException(
                f"""NanoWalletAuthenticated: receive_all finished with
{len(processed_blocks)} blocks processed.
{len(errors_encountered)} errors :
{"\n".join(errors_encountered)}""",
                "RECEIVE_ALL_ERROR",
            )

        logger.info(
            "NanoWalletAuthenticated: Receive_all finished. Successfully processed %s blocks.",
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
        """Sweep all funds to the destination address."""
        threshold_desc = (
            f"{threshold_raw} raw"
            if threshold_raw is not None
            else f"config default ({self.config.min_receive_threshold_raw} raw)"
        )
        logger.info(
            "NanoWalletAuthenticated: Starting sweep to %s (sweep_pending=%s, threshold=%s)",
            destination_account,
            sweep_pending,
            threshold_desc,
        )

        if not AccountHelper.validate_account(destination_account):
            raise InvalidAccountError("Invalid destination account for sweep")

        # 1. Optionally receive pending first
        if sweep_pending:
            logger.info("Sweep: Attempting to receive pending blocks first.")
            try:
                await self.receive_all(
                    threshold_raw=threshold_raw,
                    wait_confirmation=False,
                    timeout=timeout,
                )
                logger.info(
                    "Sweep: Pending blocks processed. Reloading state before send."
                )
                await self.reload()  # Explicit reload after receive_all finishes
            except Exception as e:
                # Log warning but continue sweep attempt
                logger.warning(
                    "Sweep: Error receiving some pending blocks, proceeding with sweep anyway: %s",
                    str(e),
                )
                await self.reload()  # Reload even if receive_all failed

        # 2. Check current balance
        current_balance_raw = self._state_manager.balance_info.balance_raw
        if current_balance_raw <= 0:
            logger.warning(
                "Sweep: No balance to sweep (Balance: %d raw).", current_balance_raw
            )
            raise InsufficientBalanceError("No balance to sweep.")

        # 3. Send the entire balance
        logger.info(
            "Sweep: Sending balance of %d raw to %s",
            current_balance_raw,
            destination_account,
        )
        try:
            # Use retry version for robustness
            final_hash = await self._block_operations.send_raw_with_retry(
                destination_account=destination_account,
                amount_raw=current_balance_raw,
                wait_confirmation=wait_confirmation,
                timeout=timeout,
            )
            logger.info("Sweep successful. Sent block hash: %s", final_hash)
            return final_hash
        except Exception as e:
            logger.error("Sweep failed: Error during send: %s", str(e))
            if isinstance(e, NanoException):
                raise  # Re-raise known Nano exceptions
            # Wrap unexpected errors
            raise NanoException(
                f"Sweep failed during send: {e}", "SWEEP_SEND_ERROR"
            ) from e

    async def _internal_refund_receivable(
        self, receivable_hash: str, wait_confirmation: bool, timeout: int
    ) -> RefundDetail:
        """Internal logic to receive a block and send it back to its source."""
        logger.debug(
            "NanoWalletAuthenticated: Internal refund processing for receivable: %s",
            receivable_hash,
        )
        receive_hash: Optional[str] = None
        refund_hash: Optional[str] = None
        source_account: Optional[str] = None
        amount_raw: int = 0
        status: RefundStatus = RefundStatus.INITIATED
        error_message: Optional[str] = None
        received_block: Optional[ReceivedBlock] = None

        try:
            # 1. Receive the block
            logger.debug(
                "Refund Internal: Attempting receive for refund: %s", receivable_hash
            )
            received_block = await self._block_operations.receive_by_hash(
                receivable_hash, wait_confirmation=wait_confirmation, timeout=timeout
            )
            receive_hash = received_block.block_hash
            amount_raw = received_block.amount_raw
            source_account = received_block.source
            logger.info(
                "Refund Internal: Received block %s -> new block %s. Source: %s, Amount: %s raw",
                receivable_hash,
                receive_hash,
                source_account,
                amount_raw,
            )

            # 2. Validate received info
            if not source_account or not AccountHelper.validate_account(source_account):
                raise InvalidAccountError(
                    f"Invalid source account obtained after receive: {source_account}"
                )
            if amount_raw <= 0:
                raise InvalidAmountError(
                    f"Non-positive amount obtained after receive: {amount_raw}"
                )

            # Skip refunding to self
            if source_account == self.account:
                logger.info(
                    "Refund Internal: Skipping refund for block %s as source is self (%s)",
                    receivable_hash,
                    self.account,
                )
                status = RefundStatus.SKIPPED
                error_message = "Refunding to self"
                return RefundDetail(
                    receivable_hash=receivable_hash,
                    amount_raw=amount_raw,
                    status=status,
                    source_account=source_account,
                    receive_hash=receive_hash,
                    refund_hash=None,
                    error_message=error_message,
                )

            # 3. Send the refund
            logger.debug(
                "Refund Internal: Attempting refund send to %s for %s raw",
                source_account,
                amount_raw,
            )
            refund_hash = await self._block_operations.send_raw(
                destination_account=source_account,
                amount_raw=amount_raw,
                wait_confirmation=wait_confirmation,
                timeout=timeout,
            )
            status = RefundStatus.SUCCESS
            logger.info(
                "Refund Internal: Successfully refunded %s raw to %s. Refund block hash: %s",
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
            # Handle specific errors during receive or send phases
            error_code = getattr(e, "code", "REFUND_ERROR")
            if received_block is None:
                # Error occurred during receive phase or info validation
                status = RefundStatus.RECEIVE_FAILED
                error_message = f"Failed to receive block or invalid data: {str(e)}"
                logger.error(
                    "Refund Internal: %s (receivable_hash: %s)",
                    error_message,
                    receivable_hash,
                )
                # Try to get amount/source if possible, even if receive failed
                try:
                    logger.debug(
                        "Refund Internal: Attempting block info lookup after receive failure: %s",
                        receivable_hash,
                    )
                    block_info = await self._rpc_component.block_info(receivable_hash)
                    if amount_raw == 0:
                        amount_raw = int(block_info.get("amount", 0))
                    if source_account is None:
                        source_account = block_info.get("block_account")
                except Exception as info_e:
                    logger.warning(
                        "Refund Internal: Could not retrieve block info after receive failure for %s: %s",
                        receivable_hash,
                        info_e,
                    )
            else:
                # Error occurred during send phase
                status = RefundStatus.SEND_FAILED
                error_message = f"Failed to send refund: {str(e)}"
                logger.error(
                    "Refund Internal: %s (dest: %s, amount: %s)",
                    error_message,
                    source_account,
                    amount_raw,
                )

            error_message = f"[{error_code}] {error_message}"

        except Exception as e:
            # Catch any other unexpected errors
            status = RefundStatus.UNEXPECTED_ERROR
            error_message = (
                f"Unexpected error processing refund for {receivable_hash}: {e}"
            )
            logger.exception("Refund Internal: %s", error_message)  # Log full traceback

        # 4. Create and return detail object
        return RefundDetail(
            receivable_hash=receivable_hash,
            amount_raw=amount_raw,  # Amount might be 0 if info lookup failed
            source_account=source_account,  # Source might be None if info lookup failed
            status=status,
            receive_hash=receive_hash,  # Will be None if receive failed
            refund_hash=refund_hash,  # Will be None if send failed
            error_message=error_message,
        )

    @reload_after
    @handle_errors
    async def refund_receivable_by_hash(
        self, receivable_hash: str, wait_confirmation: bool = False, timeout: int = 30
    ) -> RefundDetail:
        """Receives a specific block and sends the funds back to the sender."""
        logger.info(
            "NanoWalletAuthenticated: Starting refund_receivable_by_hash for block %s",
            receivable_hash,
        )
        # Delegate to the internal orchestration method
        result_detail = await self._internal_refund_receivable(
            receivable_hash=receivable_hash,
            wait_confirmation=wait_confirmation,
            timeout=timeout,
        )
        return result_detail

    @reload_after
    @handle_errors
    async def refund_all_receivables(
        self,
        threshold_raw: Optional[int] = None,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> List[RefundDetail]:
        """Refunds all receivable blocks above an optional threshold."""
        threshold_desc = (
            f"{threshold_raw} raw"
            if threshold_raw is not None
            else f"config default ({self.config.min_receive_threshold_raw} raw)"
        )
        logger.info(
            "NanoWalletAuthenticated: Starting refund_all_receivables (threshold=%s, wait_confirmation=%s)",
            threshold_desc,
            wait_confirmation,
        )

        # 1. List receivables
        try:
            await self.reload()  # Freshen state
            receivables = await self._query_operations.list_receivables(
                threshold_raw=threshold_raw
            )
        except Exception as e:
            logger.error(
                "NanoWalletAuthenticated: Failed to list receivables during refund_all: %s",
                e,
            )
            raise NanoException(
                f"Failed to list receivables for refund_all: {e}",
                "LIST_RECEIVABLES_ERROR",
            ) from e

        if not receivables:
            logger.info(
                "NanoWalletAuthenticated: No receivable blocks found matching criteria for refund."
            )
            return []

        logger.info(
            "NanoWalletAuthenticated: Found %s receivable blocks to attempt refund.",
            len(receivables),
        )
        refund_results: List[RefundDetail] = []

        # 2. Iterate and call internal refund logic for each
        for receivable in receivables:
            detail = await self._internal_refund_receivable(
                receivable_hash=receivable.block_hash,
                wait_confirmation=wait_confirmation,
                timeout=timeout,
            )
            refund_results.append(detail)

        logger.info(
            "NanoWalletAuthenticated: refund_all_receivables finished. Processed %s blocks.",
            len(receivables),
        )
        return refund_results

    @handle_errors
    async def refund_first_sender(self, wait_confirmation: bool = False) -> str:
        """
        Receives all pending funds and sends the entire balance back to the
        account that sent the *first ever* block (open block) to this wallet.
        """
        # Reload state first to get current balance and account info
        await self.reload()

        current_balance = self._state_manager.balance_info.balance_raw
        current_receivable = self._state_manager.balance_info.receivable_raw
        account_info = self._state_manager.account_info

        if current_balance <= 0 and current_receivable <= 0:
            raise InsufficientBalanceError(
                "No funds available (balance or receivable) to refund."
            )

        refund_account: Optional[str] = None

        # 1. Try getting source from Open Block
        if account_info and account_info.open_block:
            logger.debug(
                "RefundFirstSender: Trying to get source from open block: %s",
                account_info.open_block,
            )
            try:
                open_block_info = await self._rpc_component.block_info(
                    account_info.open_block
                )
                source_account = open_block_info.get("source_account")
                if source_account:
                    refund_account = source_account
                    logger.info(
                        "RefundFirstSender: Determined refund account from open block source: %s",
                        refund_account,
                    )
                else:
                    logger.warning(
                        "RefundFirstSender: Open block %s found, but link was zero or missing.",
                        account_info.open_block,
                    )
            except BlockNotFoundError:
                logger.warning(
                    "RefundFirstSender: Open block %s not found.",
                    account_info.open_block,
                )
            except Exception as e:
                logger.warning(
                    "RefundFirstSender: Could not determine refund account from open block %s: %s",
                    account_info.open_block,
                    str(e),
                )

        # 2. If open block failed, try oldest receivable
        if not refund_account:
            logger.debug(
                "RefundFirstSender: Open block source failed, trying oldest receivable."
            )
            try:
                receivables = await self._query_operations.list_receivables(
                    threshold_raw=0
                )  # Get all receivables
                if receivables:
                    first_receivable = receivables[0]
                    logger.debug(
                        "RefundFirstSender: Trying block info for receivable: %s",
                        first_receivable.block_hash,
                    )
                    block_info = await self._rpc_component.block_info(
                        first_receivable.block_hash
                    )
                    source = block_info.get(
                        "block_account"
                    )  # Sender of the receivable block
                    if source:
                        refund_account = source
                        logger.info(
                            "RefundFirstSender: Determined refund account from receivable source: %s",
                            refund_account,
                        )
                    else:
                        logger.warning(
                            "RefundFirstSender: Could not get source from receivable block %s info.",
                            first_receivable.block_hash,
                        )
                else:
                    logger.warning(
                        "RefundFirstSender: No receivable blocks found to determine source."
                    )
            except Exception as e:
                logger.warning(
                    "RefundFirstSender: Could not determine refund account from receivables: %s",
                    str(e),
                )

        # 3. Validate refund account
        account_info = await self._rpc_component.fetch_account_info(refund_account)
        if not account_info.get("frontier"):
            raise InvalidAccountError(f"Refund account {refund_account} not found.")

        # 4. Perform the sweep to the determined account
        logger.info("RefundFirstSender: Sweeping all funds to %s", refund_account)
        refund_hash = await self.sweep(
            destination_account=refund_account,
            sweep_pending=True,  # Ensure pending are received first
            threshold_raw=0,  # Receive all pending regardless of amount
            wait_confirmation=wait_confirmation,
        )

        logger.info(
            "RefundFirstSender: Refund sweep successful. Block hash: %s", refund_hash
        )
        return refund_hash.unwrap()

    def to_string(self) -> str:
        """
        Generate a human-readable representation of the wallet state.

        Returns:
            Detailed string representation of the wallet
        """
        # Access state via state_manager properties
        balance_info = self._state_manager.balance_info
        account_info = self._state_manager.account_info

        balance_nano = raw_to_nano(balance_info.balance_raw)
        receivable_nano = raw_to_nano(balance_info.receivable_raw)
        weight_nano = raw_to_nano(account_info.weight_raw) if account_info else "N/A"
        rep = account_info.representative if account_info else "N/A"
        conf_height = account_info.confirmation_height if account_info else "N/A"
        block_count = account_info.block_count if account_info else "N/A"

        return (
            f"NanoWalletAuthenticated:\n"
            f"  Account: {self.account}\n"
            f"  Balance: {balance_nano} Nano ({balance_info.balance_raw} raw)\n"
            f"  Receivable: {receivable_nano} Nano ({balance_info.receivable_raw} raw)\n"
            f"  Voting Weight: {weight_nano} Nano ({getattr(account_info, 'weight_raw', 'N/A')} raw)\n"
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
        balance_info = self._state_manager.balance_info
        return (
            f"NanoWalletAuthenticated: Account={self.account}, "
            f"BalanceRaw={balance_info.balance_raw}, "
            f"ReceivableRaw={balance_info.receivable_raw}"
        )
