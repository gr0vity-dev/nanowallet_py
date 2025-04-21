# import pytest
# from unittest.mock import AsyncMock, patch, Mock
# from decimal import Decimal

# from nanowallet.wallets import NanoWallet, NanoWalletRpc
# from nanorpc.client import NanoRpcTyped
# from nanowallet.utils.decorators import NanoResult
# from nanowallet.models import RefundedReceivable, Receivable
# from nanowallet.errors import BlockNotFoundError


# @pytest.fixture
# def seed():
#     return "b632a26208f2f5f36871b4ae952c2f81415728e0ab402c7d7e995f586bef5fd6"


# @pytest.fixture
# def index():
#     return 0


# @pytest.fixture
# def account():
#     return "nano_3pay1r1z3fs5t3qix93oyt97np76qcp41afa7nzet9cem1ea334eoasot38s"


# @pytest.fixture
# def mock_rpc_typed():
#     """Fixture that provides a mocked NanoRpcTyped instance"""
#     mock = AsyncMock(spec=NanoRpcTyped)
#     return mock


# @pytest.fixture
# def mock_rpc(mock_rpc_typed):
#     rpc = NanoWalletRpc(url="mock://test")
#     # Only mock the underlying _rpc, not the wrapper methods
#     rpc._rpc = mock_rpc_typed
#     return rpc


# @pytest.mark.asyncio
# @patch("nanowallet.wallets.mixins.NanoWalletBlock")
# async def test_refund_receivables_happy_path(
#     mock_block, mock_rpc_typed, mock_rpc, seed, index
# ):
#     """Test the happy path of refunding two receivable blocks"""

#     # Configure mock_block for proper operation
#     mock_block_instance = Mock()
#     mock_block_instance.work_block_hash = "work_block_hash"
#     mock_block_instance.json.return_value = {"mock": "block_json"}
#     mock_block.return_value = mock_block_instance

#     # Set up the mocks for receivable blocks
#     mock_rpc_typed.receivable.return_value = {
#         "blocks": {
#             "block1": "1000000000000000000000000000000",  # 1 Nano
#             "block2": "2000000000000000000000000000000",  # 2 Nano
#         }
#     }

#     # Set up blocks_info to provide sender info for the blocks
#     def blocks_info_side_effect(hashes, **kwargs):
#         if "block1" in hashes:
#             return {
#                 "blocks": {
#                     "block1": {
#                         "amount": "1000000000000000000000000000000",
#                         "block_account": "nano_1epochfo6oqad7mgn6rcikgka9bps43nedz1kpm1t35e579mregxgf6srhpd",
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         elif "block2" in hashes:
#             return {
#                 "blocks": {
#                     "block2": {
#                         "amount": "2000000000000000000000000000000",
#                         "block_account": "nano_3msudh3xmsk7qfa31gpas4auqd815fo1hb57e4yheiczcez59eqeng8hrsob",
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         elif "receive_hash1" in hashes:
#             return {
#                 "blocks": {
#                     "receive_hash1": {
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         elif "receive_hash2" in hashes:
#             return {
#                 "blocks": {
#                     "receive_hash2": {
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         elif "send_hash1" in hashes:
#             return {
#                 "blocks": {
#                     "send_hash1": {
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         elif "send_hash2" in hashes:
#             return {
#                 "blocks": {
#                     "send_hash2": {
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         return {"error": "Block not found"}

#     mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect

#     # Mock account_info
#     # Return account not found for the first call, then account info for subsequent calls
#     mock_rpc_typed.account_info.side_effect = [
#         # First call: account not found
#         {"error": "Account not found"},
#         # After first receive of block1 (since receivables are sorted by hash)
#         {
#             "frontier": "receive_hash1",
#             "representative": "nano_3rrop...16nf",
#             "balance": "1000000000000000000000000000000",
#         },
#         # After first send of block1
#         {
#             "frontier": "send_hash1",
#             "representative": "nano_3rrop...16nf",
#             "balance": "0",
#         },
#         # After second receive of block2
#         {
#             "frontier": "receive_hash2",
#             "representative": "nano_3rrop...16nf",
#             "balance": "2000000000000000000000000000000",
#         },
#         # After second send of block2
#         {
#             "frontier": "send_hash2",
#             "representative": "nano_3rrop...16nf",
#             "balance": "0",
#         },
#     ]

#     # Mock work generation
#     mock_rpc_typed.work_generate.return_value = {"work": "work_value"}

#     # Mock block processing
#     mock_rpc_typed.process.side_effect = [
#         {"hash": "receive_hash1"},  # First receive - block1
#         {"hash": "send_hash1"},  # First send - block1
#         {"hash": "receive_hash2"},  # Second receive - block2
#         {"hash": "send_hash2"},  # Second send - block2
#     ]

