from dataclasses import dataclass
from decimal import Decimal


@dataclass
class WalletConfig:
    """Configuration for NanoWallet"""

    use_work_peers: bool = False
    default_representative: str = (
        "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
    )


# @dataclass
# class WalletBalance:
#     """Balance information for a wallet"""

#     balance_raw: int
#     balance_nano: Decimal
#     receivable_raw: int
#     receivable_nano: Decimal
