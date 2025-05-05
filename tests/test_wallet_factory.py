import pytest
from unittest.mock import AsyncMock, patch, Mock
import asyncio

from nanowallet.wallets.wallet_factory import (
    create_wallet_from_seed,
    create_wallet_from_private_key,
)
from nanowallet.libs.rpc import INanoRpc
from nanowallet.errors import (
    InvalidSeedError,
    InvalidIndexError,
    InvalidPrivateKeyError,
)
from nanowallet.models import WalletConfig
from nanowallet.wallets.authenticated_impl import NanoWalletAuthenticated
from nanowallet.wallets.read_only_impl import NanoWalletReadOnly


@pytest.fixture
def mock_rpc():
    """Fixture that provides a mocked RPC client instance"""
    mock = AsyncMock(spec=INanoRpc)
    return mock


@pytest.fixture
def valid_seed():
    return "b632a26208f2f5f36871b4ae952c2f81415728e0ab402c7d7e995f586bef5fd6"


@pytest.fixture
def invalid_seed():
    return "invalid seed"


@pytest.fixture
def valid_private_key():
    return "0efa90463f5397f0c4e09c6c2a4a423cf34bd5ff9d14368201225e0e672193e7"


@pytest.fixture
def invalid_private_key():
    return "invalid private key"


@pytest.fixture
def expected_account():
    return "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s"


