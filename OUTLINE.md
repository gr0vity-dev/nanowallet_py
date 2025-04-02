# Nano Wallet Library Documentation

## 1. Introduction

*   **What is `nanowallet`?**
    *   Overview of the library's purpose.
    *   Target audience (Python developers interacting with Nano).
*   **Core Philosophy**
    *   Asynchronous by default (`asyncio`).
    *   Type safety and static analysis support.
    *   Robust error handling (`NanoResult`).
    *   Focus on ease of use for common Nano operations.
*   **Features**
    *   (Expand on README list) Read-only, Key-based, Seed-based wallets.
    *   Send, Receive (all/specific), Sweep, History, Account Info.
    *   Automatic state reloading for sequential operations.
    *   Configuration (RPC, Work Peers, Representative).

## 2. Getting Started

*   **Installation**
    *   `pip install nanowallet`
    *   Mention requirements (Python version, dependencies if any beyond stdlib + direct deps).
*   **Connecting to a Nano Node**
    *   Explaining the need for an RPC endpoint.
    *   Using `NanoWalletRpc`.
    *   Connecting to local vs. public nodes.
    *   Authentication (`username`, `password`).
    *   Security considerations (HTTPS).
    ```python
    from nanowallet import NanoWalletRpc

    # Local unsecured node
    rpc = NanoWalletRpc(url="http://localhost:7076")

    # Public node with HTTPS (recommended for remote)
    # rpc = NanoWalletRpc(url="https://your-trusted-node.com")

    # Node with authentication
    # rpc = NanoWalletRpc(url="https://secure-node.com", username="user", password="pass")
    ```
*   **Creating Your First Wallet**
    *   Focus on `NanoWallet` (seed-based) as the most common starting point.
    *   Explain seeds (64-char hex) and indices (account derivation).
    *   **CRITICAL:** Emphasize seed security. Show retrieving from environment variables.
    ```python
    import os
    from nanowallet import NanoWallet, WalletConfig

    wallet_seed = os.environ.get("NANO_WALLET_SEED")
    if not wallet_seed:
        raise ValueError("NANO_WALLET_SEED environment variable not set!")

    # Minimal setup
    wallet = NanoWallet(rpc=rpc, seed=wallet_seed, index=0)

    # With optional configuration
    # config = WalletConfig(default_representative="nano_...")
    # wallet_with_config = NanoWallet(rpc=rpc, seed=wallet_seed, index=0, config=config)

    print(f"Wallet Account: {wallet.account}")
    print(f"Wallet Index: {wallet.index}")
    ```
*   **Basic Operations: Check Balance & Receive**
    *   Demonstrate `balance_info()` and `receive_all()`.
    *   Introduce `async`/`await`.
    *   Introduce `NanoResult` and the two handling patterns (`.success` check vs `.unwrap()` with `try/except`).
    *   (Include a runnable example similar to the Quick Start in the README).

## 3. Core Concepts

*   **Wallet Types**
    *   `NanoWalletReadOnly`: Purpose (monitoring, checking balances/history without risk), initialization.
    *   `NanoWalletKey`: Purpose (controlling a single account with its private key), initialization.
    *   `NanoWallet` (Seed-Based): Purpose (HD Wallet, generating multiple accounts from one seed), initialization, seed/index relationship.
    *   Inheritance relationship (`ReadOnly` -> `Key` -> `Seed`).
    *   (Include the "Features Comparison" table from your draft).
*   **Asynchronous Operations**
    *   Why async? (Network I/O benefits).
    *   Basic usage (`async def`, `await`).
    *   Running the main function (`asyncio.run()`).
*   **Error Handling: `NanoResult` and `NanoException`**
    *   Deep dive into the `NanoResult[T]` generic class (fields: `value`, `error`, `error_code`, property: `success`).
    *   The `.unwrap()` method and the `NanoException` it raises.
    *   Benefits: No hidden exceptions, forces explicit handling.
    *   Common Error Codes (`INSUFFICIENT_BALANCE`, `INVALID_ACCOUNT`, `BLOCK_NOT_FOUND`, `RPC_ERROR`, `TIMEOUT`, etc.). Reference `errors.py`.
    *   Show both handling patterns again with clear explanations.
*   **State Management: `reload()` and `@reload_after`**
    *   Explain Nano's block lattice and the requirement for sequential blocks *per account* (frontier/previous block, balance).
    *   Explain how creating blocks out of order causes forks.
    *   Introduce `@reload_after`: Automatically calls `reload()` after successful state-changing operations (`send`, `receive_all`, etc.) to fetch the latest frontier and balance, ensuring the *next* operation on that account uses the correct state.
    *   Explain the explicit `reload()` method for manual state refresh.
    *   *(Self-correction based on previous discussion):* Clarify the behavior if the decorated method *fails* (Does reload run? Recommended: No).
*   **Nano Units: Raw vs. Nano**
    *   Define the relationship (1 Nano = 10^30 Raw).
    *   Explain why operations often use raw internally.
    *   Point out model properties (`.balance`, `.amount`) for easy conversion to Nano (Decimal).
    *   Reference `utils.conversion` functions (`nano_to_raw`, `raw_to_nano`) for manual conversion.
*   **Configuration (`WalletConfig`)**
    *   `use_work_peers`: Explain PoW and how peers *might* help (or rely on the node).
    *   `default_representative`: Importance of choosing a representative, when this default is used (e.g., opening an account).
