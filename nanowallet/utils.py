from __future__ import annotations
import functools
from typing import TypeVar, Callable, Awaitable
from dataclasses import dataclass
import logging
# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


def nano_to_raw(amount_nano: float) -> int:
    """
    Converts Nano amount to raw.
    """
    if float(amount_nano) < 0:
        raise ValueError("Nano amount is negative")

    amount_nano = str(amount_nano)

    if '.' in amount_nano:
        whole, fraction = amount_nano.split('.')
    else:
        whole, fraction = amount_nano, ''

    if len(fraction) > 30:
        raise ValueError("Nano amount has more than 30 decimal places.")

    whole = whole.lstrip('0') or '0'
    fraction = fraction.ljust(30, '0')
    raw_str = whole + fraction
    raw_str = raw_str.lstrip('0') or '0'

    return int(raw_str)


def raw_to_nano(raw_amount: int) -> float:
    return int(raw_amount) / (10 ** 30)


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
