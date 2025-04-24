# Nano Wallet Library - Full Documentation

This document provides comprehensive details for the `nanowallet` Python library.

## Table of Contents

1.  [Overview](#overview)
2.  [Installation](#installation)
3.  [Core Concepts](#core-concepts)
    *   [Asynchronous Operations](#asynchronous-operations)
    *   [Wallet Types](#wallet-types)
    *   [Error Handling: `NanoResult`](#error-handling-nanoresult)
    *   [Nano Units: Raw vs. Nano](#nano-units-raw-vs-nano)
    *   [RPC Client (`NanoWalletRpc`)](#rpc-client-nanowalletrpc)
    *   [Configuration (`WalletConfig`)](#configuration-walletconfig)
    *   [Important Decorators](#important-decorators)
4.  [Wallet Initialization](#wallet-initialization)
    *   [RPC Client Setup](#rpc-client-setup)
    *   [Read-Only Wallet](#read-only-wallet-initialization)
    *   [Authenticated Wallet (Seed + Index)](#authenticated-wallet-seed--index)
    *   [Authenticated Wallet (Private Key)](#authenticated-wallet-private-key)
5.  [Key Operations & API](#key-operations--api)
    *   [Method Availability by Wallet Type](#method-availability-by-wallet-type)
    *   [Method Signatures & Descriptions](#method-signatures--descriptions)
6.  [Data Models](#data-models)
    *   [Property Type Conversions](#property-type-conversions)
7.  [Examples](#examples)
    *   [Receiving All Pending Blocks](#receiving-all-pending-blocks)
    *   [Sending with Retry Logic](#sending-with-retry-logic)
    *   [Refunding Incoming Transactions](#refunding-incoming-transactions)
8.  [Best Practices](#best-practices)
9.  [License](#license)

## 1. Overview

`nanowallet` is a Python library for interacting with the Nano cryptocurrency network. It supports:

*   **Read-only monitoring:** Check balances and history for any account.
*   **Authenticated operations:** Send funds, receive blocks, etc., using a private key derived from:
    *   A raw private key string.
    *   A standard Nano seed + account index pair (HD Wallet functionality).

It's built with `asyncio` for non-blocking network I/O and emphasizes type safety and explicit error handling via the `NanoResult` wrapper.

## 2. Installation

```bash
pip install nanowallet
```
*Requires Python 3.8+*

## 3. Core Concepts

### Asynchronous Operations

All network operations are `async` and must be `await`ed within an `async def` function.

```python
async def check_balance():
    await wallet.reload()
    result = await wallet.balance_info()
    # ...
```

### Wallet Types

*   **`NanoWalletReadOnly`**: For monitoring only. Created with an account address. Cannot sign transactions.
*   **`NanoWalletAuthenticated`**: For full read/write access. Can sign transactions. Created using factory functions:
    *   `create_wallet_from_seed(rpc, seed, index, config=None)`
    *   `create_wallet_from_private_key(rpc, private_key, config=None)`

### Error Handling: `NanoResult`

Nearly all wallet methods return a `NanoResult[T]` object to handle potential errors gracefully without raising exceptions directly.

```python
from typing import Optional, TypeVar, Generic

T = TypeVar('T')

class NanoResult(Generic[T]):
    value: Optional[T]        # The successful result value (None if error)
    error: Optional[str]      # Error message string (None if success)
    error_code: Optional[str] # Specific error code string (None if success)

    @property
    def success(self) -> bool:
        # Returns True if error is None, False otherwise
        ...

    def unwrap(self) -> T:
        # Returns value if success, otherwise raises NanoException
        ...

    def __bool__(self) -> bool:
        # Allows checking result in boolean contexts (if result: ...)
        return self.success
```

**Common Usage Patterns:**

```python
# Pattern 1: Check success explicitly
result = await wallet.balance_info()
if result.success:
    balance_info = result.value
    print(f"Balance: {balance_info.balance} Nano")
else:
    print(f"Error fetching balance: {result.error} (Code: {result.error_code})")

# Pattern 2: Use boolean context (convenient)
history_result = await wallet.account_history(count=5)
if history_result: # Checks if history_result.success is True
    history = history_result.unwrap() # Safe to unwrap here
    print(f"Found {len(history)} transactions.")
else:
    print(f"Error fetching history: {history_result.error}")

# Pattern 3: Use unwrap() directly (raises NanoException on failure)
try:
    # unwrap() returns the value on success or raises NanoException
    block_hash = (await wallet.send(...)).unwrap()
    print(f"Send successful! Hash: {block_hash}")
except NanoException as e:
    # Handle specific Nano exceptions (e.g., InsufficientBalanceError)
    print(f"Send failed: {e.message} (Code: {e.code})")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
```

### Nano Units: Raw vs. Nano

*   The network uses `raw` (smallest unit, `int`).
*   The library generally uses `Decimal` for user-facing amounts (Nano).
*   Data models often contain both `_raw` (`int`) and Nano (`Decimal`) properties.
*   Use `nano_to_raw()` and `raw_to_nano()` utilities for conversion if needed.

### RPC Client (`NanoWalletRpc`)

Handles communication with a Nano node. Instantiate it once with the node URL.

```python
from nanowallet import NanoWalletRpc

# Local node (recommended)
rpc = NanoWalletRpc(url="http://localhost:7076")

# Public node (use with caution)
# rpc = NanoWalletRpc(url="https://proxy.powernode.cc/proxy")

# Node with authentication
# rpc = NanoWalletRpc(url="http://...", username="rpc_user", password="rpc_password")
```

### Configuration (`WalletConfig`)

Customize wallet behavior by passing a `WalletConfig` object during creation.

```python
from nanowallet import WalletConfig

config = WalletConfig(
    use_work_peers=False, # Default: Generate PoW locally
    default_representative="nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6" # Default
)
```
**`WalletConfig` Attributes:**

| Attribute              | Type | Default                               | Description                                                          |
| :--------------------- | :--- | :------------------------------------ | :------------------------------------------------------------------- |
| `use_work_peers`       | bool | `False`                               | Request Proof-of-Work from network peers instead of local generation. |
| `default_representative` | str  | `nano_3msc...bw6` (Community Rep) | Representative used for new accounts or when current is unknown.       |

### Important Decorators

These are used internally but understanding them helps:

*   `@handle_errors`: Wraps the decorated `async` method's return value or exceptions into a `NanoResult`.
*   `@reload_after`: Ensures the wallet's internal state (`balance_info`, `account_info`, etc.) is automatically refreshed from the network *after* the decorated method (like `send`, `receive_all`) completes successfully.

## 4. Wallet Initialization

### RPC Client Setup
(See [RPC Client (`NanoWalletRpc`)](#rpc-client-nanowalletrpc) above)

### Read-Only Wallet Initialization

For monitoring accounts without transaction capabilities.

```python
from nanowallet import NanoWalletReadOnly, NanoWalletRpc

rpc = NanoWalletRpc(url="http://localhost:7076")
account_to_watch = "nano_3t6k35gi95xu6tergt6p69ck76ogmrs8dwzopyettafxszniqv1z61sgfga7"

# Basic initialization
readonly_wallet = NanoWalletReadOnly(rpc=rpc, account=account_to_watch)

# With custom config (rarely needed for read-only)
# readonly_wallet = NanoWalletReadOnly(rpc=rpc, account=account_to_watch, config=WalletConfig(...))

# Usage example
await readonly_wallet.reload() # Important first step
balance = await readonly_wallet.balance_info()
if balance.success:
    print(f"Balance: {balance.value.balance} NANO")
else:
    print(f"Error: {balance.error}")
```

### Authenticated Wallet (Seed + Index)

Standard method for HD wallets. **Handle seeds securely!**

```python
from nanowallet import create_wallet_from_seed, NanoWalletRpc, WalletConfig, NanoException
import os

rpc = NanoWalletRpc(url="http://localhost:7076")
seed = os.environ.get("NANO_WALLET_SEED") # Get securely from environment
if not seed: raise ValueError("Set NANO_WALLET_SEED")

index = 0 # First account derived from the seed

# Optional config
config = WalletConfig(default_representative="nano_...")

try:
    # Use the factory function
    auth_wallet = create_wallet_from_seed(
        rpc=rpc,
        seed=seed,
        index=index,
        config=config # Optional
    )
    print(f"Authenticated Wallet Account: {auth_wallet.account}")

    # Usage example
    result = await auth_wallet.send(...)
    # ... handle result

except NanoException as e:
    print(f"Initialization failed: {e.message} ({e.code})") # e.g., InvalidSeedError
```

### Authenticated Wallet (Private Key)

Use if you have the specific private key. **Handle keys securely!**

```python
from nanowallet import create_wallet_from_private_key, NanoWalletRpc, NanoException
import os

rpc = NanoWalletRpc(url="http://localhost:7076")
private_key = os.environ.get("NANO_ACCOUNT_PRIVATE_KEY") # Get securely
if not private_key: raise ValueError("Set NANO_ACCOUNT_PRIVATE_KEY")

try:
    # Use the factory function
    auth_wallet_pk = create_wallet_from_private_key(
        rpc=rpc,
        private_key=private_key
        # config=config # Also supports optional config
    )
    print(f"Authenticated Wallet Account: {auth_wallet_pk.account}")

    # Usage example
    result = await auth_wallet_pk.receive_all()
    # ... handle result

except NanoException as e:
    print(f"Initialization failed: {e.message} ({e.code})") # e.g., InvalidSeedError (for format)
```

## 5. Key Operations & API

### Method Availability by Wallet Type

| Method/Property         | `NanoWalletReadOnly` | `NanoWalletAuthenticated` (Seed/Key) | Description                                                  |
| :---------------------- | :-------------------: | :-----------------------------------: | :----------------------------------------------------------- |
| **Properties**          |                       |                                       |                                                              |
| `account`               |           X           |                   X                   | The Nano account address (`nano_...`)                        |
| `private_key`           |           -           |                   X                   | The associated private key (handle with care)                |
| `config`                |           X           |                   X                   | The `WalletConfig` instance                                  |
| **Read Operations**     |                       |                                       | (All return `NanoResult[T]`)                                 |
| `reload()`              |           X           |                   X                   | Refresh wallet state from network                            |
| `balance_info()`        |           X           |                   X                   | Get `WalletBalance` (requires reload)                        |
| `account_info()`        |           X           |                   X                   | Get `AccountInfo` (requires reload)                          |
| `has_balance()`         |           X           |                   X                   | Check if balance or receivable > 0 (requires reload)         |
| `list_receivables()`    |           X           |                   X                   | Get `List[Receivable]` pending blocks (requires reload)      |
| `account_history()`     |           X           |                   X                   | Get `List[Transaction]` history                              |
| **Write Operations**    |                       |                                       | (All return `NanoResult[T]`)                                 |
| `send()`                |           -           |                   X                   | Send Nano (amount as `Decimal`)                              |
| `send_raw()`            |           -           |                   X                   | Send Nano (amount as `int` raw)                              |
| `send_with_retry()`     |           -           |                   X                   | Send Nano (`Decimal`) with automatic RPC retry logic         |
| `send_raw_with_retry()` |           -           |                   X                   | Send Nano (`int` raw) with automatic RPC retry logic         |
| `receive_by_hash()`     |           -           |                   X                   | Receive a specific pending block, returns `ReceivedBlock`    |
| `receive_all()`         |           -           |                   X                   | Receive all pending blocks above threshold, returns `List[ReceivedBlock]` |
| `sweep()`               |           -           |                   X                   | Send *entire* confirmed balance                              |
| `refund_first_sender()` |           -           |                   X                   | Sweep funds back to the account opener/first sender          |
| `refund_receivable_by_hash()` |           -           |                   X                   | Receive a specific pending block and refund to its sender    |
| `refund_all_receivables()` |           -           |                   X                   | Receive all pending blocks and refund each to its sender      |

*Legend: X = Available, - = Not Available*

### Method Signatures & Descriptions

All `async` methods below return `NanoResult[T]` where `T` is the type hint shown.

```python
# --- Methods available on both ReadOnly and Authenticated ---
async def reload(self) -> None:
    """Fetches the latest account state (balance, receivables, etc.) from the network."""

async def balance_info(self) -> WalletBalance:
    """Gets the current confirmed and receivable balance. Requires `reload` first."""

async def account_info(self) -> AccountInfo:
    """Gets detailed account information (frontier, rep, etc.). Requires `reload` first."""

async def has_balance(self) -> bool:
    """Checks if the account has any confirmed or receivable balance > 0. Requires `reload`."""

async def list_receivables(self, threshold_raw: int = DEFAULT_THRESHOLD_RAW) -> List[Receivable]:
    """Lists pending incoming blocks above a raw threshold. Requires `reload`."""

async def account_history(self, count: Optional[int] = -1, head: Optional[str] = None) -> List[Transaction]:
    """Retrieves the transaction history for the account. count=-1 means all."""

# --- Methods available ONLY on Authenticated ---
async def send(
    self, destination_account: str, amount: Decimal | str | int,
    wait_confirmation: bool = False, timeout: int = 30
) -> str: # Returns block hash on success
    """Sends Nano (specified in standard Nano units) to a destination."""

async def send_raw(
    self, destination_account: str, amount_raw: int | str,
    wait_confirmation: bool = False, timeout: int = 30
) -> str: # Returns block hash on success
    """Sends Nano (specified in raw units) to a destination."""

async def send_with_retry(
    self, destination_account: str, amount: Decimal | str | int,
    max_retries: int = 5, retry_delay_base: float = 0.1, retry_delay_backoff: float = 1.5,
    wait_confirmation: bool = False, timeout: int = 30
) -> str: # Returns block hash on success
    """Sends Nano (standard units) with automatic retries on specific transient RPC errors."""

async def send_raw_with_retry(
    self, destination_account: str, amount_raw: int | str,
    max_retries: int = 5, retry_delay_base: float = 0.1, retry_delay_backoff: float = 1.5,
    wait_confirmation: bool = False, timeout: int = 30
) -> str: # Returns block hash on success
    """Sends Nano (raw units) with automatic retries on specific transient RPC errors."""

async def receive_by_hash(
    self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
) -> ReceivedBlock: # Returns details of the *new* receive block
    """Creates a receive block for a specific incoming send block hash."""

async def receive_all(
    self, threshold_raw: float = DEFAULT_THRESHOLD_RAW,
    wait_confirmation: bool = True, timeout: int = 30
) -> List[ReceivedBlock]: # Returns list of new receive block details
    """Receives all pending blocks above a threshold."""

async def sweep(
    self, destination_account: str, sweep_pending: bool = True,
    threshold_raw: int = DEFAULT_THRESHOLD_RAW, wait_confirmation: bool = True, timeout: int = 30
) -> str: # Returns block hash of the final send block
    """Sends the *entire* confirmed balance. Can optionally receive pending first."""

async def refund_first_sender(self, wait_confirmation: bool = False) -> str:
    """Sweeps all funds back to the account that sent the first transaction (open block source or first receivable)."""

async def refund_receivable_by_hash(
    self, receivable_hash: str, wait_confirmation: bool = False, timeout: int = 30
) -> RefundDetail: # Returns details of the refund attempt
    """Receives a specific pending block and immediately refunds the amount to the sender."""

async def refund_all_receivables(
    self, threshold_raw: Optional[int] = None, wait_confirmation: bool = False, timeout: int = 30
) -> List[RefundDetail]: # Returns list of refund details with status for each block
    """Receives all pending blocks above a threshold and immediately refunds each amount to its sender."""
```

## 6. Data Models

These `dataclass` objects represent various data structures used by the library.

```python
# Located in nanowallet.models

@dataclass
class WalletConfig:
    use_work_peers: bool
    default_representative: str

@dataclass
class WalletBalance:
    balance_raw: int = 0
    receivable_raw: int = 0
    # Properties: balance: Decimal, receivable: Decimal

@dataclass
class AccountInfo:
    account: str
    frontier_block: Optional[str] = None
    representative: Optional[str] = None
    representative_block: Optional[str] = None
    open_block: Optional[str] = None
    confirmation_height: int = 0
    block_count: int = 0
    weight_raw: int = 0
    # Property: weight: Decimal

@dataclass(frozen=True)
class Receivable:
    block_hash: str # Hash of the incoming send block
    amount_raw: int
    # Property: amount: Decimal

@dataclass(frozen=True)
class ReceivedBlock:
    block_hash: str # Hash of the NEWLY CREATED receive block
    amount_raw: int
    source: str # Sender account address
    confirmed: bool
    # Property: amount: Decimal

@dataclass(frozen=True)
class Transaction:
    block_hash: str
    type: str
    subtype: Optional[str]
    account: str # Counterparty account in send/receive
    representative: str
    previous: str
    amount_raw: int
    balance_raw: int # Balance AFTER this block
    timestamp: int # Unix timestamp (local)
    height: int
    confirmed: bool
    link: str # Block link field (public key for send, source hash for receive)
    signature: str
    work: str
    # Properties: amount: Decimal, balance: Decimal,
    #             link_as_account: str, destination: str, pairing_block_hash: str

@dataclass(frozen=True)
class AmountReceived: # Often returned by utility functions like sum_received_amount
    amount_raw: int
    # Property: amount: Decimal

@dataclass(frozen=True)
class RefundDetail:
    receivable_hash: str  # Hash of the incoming send block
    amount_raw: int       # Amount being refunded
    source_account: Optional[str]  # Sender account address
    status: RefundStatus  # Status of the refund operation
    receive_hash: Optional[str] = None  # Hash of receive block (if successful)
    refund_hash: Optional[str] = None   # Hash of refund send block (if successful)
    error_message: Optional[str] = None # Error details if unsuccessful
    # Property: amount: Decimal

class RefundStatus(Enum):
    INITIATED = "initiated"       # Refund process started
    SUCCESS = "success"           # Fully successful refund
    SKIPPED = "skipped"           # Skipped (usually self-send)
    RECEIVE_FAILED = "receive_failed"  # Failed during receive step
    SEND_FAILED = "send_failed"   # Failed during send/refund step
    UNEXPECTED_ERROR = "unexpected_error"  # Unhandled error
```

### Property Type Conversions

Many models provide convenient `Decimal` properties calculated from their `_raw` integer counterparts.

| Class           | Raw Property (`int`) | Nano Property (`Decimal`) |
| :-------------- | :------------------- | :------------------------ |
| `WalletBalance` | `balance_raw`        | `balance`                 |
| `WalletBalance` | `receivable_raw`     | `receivable`              |
| `AccountInfo`   | `weight_raw`         | `weight`                  |
| `Receivable`    | `amount_raw`         | `amount`                  |
| `ReceivedBlock` | `amount_raw`         | `amount`                  |
| `Transaction`   | `amount_raw`         | `amount`                  |
| `Transaction`   | `balance_raw`        | `balance`                 |

## 7. Examples

### Receiving All Pending Blocks

```python
from nanowallet import sum_received_amount, NanoException # Assuming wallet is initialized

async def process_pending():
    print("Checking for pending blocks...")
    try:
        # Use unwrap() to get the list or raise exception
        received_blocks = (await wallet.receive_all(
            wait_confirmation=True, # Wait for each receive block to confirm
            timeout=90 # Increase timeout if many blocks expected
        )).unwrap()

        if not received_blocks:
            print("No pending blocks found.")
            return

        # Use the utility function to sum amounts
        total_amount_info = sum_received_amount(received_blocks)
        print(f"Successfully received {len(received_blocks)} blocks.")
        print(f"Total Amount Received: {total_amount_info.amount} NANO")

        for block in received_blocks:
            print(f"- Received {block.amount} NANO from {block.source[:12]}... "
                  f"(New Block: {block.block_hash[:10]}...)")

    except NanoException as e:
        print(f"Error during receive_all: {e.message} ({e.code})")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# asyncio.run(process_pending())
```

### Sending with Retry Logic

Use `send_with_retry` or `send_raw_with_retry` to handle transient RPC errors automatically (like `Fork`, `gap previous`).

```python
from decimal import Decimal
from nanowallet import NanoException # Assuming wallet is initialized

async def reliable_send():
    destination = "nano_..."
    amount = Decimal("0.1")

    print(f"Attempting to send {amount} NANO to {destination[:12]}... with retries")
    try:
        # Use send_with_retry
        block_hash = (await wallet.send_with_retry(
            destination_account=destination,
            amount=amount,
            max_retries=3,             # Try up to 3 times after initial failure
            retry_delay_base=0.5,      # Start with 0.5s delay
            retry_delay_backoff=2.0,   # Double delay each time (0.5s, 1s, 2s)
            wait_confirmation=True,    # Wait for final confirmation
            timeout=60
        )).unwrap()
        print(f"Send successful (possibly after retries)! Hash: {block_hash}")

    except NanoException as e:
        print(f"Send failed even after retries: {e.message} ({e.code})")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# asyncio.run(reliable_send())
```

### Refunding Incoming Transactions

```python
from nanowallet import NanoException # Assuming wallet is initialized

async def refund_incoming_transactions():
    print("Starting refund operation for incoming transactions...")
    try:
        # First, check pending blocks
        await wallet.reload()
        pending_result = await wallet.list_receivables()
        
        if not pending_result:
            print("No pending blocks to refund.")
            return
            
        pending_blocks = pending_result.unwrap()
        print(f"Found {len(pending_blocks)} pending blocks to process.")
        
        # Option 1: Refund a specific block
        if pending_blocks:
            specific_hash = pending_blocks[0].block_hash
            print(f"Refunding specific block: {specific_hash[:10]}...")
            
            refund_detail = (await wallet.refund_receivable_by_hash(
                receivable_hash=specific_hash,
                wait_confirmation=True,
                timeout=60
            )).unwrap()
            
            if refund_detail.status == "success":
                print(f"Successfully refunded {refund_detail.amount} NANO to {refund_detail.source_account[:12]}...")
                print(f"Receive hash: {refund_detail.receive_hash[:10]}...")
                print(f"Refund hash: {refund_detail.refund_hash[:10]}...")
            else:
                print(f"Refund failed with status: {refund_detail.status}")
                print(f"Error: {refund_detail.error_message}")
        
        # Option 2: Refund all pending blocks
        print("Refunding all pending transactions...")
        refund_results = (await wallet.refund_all_receivables(
            threshold_raw=None,  # Use default threshold from config
            wait_confirmation=False,
            timeout=30
        )).unwrap()
        
        # Print summary statistics
        successful = sum(1 for r in refund_results if r.status == "success")
        skipped = sum(1 for r in refund_results if r.status == "skipped")
        failed = len(refund_results) - successful - skipped
        
        print(f"Refund summary: {successful} successful, {skipped} skipped, {failed} failed")
        
        # Print details for failed refunds
        if failed > 0:
            print("\nFailed refunds:")
            for result in refund_results:
                if result.status not in ("success", "skipped"):
                    print(f"- Block {result.receivable_hash[:10]}...: {result.status}")
                    print(f"  Error: {result.error_message}")

    except NanoException as e:
        print(f"Error during refund operation: {e.message} ({e.code})")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# asyncio.run(refund_incoming_transactions())
```

## 8. Best Practices

1.  **Error Handling**: Always check `NanoResult.success` or use `.unwrap()` within a `try...except NanoException` block to handle potential failures.
2.  **Seed/Key Security**: **Never** hardcode seeds or private keys in your source code. Use environment variables, configuration files with proper permissions, or dedicated secrets management systems.
3.  **RPC Security**: When connecting to remote Nano nodes, prefer HTTPS URLs. If the node requires authentication, provide the username and password to `NanoWalletRpc`. Do not expose RPC credentials publicly.
4.  **State Reloading**: While `@reload_after` handles state updates after write operations, call `await wallet.reload()` explicitly before performing actions based on balance or account state if there might have been external changes.
5.  **Configuration**: Choose a reliable `default_representative` you trust. Consider `use_work_peers=True` if local PoW generation is too slow or resource-intensive, but be aware it relies on external peers.

## 9. License

This project is licensed under the MIT License. See the `LICENSE` file in the repository for details.

