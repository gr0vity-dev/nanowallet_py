# nano_wallet_lib/nanowallet.py
from __future__ import annotations
from nanorpc.client import NanoRpcTyped
from .rpc_errors import account_not_found, zero_balance
from .utils import nano_to_raw, raw_to_nano, handle_errors, reload_after
from nano_lib_py import generate_account_private_key, get_account_id, Block, validate_account_id


class NanoWallet:
    """
    A class representing a Nano wallet.
    """

    def __init__(self, rpc: NanoRpcTyped, seed: str, index: int,
                 use_work_peers: bool = True,
                 default_representative="nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"):
        """
        Initializes the NanoWallet.

        :param rpc: An instance of NanoRpc client.
        :param seed: The seed of the wallet.
        :param index: The account index derived from the seed.
        :param use_work_peers: Whether to use work peers for PoW generation.
        """
        self.rpc = rpc
        self.seed = seed
        self.index = index
        self.use_work_peers = use_work_peers
        self.default_representative = default_representative

        self.private_key = generate_account_private_key(seed, index)
        self.account = get_account_id(private_key=self.private_key)
        self.balance = 0
        self.weight = 0
        self.balance_raw = 0
        self.weight_raw = 0
        self.receivable_balance = 0
        self.receivable_balance_raw = 0
        self.confirmation_height = 0
        self.block_count = 0

        self.frontier_block = None
        self.representative_block = None
        self.representative = None
        self.open_block = None

        self.receivable_blocks = []

    async def _block_info(self, block_hash: str) -> str:
        block_info = await self.rpc.blocks_info([block_hash], source=True)
        return block_info['blocks'][block_hash]

    async def _generate_work(self, pow_hash: str) -> str:
        """
        Generates work for a given hash.

        :param pow_hash: The hash to generate work for.
        :return: The generated work.
        """
        work = await self.rpc.work_generate(pow_hash, use_peers=self.use_work_peers)
        return work['work']