#     # Create wallet and call refund_receivables - patch list_receivables to avoid double call
#     wallet = create_wallet_from_seed(mock_rpc, seed, index)

#     # Mock list_receivables to avoid double calls to receivable
#     with patch.object(wallet, "list_receivables") as mock_list_receivables:
#         mock_list_receivables.return_value = NanoResult(
#             value=[
#                 Receivable(
#                     block_hash="block1", amount_raw=1000000000000000000000000000000
#                 ),
#                 Receivable(
#                     block_hash="block2", amount_raw=2000000000000000000000000000000
#                 ),
#             ]
#         )

#         result = await wallet.refund_receivables(
#             threshold_raw=1, wait_confirmation=True
#         )

#         # Verify result
#         assert result.success is True
#         refunded = result.unwrap()
#         assert len(refunded) == 2

#         # Verify first refunded receivable
#         assert refunded[0].receivable_hash == "block1"
#         assert (
#             refunded[0].sender_account
#             == "nano_1epochfo6oqad7mgn6rcikgka9bps43nedz1kpm1t35e579mregxgf6srhpd"
#         )
#         assert refunded[0].amount_raw == 1000000000000000000000000000000
#         assert refunded[0].receive_block_hash == "receive_hash1"
#         assert refunded[0].refund_send_block_hash == "send_hash1"
#         assert refunded[0].confirmed is True

#         # Verify second refunded receivable
#         assert refunded[1].receivable_hash == "block2"
#         assert (
#             refunded[1].sender_account
#             == "nano_3msudh3xmsk7qfa31gpas4auqd815fo1hb57e4yheiczcez59eqeng8hrsob"
#         )
#         assert refunded[1].amount_raw == 2000000000000000000000000000000
#         assert refunded[1].receive_block_hash == "receive_hash2"
#         assert refunded[1].refund_send_block_hash == "send_hash2"
#         assert refunded[1].confirmed is True

#         # Verify expected calls
#         assert mock_list_receivables.call_count == 1
#         assert (
#             mock_rpc_typed.blocks_info.call_count == 6
#         )  # 2 for blocks, 4 for confirmations
#         assert (
#             mock_rpc_typed.account_info.call_count == 5
#         )  # Initial + 4 after operations
#         assert mock_rpc_typed.process.call_count == 4  # 2 receives + 2 sends
#         assert mock_rpc_typed.work_generate.call_count == 4  # 2 receives + 2 sends


# @pytest.mark.asyncio
# async def test_refund_receivables_no_pending(mock_rpc_typed, mock_rpc, seed, index):
#     """Test refund_receivables with no pending blocks"""

#     # Mock no pending blocks - this is what list_receivables will actually see
#     mock_rpc_typed.receivable.return_value = {"blocks": ""}

#     # Create wallet and call refund_receivables
#     wallet = create_wallet_from_seed(mock_rpc, seed, index)

#     # Use mock to make list_receivables return an empty list directly
#     with patch.object(wallet, "list_receivables") as mock_list_receivables:
#         mock_list_receivables.return_value = NanoResult(value=[])

#         result = await wallet.refund_receivables()

#         # Verify empty result
#         assert result.success is True
#         assert result.unwrap() == []

#         # Verify expected calls
#         assert mock_list_receivables.call_count == 1
#         assert mock_rpc_typed.blocks_info.call_count == 0
#         assert mock_rpc_typed.process.call_count == 0


# @pytest.mark.asyncio
# async def test_refund_receivables_below_threshold(
#     mock_rpc_typed, mock_rpc, seed, index
# ):
#     """Test refund_receivables with blocks below the threshold"""

#     # Mock pending blocks below threshold
#     mock_rpc_typed.receivable.return_value = {
#         "blocks": {
#             "block1": "1000000000000000000000000000000",  # 1 Nano
#             "block2": "500000000000000000000000000000",  # 0.5 Nano
#         }
#     }

#     # First, need to properly mock the blocks_info for block1
#     def blocks_info_side_effect(hashes, **kwargs):
#         if "block1" in hashes:
#             return {
#                 "blocks": {
#                     "block1": {
#                         "amount": "1000000000000000000000000000000",
#                         "block_account": "nano_1epochfo6oqad7mgn6rcikgka9bps43nedz1kpm1t35e579mregxgf6srhpd",
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         return {"blocks": {}}

#     mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect

#     # Mock account_info for the receive and send
#     mock_rpc_typed.account_info.side_effect = [
#         {"error": "Account not found"},  # Initial check
#         {
#             "frontier": "receive_hash1",
#             "representative": "nano_rep",
#             "balance": "1000000000000000000000000000000",
#         },  # After receive
#         {
#             "frontier": "send_hash1",
#             "representative": "nano_rep",
#             "balance": "0",
#         },  # After send
#     ]

