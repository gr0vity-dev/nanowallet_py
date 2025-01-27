from typing import Optional, Protocol, Dict, Any
from decimal import Decimal
import asyncio
import time
import logging


from nanorpc.client import NanoRpcTyped
from nano_lib_py import (
    Block,
    get_account_id,
    get_account_public_key,
)


from ..models import WalletConfig
from ..utils.conversion import raw_to_nano, nano_to_raw
from ..utils.validation import validate_account_id, validate_nano_amount
from ..utils.decorators import handle_errors, reload_after

from ..errors import (
    try_raise_error,
    account_not_found,
    BlockNotFoundError,
    InsufficientBalanceError,
    InvalidAccountError,
    TimeoutException,
)
from .read_only import NanoWalletReadOnly, NanoWalletReadOnlyProtocol

# Configure logging
logger = logging.getLogger(__name__)

# Constants
ZERO_HASH = "0" * 64
DEFAULT_THRESHOLD_RAW = 10**24


class NanoWalletKeyProtocol(NanoWalletReadOnlyProtocol, Protocol):
    """Protocol defining key operations for a Nano wallet"""

    private_key: str  # The private key for signing transactions

    async def send(self, destination_account: str, amount: Decimal | str | int) -> str:
        """Sends Nano to a destination account"""
        ...

    async def send_raw(self, destination_account: str, amount: int) -> str:
        """Sends Nano to a destination account"""
        ...

    async def receive(self, source_hash: str) -> str:
        """Receives Nano from a source account"""
        ...

    async def sweep(
        self,
        destination_account: str,
        sweep_pending: bool = True,
        threshold_raw: int = DEFAULT_THRESHOLD_RAW,
    ) -> str:
        """Transfers all funds from the current account to the destination account"""
        ...

    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> dict:
        """Receives a specific block by its hash"""
        ...

    async def receive_all(
        self,
        threshold_raw: float = DEFAULT_THRESHOLD_RAW,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> list:
        """Receives all pending receivable blocks"""
        ...

    async def refund_first_sender(self) -> str:
        """Sends remaining funds to the account opener"""
        ...


class NanoWalletKey(NanoWalletReadOnly, NanoWalletKeyProtocol):
    """Key operations implementation of NanoWallet"""

    def __init__(
        self,
        rpc: NanoRpcTyped,
        private_key: str,
        config: Optional[WalletConfig] = None,
    ):
        """
        Initialize wallet with a private key.

        :param rpc: RPC client
        :param private_key: Private key for signing transactions
        :param config: Optional wallet configuration
        """
        # First get the account from the private key
        account = get_account_id(private_key=private_key)
        super().__init__(rpc, account, config)
        self.private_key = private_key

    async def _build_block(
        self,
        previous: str,
        representative: str,
        balance: int,
        source_hash: Optional[str] = None,
        destination_account: Optional[str] = None,
    ) -> Block:
        """
        Builds a state block with the given parameters.

        :param previous: Previous block hash or zeros for first block
        :param representative: Representative account
        :param balance: Account balance after this block
        :param source_hash: Hash of send block to receive (for receive blocks)
        :param destination_account: Destination account (for send blocks)
        :return: Block instance
        :raises ValueError: If parameters are invalid
        """
        if source_hash and destination_account:
            raise ValueError(
                "Specify either `source_hash` or `destination_account`. Never both"
            )
        if not source_hash and not destination_account:
            raise ValueError(
                "Missing argument. Specify either `source_hash` or `destination_account`."
            )

        # Initialize link before using it
        link = None
        if destination_account:
            link = get_account_public_key(account_id=destination_account)
        elif source_hash:
            link = source_hash

        if link is None:
            raise ValueError("Failed to generate link value")

        block = Block(
            block_type="state",
            account=self.account,
            previous=previous,
            representative=representative,
            balance=balance,
            link=link,
        )

        Block.sign(block, self.private_key)
        work = await self._generate_work(block.work_block_hash)
        block.work = work
        return block

    async def _generate_work(self, pow_hash: str) -> str:
        """
        Generate proof of work for a block.

        :param pow_hash: The hash to generate work for
        :return: The generated work value
        :raises ValueError: If work generation fails
        """
        response = await self.rpc.work_generate(
            pow_hash, use_peers=self.config.use_work_peers
        )
        try_raise_error(response)
        return response["work"]

    async def _wait_for_confirmation(self, block_hash: str, timeout: int = 300) -> bool:
        """Wait for block confirmation with exponential backoff."""
        start_time = time.time()
        delay = 0.5  # Start with 500ms
        max_delay = 32  # Cap maximum delay
        attempt = 1

        logger.debug(
            f"Starting confirmation wait for {block_hash} with timeout={timeout}"
        )

        while (time.time() - start_time) < timeout:
            try:
                block_info = await self._block_info(block_hash)
                confirmed = block_info.get("confirmed", "false") == "true"
                logger.debug(
                    f"Confirmation check attempt {attempt}: confirmed={confirmed}, elapsed={time.time() - start_time}"
                )

                if confirmed:
                    return True

                # Exponential backoff with cap
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                attempt += 1

            except BlockNotFoundError:
                logger.debug(
                    f"Block not found on attempt {attempt}, retrying after {delay}s"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                attempt += 1
                continue

        logger.debug(f"Confirmation wait timed out after {time.time() - start_time}s")
        return False

    async def _process_block(self, block: Block, operation: str) -> str:
        """
        Process a block and handle errors consistently.

        :param block: The block to process
        :param operation: Description of the operation (for logging)
        :return: Hash of the processed block
        :raises ValueError: If block processing fails
        """
        try:
            response = await self.rpc.process(block.json())
            try_raise_error(response)
            block_hash = response["hash"]
            logger.debug(f"Successfully processed {operation}, hash: {block_hash}")
            return block_hash
        except Exception as e:
            logger.error(f"Failed to process {operation}: {str(e)}")
            raise

    async def _get_block_params(self) -> Dict[str, Any]:
        """
        Get common parameters for block creation.

        :return: Dictionary with previous block hash, balance, and representative
        :raises ValueError: If account info cannot be retrieved
        """
        account_info = await self._account_info()
        if account_not_found(account_info):
            logger.debug(f"Account {self.account} not found, using default parameters")
            return {
                "previous": ZERO_HASH,
                "balance": 0,
                "representative": self.config.default_representative,
            }

        logger.debug(
            f"Retrieved block params for {self.account}: balance={account_info['balance']}"
        )
        return {
            "previous": account_info["frontier"],
            # this is actually balance_raw
            "balance": int(account_info["balance"]),
            "representative": account_info["representative"],
        }

    @handle_errors
    @reload_after
    async def send(self, destination_account: str, amount: Decimal | str | int) -> str:
        """
        Sends Nano to a destination account.

        Args:
            destination_account: The destination account
            amount: The amount in Nano (as Decimal, string, or int)

        Returns:
            str: The hash of the sent block

        Raises:
            TypeError: If amount is float or invalid type
            ValueError: If amount is negative or invalid format
            InvalidAccountError: If destination account is invalid
            InsufficientBalanceError: If insufficient balance
        """
        amount_decimal = validate_nano_amount(amount)
        amount_raw = nano_to_raw(amount_decimal)
        response = await self.send_raw(destination_account, amount_raw)
        return response.unwrap()

    @handle_errors
    @reload_after
    async def send_raw(self, destination_account: str, amount_raw: int) -> str:
        """
        Sends Nano to a destination account.

        :param destination_account: The destination account
        :param amount_raw: The amount in raw
        :return: The hash of the sent block
        :raises InvalidAccountError: If destination account is invalid
        :raises InsufficientBalanceError: If insufficient balance
        """
        logger.debug(f"Attempting to send {amount_raw} raw to {destination_account}")

        if not destination_account:
            logger.error(f"Invalid destination account: {destination_account}")
            raise InvalidAccountError("Destination can't be None")

        if not validate_account_id(destination_account):
            logger.error(f"Invalid destination account: {destination_account}")
            raise InvalidAccountError("Invalid destination account.")

        params = await self._get_block_params()
        new_balance = params["balance"] - amount_raw

        if params["balance"] == 0 or new_balance < 0:
            msg = f"Insufficient balance for send! balance:{params['balance']} send_amount:{amount_raw}"
            logger.error(msg)
            raise InsufficientBalanceError(msg)

        block = await self._build_block(
            previous=params["previous"],
            representative=params["representative"],
            balance=new_balance,
            destination_account=destination_account,
        )

        return await self._process_block(
            block, f"send of {amount_raw} raw to {destination_account}"
        )

    @handle_errors
    @reload_after
    async def sweep(
        self,
        destination_account: str,
        sweep_pending: bool = True,
        threshold_raw: int = DEFAULT_THRESHOLD_RAW,
    ) -> str:
        """
        Transfers all funds from the current account to the destination account.

        :param destination_account: The account to receive the funds.
        :param sweep_pending: Whether to receive pending blocks before sending.
        :param threshold_raw: Minimum amount to consider for receiving pending blocks (in raw).
        :return: The hash of the sent block.
        :raises ValueError: If the destination account is invalid or insufficient balance.
        """
        if not validate_account_id(destination_account):
            raise InvalidAccountError("Invalid destination account.")

        if sweep_pending:
            await self.receive_all(threshold_raw=threshold_raw)

        response = await self.send_raw(destination_account, self.balance_raw)
        return response.unwrap()

    @handle_errors
    @reload_after
    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> dict:
        """Receives a specific block by its hash."""
        logger.debug(
            f"Starting receive_by_hash for block {block_hash}, wait_confirmation={wait_confirmation}, timeout={timeout}"
        )

        try:
            send_block_info = await self._block_info(block_hash)
            amount_raw = int(send_block_info["amount"])
            logger.debug(f"Block {block_hash} contains {amount_raw} raw")

            params = await self._get_block_params()
            new_balance = params["balance"] + amount_raw
            logger.debug(f"Building block with new_balance={new_balance}")

            block = await self._build_block(
                previous=params["previous"],
                representative=params["representative"],
                balance=new_balance,
                source_hash=block_hash,
            )

            received_hash = await self._process_block(
                block, f"receive of {amount_raw} raw from block {block_hash}"
            )
            logger.debug(f"Block processed with hash {received_hash}")

            if wait_confirmation:
                start_time = time.time()
                logger.debug(
                    f"Starting confirmation wait at {start_time}, timeout={timeout}"
                )

                confirmed = await self._wait_for_confirmation(received_hash, timeout)
                elapsed = time.time() - start_time
                logger.debug(
                    f"Confirmation wait finished. confirmed={confirmed}, elapsed={elapsed}"
                )

                if not confirmed:
                    logger.debug(f"Confirmation timeout, raising TimeoutError")
                    raise TimeoutException(
                        f"Block {received_hash} not confirmed within {timeout} seconds"
                    )

            result = {
                "hash": received_hash,
                "amount_raw": amount_raw,
                "amount": raw_to_nano(amount_raw),
                "source": send_block_info["block_account"],
                "confirmed": wait_confirmation and confirmed,
            }
            logger.debug(f"Returning result: {result}")
            return result

        except Exception as e:
            logger.debug(f"Exception in receive_by_hash: {type(e).__name__}: {str(e)}")
            raise

    @handle_errors
    @reload_after
    async def receive_all(
        self,
        threshold_raw: float = DEFAULT_THRESHOLD_RAW,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> list:
        """
        Receives all pending receivable blocks.

        Args:
            threshold_raw: Minimum amount to receive
            wait_confirmation: If True, wait for block confirmations
            timeout: Max seconds to wait for each confirmation

        Returns:
            List of dictionaries with information about each received block
        """
        block_results = []
        response = await self.list_receivables(threshold_raw=threshold_raw)
        receivables = response.unwrap()

        for receivable in receivables:
            response = await self.receive_by_hash(
                receivable[0], wait_confirmation=wait_confirmation, timeout=timeout
            )
            block_results.append(response.unwrap())

        return block_results

    @handle_errors
    async def refund_first_sender(self) -> str:
        """
        Sends remaining funds to the account opener.

        :return: The hash of the sent block.
        :raises ValueError: If no funds are available or the refund account cannot be determined.
        """
        has_balance = await self.has_balance()
        if not has_balance.unwrap():
            raise InsufficientBalanceError(
                "Insufficient balance. No funds available to refund."
            )
        if self.open_block:
            block_info = await self._block_info(self.open_block)
            refund_account = block_info["source_account"]
        elif self.receivable_blocks:
            first_receivable_hash = next(iter(self.receivable_blocks))
            block_info = await self._block_info(first_receivable_hash)
            refund_account = block_info["block_account"]
        else:
            raise ValueError("Cannot determine refund account.")

        response = await self.sweep(refund_account)
        return response.unwrap()
