# Nano Wallet Library

A Python implementation of a Nano cryptocurrency wallet supporting read-only monitoring, key-based operations, and seed-based HD wallets. This library provides full transaction capabilities including sending, receiving, and sweeping funds.

## Features

- Multiple wallet types for different use cases:
  - Read-only wallet for monitoring accounts
  - Key-based wallet for full transaction capabilities
  - Seed-based HD wallet for deterministic wallet generation
- Comprehensive transaction support (send, receive, sweep)
- Safe error handling with NanoResult wrapper
- Automatic wallet state reloading
- Support for work peers for PoW generation
- Configurable default representatives

## Installation

```bash
pip install nanowallet
```

## Wallet Types

### 1. Read-Only Wallet
```python
from nanowallet import NanoWalletReadOnly, NanoWalletRpc

rpc = NanoWalletRpc(url="http://localhost:7076")
readonly_wallet = NanoWalletReadOnly(
    rpc=rpc,
    account="nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
)

# Usage example
balance = await readonly_wallet.balance_info()
if balance.success:
    print(f"Balance: {balance.value.balance} NANO")
```

### 2. Key-Based Wallet
```python
from nanowallet import NanoWalletKey, NanoWalletRpc

rpc = NanoWalletRpc(url="http://localhost:7076")
key_wallet = NanoWalletKey(
    rpc=rpc,
    private_key="1234567890ABCDEF..." # 64 character hex string
)

# Send transaction example
result = await key_wallet.send(
    destination_account="nano_1abc...",
    amount=Decimal("1.5")
)
```

### 3. Seed-Based Wallet (HD Wallet)
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
```

## Error Handling

All methods return a `NanoResult[T]` wrapper for safe error handling:

```python
# Safe pattern with success check
result = await wallet.send(destination="nano_1abc...", amount="1.5")
if result.success:
    print(f"Success: {result.value}")
else:
    print(f"Error: {result.error} ({result.error_code})")

# Alternative pattern using unwrap()
try:
    block_hash = (await wallet.send(
        destination_account="nano_1abc...",
        amount="2.5"
    )).unwrap()
    print(f"Sent! Block hash: {block_hash}")
except NanoException as e:
    print(f"Error: {e.message} ({e.code})")
```

## Available Methods

### Read Operations
- `account_history()`: List of historical transactions
- `has_balance()`: Check if account has available balance
- `balance_info()`: Current and pending balance information
- `account_info()`: Detailed account metadata
- `list_receivables()`: List of pending incoming transactions

### Transaction Operations
- `send()`: Send NANO to a destination account
- `send_raw()`: Send raw amount of NANO
- `sweep()`: Send all available funds to destination
- `receive_by_hash()`: Receive specific pending block
- `receive_all()`: Receive all pending transactions
- `refund_first_sender()`: Return funds to original sender

## Best Practices

1. **Secure Configuration**
```python
config = WalletConfig(
    use_work_peers=True,  # For faster PoW
    default_representative="nano_3..."  # Trusted representative
)
```

2. **Seed Security**
```python
# Use environment variables for sensitive data
import os
seed = os.environ.get("NANO_WALLET_SEED")
if not seed:
    raise ValueError("Missing NANO_WALLET_SEED environment variable")
```

3. **RPC Security**
```python
rpc = NanoWalletRpc(
    url="https://secure-node.example.com:7076",
    username="user",
    password="pass"
)
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or create an issue for any bugs or feature requests.

## License

This project is licensed under an open-source license that allows free use and modification for both commercial and private use. For more details, please see the LICENSE file in the repository.