# nanowallet/models.py
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .utils.conversion import _raw_to_nano
from .libs.account_helper import AccountHelper


@dataclass
class WalletConfig:
    """Configuration for NanoWallet"""

    use_work_peers: bool = False
    default_representative: str = (
        "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
    )
    # Minimum amount in raw units required for *send* operations (default: 10**24 raw = 1 microNano)
    min_send_amount_raw: int = 10**24
    # Default minimum threshold in raw units for *listing/processing receivables* (default: 10**24 raw = 1 microNano)
    min_receive_threshold_raw: int = 10**24


@dataclass
class WalletBalance:
    """Balance information for a wallet"""

    balance_raw: int = 0
    receivable_raw: int = 0

    @property
    def balance(self) -> Decimal:
        """Current balance in Nano"""
        return _raw_to_nano(self.balance_raw)

    @property
    def receivable(self) -> Decimal:
        """Receivable balance in Nano"""
        return _raw_to_nano(self.receivable_raw)


@dataclass
class AccountInfo:
    """Detailed account information"""

    account: str
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
        return _raw_to_nano(self.weight_raw)


@dataclass(frozen=True)
class Receivable:
    """Represents a pending transaction waiting to be received"""

    block_hash: str
    amount_raw: int
    source_account: str

    @property
    def amount(self) -> Decimal:
        """Convert raw amount to Nano"""
        return _raw_to_nano(self.amount_raw)


@dataclass(frozen=True)
class ReceivedBlock:
    """Represents a received block with its details"""

    block_hash: str
    amount_raw: int
    source: str
    confirmed: bool

    @property
    def amount(self) -> Decimal:
        """Convert raw amount to Nano"""
        return _raw_to_nano(self.amount_raw)


@dataclass(frozen=True)
class AmountReceived:
    amount_raw: int

    @property
    def amount(self) -> Decimal:
        """Convert raw amount to Nano"""
        return _raw_to_nano(self.amount_raw)


@dataclass
class RefundStatus:
    INITIATED = "INITIATED"
    SKIPPED = "SKIPPED"
    SUCCESS = "SUCCESS"
    INFO_FAILED = "INFO_FAILED"
    RECEIVE_FAILED = "RECEIVE_FAILED"
    SEND_FAILED = "SEND_FAILED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


@dataclass(frozen=True)
class RefundDetail:
    receivable_hash: str
    amount_raw: int
    status: RefundStatus
    source_account: Optional[str] = None
    receive_hash: Optional[str] = None
    refund_hash: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def amount(self) -> Decimal:
        return _raw_to_nano(self.amount_raw)


@dataclass(frozen=True)
class Transaction:
    """Represents a confirmed transaction in account history"""

    block_hash: str
    type: str  # "state", "send", "receive", etc.
    subtype: Optional[str]  # "send", "receive", "epoch", "change", etc.
    account: str  # Counterparty account
    representative: str  # Representative account
    previous: str  # Previous block hash
    amount_raw: int
    balance_raw: int
    timestamp: int
    height: int
    confirmed: bool
    link: str  # Transaction link/recipient
    signature: str
    work: str

    @property
    def amount(self) -> Decimal:
        """Convert raw amount to Nano"""
        return _raw_to_nano(self.amount_raw)

    @property
    def balance(self) -> Decimal:
        """Convert raw balance to Nano"""
        return _raw_to_nano(self.balance_raw)

    @property
    def link_as_account(self) -> str:
        """The account receiving funds"""
        return AccountHelper.get_account(public_key=self.link)

    @property
    def destination(self) -> str:
        """The account receiving funds"""
        if self.subtype == "send":
            return self.link_as_account

    @property
    def pairing_block_hash(self) -> str:
        """The block sending funds"""
        if self.subtype == "receive":
            return self.link


@dataclass
class UnsignedBlockDetails:
    """Contains all fields for a block before signing and work generation.
    Includes the hash to be signed and the hash needed for work generation.
    This object is returned by prepare_* and passed back into submit_*."""

    # Core block fields
    account: str
    previous: str
    representative: str
    balance_raw: int  # The final balance AFTER the operation
    link: str

    # Hashes calculated during preparation
    hash_to_sign: (
        str  # The actual block hash (hash of all fields above) - user signs this
    )
    hash_for_work: str  # The hash requiring PoW (work_block_hash) - library uses this

    # Optional context field (read-only for user)
    link_as_account: Optional[str] = None  # For send blocks, the destination account ID
