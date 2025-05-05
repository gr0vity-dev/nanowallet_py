import pytest
from unittest.mock import patch, Mock
import asyncio

from nanowallet.wallets import NanoWalletRpc
from nanowallet.wallets import NanoWalletAuthenticated
from nanorpc.client import NanoRpcTyped
from nanowallet.wallets.wallet_factory import create_wallet_from_seed

from nanowallet.utils.decorators import NanoResult, handle_errors, reload_after
from nanowallet.errors import NanoException, InvalidAccountError, InvalidAmountError
from decimal import Decimal
from nanowallet.utils.conversion import raw_to_nano, nano_to_raw
from nanowallet.utils.amount_operations import sum_received_amount
from nanowallet.models import *
import logging


@pytest.fixture
def seed():
    return "b632a26208f2f5f36871b4ae952c2f81415728e0ab402c7d7e995f586bef5fd6"


@pytest.fixture
def index():
    return 0


@pytest.fixture
def account():
    return "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s"


@pytest.fixture
def private_key():
    return "0efa90463f5397f0c4e09c6c2a4a423cf34bd5ff9d14368201225e0e672193e7"


@pytest.fixture
def dummy_account_info():
    return {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "10",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "10",
        "receivable": "10",
    }


@pytest.fixture
def mock_rpc_typed():
    """Fixture that provides a mocked NanoRpcTyped instance"""
    mock = Mock(spec=NanoRpcTyped)
    mock.account_info.return_value = {}  # Empty dict to supress warnings
    mock.receivable.return_value = {}  # Empty dict to supress warnings
    mock.blocks_info.return_value = {}  # Empty dict to supress warnings
    mock.work_generate.return_value = {}  # Empty dict to supress warnings
    mock.process.return_value = {}  # Empty dict to supress warnings
    mock.account_history.return_value = {}  # Empty dict to supress warnings
    return mock


@pytest.fixture
def mock_rpc(mock_rpc_typed):

    rpc = NanoWalletRpc(url="mock://test")
    # Only mock the underlying _rpc, not the wrapper methods
    rpc._rpc = mock_rpc_typed
    return rpc


@pytest.mark.asyncio
async def test_init(mock_rpc, seed, index, account, private_key):

    wallet = create_wallet_from_seed(mock_rpc, seed, index)

    assert wallet.account == account
    assert wallet.private_key == private_key


@pytest.mark.asyncio
async def test_reload(mock_rpc, mock_rpc_typed, seed, index):

    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            "11F170F6BEAC5734A6CEBBFB447EB6A3524F6B4CCCB6FC5F51DEE82BE4B57151": {
                "amount": "1000000000000000000000000000000",
                "source": "nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
            }
        }
    }

    mock_rpc_typed.account_info.return_value = {
        "frontier": "frontier_block",
        "open_block": "open_block",
        "representative_block": "representative_block",
        "balance": "2000000000000000000000000000000",
        "modified_timestamp": "1611868227",
        "block_count": "50",
        "account_version": "1",
        "confirmation_height": "40",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }
    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}
    mock_rpc_typed.blocks_info.return_value = {}
    mock_rpc_typed.account_history.return_value = {}

    wallet = create_wallet_from_seed(mock_rpc_typed, seed, index)
    wallet_info_response = await wallet.account_info()

    balance_info_response = await wallet.balance_info()
    wallet_info: AccountInfo = wallet_info_response.unwrap()
    print("WALLET INFO RESPONSE", wallet_info)
    balance_info: WalletBalance = balance_info_response.unwrap()

    assert balance_info.balance == 2
    assert balance_info.balance_raw == 2000000000000000000000000000000
    assert balance_info.receivable == 1
    assert balance_info.receivable_raw == 1000000000000000000000000000000

    assert wallet_info.frontier_block == "frontier_block"
    assert wallet_info.representative_block == "representative_block"
    assert (
        wallet_info.representative
        == "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf"
    )
    assert wallet_info.open_block == "open_block"
    assert wallet_info.confirmation_height == 40
    assert wallet_info.block_count == 50
    assert wallet_info.weight == 3
    assert wallet_info.weight_raw == 3000000000000000000000000000000


@pytest.mark.asyncio
async def test_reload_unopened(mock_rpc, mock_rpc_typed, seed, index):

    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            "b1": {
                "amount": "1000000000000000000000000000000",
                "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
            },
            "b2": {
                "amount": "1",
                "source": "nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
            },
            "b3": {
                "amount": "3000000000000000000000000000000",
                "source": "nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
            },
        }
    }
    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    await wallet.reload()

    assert wallet._state_manager.balance_info.balance == 0
    assert wallet._state_manager.balance_info.balance_raw == 0
    assert wallet._state_manager.account_info.frontier_block == None
    assert wallet._state_manager.account_info.representative_block == None
    assert wallet._state_manager.account_info.representative == None
    assert wallet._state_manager.account_info.open_block == None
    assert wallet._state_manager.account_info.confirmation_height == 0
    assert wallet._state_manager.account_info.block_count == 0
    assert wallet._state_manager.account_info.weight == 0
    assert wallet._state_manager.account_info.weight_raw == 0
    assert wallet._state_manager.balance_info.receivable == Decimal(
        "4.000000000000000000000000000001"
    )
    assert (
        wallet._state_manager.balance_info.receivable_raw
        == 4000000000000000000000000000001
    )
    assert wallet._state_manager.receivable_blocks == [
        Receivable(
            block_hash="b1",
            amount_raw=1000000000000000000000000000000,
            source_account="nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
        ),
        Receivable(
            block_hash="b2",
            amount_raw=1,
            source_account="nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
        ),
        Receivable(
            block_hash="b3",
            amount_raw=3000000000000000000000000000000,
            source_account="nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
        ),
    ]


@pytest.mark.asyncio
async def test_reload_unopened_2(mock_rpc, mock_rpc_typed, seed, index):

    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            "b1": {
                "amount": "1000000000000000000000000000123",
                "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
            }
        }
    }
    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    await wallet.reload()
    await wallet.reload()

    assert (
        wallet._state_manager.balance_info.receivable_raw
        == 1000000000000000000000000000123
    )
    assert wallet._state_manager.receivable_blocks == [
        Receivable(
            block_hash="b1",
            amount_raw=1000000000000000000000000000123,
            source_account="nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
        )
    ]