#     # Mock work generation and processing
#     mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
#     mock_rpc_typed.process.side_effect = [
#         {"hash": "receive_hash1"},  # Receive block
#         {"hash": "send_hash1"},  # Send block
#     ]

#     # Set threshold to 750000000000000000000000000000 (0.75 Nano)
#     threshold_raw = 750000000000000000000000000000

#     # Create wallet and call refund_receivables
#     wallet = create_wallet_from_seed(mock_rpc, seed, index)

#     # Mock list_receivables to directly return filtered list based on threshold
#     with patch.object(wallet, "list_receivables") as mock_list_receivables:
#         # Only return block1 (1 Nano) since block2 (0.5 Nano) is below threshold
#         mock_list_receivables.return_value = NanoResult(
#             value=[
#                 Receivable(
#                     block_hash="block1", amount_raw=1000000000000000000000000000000
#                 )
#             ]
#         )

#         # Mock _build_block as well for the test to properly work
#         with patch.object(wallet, "_build_block") as mock_build_block:
#             mock_block = Mock()
#             mock_block.work_block_hash = "work_block_hash"
#             mock_block.json.return_value = {"mock": "block_json"}
#             mock_build_block.return_value = mock_block

#             result = await wallet.refund_receivables(threshold_raw=threshold_raw)

#             # Verify result with only the block above threshold
#             assert result.success is True
#             refunded = result.unwrap()
#             assert len(refunded) == 1
#             assert refunded[0].receivable_hash == "block1"
#             assert refunded[0].amount_raw == 1000000000000000000000000000000
#             assert (
#                 refunded[0].sender_account
#                 == "nano_1epochfo6oqad7mgn6rcikgka9bps43nedz1kpm1t35e579mregxgf6srhpd"
#             )

#             # Verify expected calls
#             assert mock_list_receivables.call_count == 1
#             assert mock_rpc_typed.blocks_info.call_count >= 1
#             assert mock_rpc_typed.process.call_count == 2  # 1 receive + 1 send


# @pytest.mark.asyncio
# async def test_refund_receivables_block_info_error(
#     mock_rpc_typed, mock_rpc, seed, index
# ):
#     """Test refund_receivables when block_info fails for one block"""

#     # Mock pending blocks
#     mock_rpc_typed.receivable.return_value = {
#         "blocks": {
#             "good_block": "1000000000000000000000000000000",  # 1 Nano
#             "bad_block": "2000000000000000000000000000000",  # 2 Nano - will cause error
#         }
#     }

#     # Set up blocks_info to fail for the bad block
#     def blocks_info_side_effect(hashes, **kwargs):
#         if "bad_block" in hashes:
#             raise BlockNotFoundError(f"Block not found bad_block")

#         if "good_block" in hashes:
#             return {
#                 "blocks": {
#                     "good_block": {
#                         "amount": "1000000000000000000000000000000",
#                         "block_account": "nano_1epochfo6oqad7mgn6rcikgka9bps43nedz1kpm1t35e579mregxgf6srhpd",
#                         "confirmed": "true",
#                     }
#                 }
#             }

#         return {"blocks": {}}

#     mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect

#     # Mock account_info to return appropriate values
#     mock_rpc_typed.account_info.side_effect = [
#         {"error": "Account not found"},
#         {
#             "frontier": "receive_hash1",
#             "representative": "nano_3rrop...16nf",
#             "balance": "1000000000000000000000000000000",
#         },
#         {
#             "frontier": "send_hash1",
#             "representative": "nano_3rrop...16nf",
#             "balance": "0",
#         },
#     ]

#     # Mock work generation and processing
#     mock_rpc_typed.work_generate.return_value = {"work": "work_value"}
#     mock_rpc_typed.process.side_effect = [
#         {"hash": "receive_hash1"},
#         {"hash": "send_hash1"},
#     ]

#     # Create wallet and call refund_receivables
#     wallet = create_wallet_from_seed(mock_rpc, seed, index)

#     # Mock list_receivables to avoid double calls to receivable
#     with patch.object(wallet, "_build_block") as mock_build_block:
#         # Configure the build_block mock to return a properly mocked block
#         mock_block = Mock()
#         mock_block.work_block_hash = "work_block_hash"
#         mock_block.json.return_value = {"mock": "block_json"}
#         mock_build_block.return_value = mock_block

#         # Mock list_receivables to avoid double calls to receivable
#         with patch.object(wallet, "list_receivables") as mock_list_receivables:
#             mock_list_receivables.return_value = NanoResult(
#                 value=[
#                     Receivable(
#                         block_hash="bad_block",
#                         amount_raw=2000000000000000000000000000000,
#                     ),
#                     Receivable(
#                         block_hash="good_block",
#                         amount_raw=1000000000000000000000000000000,
#                     ),
#                 ]
#             )

