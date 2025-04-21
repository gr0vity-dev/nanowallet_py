import pytest
from unittest.mock import patch, Mock

from nanowallet.libs.account_helper import AccountHelper
from nanowallet.errors import InvalidAccountError
from nano_lib_py.accounts import InvalidAccount, AccountIDPrefix


class TestAccountHelper:
    """Tests for the AccountHelper class."""

    @pytest.fixture
    def valid_account(self):
        return "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s"

    @pytest.fixture
    def valid_xrb_account(self):
        return "xrb_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s"

    @pytest.fixture
    def invalid_account(self):
        return "invalid_account"

    @pytest.fixture
    def valid_private_key(self):
        return "0efa90463f5397f0c4e09c6c2a4a423cf34bd5ff9d14368201225e0e672193e7"

    @pytest.fixture
    def valid_public_key(self):
        return "0e64396e562ed52de819d6b5c9c8526be3dd9c4baaedee850bac4c4057bc2933"

    @pytest.fixture
    def valid_seed(self):
        return "b632a26208f2f5f36871b4ae952c2f81415728e0ab402c7d7e995f586bef5fd6"

    def test_validate_account_valid_nano(self, valid_account):
        """Test validating a valid nano_ account."""
        result = AccountHelper.validate_account(valid_account)
        assert result is True

    def test_validate_account_valid_xrb(self, valid_xrb_account):
        """Test validating a valid xrb_ account."""
        result = AccountHelper.validate_account(valid_xrb_account)
        assert result is True

    def test_validate_account_invalid(self, invalid_account):
        """Test validating an invalid account raises an exception."""
        with pytest.raises(InvalidAccountError):
            AccountHelper.validate_account(invalid_account)

    def test_validate_account_too_short(self):
        """Test validating a too short account."""
        with pytest.raises(InvalidAccountError):
            AccountHelper.validate_account("nano_1short")

    def test_validate_account_invalid_checksum(self):
        """Test validating an account with invalid checksum."""
        # Same as valid_account but last character changed
        invalid_checksum = (
            "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38z"
        )
        with pytest.raises(InvalidAccountError):
            AccountHelper.validate_account(invalid_checksum)

    @patch("nanowallet.libs.account_helper.get_account_id")
    def test_get_account_address(
        self, mock_get_account_id, valid_private_key, valid_account
    ):
        """Test getting an account address from a private key."""
        mock_get_account_id.return_value = valid_account

        result = AccountHelper.get_account_address(valid_private_key)

        assert result == valid_account
        mock_get_account_id.assert_called_once_with(private_key=valid_private_key)

    @patch("nanowallet.libs.account_helper.get_account_id")
    def test_get_account_address_error(self, mock_get_account_id, valid_private_key):
        """Test error handling when getting account address."""
        mock_get_account_id.side_effect = Exception("Test error")

        with pytest.raises(ValueError, match="Invalid private key"):
            AccountHelper.get_account_address(valid_private_key)

    @patch("nanowallet.libs.account_helper.get_account_public_key")
    def test_get_public_key(self, mock_get_public_key, valid_account, valid_public_key):
        """Test getting a public key from an account ID."""
        mock_get_public_key.return_value = valid_public_key

        result = AccountHelper.get_public_key(valid_account)

        assert result == valid_public_key
        mock_get_public_key.assert_called_once_with(account_id=valid_account)

    @patch("nanowallet.libs.account_helper.get_account_public_key")
    def test_get_public_key_error(self, mock_get_public_key, valid_account):
        """Test error handling when getting public key."""
        mock_get_public_key.side_effect = InvalidAccount("Test error")

        with pytest.raises(InvalidAccountError, match="Invalid account ID"):
            AccountHelper.get_public_key(valid_account)

    @patch("nanowallet.libs.account_helper.generate_account_private_key")
    def test_generate_private_key(
        self, mock_generate_key, valid_seed, valid_private_key
    ):
        """Test generating a private key from seed and index."""
        mock_generate_key.return_value = valid_private_key

        result = AccountHelper.generate_private_key(valid_seed, 0)

        assert result == valid_private_key
        mock_generate_key.assert_called_once_with(valid_seed, 0)

    @patch("nanowallet.libs.account_helper.generate_account_private_key")
    def test_generate_private_key_error(self, mock_generate_key, valid_seed):
        """Test error handling when generating private key."""
        mock_generate_key.side_effect = Exception("Test error")

        with pytest.raises(ValueError, match="Invalid seed"):
            AccountHelper.generate_private_key(valid_seed, 0)

    @patch("nanowallet.libs.account_helper.get_account_id")
    def test_get_account_from_public_key(
        self, mock_get_account_id, valid_public_key, valid_account
    ):
        """Test getting an account ID from a public key."""
        mock_get_account_id.return_value = valid_account

        result = AccountHelper.get_account(public_key=valid_public_key)

        assert result == valid_account
        mock_get_account_id.assert_called_once_with(
            public_key=valid_public_key, private_key=None, prefix=AccountIDPrefix.NANO
        )

    @patch("nanowallet.libs.account_helper.get_account_id")
    def test_get_account_from_private_key(
        self, mock_get_account_id, valid_private_key, valid_account
    ):
        """Test getting an account ID from a private key."""
        mock_get_account_id.return_value = valid_account

        result = AccountHelper.get_account(private_key=valid_private_key)

        assert result == valid_account
        mock_get_account_id.assert_called_once_with(
            public_key=None, private_key=valid_private_key, prefix=AccountIDPrefix.NANO
        )

    @patch("nanowallet.libs.account_helper.get_account_id")
    def test_get_account_error(self, mock_get_account_id, valid_public_key):
        """Test error handling when getting account ID."""
        mock_get_account_id.side_effect = Exception("Test error")

        with pytest.raises(InvalidAccountError, match="Invalid public key"):
            AccountHelper.get_account(public_key=valid_public_key)

    def test_get_account_no_keys(self):
        """Test getting an account ID without providing any keys."""
        with pytest.raises(InvalidAccountError):
            # Neither public_key nor private_key provided
            AccountHelper.get_account()