@pytest.mark.asyncio
async def test_reload_unopen_no_receivables(mock_rpc, mock_rpc_typed, seed, index):

    mock_rpc_typed.receivable.return_value = {"blocks": ""}
    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}

    wallet = create_wallet_from_seed(mock_rpc_typed, seed, index)
    await wallet.reload()

    assert wallet._state_manager.balance_info.balance == 0
    assert wallet._state_manager.balance_info.balance_raw == 0
    assert wallet._state_manager.account_info.frontier_block == None
    assert wallet._state_manager.account_info.representative_block == None
    assert wallet._state_manager.account_info.representative == None
    assert wallet._state_manager.account_info.open_block == None
    assert wallet._state_manager.account_info.confirmation_height == 0
    assert wallet._state_manager.account_info.block_count == 0
    assert wallet._state_manager.account_info.weight == 0
    assert wallet._state_manager.account_info.weight_raw == 0
    assert wallet._state_manager.balance_info.receivable == 0
    assert wallet._state_manager.balance_info.receivable_raw == 0
    assert wallet._state_manager.receivable_blocks == []


@pytest.mark.asyncio
async def test_reload_no_receivables(mock_rpc, mock_rpc_typed, seed, index):
    mock_rpc_typed.receivable.return_value = {"blocks": ""}
    mock_rpc_typed.account_info.return_value = {
        "frontier": "frontier_block",
        "open_block": "open_block",
        "representative_block": "representative_block",
        "balance": "2000000000000000000000000000000",
        "modified_timestamp": "1611868227",
        "block_count": "50",
        "account_version": "1",
        "confirmation_height": "40",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    await wallet.reload()

    assert wallet._state_manager.balance_info.balance == 2
    assert (
        wallet._state_manager.balance_info.balance_raw
        == 2000000000000000000000000000000
    )
    assert wallet._state_manager.account_info.frontier_block == "frontier_block"
    assert (
        wallet._state_manager.account_info.representative_block
        == "representative_block"
    )
    assert (
        wallet._state_manager.account_info.representative
        == "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf"
    )
    assert wallet._state_manager.account_info.open_block == "open_block"
    assert wallet._state_manager.account_info.confirmation_height == 40
    assert wallet._state_manager.account_info.block_count == 50
    assert wallet._state_manager.account_info.weight == 3
    assert (
        wallet._state_manager.account_info.weight_raw == 3000000000000000000000000000000
    )
    assert wallet._state_manager.balance_info.receivable == 1
    assert (
        wallet._state_manager.balance_info.receivable_raw
        == 1000000000000000000000000000000
    )


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_send_with_confirmation(
    mock_block, mock_rpc_typed, mock_rpc, seed, index
):

    received_block_1 = "c" * 64

    mock_rpc_typed.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }
    mock_rpc_typed.work_generate.return_value = {"work": "000000000000000a"}
    mock_rpc_typed.process.side_effect = [
        {"hash": received_block_1},  # First call succeeds
    ]

    def blocks_info_side_effect(hashes, **kwargs):
        responses = {
            received_block_1: {"confirmed": "false", "contents": {}},
            received_block_1: {"confirmed": "false", "contents": {}},
            received_block_1: {"confirmed": "true", "contents": {}},
        }
        return {"blocks": {hash: responses[hash] for hash in hashes}}

    mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.send(
        "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s",
        1,
        wait_confirmation=True,
    )
    assert result.success == True
    assert result.value == received_block_1
    mock_block.assert_called()
    mock_rpc_typed.process.assert_called()


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_send_with_no_confirmation_timeout(
    mock_block, mock_rpc_typed, mock_rpc, seed, index
):

    received_block_1 = "c" * 64

    mock_rpc_typed.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }
    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.side_effect = [
        {"hash": received_block_1},  # First call succeeds
    ]

    def blocks_info_side_effect(hashes, **kwargs):
        responses = {
            received_block_1: {"confirmed": "false", "contents": {}},
            received_block_1: {"confirmed": "false", "contents": {}},
            received_block_1: {"confirmed": "false", "contents": {}},
        }
        return {"blocks": {hash: responses[hash] for hash in hashes}}

    mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.send(
        "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s",
        1,
        wait_confirmation=True,
        timeout=0.1,
    )

    assert result.success == False
    assert result.value == None
    mock_rpc_typed.process.assert_called()


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_send(mock_block, mock_rpc_typed, mock_rpc, seed, index):

    mock_rpc_typed.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }
    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.side_effect = [{"hash": "processed_block_hash"}]

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.send(
        "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s",
        1,
    )

    assert result.success == True
    assert result.value == "processed_block_hash"
    mock_block.assert_called()
    mock_rpc_typed.process.assert_called()


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_send_raw(mock_block, mock_rpc, mock_rpc_typed, seed, index):

    mock_rpc_typed.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }
    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.send_raw(
        "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s", 1e30
    )

    assert result.success == True
    assert result.value == "processed_block_hash"
    mock_block.assert_called()
    mock_rpc_typed.process.assert_called()


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_send_raw_below_min_send_amount(
    mock_block, mock_rpc, mock_rpc_typed, seed, index
):

    mock_rpc_typed.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }
    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}

    wallet_config = WalletConfig(min_send_amount_raw=10**30)
    wallet = create_wallet_from_seed(mock_rpc, seed, index, wallet_config)
    result = await wallet.send_raw(
        "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s",
        10**29,
    )

    assert result.success == False
    assert result.value == None
    mock_block.assert_not_called()
    mock_rpc_typed.process.assert_not_called()

    result = await wallet.send(
        "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s", "0.99"
    )
    assert result.success == False
    assert result.value == None
    mock_block.assert_not_called()
    mock_rpc_typed.process.assert_not_called()


@pytest.mark.asyncio
async def test_send_raw_error(mock_rpc, mock_rpc_typed, seed, index):

    mock_rpc_typed.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }
    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.send_raw(
        "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s",
        1000000000000000000000000000000,
    )

    assert result.success == False
    assert (
        result.error
        == "Insufficient balance for send! Current balance: 2000 raw, trying to send: 1000000000000000000000000000000 raw"
    )


@pytest.mark.asyncio
async def test_list_receivables(
    mock_rpc, mock_rpc_typed, seed, index, dummy_account_info
):

    mock_rpc_typed.account_info.return_value = dummy_account_info

    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            "block1": {
                "amount": "2000000000000000000000000000000",
                "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
            },
            "block2": {
                "amount": "1000000000000000000000000000000",
                "source": "nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
            },
        }
    }

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.list_receivables()

    expected = [
        Receivable(
            block_hash="block1",
            amount_raw=2000000000000000000000000000000,
            source_account="nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
        ),
        Receivable(
            block_hash="block2",
            amount_raw=1000000000000000000000000000000,
            source_account="nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
        ),
    ]

    assert result.value[0].amount == 2
    assert result.value[1].amount == 1
    assert result.success == True
    assert result.value == expected


