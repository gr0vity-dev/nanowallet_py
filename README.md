# Nano Wallet Library (nanowallet)

[![PyPI version](https://badge.fury.io/py/nanowallet.svg)](https://badge.fury.io/py/nanowallet) 
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) 

A modern, asynchronous Python library for interacting with the Nano cryptocurrency network. `nanowallet` supports read-only monitoring and authenticated operations via private key or seed+index, providing full transaction capabilities including sending, receiving, and sweeping funds.

Designed with type safety and robust error handling in mind.

## Key Features

*   **Asynchronous:** Built with `asyncio` for efficient network communication.
*   **Typed:** Fully type-hinted for better developer experience and static analysis.
*   **Wallet Types:**
    *   `NanoWalletReadOnly`: Monitor accounts without exposing keys.
    *   `NanoWalletAuthenticated`: Operate a wallet using a private key (via `create_wallet_from_private_key`) or seed+index (via `create_wallet_from_seed`).
*   **Comprehensive Operations:** Send, receive (specific blocks or all pending), sweep funds, check history, get account info.
*   **Safe Error Handling:** Uses a `NanoResult[T]` wrapper to prevent unexpected crashes, promoting explicit error checks.
*   **Automatic State Management:** Handles Nano's sequential block requirements automatically after operations.
*   **Configurable:** Set default representatives, control work generation sources.
*   **Automatic Retry:** Includes methods like `send_with_retry` for handling transient network/RPC issues.

## Installation

```bash
pip install nanowallet
```
*Requires Python 3.8+*

## Quick Start

```python
import asyncio
from nanowallet import create_wallet_from_seed, NanoWalletRpc, WalletConfig
from nanowallet.utils import sum_received_amount

async def main():
    # Connect to a Nano node
    rpc = NanoWalletRpc(url="http://localhost:7076")
    wallet_config = WalletConfig(use_work_peers=False)  # Optional configuration
    
    # Create wallet from seed and index
    # ------------------------------------------------------------
    wallet = create_wallet_from_seed(
        rpc=rpc,
        seed="0000000000000000000000000000000000000000000000000000000000000000",
        index=0,
        config=wallet_config,
    )
    
    # Check balance
    # ------------------------------------------------------------
    response = await wallet.balance_info()
    balance_info = response.unwrap()  # Option 1 - .unwrap() to handle the response
    print(f"Balance: {balance_info.balance} NANO")
    print(f"Receivable Balance: {balance_info.receivable} NANO")
    
    # Receive all pending transactions
    # ------------------------------------------------------------
    result = await wallet.receive_all()
    if result.success:  # Option 2 - check success
        received_amount = sum_received_amount(result.value)
        print(f"Received {len(result.value)} blocks!")
        print(f"Received amount: {received_amount.amount} NANO")
    else:
        print(f"Error receiving blocks: {result.error}")
    
    # Send entire balance to another account
    # ------------------------------------------------------------
    destination = "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
    send_result = await wallet.sweep(
        destination, sweep_pending=True
    )  # Sweeps pending/receivable balance + confirmed balance
    
    try:
        send_hash = send_result.unwrap()
        print(f"Sent! Block hash: {send_hash}")
    except Exception as e:
        print(f"Error sending: {e}")

asyncio.run(main())
```

That's it! The library handles all the complexity of work generation, block signing, and state management for you.

## Documentation

For full details on wallet types, methods, error handling, and configuration, see the [Full Documentation](DOCUMENTATION.md).

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.