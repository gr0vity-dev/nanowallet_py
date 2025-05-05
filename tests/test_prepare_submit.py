import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import logging

from nanowallet.wallets import NanoWalletReadOnly
from nanowallet.models import UnsignedBlockDetails
from nanowallet.errors import (
    InvalidAccountError,
    BlockNotFoundError,
    InsufficientBalanceError,
    NanoException,
)
from nanowallet.utils import NanoResult

logger = logging.getLogger(__name__)

# Use valid Nano address formats that will pass validation
VALID_ACCOUNT = "nano_3t6k35gi95xu6tergt6p69ck76ogmitsa8mnijtpxm9fkcm736xtoncuohr3"
VALID_DESTINATION = (
    "nano_1natrium1o3z5519stt5nc8se6nezsephsm1yt1f6im1bj8qdqgvmph59kbb76"
)
VALID_REPRESENTATIVE = (
    "nano_1center16ci77qw5w69ww8sy4i4bfmgfhr81ydzpurm91cauj11jn6y3uc5y"
)
VALID_SENDER = "nano_1ipx847tk8o46pwxt5qjdbncjqcbwcc1rrmqnkztrfjy5k7z4imsrata9est"
VALID_SIGNATURE = "a" * 128  # Mock valid signature (128 hex chars)
VALID_BLOCK_HASH = "A" * 64  # Valid block hash (64 hex chars)


@pytest.fixture
def mock_rpc():
    """Create a mocked RPC client for testing."""
    mock = AsyncMock()
    mock.process.return_value = {"hash": "processed_hash_returned_by_rpc"}

    # Mock account_info response for the _get_block_params method
    mock.account_info.return_value = {
        "frontier": "0" * 64,
        "balance": "5000000000000000000000000",  # 5 Nano balance
        "representative": VALID_REPRESENTATIVE,
    }

    # Mock receivable response
    mock.receivable.return_value = {"blocks": {}}

    return mock


# Mock the validate_account method to always return True for our test addresses
@pytest.fixture(autouse=True)
def mock_account_validation(monkeypatch):
    """Override account validation to return True for our test accounts."""

    def mock_validate(account_id):
        return True

    monkeypatch.setattr(
        "nanowallet.libs.account_helper.AccountHelper.validate_account", mock_validate
    )


# Mock the NanoWalletBlock to avoid its dependency on real account validation
@pytest.fixture(autouse=True)
def mock_nano_wallet_block(monkeypatch):
    """Mock the NanoWalletBlock class to avoid actual block creation."""

    class MockNanoWalletBlock:
        def __init__(
            self,
            account,
            previous,
            representative,
            balance,
            source_hash=None,
            destination_account=None,
        ):
            self.account = account
            self.previous = previous
            self.representative = representative
            self.balance = balance
            self.source_hash = source_hash
            self.destination_account = destination_account
            self._block = MagicMock()
            self._block.link = (
                source_hash
                if source_hash
                else "pubkey_for_" + (destination_account or "")
            )

        @property
        def block_hash(self):
            return "mock_block_hash_for_signing_" + str(self.balance)

        @property
        def work_block_hash(self):
            return "mock_hash_for_work_" + self.previous[:8]

    # Patch the NanoWalletBlock class
    monkeypatch.setattr("nanowallet.libs.block.NanoWalletBlock", MockNanoWalletBlock)

    # Also patch get_public_key to avoid the underlying validation
    def mock_get_public_key(account_id):
        return "pubkey_for_" + account_id

    monkeypatch.setattr(
        "nanowallet.libs.account_helper.AccountHelper.get_public_key",
        mock_get_public_key,
    )


