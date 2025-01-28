# Nano Wallet Documentation

## Overview
A Python implementation of a Nano cryptocurrency wallet supporting read-only monitoring, key-based operations, and seed-based HD wallets. Provides full transaction capabilities including sending, receiving, and sweeping funds.

# Nano Wallet Data Models Overview

## Error Handling with NanoResult

All methods in the Nano wallet return a `NanoResult[T]` wrapper that provides safe error handling without raising exceptions. This is a crucial implementation detail.

```python
class NanoResult[T]:
    value: Optional[T]        # The successful result value
    error: Optional[str]      # Error message if failed
    error_code: Optional[str] # Error code if failed
    
    # Properties
    success: bool            # True if no error occurred
    
    # Methods
    unwrap() -> T           # Returns value or raises NanoException
```

### Usage Patterns

```python
# Safe pattern - Check success
result = await wallet.send(...)
if result.success:
    print(f"Success: {result.value}")
else:
    print(f"Error: {result.error} ({result.error_code})")

# Python-style pattern - Using unwrap()
try:
    block_hash = (await wallet.send(...)).unwrap()
    print(f"Sent with hash: {block_hash}")
except NanoException as e:
    print(f"Failed: {e.message} ({e.code})")
```

## Method Return Types

Note: All methods are wrapped in `NanoResult[T]` where T is the specified return type.

| Method | Return Type | Actual Return | Description |
|--------|-------------|---------------|-------------|
| `account_history()` | `List[Transaction]` | `NanoResult[List[Transaction]]` | List of historical transactions |
| `has_balance()` | `bool` | `NanoResult[bool]` | Whether account has available balance |
| `balance_info()` | `WalletBalance` | `NanoResult[WalletBalance]` | Current and pending balance information |
| `account_info()` | `AccountInfo` | `NanoResult[AccountInfo]` | Detailed account metadata |
| `list_receivables()` | `List[Receivable]` | `NanoResult[List[Receivable]]` | List of pending incoming transactions |
| `send()` | `str` | `NanoResult[str]` | Block hash of sent transaction |
| `send_raw()` | `str` | `NanoResult[str]` | Block hash of sent transaction |
| `receive()` | `str` | `NanoResult[str]` | Block hash of received transaction |
| `sweep()` | `str` | `NanoResult[str]` | Block hash of sweep transaction |
| `receive_by_hash()` | `ReceivedBlock` | `NanoResult[ReceivedBlock]` | Details of received transaction |
| `receive_all()` | `List[ReceivedBlock]` | `NanoResult[List[ReceivedBlock]]` | List of received transactions |
| `refund_first_sender()` | `str` | `NanoResult[str]` | Block hash of refund transaction |

## Data Models

### WalletConfig
Configuration settings for the Nano wallet.
```python
@dataclass
class WalletConfig:
    use_work_peers: bool                # Use work peers for PoW generation
    default_representative: str         # Default representative account
```

### WalletBalance
Represents wallet balance information.
```python
@dataclass
class WalletBalance:
    balance_raw: int                    # Current balance in raw units
    receivable_raw: int                # Pending balance in raw units
    
    Properties:
    - balance: Decimal                 # Current balance in Nano
    - receivable: Decimal             # Pending balance in Nano
```

### AccountInfo
Detailed information about a Nano account.
```python
@dataclass
class AccountInfo:
    frontier_block: Optional[str]       # Latest block hash
    representative: Optional[str]       # Current representative
    representative_block: Optional[str] # Representative block hash
    open_block: Optional[str]          # First block hash
    confirmation_height: int           # Confirmed block height
    block_count: int                   # Total block count
    weight_raw: int                    # Voting weight in raw
    
    Properties:
    - weight: Decimal                  # Voting weight in Nano
```

### Receivable
Represents a pending incoming transaction.
```python
@dataclass(frozen=True)
class Receivable:
    block_hash: str                    # Hash of pending block
    amount_raw: int                    # Amount in raw units
    
    Properties:
    - amount: Decimal                  # Amount in Nano
```

### ReceivedBlock
Represents a completed receive operation.
```python
@dataclass(frozen=True)
class ReceivedBlock:
    block_hash: str                    # Hash of received block
    amount_raw: int                    # Amount in raw units
    source: str                        # Source account
    confirmed: bool                    # Confirmation status
    
    Properties:
    - amount: Decimal                  # Amount in Nano
```

