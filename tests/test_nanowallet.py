import pytest
from unittest.mock import AsyncMock, patch
from nanorpc.client import NanoRpcTyped
from nanowallet.nanowallet import NanoWallet, WalletUtils
from nanowallet.utils import nano_to_raw, raw_to_nano


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
def mock_rpc():
    return AsyncMock(spec=NanoRpcTyped)


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_init(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    wallet = NanoWallet(mock_rpc, seed, index)

    assert wallet.seed == seed
    assert wallet.index == index
    assert wallet.account == account
    assert wallet.private_key == private_key


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_reload(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": {
            "block1": "1000000000000000000000000000000"
        }
    }
    mock_rpc.account_info.return_value = {
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
        "receivable": "1000000000000000000000000000000"
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()

    assert wallet.balance == 2
    assert wallet.balance_raw == 2000000000000000000000000000000
    assert wallet.frontier_block == "frontier_block"
    assert wallet.representative_block == "representative_block"
    assert wallet.representative == "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf"
    assert wallet.open_block == "open_block"
    assert wallet.confirmation_height == 40
    assert wallet.block_count == 50
    assert wallet.weight == 3
    assert wallet.weight_raw == 3000000000000000000000000000000
    assert wallet.receivable_balance == 1
    assert wallet.receivable_balance_raw == 1000000000000000000000000000000


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_reload_unopened(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": {
            "b1": "1000000000000000000000000000000",
            "b2": "1",
            "b3": "3000000000000000000000000000000"}
    }
    mock_rpc.account_info.return_value = {
        "error": "Account not found"
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()

    assert wallet.balance == 0
    assert wallet.balance_raw == 0
    assert wallet.frontier_block == None
    assert wallet.representative_block == None
    assert wallet.representative == None
    assert wallet.open_block == None
    assert wallet.confirmation_height == 0
    assert wallet.block_count == 0
    assert wallet.weight == 0
    assert wallet.weight_raw == 0
    assert wallet.receivable_balance == 4
    assert wallet.receivable_balance_raw == 4000000000000000000000000000001
    assert wallet.receivable_blocks == {
        "b1": "1000000000000000000000000000000", "b2": "1", "b3": "3000000000000000000000000000000"}


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_reload_unopened(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": {
            "b1": "1000000000000000000000000000123"}
    }
    mock_rpc.account_info.return_value = {
        "error": "Account not found"
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()
    await wallet.reload()

    assert wallet.receivable_balance_raw == 1000000000000000000000000000123
    assert wallet.receivable_blocks == {
        "b1": "1000000000000000000000000000123"}


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_reload_unopen_no_receivables(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": ""
    }
    mock_rpc.account_info.return_value = {
        "error": "Account not found"
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()

    assert wallet.balance == 0
    assert wallet.balance_raw == 0
    assert wallet.frontier_block == None
    assert wallet.representative_block == None
    assert wallet.representative == None
    assert wallet.open_block == None
    assert wallet.confirmation_height == 0
    assert wallet.block_count == 0
    assert wallet.weight == 0
    assert wallet.weight_raw == 0
    assert wallet.receivable_balance == 0
    assert wallet.receivable_balance_raw == 0
    assert wallet.receivable_blocks == ""


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_reload_no_receivables(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": ""
    }
    mock_rpc.account_info.return_value = {
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
        "receivable": "1000000000000000000000000000000"
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()

    assert wallet.balance == 2
    assert wallet.balance_raw == 2000000000000000000000000000000
    assert wallet.frontier_block == "frontier_block"
    assert wallet.representative_block == "representative_block"
    assert wallet.representative == "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf"
    assert wallet.open_block == "open_block"
    assert wallet.confirmation_height == 40
    assert wallet.block_count == 50
    assert wallet.weight == 3
    assert wallet.weight_raw == 3000000000000000000000000000000
    assert wallet.receivable_balance == 1
    assert wallet.receivable_balance_raw == 1000000000000000000000000000000


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
@patch('nanowallet.nanowallet.Block')
async def test_send(mock_block, mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000"
    }
    mock_rpc.work_generate.return_value = {"work": "work_value"}
    mock_rpc.process.return_value = {"hash": "processed_block_hash"}

    wallet = NanoWallet(mock_rpc, seed, index)
    result = await wallet.send("nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s", 1)

    assert result.success == True
    assert result.value == "processed_block_hash"
    mock_block.assert_called()
    mock_rpc.process.assert_called()


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
@patch('nanowallet.nanowallet.Block')
async def test_send_raw(mock_block, mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000"
    }
    mock_rpc.work_generate.return_value = {"work": "work_value"}
    mock_rpc.process.return_value = {"hash": "processed_block_hash"}

    wallet = NanoWallet(mock_rpc, seed, index)
    result = await wallet.send_raw("nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s", 1e30)

    assert result.success == True
    assert result.value == "processed_block_hash"
    mock_block.assert_called()
    mock_rpc.process.assert_called()


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
@patch('nanowallet.nanowallet.Block')
async def test_send_raw_error(mock_block, mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.account_info.return_value = {
        "frontier": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b78",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000",
        "representative_block": "representative_block",
        "open_block": "open_block",
        "confirmation_height": "1",
        "block_count": "50",
        "account_version": "1",
        "weight": "3000000000000000000000000000000",
        "receivable": "1000000000000000000000000000000"
    }
    mock_rpc.work_generate.return_value = {"work": "work_value"}
    mock_rpc.process.return_value = {"hash": "processed_block_hash"}

    wallet = NanoWallet(mock_rpc, seed, index)
    result = await wallet.send_raw("nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s", 1e30)

    assert result.success == False
    assert result.error == "Insufficient funds! balance_raw:2000 amount_raw:1000000000000000000000000000000"


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_list_receivables(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": {
            "block1": "2000000000000000000000000000000",
            "block2": "1000000000000000000000000000000"
        }
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()
    result = await wallet.list_receivables()

    expected = [
        ('block1', '2000000000000000000000000000000'),
        ('block2', '1000000000000000000000000000000')
    ]
    assert result.success == True
    assert result.value == expected


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_list_receivables_none(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": ""
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()
    result = await wallet.list_receivables()

    expected = []
    assert result.success == True
    assert result.value == expected


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_list_receivables_threshold(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": {
            "block1": "2000000000000000000000000000000",
            "block2": "1000000000000000000000000000000"
        }
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()
    result = await wallet.list_receivables(threshold_raw=1000000000000000000000000000001)

    expected = [
        ('block1', '2000000000000000000000000000000'),
    ]
    assert result.success == True
    assert result.value == expected


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
@patch('nanowallet.nanowallet.Block')
async def test_receive_by_hash(mock_block, mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index):

    mock_rpc.blocks_info.return_value = {"blocks":
                                         {"block_hash_to_receive":
                                          {"amount": "5",
                                              "source_account": "source_account1", }}}
    mock_rpc.account_info.return_value = {
        "frontier": "frontier_block",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "1000000000000000000000000000000"
    }
    mock_rpc.work_generate.return_value = {"work": "work_value"}
    mock_rpc.process.return_value = {"hash": "processed_block_hash"}

    wallet = NanoWallet(mock_rpc, seed, index)
    result = await wallet.receive_by_hash("block_hash_to_receive")

    assert result.success == True
    assert result.value == {"hash": 'processed_block_hash', 'amount_raw': 5,
                            'amount': 5e-30, 'source': 'source_account1'}
    mock_block.assert_called()
    mock_rpc.process.assert_called()


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
@patch('nanowallet.nanowallet.Block')
async def test_receive_by_hash_new_account(mock_block, mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index):

    mock_rpc.blocks_info.return_value = {"blocks":
                                         {"block_hash_to_receive":
                                          {"amount": "5000",
                                              "source_account": "source_account1", }}}
    mock_rpc.account_info.return_value = {
        "error": "Account not found"
    }
    mock_rpc.work_generate.return_value = {"work": "work_value"}
    mock_rpc.process.return_value = {"hash": "processed_block_hash"}

    wallet = NanoWallet(mock_rpc, seed, index)
    result = await wallet.receive_by_hash("block_hash_to_receive")

    assert result.success == True
    assert result.value == {"hash": 'processed_block_hash', 'amount_raw': 5000,
                            'amount': 5e-27, 'source': 'source_account1'}
    mock_block.assert_called()
    mock_rpc.process.assert_called()


def test_nano_to_raw():
    # Test case with 0.00005 Nano
    input_nano = "0.00005"
    expected_raw = 50000000000000000000000000

    result = nano_to_raw(input_nano)

    assert result == expected_raw, f"Expected {expected_raw}, but got {result}"

    # Additional test cases
    assert nano_to_raw(
        1) == 1000000000000000000000000000000, "Failed for 1 Nano"
    assert nano_to_raw(
        0.1) == 100000000000000000000000000000, "Failed for 0.1 Nano"
    assert nano_to_raw(
        1.23456789) == 1234567890000000000000000000000, "Failed for 1.23456789 Nano"

    # Test case for a very small amount
    small_amount = "0.000000000000000000000000000001"
    assert nano_to_raw(small_amount) == 1, "Failed for very small amount"

    with pytest.raises(ValueError, match="Nano amount is negative"):
        nano_to_raw("-1")
    with pytest.raises(ValueError, match="Nano amount is negative"):
        nano_to_raw("-0.0001")
    with pytest.raises(ValueError, match="Nano amount is negative"):
        nano_to_raw(
            "-100000000000000000000000000000100000000000000000000000000000")
    with pytest.raises(ValueError):
        nano_to_raw("invalid_input")


def test_raw_to_nano():
    # Test case with 0.00005 Nano
    input_raw = 1234567890000000000000000011111
    expected_nano = 1.23456789

    result = raw_to_nano(input_raw)
    print(result)

    assert result == expected_nano, f"""Expected {
        expected_nano}, but got {result}"""


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
async def test_receive_all(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    # Mock the RPC calls
    mock_rpc.receivable.return_value = {
        "blocks": {
            "763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4": "500000000000000000000000000",
            "0000000000000000000000000000000000000000000000000000000000001234": "27"
        }
    }
    mock_rpc.blocks_info.return_value = {
        "blocks": {
            "763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4": {
                "block_account": "nano_3rdcmdz7rjupyhadrxbrmx7kb8smk48oyns63uowtm3uw87c8r65gujufy8o",
                "amount": "500000000000000000000000000",
                "source_account": "source_account1",
            },
            "0000000000000000000000000000000000000000000000000000000000001234": {
                "block_account": "nano_3rdcmdz7rjupyhadrxbrmx7kb8smk48oyns63uowtm3uw87c8r65gujufy8o",
                "amount": "2",
                "source_account": "source_account2",
            }
        }
    }

    mock_rpc.account_info.return_value = {
        "error": "Account not found"
    }
    mock_rpc.work_generate.return_value = {"work": "3134dc9344d96938"}

    mock_rpc.process.side_effect = [
        {"hash": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b79"},
        {"hash": "0000000000000000000000000000000000000000000000000000000000007777"}
    ]

    wallet = NanoWallet(mock_rpc, seed, index)
    result = await wallet.receive_all()

    assert result.success == True

    assert result.value == [
        {"hash": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b79",
            "amount_raw": 500000000000000000000000000, 'amount': 0.0005, 'source': 'source_account1'},
        {"hash": "0000000000000000000000000000000000000000000000000000000000007777",
            "amount_raw": 2, 'amount': 2e-30, 'source': 'source_account2'}
    ]
    assert mock_rpc.receivable.call_count == 3
    assert mock_rpc.blocks_info.call_count == 2
    assert mock_rpc.account_info.call_count == 5
    assert mock_rpc.work_generate.call_count == 2
    assert mock_rpc.process.call_count == 2


def test_sum_amount():
    received_amount_response = [
        {"hash": "4c816abe42472ba8862d73139d0397ecb4cead4b21d9092281acda9ad8091b79",
            "amount_raw": 500000000000000000000000000, 'amount': 0.0005, 'source': 'source_account1'},
        {"hash": "0000000000000000000000000000000000000000000000000000000000007777",
            "amount_raw": 21, 'amount': 2e-30, 'source': 'source_account2'}
    ]
    sum = WalletUtils.sum_received_amount(received_amount_response)
    assert sum["amount_raw"] == 500000000000000000000000000 + 21


@ pytest.mark.asyncio
@ patch('nanowallet.nanowallet.generate_account_private_key')
@ patch('nanowallet.nanowallet.get_account_id')
async def test_receive_all_not_found(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    # Mock the RPC calls
    mock_rpc.receivable.return_value = {
        "blocks": {
            "763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4": "500000000000000000000000000"
        }
    }

    mock_rpc.blocks_info.return_value = {
        "error": "Block not found"
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    result = await wallet.receive_all()

    assert result.success == False
    assert result.error == "Block not found: 763F295D61A6774F3F9CDECEFCF3A6A91C09107042BFA1BFCC269936AC6DA1B4"