#             result = await wallet.refund_receivables()

#             # Verify result - should have processed good_block but skipped bad_block
#             assert result.success is True
#             refunded = result.unwrap()
#             assert len(refunded) == 1
#             assert refunded[0].receivable_hash == "good_block"

#             # Verify expected calls
#             assert mock_list_receivables.call_count == 1
#             assert mock_rpc_typed.blocks_info.call_count >= 2  # Called for both blocks
#             assert mock_rpc_typed.process.call_count == 2  # 1 receive + 1 send


# @pytest.mark.asyncio
# @patch("nanowallet.wallets.mixins.NanoWalletBlock")
# async def test_refund_receivables_process_error(
#     mock_block, mock_rpc_typed, mock_rpc, seed, index
# ):
#     """Test refund_receivables when process fails for a send block"""

#     # Configure mock_block for proper operation
#     mock_block_instance = Mock()
#     mock_block_instance.work_block_hash = "work_block_hash"
#     mock_block_instance.json.return_value = {"mock": "block_json"}
#     mock_block.return_value = mock_block_instance

#     # Mock pending blocks
#     mock_rpc_typed.receivable.return_value = {
#         "blocks": {
#             "block1": "1000000000000000000000000000000",  # 1 Nano
#             "block2": "2000000000000000000000000000000",  # 2 Nano - will fail during send
#         }
#     }

#     # Set up blocks_info to provide sender info
#     def blocks_info_side_effect(hashes, **kwargs):
#         if "block1" in hashes:
#             return {
#                 "blocks": {
#                     "block1": {
#                         "amount": "1000000000000000000000000000000",
#                         "block_account": "nano_1epochfo6oqad7mgn6rcikgka9bps43nedz1kpm1t35e579mregxgf6srhpd",
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         elif "block2" in hashes:
#             return {
#                 "blocks": {
#                     "block2": {
#                         "amount": "2000000000000000000000000000000",
#                         "block_account": "nano_3msudh3xmsk7qfa31gpas4auqd815fo1hb57e4yheiczcez59eqeng8hrsob",
#                         "confirmed": "true",
#                     }
#                 }
#             }
#         return {"blocks": {}}

#     mock_rpc_typed.blocks_info.side_effect = blocks_info_side_effect

#     # Mock account_info
#     mock_rpc_typed.account_info.side_effect = [
#         {"error": "Account not found"},  # Initial check
#         # After first receive - block1 (since we're sorting by hash)
#         {
#             "frontier": "receive_hash1",
#             "representative": "nano_3rrop...16nf",
#             "balance": "1000000000000000000000000000000",
#         },
#         # After first send - block1
#         {
#             "frontier": "send_hash1",
#             "representative": "nano_3rrop...16nf",
#             "balance": "0",
#         },
#         # After second receive - block2
#         {
#             "frontier": "receive_hash2",
#             "representative": "nano_3rrop...16nf",
#             "balance": "2000000000000000000000000000000",
#         },
#     ]

#     # Mock work generation
#     mock_rpc_typed.work_generate.return_value = {"work": "work_value"}

#     # Mock process to succeed for first refund but fail on second refund's send
#     mock_rpc_typed.process.side_effect = [
#         {"hash": "receive_hash1"},  # First receive - block1
#         {"hash": "send_hash1"},  # First send - block1
#         {"hash": "receive_hash2"},  # Second receive - block2
#         {"error": "Some processing error"},  # Second send - block2 FAIL
#     ]

#     # Create wallet and call refund_receivables
#     wallet = create_wallet_from_seed(mock_rpc, seed, index)

#     # Mock list_receivables to avoid double calls to receivable
#     with patch.object(wallet, "list_receivables") as mock_list_receivables:
#         mock_list_receivables.return_value = NanoResult(
#             value=[
#                 Receivable(
#                     block_hash="block1", amount_raw=1000000000000000000000000000000
#                 ),
#                 Receivable(
#                     block_hash="block2", amount_raw=2000000000000000000000000000000
#                 ),
#             ]
#         )

#         result = await wallet.refund_receivables()

#         # Verify result - should have processed first block successfully
#         assert result.success is True
#         refunded = result.unwrap()
#         assert len(refunded) == 1
#         assert refunded[0].receivable_hash == "block1"

#         # Second block was received but not sent back due to error, so no complete refund

#         # Verify expected calls
#         assert mock_list_receivables.call_count == 1
#         assert mock_rpc_typed.blocks_info.call_count == 2
#         assert mock_rpc_typed.process.call_count == 4  # All 4 calls should be made