### Transaction
Represents a confirmed transaction in account history.
```python
@dataclass(frozen=True)
class Transaction:
    block_hash: str                    # Block hash
    type: str                          # Block type (state, send, etc.)
    subtype: Optional[str]             # Block subtype
    account: str                       # Counterparty account
    representative: str                # Representative account
    previous: str                      # Previous block hash
    amount_raw: int                    # Amount in raw units
    balance_raw: int                   # Balance in raw units
    timestamp: int                     # Unix timestamp
    height: int                        # Block height
    confirmed: bool                    # Confirmation status
    link: str                          # Transaction link/recipient
    signature: str                     # Block signature
    work: str                          # Proof of work
    
    Properties:
    - amount: Decimal                  # Amount in Nano
    - balance: Decimal                # Balance in Nano
    - link_as_account: str            # Recipient account address
    - destination: str                # Recipient (send only)
    - pairing_block_hash: str         # Source block hash (receive only)
```

## Important Decorators

### @handle_errors
Wraps method responses in `NanoResult` for safe error handling:
```python
@handle_errors
async def some_method() -> str:  # Actually returns NanoResult[str]
```

### @reload_after
Reloads wallet state after method execution:
```python
@reload_after
async def some_method() -> str:  # Reloads wallet after completion
```

## Property Type Conversions

| Class | Raw Property | Nano Property |
|-------|--------------|---------------|
| `WalletBalance` | `balance_raw: int` | `balance: Decimal` |
| `WalletBalance` | `receivable_raw: int` | `receivable: Decimal` |
| `AccountInfo` | `weight_raw: int` | `weight: Decimal` |
| `Receivable` | `amount_raw: int` | `amount: Decimal` |
| `ReceivedBlock` | `amount_raw: int` | `amount: Decimal` |
| `Transaction` | `amount_raw: int` | `amount: Decimal` |
| `Transaction` | `balance_raw: int` | `balance: Decimal` |

Note: All raw to Nano conversions use the `_raw_to_nano()` utility function for consistent decimal precision handling.

**Key Methods:**

# Nano Wallet Features Comparison

## Method Availability Across Wallet Types

| Method/Property | ReadOnly Wallet | Key-Based Wallet | Seed-Based Wallet (NanoWallet) |
|----------------|-----------------|------------------|-------------------------------|
| **Properties** |
| `account` | X | X | X |
| `private_key` | - | X | X |
| **Read Operations** |
| `account_history()` | X | X | X |
| `has_balance()` | X | X | X |
| `balance_info()` | X | X | X |
| `account_info()` | X | X | X |
| `list_receivables()` | X | X | X |
| `reload()` | X | X | X |
| **Transaction Operations** |
| `send()` | - | X | X |
| `send_raw()` | - | X | X |
| `sweep()` | - | X | X |
| `receive_by_hash()` | - | X | X |
| `receive_all()` | - | X | X |
| `refund_first_sender()` | - | X | X |

## Notes:
- ReadOnly Wallet: Limited to query operations only
- Key-Based Wallet: Inherits all ReadOnly features + adds transaction capabilities
- Seed-Based Wallet: Inherits all Key-Based features + adds HD wallet functionality

## Legend:
- X: Feature available
- -: Feature not available

Method signatures:
```python
    async def account_history(
        self, count: Optional[int] = -1, head: Optional[str] = None
    ) -> List[Transaction]:
        """Get block history for the wallet's account"""

    async def has_balance(self) -> bool:
        """Check if account has available balance"""

    async def balance_info(self) -> WalletBalance:
        """Get detailed balance information"""

    async def account_info(self) -> AccountInfo:
        """Get detailed account information"""

    async def list_receivables(
        self, threshold_raw: int = DEFAULT_THRESHOLD_RAW
    ) -> List[Receivable]:
        """List receivable blocks"""

    async def reload(self):
        """Reload account information"""

    async def send(self, destination_account: str, amount: Decimal | str | int) -> str:
        """Sends Nano to a destination account"""

    async def send_raw(self, destination_account: str, amount: int) -> str:
        """Sends Nano to a destination account"""

    async def sweep(
        self,
        destination_account: str,
        sweep_pending: bool = True,
        threshold_raw: int = DEFAULT_THRESHOLD_RAW,
    ) -> str:
        """Transfers all funds from the current account to the destination account"""

    async def receive_by_hash(
        self, block_hash: str, wait_confirmation: bool = True, timeout: int = 30
    ) -> ReceivedBlock:
        """Receives a specific block by its hash"""

    async def receive_all(
        self,
        threshold_raw: float = DEFAULT_THRESHOLD_RAW,
        wait_confirmation: bool = True,
        timeout: int = 30,
    ) -> List[ReceivedBlock]:
        """Receives all pending receivable blocks"""

    async def refund_first_sender(self) -> str:
        """Sends remaining funds to the account opener"""    

```



# Nano Wallet Initialization Examples

## Common Components

### RPC Client Setup
```python
# Basic RPC initialization
rpc = NanoWalletRpc(url="http://localhost:7076")

# RPC with authentication
rpc = NanoWalletRpc(
    url="https://mynanonode.com:7076",
    username="user",
    password="pass"
)

# Optional: Custom wallet configuration
config = WalletConfig(
    use_work_peers=True,
    default_representative="nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
)
```