@pytest.mark.asyncio
async def test_list_receivables_none(mock_rpc, mock_rpc_typed, seed, index):

    mock_rpc_typed.receivable.return_value = {"blocks": ""}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    await wallet.reload()
    result = await wallet.list_receivables()

    expected = []
    assert result.success == True
    assert result.value == expected


@pytest.mark.asyncio
async def test_list_receivables_threshold(
    mock_rpc, mock_rpc_typed, seed, index, dummy_account_info
):

    mock_rpc_typed.account_info.return_value = dummy_account_info
    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            "block1": {
                "amount": "2000000000000000000000000000000",
                "source": "nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
            },
            "block2": {
                "amount": "1000000000000000000000000000000",
                "source": "nano_1xo4zftmuhihhmrc6szair5fjpmd71jwiu66yjmguxhshih7fnuth8bc63y6",
            },
        }
    }

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    await wallet.reload()
    result = await wallet.list_receivables(
        threshold_raw=1000000000000000000000000000001
    )

    expected = [
        Receivable(
            block_hash="block1",
            amount_raw=2000000000000000000000000000000,
            source_account="nano_1otqmatyh3f8ykkq1nkjy198unzw1js9c7ehyjc1346um7dnoskto7w7woiw",
        ),
    ]
    assert result.success == True
    assert result.value == expected


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_receive_by_hash(mock_block, mock_rpc_typed, mock_rpc, seed, index):

    mock_rpc_typed.blocks_info.return_value = {
        "blocks": {
            "block_hash_to_receive": {
                "amount": "5",
                "source_account": "0",
                "block_account": "source_account1",
                "subtype": "send",
            }
        }
    }
    mock_rpc_typed.account_info.return_value = {
        "frontier": "frontier_block",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "1000000000000000000000000000000",
    }
    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.receive_by_hash(
        "block_hash_to_receive", wait_confirmation=False
    )

    assert result.success == True
    assert result.value == ReceivedBlock(
        block_hash="processed_block_hash",
        amount_raw=5,
        source="source_account1",
        confirmed=False,
    )

    mock_block.assert_called()
    mock_rpc_typed.process.assert_called()


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_receive_by_hash_wait_conf(
    mock_block, mock_rpc_typed, mock_rpc, seed, index
):
    # Mock initial block info for receiving

    mock_rpc_typed.blocks_info.side_effect = [
        # First call - for the block to receive
        {
            "blocks": {
                "block_hash_to_receive": {
                    "amount": "5",
                    "source_account": "0",
                    "block_account": "source_account1",
                    "subtype": "send",
                }
            }
        },
        # Second call - for confirmation check
        {"blocks": {"processed_block_hash": {"confirmed": "true", "contents": {}}}},
    ]

    mock_rpc_typed.account_info.return_value = {
        "frontier": "frontier_block",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "1000000000000000000000000000000",
        "representative_block": "representative_block",
    }

    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.receive_by_hash("block_hash_to_receive")

    assert result.success == True

    assert result.value == ReceivedBlock(
        block_hash="processed_block_hash",
        amount_raw=5,
        source="source_account1",
        confirmed=True,
    )
    assert result.value.amount == Decimal("5E-30")

    # Verify the expected calls
    mock_block.assert_called()
    mock_rpc_typed.process.assert_called()

    # Verify blocks_info was called for both receiving and confirmation
    assert mock_rpc_typed.blocks_info.call_count == 2
    mock_rpc_typed.blocks_info.assert_any_call(
        ["block_hash_to_receive"], source=True, receive_hash=True, json_block=True
    )
    mock_rpc_typed.blocks_info.assert_any_call(
        ["processed_block_hash"], source=True, receive_hash=True, json_block=True
    )


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_receive_by_hash_new_account(
    mock_block, mock_rpc_typed, mock_rpc, seed, index
):

    mock_rpc_typed.blocks_info.return_value = {
        "blocks": {
            "block_hash_to_receive": {
                "amount": "5000",
                "source_account": "0",
                "block_account": "source_account1",
                "subtype": "send",
            }
        }
    }
    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}
    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.receive_by_hash(
        "block_hash_to_receive", wait_confirmation=False
    )

    assert result.success == True
    assert result.value == ReceivedBlock(
        block_hash="processed_block_hash",
        amount_raw=5000,
        source="source_account1",
        confirmed=False,
    )

    assert result.value.amount == Decimal("5E-27")
    mock_block.assert_called()
    mock_rpc_typed.process.assert_called()


@pytest.mark.asyncio
@patch("nanowallet.wallets.components.block_operations.NanoWalletBlock")
async def test_receive_by_hash_new_account_with_conf(
    mock_block, mock_rpc_typed, mock_rpc, seed, index
):
    # Mock initial block info for receiving, and subsequent confirmation check
    mock_rpc_typed.blocks_info.side_effect = [
        # First call - for the block to receive
        {
            "blocks": {
                "block_hash_to_receive": {
                    "amount": "5000",
                    "source_account": "0",
                    "block_account": "source_account1",
                    "subtype": "send",
                }
            }
        },
        # Second call - for confirmation check
        {"blocks": {"processed_block_hash": {"confirmed": "true", "contents": {}}}},
    ]

    # First call returns account not found, subsequent calls after receiving should return account info
    mock_rpc_typed.account_info.side_effect = [
        # First call - account doesn't exist yet
        {"error": "Account not found"},
        # Subsequent calls after receive
        {
            "frontier": "processed_block_hash",
            "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
            "balance": "5000",
            "representative_block": "processed_block_hash",
        },
    ]

    mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    # Default wait_confirmation=True
    result = await wallet.receive_by_hash("block_hash_to_receive")

    assert result.success == True
    assert result.value == ReceivedBlock(
        block_hash="processed_block_hash",
        amount_raw=5000,
        source="source_account1",
        confirmed=True,
    )
    assert result.value.amount == Decimal("5E-27")

    # Verify the expected calls
    mock_block.assert_called()
    mock_rpc_typed.process.assert_called()

    # Verify blocks_info was called for both receiving and confirmation
    assert mock_rpc_typed.blocks_info.call_count == 2
    mock_rpc_typed.blocks_info.assert_any_call(
        ["block_hash_to_receive"], source=True, receive_hash=True, json_block=True
    )
    mock_rpc_typed.blocks_info.assert_any_call(
        ["processed_block_hash"], source=True, receive_hash=True, json_block=True
    )

    # Verify account_info was called multiple times
    # At least twice - could be more due to retries
    assert mock_rpc_typed.account_info.call_count >= 2


