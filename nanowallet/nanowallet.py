# nano_wallet_lib/nanowallet.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
from nanorpc.client import NanoRpcTyped
from .errors import try_raise_error, account_not_found, no_error, block_not_found
from .errors import InsufficientBalanceError, InvalidAccountError, BlockNotFoundError, InvalidSeedError, InvalidIndexError, TimeoutException
from .utils import nano_to_raw, raw_to_nano, handle_errors, reload_after, validate_nano_amount, NanoResult
from nano_lib_py import generate_account_private_key, get_account_id, Block, validate_account_id, get_account_public_key
from dataclasses import dataclass
import logging
from decimal import Decimal
import asyncio
import time

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class WalletConfig:
    """Configuration for NanoWallet"""
    use_work_peers: bool = False
    default_representative: str = "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"


# Constants
SEED_LENGTH = 64  # Length of hex seed
MAX_INDEX = 4294967295  # Maximum index value (2^32 - 1)
ZERO_HASH = "0" * 64
DEFAULT_THRESHOLD_RAW = 10 ** 24


class NanoWallet:
    """
    A class representing a Nano wallet.
    """

    def __init__(self, rpc: NanoRpcTyped, seed: str, index: int,
                 config: Optional[WalletConfig] = None):
        """
        Initializes the NanoWallet.

        :param rpc: An instance of NanoRpcTyped client
        :param seed: The seed of the wallet (64 character hex string)
        :param index: The account index derived from the seed (0 to 2^32-1)
        :param config: Optional wallet configuration
        :raises InvalidSeedError: If seed format is invalid
        :raises InvalidIndexError: If index is out of valid range
        """
        # Validate seed
        if not isinstance(seed, str) or len(seed) != SEED_LENGTH or not all(c in '0123456789abcdefABCDEF' for c in seed):
            logger.error(
                f"Invalid seed format provided: length={len(seed) if isinstance(seed, str) else 'N/A'}")
            raise InvalidSeedError("Seed must be a 64 character hex string")

        # Validate index
        if not isinstance(index, int) or index < 0 or index > MAX_INDEX:
            logger.error(f"Invalid index provided: {index}")
            raise InvalidIndexError(f"Index must be between 0 and {MAX_INDEX}")

        self.rpc = rpc
        self.seed = seed.lower()  # Normalize to lowercase
        self.index = index
        self.config = config or WalletConfig()

        self.private_key = generate_account_private_key(self.seed, index)
        self.account = get_account_id(private_key=self.private_key)
        logger.debug(
            f"Initialized wallet for account {self.account} with index {index}")
        self._init_account_state()

    def _init_account_state(self):
        """Initialize account state variables"""
        self.balance = Decimal('0.0')
        self.weight = Decimal('0.0')
        self.balance_raw = 0
        self.weight_raw = 0
        self.receivable_balance = Decimal('0.0')
        self.receivable_balance_raw = 0
        self.confirmation_height = 0
        self.block_count = 0

        self.frontier_block = None
        self.representative_block = None
        self.representative = None
        self.open_block = None

        self.receivable_blocks = {}

    async def _build_block(self, previous: str, representative: str, balance: int,
                           source_hash: Optional[str] = None, destination_account: Optional[str] = None) -> Block:
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
                "Specify either `source_hash` or `destination_account`. Never both")
        if not source_hash and not destination_account:
            raise ValueError(
                "Missing argument. Specify either `source_hash` or `destination_account`.")

        # Initialize link before using it
        link = None
        if destination_account:
            link = get_account_public_key(account_id=destination_account)
        elif source_hash:
            link = source_hash

        if link is None:
            raise ValueError("Failed to generate link value")

        block = Block(
            block_type='state',
            account=self.account,
            previous=previous,
            representative=representative,
            balance=balance,
            link=link
        )

        Block.sign(block, self.private_key)
        work = await self._generate_work(block.work_block_hash)
        block.work = work
        return block

    async def _account_info(self) -> Dict[str, Any]:
        """
        Get account information from the RPC.

        :return: Dictionary containing account information including balance, representative, etc.
        """
        response = await self.rpc.account_info(self.account, weight=True, receivable=True, representative=True, include_confirmed=False)
        return response

    async def _block_info(self, block_hash: str) -> Dict[str, Any]:
        """
        Get information about a specific block.

        :param block_hash: The hash of the block to get information about
        :return: Dictionary containing block information
        :raises ValueError: If block is not found or RPC returns an error
        """
        response = await self.rpc.blocks_info([block_hash], source=True, receive_hash=True, json_block=True)
        if block_not_found(response):
            raise BlockNotFoundError(f"Block not found {block_hash}")
        try_raise_error(response)
        return response['blocks'][block_hash]

    async def _generate_work(self, pow_hash: str) -> str:
        """
        Generate proof of work for a block.

        :param pow_hash: The hash to generate work for
        :return: The generated work value
        :raises ValueError: If work generation fails
        """
        response = await self.rpc.work_generate(pow_hash, use_peers=self.config.use_work_peers)
        try_raise_error(response)
        return response['work']

    async def _wait_for_confirmation(self, block_hash: str, timeout: int = 300) -> bool:
        """Wait for block confirmation with exponential backoff."""
        start_time = time.time()
        delay = 0.5  # Start with 500ms
        max_delay = 32  # Cap maximum delay
        attempt = 1

        logger.debug(
            f"Starting confirmation wait for {block_hash} with timeout={timeout}")

        while (time.time() - start_time) < timeout:
            try:
                block_info = await self._block_info(block_hash)
                confirmed = block_info.get("confirmed", "false") == "true"
                logger.debug(
                    f"Confirmation check attempt {attempt}: confirmed={confirmed}, elapsed={time.time() - start_time}")

                if confirmed:
                    return True

                # Exponential backoff with cap
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                attempt += 1

            except BlockNotFoundError:
                logger.debug(
                    f"Block not found on attempt {attempt}, retrying after {delay}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                attempt += 1
                continue

        logger.debug(
            f"Confirmation wait timed out after {time.time() - start_time}s")
        return False

    @handle_errors
    async def reload(self):
        """
        Reloads the wallet's account information and receivable blocks.
        """
        response = await self.rpc.receivable(self.account, threshold=1)
        try_raise_error(response)

        self.receivable_blocks = response["blocks"]
        account_info = await self._account_info()
        if account_not_found(account_info) and self.receivable_blocks:
            # New account with receivable blocks
            self.receivable_balance_raw = sum(
                int(amount) for amount in self.receivable_blocks.values())
            self.receivable_balance = raw_to_nano(self.receivable_balance_raw)
        elif no_error(account_info):
            self.balance = raw_to_nano(account_info["balance"])
            self.balance_raw = int(account_info["balance"])
            self.frontier_block = account_info["frontier"]
            self.representative_block = account_info["representative_block"]
            self.representative = account_info["representative"]
            self.open_block = account_info["open_block"]
            self.confirmation_height = int(account_info["confirmation_height"])
            self.block_count = int(account_info["block_count"])
            self.weight = raw_to_nano(account_info["weight"])
            self.weight_raw = int(account_info["weight"])
            self.receivable_balance = raw_to_nano(account_info["receivable"])
            self.receivable_balance_raw = int(account_info["receivable"])
            self.total_balance_raw = self.receivable_balance_raw + self.balance_raw

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
            block_hash = response['hash']
            logger.debug(
                f"Successfully processed {operation}, hash: {block_hash}")
            return block_hash
        except Exception as e:
            logger.error(f"Failed to process {operation}: {str(e)}")
            raise

    @handle_errors
    @reload_after
    async def send(self, destination_account: str, amount: Decimal | str | int) -> NanoResult[str]:
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
    async def send_raw(self, destination_account: str, amount_raw: int) -> NanoResult[str]:
        """
        Sends Nano to a destination account.

        :param destination_account: The destination account
        :param amount_raw: The amount in raw
        :return: The hash of the sent block
        :raises InvalidAccountError: If destination account is invalid
        :raises InsufficientBalanceError: If insufficient balance
        """
        logger.debug(
            f"Attempting to send {amount_raw} raw to {destination_account}")

        if not destination_account:
            logger.error(f"Invalid destination account: {destination_account}")
            raise InvalidAccountError("Destination can't be None")

        if not validate_account_id(destination_account):
            logger.error(f"Invalid destination account: {destination_account}")
            raise InvalidAccountError("Invalid destination account.")

        params = await self._get_block_params()
        new_balance = params['balance'] - amount_raw

        if params['balance'] == 0 or new_balance < 0:
            msg = f"Insufficient balance for send! balance:{params['balance']} send_amount:{amount_raw}"
            logger.error(msg)
            raise InsufficientBalanceError(msg)

        block = await self._build_block(
            previous=params['previous'],
            representative=params['representative'],
            balance=new_balance,
            destination_account=destination_account
        )

        return await self._process_block(block, f"send of {amount_raw} raw to {destination_account}")

    @handle_errors
    @reload_after
    async def sweep(self, destination_account: str, sweep_pending: bool = True, threshold_raw: int = DEFAULT_THRESHOLD_RAW) -> NanoResult[str]:
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
    async def list_receivables(self, threshold_raw: int = DEFAULT_THRESHOLD_RAW) -> NanoResult[List[tuple]]:
        """
        Lists receivable blocks sorted by descending amount.

        :param threshold_raw: Minimum amount to consider (in raw).
        :return: A list of tuples containing block hashes and amounts.
        """
        await self.reload()

        # If receivable_blocks is empty, return an empty list
        if not self.receivable_blocks:
            return []

        # Filter blocks based on threshold if provided
        filtered_blocks = self.receivable_blocks.items()
        if threshold_raw is not None:
            filtered_blocks = [
                (block, amount) for block, amount in filtered_blocks
                if int(amount) >= threshold_raw
            ]

        # Sort the filtered blocks by descending amount
        sorted_receivables = sorted(
            filtered_blocks,
            key=lambda x: int(x[1]),
            reverse=True
        )

        return sorted_receivables

    @handle_errors
    @reload_after
    async def receive_by_hash(self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30) -> NanoResult[dict]:
        """Receives a specific block by its hash."""
        logger.debug(
            f"Starting receive_by_hash for block {block_hash}, wait_confirmation={wait_confirmation}, timeout={timeout}")

        try:
            send_block_info = await self._block_info(block_hash)
            amount_raw = int(send_block_info['amount'])
            logger.debug(f"Block {block_hash} contains {amount_raw} raw")

            params = await self._get_block_params()
            new_balance = params['balance'] + amount_raw
            logger.debug(f"Building block with new_balance={new_balance}")

            block = await self._build_block(
                previous=params['previous'],
                representative=params['representative'],
                balance=new_balance,
                source_hash=block_hash
            )

            received_hash = await self._process_block(block, f"receive of {amount_raw} raw from block {block_hash}")
            logger.debug(f"Block processed with hash {received_hash}")

            if wait_confirmation:
                start_time = time.time()
                logger.debug(
                    f"Starting confirmation wait at {start_time}, timeout={timeout}")

                confirmed = await self._wait_for_confirmation(received_hash, timeout)
                elapsed = time.time() - start_time
                logger.debug(
                    f"Confirmation wait finished. confirmed={confirmed}, elapsed={elapsed}")

                if not confirmed:
                    logger.debug(f"Confirmation timeout, raising TimeoutError")
                    raise TimeoutException(
                        f"Block {received_hash} not confirmed within {timeout} seconds")

            result = {
                'hash': received_hash,
                'amount_raw': amount_raw,
                'amount': raw_to_nano(amount_raw),
                'source': send_block_info['block_account'],
                'confirmed': wait_confirmation and confirmed
            }
            logger.debug(f"Returning result: {result}")
            return result

        except Exception as e:
            logger.debug(
                f"Exception in receive_by_hash: {type(e).__name__}: {str(e)}")
            raise

    @handle_errors
    @reload_after
    async def receive_all(self, threshold_raw: float = DEFAULT_THRESHOLD_RAW,
                          wait_confirmation: bool = True,
                          timeout: int = 30) -> NanoResult[list]:
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
            response_2 = await self.receive_by_hash(
                receivable[0],
                wait_confirmation=wait_confirmation,
                timeout=timeout
            )
            block_results.append(response_2.unwrap())

        return block_results

    @handle_errors
    async def refund_first_sender(self) -> NanoResult[str]:
        """
        Sends remaining funds to the account opener.

        :return: The hash of the sent block.
        :raises ValueError: If no funds are available or the refund account cannot be determined.
        """
        has_balance = await self.has_balance()
        if not has_balance.unwrap():
            raise InsufficientBalanceError(
                "Insufficient balance. No funds available to refund.")
        if self.open_block:
            block_info = await self._block_info(self.open_block)
            refund_account = block_info['source_account']
        elif self.receivable_blocks:
            first_receivable_hash = next(iter(self.receivable_blocks))
            block_info = await self._block_info(first_receivable_hash)
            refund_account = block_info['block_account']
        else:
            raise ValueError("Cannot determine refund account.")

        response = await self.sweep(refund_account)
        result = response.unwrap()
        return result

    @handle_errors
    async def has_balance(self) -> NanoResult[bool]:
        """
        Checks if the account has available balance or receivable balance.

        :return: True if balance or receivable balance is greater than zero, False otherwise.
        """
        await self.reload()
        if (self.balance_raw and self.balance_raw > 0) or (self.receivable_balance_raw and self.receivable_balance_raw > 0):
            return True
        return False

    @handle_errors
    @reload_after
    async def balance_info(self) -> NanoResult[dict]:
        """
        Get detailed balance information for the account.

        :return: Dictionary containing:
            - balance: Current balance in Nano
            - balance_raw: Current balance in raw
            - receivable_balance: Pending receivable balance in Nano
            - receivable_balance_raw: Pending receivable balance in raw
        """
        await self.reload()
        return {
            "balance": self.balance,
            "balance_raw": self.balance_raw,
            "receivable_balance": self.receivable_balance,
            "receivable_balance_raw": self.receivable_balance_raw,
        }

    def to_string(self):
        return (f"NanoWallet:\n"
                f"  Account: {self.account}\n"
                f"  Balance: {self.balance} Nano\n"
                f"  Balance raw: {self.balance_raw} raw\n"
                f"  Receivable Balance: {self.receivable_balance} Nano\n"
                f"  Receivable Balance raw: {self.receivable_balance_raw} raw\n"
                f"  Voting Weight: {self.weight} Nano\n"
                f"  Voting Weight raw: {self.weight_raw} raw\n"
                f"  Representative: {self.representative}\n"
                f"  Confirmation Height: {self.confirmation_height}\n"
                f"  Block Count: {self.block_count}")

    def __str__(self):
        return (f"NanoWallet:\n"
                f"  Account: {self.account}\n"
                f"  Balance raw: {self.balance_raw} raw\n"
                f"  Receivable Balance raw: {self.receivable_balance_raw} raw")

    async def _get_block_params(self) -> Dict[str, Any]:
        """
        Get common parameters for block creation.

        :return: Dictionary with previous block hash, balance, and representative
        :raises ValueError: If account info cannot be retrieved
        """
        account_info = await self._account_info()
        if account_not_found(account_info):
            logger.debug(
                f"Account {self.account} not found, using default parameters")
            return {
                'previous': ZERO_HASH,
                'balance': 0,
                'representative': self.config.default_representative
            }

        logger.debug(
            f"Retrieved block params for {self.account}: balance={account_info['balance']}")
        return {
            'previous': account_info["frontier"],
            # this is actually balance_raw
            'balance': int(account_info["balance"]),
            'representative': account_info["representative"]
        }


class WalletUtils:

    @staticmethod
    def raw_to_nano(amount_raw: int, decimal_places=6) -> Decimal:
        """
        Converts raw amount to Nano, truncating to 6 decimal places.

        Args:
            raw_amount: Amount in raw units

        Returns:
            Decimal: Amount in NANO, truncated to 6 decimal places
        """
        return raw_to_nano(amount_raw, decimal_places=decimal_places)

    @staticmethod
    def nano_to_raw(amount_nano: Decimal | str | int, decimal_places=30) -> int:
        """
        Converts Nano amount to raw amount.

        Args:
            amount_nano: The amount in Nano (as Decimal, string, or int)

        Returns:
            int: The amount in raw

        Raises:
            TypeError: If amount is float or invalid type
            ValueError: If amount is negative or invalid format
        """
        amount_decimal = validate_nano_amount(amount_nano)
        return nano_to_raw(raw_to_nano(nano_to_raw(amount_decimal), decimal_places=decimal_places))

    @staticmethod
    def sum_received_amount(receive_all_response: List[dict]) -> dict:
        """
        Sums the amount_raw values from a list of receivable responses.

        Args:
            receive_all_response: A list of dictionaries containing 'amount_raw'

        Returns:
            dict: A dictionary with the total amount in raw and Nano
        """
        total_amount_raw = sum(int(item['amount_raw'])
                               for item in receive_all_response)
        return {
            "amount_raw": total_amount_raw,
            "amount": raw_to_nano(total_amount_raw)
        }
