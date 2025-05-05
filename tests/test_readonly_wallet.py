import pytest
from unittest.mock import AsyncMock, patch, Mock
import asyncio
from decimal import Decimal

from nanowallet.wallets.read_only_impl import NanoWalletReadOnly
from nanowallet.libs.rpc import INanoRpc
from nanowallet.errors import InvalidAccountError, NanoException
from nanowallet.models import (
    WalletConfig,
    WalletBalance,
    AccountInfo,
    Receivable,
    Transaction,
)
from nanowallet.utils.decorators import NanoResult


@pytest.fixture
def valid_account():
    return "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s"


@pytest.fixture
def invalid_account():
    return "not_a_valid_nano_account"


@pytest.fixture
def mock_rpc():
    """Fixture that provides a mocked RPC client instance"""
    mock = AsyncMock(spec=INanoRpc)
    return mock


@pytest.fixture
def dummy_account_info():
    return {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "10000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "42",
        "block_count": "50",
        "account_version": "1",
        "weight": "5000000000000000000000000000000",
        "receivable": "2000000000000000000000000000000",
    }


class TestNanoWalletReadOnly:
    """Tests for the NanoWalletReadOnly class."""

    @pytest.mark.asyncio
    async def test_init_valid_account(self, mock_rpc, valid_account):
        """Test initialization with a valid account."""
        wallet = NanoWalletReadOnly(mock_rpc, valid_account)

        assert wallet.account == valid_account
        assert wallet._rpc_component.rpc == mock_rpc
        assert isinstance(wallet.config, WalletConfig)

        # Verify initial state
        assert wallet._state_manager.balance_info.balance_raw == 0
        assert wallet._state_manager.balance_info.receivable_raw == 0
        assert wallet._state_manager.account_info.account == valid_account
        assert wallet._state_manager.account_info.frontier_block is None
        assert wallet._state_manager.receivable_blocks == []

    def test_init_invalid_account(self, mock_rpc, invalid_account):
        """Test initialization with an invalid account raises an exception."""
        with pytest.raises(InvalidAccountError):
            NanoWalletReadOnly(mock_rpc, invalid_account)

    def test_init_with_config(self, mock_rpc, valid_account):
        """Test initialization with a custom config."""
        custom_config = WalletConfig(
            default_representative="nano_1custom9representative99address9goes9here",
            use_work_peers=True,
        )
        wallet = NanoWalletReadOnly(mock_rpc, valid_account, config=custom_config)

        assert wallet.config == custom_config
        assert (
            wallet.config.default_representative
            == "nano_1custom9representative99address9goes9here"
        )
        assert wallet.config.use_work_peers is True

    @pytest.mark.asyncio
    async def test_reload_account_exists(
        self, mock_rpc, valid_account, dummy_account_info
    ):
        """Test reload when account exists on the network."""
        mock_rpc.account_info.return_value = dummy_account_info
        mock_rpc.receivable.return_value = {
            "blocks": {
                "block1": {
                    "amount": "1000000000000000000000000000000",
                    "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
                }
            }
        }

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        await wallet.reload()

        # Verify reloaded state
        assert (
            wallet._state_manager.balance_info.balance_raw
            == 10000000000000000000000000000000
        )
        # Receivable amount calculated from blocks takes precedence over account_info call
        # account_info RPC call does not include receivable amount for unopened accounts
        assert (
            wallet._state_manager.balance_info.receivable_raw
            == 1000000000000000000000000000000
        )
        assert (
            wallet._state_manager.account_info.frontier_block
            == "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78"
        )
        assert (
            wallet._state_manager.account_info.representative
            == "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf"
        )
        assert wallet._state_manager.account_info.confirmation_height == 42
        assert wallet._state_manager.account_info.block_count == 50
        assert (
            wallet._state_manager.account_info.weight_raw
            == 5000000000000000000000000000000
        )
        assert wallet._state_manager.receivable_blocks == [
            Receivable(
                block_hash="block1",
                amount_raw=1000000000000000000000000000000,
                source_account="nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
            )
        ]

    @pytest.mark.asyncio
    async def test_reload_account_not_found(self, mock_rpc, valid_account):
        """Test reload when account doesn't exist but has receivables."""
        mock_rpc.account_info.return_value = {"error": "Account not found"}
        mock_rpc.receivable.return_value = {
            "blocks": {
                "block1": {
                    "amount": "1000000000000000000000000000000",
                    "source": "nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
                },
                "block2": {
                    "amount": "2000000000000000000000000000000",
                    "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
                },
            }
        }

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        await wallet.reload()

        # Verify state for non-existent account with receivables
        assert wallet._state_manager.balance_info.balance_raw == 0
        assert (
            wallet._state_manager.balance_info.receivable_raw
            == 3000000000000000000000000000000
        )
        assert wallet._state_manager.account_info.frontier_block is None
        assert wallet._state_manager.account_info.representative is None
        assert wallet._state_manager.receivable_blocks == [
            Receivable(
                block_hash="block1",
                amount_raw=1000000000000000000000000000000,
                source_account="nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
            ),
            Receivable(
                block_hash="block2",
                amount_raw=2000000000000000000000000000000,
                source_account="nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
            ),
        ]

    @pytest.mark.asyncio
    async def test_reload_account_not_found_no_receivables(
        self, mock_rpc, valid_account
    ):
        """Test reload when account doesn't exist and has no receivables."""
        mock_rpc.account_info.return_value = {"error": "Account not found"}
        mock_rpc.receivable.return_value = {"blocks": ""}

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        await wallet.reload()

        # Verify default state
        assert wallet._state_manager.balance_info.balance_raw == 0
        assert wallet._state_manager.balance_info.receivable_raw == 0
        assert wallet._state_manager.account_info.frontier_block is None
        assert wallet._state_manager.account_info.representative is None
        assert wallet._state_manager.receivable_blocks == []

    @pytest.mark.asyncio
    async def test_reload_error_handling(self, mock_rpc, valid_account):
        """Test error handling during reload."""
        # Mock receivable to raise an exception, which should be caught by handle_errors
        mock_rpc.receivable.side_effect = Exception("RPC Error")

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        result = await wallet.reload()

        # NanoResult is successful but logs the error (check the logs)
        # This is because handle_errors decorator returns success=True
        # even when there are errors, and it logs the exception
        assert isinstance(result, NanoResult)
        assert result.success == False
        assert "Failed to fetch receivables: RPC Error" in result.error
        assert result.error_code == "RELOAD_ERROR"

    @pytest.mark.asyncio
    async def test_has_balance_with_balance(
        self, mock_rpc, valid_account, dummy_account_info
    ):
        """Test has_balance when account has balance."""
        mock_rpc.account_info.return_value = dummy_account_info
        mock_rpc.receivable.return_value = {"blocks": ""}

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)

        # Manually update state via state_manager
        wallet._state_manager._balance_info.balance_raw = (
            10000000000000000000000000000000
        )
        wallet._state_manager._balance_info.receivable_raw = 0

        result = await wallet.has_balance()
        assert result.success is True
        assert result.unwrap() is True

    @pytest.mark.asyncio
    async def test_has_balance_with_receivable(self, mock_rpc, valid_account):
        """Test has_balance when account has only receivable."""
        mock_rpc.account_info.return_value = {"error": "Account not found"}
        mock_rpc.receivable.return_value = {
            "blocks": {
                "block1": {
                    "amount": "1000000000000000000000000000000",
                    "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
                }
            }
        }

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)

        # Manually update state via state_manager
        wallet._state_manager._balance_info.receivable_raw = (
            1000000000000000000000000000000
        )

        result = await wallet.has_balance()
        assert result.success is True
        assert result.unwrap() is True

    @pytest.mark.asyncio
    async def test_has_balance_no_balance(self, mock_rpc, valid_account):
        """Test has_balance when account has no balance and no receivable."""
        mock_rpc.account_info.return_value = {"error": "Account not found"}
        mock_rpc.receivable.return_value = {"blocks": {}}

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        result = await wallet.has_balance()
        assert result.success is True
        assert result.unwrap() is False

    @pytest.mark.asyncio
    async def test_balance_info(self, mock_rpc, valid_account, dummy_account_info):
        """Test balance_info method."""
        mock_rpc.account_info.return_value = dummy_account_info
        mock_rpc.receivable.return_value = {"blocks": {}}

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        await wallet.reload()
        result = await wallet.balance_info()

        assert isinstance(result, NanoResult)
        assert result.success is True

        balance_info = result.unwrap()
        assert isinstance(balance_info, WalletBalance)
        assert balance_info.balance_raw == 10000000000000000000000000000000
        assert balance_info.receivable_raw == 2000000000000000000000000000000
        assert balance_info.balance == Decimal("10")
        assert balance_info.receivable == Decimal("2")

    @pytest.mark.asyncio
    async def test_account_info(self, mock_rpc, valid_account, dummy_account_info):
        """Test account_info method."""
        mock_rpc.account_info.return_value = dummy_account_info
        mock_rpc.receivable.return_value = {"blocks": {}}

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        await wallet.reload()
        result = await wallet.account_info()

        assert isinstance(result, NanoResult)
        assert result.success is True

        account_info = result.unwrap()
        assert isinstance(account_info, AccountInfo)
        assert account_info.account == valid_account
        assert (
            account_info.frontier_block
            == "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78"
        )
        assert (
            account_info.representative
            == "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf"
        )
        assert account_info.confirmation_height == 42
        assert account_info.block_count == 50
        assert account_info.weight_raw == 5000000000000000000000000000000
        assert account_info.weight == Decimal("5")

    @pytest.mark.asyncio
    async def test_list_receivables(self, mock_rpc, valid_account):
        """Test list_receivables method."""
        mock_rpc.account_info.return_value = {"error": "Account not found"}
        mock_rpc.receivable.return_value = {
            "blocks": {
                "block1": {
                    "amount": "2000000000000000000000000000000",
                    "source": "nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
                },
                "block2": {
                    "amount": "1000000000000000000000000000000",
                    "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
                },
                "block3": {
                    "amount": "500000000000000000000000000000",
                    "source": "nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
                },
                "block4": {
                    "amount": "100000000000000000000000000",
                    "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
                },
            }
        }

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        await wallet.reload()

        # Create a custom threshold of 500000000000000000000000000000 (0.5 Nano)
        custom_threshold = 500000000000000000000000000000
        result = await wallet.list_receivables(threshold_raw=custom_threshold)

        assert isinstance(result, NanoResult)
        assert result.success is True

        receivables = result.unwrap()

        # We should see 3 receivables above 0.5 Nano
        assert len(receivables) == 3

        # Verify they're sorted in descending order
        assert receivables[0].block_hash == "block1"  # 2 Nano
        assert receivables[1].block_hash == "block2"  # 1 Nano
        assert receivables[2].block_hash == "block3"  # 0.5 Nano

        # Verify sorting by amount
        assert receivables[0].amount_raw > receivables[1].amount_raw
        assert receivables[1].amount_raw > receivables[2].amount_raw

    @pytest.mark.asyncio
    async def test_list_receivables_no_receivables(self, mock_rpc, valid_account):
        """Test list_receivables method with no receivables."""
        mock_rpc.account_info.return_value = {"error": "Account not found"}
        mock_rpc.receivable.return_value = {"blocks": {}}

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        result = await wallet.list_receivables()

        assert isinstance(result, NanoResult)
        assert result.success is True
        receivables = result.unwrap()

        assert isinstance(receivables, list)
        assert len(receivables) == 0

    @pytest.mark.asyncio
    async def test_account_history(self, mock_rpc, valid_account):
        """Test account_history method."""
        # Use valid public key hex values for the links
        source_public_key = (
            "0000000000000000000000000000000000000000000000000000000000000001"
        )
        dest_public_key = (
            "0000000000000000000000000000000000000000000000000000000000000002"
        )

        mock_response = {
            "account": valid_account,
            "history": [
                {
                    "account": "nano_1sender1address1here1iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii",
                    "amount": "2000000000000000000000000000000",
                    "balance": "12000000000000000000000000000000",
                    "confirmed": "true",
                    "hash": "block_hash_1",
                    "height": "42",
                    "link": source_public_key,  # Valid 64-char hex for receive
                    "local_timestamp": "1612345678",
                    "previous": "previous_hash_1",
                    "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
                    "signature": "signature_1",
                    "subtype": "receive",
                    "type": "state",
                    "work": "work_1",
                },
                {
                    "account": "nano_1receiver1address1here1iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii",
                    "amount": "1000000000000000000000000000000",
                    "balance": "10000000000000000000000000000000",
                    "confirmed": "true",
                    "hash": "block_hash_2",
                    "height": "41",
                    "link": dest_public_key,  # Valid 64-char hex for send
                    "local_timestamp": "1612345600",
                    "previous": "previous_hash_2",
                    "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
                    "signature": "signature_2",
                    "subtype": "send",
                    "type": "state",
                    "work": "work_2",
                },
            ],
        }

        mock_rpc.account_history.return_value = mock_response

        # Mock the AccountHelper.get_account method to return predictable values
        with patch("nanowallet.models.AccountHelper.get_account") as mock_get_account:
            # When called with the destination public key, return a specific address
            mock_get_account.return_value = (
                "nano_1receiver1address1here1iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"
            )

            wallet = NanoWalletReadOnly(mock_rpc, valid_account)
            result = await wallet.account_history(count=2)

            assert isinstance(result, NanoResult)
            assert result.success is True

            transactions = result.unwrap()

            assert len(transactions) == 2
            assert isinstance(transactions[0], Transaction)

            # Check first transaction (receive)
            assert transactions[0].block_hash == "block_hash_1"
            assert transactions[0].subtype == "receive"
            assert transactions[0].amount_raw == 2000000000000000000000000000000
            assert transactions[0].amount == Decimal("2")

            # Check second transaction (send)
            assert transactions[1].block_hash == "block_hash_2"
            assert transactions[1].subtype == "send"
            assert transactions[1].amount_raw == 1000000000000000000000000000000
            assert transactions[1].amount == Decimal("1")

            # Verify destination is correctly determined
            # The mock will return our predefined value
            assert (
                transactions[1].destination
                == "nano_1receiver1address1here1iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"
            )

    @pytest.mark.asyncio
    async def test_account_history_account_not_found(self, mock_rpc, valid_account):
        """Test account_history when account doesn't exist."""
        mock_rpc.account_history.return_value = {"error": "Account not found"}

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        result = await wallet.account_history()

        assert isinstance(result, NanoResult)
        assert result.success is True

        transactions = result.unwrap()
        assert isinstance(transactions, list)
        assert len(transactions) == 0

    @pytest.mark.asyncio
    async def test_account_history_with_head(self, mock_rpc, valid_account):
        """Test account_history with custom head parameter."""
        # Simple mock to verify head parameter is passed correctly
        mock_rpc.account_history.return_value = {"history": []}

        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        await wallet.account_history(head="custom_head_hash")

        # Verify head parameter was passed to RPC call
        mock_rpc.account_history.assert_called_with(
            account=valid_account, count=-1, raw=True, head="custom_head_hash"
        )

    def test_to_string(self, mock_rpc, valid_account, dummy_account_info):
        """Test to_string method."""
        # Create wallet with predefined state for consistent output
        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        wallet._state_manager._balance_info.balance_raw = (
            10000000000000000000000000000000  # 10 Nano
        )
        wallet._state_manager._balance_info.receivable_raw = (
            2000000000000000000000000000000  # 2 Nano
        )
        wallet._state_manager._account_info.weight_raw = (
            5000000000000000000000000000000  # 5 Nano
        )
        wallet._state_manager._account_info.representative = (
            "nano_1representative1address1here1iiiiiiiiiiiiiiiiiiiiiiiiiiii"
        )
        wallet._state_manager._account_info.confirmation_height = 42
        wallet._state_manager._account_info.block_count = 50

        string_output = wallet.to_string()

        # Check that important wallet data is included in the string representation
        assert valid_account in string_output
        assert "Balance: 10 Nano" in string_output
        assert "Receivable: 2 Nano" in string_output
        assert "Voting Weight: 5 Nano" in string_output
        assert "Confirmation Height: 42" in string_output
        assert "Block Count: 50" in string_output

    def test_str_representation(self, mock_rpc, valid_account):
        """Test __str__ method."""
        wallet = NanoWalletReadOnly(mock_rpc, valid_account)
        wallet._state_manager._balance_info.balance_raw = (
            10000000000000000000000000000000  # 10 Nano
        )
        wallet._state_manager._balance_info.receivable_raw = (
            2000000000000000000000000000000  # 2 Nano
        )

        str_output = str(wallet)

        # Check that the string representation contains the account and balances
        assert "NanoWalletReadOnly" in str_output
        assert valid_account in str_output
        assert "BalanceRaw=10000000000000000000000000000000" in str_output
        assert "ReceivableRaw=2000000000000000000000000000000" in str_output

    def test_verify_no_active_methods(self, mock_rpc, valid_account):
        """Verify that the read-only wallet doesn't have active methods like send, receive."""
        wallet = NanoWalletReadOnly(mock_rpc, valid_account)

        # These methods should not exist in the read-only wallet
        assert not hasattr(wallet, "send")
        assert not hasattr(wallet, "send_raw")
        assert not hasattr(wallet, "receive_by_hash")
        assert not hasattr(wallet, "receive_all")
        assert not hasattr(wallet, "sweep")
        assert not hasattr(wallet, "refund_first_sender")
