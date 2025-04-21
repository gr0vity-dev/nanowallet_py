from typing import Optional
from nano_lib_py.blocks import Block

from nanowallet.libs.account_helper import AccountHelper


class NanoWalletBlock:
    """Encapsulates block creation and manipulation"""

    def __init__(
        self,
        account: str,
        previous: str,
        representative: str,
        balance: int,
        source_hash: Optional[str] = None,
        destination_account: Optional[str] = None,
    ):

        if source_hash and destination_account:
            raise ValueError("Cannot specify both source_hash and destination_account")

        self._block = Block(
            block_type="state",
            account=account,
            previous=previous,
            representative=representative,
            balance=balance,
            link=self._get_link_value(source_hash, destination_account),
        )

    def _get_link_value(
        self, source_hash: Optional[str], destination_account: Optional[str]
    ) -> str:
        """Get the link value for the block based on source hash or destination account"""
        if destination_account:
            return AccountHelper.get_public_key(destination_account)
        return source_hash or "0" * 64

    def sign(self, private_key: str) -> None:
        """Sign the block with provided private key"""
        self._block.sign(private_key)

    @property
    def work_block_hash(self) -> str:
        """Get the work block hash for work generation"""
        return self._block.work_block_hash

    @property
    def block_hash(self) -> str:
        """Get the block hash"""
        return self._block.block_hash

    def set_work(self, work: str) -> None:
        """Set the work value on the block"""
        self._block.set_work(work)

    def json(self) -> dict:
        """Get the block as a JSON-compatible dictionary"""
        return self._block.json()
