import logging
from typing import Any, Dict, List, Optional

from nanowallet.libs.rpc import INanoRpc
from nanowallet.errors import (
    BlockNotFoundError,
    try_raise_error,
    NanoException,
)

logger = logging.getLogger(__name__)


class RpcComponent:
    """Manages direct interactions with the Nano RPC node."""

    def __init__(self, rpc: INanoRpc):
        self.rpc = rpc
        logger.debug("RpcComponent initialized.")

    async def fetch_account_info(self, account: str) -> Dict[str, Any]:
        """Fetches account info via RPC."""
        logger.debug("RpcComponent: Fetching account info for %s", account)
        # Delegate directly to the injected rpc instance
        response = await self.rpc.account_info(
            account,
            include_weight=True,
            include_receivable=True,
            include_representative=True,
            include_confirmed=False,
        )
        # Caller (e.g., StateUtils) should check response for errors/not_found
        return response

    async def block_info(self, block_hash: str) -> Dict[str, Any]:
        """Fetches block info via RPC, raising BlockNotFoundError if not found."""
        logger.debug("RpcComponent: Fetching block info for %s", block_hash)
        response = await self.rpc.blocks_info(
            [block_hash],
            include_source=True,
            include_receive_hash=True,
            json_block=True,
        )
        # Check within the response structure
        if "blocks" not in response or block_hash not in response["blocks"]:
            logger.error(
                "RpcComponent: Block %s not found in blocks_info response: %s",
                block_hash,
                response,
            )
            raise BlockNotFoundError(f"Block not found: {block_hash}")
        return response["blocks"][block_hash]

    async def get_receivables(self, account: str, threshold: int = 1) -> Dict[str, Any]:
        """Fetches receivable blocks via RPC."""
        logger.debug(
            "RpcComponent: Fetching receivables for %s (threshold=%d)",
            account,
            threshold,
        )
        response = await self.rpc.receivable(account, threshold=threshold, source=True)
        # Caller (e.g., StateUtils) should check response for errors/not_found
        return response

    async def generate_work(self, pow_hash: str, use_peers: bool) -> str:
        """Generates PoW using RPC."""
        logger.debug(
            "RpcComponent: Generating work for hash: %s (use_peers=%s)",
            pow_hash,
            use_peers,
        )
        response = await self.rpc.work_generate(pow_hash, use_peers=use_peers)
        try_raise_error(response)  # Raise if RPC reported an error
        if "work" not in response:
            raise NanoException(
                f"Work generation failed for {pow_hash}. 'work' key missing.",
                "WORK_GENERATION_ERROR",
            )
        return response["work"]

    async def process_block(self, block_json: Dict[str, Any]) -> str:
        """Submits a block JSON to the network via RPC."""
        logger.debug("RpcComponent: Processing block JSON via RPC")

        response = await self.rpc.process(block_json)
        try_raise_error(response)  # Raise if RPC reported an error
        if "hash" not in response:
            raise NanoException(
                f"Block processing failed. 'hash' key missing.", "PROCESS_ERROR"
            )
        return response["hash"]

    async def account_history(
        self, account: str, count: int, raw: bool, head: Optional[str]
    ) -> Dict[str, Any]:
        """Fetches account history via RPC."""
        logger.debug(
            "RpcComponent: Fetching history for %s: count=%s, head=%s",
            account,
            count,
            head,
        )
        response = await self.rpc.account_history(
            account=account, count=count, raw=raw, head=head
        )
        # Caller should check response for errors/not_found
        return response