@pytest.mark.asyncio
async def test_receive_by_hash_new_account_timeout(
    mock_rpc, mock_rpc_typed, seed, index
):
    block_hash_to_receive = "0" * 64
    processed_block_hash = "1" * 64

    # Create a list for blocks_info responses
    blocks_info_responses = [
        # First call for getting block info to receive
        {
            "blocks": {
                block_hash_to_receive: {
                    "amount": "5000",
                    "source_account": "0",
                    "block_account": "source_account1",
                    "subtype": "send",
                }
            }
        }
    ]

    # Add confirmation check responses
    confirmation_response = {
        "blocks": {processed_block_hash: {"confirmed": "false", "contents": {}}}
    }
    blocks_info_responses.extend([confirmation_response] * 10)

    mock_rpc_typed.blocks_info.side_effect = blocks_info_responses

    # Fix the account_info mock to include all required fields
    mock_rpc_typed.account_info.side_effect = [
        {"error": "Account not found"},
        {
            "frontier": processed_block_hash,
            "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
            "balance": "5000",
            "representative_block": processed_block_hash,
            "open_block": processed_block_hash,
            "confirmation_height": "0",
            "block_count": "1",
            "account_version": "1",
            "weight": "0",
            "receivable": "0",
        },
    ]

    mock_rpc_typed.work_generate.return_value = {"work": "0" * 16}
    mock_rpc_typed.process.return_value = {"hash": processed_block_hash}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)

    # Get the NanoResult
    result = await wallet.receive_by_hash(block_hash_to_receive, timeout=0.1)

    # Since @handle_errors wraps the TimeoutError into a NanoException,
    # we should expect NanoException with the timeout message
    with pytest.raises(NanoException) as exc_info:
        result.unwrap()

    assert (
        exc_info.value.message
        == f"Block {processed_block_hash} not confirmed within 0.1 seconds"
    )
    # TimeoutError gets wrapped with this code
    assert exc_info.value.code == "TIMEOUT"


@pytest.mark.asyncio
async def test_receive_by_hash_not_found(mock_rpc, mock_rpc_typed, seed, index):
    # Mock the RPC calls

    mock_rpc_typed.blocks_info.return_value = {"error": "Block not found"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.receive_by_hash(
        "763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4"
    )

    assert result.success == False
    assert (
        result.error
        == "Block not found 763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4"
    )


@pytest.mark.asyncio
async def test_receive_all_nothing_found(mock_rpc, mock_rpc_typed, seed, index):
    # Mock the RPC calls

    mock_rpc_typed.receivable.return_value = {"blocks": ""}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.receive_all()
    print(result.unwrap())

    assert result.success == True


def test_nano_to_raw():
    # Test case with 0.00005 Nano
    input_nano = "0.000000000005"
    expected_raw = 5000000000000000000

    result = nano_to_raw(input_nano)
    assert result == expected_raw, f"Expected {expected_raw}, but got {result}"

    result = nano_to_raw(input_nano, precision=6)
    assert result == 0, f"Expected 0, but got {result}"

    result = nano_to_raw(input_nano, precision=12)
    assert result == 5000000000000000000, f"Expected {expected_raw}, but got {result}"

    # Additional test cases
    assert nano_to_raw(1) == 1000000000000000000000000000000, "Failed for 1 Nano"
    assert nano_to_raw("0.1") == 100000000000000000000000000000, "Failed for 0.1 Nano"
    assert (
        nano_to_raw("1.23456789") == 1234567890000000000000000000000
    ), "Failed for 1.23456789 Nano"

    # Test case for a very small amount
    small_amount = "0.000000000000000000000000000001"
    assert nano_to_raw(small_amount) == 1, "Failed for very small amount"

    with pytest.raises(InvalidAmountError, match="Negative values are not allowed"):
        nano_to_raw("-1")
    with pytest.raises(NanoException, match="Negative values are not allowed"):
        nano_to_raw("-0.0001")
    with pytest.raises(NanoException):
        nano_to_raw("-100000000000000000000000000000100000000000000000000000000000")
    with pytest.raises(Exception):
        nano_to_raw("invalid_input")


def test_raw_to_nano():
    # Test case with 0.00005 Nano
    input_raw = 1234567890000000000000000011111
    expected_nano = Decimal("1.234567890000000000000000011111")

    result = raw_to_nano(input_raw, decimal_places=30)
    print(result)

    assert (
        result == expected_nano
    ), f"""Expected {
        expected_nano}, but got {result}"""


@pytest.mark.asyncio
async def test_receive_all(mock_rpc, mock_rpc_typed, seed, index):

    # Mock the RPC calls
    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            "763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4": {
                "amount": "500000000000000000000000000",
                "source": "0",
            },
            "0000000000000000000000000000000000000000000000000000000000001234": {
                "amount": "27",
                "source": "0",
            },
        }
    }

    mock_rpc_typed.blocks_info.return_value = {
        "blocks": {
            "763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4": {
                "block_account": "source_account1",
                "amount": "500000000000000000000000000",
                "source_account": "0",
            },
            "0000000000000000000000000000000000000000000000000000000000001234": {
                "block_account": "source_account2",
                "amount": "2",
                "source_account": "0",
            },
        }
    }

    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}
    mock_rpc_typed.work_generate.return_value = {"work": "3134dc9344d96938"}

    mock_rpc_typed.process.side_effect = [
        {"hash": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b79"},
        {"hash": "0000000000000000000000000000000000000000000000000000000000007777"},
    ]

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.receive_all(threshold_raw=1, wait_confirmation=False)

    assert result.success == True

    assert result.value == [
        ReceivedBlock(
            block_hash="4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b79",
            amount_raw=500000000000000000000000000,
            source="source_account1",
            confirmed=False,
        ),
        ReceivedBlock(
            block_hash="0000000000000000000000000000000000000000000000000000000000007777",
            amount_raw=2,
            source="source_account2",
            confirmed=False,
        ),
    ]

    assert result.value[0].amount == Decimal("0.0005")
    assert result.value[1].amount == Decimal("2E-30")
    assert mock_rpc_typed.receivable.call_count == 2
    assert mock_rpc_typed.blocks_info.call_count == 2
    assert mock_rpc_typed.account_info.call_count == 4
    assert mock_rpc_typed.work_generate.call_count == 2
    assert mock_rpc_typed.process.call_count == 2


@pytest.mark.asyncio
async def test_receive_all_threshold_filtering(mock_rpc, mock_rpc_typed, seed, index):
    """Test receive_all with threshold filtering"""

    # Define consistent block hashes
    block_1 = "1" * 64  # 64-character hex string
    block_2 = "2" * 64
    block_3 = "3" * 64
    received_hash = "4" * 64

    # Mock receivable blocks with different amounts
    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            block_1: {
                "amount": "1000000000000000000000000000",
                "source": "0",
            },  # 1 Nano
            block_2: {
                "amount": "100000000000000000000000",
                "source": "0",
            },  # 0.0001 Nano
            block_3: {
                "amount": "1000000000000000000000",
                "source": "0",
            },  # 0.000001 Nano
        }
    }

    # Mock block info responses
    def blocks_info_side_effect(hashes, **kwargs):
        responses = {
            block_1: {
                "block_account": "source1",
                "amount": "1000000000000000000000000000",
                "source_account": "0",
            },
            block_2: {
                "block_account": "source2",
                "amount": "100000000000000000000000",
                "source_account": "0",
            },
            block_3: {
                "block_account": "source3",
                "amount": "1000000000000000000000",
                "source_account": "0",
            },
            received_hash: {"confirmed": "true", "contents": {}},
        }
        return {"blocks": {hash: responses[hash] for hash in hashes}}

    mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect

    # Mock account_info to simulate new account
    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}

    # Mock work generation and block processing
    mock_rpc_typed.work_generate.return_value = {"work": "1234567890abcdef"}
    mock_rpc_typed.process.return_value = {"hash": received_hash}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)

    # Test with threshold of 0.0001 Nano (should receive top 2 blocks)
    threshold = 100000000000000000000000  # 0.0001 Nano in raw
    result = await wallet.receive_all(
        threshold_raw=threshold, wait_confirmation=True, timeout=0.1
    )

    received_blocks = result.unwrap()
    # Should receive only the two blocks above threshold
    assert len(received_blocks) == 2

    # Verify amounts are above threshold and blocks are confirmed
    for block in received_blocks:
        assert block.amount_raw >= threshold
        assert block.confirmed == True

    # Verify the expected RPC calls
    assert mock_rpc_typed.receivable.call_count >= 1
    assert mock_rpc_typed.blocks_info.call_count >= 2  # At least one per received block
    assert mock_rpc_typed.process.call_count == 2  # Should process exactly two blocks


