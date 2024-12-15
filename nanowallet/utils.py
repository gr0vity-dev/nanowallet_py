from __future__ import annotations
import functools
from typing import TypeVar, Callable, Awaitable
from dataclasses import dataclass
import logging
from decimal import Decimal, ROUND_DOWN, getcontext
import decimal

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Set precision for Decimal - allowing for 133 million (9 digits) plus 30 decimal places
getcontext().prec = 40

RAW_PER_NANO = Decimal('10') ** 30


def nano_to_raw_short(amount: Decimal | str) -> int:
    # Convert to Decimal and round to 6 decimal places
    amount_decimal = Decimal(str(amount))
    truncated = amount_decimal.quantize(Decimal('0.000001'), rounding=ROUND_DOWN)
    return nano_to_raw(truncated)
    

def nano_to_raw(amount_nano: Decimal | str) -> int:
    """
    Converts Nano amount to raw.
    
    Args:
        amount_nano: Amount in NANO as Decimal or string
        
    Returns:
        int: Amount in raw units
        
    Raises:
        ValueError: If amount is negative or invalid, or has more than 30 decimal places
    """
    try:
        amount_decimal = Decimal(str(amount_nano))
    except (decimal.InvalidOperation, TypeError):
        raise ValueError(f"Invalid NANO amount: {amount_nano}")

    if amount_decimal < 0:
        raise ValueError("NANO amount cannot be negative")

    # Convert to normalized string without scientific notation
    amount_str = format(amount_decimal, 'f')  # 'f' format forces fixed-point notation

    if '.' in amount_str:
        whole, fraction = amount_str.split('.')
    else:
        whole, fraction = amount_str, ''

    if len(fraction) > 30:
        raise ValueError("NANO amount has more than 30 decimal places")

    whole = whole.lstrip('0') or '0'
    fraction = fraction.ljust(30, '0')
    raw_str = whole + fraction
    raw_str = raw_str.lstrip('0') or '0'

    return int(raw_str)


def raw_to_nano(raw_amount: int) -> Decimal:
    return Decimal(str(raw_amount)) / RAW_PER_NANO    

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
