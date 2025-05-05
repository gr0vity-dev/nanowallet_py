import logging
from typing import Optional, List
from ..libs.rpc import INanoRpc
from ..models import WalletConfig, WalletBalance, AccountInfo, Receivable, Transaction
from ..utils.conversion import _raw_to_nano
from ..utils.decorators import handle_errors
from ..errors import InvalidAccountError
from ..libs.account_helper import AccountHelper

from .protocols import IReadOnlyWallet
from .components import RpcComponent, StateManager, QueryOperations

# Configure logging
logger = logging.getLogger(__name__)


class NanoWalletReadOnly(IReadOnlyWallet):
    """Read-only implementation of NanoWallet using composition."""

    def __init__(
        self,
        rpc: INanoRpc,
        account: str,
        config: Optional[WalletConfig] = None,
    ):
        """
        Initialize read-only wallet with an account address.

        Args:
            rpc: RPC client for blockchain interaction
            account: Nano account address to monitor
            config: Optional wallet configuration
        """
        if not AccountHelper.validate_account(account):
            raise InvalidAccountError("Invalid account address")

        self.account = account
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

        logger.info("Initialized NanoWalletReadOnly for account: %s", self.account)

    # Delegate Methods to Components

    @handle_errors
    async def reload(self) -> None:
        """Reload wallet state using the StateManager component."""
        await self._state_manager.reload()

    @handle_errors
    async def account_history(
        self, count: Optional[int] = -1, head: Optional[str] = None
    ) -> List[Transaction]:
        """Get account history using the QueryOperations component."""
        return await self._query_operations.account_history(count=count, head=head)

    @handle_errors
    async def has_balance(self) -> bool:
        """Check balance using the QueryOperations component (which reads state)."""
        await self.reload()  # Call the wallet's reload method
        return await self._query_operations.has_balance()

    @handle_errors
    async def balance_info(self) -> WalletBalance:
        """Get balance info using the QueryOperations component (reads state)."""
        await self.reload()
        return await self._query_operations.balance_info()

    @handle_errors
    async def account_info(self) -> AccountInfo:
        """Get account info using the QueryOperations component (reads state)."""
        await self.reload()
        return await self._query_operations.account_info()

    @handle_errors
    async def list_receivables(
        self, threshold_raw: Optional[int] = None
    ) -> List[Receivable]:
        """List receivables using the QueryOperations component (reads state)."""
        await self.reload()
        return await self._query_operations.list_receivables(
            threshold_raw=threshold_raw
        )

    def to_string(self) -> str:
        """
        Generate a human-readable representation of the wallet state.

        Returns:
            Detailed string representation of the wallet
        """
        # Access state via state_manager properties
        balance_info = self._state_manager.balance_info
        account_info = self._state_manager.account_info

        balance_nano = _raw_to_nano(balance_info.balance_raw)
        receivable_nano = _raw_to_nano(balance_info.receivable_raw)
        weight_nano = _raw_to_nano(account_info.weight_raw) if account_info else "N/A"
        rep = account_info.representative if account_info else "N/A"
        conf_height = account_info.confirmation_height if account_info else "N/A"
        block_count = account_info.block_count if account_info else "N/A"

        return (
            f"NanoWalletReadOnly:\n"
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
            f"NanoWalletReadOnly: Account={self.account}, "
            f"BalanceRaw={balance_info.balance_raw}, "
            f"ReceivableRaw={balance_info.receivable_raw}"
        )
