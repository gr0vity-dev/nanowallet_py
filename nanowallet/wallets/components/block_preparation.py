import logging
from typing import Dict, Any, Optional

from .rpc_component import RpcComponent
from ...libs.account_helper import AccountHelper
from ...libs.block import NanoWalletBlock  # Needed to calculate hashes
from ...models import WalletConfig, UnsignedBlockDetails  # Use new model
from ...errors import (
    NanoException,
    account_not_found,
    no_error,
    try_raise_error,
    BlockNotFoundError,
    InvalidAccountError,
    InsufficientBalanceError,
    InvalidAmountError,
)

logger = logging.getLogger(__name__)
ZERO_HASH = "0" * 64


class BlockPreparationComponent:
    """Component responsible for preparing unsigned block details, including hashes."""

    def __init__(self, account: str, config: WalletConfig, rpc_component: RpcComponent):
        self.account = account
        self.config = config
        self._rpc_component = rpc_component
        logger.debug(
            "BlockPreparationComponent initialized for account: %s", self.account
        )

    async def _get_block_params(self) -> Dict[str, Any]:
        """Fetches current account state needed for building the next block via RPC."""
        logger.debug(
            "BlockPreparationComponent: Getting block parameters for %s via RPC",
            self.account,
        )
        try:
            account_info_response = await self._rpc_component.fetch_account_info(
                self.account
            )

            if account_not_found(account_info_response):
                logger.debug(
                    "BlockPreparationComponent: Account %s not found.", self.account
                )
                # Check for receivables to distinguish between truly unopened and pending open
                receivables_response = await self._rpc_component.get_receivables(
                    self.account, threshold=1
                )
                has_receivables = False
                if no_error(receivables_response):
                    blocks_data = receivables_response.get("blocks", {})
                    if isinstance(blocks_data, dict) and blocks_data:
                        has_receivables = True

                if has_receivables:
                    logger.debug(
                        "BlockPreparationComponent: Account %s not found but has receivables.",
                        self.account,
                    )
                    # Treat as state before first receive (open block)
                    return {
                        "previous": ZERO_HASH,
                        "balance": 0,
                        "representative": self.config.default_representative,
                    }
                else:
                    logger.debug(
                        "BlockPreparationComponent: Account %s not found and no receivables.",
                        self.account,
                    )
                    # Cannot send from unopened, non-pending account.
                    # Preparation for receive/change on such an account uses zero state.
                    return {
                        "previous": ZERO_HASH,
                        "balance": 0,
                        "representative": self.config.default_representative,
                    }
            elif no_error(account_info_response):
                frontier = account_info_response.get("frontier")
                balance = account_info_response.get("balance")
                representative = account_info_response.get("representative")

                if frontier is None or balance is None or representative is None:
                    logger.error(
                        "BlockPreparationComponent: Account info response missing critical fields. Resp: %s",
                        account_info_response,
                    )
                    raise NanoException(
                        "Account info response missing critical fields.",
                        "RPC_RESPONSE_MALFORMED",
                    )

                logger.debug(
                    "BlockPreparationComponent: Retrieved block params: balance=%s, frontier=%s...",
                    balance,
                    frontier[:10],
                )
                return {
                    "previous": frontier,
                    "balance": int(balance),
                    "representative": representative,
                }
            else:
                logger.error(
                    "BlockPreparationComponent: Failed to get block params due to RPC error: %s",
                    account_info_response.get("error"),
                )
                try_raise_error(
                    account_info_response
                )  # Raise specific error if possible
                raise NanoException(
                    "Unknown error fetching block params", "PARAMS_ERROR"
                )  # Fallback exception

        except NanoException as e:
            logger.error(
                "BlockPreparationComponent: NanoException while getting block parameters for %s: %s",
                self.account,
                e,
            )
            raise  # Re-raise known exceptions
        except Exception as e:
            logger.exception(
                "BlockPreparationComponent: Unexpected exception while getting block parameters for %s",
                self.account,
            )
            raise NanoException(
                f"Failed to get block parameters: {e}", "PARAMS_ERROR"
            ) from e

    async def prepare_send(
        self, destination_account: str, amount_raw: int
    ) -> UnsignedBlockDetails:
        """Prepares the details needed to create and sign a send block."""
        logger.debug(
            "BlockPreparationComponent: Preparing send block to %s for %d raw",
            destination_account,
            amount_raw,
        )

        if amount_raw <= 0:
            raise InvalidAmountError("Send amount must be positive.")
        if not destination_account or not AccountHelper.validate_account(
            destination_account
        ):
            raise InvalidAccountError(
                f"Invalid destination account: {destination_account}"
            )

        params = await self._get_block_params()
        current_balance_raw = params["balance"]
        new_balance = current_balance_raw - amount_raw

        if new_balance < 0:
            msg = f"Insufficient balance for send. Current: {current_balance_raw} raw, Sending: {amount_raw} raw"
            logger.error("BlockPreparationComponent: %s", msg)
            raise InsufficientBalanceError(msg)

        # Use NanoWalletBlock helper to calculate fields and hashes
        try:
            # Instantiate the block object - this calculates the 'link' internally
            temp_block_helper = NanoWalletBlock(
                account=self.account,
                previous=params["previous"],
                representative=params["representative"],
                balance=new_balance,
                destination_account=destination_account,  # Sets link to public key
            )
            # Extract calculated values
            link_value = (
                temp_block_helper._block.link
            )  # Get the calculated link (public key)
            hash_to_sign = (
                temp_block_helper.block_hash
            )  # Get the hash of the block fields
            hash_for_work = (
                temp_block_helper.work_block_hash
            )  # Get the hash needing work

        except Exception as e:
            logger.exception(
                "BlockPreparationComponent: Error during internal block object creation/hash calculation for send."
            )
            raise NanoException(
                f"Failed to prepare send block details: {e}", "PREPARE_SEND_ERROR"
            ) from e

        # Construct the result object
        unsigned_details = UnsignedBlockDetails(
            account=self.account,
            previous=params["previous"],
            representative=params["representative"],
            balance_raw=new_balance,
            link=link_value,
            hash_to_sign=hash_to_sign,
            hash_for_work=hash_for_work,
            link_as_account=destination_account,
        )
        logger.debug(
            "BlockPreparationComponent: Prepared unsigned send details: %s",
            unsigned_details,
        )
        return unsigned_details

    async def prepare_receive(self, source_hash: str) -> UnsignedBlockDetails:
        """Prepares the details needed to create and sign a receive block."""
        logger.debug(
            "BlockPreparationComponent: Preparing receive block for source hash %s",
            source_hash,
        )

        if not source_hash or len(source_hash) != 64:
            raise BlockNotFoundError(
                f"Invalid source block hash provided: {source_hash}"
            )

        try:
            # Fetch info about the source block to get the amount
            send_block_info = await self._rpc_component.block_info(source_hash)
            amount_raw = int(send_block_info["amount"])
            if amount_raw <= 0:
                raise InvalidAmountError(
                    f"Source block {source_hash} has non-positive amount: {amount_raw}"
                )
            logger.debug(
                "BlockPreparationComponent: Source block %s amount is %d raw",
                source_hash,
                amount_raw,
            )
        except BlockNotFoundError:
            logger.error(
                "BlockPreparationComponent: Source block hash %s not found.",
                source_hash,
            )
            raise
        except KeyError as e:
            logger.error(
                "BlockPreparationComponent: Missing key '%s' in block_info for %s",
                e,
                source_hash,
            )
            raise NanoException(
                f"Invalid block info response for {source_hash}",
                "RPC_RESPONSE_MALFORMED",
            ) from e
        except Exception as e:
            logger.exception(
                "BlockPreparationComponent: Failed to get info for source block %s",
                source_hash,
            )
            if isinstance(e, NanoException):
                raise
            raise NanoException(
                f"Failed to get source block info: {e}", "RPC_ERROR"
            ) from e

        # Get current state
        params = await self._get_block_params()
        current_balance_raw = params["balance"]
        new_balance = current_balance_raw + amount_raw

        # Determine representative (use default for open block)
        representative = params["representative"]
        is_open_block = params["previous"] == ZERO_HASH and current_balance_raw == 0
        if is_open_block:
            representative = self.config.default_representative
            logger.debug(
                "BlockPreparationComponent: Open block detected, using default representative %s",
                representative,
            )

        # Use NanoWalletBlock helper to calculate fields and hashes
        try:
            temp_block_helper = NanoWalletBlock(
                account=self.account,
                previous=params["previous"],
                representative=representative,  # Use potentially adjusted representative
                balance=new_balance,
                source_hash=source_hash,  # Sets link to source_hash
            )
            # Extract calculated values
            link_value = temp_block_helper._block.link  # Should be == source_hash
            hash_to_sign = temp_block_helper.block_hash
            hash_for_work = temp_block_helper.work_block_hash

            # Sanity check link value
            if link_value != source_hash:
                logger.warning(
                    "BlockPreparationComponent: Link mismatch during receive prep. Expected %s, got %s",
                    source_hash,
                    link_value,
                )
                link_value = source_hash  # Ensure correct link is stored

        except Exception as e:
            logger.exception(
                "BlockPreparationComponent: Error during internal block object creation/hash calculation for receive."
            )
            raise NanoException(
                f"Failed to prepare receive block details: {e}", "PREPARE_RECEIVE_ERROR"
            ) from e

        # Construct the result object
        unsigned_details = UnsignedBlockDetails(
            account=self.account,
            previous=params["previous"],
            representative=representative,
            balance_raw=new_balance,
            link=link_value,  # Should be source_hash
            hash_to_sign=hash_to_sign,
            hash_for_work=hash_for_work,
            link_as_account=None,  # Not applicable for receive
        )
        logger.debug(
            "BlockPreparationComponent: Prepared unsigned receive details: %s",
            unsigned_details,
        )
        return unsigned_details
