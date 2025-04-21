import asyncio
import time
import logging
from typing import Optional, Dict, Any, TypeVar

from ..libs.rpc import INanoRpc
from ..libs.block import NanoWalletBlock
from ..models import WalletConfig, WalletBalance, AccountInfo
from ..errors import (
    account_not_found,
    no_error,
    try_raise_error,
    BlockNotFoundError,
    TimeoutException,
    NanoException,
)
from ..utils.decorators import handle_errors

logger = logging.getLogger(__name__)
ZERO_HASH = "0" * 64

# Forward declarations for type hints
T = TypeVar("T")


class _WalletWithRpc:
    rpc: INanoRpc
    config: WalletConfig
    account: str


class _WalletWithState(_WalletWithRpc):
    _balance_info: WalletBalance
    _account_info: AccountInfo
    receivable_blocks: Dict[str, str]  # block_hash -> amount_raw_str


class _WalletWithPrivateKey(_WalletWithState):
    private_key: str


class RpcInteractionMixin:
    """Provides basic RPC interaction helpers."""

    # Type-checked references to expected attributes
    rpc: INanoRpc
    account: str

    async def _fetch_account_info(self) -> Dict[str, Any]:
        """Fetch account information from the RPC node."""
        logger.debug("Fetching account info for %s", self.account)
        response = await self.rpc.account_info(
            self.account,
            include_weight=True,
            include_receivable=True,
            include_representative=True,
            include_confirmed=False,
        )
        return response

    async def _block_info(self, block_hash: str) -> Dict[str, Any]:
        """Fetch information about a specific block."""
        logger.debug("Fetching block info for %s", block_hash)
        response = await self.rpc.blocks_info(
            [block_hash],
            include_source=True,
            include_receive_hash=True,
            json_block=True,
        )

        if "blocks" not in response or block_hash not in response["blocks"]:
            logger.error("Block %s not found in blocks_info response", block_hash)
            raise BlockNotFoundError(f"Block not found: {block_hash}")

        return response["blocks"][block_hash]


class StateManagementMixin(RpcInteractionMixin):
    """Manages wallet state like balance, account info, and receivables."""

    config: WalletConfig
    _balance_info: WalletBalance
    _account_info: AccountInfo
    receivable_blocks: Dict[str, str]

    def _init_account_state(self) -> None:
        """Initialize the wallet state with default values."""
        account = getattr(self, "account", None)
        self._balance_info = WalletBalance()
        self._account_info = AccountInfo(account=account)
        self.receivable_blocks = {}

    @handle_errors
    async def reload(self) -> None:
        """Reload wallet state from the network."""
        if not self.account:
            logger.warning("Attempted to reload wallet state without an account set")
            self._init_account_state()
            return

        logger.debug("Reloading state for account %s", self.account)

        # Fetch receivables
        try:
            receivable_response = await self.rpc.receivable(self.account, threshold=1)
            if account_not_found(receivable_response):
                self.receivable_blocks = {}
            elif no_error(receivable_response):
                self.receivable_blocks = receivable_response.get("blocks", {})
            else:
                logger.error(
                    "Error fetching receivables: %s", receivable_response.get("error")
                )
                try_raise_error(receivable_response)
                self.receivable_blocks = {}  # Fallback
        except Exception as e:
            logger.exception("Exception fetching receivables for %s", self.account)
            self.receivable_blocks = {}
            if isinstance(e, NanoException):
                raise
            raise NanoException(
                f"Failed to fetch receivables: {e}", "RELOAD_ERROR"
            ) from e

        # Fetch account info
        try:
            account_info_response = await self._fetch_account_info()

            if account_not_found(account_info_response):
                # Account exists only if it has receivables
                if self.receivable_blocks:
                    logger.debug(
                        "Account %s not found but has receivables", self.account
                    )
                    receivable_sum = sum(
                        int(amount) for amount in self.receivable_blocks.values()
                    )
                    self._balance_info = WalletBalance(
                        balance_raw=0, receivable_raw=receivable_sum
                    )
                    self._account_info = AccountInfo(account=self.account)
                else:
                    # Account genuinely doesn't exist
                    logger.debug(
                        "Account %s not found and no receivables", self.account
                    )
                    self._init_account_state()
            elif no_error(account_info_response):
                # Account found, update state
                logger.debug("Account info found for %s", self.account)

                # Safely extract and convert values with proper error handling
                try:
                    balance_value = account_info_response.get("balance", "0")
                    receivable_value = account_info_response.get("receivable", "0")
                    confirmation_height = account_info_response.get(
                        "confirmation_height", "0"
                    )
                    block_count = account_info_response.get("block_count", "0")
                    weight = account_info_response.get("weight", "0")

                    self._balance_info = WalletBalance(
                        balance_raw=int(balance_value),
                        receivable_raw=int(receivable_value),
                    )

                    self._account_info = AccountInfo(
                        account=self.account,
                        frontier_block=account_info_response.get("frontier"),
                        representative=account_info_response.get("representative"),
                        representative_block=account_info_response.get(
                            "representative_block"
                        ),
                        open_block=account_info_response.get("open_block"),
                        confirmation_height=int(confirmation_height),
                        block_count=int(block_count),
                        weight_raw=int(weight),
                    )
                except (ValueError, TypeError) as e:
                    logger.error("Error parsing account info values: %s", str(e))
                    # Fall back to defaults if conversion fails
                    self._balance_info = WalletBalance(balance_raw=0, receivable_raw=0)
                    self._account_info = AccountInfo(account=self.account)
            else:
                # Handle specific errors
                logger.error(
                    "Error fetching account info: %s",
                    account_info_response.get("error"),
                )
                try_raise_error(account_info_response)
                self._init_account_state()

        except Exception as e:
            logger.exception("Exception fetching account info for %s", self.account)
            self._init_account_state()
            if isinstance(e, NanoException):
                raise
            raise NanoException(
                f"Failed to fetch account info: {e}", "RELOAD_ERROR"
            ) from e

        logger.debug(
            "Reload complete for %s. Balance: %s raw, Receivables: %d",
            self.account,
            self._balance_info.balance_raw,
            len(self.receivable_blocks),
        )


