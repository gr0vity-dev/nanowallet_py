from __future__ import annotations
import functools
from typing import TypeVar, Callable, Awaitable
from dataclasses import dataclass
import logging
from decimal import Decimal, ROUND_DOWN
import decimal

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

RAW_PER_NANO = Decimal('10') ** 30


def raw_to_nano(raw_amount, decimal_places=30):
    """
    Convert raw amount to nano with configurable decimal places precision
    1 nano = 10^30 raw

    Args:
        raw_amount: The raw amount to convert
        decimal_places: Number of decimal places to keep (default: 30)
    """
    # Convert to Decimal for precise calculation
    raw_decimal = Decimal(str(raw_amount))
    nano_amount = raw_decimal / Decimal('1000000000000000000000000000000')

    # Convert to string with full precision
    # Use 'f' format to avoid scientific notation
    nano_str = format(nano_amount, 'f')

    # Split into integer and decimal parts
    if '.' in nano_str:
        int_part, dec_part = nano_str.split('.')
        # Truncate decimal part to specified places
        dec_part = dec_part[:decimal_places]
        # Pad with zeros if needed
        dec_part = dec_part.ljust(decimal_places, '0')
        # Recombine
        truncated_str = f"{int_part}.{dec_part}"
    else:
        # Handle whole numbers
        truncated_str = f"{nano_str}.{'0' * decimal_places}"

    # Convert back to Decimal using the string
    return Decimal(truncated_str.rstrip('0').rstrip('.') if '.' in truncated_str else truncated_str)


def nano_to_raw(nano_amount):
    """
    Convert nano amount to raw
    1 nano = 10^30 raw
    """
    # Convert to Decimal for precise calculation
    nano_decimal = Decimal(str(nano_amount))
    if nano_decimal < 0:
        raise ValueError("Negative values are not allowed")
    raw_amount = nano_decimal * Decimal('1000000000000000000000000000000')
    # Return as integer
    return int(raw_amount)


def validate_nano_amount(amount: Decimal | str | int) -> Decimal:
    """
    Validates and converts an amount to Decimal.

    Args:
        amount: Amount in NANO as Decimal, string, or int

    Returns:
        Decimal: The validated amount

    Raises:
        TypeError: If amount is float or invalid type
        ValueError: If amount is negative or invalid format
    """
    if isinstance(amount, float):
        raise TypeError(
            "Float values are not allowed for NANO amounts - use Decimal or string to maintain precision")

    if not isinstance(amount, (Decimal, str, int)):
        raise TypeError(f"Invalid type for NANO amount: {type(amount)}")

    try:
        amount_decimal = Decimal(str(amount))
        if amount_decimal < 0:
            raise ValueError("NANO amount cannot be negative")
        return amount_decimal
    except decimal.InvalidOperation:
        raise ValueError(f"Invalid NANO amount format: {amount}")

# DECORATORS


def reload_after(func: Callable) -> Callable:
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
        Unwraps the NanoResult, returning the value if successful or raising an exception if there's an error.
        :return: The value contained in the NanoResult.
        :raises NanoException: If the NanoResult contains an error.
        """
        if self.error:
            raise NanoException(self.error, self.error_code)
        return self.value


class NanoException(Exception):
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


def handle_errors(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[NanoResult]]:
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            result = await func(self, *args, **kwargs)
            return NanoResult(value=result)
        except NanoException as e:
            logger.error("NanoException in %s: %s",
                         func.__name__, e.message, exc_info=True)
            return NanoResult(error=e.message, error_code=e.code)
        except Exception as e:
            logger.error("Unexpected error in %s: %s",
                         func.__name__, str(e), exc_info=True)
            return NanoResult(error=str(e), error_code="UNEXPECTED_ERROR")
    return wrapper
