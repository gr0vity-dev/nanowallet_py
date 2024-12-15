class RpcError():
    """Utility class for handling RPC response errors."""
    
    @staticmethod
    def account_not_found(response):
        """Check if response indicates account not found error."""
        if 'error' in response:
            if response['error'] == 'Account not found':
                return True
        return False

    @staticmethod
    def no_error(response):
        """Check if response contains no error."""
        if 'error' in response:
            return False
        return True

    @staticmethod 
    def raise_error(response, more=""):
        """Raise ValueError if response contains an error."""
        if 'error' in response:
            raise ValueError(f"Error raised by RPC : {response['error']}{more}")

    @staticmethod
    def get_error(response):
        """Get error message from response if present."""
        if 'error' in response:
            return response['error']
        return None

    @staticmethod
    def zero_balance(response):
        """Check if response indicates zero balance."""
        if 'balance' in response:
            if response['balance'] == '0':
                return True
        return False

    @staticmethod
    def block_not_found(response):
        """Check if response indicates block not found error."""
        if 'error' in response:
            if response['error'] == 'Block not found':
                return True
        return False




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