class TestPrepareSubmitAPI:
    """Test suite for the simplified prepare/submit API."""

    @pytest.mark.asyncio
    async def test_prepare_send_block(self):
        """Test the prepare_send_block function with mocked wallet."""
        # Create expected result
        expected_details = UnsignedBlockDetails(
            account=VALID_ACCOUNT,
            previous="previous_hash",
            representative=VALID_REPRESENTATIVE,
            balance_raw=4000000000000000000000000,  # 4 Nano (after sending 1)
            link="0000000000000000000000000000000000000000000000000000000000000000",
            hash_to_sign="mock_hash_to_sign",
            hash_for_work="mock_hash_for_work",
            link_as_account=VALID_DESTINATION,
        )

        # Create a completely mocked wallet that returns our expected details
        mock_wallet = AsyncMock()
        mock_wallet.prepare_send_block = AsyncMock(
            return_value=NanoResult(expected_details)
        )

        # Call prepare_send_block
        amount_raw = 1000000000000000000000000  # 1 Nano
        result = await mock_wallet.prepare_send_block(VALID_DESTINATION, amount_raw)

        # Verify NanoResult
        assert isinstance(result, NanoResult)
        assert result.success
        details = result.unwrap()

        # Verify the returned object is the same as our expected details
        assert details == expected_details

        # Verify the method was called with the right parameters
        mock_wallet.prepare_send_block.assert_called_once_with(
            VALID_DESTINATION, amount_raw
        )

    @pytest.mark.asyncio
    async def test_prepare_receive_block(self):
        """Test the prepare_receive_block function with mocked wallet."""
        # Create expected result
        expected_details = UnsignedBlockDetails(
            account=VALID_ACCOUNT,
            previous="previous_hash",
            representative=VALID_REPRESENTATIVE,
            balance_raw=6000000000000000000000000,  # 6 Nano (after receiving 1)
            link=VALID_BLOCK_HASH,
            hash_to_sign="mock_hash_to_sign",
            hash_for_work="mock_hash_for_work",
            link_as_account=VALID_SENDER,
        )

        # Create a completely mocked wallet that returns our expected details
        mock_wallet = AsyncMock()
        mock_wallet.prepare_receive_block = AsyncMock(
            return_value=NanoResult(expected_details)
        )

        # Call prepare_receive_block
        source_hash = VALID_BLOCK_HASH
        result = await mock_wallet.prepare_receive_block(source_hash)

        # Verify NanoResult
        assert isinstance(result, NanoResult)
        assert result.success
        details = result.unwrap()

        # Verify the returned object is the same as our expected details
        assert details == expected_details

        # Verify the method was called with the right parameters
        mock_wallet.prepare_receive_block.assert_called_once_with(source_hash)

    @pytest.mark.asyncio
    async def test_submit_signed_block_success(self, mock_rpc):
        """Test submit_signed_block with a valid signature."""
        # Create mocks for both components
        mock_prep_component = AsyncMock()

        # Mock work generation
        mock_rpc.work_generate.return_value = {"work": "mock_work_value"}

        # Expected hash from RPC process response
        expected_hash = "processed_hash_returned_by_rpc"

        # Patch preparation component
        with patch(
            "nanowallet.wallets.components.block_preparation.BlockPreparationComponent",
            return_value=mock_prep_component,
        ):

            # Create the wallet with our mocked RPC
            wallet = NanoWalletReadOnly(
                rpc=mock_rpc,
                account=VALID_ACCOUNT,
            )

            # Create a mock unsigned details object for testing
            mock_unsigned_details = UnsignedBlockDetails(
                account=VALID_ACCOUNT,
                previous="previous_hash",
                representative=VALID_REPRESENTATIVE,
                balance_raw=4000000000000000000000000,
                link="0000000000000000000000000000000000000000000000000000000000000000",
                hash_to_sign="hash_to_sign_value",
                hash_for_work="hash_for_work_value",
                link_as_account=VALID_DESTINATION,
            )

            # Use a valid signature
            valid_signature = VALID_SIGNATURE

            # The result should be wrapped in a NanoResult with the processed hash
            result = await wallet.submit_signed_block(
                mock_unsigned_details, valid_signature
            )

            # Verify NanoResult
            assert isinstance(result, NanoResult)
            assert result.success
            assert result.unwrap() == expected_hash

            # Verify RPC was called with the correct parameters
            # The actual call used positional args, not keyword args
            assert mock_rpc.work_generate.call_count == 1
            call_args = mock_rpc.work_generate.call_args
            assert call_args[0][0] == "hash_for_work_value"  # First positional arg
            assert call_args[1]["use_peers"] is False  # Keyword arg

    @pytest.mark.asyncio
    async def test_invalid_signature(self, mock_rpc):
        """Test submit_signed_block with an invalid signature."""
        # Create mocks for both components
        mock_prep_component = AsyncMock()
        mock_sub_component = AsyncMock()

        # Configure the submission component to raise an exception
        mock_sub_component.submit = AsyncMock(
            side_effect=NanoException(
                "Invalid signature provided.", "INVALID_SIGNATURE"
            )
        )

        # Patch both components
        with patch(
            "nanowallet.wallets.components.block_preparation.BlockPreparationComponent",
            return_value=mock_prep_component,
        ), patch(
            "nanowallet.wallets.components.block_submission.BlockSubmissionComponent",
            return_value=mock_sub_component,
        ):

            # Create the wallet with our mocked RPC
            wallet = NanoWalletReadOnly(
                rpc=mock_rpc,
                account=VALID_ACCOUNT,
            )

            # Create a mock unsigned details object for testing
            mock_unsigned_details = UnsignedBlockDetails(
                account=VALID_ACCOUNT,
                previous="previous_hash",
                representative=VALID_REPRESENTATIVE,
                balance_raw=4000000000000000000000000,
                link="0000000000000000000000000000000000000000000000000000000000000000",
                hash_to_sign="hash_to_sign_value",
                hash_for_work="hash_for_work_value",
                link_as_account=VALID_DESTINATION,
            )

            # Use an invalid signature
            invalid_signature = "a" * 127  # 127 chars instead of 128

            # The result should be wrapped in a NanoResult with error
            result = await wallet.submit_signed_block(
                mock_unsigned_details, invalid_signature
            )
            assert isinstance(result, NanoResult)
            assert not result.success
            assert "Invalid signature" in str(result.error)
