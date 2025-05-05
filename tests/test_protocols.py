#!/usr/bin/env python3
"""
Pytest test file for the nanowallet protocol implementations.
"""
import os
import pytest
import pytest_asyncio
import asyncio
from decimal import Decimal

from nanowallet.wallets.wallet_factory import create_wallet_from_seed
from nanowallet import (
    IReadOnlyWallet,
    IAuthenticatedWallet,
    NanoWalletReadOnly,
    NanoWalletAuthenticated,
    create_wallet_from_seed,
    NanoWalletRpc,
)

# Test configuration
RPC_URL = os.environ.get("NANO_RPC_URL", "http://localhost:7076")
TEST_SEED = os.environ.get(
    "NANO_TEST_SEED", "8D55678AD4CD3C2182AA5395800F89AAA4266098F88F0731865576D4C37252EC"
)
TEST_INDEX = int(os.environ.get("NANO_TEST_INDEX", "0"))


@pytest_asyncio.fixture
async def rpc_client():
    """Create a RPC client to use in tests."""
    rpc = NanoWalletRpc(url=RPC_URL)
    return rpc


@pytest_asyncio.fixture
async def account_address(rpc_client):
    """Get a test account address derived from the seed."""
    wallet = create_wallet_from_seed(rpc=rpc_client, seed=TEST_SEED, index=TEST_INDEX)
    return wallet.account


@pytest_asyncio.fixture
async def read_only_wallet(rpc_client, account_address):
    """Create a read-only wallet for testing."""
    wallet = NanoWalletReadOnly(rpc=rpc_client, account=account_address)
    return wallet


@pytest_asyncio.fixture
async def authenticated_wallet(rpc_client):
    """Create an authenticated wallet for testing."""
    wallet = create_wallet_from_seed(rpc=rpc_client, seed=TEST_SEED, index=TEST_INDEX)
    return wallet


class TestReadOnlyWallet:
    """Tests for the IReadOnlyWallet implementation."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reload_readonly(self, read_only_wallet):
        """Test reload functionality."""
        result = await read_only_wallet.reload()
        assert result.success

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_account_info(self, read_only_wallet):
        """Test account info retrieval."""
        result = await read_only_wallet.account_info()
        assert result.success
        info = result.unwrap()
        assert info.account is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_balance_info(self, read_only_wallet):
        """Test balance info retrieval."""
        result = await read_only_wallet.balance_info()
        assert result.success
        balance = result.unwrap()
        assert isinstance(balance.balance_raw, int)
        assert isinstance(balance.receivable_raw, int)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_has_balance(self, read_only_wallet):
        """Test has_balance method."""
        result = await read_only_wallet.has_balance()
        assert result.success
        # result is either True or False, both are valid

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_list_receivables(self, read_only_wallet):
        """Test receivables listing."""
        result = await read_only_wallet.list_receivables()
        assert result.success
        receivables = result.unwrap()
        assert isinstance(receivables, list)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_account_history(self, read_only_wallet):
        """Test account history retrieval."""
        result = await read_only_wallet.account_history(count=5)
        assert result.success
        history = result.unwrap()
        assert isinstance(history, list)


class TestAuthenticatedWallet:
    """Tests for the IAuthenticatedWallet implementation."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reload_authenticated(self, authenticated_wallet):
        """Test reload functionality."""
        result = await authenticated_wallet.reload()
        assert result.success

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_account_info(self, authenticated_wallet):
        """Test account info retrieval."""
        result = await authenticated_wallet.account_info()
        assert result.success
        info = result.unwrap()
        assert info.account is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_balance_info(self, authenticated_wallet):
        """Test balance info retrieval."""
        result = await authenticated_wallet.balance_info()
        assert result.success
        balance = result.unwrap()
        assert isinstance(balance.balance_raw, int)
        assert isinstance(balance.receivable_raw, int)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_send(self, authenticated_wallet, account_address):
        """Test has_balance method."""
        result = await authenticated_wallet.has_balance()
        assert result.success
        # result is either True or False, both are valid

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_receive_all(self, authenticated_wallet):
        """Test receive_all functionality."""
        # First check for any receivables
        receivables_result = await authenticated_wallet.list_receivables()
        assert receivables_result.success
        receivables = receivables_result.unwrap()

        # If there are receivables, try to receive them
        if receivables:
            receive_result = await authenticated_wallet.receive_all()
            assert receive_result.success
            received = receive_result.unwrap()
            assert isinstance(received, list)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_send_2(self, authenticated_wallet, account_address):
        """Test send functionality (skipped by default)."""
        # First check balance
        balance_result = await authenticated_wallet.balance_info()
        assert balance_result.success
        balance = balance_result.unwrap()

        if balance.balance_raw > 0:
            # Only attempt to send if we have balance
            result = await authenticated_wallet.send(
                destination_account=account_address,
                amount="0.00001",
                wait_confirmation=True,
            )
            assert result.success
            block_hash = result.unwrap()
            assert isinstance(block_hash, str) and len(block_hash) == 64
