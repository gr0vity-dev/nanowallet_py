from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from .utils.conversion import raw_to_nano


@dataclass
class WalletConfig:
    """Configuration for NanoWallet"""

    use_work_peers: bool = False
    default_representative: str = (
        "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
    )


@dataclass
class WalletBalance:
    """Balance information for a wallet"""

    balance_raw: int = 0
    receivable_raw: int = 0

    @property
    def balance(self) -> Decimal:
        """Current balance in Nano"""
        return raw_to_nano(self.balance_raw)

    @property
    def receivable(self) -> Decimal:
        """Receivable balance in Nano"""
        return raw_to_nano(self.receivable_raw)


@dataclass
class AccountInfo:
    """Detailed account information"""

    frontier_block: Optional[str] = None
    representative: Optional[str] = None
    representative_block: Optional[str] = None
    open_block: Optional[str] = None
    confirmation_height: int = 0
    block_count: int = 0
    weight_raw: int = 0

    @property
    def weight(self) -> Decimal:
        """Account weight in Nano"""
        return raw_to_nano(self.weight_raw)