@pytest.mark.asyncio
async def test_receive_all_mixed_confirmation(mock_rpc, mock_rpc_typed, seed, index):
    """Test receive_all where one block confirms and another times out"""

    # Define consistent block hashes - using different hex digits for clarity
    send_block_1 = "a" * 64
    send_block_2 = "b" * 64
    received_block_1 = "c" * 64
    received_block_2 = "d" * 64

    # Mock receivable blocks
    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            send_block_1: {
                "amount": "500000000000000000000000000",
                "source": "0",
            },  # Will confirm
            send_block_2: {
                "amount": "300000000000000000000000000",
                "source": "0",
            },  # Will timeout
        }
    }

    # Mock block info responses with side effect to handle both initial info and confirmation checks
    def blocks_info_side_effect(hashes, **kwargs):
        responses = {
            send_block_1: {
                "block_account": "source1",
                "amount": "500000000000000000000000000",
                "source_account": "0",
            },
            send_block_2: {
                "block_account": "source2",
                "amount": "300000000000000000000000000",
                "source_account": "0",
            },
            received_block_1: {"confirmed": "true", "contents": {}},
            received_block_2: {"confirmed": "false", "contents": {}},
        }
        return {"blocks": {hash: responses[hash] for hash in hashes}}

    mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect
    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}
    mock_rpc_typed.work_generate.return_value = {"work": "1234567890abcdef"}

    # Mock process responses for the two blocks
    mock_rpc_typed.process.side_effect = [
        {"hash": received_block_1},
        {"hash": received_block_2},
    ]

    wallet = create_wallet_from_seed(mock_rpc, seed, index)

    # Test with confirmation timeout of 0.1 seconds
    with pytest.raises(NanoException) as exc_info:
        result = await wallet.receive_all(
            threshold_raw=1, wait_confirmation=True, timeout=0.1
        )
        result.unwrap()

    # assert "not confirmed within 0.1 seconds" in str(exc_info.value)

    # Verify RPC calls
    assert mock_rpc_typed.receivable.call_count >= 1
    assert mock_rpc_typed.blocks_info.call_count >= 2  # At least one per block
    assert mock_rpc_typed.process.call_count == 2


@pytest.mark.asyncio
async def test_receive_all_process_error(mock_rpc, mock_rpc_typed, seed, index, caplog):
    """Test receive_all handling of process errors"""
    caplog.set_level(logging.DEBUG)  # Enable debug logging

    # Define consistent block hashes
    send_block_1 = "e" * 64
    send_block_2 = "f" * 64
    received_block_1 = "1" * 64

    def blocks_info_side_effect(hashes, **kwargs):
        responses = {
            send_block_1: {
                "block_account": "source1",
                "amount": "1000000000000000000000000000",
                "source_account": "0",
            },
            send_block_2: {
                "block_account": "source2",
                "amount": "2000000000000000000000000000",
                "source_account": "0",
            },
            received_block_1: {"confirmed": "true", "contents": {}},
        }
        return {"blocks": {hash: responses[hash] for hash in hashes}}

    # Only patch list_receivables as it's not part of the process flow we want to test
    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            send_block_1: {
                "amount": "1000000000000000000000000000",
                "source": "0",
            },
            send_block_2: {
                "amount": "2000000000000000000000000000",
                "source": "0",
            },
        }
    }
    mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect
    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}
    mock_rpc_typed.work_generate.return_value = {"work": "1234567890abcdef"}
    # Setup the underlying _rpc.process mock responses
    mock_rpc_typed.process.side_effect = [
        {"hash": received_block_1},  # First call succeeds
        {"error": "Fork detected"},  # Second call fails
    ]

    wallet = create_wallet_from_seed(mock_rpc, seed, index)

    with pytest.raises(NanoException) as exc_info:
        result = await wallet.receive_all(wait_confirmation=False)
        result.unwrap()

    assert "Fork detected" in str(exc_info.value)
    assert mock_rpc_typed.process.call_count == 2


