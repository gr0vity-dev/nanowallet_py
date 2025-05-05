from typing import Protocol, Optional, List, Dict, Any
from decimal import Decimal
from ..models import (
    WalletBalance,
    AccountInfo,
    Receivable,
    Transaction,
    ReceivedBlock,
    RefundDetail,
    UnsignedBlockDetails,
)
from ..utils import NanoResult


class IReadOnlyWallet(Protocol):
    """Protocol defining the interface for read-only wallet operations."""

    account: str
    _balance_info: WalletBalance
    _account_info: AccountInfo
    _receivable_blocks: List[Receivable]

    async def reload(self) -> NanoResult[None]: ...
    async def balance_info(self) -> NanoResult[WalletBalance]: ...
    async def account_info(self) -> NanoResult[AccountInfo]: ...
    async def has_balance(self) -> NanoResult[bool]: ...
    async def list_receivables(
        self, threshold_raw: int = ...
    ) -> NanoResult[List[Receivable]]: ...
    async def account_history(
        self, count: Optional[int] = -1, head: Optional[str] = None
    ) -> NanoResult[List[Transaction]]: ...

    # --- New Methods for Simplified 2-Phase Blocks ---
    async def prepare_send_block(
        self, destination_account: str, amount_raw: int
    ) -> NanoResult[UnsignedBlockDetails]: ...
    async def prepare_receive_block(
        self, source_hash: str
    ) -> NanoResult[UnsignedBlockDetails]: ...
    async def submit_signed_block(
        self,
        unsigned_details: UnsignedBlockDetails,  # Pass back the prepared data
        signature: str,  # Pass the signature
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> NanoResult[str]: ...


class IAuthenticatedWallet(IReadOnlyWallet, Protocol):
    """Protocol defining the interface for authenticated wallet operations."""

    private_key: str

    async def send(
        self,
        destination_account: str,
        amount: Decimal | str | int,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> NanoResult[str]: ...
    async def send_raw(
        self,
        destination_account: str,
        amount_raw: int | str,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> NanoResult[str]: ...
    async def send_with_retry(
        self,
        destination_account: str,
        amount: Decimal | str | int,
        max_retries: int = 5,
        retry_delay_base: float = 0.1,
        retry_delay_backoff: float = 1.5,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> NanoResult[str]: ...
    async def send_raw_with_retry(
        self,
        destination_account: str,
        amount_raw: int | str,
        max_retries: int = 5,
        retry_delay_base: float = 0.1,
        retry_delay_backoff: float = 1.5,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> NanoResult[str]: ...
    async def sweep(
        self,
        destination_account: str,
        sweep_pending: bool = True,
        threshold_raw: int = ...,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> NanoResult[str]: ...
    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> NanoResult[ReceivedBlock]: ...
    async def receive_all(
        self,
        threshold_raw: int = ...,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> NanoResult[List[ReceivedBlock]]: ...
    async def refund_first_sender(
        self, wait_confirmation: bool = False
    ) -> NanoResult[str]: ...
    async def refund_receivable_by_hash(
        self, receivable_hash: str, wait_confirmation: bool = False, timeout: int = 30
    ) -> NanoResult[RefundDetail]: ...
    async def refund_all_receivables(
        self,
        threshold_raw: int = ...,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> NanoResult[List[RefundDetail]]: ...
