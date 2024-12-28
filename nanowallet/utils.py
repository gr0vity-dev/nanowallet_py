from __future__ import annotations
import functools
from typing import TypeVar, Callable, Awaitable, Union
from decimal import Decimal
import decimal
import logging

from .errors import NanoException, InvalidAmountError

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

RAW_PER_NANO = Decimal('10') ** 30

R = TypeVar('R')
T = TypeVar('T')


class NanoResult():
    def __init__(self, value: T = None, error: str = None, error_code: str = None):
        self.value = value
        self.error = error
        self.error_code = error_code

    @property
    def success(self) -> bool:
        return self.error is None

    def __bool__(self) -> bool:
        return self.success

    def unwrap(self) -> T:
        """
        Unwraps the NanoResult, returning the value if successful or
        raising a NanoException if there's an error.
        """
        if self.error:
            raise NanoException(
                self.error, self.error_code if self.error_code else "UNKNOWN_ERROR")
        return self.value


#
# Conversion utilities
#

def raw_to_nano(raw_amount: Union[int, str, Decimal], decimal_places=30) -> Decimal:
    """
    Convert raw amount to nano with configurable decimal places precision.
    1 nano = 10^30 raw
    """
    raw_decimal = Decimal(str(raw_amount))
    nano_amount = raw_decimal / RAW_PER_NANO

    # Convert to string with full precision
    nano_str = format(nano_amount, 'f')

    # Split into integer and decimal parts
    if '.' in nano_str:
        int_part, dec_part = nano_str.split('.')
        # Truncate decimal part to specified places
        dec_part = dec_part[:decimal_places]
        # Pad with zeros if needed
        dec_part = dec_part.ljust(decimal_places, '0')
        truncated_str = f"{int_part}.{dec_part}"
    else:
        # Handle whole numbers
        truncated_str = f"{nano_str}.{'0' * decimal_places}"

    # Convert back to Decimal
    return Decimal(truncated_str.rstrip('0').rstrip('.') if '.' in truncated_str else truncated_str)


def nano_to_raw(nano_amount: Union[str, Decimal, int]) -> int:
    """
    Convert nano amount to raw
    1 nano = 10^30 raw
    """
    nano_decimal = Decimal(str(nano_amount))
    if nano_decimal < 0:
        raise InvalidAmountError("Negative values are not allowed")
    raw_amount = nano_decimal * RAW_PER_NANO
    return int(raw_amount)


def validate_nano_amount(amount: Union[Decimal, str, int]) -> Decimal:
    """
    Validates and converts an amount to Decimal.

    Raises InvalidAmountError on invalid input.
    """
    if isinstance(amount, float):
        raise InvalidAmountError(
            "Float values are not allowed for NANO amounts - use Decimal or string to maintain precision")

    if not isinstance(amount, (Decimal, str, int)):
        raise InvalidAmountError(
            f"Invalid type for NANO amount: {type(amount)}")

    try:
        amount_decimal = Decimal(str(amount))
        if amount_decimal < 0:
            raise InvalidAmountError("Negative values are not allowed")
        return amount_decimal
    except decimal.InvalidOperation:
        raise InvalidAmountError(f"Invalid NANO amount format: {amount}")


#
# Decorators
#

def reload_after(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            result = await func(self, *args, **kwargs)
            await self.reload()
            return result
        except Exception as e:
            await self.reload()
            raise e
    return wrapper


def handle_errors(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[NanoResult]]:
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            result = await func(self, *args, **kwargs)
            return NanoResult(value=result)
        except NanoException as e:
            # Known Nano-related exception
            logger.error("NanoException in %s: %s",
                         func.__name__, e.message, exc_info=True)
            return NanoResult(error=e.message, error_code=e.code)
        except Exception as e:
            # For any other exception, preserve the original message so existing tests pass.
            # The test expects the original error message (e.g. ValueError("No funds available to refund."))
            logger.error("Unexpected error in %s: %s",
                         func.__name__, str(e), exc_info=True)
            return NanoResult(error=str(e), error_code="UNEXPECTED_ERROR")
    return wrapper
