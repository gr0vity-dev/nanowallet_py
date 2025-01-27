from typing import Optional, Dict, Any, List
from decimal import Decimal
from nanorpc.client import NanoRpcTyped
from ..models import WalletConfig, WalletBalance, AccountInfo
from ..errors import (
    try_raise_error,
    block_not_found,
    BlockNotFoundError,
)
from ..utils.validation import validate_nano_amount
from ..utils.conversion import nano_to_raw, raw_to_nano


class NanoWalletBase:
    """Base implementation with shared functionality"""

    def __init__(
        self,
        rpc: NanoRpcTyped,
        config: Optional[WalletConfig] = None,
    ):
        self.rpc = rpc
        self.config = config or WalletConfig()
        self._init_account_state()

    def _init_account_state(self):
        """Initialize account state variables"""
        self.account = None
        self.receivable_blocks = {}

        # Initialize data models
        self._balance_info = WalletBalance()
        self._account_info = AccountInfo()

        # For backward compatibility
        self._update_legacy_attributes()

    def _update_legacy_attributes(self):
        """Update legacy attributes from data models for backward compatibility"""
        # Balance related
        self.balance = self._balance_info.balance
        self.balance_raw = self._balance_info.balance_raw
        self.receivable_balance = self._balance_info.receivable
        self.receivable_balance_raw = self._balance_info.receivable_raw

        # Account related
        self.weight = self._account_info.weight
        self.weight_raw = self._account_info.weight_raw
        self.confirmation_height = self._account_info.confirmation_height
        self.block_count = self._account_info.block_count
        self.frontier_block = self._account_info.frontier_block
        self.representative_block = self._account_info.representative_block
        self.representative = self._account_info.representative
        self.open_block = self._account_info.open_block

    async def _fetch_account_info(self) -> Dict[str, Any]:
        """Get account information from RPC"""
        response = await self.rpc.account_info(
            self.account,
            weight=True,
            receivable=True,
            representative=True,
            include_confirmed=False,
        )
        return response

    async def _block_info(self, block_hash: str) -> Dict[str, Any]:
        """Get block information"""
        response = await self.rpc.blocks_info(
            [block_hash], source=True, receive_hash=True, json_block=True
        )
        if block_not_found(response):
            raise BlockNotFoundError(f"Block not found {block_hash}")
        try_raise_error(response)
        return response["blocks"][block_hash]


class WalletUtils:

    @staticmethod
    def raw_to_nano(amount_raw: int, decimal_places=6) -> Decimal:
        """
        Converts raw amount to Nano, truncating to 6 decimal places.

        Args:
            raw_amount: Amount in raw units

        Returns:
            Decimal: Amount in NANO, truncated to 6 decimal places
        """
        return raw_to_nano(amount_raw, decimal_places=decimal_places)

    @staticmethod
    def nano_to_raw(amount_nano: Decimal | str | int, decimal_places=30) -> int:
        """
        Converts Nano amount to raw amount.

        Args:
            amount_nano: The amount in Nano (as Decimal, string, or int)

        Returns:
            int: The amount in raw

        Raises:
            TypeError: If amount is float or invalid type
            ValueError: If amount is negative or invalid format
        """
        amount_decimal = validate_nano_amount(amount_nano)
        return nano_to_raw(
            raw_to_nano(nano_to_raw(amount_decimal), decimal_places=decimal_places)
        )

    @staticmethod
    def sum_received_amount(receive_all_response: List[dict]) -> dict:
        """
        Sums the amount_raw values from a list of receivable responses.

        Args:
            receive_all_response: A list of dictionaries containing 'amount_raw'

        Returns:
            dict: A dictionary with the total amount in raw and Nano
        """
        total_amount_raw = sum(int(item["amount_raw"]) for item in receive_all_response)
        return {"amount_raw": total_amount_raw, "amount": raw_to_nano(total_amount_raw)}
