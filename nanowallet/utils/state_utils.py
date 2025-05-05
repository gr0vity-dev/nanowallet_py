import logging
from typing import Tuple, Optional, List


from nanowallet.models import WalletBalance, AccountInfo, Receivable

from nanowallet.libs.rpc import INanoRpc
from nanowallet.errors import (
    account_not_found,
    no_error,
    try_raise_error,
    NanoException,
)

logger = logging.getLogger(__name__)

# Define a type alias using Any to avoid the need for importing the actual types
WalletStateType = Tuple[
    WalletBalance, AccountInfo, List[Receivable]
]  # (WalletBalance, AccountInfo, List[Receivable])


class StateUtils:
    """A utility class for managing wallet state derivation."""

    @staticmethod
    def init_account_state(account: Optional[str]) -> WalletStateType:
        """Initializes default state for a wallet."""

        effective_account = account if account else "UNKNOWN"
        logger.debug(
            "StateUtils: Initializing default state for account %s", effective_account
        )

        balance_info = WalletBalance()
        account_info = AccountInfo(account=account)
        receivable_blocks = []
        return balance_info, account_info, receivable_blocks

    @staticmethod
    async def reload_state(rpc: INanoRpc, account: str) -> WalletStateType:
        """Fetches data using INanoRpc and computes the latest wallet state."""

        if not account:
            logger.warning("StateUtils: No valid account provided.")
            return StateUtils.init_account_state(account)

        logger.debug("StateUtils: Reloading state for account %s", account)

        # Initialize default values
        balance_info = WalletBalance()
        account_info = AccountInfo(account=account)
        receivable_blocks = []
        receivable_sum = 0

        # 1. Fetch receivables
        try:
            receivable_response = await rpc.receivable(
                account, threshold=1, include_source=True
            )
            if not account_not_found(receivable_response) and no_error(
                receivable_response
            ):
                blocks_data = receivable_response.get("blocks", {})
                if blocks_data == "":
                    receivable_blocks = []
                else:
                    # The response structure has block hashes as keys in the "blocks" dictionary
                    receivable_blocks = [
                        Receivable(
                            block_hash=block_hash,
                            amount_raw=int(block_info.get("amount", "0")),
                            source_account=block_info.get("source", ""),
                        )
                        for block_hash, block_info in blocks_data.items()
                    ]

                # Calculate receivable sum
                receivable_sum = (
                    sum(block.amount_raw for block in receivable_blocks)
                    if receivable_blocks
                    else 0
                )

        except Exception as e:
            logger.exception("Failed fetching receivables for %s: %s", account, e)
            raise NanoException(
                f"Failed to fetch receivables: {e}", "RELOAD_RECEIVABLE_ERROR"
            ) from e

        # 2. Fetch account info
        try:
            account_info_response = await rpc.account_info(
                account,
                include_weight=True,
                include_receivable=True,
                include_representative=True,
                include_confirmed=False,
            )

            if account_not_found(account_info_response):
                # Account not found, use receivable sum from RPC call
                balance_info = WalletBalance(
                    balance_raw=0, receivable_raw=receivable_sum
                )
            elif no_error(account_info_response):
                # Parse account info
                balance_raw = int(account_info_response.get("balance", "0"))

                # Use receivable sum from blocks calculation as primary source
                receivable_raw = receivable_sum or int(
                    account_info_response.get("receivable", "0")
                )

                balance_info = WalletBalance(
                    balance_raw=balance_raw, receivable_raw=receivable_raw
                )
                account_info = AccountInfo(
                    account=account,
                    frontier_block=account_info_response.get("frontier"),
                    representative=account_info_response.get("representative"),
                    representative_block=account_info_response.get(
                        "representative_block"
                    ),
                    open_block=account_info_response.get("open_block"),
                    confirmation_height=int(
                        account_info_response.get("confirmation_height", "0")
                    ),
                    block_count=int(account_info_response.get("block_count", "0")),
                    weight_raw=int(account_info_response.get("weight", "0")),
                )
            else:
                try_raise_error(account_info_response)
        except Exception as e:
            if not isinstance(e, NanoException):
                logger.exception("Failed fetching account info for %s: %s", account, e)
                raise NanoException(
                    f"Failed to fetch account info: {e}", "RELOAD_ACCOUNT_ERROR"
                ) from e
            raise  # Re-raise existing NanoException

        logger.debug(
            "StateUtils: Reload complete for %s. Balance: %s, Receivables: %d blocks (%d raw)",
            account,
            balance_info.balance_raw,
            len(receivable_blocks),
            balance_info.receivable_raw,
        )

        return balance_info, account_info, receivable_blocks
