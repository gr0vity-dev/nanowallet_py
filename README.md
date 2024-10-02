# NanoWallet Library


**nanowallet_py** is a Python library that provides an easy-to-use interface for interacting with Nano nodes. This library allows you to manage your Nano account inside a wallet. It allows you to send and receive transactions, and interact with the Nano network using the `NanoRpcTyped` client.

## Installation

You can install NanoWallet using pip:

```
pip install nanowallet
```

## Usage

Here's a basic example of how to use the NanoWallet library:

```python
import asyncio
from nanorpc.client import NanoRpcTyped
from nanowallet import NanoWallet

async def main():
    # Replace with your RPC endpoint
    rpc = NanoRpcTyped(url='http://localhost:7076')
    seed = '4f2dd...'  # Replace with your seed
    index = 0

    wallet = NanoWallet(rpc, seed, index)
    await wallet.reload()  # Optional - loads all account data
    print(wallet.account)
    print(wallet.receivable_blocks)

    response = await wallet.receive_all()
    if response.success:
        print(response.value)  # list of received block hashes

asyncio.run(main())
```

## Features

- Create and manage Nano wallets
- Send and receive Nano transactions
- Check account balance and pending blocks
- Use work peers for PoW (Proof of Work) generation.
- Handle errors with a robust error handling system
- Seamlessly reload wallet state.

## Available Methods

- `reload()`:  
  Loads the current state of the wallet, including balance, receivable blocks, account info, and more.

- `send(destination_account: str, amount: float)`:  
  Sends a specified amount of Nano to the destination account. Returns the hash of the sent block.

- `receive_by_hash(block_hash: str)`:  
  Receives a specific receivable block by its hash. Returns the hash of the received block.

- `sweep(destination_account: str)`:  
  Sends all available funds from the current wallet to the specified destination account.

- `receive_all(threshold: float = None)`:  
  Receives all pending receivable blocks. Optionally, a threshold can be set to only receive blocks with amounts greater than the threshold.

- `list_receivables(threshold: float = None)`:  
  Lists all receivable blocks, sorted by the amount in descending order. A threshold can be used to filter the results.

- `refund_first_sender()`:  
  Receives all receivable blocks and sends the entire funds back to the first sender (i.e., the account opener or eldest unreceived block).


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or create an issue for any bugs or feature requests.

## License

This project is licensed under an open-source license that allows free use and modification for both commercial and private use. For more details, please see the LICENSE file in the repository.