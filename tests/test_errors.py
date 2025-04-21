import pytest

from nanowallet.errors import (
    NanoException,
    TimeoutException,
    InvalidAmountError,
    RpcError,
    InsufficientBalanceError,
    InvalidAccountError,
    BlockNotFoundError,
    InvalidSeedError,
    InvalidIndexError,
    has_error,
    get_error,
    no_error,
    zero_balance,
    account_not_found,
    block_not_found,
    try_raise_error,
)


class TestNanoExceptions:
    """Tests for the Nano exception classes."""

    def test_nano_exception_base(self):
        """Test the base NanoException class."""
        exception = NanoException("Test message", "TEST_CODE")
        assert exception.message == "Test message"
        assert exception.code == "TEST_CODE"
        assert str(exception) == "Test message"

    def test_timeout_exception(self):
        """Test the TimeoutException class."""
        exception = TimeoutException("Operation timed out")
        assert exception.message == "Operation timed out"
        assert exception.code == "TIMEOUT"
        assert isinstance(exception, NanoException)

    def test_invalid_amount_error(self):
        """Test the InvalidAmountError class."""
        exception = InvalidAmountError("Invalid amount provided")
        assert exception.message == "Invalid amount provided"
        assert exception.code == "INVALID_AMOUNT"
        assert isinstance(exception, NanoException)

    def test_rpc_error(self):
        """Test the RpcError class."""
        exception = RpcError("RPC call failed")
        assert exception.message == "RPC call failed"
        assert exception.code == "RPC_ERROR"
        assert isinstance(exception, NanoException)

    def test_insufficient_balance_error(self):
        """Test the InsufficientBalanceError class."""
        exception = InsufficientBalanceError("Not enough funds")
        assert exception.message == "Not enough funds"
        assert exception.code == "INSUFFICIENT_BALANCE"
        assert isinstance(exception, NanoException)

    def test_invalid_account_error(self):
        """Test the InvalidAccountError class."""
        exception = InvalidAccountError("Invalid account address")
        assert exception.message == "Invalid account address"
        assert exception.code == "INVALID_ACCOUNT"
        assert isinstance(exception, NanoException)

    def test_block_not_found_error(self):
        """Test the BlockNotFoundError class."""
        exception = BlockNotFoundError("Block hash not found")
        assert exception.message == "Block hash not found"
        assert exception.code == "BLOCK_NOT_FOUND"
        assert isinstance(exception, NanoException)

    def test_invalid_seed_error(self):
        """Test the InvalidSeedError class."""
        exception = InvalidSeedError("Invalid seed format")
        assert exception.message == "Invalid seed format"
        assert exception.code == "INVALID_SEED"
        assert isinstance(exception, NanoException)

    def test_invalid_index_error(self):
        """Test the InvalidIndexError class."""
        exception = InvalidIndexError("Invalid account index")
        assert exception.message == "Invalid account index"
        assert exception.code == "INVALID_INDEX"
        assert isinstance(exception, NanoException)


class TestErrorUtilityFunctions:
    """Tests for the error utility functions."""

    def test_has_error(self):
        """Test has_error function."""
        assert has_error({"error": "Some error"}) is True
        assert has_error({"result": "Success"}) is False
        assert has_error({}) is False

    def test_get_error(self):
        """Test get_error function."""
        assert get_error({"error": "Some error"}) == "Some error"
        assert get_error({"result": "Success"}) is None
        assert get_error({}) is None

    def test_no_error(self):
        """Test no_error function."""
        assert no_error({"error": "Some error"}) is False
        assert no_error({"result": "Success"}) is True
        assert no_error({}) is True

    def test_zero_balance(self):
        """Test zero_balance function."""
        assert zero_balance({"balance": "0"}) is True
        assert zero_balance({"balance": "1000"}) is False
        assert zero_balance({"other_field": "value"}) is False
        assert zero_balance({}) is False

    def test_account_not_found(self):
        """Test account_not_found function."""
        assert account_not_found({"error": "Account not found"}) is True
        assert account_not_found({"error": "Other error"}) is False
        assert account_not_found({"result": "Success"}) is False
        assert account_not_found({}) is False

    def test_block_not_found(self):
        """Test block_not_found function."""
        assert block_not_found({"error": "Block not found"}) is True
        assert block_not_found({"error": "Other error"}) is False
        assert block_not_found({"result": "Success"}) is False
        assert block_not_found({}) is False

    def test_try_raise_error_no_error(self):
        """Test try_raise_error with no error."""
        # Should not raise any exception
        try_raise_error({"result": "Success"})
        try_raise_error({})

    def test_try_raise_error_block_not_found(self):
        """Test try_raise_error with block not found error."""
        with pytest.raises(BlockNotFoundError) as excinfo:
            try_raise_error({"error": "Block not found"})
        assert excinfo.value.message == "Block not found"
        assert excinfo.value.code == "BLOCK_NOT_FOUND"

    def test_try_raise_error_account_not_found(self):
        """Test try_raise_error with account not found error."""
        # According to the implementation, account_not_found doesn't raise an exception
        try_raise_error({"error": "Account not found"})

    def test_try_raise_error_generic_error(self):
        """Test try_raise_error with a generic error."""
        with pytest.raises(RpcError) as excinfo:
            try_raise_error({"error": "Some generic error"})
        assert excinfo.value.message == "Some generic error"
        assert excinfo.value.code == "RPC_ERROR"

    def test_try_raise_error_empty_error(self):
        """Test try_raise_error with an empty error."""
        with pytest.raises(RpcError) as excinfo:
            try_raise_error({"error": ""})
        assert excinfo.value.message == "Unknown error"
        assert excinfo.value.code == "RPC_ERROR"

    def test_try_raise_error_none_error(self):
        """Test try_raise_error with a None error."""
        with pytest.raises(RpcError) as excinfo:
            try_raise_error({"error": None})
        assert excinfo.value.message == "Unknown error"
        assert excinfo.value.code == "RPC_ERROR"