class BlockOperationsMixin(RpcInteractionMixin):
    """Handles authenticated operations like sending, receiving, signing."""

    private_key: str
    config: WalletConfig
    account: str
    _balance_info: WalletBalance
    _account_info: AccountInfo
    receivable_blocks: Dict[str, str]

    async def _generate_work(self, pow_hash: str) -> str:
        """Generate proof of work for a block."""
        logger.debug(
            "Generating work for hash: %s (use_peers=%s)",
            pow_hash,
            self.config.use_work_peers,
        )
        response = await self.rpc.work_generate(
            pow_hash, use_peers=self.config.use_work_peers
        )
        return response["work"]

    async def _build_block(
        self,
        previous: str,
        representative: str,
        balance: int,
        source_hash: Optional[str] = None,
        destination_account: Optional[str] = None,
    ) -> NanoWalletBlock:
        """Build a new block with the given parameters."""
        logger.debug(
            "Building block: prev=%s, rep=%s, bal=%d, src=%s, dest=%s",
            previous[:10] + "...",
            representative[:10] + "...",
            balance,
            source_hash,
            destination_account,
        )

        block = NanoWalletBlock(
            account=self.account,
            previous=previous,
            representative=representative,
            balance=balance,
            source_hash=source_hash,
            destination_account=destination_account,
        )
        block.sign(self.private_key)
        logger.debug("Block signed. Work block hash: %s...", block.work_block_hash[:10])

        work = await self._generate_work(block.work_block_hash)
        block.set_work(work)
        logger.debug("Work generated and set: %s", work)

        return block

    async def _process_block(self, block: NanoWalletBlock, operation: str) -> str:
        """Process a block and publish it to the network."""
        logger.debug("Processing block for operation: %s", operation)
        block_json = block.json()
        response = await self.rpc.process(block_json)
        block_hash = response["hash"]
        logger.debug("Successfully processed %s, hash: %s", operation, block_hash)
        return block_hash

    async def _wait_for_confirmation(
        self, block_hash: str, timeout: int = 30, raise_on_timeout: bool = False
    ) -> bool:
        """Wait for a block to be confirmed by the network."""
        start_time = time.time()
        delay = 0.5  # Initial delay
        max_delay = 5  # Max delay between checks
        attempt = 1
        logger.debug(
            "Starting confirmation wait for %s with timeout=%s", block_hash, timeout
        )

        while time.time() - start_time < timeout:
            try:
                block_info = await self._block_info(block_hash)
                confirmed = block_info.get("confirmed", "false") == "true"
                elapsed = time.time() - start_time

                logger.debug(
                    "Confirmation check attempt %d: hash=%s confirmed=%s, elapsed=%.2fs",
                    attempt,
                    block_hash[:10] + "...",
                    confirmed,
                    elapsed,
                )

                if confirmed:
                    logger.info("Block %s confirmed after %.2fs", block_hash, elapsed)
                    return True

                # Wait before next attempt
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)  # Exponential backoff with cap
                attempt += 1

            except BlockNotFoundError:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning("Block %s not found and timeout reached", block_hash)
                    break

                logger.debug(
                    "Block %s not found on attempt %d, retrying after %.2f seconds",
                    block_hash[:10] + "...",
                    attempt,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                attempt += 1

            except Exception:
                logger.exception("Error during confirmation check for %s", block_hash)
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                attempt += 1

        elapsed = time.time() - start_time
        logger.warning("Confirmation wait timed out after %.2fs", elapsed)

        if raise_on_timeout:
            raise TimeoutException(
                f"Block {block_hash} not confirmed within {timeout} seconds"
            )
        return False

    async def _get_block_params(self) -> Dict[str, Any]:
        """Get parameters needed for building a new block."""
        logger.debug("Getting block parameters for %s", self.account)

        try:
            account_info_response = await self._fetch_account_info()

            if account_not_found(account_info_response):
                # Account not found - check for receivables
                if self.receivable_blocks:
                    # Account needs opening via a receive block
                    logger.debug(
                        "Account %s not found but has receivables", self.account
                    )
                    return {
                        "previous": ZERO_HASH,
                        "balance": 0,
                        "representative": self.config.default_representative,
                    }
                else:
                    # Account doesn't exist yet
                    logger.debug(
                        "Account %s not found and no receivables", self.account
                    )
                    return {
                        "previous": ZERO_HASH,
                        "balance": 0,
                        "representative": self.config.default_representative,
                    }
            elif no_error(account_info_response):
                logger.debug(
                    "Retrieved block params: balance=%s, frontier=%s...",
                    account_info_response["balance"],
                    account_info_response["frontier"][:10],
                )
                return {
                    "previous": account_info_response["frontier"],
                    "balance": int(account_info_response["balance"]),
                    "representative": account_info_response["representative"],
                }
            else:
                # Handle error from account_info
                logger.error(
                    "Failed to get block params: %s", account_info_response.get("error")
                )
                try_raise_error(account_info_response)
                raise NanoException(
                    "Unknown error fetching block params", "PARAMS_ERROR"
                )

        except Exception as e:
            logger.exception("Failed to get block parameters for %s", self.account)
            if isinstance(e, NanoException):
                raise
            raise NanoException(
                f"Failed to get block parameters: {e}", "PARAMS_ERROR"
            ) from e
