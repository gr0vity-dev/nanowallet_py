import pytest
from unittest.mock import patch, Mock

from nanowallet.libs.block import NanoWalletBlock
from nanowallet.errors import InvalidAccountError


class TestNanoWalletBlock:
    """Tests for the NanoWalletBlock class."""

    @pytest.fixture
    def valid_account(self):
        return "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s"

    @pytest.fixture
    def valid_representative(self):
        return "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf"

    @pytest.fixture
    def valid_destination(self):
        return "nano_1natrium1o3z5519ifou7xii8crpxpk8y65qmkih8e8bpsjri651oza8imdd"

    @pytest.fixture
    def valid_previous(self):
        return "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78"

    @pytest.fixture
    def valid_source_hash(self):
        return "3F48EA21C70DE2221AFEAB533C9FF28BF19147FC674F01376D05202F28BD7878"

    @pytest.fixture
    def valid_balance(self):
        return 1000000000000000000000000000000  # 1 Nano in raw

    @pytest.fixture
    def valid_private_key(self):
        return "0efa90463f5397f0c4e09c6c2a4a423cf34bd5ff9d14368201225e0e672193e7"

    @pytest.fixture
    def valid_public_key(self):
        return "1natrium1o3z5519ifou7xii8crpxpk8y65qmkih8e8bpsjri651oza8imdd"

    @pytest.fixture
    def valid_work(self):
        return "7fe398470f748c75"

    @patch("nanowallet.libs.block.Block")
    def test_init_send_block(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
        valid_destination,
    ):
        """Test initialization of a send block."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance

        # Mock AccountHelper.get_public_key to return a predetermined value
        with patch(
            "nanowallet.libs.block.AccountHelper.get_public_key"
        ) as mock_get_public_key:
            mock_get_public_key.return_value = (
                "deadbeef"  # Simplified public key for testing
            )

            # Create a send block (with destination account)
            block = NanoWalletBlock(
                account=valid_account,
                previous=valid_previous,
                representative=valid_representative,
                balance=valid_balance,
                destination_account=valid_destination,
            )

            # Verify Block was created with correct parameters
            mock_block_class.assert_called_once_with(
                block_type="state",
                account=valid_account,
                previous=valid_previous,
                representative=valid_representative,
                balance=valid_balance,
                link="deadbeef",  # Should be the result of get_public_key
            )

            # Verify AccountHelper.get_public_key was called with destination_account
            mock_get_public_key.assert_called_once_with(valid_destination)

    @patch("nanowallet.libs.block.Block")
    def test_init_receive_block(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
        valid_source_hash,
    ):
        """Test initialization of a receive block."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance

        # Create a receive block (with source_hash)
        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
            source_hash=valid_source_hash,
        )

        # Verify Block was created with correct parameters
        mock_block_class.assert_called_once_with(
            block_type="state",
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
            link=valid_source_hash,
        )

    @patch("nanowallet.libs.block.Block")
    def test_init_change_block(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
    ):
        """Test initialization of a change representative block."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance

        # Create a change block (no source_hash or destination_account)
        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
        )

        # Verify Block was created with correct parameters
        mock_block_class.assert_called_once_with(
            block_type="state",
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
            link="0" * 64,  # Default zero hash
        )

    def test_init_invalid_params(
        self,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
        valid_source_hash,
        valid_destination,
    ):
        """Test initialization with invalid parameters."""
        # Test that specifying both source_hash and destination_account raises an error
        with pytest.raises(
            ValueError, match="Cannot specify both source_hash and destination_account"
        ):
            NanoWalletBlock(
                account=valid_account,
                previous=valid_previous,
                representative=valid_representative,
                balance=valid_balance,
                source_hash=valid_source_hash,
                destination_account=valid_destination,
            )

    @patch("nanowallet.libs.block.Block")
    @patch("nanowallet.libs.block.AccountHelper.get_public_key")
    def test_get_link_value_with_destination(
        self,
        mock_get_public_key,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
        valid_destination,
    ):
        """Test _get_link_value with destination account."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance
        mock_get_public_key.return_value = "deadbeef"  # Simplified public key

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
            destination_account=valid_destination,
        )

        # Test internal method directly
        link = block._get_link_value(None, valid_destination)
        assert link == "deadbeef"
        mock_get_public_key.assert_called_with(valid_destination)

    @patch("nanowallet.libs.block.Block")
    def test_get_link_value_with_source(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
        valid_source_hash,
    ):
        """Test _get_link_value with source hash."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
            source_hash=valid_source_hash,
        )

        # Test internal method directly
        link = block._get_link_value(valid_source_hash, None)
        assert link == valid_source_hash

    @patch("nanowallet.libs.block.Block")
    def test_get_link_value_default(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
    ):
        """Test _get_link_value with no source or destination."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
        )

        # Test internal method directly
        link = block._get_link_value(None, None)
        assert link == "0" * 64  # Zero hash

    @patch("nanowallet.libs.block.Block")
    def test_sign(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
        valid_private_key,
    ):
        """Test sign method."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
        )

        # Sign the block
        block.sign(valid_private_key)

        # Verify underlying block.sign was called
        mock_block_instance.sign.assert_called_once_with(valid_private_key)

    @patch("nanowallet.libs.block.Block")
    def test_work_block_hash(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
    ):
        """Test work_block_hash property."""
        mock_block_instance = Mock()
        mock_block_instance.work_block_hash = "workhash123"
        mock_block_class.return_value = mock_block_instance

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
        )

        # Get work block hash
        work_hash = block.work_block_hash

        # Verify property returns correct value
        assert work_hash == "workhash123"

    @patch("nanowallet.libs.block.Block")
    def test_block_hash(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
    ):
        """Test block_hash property."""
        mock_block_instance = Mock()
        mock_block_instance.block_hash = "blockhash456"
        mock_block_class.return_value = mock_block_instance

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
        )

        # Get block hash
        block_hash = block.block_hash

        # Verify property returns correct value
        assert block_hash == "blockhash456"

    @patch("nanowallet.libs.block.Block")
    def test_set_work(
        self,
        mock_block_class,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
        valid_work,
    ):
        """Test set_work method."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
        )

        # Set work value
        block.set_work(valid_work)

        # Verify underlying block.set_work was called
        mock_block_instance.set_work.assert_called_once_with(valid_work)

    def test_json(
        self,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
    ):
        """Test json method."""
        expected_json = {
            "account": valid_account,
            "previous": valid_previous.upper(),
            "representative": valid_representative,
            "balance": str(valid_balance),
            "link": "0" * 64,
            "link_as_account": "nano_1111111111111111111111111111111111111111111111111111hifc8npp",
            "type": "state",
        }

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
        )

        # Get JSON representation
        json_output = block.json()

        # Verify json method returns correct value
        assert json_output == str(expected_json).replace("'", '"')

    def test_to_dict(
        self,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
    ):
        """Test json method."""
        expected_json = {
            "type": "state",
            "account": valid_account,
            "previous": valid_previous.upper(),
            "representative": valid_representative,
            "balance": str(valid_balance),
            "link": "0" * 64,
            "link_as_account": "nano_1111111111111111111111111111111111111111111111111111hifc8npp",
        }

        block = NanoWalletBlock(
            account=valid_account,
            previous=valid_previous,
            representative=valid_representative,
            balance=valid_balance,
        )

        # Get JSON representation
        json_output = block.to_dict()

        # Verify json method returns correct value
        assert json_output == expected_json

    @patch("nanowallet.libs.block.AccountHelper.get_public_key")
    @patch("nanowallet.libs.block.Block")
    def test_destination_account_error(
        self,
        mock_block_class,
        mock_get_public_key,
        valid_account,
        valid_previous,
        valid_representative,
        valid_balance,
        valid_destination,
    ):
        """Test error handling when destination account is invalid."""
        mock_block_instance = Mock()
        mock_block_class.return_value = mock_block_instance
        mock_get_public_key.side_effect = InvalidAccountError("Invalid account")

        # Creating block with invalid destination should raise InvalidAccountError
        with pytest.raises(InvalidAccountError, match="Invalid account"):
            NanoWalletBlock(
                account=valid_account,
                previous=valid_previous,
                representative=valid_representative,
                balance=valid_balance,
                destination_account=valid_destination,
            )