class TestWalletFactory:
    """Tests for the wallet factory functions."""

    def test_create_wallet_from_seed_success(
        self, mock_rpc, valid_seed, expected_account
    ):
        """Test successful wallet creation from seed."""
        # Use index 0 for simplicity
        wallet = create_wallet_from_seed(mock_rpc, valid_seed, 0)

        assert isinstance(wallet, NanoWalletAuthenticated)
        assert wallet.account == expected_account
        assert (
            wallet.private_key
            == "0efa90463f5397f0c4e09c6c2a4a423cf34bd5ff9d14368201225e0e672193e7"
        )
        assert wallet._rpc_component.rpc == mock_rpc
        assert isinstance(wallet.config, WalletConfig)

    def test_create_wallet_from_seed_with_config(self, mock_rpc, valid_seed):
        """Test wallet creation from seed with custom config."""
        custom_config = WalletConfig(
            default_representative="nano_1custom9representative99address9goes9here",
            use_work_peers=True,
        )

        wallet = create_wallet_from_seed(mock_rpc, valid_seed, 0, config=custom_config)

        assert wallet.config == custom_config
        assert (
            wallet.config.default_representative
            == "nano_1custom9representative99address9goes9here"
        )
        assert wallet.config.use_work_peers is True

    def test_create_wallet_from_seed_different_indexes(self, mock_rpc, valid_seed):
        """Test that different indexes create different wallets."""
        wallet1 = create_wallet_from_seed(mock_rpc, valid_seed, 0)
        wallet2 = create_wallet_from_seed(mock_rpc, valid_seed, 1)

        # Different indexes should result in different accounts and private keys
        assert wallet1.account != wallet2.account
        assert wallet1.private_key != wallet2.private_key

    def test_create_wallet_from_seed_max_index(self, mock_rpc, valid_seed):
        """Test wallet creation with maximum valid index."""
        max_index = 4294967295  # 2^32 - 1

        # This should not raise an exception
        wallet = create_wallet_from_seed(mock_rpc, valid_seed, max_index)
        assert isinstance(wallet, NanoWalletAuthenticated)

    def test_create_wallet_from_seed_invalid_seed_length(self, mock_rpc, invalid_seed):
        """Test wallet creation with invalid seed length."""
        with pytest.raises(InvalidSeedError) as excinfo:
            create_wallet_from_seed(mock_rpc, invalid_seed, 0)

        # Check error message
        assert "character hex string" in str(excinfo.value)

    def test_create_wallet_from_seed_invalid_seed_format(self, mock_rpc, invalid_seed):
        """Test wallet creation with invalid seed format (non-hex)."""
        # Replace the invalid_seed with a hex-invalid but length-valid seed
        invalid_hex_seed = "g" * 64  # 'g' is not a valid hex character

        with pytest.raises(InvalidSeedError, match="valid hex string"):
            create_wallet_from_seed(mock_rpc, invalid_hex_seed, 0)

    def test_create_wallet_from_seed_invalid_index_type(self, mock_rpc, valid_seed):
        """Test wallet creation with invalid index type."""
        invalid_indexes = [
            "0",  # String
            1.5,  # Float
            None,  # None
            {},  # Dict
            [],  # List
        ]

        for invalid_index in invalid_indexes:
            with pytest.raises(InvalidIndexError):
                create_wallet_from_seed(mock_rpc, valid_seed, invalid_index)

    def test_create_wallet_from_seed_invalid_index_range(self, mock_rpc, valid_seed):
        """Test wallet creation with invalid index range."""
        invalid_indexes = [
            -1,  # Negative
            4294967296,  # 2^32 (one above max)
        ]

        for invalid_index in invalid_indexes:
            with pytest.raises(InvalidIndexError):
                create_wallet_from_seed(mock_rpc, valid_seed, invalid_index)

    @patch("nanowallet.wallets.wallet_factory.AccountHelper.generate_private_key")
    def test_create_wallet_from_seed_generation_failure(
        self, mock_generate_key, mock_rpc, valid_seed
    ):
        """Test handling of key generation failures."""
        # Make the key generation fail
        mock_generate_key.side_effect = Exception("Key generation failed")

        with pytest.raises(ValueError, match="Failed to generate private key"):
            create_wallet_from_seed(mock_rpc, valid_seed, 0)

    def test_create_wallet_from_private_key_success(
        self, mock_rpc, valid_private_key, expected_account
    ):
        """Test successful wallet creation from private key."""
        wallet = create_wallet_from_private_key(mock_rpc, valid_private_key)

        assert isinstance(wallet, NanoWalletAuthenticated)
        assert wallet.account == expected_account
        assert wallet.private_key == valid_private_key
        assert wallet._rpc_component.rpc == mock_rpc
        assert isinstance(wallet.config, WalletConfig)

    def test_create_wallet_from_private_key_with_config(
        self, mock_rpc, valid_private_key
    ):
        """Test wallet creation from private key with custom config."""
        custom_config = WalletConfig(
            default_representative="nano_1custom9representative99address9goes9here",
            use_work_peers=True,
        )

        wallet = create_wallet_from_private_key(
            mock_rpc, valid_private_key, config=custom_config
        )

        assert wallet.config == custom_config
        assert (
            wallet.config.default_representative
            == "nano_1custom9representative99address9goes9here"
        )
        assert wallet.config.use_work_peers is True

    def test_create_wallet_from_private_key_invalid_length(self, mock_rpc):
        """Test wallet creation with invalid private key length."""
        invalid_keys = [
            "",  # Empty
            "abc123",  # Too short
            "a" * 63,  # One character short
            "a" * 65,  # One character too long
        ]

        for invalid_key in invalid_keys:
            with pytest.raises(InvalidPrivateKeyError, match="Invalid private key"):
                create_wallet_from_private_key(mock_rpc, invalid_key)

    def test_create_wallet_from_private_key_invalid_format(self, mock_rpc):
        """Test wallet creation with invalid private key format (non-hex)."""
        # Valid length but contains non-hex characters
        invalid_key = "g" * 64  # 'g' is not a valid hex character

        with pytest.raises(InvalidPrivateKeyError, match="Invalid private key"):
            create_wallet_from_private_key(mock_rpc, invalid_key)

    def test_seed_case_insensitivity(self, mock_rpc, valid_seed, expected_account):
        """Test that seed is processed case-insensitively."""
        # Create a wallet with uppercase seed
        uppercase_seed = valid_seed.upper()
        wallet_uppercase = create_wallet_from_seed(mock_rpc, uppercase_seed, 0)

        # Create a wallet with lowercase seed
        lowercase_seed = valid_seed.lower()
        wallet_lowercase = create_wallet_from_seed(mock_rpc, lowercase_seed, 0)

        # Both should generate the same account and private key
        assert wallet_uppercase.account == wallet_lowercase.account == expected_account
        assert wallet_uppercase.private_key == wallet_lowercase.private_key

    def test_private_key_case_insensitivity(
        self, mock_rpc, valid_private_key, expected_account
    ):
        """Test that private key is processed case-insensitively."""
        # Create a wallet with uppercase private key
        uppercase_key = valid_private_key.upper()
        wallet_uppercase = create_wallet_from_private_key(mock_rpc, uppercase_key)

        # Create a wallet with lowercase private key
        lowercase_key = valid_private_key.lower()
        wallet_lowercase = create_wallet_from_private_key(mock_rpc, lowercase_key)

        # Both should generate the same account
        assert wallet_uppercase.account == wallet_lowercase.account == expected_account

    def test_create_wallet_from_private_key_invalid_key(
        self, mock_rpc, invalid_private_key
    ):
        """Test wallet creation with invalid private key."""
        with pytest.raises(InvalidPrivateKeyError) as excinfo:
            create_wallet_from_private_key(mock_rpc, invalid_private_key)

        # Check error message
        assert "Invalid private key" in str(excinfo.value)

    def test_create_wallet_from_private_key_case_insensitive(self, mock_rpc):
        """Test that private key case doesn't matter."""
        lower_key = "0efa90463f5397f0c4e09c6c2a4a423cf34bd5ff9d14368201225e0e672193e7"
        upper_key = lower_key.upper()

        wallet_lower = create_wallet_from_private_key(mock_rpc, lower_key)
        wallet_upper = create_wallet_from_private_key(mock_rpc, upper_key)

        # Should generate the same wallet regardless of case
        assert wallet_lower.account == wallet_upper.account
