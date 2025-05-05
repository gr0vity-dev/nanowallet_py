import logging
from typing import List, Optional

from .rpc_component import RpcComponent
from .state_manager import StateManager
from ...models import WalletConfig, WalletBalance, AccountInfo, Receivable, Transaction
from ...errors import account_not_found, try_raise_error

logger = logging.getLogger(__name__)


class QueryOperations:
    """Handles read-only wallet operations."""

    def __init__(
        self,
        account: str,
        config: WalletConfig,
        rpc_component: RpcComponent,
        state_manager: StateManager,
    ):
        self.account = account
        self.config = config
        self._rpc_component = rpc_component
        self._state_manager = state_manager
        logger.debug("QueryOperations initialized for account: %s", self.account)

    async def has_balance(self) -> bool:
        """Check if the account has available balance (checks state)."""
        # Access state via the state_manager property
        balance_info = self._state_manager.balance_info
        return (balance_info.balance_raw > 0) or (balance_info.receivable_raw > 0)

    async def balance_info(self) -> WalletBalance:
        """Get detailed balance information (from state)."""
        return self._state_manager.balance_info

    async def account_info(self) -> AccountInfo:
        """Get detailed account information (from state)."""
        logger.debug(
            "QueryOperations: Fetching account info state for account: %s", self.account
        )
        return self._state_manager.account_info

    async def list_receivables(
        self, threshold_raw: Optional[int] = None
    ) -> List[Receivable]:
        """List receivable blocks sorted by amount (from state)."""
        receivable_blocks = self._state_manager.receivable_blocks
        if not receivable_blocks:
            return []

        effective_threshold = (
            threshold_raw
            if threshold_raw is not None
            else self.config.min_receive_threshold_raw
        )
        logger.debug(
            "QueryOperations: Listing receivables from state with effective threshold: %d raw",
            effective_threshold,
        )
        receivables = [
            block
            for block in receivable_blocks
            if block.amount_raw >= effective_threshold
        ]

        # Sort by amount descending
        return sorted(receivables, key=lambda x: x.amount_raw, reverse=True)

    async def account_history(
        self, count: Optional[int] = -1, head: Optional[str] = None
    ) -> List[Transaction]:
        """Get block history for the wallet's account (uses RPC)."""
        logger.debug(
            "QueryOperations: Fetching account history for %s via RpcComponent",
            self.account,
        )
        try:
            # Access _rpc_component directly
            response = await self._rpc_component.account_history(
                account=self.account, count=count, raw=True, head=head
            )
            if account_not_found(response):
                return []
            try_raise_error(response)
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
            logger.error(
                "QueryOperations: Error retrieving account history: %s",
                str(e),
                exc_info=True,
            )
            raise  # Re-raise exception to be caught by @handle_errors in wallet class