@pytest.mark.asyncio
async def test_receive_all_empty_receivable(mock_rpc, mock_rpc_typed, seed, index):
    """Test receive_all with no receivable blocks"""

    # Mock account info with valid balance values
    mock_rpc_typed.account_info.return_value = {
        "frontier": "0" * 64,
        "open_block": "0" * 64,
        "representative_block": "0" * 64,
        "balance": "0",  # Valid numeric string for balance
        "modified_timestamp": "0",
        "block_count": "0",
        "confirmation_height": "0",  # Added required field
        "account_version": "0",
        "representative": "nano_1q3hqecaw15cjt7thbtxu3pbzr1eihtzzpzxguoc37bj1wc5ffoh7w74gi6p",
        "weight": "0",
        "pending": "0",
        "receivable": "0",  # Valid numeric string for receivable
    }

    # Mock empty receivable
    mock_rpc_typed.receivable.return_value = {"blocks": {}}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.receive_all(wait_confirmation=True)

    assert result.success == True
    assert result.unwrap() == []

    # Verify minimal RPC calls - receivable is called twice:
    # 1. During wallet initialization/reload
    # 2. During receive_all
    assert mock_rpc_typed.receivable.call_count == 2
    assert mock_rpc_typed.blocks_info.call_count == 0
    assert mock_rpc_typed.process.call_count == 0


def test_sum_amount():
    received_amount_response = [
        ReceivedBlock(
            block_hash="4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b79",
            amount_raw=500000000000000000000000000,
            source="source_account1",
            confirmed=True,
        ),
        ReceivedBlock(
            block_hash="0000000000000000000000000000000000000000000000000000000000007777",
            amount_raw=21,
            source="source_account2",
            confirmed=False,
        ),
    ]
    sum = sum_received_amount(received_amount_response)
    assert sum.amount_raw == 500000000000000000000000000 + 21
    assert sum.amount == Decimal("0.0005") + Decimal("21e-30")


@pytest.mark.asyncio
async def test_receive_all_not_found(mock_rpc, mock_rpc_typed, seed, index):

    # Mock the RPC calls
    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            "763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4": {
                "amount": "500000000000000000000000000",
                "source": "0",
            }
        }
    }

    # We're intentionally not mocking account_info properly to test our defensive code
    # This will cause account_info.get("receivable") to return a coroutine

    # This is the critical part - we want blocks_info to return a "Block not found" error
    # when receive_by_hash tries to get info about the block
    mock_rpc_typed.blocks_info.return_value = {"error": "Block not found"}

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    result = await wallet.receive_all()

    assert result.success == False
    assert (
        "Block not found 763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4"
        in result.error
    )


@pytest.mark.asyncio
async def test_validate_work_send(mock_rpc, mock_rpc_typed, seed, index):

    wallet: NanoWalletAuthenticated = create_wallet_from_seed(mock_rpc, seed, index)

    mock_rpc_typed.work_generate.return_value = {"work": "b97cf24869b976eb"}

    prev = "474B9BEBD9AB9B39E05F0260555A31ECFB05E4BB0B2F6386904B9CEAD222FA0D"
    rep = "nano_3nbst43by3nytxfzcbmw5sdoq78i394ppso34cm5861eom6q45niyochomnp"
    destination = "nano_348ggsrnzh44jp5cm1114r495fmz77tqf36fxunzg3ufmj3yzj5jhaat5ew1"

    # Fake account for testing
    wallet._block_operations.account = (
        "nano_3rdcmdz7rjupyhadrxbrmx7kb8smk48oyns63uowtm3uw87c8r65gujufy8o"
    )
    block = await wallet._block_operations._build_block(
        prev, rep, 927438000000000000000000000000, destination_account=destination
    )
    assert (
        block.block_hash
        == "6EC6792F999FA02F0026FC7702E04FD23BA4B4736E26A5EDB578CEE3A8CBFD6D"
    )


@pytest.mark.asyncio
async def test_validate_work_receive(mock_rpc, mock_rpc_typed, seed, index):

    wallet = create_wallet_from_seed(mock_rpc, seed, index)

    mock_rpc_typed.work_generate.return_value = {"work": "7fe398470f748c75"}

    prev = "0" * 64
    rep = "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6"
    source_hash = "6EC6792F999FA02F0026FC7702E04FD23BA4B4736E26A5EDB578CEE3A8CBFD6D"

    # Fake account for testing
    wallet._block_operations.account = (
        "nano_348ggsrnzh44jp5cm1114r495fmz77tqf36fxunzg3ufmj3yzj5jhaat5ew1"
    )
    block = await wallet._block_operations._build_block(
        prev, rep, 500000000000000000000000000, source_hash=source_hash
    )
    assert (
        block.block_hash
        == "1754AE5ED04C23DE2A7943DF60171061778ECD6901878877A71B39B83C233476"
    )


@pytest.mark.asyncio
async def test_refund_first_sender_unopened(mock_rpc, mock_rpc_typed, seed, index):

    wallet = create_wallet_from_seed(mock_rpc, seed, index)

    # Mock the necessary methods
    wallet._state_manager.balance_info.balance_raw = 1000

    account_info_not_found = {"error": "Account not found"}

    # Account after receiving the block - would have the balance from the receivable
    # Make sure frontier/previous is a valid 64-char hex string
    account_info_after_receive = {
        "frontier": "a" * 64,  # Valid 64-char hex string for previous
        "representative": "nano_3msc38fyn67pgio16dj586pdrceahtn75qgnx7fy19wscixrc8dbb3abhbw6",
        "balance": "3187918000000000000000000000000",
        "representative_block": "a" * 64,
        "open_block": "a" * 64,
        "confirmation_height": "1",
        "block_count": "1",
        "account_version": "1",
        "weight": "0",
        "receivable": "0",
    }

    account_info_first_sender = {
        "frontier": "a" * 64,  # Valid 64-char hex string for previous
        "representative": "nano_118tih7f81iiuujdezyqnbb9aonybf6y3cj7mo7hbeetqiymkn16a67w8rkp",
        "balance": "3187918000000000000000000000000",
        "representative_block": "a" * 64,
        "open_block": "a" * 64,
        "confirmation_height": "1",
        "block_count": "1",
        "account_version": "1",
        "weight": "0",
        "receivable": "0",
    }

    # Instead of setting side effects all at once, let's modify them during the test
    mock_rpc_typed.account_info.side_effect = [
        account_info_not_found,  # Initial reload
        account_info_first_sender,  # querying destination account
        account_info_not_found,  # During list_receivables
        account_info_not_found,  # During refund_first_sender blocks_info lookup
        account_info_after_receive,  # After receive when reloading
        account_info_after_receive,
        account_info_after_receive,
    ]

    mock_rpc_typed.receivable.return_value = {
        "blocks": {
            "1234000000000000000000000000000000000000000000000000000000000000": {
                "amount": "3187918000000000000000000000000",
                "source": "0",
            }
        }
    }
    mock_rpc_typed.work_generate.return_value = {"work": "7fe398470f748c75"}
    mock_rpc_typed.process.return_value = {"hash": "processed_block_hash"}
    mock_rpc_typed.blocks_info.return_value = {
        "blocks": {
            "1234000000000000000000000000000000000000000000000000000000000000": {
                "block_account": "nano_118tih7f81iiuujdezyqnbb9aonybf6y3cj7mo7hbeetqiymkn16a67w8rkp",
                "amount": "3187918000000000000000000000000",
                "balance": "704403060752542192142227299368960",
                "confirmed": "true",
                "subtype": "send",
                "receive_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                "source_account": "0",
            }
        }
    }
    result = await wallet.refund_first_sender()

    assert result.success == True
    assert result.value == "processed_block_hash"