## Wallet Type Examples

### 1. Read-Only Wallet
For monitoring accounts without transaction capabilities.

```python
# Basic initialization
readonly_wallet = NanoWalletReadOnly(
    rpc=rpc,
    account="nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
)

# With custom config
readonly_wallet = NanoWalletReadOnly(
    rpc=rpc,
    account="nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6",
    config=WalletConfig(use_work_peers=True)
)

# Usage example
balance = await readonly_wallet.balance_info()
if balance.success:
    print(f"Balance: {balance.value.balance} NANO")
else:
    print(f"Error: {balance.error}")
```

### 2. Key-Based Wallet
For full transaction capabilities using a private key.

```python
# Basic initialization
key_wallet = NanoWalletKey(
    rpc=rpc,
    private_key="1234567890ABCDEF..." # 64 character hex string
)

# With custom config
key_wallet = NanoWalletKey(
    rpc=rpc,
    private_key="1234567890ABCDEF...",
    config=WalletConfig(
        use_work_peers=True,
        default_representative="nano_3abc..."
    )
)

# Usage example
result = await key_wallet.send(
    destination_account="nano_1abc...",
    amount=Decimal("1.5")
)
if result.success:
    print(f"Sent! Block hash: {result.value}")
else:
    print(f"Error: {result.error}")
```

### 3. Seed-Based Wallet (HD Wallet)
For deterministic wallet generation using a seed phrase.

```python
# Basic initialization
seed_wallet = NanoWallet(
    rpc=rpc,
    seed="0000000000000000000000000000000000000000000000000000000000000000",  # 64 character hex
    index=0  # First wallet from seed
)

# With custom config and different index
seed_wallet = NanoWallet(
    rpc=rpc,
    seed="0000000000000000000000000000000000000000000000000000000000000000",
    index=5,  # Generate 6th wallet from seed
    config=WalletConfig(use_work_peers=True)
)

# Multiple wallets from same seed
wallets = [
    NanoWallet(rpc=rpc, seed="000...000", index=i)
    for i in range(5)
]

# Usage example
try:
    block_hash = (await seed_wallet.send(
        destination_account="nano_1abc...",
        amount="2.5"
    )).unwrap()
    print(f"Sent! Block hash: {block_hash}")
except NanoException as e:
    print(f"Error: {e.message} ({e.code})")
```


```python
from nanowallet import NanoWallet, WalletConfig, NanoWalletRpc, sum_received_amount

rpc = NanoWalletRpc(url="http://localhost:7076")
wallet = NanoWallet(
    rpc=rpc,
    seed="0000000000000000000000000000000000000000000000000000000000000000",
    index=0,  # First wallet from seed
    config=WalletConfig(
        use_work_peers=True,
        default_representative="nano_3abc..."
    )
)

# Receive all pending transactions
result = await wallet.receive_all()
if result.success:
    received_blocks = result.value

    received_sum = sum_received_amount(received_blocks)
    print(received_sum.amount)
    
    for block in received_blocks:
        print(f"Received {block.amount} NANO from {block.source}")
        print(f"Block hash: {block.block_hash}")
        print(f"Confirmed: {block.confirmed}")
else:
    print(f"Error receiving blocks: {result.error}")

# Alternative using unwrap
try:
    received_blocks = (await wallet.receive_all()).unwrap()
    total_received = sum(block.amount for block in received_blocks)
    print(f"Successfully received {total_received} NANO across {len(received_blocks)} blocks")
except NanoException as e:
    print(f"Failed to receive blocks: {e.message} ({e.code})")


## Best Practices

1. **Error Handling**: Always check `NanoResult.success` or use `.unwrap()` in a try-catch block
   ```python
   # Safe pattern
   result = await wallet.send(...)
   if result.success:
       print(f"Success: {result.value}")
   
   # Unwrap pattern
   try:
       hash = (await wallet.send(...)).unwrap()
       print(f"Success: {hash}")
   except NanoException as e:
       print(f"Error: {e.message}")
   ```

2. **Configuration**: Set appropriate `default_representative` and `use_work_peers` based on needs
   ```python
   config = WalletConfig(
       use_work_peers=True,  # For faster PoW
       default_representative="nano_3..."  # Trusted representative
   )
   ```

3. **Seed Security**: Never hardcode seeds or private keys
   ```python
   # BAD
   seed = "0000000000000000000000000000000000000000000000000000000000000000"
   
   # GOOD
   seed = os.environ.get("NANO_WALLET_SEED")
   if not seed:
       raise ValueError("Missing NANO_WALLET_SEED environment variable")
   ```

4. **RPC Security**: Use HTTPS and authentication when connecting to remote nodes
   ```python
   rpc = NanoWalletRpc(
       url="https://secure-node.example.com:7076",
       username="user",
       password="pass"
   )
   ```


