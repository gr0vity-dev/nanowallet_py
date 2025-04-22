import logging
from typing import Optional, List, Dict, Any
from ..libs.rpc import INanoRpc
from ..models import WalletConfig, WalletBalance, AccountInfo, Receivable, Transaction
from ..utils.conversion import _raw_to_nano
from ..utils.decorators import handle_errors, reload_after
from ..errors import try_raise_error, account_not_found, InvalidAccountError
from ..libs.account_helper import AccountHelper
from ..utils import NanoResult

# Import the protocol and mixin
from .protocols import IReadOnlyWallet
from .mixins import StateManagementMixin

# Configure logging
logger = logging.getLogger(__name__)


class NanoWalletReadOnly(StateManagementMixin, IReadOnlyWallet):
    """Read-only implementation of NanoWallet using composition and mixins."""

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

        # Store instance attributes directly
        self.rpc = rpc
        self.account = account
        self.config = config or WalletConfig()

        # Initialize state
        self._init_account_state()
        logger.info("Initialized NanoWalletReadOnly for account: %s", self.account)

    @handle_errors
    async def reload(self) -> None:
        """Reload wallet state from the network."""
        # Call the mixin's implementation
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

            try_raise_error(response)

            # Extract and normalize the history list
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
        # If receivable_blocks is empty, return an empty list
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

        # Convert blocks to Receivable objects and filter by threshold
        receivables = [
            Receivable(block_hash=block, amount_raw=int(amount))
            for block, amount in self.receivable_blocks.items()
            if int(amount) >= effective_threshold
        ]

        # Sort by descending amount
        return sorted(receivables, key=lambda x: x.amount_raw, reverse=True)

    def to_string(self) -> str:
        """
        Generate a human-readable representation of the wallet state.

        Returns:
            Detailed string representation of the wallet
        """
        balance_nano = _raw_to_nano(self._balance_info.balance_raw)
        receivable_nano = _raw_to_nano(self._balance_info.receivable_raw)
        weight_nano = (
            _raw_to_nano(self._account_info.weight_raw) if self._account_info else "N/A"
        )
        rep = self._account_info.representative if self._account_info else "N/A"
        conf_height = (
            self._account_info.confirmation_height if self._account_info else "N/A"
        )
        block_count = self._account_info.block_count if self._account_info else "N/A"

        return (
            f"NanoWalletReadOnly:\n"
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
            f"NanoWalletReadOnly: Account={self.account}, "
            f"BalanceRaw={self._balance_info.balance_raw}, "
            f"ReceivableRaw={self._balance_info.receivable_raw}"
        )
