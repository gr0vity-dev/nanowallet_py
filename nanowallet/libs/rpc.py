from typing import Any, Dict, List, Optional, Protocol
import logging

from nanorpc.client import NanoRpcTyped
from nanowallet.errors import try_raise_error, block_not_found, BlockNotFoundError

# Configure logging
logger = logging.getLogger(__name__)


class INanoRpc(Protocol):
    """Protocol defining required RPC operations"""

    async def account_info(
        self,
        account: str,
        *,
        include_representative: bool = True,
        include_weight: bool = True,
        include_receivable: bool = True,
        include_confirmed: bool = False,
    ) -> Dict[str, Any]:
        """Get account information"""

    async def blocks_info(
        self,
        hashes: List[str],
        *,
        include_source: bool = False,
        include_receive_hash: bool = False,
        json_block: bool = False,
    ) -> Dict[str, Any]:
        """Get block information"""

    async def work_generate(
        self, block_hash: str, use_peers: bool = False
    ) -> Dict[str, Any]:
        """Generate work for block"""

    async def process(self, block: Dict[str, Any]) -> Dict[str, Any]:
        """Process a block"""

    async def receivable(
        self,
        account: str,
        *,
        threshold: Optional[int] = None,
        include_source: bool = False,
    ) -> Dict[str, Any]:
        """Get receivable blocks"""

    async def account_history(
        self,
        account: str,
        *,
        count: Optional[int] = None,
        raw: bool = False,
        head: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get account history"""


class NanoWalletRpc(INanoRpc):
    """Abstraction layer for Nano RPC operations"""

    def __init__(
        self, url: str, username: Optional[str] = None, password: Optional[str] = None
    ):
        """
        Initialize RPC client with connection details.

        Args:
            url: RPC endpoint URL
            username: Optional username for authentication
            password: Optional password for authentication
        """
        self._rpc = NanoRpcTyped(
            url=url, username=username, password=password, wrap_json=True
        )
        logger.debug("Initialized RPC client with URL: %s", url)

    def _ensure_dict_response(self, response):
        """
        Ensures the RPC response is a dictionary.

        Args:
            response: The response from the RPC call

        Returns:
            Dict: Either the original response if it's a dict or an error dict
        """
        if not isinstance(response, dict):
            return {
                "error": "Invalid response format",
                "details": f"Expected dictionary, got {type(response).__name__}",
                "raw_response": str(response),
            }
        return response

    async def account_info(
        self,
        account: str,
        *,
        include_representative: bool = True,
        include_weight: bool = True,
        include_receivable: bool = True,
        include_confirmed: bool = False,
    ) -> Dict[str, Any]:
        """
        Get account information.

        Args:
            account: Account address
            include_representative: Include representative
            include_weight: Include voting weight
            include_receivable: Include receivable balance
            include_confirmed: Include confirmation info

        Returns:
            Dict containing account information
        """
        logger.debug("Fetching account info for %s", account)
        response = await self._rpc.account_info(
            account,
            representative=include_representative,
            weight=include_weight,
            receivable=include_receivable,
            include_confirmed=include_confirmed,
        )
        try_raise_error(response)
        return self._ensure_dict_response(response)

    async def blocks_info(
        self,
        hashes: List[str],
        *,
        include_source: bool = False,
        include_receive_hash: bool = False,
        json_block: bool = False,
    ) -> Dict[str, Any]:
        """
        Get information about blocks.

        Args:
            hashes: List of block hashes
            include_source: Include source account
            include_receive_hash: Include receive block hash
            json_block: Return blocks in JSON format

        Returns:
            Dict containing block information
        """
        logger.debug("Fetching info for blocks: %s", hashes)
        response = await self._rpc.blocks_info(
            hashes,
            source=include_source,
            receive_hash=include_receive_hash,
            json_block=json_block,
        )
        if block_not_found(response):
            for hash in hashes:
                raise BlockNotFoundError(f"Block not found {hash}")
        try_raise_error(response)
        return self._ensure_dict_response(response)

    async def work_generate(
        self, block_hash: str, use_peers: bool = False
    ) -> Dict[str, Any]:
        """
        Generate work for a block.

        Args:
            block_hash: Hash to generate work for
            use_peers: Use work peers

        Returns:
            Dict containing generated work
        """
        logger.debug("Generating work for hash: %s", block_hash)
        response = await self._rpc.work_generate(block_hash, use_peers=use_peers)
        logger.debug(
            "Work generated for hash: %s, %s", block_hash, response.get("work")
        )
        try_raise_error(response)
        return self._ensure_dict_response(response)

    async def process(self, block: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publish a block to the network.

        Args:
            block: Block to process

        Returns:
            Dict containing process result
        """
        logger.debug("Processing block: %s", block)
        response = await self._rpc.process(block, json_block=True)
        try_raise_error(response)
        return self._ensure_dict_response(response)

    async def receivable(
        self,
        account: str,
        *,
        threshold: Optional[int] = None,
        include_source: bool = False,
    ) -> Dict[str, Any]:
        """
        List all receivable blocks if any.

        Args:
            account: Account address
            threshold: Only return blocks above threshold
            include_source: Include source account

        Returns:
            Dict containing receivable blocks
        """
        logger.debug("Fetching receivable blocks for %s", account)
        response = await self._rpc.receivable(
            account,
            threshold=threshold,
            source=include_source,
        )
        try_raise_error(response)
        return self._ensure_dict_response(response)

    async def account_history(
        self,
        account: str,
        *,
        count: Optional[int] = None,
        raw: bool = False,
        head: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get account transaction history.

        Args:
            account: Account address
            count: Number of transactions
            raw: Return amounts in raw units
            head: Start from specific block hash

        Returns:
            Dict containing account history
        """
        logger.debug("Fetching history for %s", account)
        response = await self._rpc.account_history(
            account,
            count=count,
            raw=raw,
            head=head,
        )
        try_raise_error(response)
        return self._ensure_dict_response(response)
