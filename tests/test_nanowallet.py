import pytest
from unittest.mock import AsyncMock, patch
from nanorpc.client import NanoRpcTyped
from nanowallet.nanowallet import NanoWallet
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
@patch('nanowallet.nanowallet.Block')
async def test_send(mock_block, mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.account_info.return_value = {
        "frontier": "frontier_block",
        "representative": "nano_3rropjiqfxpmrrkooej4qtmm1pueu36f9ghinpho4esfdor8785a455d16nf",
        "balance": "2000000000000000000000000000000"
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
async def test_list_receivables(mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.receivable.return_value = {
        "blocks": {
            "block1": {"amount": "2000000000000000000000000000000"},
            "block2": {"amount": "1000000000000000000000000000000"}
        }
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()
    result = await wallet.list_receivables()

    expected = [
        ('block1', {'amount': '2000000000000000000000000000000'}),
        ('block2', {'amount': '1000000000000000000000000000000'})
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
            "block1": {"amount": "2000000000000000000000000000000"},
            "block2": {"amount": "1000000000000000000000000000000"}
        }
    }

    wallet = NanoWallet(mock_rpc, seed, index)
    await wallet.reload()
    result = await wallet.list_receivables(threshold_raw=1000000000000000000000000000001)

    expected = [
        ('block1', {'amount': '2000000000000000000000000000000'}),
    ]
    assert result.success == True
    assert result.value == expected


@pytest.mark.asyncio
@patch('nanowallet.nanowallet.generate_account_private_key')
@patch('nanowallet.nanowallet.get_account_id')
@patch('nanowallet.nanowallet.Block')
async def test_receive_by_hash(mock_block, mock_get_account_id, mock_generate_private_key, mock_rpc, seed, index, account, private_key):
    mock_generate_private_key.return_value = private_key
    mock_get_account_id.return_value = account

    mock_rpc.block_info.return_value = {
        "amount": "1000000000000000000000000000000"}
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
    assert result.value == "processed_block_hash"
    mock_block.assert_called()
    mock_rpc.process.assert_called()