@pytest.mark.asyncio
async def test_refund_first_sender_no_account(mock_rpc, mock_rpc_typed, seed, index):

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    print(wallet._state_manager.account_info.open_block)

    mock_rpc_typed.account_info.return_value = {"error": "Account not found"}
    response = await wallet.refund_first_sender()

    assert response.success == False
    assert response.error == "No funds available (balance or receivable) to refund."


@pytest.mark.asyncio
async def test_refund_first_sender_no_funds(mock_rpc, mock_rpc_typed, seed, index):

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    mock_rpc_typed.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "0",
        "representative_block": "representative_block",
        "open_block": "open_block_hash",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "0",
    }
    mock_rpc_typed.blocks_info.return_value = {"blocks": ""}

    response = await wallet.refund_first_sender()

    assert response.success == False
    assert response.error == "No funds available (balance or receivable) to refund."


@pytest.mark.asyncio
async def test_wallett_to_str(mock_rpc, mock_rpc_typed, seed, index):

    wallet = create_wallet_from_seed(mock_rpc, seed, index)
    mock_rpc_typed.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000",
    }
    await wallet.reload()

    expected_to_string = """NanoWalletAuthenticated:
  Account: nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s
  Balance: 2 Nano (2000000000000000000000000000000 raw)
  Receivable: 1 Nano (1000000000000000000000000000000 raw)
  Voting Weight: 3 Nano (3000000000000000000000000000000 raw)
  Representative: nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf
  Confirmation Height: 1
  Block Count: 50"""

    expected__str__ = """NanoWalletAuthenticated: Account=nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s, BalanceRaw=2000000000000000000000000000000, ReceivableRaw=1000000000000000000000000000000"""

    assert wallet.to_string() == expected_to_string
    assert str(wallet) == expected__str__


@pytest.mark.asyncio
async def test_valid_account(mock_rpc, mock_rpc_typed, seed):

    wallet = create_wallet_from_seed(mock_rpc, seed, 25)
    wallet.account = "nano_14ckiit8au8njgzrm4gb9se7d8yf3enec6mdy7154gr8qh3cu1yf9nqgomh3"
    await wallet.reload()


def test_nanoresult_unwrap():
    # Test successful case
    success_result = NanoResult(value="test_value")
    assert success_result.success == True
    assert success_result.unwrap() == "test_value"

    # Test error case
    error_result = NanoResult(error="test error", error_code="TEST_ERROR")
    assert error_result.success == False
    with pytest.raises(NanoException) as exc_info:
        error_result.unwrap()
    assert exc_info.value.message == "test error"
    assert exc_info.value.code == "TEST_ERROR"

    # Test error case without code
    error_result_no_code = NanoResult(error="test error")
    assert error_result_no_code.success == False
    with pytest.raises(NanoException) as exc_info:
        error_result_no_code.unwrap()
    assert exc_info.value.message == "test error"
    assert exc_info.value.code == "UNKNOWN_ERROR"  # Default error code


@pytest.mark.asyncio
async def test_handle_errors_decorator():
    # Create a test class that simulates wallet methods
    class TestClass:
        @handle_errors
        async def success_method(self):
            return "success"

        @handle_errors
        async def raises_nano_exception(self):
            raise InvalidAccountError("Invalid account")

        @handle_errors
        async def raises_regular_exception(self):
            raise ValueError("Something went wrong")

        @handle_errors
        async def raises_timeout_error(self):
            raise TimeoutError("Operation timed out")

    test = TestClass()

    # Test successful case
    result = await test.success_method()
    assert result.success == True
    assert result.unwrap() == "success"

    # Test NanoException handling
    result = await test.raises_nano_exception()
    assert result.success == False
    with pytest.raises(NanoException) as exc_info:
        result.unwrap()
    assert exc_info.value.code == "INVALID_ACCOUNT"
    assert exc_info.value.message == "Invalid account"

    # Test regular exception handling
    result = await test.raises_regular_exception()
    assert result.success == False
    with pytest.raises(NanoException) as exc_info:
        result.unwrap()
    assert exc_info.value.code == "UNEXPECTED_ERROR"
    assert exc_info.value.message == "Something went wrong"

    # Test TimeoutError handling
    result = await test.raises_timeout_error()
    assert result.success == False
    with pytest.raises(NanoException) as exc_info:
        result.unwrap()
    assert exc_info.value.message == "Operation timed out"


@pytest.mark.asyncio
async def test_reload_after_decorator():
    # Create a test class that simulates wallet
    class TestClass:
        def __init__(self):
            self.reload_called = False

        async def reload(self):
            self.reload_called = True

        @reload_after
        async def success_method(self):
            return "success"

        @reload_after
        async def failing_method(self):
            raise ValueError("Error")

    test = TestClass()

    # Test reload after success
    result = await test.success_method()
    assert result == "success"
    assert test.reload_called == True

    # Reset reload flag
    test.reload_called = False

    # Test reload after failure
    with pytest.raises(ValueError):
        await test.failing_method()
    assert test.reload_called == False  # Should reload even after exception


