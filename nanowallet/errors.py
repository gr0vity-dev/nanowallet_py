@staticmethod
def has_error(response):
    """Check if response contains no error."""
    if 'error' in response:
        return True
    return False


@staticmethod
def get_error(response):
    """Get error message from response if present."""
    if has_error(response):
        return response["error"]
    return None


@staticmethod
def no_error(response):
    """Check if response contains no error."""
    if has_error(response):
        return False
    return True


@staticmethod
def raise_error(response, more=""):
    """Raise ValueError if response contains an error."""
    if has_error(response):
        raise RpcError(
            f"Error raised by RPC : {get_error(response)}{more}")


@staticmethod
def zero_balance(response):
    """Check if response indicates zero balance."""
    if 'balance' in response:
        if response['balance'] == '0':
            return True
    return False


@staticmethod
def account_not_found(response):
    """Check if response indicates account not found error."""
    if get_error(response) == 'Account not found':
        return True
    return False


@staticmethod
def block_not_found(response):
    """Check if response indicates block not found error."""
    if get_error(response) == 'Block not found':
        return True
    return False


class RpcError(ValueError):
    """Utility class for handling RPC response errors."""
    pass


class InsufficientBalanceError(ValueError):
    """Raised when account has insufficient balance for operation"""
    pass


class InvalidAccountError(ValueError):
    """Raised when account is invalid"""
    pass


class BlockNotFoundError(ValueError):
    """Raised when block hash cannot be found"""
    pass


class InvalidSeedError(ValueError):
    """Raised when seed format is invalid"""
    pass


class InvalidIndexError(ValueError):
    """Raised when account index is invalid"""
    pass
