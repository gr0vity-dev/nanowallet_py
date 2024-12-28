from __future__ import annotations
from typing import Dict, Any, Optional


class NanoException(Exception):
    """Base exception for all Nano-related errors."""

    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


class TimeoutException(NanoException):
    """Raised when an operation times out (e.g., confirmation waiting)."""

    def __init__(self, message: str):
        super().__init__(message, "TIMEOUT")


class InvalidAmountError(NanoException):
    """Raised when an amount is invalid (negative, wrong type, etc.)."""

    def __init__(self, message: str):
        super().__init__(message, "INVALID_AMOUNT")


class RpcError(NanoException):
    """Raised when the RPC call returns an error."""

    def __init__(self, message: str):
        super().__init__(message, "RPC_ERROR")


class InsufficientBalanceError(NanoException):
    """Raised when account has insufficient balance for operation."""

    def __init__(self, message: str):
        super().__init__(message, "INSUFFICIENT_BALANCE")


class InvalidAccountError(NanoException):
    """Raised when account is invalid."""

    def __init__(self, message: str):
        super().__init__(message, "INVALID_ACCOUNT")


class BlockNotFoundError(NanoException):
    """Raised when block hash cannot be found."""

    def __init__(self, message: str):
        super().__init__(message, "BLOCK_NOT_FOUND")


class InvalidSeedError(NanoException):
    """Raised when seed format is invalid."""

    def __init__(self, message: str):
        super().__init__(message, "INVALID_SEED")


class InvalidIndexError(NanoException):
    """Raised when account index is invalid."""

    def __init__(self, message: str):
        super().__init__(message, "INVALID_INDEX")


#
# Utility functions for interpreting RPC responses
#

def has_error(response: Dict[str, Any]) -> bool:
    """Check if response contains an error field."""
    return 'error' in response


def get_error(response: Dict[str, Any]) -> Optional[str]:
    """Get error message from response if present."""
    return response["error"] if has_error(response) else None


def no_error(response: Dict[str, Any]) -> bool:
    """Check if response contains no error."""
    return not has_error(response)


def zero_balance(response: Dict[str, Any]) -> bool:
    """Check if response indicates zero balance."""
    return ('balance' in response and response['balance'] == '0')


def account_not_found(response: Dict[str, Any]) -> bool:
    """Check if response indicates account not found error."""
    error_msg = get_error(response)
    return error_msg == 'Account not found'


def block_not_found(response: Dict[str, Any]) -> bool:
    """Check if response indicates block not found error."""
    error_msg = get_error(response)
    return error_msg == 'Block not found'


def try_raise_error(response: Dict[str, Any]):
    """
    Raise a NanoException if response contains an error.
    Tries to pick a more specific exception type based on the error message.
    """
    if has_error(response):
        error_msg = get_error(response) or "Unknown error"
        full_msg = f"{error_msg}"

        if account_not_found(response):
            raise InvalidAccountError(full_msg)
        elif block_not_found(response):
            raise BlockNotFoundError(full_msg)
        else:
            raise RpcError(full_msg)