*   **Work Generation**
    *   Briefly explain Proof of Work in Nano.
    *   How the library handles it (via RPC `work_generate`).
    *   Role of `use_work_peers`. (Mention potential future local PoW if planned).

## 4. API Reference

*   **(Structure this using automated tools like Sphinx autodoc if possible, otherwise manually)**
*   **`nanowallet.rpc.NanoWalletRpc`**
    *   `__init__(url, username, password)`
    *   Methods (`account_info`, `blocks_info`, `work_generate`, `process`, `receivable`, `account_history`) - Detail parameters and return raw dictionary structure (mentioning `try_raise_error` is used internally by wallet classes).
*   **`nanowallet.wallets.NanoWalletReadOnly`**
    *   `__init__(rpc, account, config)`
    *   Properties: `account`
    *   Methods: `account_history`, `has_balance`, `balance_info`, `account_info`, `list_receivables`, `reload`. (Detail params, explain `NanoResult[T]` return).
*   **`nanowallet.wallets.NanoWalletKey`**
    *   Inherits from `NanoWalletReadOnly`.
    *   `__init__(rpc, private_key, config)`
    *   Properties: `private_key`
    *   Methods: `send`, `send_raw`, `sweep`, `receive_by_hash`, `receive_all`, `refund_first_sender`. (Detail params, explain `NanoResult[T]` return).
*   **`nanowallet.wallets.NanoWallet`**
    *   Inherits from `NanoWalletKey`.
    *   `__init__(rpc, seed, index, config)`
    *   Properties: `seed`, `index`.
*   **`nanowallet.models`**
    *   Detail each `@dataclass`: `WalletConfig`, `WalletBalance`, `AccountInfo`, `Receivable`, `ReceivedBlock`, `Transaction`. List fields and properties (explaining `_raw` vs. `Decimal` properties).
*   **`nanowallet.errors`**
    *   List custom exceptions: `NanoException`, `RpcError`, `InvalidSeedError`, etc. Explain base `NanoException` structure (`message`, `code`).
*   **`nanowallet.utils`**
    *   `conversion`: `nano_to_raw`, `raw_to_nano`.
    *   `validation`: `validate_nano_amount`, `validate_account`.
    *   `amount_operations`: `sum_received_amount`.
    *   `decorators`: `NanoResult`, `handle_errors`, `reload_after` (explain their purpose).

## 5. Examples

*   **Handling Multiple Accounts (from Seed)**
    ```python
    wallets = [NanoWallet(rpc=rpc, seed=wallet_seed, index=i) for i in range(3)]
    for i, wallet in enumerate(wallets):
        print(f"Wallet {i}: {wallet.account}")
        # ... perform operations on each wallet
    ```
*   **Receiving Blocks Above a Threshold**
    ```python
    # Receive only amounts >= 0.01 NANO
    threshold = nano_to_raw("0.01")
    receivables_result = await wallet.list_receivables(threshold_raw=threshold)
    if receivables_result.success:
        for receivable in receivables_result.value:
            print(f"Found receivable block {receivable.block_hash} for {receivable.amount} NANO")
            # Optionally call receive_by_hash here
            receive_op = await wallet.receive_by_hash(receivable.block_hash)
            # ... handle receive_op result
    ```
*   **Checking Transaction History**
    ```python
    history_result = await wallet.account_history(count=10) # Get last 10
    if history_result.success:
        for tx in history_result.value:
            if tx.subtype == 'send':
                print(f"Sent {tx.amount} NANO to {tx.destination} (Hash: {tx.block_hash})")
            elif tx.subtype == 'receive':
                 print(f"Received {tx.amount} NANO from {tx.account} (Hash: {tx.block_hash})") # tx.account is the sender in history context for receive
            # ... handle other types/subtypes
    ```
*   **Sweeping an Account**
    ```python
    sweep_destination = "nano_..."
    sweep_result = await wallet.sweep(destination_account=sweep_destination)
    if sweep_result.success:
        print(f"Swept funds to {sweep_destination}. Send block: {sweep_result.value}")
    else:
        print(f"Sweep failed: {sweep_result.error}")
    ```
*   **Using `NanoResult` Patterns**
    *   Show side-by-side examples of the `.success` check vs. `try/except .unwrap()`.

## 6. Best Practices

*   **Security**
    *   **Seed/Key Management:** NEVER hardcode seeds/keys. Use environment variables, secrets managers (like HashiCorp Vault, AWS Secrets Manager), or secure configuration files with appropriate permissions.
    *   **RPC Security:** Always prefer HTTPS for remote nodes. Use authentication if provided by the node operator. Be cautious connecting to untrusted public nodes. Consider running your own node.
*   **Configuration**
    *   **Representative Choice:** Choose a reliable, high-uptime representative. Research options on sites like My Nano Ninja or NanoLooker. Understand the implications of your choice for network decentralization and performance. Update it if your chosen one goes offline.
    *   **Work Generation:** Test performance with `use_work_peers=True` vs `False` if using a public node. Relying on the node (`False`) might be simpler but potentially slower.
*   **Error Handling**
    *   Always check the outcome of wallet operations using `NanoResult`. Don't assume success.
    *   Log errors appropriately, including `error_code` for easier debugging.
    *   Implement retries with backoff for potentially transient network/RPC errors if needed for your application's robustness.
*   **Asynchronous Code**
    *   Understand how `asyncio` works if building larger applications (event loop, running tasks).
    *   Avoid blocking calls within your async code.
*   **Resource Management**
    *   Consider managing the `NanoWalletRpc` client lifecycle if your application runs continuously (though typically it's lightweight).
