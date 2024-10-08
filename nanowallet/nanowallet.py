# nano_wallet_lib/nanowallet.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
from nanorpc.client import NanoRpcTyped
from .rpc_errors import account_not_found, zero_balance, block_not_found, no_error, get_error, raise_error
from .utils import nano_to_raw, raw_to_nano, handle_errors, reload_after, NanoException
from nano_lib_py import generate_account_private_key, get_account_id, Block, validate_account_id, get_account_public_key


class NanoWallet:
    """
    A class representing a Nano wallet.
    """

    def __init__(self, rpc: NanoRpcTyped, seed: str, index: int,
                 use_work_peers: bool = True,
                 default_representative: str = "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"):
        """
        Initializes the NanoWallet.

        :param rpc: An instance of NanoRpcTyped client.
        :param seed: The seed of the wallet.
        :param index: The account index derived from the seed.
        :param use_work_peers: Whether to use work peers for PoW generation.
        :param default_representative: defaults to gr0vity's representative node.
        """
        self.rpc = rpc
        self.seed = seed
        self.index = index
        self.use_work_peers = use_work_peers
        self.default_representative = default_representative

        self.private_key = generate_account_private_key(seed, index)
        self.account = get_account_id(private_key=self.private_key)
        self.balance = 0.0
        self.weight = 0.0
        self.balance_raw = 0
        self.weight_raw = 0
        self.receivable_balance = 0.0
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

        if source_hash and destination_account:
            raise ValueError(
                "Specify either `source_hash` or `destination_account`. Never both")
        if not source_hash and not destination_account:
            raise ValueError(
                "Missing argument. Specify either `source_hash` or `destination_account`.")

        if destination_account:
            link = get_account_public_key(account_id=destination_account)
        elif source_hash:
            link = source_hash

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
        response = await self.rpc.account_info(self.account, weight=True, receivable=True, representative=True)
        return response

    async def _block_info(self, block_hash: str) -> Dict[str, Any]:
        response = await self.rpc.blocks_info([block_hash], source=True, receive_hash=True, json_block=True)
        raise_error(response, more=f" {block_hash}")
        return response['blocks'][block_hash]

    async def _generate_work(self, pow_hash: str) -> str:
        response = await self.rpc.work_generate(pow_hash, use_peers=self.use_work_peers)
        raise_error(response)
        return response['work']

    @handle_errors
    async def reload(self):
        """
        Reloads the wallet's account information and receivable blocks.
        """
        response = await self.rpc.receivable(self.account, threshold=1)
        raise_error(response)

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
        else:
            raise ValueError(get_error(account_info))

    @handle_errors
    @reload_after
    async def send(self, destination_account: str, amount: float) -> str:
        """
        Sends Nano to a destination account.

        :param destination_account: The destination account ID.
        :param amount: The amount in Nano.
        :return: The hash of the sent block.
        :raises ValueError: If the destination account ID is invalid, account not found, or insufficient balance.
        """
        if not validate_account_id(destination_account):
            raise ValueError("Invalid destination account ID.")

        amount_raw = nano_to_raw(amount)

        account_info = await self._account_info()
        if account_not_found(account_info):
            raise ValueError("Account not found.")
        if zero_balance(account_info):
            raise ValueError("Insufficient balance.")

        balance = int(account_info["balance"])
        new_balance = balance - amount_raw
        if new_balance < 0:
            msg = f"""Insufficient funds! balance_raw:{
                balance} amount_raw:{amount_raw}"""
            raise ValueError(msg)

        block = await self._build_block(
            previous=account_info["frontier"],
            representative=account_info["representative"],
            balance=new_balance,
            destination_account=destination_account
        )

        response = await self.rpc.process(block.json())
        raise_error(response)
        return response['hash']

    @handle_errors
    async def send_raw(self, destination_account: str, amount_raw: int) -> str:
        """
        Sends Nano to a destination account.

        :param destination_account: The destination account ID.
        :param amount_raw: The amount in raw.
        :return: The hash of the sent block.
        """
        amount = raw_to_nano(amount_raw)
        response = await self.send(destination_account, amount)
        return response.unwrap()

    @handle_errors
    @reload_after
    async def sweep(self, destination_account: str, sweep_pending: bool = True, threshold_raw: int = None) -> str:
        """
        Transfers all funds from the current account to the destination account.

        :param destination_account: The account ID to receive the funds.
        :param sweep_pending: Whether to receive pending blocks before sending.
        :param threshold_raw: Minimum amount to consider for receiving pending blocks (in raw).
        :return: The hash of the sent block.
        :raises ValueError: If the destination account ID is invalid or insufficient balance.
        """
        if not validate_account_id(destination_account):
            raise ValueError("Invalid destination account ID.")

        if sweep_pending:
            await self.receive_all(threshold_raw=threshold_raw)

        account_info = await self._account_info()
        if account_not_found(account_info):
            raise ValueError("Account not found.")
        if zero_balance(account_info):
            raise ValueError("Insufficient balance.")

        block = await self._build_block(
            previous=account_info["frontier"],
            representative=account_info["representative"],
            balance=0,
            destination_account=destination_account
        )

        response = await self.rpc.process(block.json())
        raise_error(response)
        return response['hash']

    @handle_errors
    async def list_receivables(self, threshold_raw: int = None) -> List[tuple]:
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
    async def receive_by_hash(self, block_hash: str) -> dict:
        """
        Receives a specific block by its hash.

        :param block_hash: The hash of the block to receive.
        :return: A dictionary with information about the received block.
        :raises ValueError: If the block is not found.
        """
        send_block_info = await self._block_info(block_hash)
        amount_raw = int(send_block_info['amount'])

        account_info = await self._account_info()
        if account_not_found(account_info):
            # Account is unopened
            previous = '0' * 64
            balance = 0
            representative = self.default_representative
        else:
            previous = account_info["frontier"]
            balance = int(account_info["balance"])
            representative = account_info["representative"]

        new_balance = balance + amount_raw

        block = await self._build_block(
            previous=previous,
            representative=representative,
            balance=new_balance,
            source_hash=block_hash
        )

        response = await self.rpc.process(block.json())
        raise_error(response)

        result = {
            'hash': response['hash'],
            'amount_raw': amount_raw,
            'amount': raw_to_nano(amount_raw),
            'source': send_block_info['block_account']
        }

        return result

    @ handle_errors
    async def receive_all(self, threshold_raw: float = None) -> list:
        """
        Receives all pending receivable blocks.
        """
        block_results = []
        response = await self.list_receivables(threshold_raw=threshold_raw)
        receivables = response.unwrap()

        for receivable in receivables:
            response_2 = await self.receive_by_hash(receivable[0])
            block_results.append(response_2.unwrap())

        return block_results

    @handle_errors
    async def refund_first_sender(self) -> str:
        """
        Sends remaining funds to the account opener.

        :return: The hash of the sent block.
        :raises ValueError: If no funds are available or the refund account cannot be determined.
        """
        if not await self.has_balance():
            raise ValueError("No funds available to refund.")
        if self.open_block:
            block_info = await self._block_info(self.open_block)
            refund_account = block_info['source_account']
        elif self.receivable_blocks:
            first_receivable_hash = next(iter(self.receivable_blocks))
            block_info = await self._block_info(first_receivable_hash)
            refund_account = block_info['source_account']
        else:
            raise ValueError("Cannot determine refund account.")
        return await self.sweep(refund_account)

    @handle_errors
    async def has_balance(self) -> bool:
        """
        Checks if the account has available balance or receivable balance.

        :return: True if balance or receivable balance is greater than zero, False otherwise.
        """
        await self.reload()
        if (self.balance_raw and self.balance_raw > 0) or (self.receivable_balance_raw and self.receivable_balance_raw > 0):
            return True
        return False

    @handle_errors
    async def balance_info(self) -> dict:
        """
        Returns the balance and receivable balance in Nano and raw amounts.

        :return: A dictionary containing balance information.
        """
        await self.reload()
        return {
            "balance": self.balance,
            "balance_raw": self.balance_raw,
            "receivable_balance": self.receivable_balance,
            "receivable_balance_raw": self.receivable_balance_raw,
        }


class WalletUtils:

    @staticmethod
    def raw_to_nano(amount_raw: int) -> float:
        """
        Converts raw amount to Nano.

        :param amount_raw: The amount in raw.
        :return: The amount in Nano.
        """
        return raw_to_nano(amount_raw)

    @staticmethod
    def nano_to_raw(amount_nano: float) -> int:
        """
        Converts Nano amount to raw amount.

        :param amount_nano: The amount in Nano.
        :return: The amount in raw.
        """
        return nano_to_raw(amount_nano)

    @staticmethod
    def sum_received_amount(receive_all_response: List[dict]) -> dict:
        """
        Sums the amount_raw values from a list of receivable responses.

        :param receive_all_response: A list of dictionaries containing 'amount_raw'.
        :return: A dictionary with the total amount in raw and Nano.
        """
        total_amount_raw = sum(int(item['amount_raw'])
                               for item in receive_all_response)
        return {
            "amount_raw": total_amount_raw,
            "amount": raw_to_nano(total_amount_raw)
        }
