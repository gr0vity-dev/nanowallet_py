# nanowallet/wallets/base.py
from typing import Optional, Dict, Any
from .rpc import NanoWalletRpc
from ..models import WalletConfig, WalletBalance, AccountInfo


class NanoWalletBase:
    """Base implementation with shared functionality"""

    def __init__(
        self,
        rpc: NanoWalletRpc,
        config: Optional[WalletConfig] = None,
    ):
        self.rpc = rpc
        self.config = config or WalletConfig()
        self._init_account_state()

    def _init_account_state(self):
        """Initialize account state variables"""
        self.account = None
        self.receivable_blocks = {}
        self._balance_info = WalletBalance()
        self._account_info = AccountInfo()

    async def _fetch_account_info(self) -> Dict[str, Any]:
        """Get account information from RPC"""
        return await self.rpc.account_info(
            self.account,
            include_weight=True,
            include_receivable=True,
            include_representative=True,
            include_confirmed=False,
        )

    async def _block_info(self, block_hash: str) -> Dict[str, Any]:
        """Get block information"""
        response = await self.rpc.blocks_info(
            [block_hash],
            include_source=True,
            include_receive_hash=True,
            json_block=True,
        )
        return response["blocks"][block_hash]
