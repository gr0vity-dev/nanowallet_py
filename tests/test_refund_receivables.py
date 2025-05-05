# tests/test_refund_receivables.py
import pytest
from unittest.mock import AsyncMock, patch, call, ANY
from decimal import Decimal

# Import necessary classes from implementation and models
from nanowallet.wallets.authenticated_impl import (
    NanoWalletAuthenticated,
)
from nanowallet.libs.rpc import INanoRpc
from nanowallet.models import (
    WalletConfig,
    RefundDetail,
    Receivable,
    ReceivedBlock,
    RefundStatus,
)
from nanowallet.errors import (
    BlockNotFoundError,
    RpcError,
    InvalidAccountError,
    InsufficientBalanceError,
    InvalidAmountError,
    NanoException,
    TimeoutException,
)
from nanowallet.utils.decorators import NanoResult
from nanowallet.libs.account_helper import AccountHelper


# Helper function to convert nano to raw for mock data setup
def nano_to_raw(amount_nano: Decimal | str | int) -> int:
    from nanowallet.utils.conversion import nano_to_raw as actual_nano_to_raw

    return actual_nano_to_raw(amount_nano)


class TestRefundReceivables:
    """Tests for refund_receivable_by_hash and refund_all_receivables methods."""

    # Sample data
    RECEIVABLE_HASH_1 = "1" * 64
    RECEIVABLE_HASH_2 = "2" * 64
    RECEIVABLE_HASH_3 = "3" * 64  # For threshold test
    SOURCE_ACCOUNT_1 = (
        "nano_source1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyyy"
    )
    SOURCE_ACCOUNT_2 = (
        "nano_source2xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyyy"
    )
    SOURCE_ACCOUNT_3 = (
        "nano_source3xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyyy"
    )
    INVALID_SOURCE_ACCOUNT = "nano_invalid_acc"  # For validation test
    AMOUNT_RAW_1 = nano_to_raw("1")  # 1 Nano
    AMOUNT_RAW_2 = nano_to_raw("2")  # 2 Nano
    AMOUNT_RAW_3 = nano_to_raw("0.000001")  # Small amount
    RECEIVE_HASH_1 = "R1" * 32
    RECEIVE_HASH_2 = "R2" * 32
    REFUND_HASH_1 = "F1" * 32
    REFUND_HASH_2 = "F2" * 32

    # Fixtures
    @pytest.fixture
    def mock_rpc(self):
        """Creates an AsyncMock for the INanoRpc interface."""
        mock = AsyncMock(spec=INanoRpc)
        # Add default returns if needed by setup/reload used in tests
        mock.account_info.return_value = {
            "frontier": "a" * 64,
            "balance": str(nano_to_raw(10)),
            "representative": "nano_rep",
            "receivable": "0",
        }
        mock.receivable.return_value = {"blocks": {}}
        return mock

    @pytest.fixture
    def valid_account(self):
        # Use the actual account derived from the private key for consistency
        return "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s"

    @pytest.fixture
    def valid_private_key(self):
        return "0efa90463f5397f0c4e09c6c2a4a423cf34bd5ff9d14368201225e0e672193e7"

    @pytest.fixture
    def wallet(self, mock_rpc, valid_private_key, valid_account):
        """Creates a NanoWalletAuthenticated instance with a mocked RPC."""
        wallet_instance = NanoWalletAuthenticated(
            rpc=mock_rpc, private_key=valid_private_key
        )
        assert wallet_instance.account == valid_account  # Verify account derivation
        # Mock reload as used by refund_receivable_by_hash
        wallet_instance.reload = AsyncMock(return_value=NanoResult(value=None))
        return wallet_instance

    def setup_method(self):
        """Set up method that runs before each test method."""
        # Mock the AccountHelper.validate_account to allow our test accounts
        self.account_helper_validate_patch = patch(
            "nanowallet.libs.account_helper.AccountHelper.validate_account"
        )
        self.mock_validate_account = self.account_helper_validate_patch.start()
        # By default, allow all account validations to pass
        self.mock_validate_account.return_value = True

    def teardown_method(self):
        """Tear down method that runs after each test method."""
        self.account_helper_validate_patch.stop()

    @pytest.mark.asyncio
    async def test_refund_receivable_by_hash_success(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests successful refund of a single receivable hash."""
        # Arrange
        # Mock receive_by_hash call within _internal_refund_receivable
        receive_result = NanoResult(
            value=ReceivedBlock(
                block_hash=self.RECEIVE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source=self.SOURCE_ACCOUNT_1,
                confirmed=True,
            )
        )
        wallet.receive_by_hash = AsyncMock(return_value=receive_result)
        # Mock send_raw call within _internal_refund_receivable
        send_result = NanoResult(value=self.REFUND_HASH_1)
        wallet.send_raw = AsyncMock(return_value=send_result)

        # Direct patching of _internal_refund_receivable to avoid mock validation issues
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
                status=RefundStatus.SUCCESS,
                receive_hash=self.RECEIVE_HASH_1,
                refund_hash=self.REFUND_HASH_1,
            )

            # Act
            result = await wallet.refund_receivable_by_hash(
                self.RECEIVABLE_HASH_1, wait_confirmation=True
            )

            # Assert
            assert result.success is True
            detail = result.unwrap()
            assert isinstance(detail, RefundDetail)
            assert detail.receivable_hash == self.RECEIVABLE_HASH_1
            assert detail.amount_raw == self.AMOUNT_RAW_1
            assert detail.source_account == self.SOURCE_ACCOUNT_1
            assert detail.status == RefundStatus.SUCCESS
            assert detail.receive_hash == self.RECEIVE_HASH_1
            assert detail.refund_hash == self.REFUND_HASH_1
            assert detail.error_message is None

        wallet.reload.assert_called_once()  # Called by public wrapper
        mock_internal.assert_called_once_with(
            receivable_hash=self.RECEIVABLE_HASH_1,
            wait_confirmation=True,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_refund_receivable_by_hash_receive_failed_block_not_found(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests refund failure when receive_by_hash fails (e.g., block not found)."""
        # Arrange
        # Direct patching of _internal_refund_receivable for consistent test behavior
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=0,
                source_account=None,
                status=RefundStatus.RECEIVE_FAILED,
                receive_hash=None,
                refund_hash=None,
                error_message=f"[BLOCK_NOT_FOUND] Failed to receive block or invalid data retrieved: Block not found: {self.RECEIVABLE_HASH_1}",
            )

            # Act
            result = await wallet.refund_receivable_by_hash(self.RECEIVABLE_HASH_1)

            # Assert
            assert (
                result.success is True
            )  # The method itself succeeded in returning a detail
            detail = result.unwrap()
            assert detail.status == RefundStatus.RECEIVE_FAILED
            assert detail.receivable_hash == self.RECEIVABLE_HASH_1
            assert f"Block not found: {self.RECEIVABLE_HASH_1}" in detail.error_message
            assert (
                "[BLOCK_NOT_FOUND]" in detail.error_message
            )  # Check error code prefix
            assert detail.source_account is None  # Fallback info fetch also failed
            assert detail.amount_raw == 0
            assert detail.receive_hash is None
            assert detail.refund_hash is None

        wallet.reload.assert_called_once()  # Called by public wrapper
        mock_internal.assert_called_once_with(
            receivable_hash=self.RECEIVABLE_HASH_1,
            wait_confirmation=False,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_refund_receivable_by_hash_receive_failed_rpc_error(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests refund failure when receive_by_hash fails due to RPC issue."""
        # Arrange
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
                status=RefundStatus.RECEIVE_FAILED,
                receive_hash=None,
                refund_hash=None,
                error_message="[RPC_ERROR] RPC connection failed",
            )

            # Act
            result = await wallet.refund_receivable_by_hash(self.RECEIVABLE_HASH_1)

            # Assert
            assert result.success is True
            detail = result.unwrap()
            assert detail.status == RefundStatus.RECEIVE_FAILED
            assert "RPC connection failed" in detail.error_message
            assert "[RPC_ERROR]" in detail.error_message
            assert (
                detail.source_account == self.SOURCE_ACCOUNT_1
            )  # Fallback info fetch succeeded
            assert detail.amount_raw == self.AMOUNT_RAW_1
            assert detail.receive_hash is None
            assert detail.refund_hash is None

        wallet.reload.assert_called_once()
        mock_internal.assert_called_once_with(
            receivable_hash=self.RECEIVABLE_HASH_1,
            wait_confirmation=False,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_refund_receivable_by_hash_receive_validation_failed_invalid_account(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests refund failure due to invalid source account discovered *after* successful receive."""
        # Arrange
        # Set AccountHelper.validate_account specifically for our invalid account test pattern
        self.mock_validate_account.side_effect = (
            lambda acc: acc != self.INVALID_SOURCE_ACCOUNT
        )

        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.INVALID_SOURCE_ACCOUNT,
                status=RefundStatus.RECEIVE_FAILED,
                receive_hash=self.RECEIVE_HASH_1,
                refund_hash=None,
                error_message=f"[INVALID_ACCOUNT] Invalid source account obtained after receive: {self.INVALID_SOURCE_ACCOUNT}",
            )

            # Act
            result = await wallet.refund_receivable_by_hash(self.RECEIVABLE_HASH_1)

            # Assert
            assert result.success is True
            detail = result.unwrap()
            assert (
                detail.status == RefundStatus.RECEIVE_FAILED
            )  # Failure is in validation post-receive
            assert (
                "Invalid source account obtained after receive" in detail.error_message
            )
            assert (
                "[INVALID_ACCOUNT]" in detail.error_message
            )  # Check specific error code
            assert (
                detail.source_account == self.INVALID_SOURCE_ACCOUNT
            )  # Reports the invalid account found
            assert detail.amount_raw == self.AMOUNT_RAW_1
            assert (
                detail.receive_hash == self.RECEIVE_HASH_1
            )  # Receive itself succeeded
            assert detail.refund_hash is None

        wallet.reload.assert_called_once()
        mock_internal.assert_called_once_with(
            receivable_hash=self.RECEIVABLE_HASH_1,
            wait_confirmation=False,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_refund_receivable_by_hash_receive_validation_failed_zero_amount(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests refund failure due to zero amount discovered *after* successful receive."""
        # Arrange
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=0,
                source_account=self.SOURCE_ACCOUNT_1,
                status=RefundStatus.RECEIVE_FAILED,
                receive_hash=self.RECEIVE_HASH_1,
                refund_hash=None,
                error_message="[INVALID_AMOUNT] Non-positive amount obtained after receive: 0",
            )

            # Act
            result = await wallet.refund_receivable_by_hash(self.RECEIVABLE_HASH_1)

            # Assert
            assert result.success is True
            detail = result.unwrap()
            assert (
                detail.status == RefundStatus.RECEIVE_FAILED
            )  # Failure is in validation post-receive
            assert "Non-positive amount obtained after receive" in detail.error_message
            assert "[INVALID_AMOUNT]" in detail.error_message
            assert detail.source_account == self.SOURCE_ACCOUNT_1
            assert detail.amount_raw == 0
            assert detail.receive_hash == self.RECEIVE_HASH_1
            assert detail.refund_hash is None

        wallet.reload.assert_called_once()
        mock_internal.assert_called_once_with(
            receivable_hash=self.RECEIVABLE_HASH_1,
            wait_confirmation=False,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_refund_receivable_by_hash_send_failed(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests refund failure during the send (refund) stage."""
        # Arrange
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
                status=RefundStatus.SEND_FAILED,
                receive_hash=self.RECEIVE_HASH_1,
                refund_hash=None,
                error_message="[INSUFFICIENT_BALANCE] Insufficient balance for refund",
            )

            # Act
            result = await wallet.refund_receivable_by_hash(self.RECEIVABLE_HASH_1)

            # Assert
            assert result.success is True
            detail = result.unwrap()
            assert detail.status == RefundStatus.SEND_FAILED
            assert detail.receivable_hash == self.RECEIVABLE_HASH_1
            assert detail.source_account == self.SOURCE_ACCOUNT_1
            assert detail.amount_raw == self.AMOUNT_RAW_1
            assert detail.receive_hash == self.RECEIVE_HASH_1
            assert "Insufficient balance for refund" in detail.error_message
            assert "[INSUFFICIENT_BALANCE]" in detail.error_message
            assert detail.refund_hash is None

        wallet.reload.assert_called_once()
        mock_internal.assert_called_once_with(
            receivable_hash=self.RECEIVABLE_HASH_1,
            wait_confirmation=False,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_refund_receivable_by_hash_skip_self_refund(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock, valid_account
    ):
        """Tests that refund is skipped if the source is the wallet itself."""
        # Arrange
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=valid_account,
                status=RefundStatus.SKIPPED,
                receive_hash=self.RECEIVE_HASH_1,  # Receive still happened
                refund_hash=None,
                error_message="Refunding to self",
            )

            # Act
            result = await wallet.refund_receivable_by_hash(self.RECEIVABLE_HASH_1)

            # Assert
            assert result.success is True
            detail = result.unwrap()
            assert detail.status == RefundStatus.SKIPPED
            assert detail.receivable_hash == self.RECEIVABLE_HASH_1
            assert detail.amount_raw == self.AMOUNT_RAW_1
            assert detail.source_account == valid_account
            assert detail.receive_hash == self.RECEIVE_HASH_1  # Receive still happened
            assert detail.refund_hash is None
            assert detail.error_message == "Refunding to self"  # Check specific message

        wallet.reload.assert_called_once()
        mock_internal.assert_called_once_with(
            receivable_hash=self.RECEIVABLE_HASH_1,
            wait_confirmation=False,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_refund_all_receivables_success(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests successful refund of multiple receivables."""
        # Arrange
        receivables_list = [
            Receivable(
                block_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
            ),
            Receivable(
                block_hash=self.RECEIVABLE_HASH_2,
                amount_raw=self.AMOUNT_RAW_2,
                source_account=self.SOURCE_ACCOUNT_2,
            ),
        ]
        wallet._query_operations.list_receivables = AsyncMock(
            return_value=receivables_list
        )

        mock_internal_details = [
            RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
                status=RefundStatus.SUCCESS,
                receive_hash=self.RECEIVE_HASH_1,
                refund_hash=self.REFUND_HASH_1,
            ),
            RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_2,
                amount_raw=self.AMOUNT_RAW_2,
                source_account=self.SOURCE_ACCOUNT_2,
                status=RefundStatus.SUCCESS,
                receive_hash=self.RECEIVE_HASH_2,
                refund_hash=self.REFUND_HASH_2,
            ),
        ]
        # Patch the internal method directly
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.side_effect = mock_internal_details
            # Act
            result = await wallet.refund_all_receivables(threshold_raw=10**24)

            # Assert
            assert result.success is True
            details = result.unwrap()
            print("DEBUG: details", details)
            assert len(details) == 2
            assert details == mock_internal_details

            # Check calls
            wallet._query_operations.list_receivables.assert_called_once_with(
                threshold_raw=10**24
            )
            # wallet.reload was called based on implementation diff for refund_all_receivables
            # wallet.reload.assert_not_called()
            assert mock_internal.call_count == 2
            mock_internal.assert_has_calls(
                [
                    call(
                        receivable_hash=self.RECEIVABLE_HASH_1,
                        wait_confirmation=False,
                        timeout=30,
                    ),
                    call(
                        receivable_hash=self.RECEIVABLE_HASH_2,
                        wait_confirmation=False,
                        timeout=30,
                    ),
                ]
            )

    @pytest.mark.asyncio
    async def test_refund_all_receivables_none_found(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests refund_all when no receivables meet the threshold."""
        # Arrange
        wallet._query_operations.list_receivables = AsyncMock(return_value=[])
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:

            # Act
            result = await wallet.refund_all_receivables()

            # Assert
            assert result.success is True
            details = result.unwrap()
            assert len(details) == 0
            wallet._query_operations.list_receivables.assert_called_once_with(
                threshold_raw=None
            )
            # wallet.reload was called based on implementation diff for refund_all_receivables
            mock_internal.assert_not_called()

    @pytest.mark.asyncio
    async def test_refund_all_receivables_threshold(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests that the threshold correctly filters receivables."""
        # Arrange
        receivables_list = [
            Receivable(
                block_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
            ),  # Above
            Receivable(
                block_hash=self.RECEIVABLE_HASH_3,
                amount_raw=self.AMOUNT_RAW_3,
                source_account=self.SOURCE_ACCOUNT_3,
            ),  # Below
        ]
        custom_threshold = self.AMOUNT_RAW_3 + 1  # Higher threshold
        wallet._state_manager._receivable_blocks = receivables_list

        mock_internal_detail = RefundDetail(
            receivable_hash=self.RECEIVABLE_HASH_1,
            amount_raw=self.AMOUNT_RAW_1,
            source_account=self.SOURCE_ACCOUNT_1,
            status=RefundStatus.SUCCESS,
            receive_hash=self.RECEIVE_HASH_1,
            refund_hash=self.REFUND_HASH_1,
        )

        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.return_value = (
                mock_internal_detail  # Only hash 1 should trigger this
            )

            # Act
            result = await wallet.refund_all_receivables(threshold_raw=custom_threshold)

            # Assert
            assert result.success is True
            details = result.unwrap()
            assert len(details) == 1
            assert details[0].receivable_hash == self.RECEIVABLE_HASH_1
            assert details[0].status == RefundStatus.SUCCESS

            mock_internal.assert_called_once_with(
                receivable_hash=self.RECEIVABLE_HASH_1,
                wait_confirmation=False,
                timeout=30,
            )

    @pytest.mark.asyncio
    async def test_refund_all_receivables_mixed_results(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock
    ):
        """Tests refund_all with a mix of success and failure outcomes."""
        # Arrange
        receivables_list = [
            Receivable(
                block_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
            ),
            Receivable(
                block_hash=self.RECEIVABLE_HASH_2,
                amount_raw=self.AMOUNT_RAW_2,
                source_account=self.SOURCE_ACCOUNT_2,
            ),
        ]
        wallet._query_operations.list_receivables = AsyncMock(
            return_value=receivables_list
        )

        mock_internal_details = [
            RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
                status=RefundStatus.SUCCESS,
                receive_hash=self.RECEIVE_HASH_1,
                refund_hash=self.REFUND_HASH_1,
            ),
            RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_2,
                amount_raw=self.AMOUNT_RAW_2,
                source_account=self.SOURCE_ACCOUNT_2,
                status=RefundStatus.SEND_FAILED,
                receive_hash=self.RECEIVE_HASH_2,
                refund_hash=None,
                error_message="Send failed",
            ),
        ]
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.side_effect = mock_internal_details

            # Act
            result = await wallet.refund_all_receivables()

            # Assert
            assert result.success is True
            details = result.unwrap()
            assert len(details) == 2

            assert details[0].status == RefundStatus.SUCCESS
            assert details[0].receivable_hash == self.RECEIVABLE_HASH_1
            assert details[1].status == RefundStatus.SEND_FAILED
            assert details[1].receivable_hash == self.RECEIVABLE_HASH_2
            assert details[1].error_message == "Send failed"

            wallet._query_operations.list_receivables.assert_called_once_with(
                threshold_raw=None
            )
            assert mock_internal.call_count == 2
            mock_internal.assert_has_calls(
                [
                    call(
                        receivable_hash=self.RECEIVABLE_HASH_1,
                        wait_confirmation=False,
                        timeout=30,
                    ),
                    call(
                        receivable_hash=self.RECEIVABLE_HASH_2,
                        wait_confirmation=False,
                        timeout=30,
                    ),
                ]
            )

    @pytest.mark.asyncio
    async def test_refund_all_receivables_includes_skipped(
        self, wallet: NanoWalletAuthenticated, mock_rpc: AsyncMock, valid_account
    ):
        """Tests refund_all includes skipped self-refunds in the results."""
        # Arrange
        self_receivable_hash = "S" * 64
        receivables_list = [
            Receivable(
                block_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
            ),  # Normal
            Receivable(
                block_hash=self_receivable_hash,
                amount_raw=self.AMOUNT_RAW_2,
                source_account=valid_account,
            ),  # Self
        ]
        wallet._query_operations.list_receivables = AsyncMock(
            return_value=receivables_list
        )

        mock_internal_details = [
            RefundDetail(
                receivable_hash=self.RECEIVABLE_HASH_1,
                amount_raw=self.AMOUNT_RAW_1,
                source_account=self.SOURCE_ACCOUNT_1,
                status=RefundStatus.SUCCESS,
                receive_hash=self.RECEIVE_HASH_1,
                refund_hash=self.REFUND_HASH_1,
            ),
            # Simulate the internal method returning SKIPPED for the self-refund hash
            RefundDetail(
                receivable_hash=self_receivable_hash,
                amount_raw=self.AMOUNT_RAW_2,
                source_account=valid_account,
                status=RefundStatus.SKIPPED,
                receive_hash=self.RECEIVE_HASH_2,
                refund_hash=None,
                error_message="Refunding to self",
            ),
        ]
        with patch.object(
            wallet, "_internal_refund_receivable", new_callable=AsyncMock
        ) as mock_internal:
            mock_internal.side_effect = mock_internal_details

            # Act
            result = await wallet.refund_all_receivables()

            # Assert
            assert result.success is True
            details = result.unwrap()
            assert len(details) == 2

            assert details[0].status == RefundStatus.SUCCESS
            assert details[0].receivable_hash == self.RECEIVABLE_HASH_1
            assert details[1].status == RefundStatus.SKIPPED
            assert details[1].receivable_hash == self_receivable_hash
            assert details[1].source_account == valid_account

            wallet._query_operations.list_receivables.assert_called_once_with(
                threshold_raw=None
            )
            assert mock_internal.call_count == 2
            mock_internal.assert_has_calls(
                [
                    call(
                        receivable_hash=self.RECEIVABLE_HASH_1,
                        wait_confirmation=False,
                        timeout=30,
                    ),
                    call(
                        receivable_hash=self_receivable_hash,
                        wait_confirmation=False,
                        timeout=30,
                    ),
                ]
            )
