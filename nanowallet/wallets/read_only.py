from typing import Optional, List, Dict, Any, Protocol
from decimal import Decimal
from nanorpc.client import NanoRpcTyped
from ..models import WalletConfig
from ..utils import raw_to_nano, handle_errors, reload_after
from ..errors import (
    try_raise_error,
    account_not_found,
    no_error,
    block_not_found,
    InvalidAccountError,
    BlockNotFoundError,
)
from nano_lib_py import validate_account_id
from .base import NanoWalletBase
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
    ) -> List[Dict[str, Any]]:
        """Get block history for the wallet's account"""
        ...

    async def has_balance(self) -> bool:
        """Check if account has available balance"""
        ...

    async def balance_info(self) -> dict:
        """Get detailed balance information"""
        ...

    async def list_receivables(
        self, threshold_raw: int = DEFAULT_THRESHOLD_RAW
    ) -> List[tuple]:
        """List receivable blocks"""
        ...

    async def reload(self):
        """Reload account information"""
        ...


class NanoWalletReadOnly(NanoWalletBase):
    """Read-only implementation of NanoWallet"""

    def __init__(
        self,
        rpc: NanoRpcTyped,
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
        if not validate_account_id(account):
            raise InvalidAccountError("Invalid account address")
        self.account = account

    @handle_errors
    @reload_after
    async def account_history(
        self, count: Optional[int] = -1, head: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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
            for block in history:
                block["amount_raw"] = int(block["amount"])
                block["amount"] = raw_to_nano(block["amount_raw"])
                block["balance_raw"] = int(block["balance"])
                block["balance"] = raw_to_nano(block["balance_raw"])
                block["timestamp"] = int(block["local_timestamp"])
                block["height"] = int(block["height"])
                block["confirmed"] = block["confirmed"] == "true"

            return history

        except Exception as e:
            logger.error(f"Error retrieving account history: {str(e)}")
            raise BlockNotFoundError("Could not retrieve account history")

    @handle_errors
    async def has_balance(self) -> bool:
        """
        Checks if the account has available balance or receivable balance.

        :return: True if balance or receivable balance is greater than zero, False otherwise.
        """
        await self.reload()
        if (self.balance_raw and self.balance_raw > 0) or (
            self.receivable_balance_raw and self.receivable_balance_raw > 0
        ):
            return True
        return False

    @handle_errors
    @reload_after
    async def balance_info(self) -> dict:
        """
        Get detailed balance information for the account.

        :return: Dictionary containing:
            - balance: Current balance in Nano
            - balance_raw: Current balance in raw
            - receivable_balance: Pending receivable balance in Nano
            - receivable_balance_raw: Pending receivable balance in raw
        """
        await self.reload()
        return {
            "balance": self.balance,
            "balance_raw": self.balance_raw,
            "receivable_balance": self.receivable_balance,
            "receivable_balance_raw": self.receivable_balance_raw,
        }

    @handle_errors
    async def list_receivables(
        self, threshold_raw: int = DEFAULT_THRESHOLD_RAW
    ) -> List[tuple]:
        """
        Lists receivable blocks sorted by descending amount.

        :param threshold_raw: Minimum amount to consider (in raw).
        :return: A list of tuples containing block hashes and amounts.
        """
        await self.reload()

        # If receivable_blocks is empty, return an empty list
        if not self.receivable_blocks:
            return []

        # Filter blocks based on threshold if provided
        filtered_blocks = self.receivable_blocks.items()
        if threshold_raw is not None:
            filtered_blocks = [
                (block, amount)
                for block, amount in filtered_blocks
                if int(amount) >= threshold_raw
            ]

        # Sort the filtered blocks by descending amount
        sorted_receivables = sorted(
            filtered_blocks, key=lambda x: int(x[1]), reverse=True
        )

        return sorted_receivables

    @handle_errors
    async def reload(self):
        """
        Reloads the wallet's account information and receivable blocks.
        """
        response = await self.rpc.receivable(self.account, threshold=1)
        try_raise_error(response)

        self.receivable_blocks = response["blocks"]
        account_info = await self._account_info()
        if account_not_found(account_info) and self.receivable_blocks:
            # New account with receivable blocks
            self.receivable_balance_raw = sum(
                int(amount) for amount in self.receivable_blocks.values()
            )
            self.receivable_balance = raw_to_nano(self.receivable_balance_raw)
        elif no_error(account_info):
            self.balance = raw_to_nano(account_info["balance"])
            self.balance_raw = int(account_info["balance"])
            self.frontier_block = account_info["frontier"]
            self.representative_block = account_info["representative_block"]
            self.representative = account_info["representative"]
            self.open_block = account_info["open_block"]
            self.confirmation_height = int(account_info["confirmation_height"])
            self.block_count = int(account_info["block_count"])
            self.weight = raw_to_nano(account_info["weight"])
            self.weight_raw = int(account_info["weight"])
            self.receivable_balance = raw_to_nano(account_info["receivable"])
            self.receivable_balance_raw = int(account_info["receivable"])
            self.total_balance_raw = self.receivable_balance_raw + self.balance_raw

    def to_string(self):
        return (
            f"NanoWallet:\n"
            f"  Account: {self.account}\n"
            f"  Balance: {self.balance} Nano\n"
            f"  Balance raw: {self.balance_raw} raw\n"
            f"  Receivable Balance: {self.receivable_balance} Nano\n"
            f"  Receivable Balance raw: {self.receivable_balance_raw} raw\n"
            f"  Voting Weight: {self.weight} Nano\n"
            f"  Voting Weight raw: {self.weight_raw} raw\n"
            f"  Representative: {self.representative}\n"
            f"  Confirmation Height: {self.confirmation_height}\n"
            f"  Block Count: {self.block_count}"
        )

    def __str__(self):
        return (
            f"NanoWallet:\n"
            f"  Account: {self.account}\n"
            f"  Balance raw: {self.balance_raw} raw\n"
            f"  Receivable Balance raw: {self.receivable_balance_raw} raw"
        )
