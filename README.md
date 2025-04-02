# Nano Wallet Library (nanowallet)

[![PyPI version](https://badge.fury.io/py/nanowallet.svg)](https://badge.fury.io/py/nanowallet) <!-- Add badges if you publish -->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) <!-- Choose your license -->

A modern, asynchronous Python library for interacting with the Nano cryptocurrency network. `nanowallet` supports read-only monitoring, key-based operations, and seed-based HD wallets, providing full transaction capabilities including sending, receiving, and sweeping funds.

Designed with type safety and robust error handling in mind.

## Key Features

*   **Asynchronous:** Built with `asyncio` for efficient network communication.
*   **Typed:** Fully type-hinted for better developer experience and static analysis.
*   **Multiple Wallet Types:**
    *   `NanoWalletReadOnly`: Monitor accounts without exposing keys.
    *   `NanoWalletKey`: Operate a wallet using a private key.
    *   `NanoWallet` (Seed-Based): Generate deterministic accounts from a seed (HD Wallet).
*   **Comprehensive Operations:** Send, receive (specific blocks or all pending), sweep funds, check history, get account info.
*   **Safe Error Handling:** Uses a `NanoResult[T]` wrapper to prevent unexpected crashes, promoting explicit error checks.
*   **Automatic State Management:** Handles Nano's sequential block requirements automatically after operations.
*   **Configurable:** Set default representatives, control work generation sources.
*   **Automatic Handling of Concurrent Sends:** Uses a retry mechanism for automatic retries in case of send failures.

## Installation

```bash
pip install nanowallet
# Or if you install from source/git:
# pip install .
```

## Quick Start

```python
import asyncio
from decimal import Decimal
from nanowallet import NanoWallet, NanoWalletRpc, NanoException, WalletConfig
import os

async def main():
    # --- Configuration ---
    # Ensure NANO_NODE_URL and NANO_WALLET_SEED are set as environment variables
    # DO NOT HARDCODE YOUR SEED!
    node_url = os.environ.get("NANO_NODE_URL", "http://localhost:7076") # Default to local node
    wallet_seed = os.environ.get("NANO_WALLET_SEED")

    if not wallet_seed:
        print("Error: NANO_WALLET_SEED environment variable not set.")
        # In a real app, generate a new seed securely if needed
        # For this example, we'll use a placeholder (DO NOT USE FOR REAL FUNDS)
        wallet_seed = "0000000000000000000000000000000000000000000000000000000000000001"
        print(f"Warning: Using placeholder seed: {wallet_seed[:4]}...{wallet_seed[-4:]}")

    # --- Initialization ---
    rpc = NanoWalletRpc(url=node_url)
    # Optional: Configure representative, work peers
    # config = WalletConfig(default_representative="nano_your_rep_here...")
    wallet = NanoWallet(rpc=rpc, seed=wallet_seed, index=0) # First account from seed

    print(f"Initialized Wallet for Account: {wallet.account}")

    # --- Check Balance ---
    print("\nChecking balance...")
    balance_result = await wallet.balance_info()
    if balance_result.success:
        print(f"Current Balance: {balance_result.value.balance} NANO")
        print(f"Receivable Balance: {balance_result.value.receivable} NANO")
    else:
        print(f"Error checking balance: {balance_result.error} ({balance_result.error_code})")

    # --- Receive Pending Blocks (Example) ---
    print("\nAttempting to receive pending blocks...")
    try:
        # Use unwrap() pattern for concise success handling, relies on exception for errors
        received_blocks = (await wallet.receive_all(wait_confirmation=False)).unwrap() # Don't wait for confirmation in this quick example
        if received_blocks:
             total_received = sum(block.amount for block in received_blocks)
             print(f"Successfully received {total_received} NANO across {len(received_blocks)} blocks.")
             # Check balance again (will reflect received amounts due to internal reload)
             balance_result = await wallet.balance_info()
             if balance_result.success:
                 print(f"New Balance: {balance_result.value.balance} NANO")
        else:
            print("No pending blocks found to receive.")

    except NanoException as e:
        print(f"Failed to receive blocks: {e.message} ({e.code})")

    # --- Send Transaction (Example) ---
    print("\nAttempting to send 0.001 NANO...")
    destination = "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6" # Example destination
    amount_to_send = Decimal("0.001")

    send_result = await wallet.send(destination_account=destination, amount=amount_to_send)

    # Use success check pattern
    if send_result.success:
        print(f"Successfully sent {amount_to_send} NANO.")
        print(f"Send Block Hash: {send_result.value}")
        # Check balance again
        balance_result = await wallet.balance_info()
        if balance_result.success:
            print(f"New Balance after send: {balance_result.value.balance} NANO")
    else:
        print(f"Error sending NANO: {send_result.error} ({send_result.error_code})")
        if send_result.error_code == 'INSUFFICIENT_BALANCE':
            print("You might need to fund the account first.")


if __name__ == "__main__":
    asyncio.run(main())
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. <!-- Create this file -->