@pytest.mark.asyncio
async def test_combined_decorators():
    class TestClass:
        def __init__(self):
            self.reload_called = False

        async def reload(self):
            self.reload_called = True

        @reload_after
        @handle_errors
        async def test_method(self, should_fail: bool = False):
            if should_fail:
                raise InvalidAccountError("Test error")
            return "success"

    test = TestClass()

    # Test success case
    result = await test.test_method(should_fail=False)
    assert test.reload_called == True
    assert result.success == True
    assert result.unwrap() == "success"

    # Reset and test failure case
    test.reload_called = False
    result = await test.test_method(should_fail=True)
    assert test.reload_called == True
    assert result.success == False
    with pytest.raises(NanoException) as exc_info:
        result.unwrap()
    assert exc_info.value.code == "INVALID_ACCOUNT"


@pytest.mark.asyncio
async def test_account_history(mock_rpc, mock_rpc_typed):

    mock_response = {
        "account": "nano_118tih7f81iiuujdezyqnbb9aonybf6y3cj7mo7hbeetqiymkn16a67w8rkp",
        "history": [
            {
                "account": "nano_1htaxaiwg5h46afhxctm9khz74zjk75zrsth16upt3b17wndty5rwoowr3hu",
                "amount": "3000000000000000000000000",
                "balance": "685480328931131963959607814791168",
                "confirmed": "true",
                "hash": "D80E18554DB0DE3CCE463943BCA91F09A72AA304F18E6E60F2AA09D6426B3BD7",
                "height": "287",
                "link": "3F48EA21C70DE2221AFEAB533C9FF28BF19147FC674F01376D05202F28BD7878",
                "local_timestamp": "1735991174",
                "previous": "C4C9BD7EC4A1B7DE65FFE50D0B29891EC5245621024C86D76947275A8FFED1FE",
                "representative": "nano_1natrium1o3z5519ifou7xii8crpxpk8y65qmkih8e8bpsjri651oza8imdd",
                "signature": "93048CA02BEA5F825AEFECBEEFCCE5364871806F74A5EB1AF59D4CA46FDF6FD8A8EE27474FB31E9A5EF9AB9ECD4BCAED2075CCF6057852AED227BA6E0720E902",
                "subtype": "send",
                "type": "state",
                "work": "9cf61f7561c1ab3c",
            },
            {
                "account": "nano_3duhkw8zo3gzgq9dgubbwsnbd5k769c5zyi4dheck8yg4ukm83gf7a7nhts5",
                "amount": "35714000000000000000000000000",
                "balance": "685480331931131963959607814791168",
                "confirmed": "true",
                "hash": "C4C9BD7EC4A1B7DE65FFE50D0B29891EC5245621024C86D76947275A8FFED1FE",
                "height": "286",
                "link": "AF6F970DFA85DF75CEB76D29E668958E4521D43FFA025BD8A91BCE16E53305CD",
                "local_timestamp": "1735434546",
                "previous": "BB48158268E2423F98B5363FB10685C593415286ED39E5F4452E29DBE0BBFD6C",
                "representative": "nano_1natrium1o3z5519ifou7xii8crpxpk8y65qmkih8e8bpsjri651oza8imdd",
                "signature": "F85918BCA24EB4E221CA49109E0DB6EEBA4BBA177B73374815AF039A42ED002433AA4FF2941A3E51CE9C339EF186937C4896756D84964003D08B4542A2034F04",
                "subtype": "send",
                "type": "state",
                "work": "fc21cadd1abbbe4f",
            },
        ],
    }

    mock_rpc_typed.account_history.return_value = mock_response

    wallet = create_wallet_from_seed(mock_rpc, "0" * 64, 0)
    result = await wallet.account_history(count=2)
    blocks = result.unwrap()

    expected_blocks = [
        Transaction(
            account="nano_1htaxaiwg5h46afhxctm9khz74zjk75zrsth16upt3b17wndty5rwoowr3hu",
            confirmed=True,
            block_hash="D80E18554DB0DE3CCE463943BCA91F09A72AA304F18E6E60F2AA09D6426B3BD7",
            height=287,
            link="3F48EA21C70DE2221AFEAB533C9FF28BF19147FC674F01376D05202F28BD7878",
            previous="C4C9BD7EC4A1B7DE65FFE50D0B29891EC5245621024C86D76947275A8FFED1FE",
            representative="nano_1natrium1o3z5519ifou7xii8crpxpk8y65qmkih8e8bpsjri651oza8imdd",
            signature="93048CA02BEA5F825AEFECBEEFCCE5364871806F74A5EB1AF59D4CA46FDF6FD8A8EE27474FB31E9A5EF9AB9ECD4BCAED2075CCF6057852AED227BA6E0720E902",
            subtype="send",
            type="state",
            work="9cf61f7561c1ab3c",
            amount_raw=3000000000000000000000000,
            balance_raw=685480328931131963959607814791168,
            timestamp=1735991174,
        ),
        Transaction(
            account="nano_3duhkw8zo3gzgq9dgubbwsnbd5k769c5zyi4dheck8yg4ukm83gf7a7nhts5",
            confirmed=True,
            block_hash="C4C9BD7EC4A1B7DE65FFE50D0B29891EC5245621024C86D76947275A8FFED1FE",
            height=286,
            link="AF6F970DFA85DF75CEB76D29E668958E4521D43FFA025BD8A91BCE16E53305CD",
            previous="BB48158268E2423F98B5363FB10685C593415286ED39E5F4452E29DBE0BBFD6C",
            representative="nano_1natrium1o3z5519ifou7xii8crpxpk8y65qmkih8e8bpsjri651oza8imdd",
            signature="F85918BCA24EB4E221CA49109E0DB6EEBA4BBA177B73374815AF039A42ED002433AA4FF2941A3E51CE9C339EF186937C4896756D84964003D08B4542A2034F04",
            subtype="send",
            type="state",
            work="fc21cadd1abbbe4f",
            amount_raw=35714000000000000000000000000,
            balance_raw=685480331931131963959607814791168,
            timestamp=1735434546,
        ),
    ]

    assert blocks[0].amount == Decimal("0.000003")
    assert blocks[1].amount == Decimal("0.035714")
    assert blocks[0].balance == Decimal("685.480328931131963959607814791168")
    assert blocks[1].balance == Decimal("685.480331931131963959607814791168")
    assert (
        blocks[0].destination
        == "nano_1htaxaiwg5h46afhxctm9khz74zjk75zrsth16upt3b17wndty5rwoowr3hu"
    )
    assert (
        blocks[1].destination
        == "nano_3duhkw8zo3gzgq9dgubbwsnbd5k769c5zyi4dheck8yg4ukm83gf7a7nhts5"
    )

    assert blocks == expected_blocks
