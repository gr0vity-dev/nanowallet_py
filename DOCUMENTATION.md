# NanoWallet Library Documentation

This documentation provides a detailed reference of the NanoWallet library's capabilities, methods, and error handling.

## Table of Contents
- [Core Classes](#core-classes)
- [Error Handling](#error-handling)
- [Utility Functions](#utility-functions)
- [Method Reference](#method-reference)

## Core Classes

### NanoWallet
The main class for interacting with Nano accounts.

#### Constructor
```python
wallet = NanoWallet(rpc: NanoRpcTyped, seed: str, index: int, config: Optional[WalletConfig] = None)
```
- `rpc`: NanoRpcTyped instance for node communication
- `seed`: 64-character hex string
- `index`: Account index (0 to 2^32-1)
- `config`: Optional WalletConfig instance

### WalletConfig
Configuration class for NanoWallet.

```python
config = WalletConfig(
    use_work_peers: bool = True,
    default_representative: str = "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
)
```

## Method Reference

### Account Management

#### reload()
```python
async def reload() -> NanoResult
```
Reloads account information including balance, pending blocks, and account details.

#### balance_info()
```python
async def balance_info() -> NanoResult[dict]
```
Returns detailed balance information:
```python
{
    "balance": float,  # Balance in NANO
    "balance_raw": int,  # Balance in raw
    "receivable_balance": float,  # Pending balance in NANO
    "receivable_balance_raw": int  # Pending balance in raw
}
```

#### has_balance()
```python
async def has_balance() -> NanoResult[bool]
```
Checks if account has any available or receivable balance.

### Transaction Operations

#### send()
```python
async def send(destination_account: str, amount: float) -> NanoResult[str]
```
Sends NANO to a destination account.
- `destination_account`: Recipient's account address
- `amount`: Amount in NANO
- Returns: Block hash of the send transaction

#### send_raw()
```python
async def send_raw(destination_account: str, amount_raw: int) -> NanoResult[str]
```
Sends raw amount to a destination account.
- `amount_raw`: Amount in raw units

#### sweep()
```python
async def sweep(
    destination_account: str, 
    sweep_pending: bool = True, 
    threshold_raw: int = DEFAULT_THRESHOLD
) -> NanoResult[str]
```
Transfers all funds to destination account.
- `sweep_pending`: Whether to receive pending blocks first
- `threshold_raw`: Minimum amount to receive

### Receiving Operations

#### receive_all()
```python
async def receive_all(threshold_raw: float = None) -> NanoResult[list]
```
Receives all pending blocks.
- Returns: List of received block information

#### receive_by_hash()
```python
async def receive_by_hash(block_hash: str) -> NanoResult[dict]
```
Receives a specific pending block.
Returns:
```python
{
    'hash': str,  # Received block hash
    'amount_raw': int,  # Amount in raw
    'amount': float,  # Amount in NANO
    'source': str  # Sender's account
}
```

#### list_receivables()
```python
async def list_receivables(threshold_raw: int = DEFAULT_THRESHOLD) -> NanoResult[List[tuple]]
```
Lists pending blocks sorted by amount.
- Returns: List of (block_hash, amount) tuples

### Special Operations

#### refund_first_sender()
```python
async def refund_first_sender() -> NanoResult[str]
```
Returns all funds to the original sender.
- Returns: Block hash of the refund transaction

## Error Handling

### NanoResult
All methods return a `NanoResult` object with the following properties:
- `success`: Boolean indicating success/failure
- `value`: The return value if successful
- `error`: Error message if failed
- `error_code`: Error code if failed

### Common Exceptions
- `InvalidAccountError`: Invalid account address
- `InsufficientBalanceError`: Insufficient funds
- `BlockNotFoundError`: Block hash not found
- `InvalidSeedError`: Invalid seed format
- `InvalidIndexError`: Invalid account index

## Utility Functions

### WalletUtils
Static utility methods for common conversions:

```python
WalletUtils.raw_to_nano(amount_raw: int) -> float
WalletUtils.nano_to_raw(amount_nano: float) -> int
WalletUtils.sum_received_amount(receive_all_response: List[dict]) -> dict
```

### Conversion Functions
```python
raw_to_nano(raw_amount: int) -> float
nano_to_raw(amount_nano: float) -> int
```

## Usage Example

```python
from nanowallet import NanoWallet, WalletConfig
from nanorpc.client import NanoRpcTyped

async def main():
    rpc = NanoRpcTyped(url='http://localhost:7076')
    config = WalletConfig(use_work_peers=True)
    wallet = NanoWallet(rpc, "your_seed", 0, config)
    
    # Check balance
    balance = await wallet.balance_info()
    if balance.success:
        print(f"Balance: {balance.value['balance']} NANO")
    
    # Send transaction
    result = await wallet.send("nano_dest...", 1.0)
    if result.success:
        print(f"Sent! Block hash: {result.value}")
    else:
        print(f"Error: {result.error}")

```

## Best Practices

1. Always check the `success` property of `NanoResult` before accessing `value`
2. Use `unwrap()` to automatically raise exceptions on errors
3. Handle exceptions appropriately in production code
4. Use raw amounts for precise calculations
5. Always await wallet operations as they are asynchronous

## Error Codes and Messages

Common error messages you might encounter:
- "Account not found"
- "Insufficient balance"
- "Block not found"
- "Invalid account ID"
- "Invalid seed format"
- "Invalid index"

## Performance Considerations

1. Use `send_raw` instead of `send` for high-precision operations
2. Batch receive operations when possible
3. Consider using thresholds for receiving to skip dust amounts
4. Cache account information when appropriate

</rewritten_file> 