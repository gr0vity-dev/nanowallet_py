# nanowallet/wallets/read_only.py
from typing import Optional, List, Dict, Any, Protocol
from ..libs.rpc import NanoRpcProtocol
from ..models import WalletConfig, WalletBalance, AccountInfo, Receivable, Transaction
from ..utils.conversion import _raw_to_nano
from ..utils.decorators import handle_errors, reload_after
from ..errors import (
    try_raise_error,
    account_not_found,
    no_error,
    InvalidAccountError,
)
from ..libs.account_helper import AccountHelper
from .base import NanoWalletBase
from ..utils import NanoResult
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_THRESHOLD_RAW = 10**24


class NanoWalletReadOnlyProtocol(Protocol):
    """Protocol defining read-only operations for a Nano wallet"""

    account: str  # The nano account address

    async def account_history(
        self, count: Optional[int] = -1, head: Optional[str] = None
    ) -> List[Transaction]:
        """Get block history for the wallet's account"""

    async def has_balance(self) -> bool:
        """Check if account has available balance"""

    async def balance_info(self) -> WalletBalance:
        """Get detailed balance information"""

    async def account_info(self) -> AccountInfo:
        """Get detailed account information"""

    async def list_receivables(
        self, threshold_raw: int = DEFAULT_THRESHOLD_RAW
    ) -> List[Receivable]:
        """List receivable blocks"""

    async def reload(self):
        """Reload account information"""


class NanoWalletReadOnly(NanoWalletBase):
    """Read-only implementation of NanoWallet"""

    def __init__(
        self,
        rpc: NanoRpcProtocol,
        account: str,
        config: Optional[WalletConfig] = None,
    ):
        """
        Initialize read-only wallet with just an account address.

        :param rpc: RPC client
        :param account: Nano account address to monitor
        :param config: Optional wallet configuration
        """
        super().__init__(rpc, config)
        if not AccountHelper.validate_account(account):
            raise InvalidAccountError("Invalid account address")
        self.account = account

    @reload_after
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
            logger.error("Error retrieving account history: %s", str(e))
            raise e

    @handle_errors
    async def has_balance(self) -> bool:
        """
        Checks if the account has available balance or receivable balance.

        :return: True if balance or receivable balance is greater than zero, False otherwise.
        """
        await self.reload()
        return (self._balance_info.balance_raw > 0) or (
            self._balance_info.receivable_raw > 0
        )

    @reload_after
    @handle_errors
    async def balance_info(self) -> WalletBalance:
        """
        Get detailed balance information for the account.

        :return: WalletBalance object containing current and receivable balances
        """
        await self.reload()
        return self._balance_info

    @reload_after
    @handle_errors
    async def account_info(self) -> AccountInfo:
        """
        Get detailed account information.

        :return: AccountInfo object containing account metadata
        """
        await self.reload()
        return self._account_info

    @handle_errors
    async def list_receivables(
        self, threshold_raw: int = DEFAULT_THRESHOLD_RAW
    ) -> List[Receivable]:
        """
        Lists receivable blocks sorted by descending amount.

        Args:
            threshold_raw: Minimum amount to consider (in raw).

        Returns:
            List of Receivable objects containing block hashes and amounts.
        """
        await self.reload()

        # If receivable_blocks is empty, return an empty list
        if not self.receivable_blocks:
            return []

        # Convert blocks to Receivable objects and filter by threshold
        receivables = [
            Receivable(block_hash=block, amount_raw=int(amount))
            for block, amount in self.receivable_blocks.items()
            if int(amount) >= threshold_raw
        ]

        # Sort by descending amount
        return sorted(receivables, key=lambda x: x.amount_raw, reverse=True)

    @handle_errors
    async def reload(self):
        """
        Reloads the wallet's account information and receivable blocks.
        """
        # pylint: disable=attribute-defined-outside-init
        response = await self.rpc.receivable(self.account, threshold=1)
        try_raise_error(response)

        self.receivable_blocks = response["blocks"] if "blocks" in response else {}
        account_info = await self._fetch_account_info()

        if account_not_found(account_info) and self.receivable_blocks:
            # New account with receivable blocks
            self._balance_info = WalletBalance(
                balance_raw=0,
                receivable_raw=sum(
                    int(amount) for amount in self.receivable_blocks.values()
                ),
            )
            self._account_info = AccountInfo()  # Empty account info
        elif no_error(account_info):
            # Update balance info
            self._balance_info = WalletBalance(
                balance_raw=int(account_info["balance"]),
                receivable_raw=int(account_info["receivable"]),
            )

            # Update account info
            self._account_info = AccountInfo(
                frontier_block=account_info["frontier"],
                representative=account_info["representative"],
                representative_block=account_info["representative_block"],
                open_block=account_info["open_block"],
                confirmation_height=int(account_info["confirmation_height"]),
                block_count=int(account_info["block_count"]),
                weight_raw=int(account_info["weight"]),
            )

    def to_string(self):
        return (
            f"NanoWallet:\n"
            f"  Account: {self.account}\n"
            f"  Balance: {self._balance_info.balance} Nano\n"
            f"  Balance raw: {self._balance_info.balance_raw} raw\n"
            f"  Receivable Balance: {self._balance_info.receivable} Nano\n"
            f"  Receivable Balance raw: {self._balance_info.receivable_raw} raw\n"
            f"  Voting Weight: {self._account_info.weight} Nano\n"
            f"  Voting Weight raw: {self._account_info.weight_raw} raw\n"
            f"  Representative: {self._account_info.representative}\n"
            f"  Confirmation Height: {self._account_info.confirmation_height}\n"
            f"  Block Count: {self._account_info.block_count}"
        )

    def __str__(self):
        return (
            f"NanoWallet:\n"
            f"  Account: {self.account}\n"
            f"  Balance raw: {self._balance_info.balance_raw} raw\n"
            f"  Receivable Balance raw: {self._balance_info.receivable_raw} raw"
        )