#

    @handle_errors
    async def reload(self):
        receivables = await self.rpc.receivable(self.account, source=True, threshold=1)
        self.receivable_blocks = receivables["blocks"]
        account_info = await self.rpc.account_info(self.account, weight=True, receivable=True, representative=True)

        if account_not_found(account_info) and self.receivable_blocks:
            # new account with receivables blocks
            print(self.receivable_blocks)
            for _, amount in self.receivable_blocks.items():
                self.receivable_balance_raw += int(amount)

            self.receivable_balance = raw_to_nano(self.receivable_balance_raw)
            print("receivable_balance", self.receivable_balance)
            print("receivable_balance_raw", self.receivable_balance_raw)

        if not account_not_found(account_info):
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

    @handle_errors
    @reload_after
    async def send(self, destination_account: str, amount: float) -> str:
        """
        Sends Nano to a destination account.

        :param destination_account: The destination account ID.
        :param amount: The amount in Nano.
        :return: The hash of the sent block.
        """
        if not validate_account_id(destination_account):
            raise ValueError("Invalid destination account ID.")

        raw_amount = nano_to_raw(amount)
        account_info = await self.rpc.account_info(self.account)

        previous = account_info["frontier"]
        representative = account_info["representative"]
        balance = int(account_info["balance"])

        new_balance = balance - raw_amount
        if new_balance < 0:
            raise ValueError("Insufficient funds.")

        block = Block(
            block_type='state',
            account=self.account,
            previous=previous,
            representative=representative,
            balance=new_balance,
            link_as_account=destination_account
        )
        Block.sign(block, self.private_key)

        work = await self._generate_work(block.work_block_hash)
        block.work = work

        response = await self.rpc.process(block.json())
        return response["hash"]

    async def send_raw(self, destination_account, amount_raw: int) -> str:
        """
        Sends Nano to a destination account.

        :param destination_account: The destination account ID.
        :param amount_raw: The amount in raw.
        :return: The hash of the sent block.
        """
        amount = raw_to_nano(amount_raw)
        return self.send(destination_account, amount)

    @handle_errors
    @reload_after
    async def sweep(self, destination_account: str, sweep_pending=True, threshold_raw=None) -> str:
        """
        Transfers all funds from the current account to the destination account.

        :param destination_account: The account ID to receive the funds.
        :return: The hash of the sent block.
        """
        if not validate_account_id(destination_account):
            raise ValueError("Invalid destination account ID.")

        if sweep_pending:
            await self.receive_all(threshold_raw=threshold_raw)

        account_info = await self.rpc.account_info(self.account, representative=True)
        if account_not_found(account_info) or zero_balance(account_info):
            return

        block = Block(
            block_type='state',
            account=self.account,
            previous=account_info["frontier"],
            representative=account_info["representative"],
            balance=0,
            link_as_account=destination_account
        )

        Block.sign(block, self.private_key)
        work = await self._generate_work(block.work_block_hash)
        block.work = work

        response = await self.rpc.process(block.json())
        return response['hash']

    @handle_errors
    async def list_receivables(self, threshold_raw: int = None) -> list:
        """
        Lists receivable blocks sorted by descending amount.
        :param threshold_raw: Minimum amount to consider (in raw).
        :return: A list of receivable blocks.
        """
        await self.has_balance()

        # If receivable_blocks is empty, return an empty list
        if not self.receivable_blocks:
            return []

        # Filter blocks based on threshold if provided
        filtered_blocks = self.receivable_blocks.items()
        if threshold_raw is not None:
            filtered_blocks = [
                (block, data) for block, data in filtered_blocks
                if int(data['amount']) >= threshold_raw
            ]

        # Sort the filtered blocks by descending amount
        sorted_receivables = sorted(
            filtered_blocks,
            key=lambda x: int(x[1]['amount']),
            reverse=True
        )

        return sorted_receivables

    @handle_errors
    @reload_after
    async def receive_by_hash(self, block_hash: str) -> str:
        """
        Receives a specific block by its hash.

        :param block_hash: The hash of the block to receive.
        :return: The hash of the received block.
        """
        block_info = await self.rpc.block_info(block_hash)
        amount_raw = int(block_info['amount'])

        account_info = await self.rpc.account_info(self.account, representative=True)
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

        block = Block(
            block_type='state',
            account=self.account,
            previous=previous,
            representative=representative,
            balance=new_balance,
            link=block_hash
        )

        Block.sign(block, self.private_key)

        work = await self._generate_work(block.work_block_hash)
        block.work = work

        response = await self.rpc.process(block.json())
        return response['hash']

    @handle_errors
    async def receive_all(self, threshold_raw: float = None) -> list:
        """
        Receives all pending receivable blocks.
        """
        block_hashes = []
        response = await self.list_receivables(threshold_raw=threshold_raw)
        for receivable in response.value:
            response = await self.receive_by_hash(receivable[0])
            if response.success:
                block_hashes.append(response.value)
            else:
                raise ValueError()
        return block_hashes

    @handle_errors
    async def refund_first_sender(self) -> str:
        """
        Sends remaining funds to the account opener.
        """
        if await self.has_balance():
            if self.open_block:
                block_info = await self._block_info(self.open_block)
                refund_account = block_info['source_account']
            elif self.receivable_blocks:
                refund_account = list(self.receivable_blocks.values())[
                    0]['source']

        return await self.sweep(refund_account)

    @handle_errors
    async def has_balance(self) -> bool:
        """
        Returns true if account has either available balance, receivable balance or both 
        """
        await self.reload()
        if (self.balance_raw and self.balance_raw > 0) or (self.receivable_balance and self.receivable_balance > 0):
            return True

    def raw_to_nano(self, amount_raw) -> int:
        """
        Converts raw amount to Nano.
        """
        return raw_to_nano(amount_raw)
