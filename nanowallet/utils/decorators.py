import functools
import logging
from typing import TypeVar, Callable, Awaitable
from ..errors import NanoException

logger = logging.getLogger(__name__)

R = TypeVar("R")
T = TypeVar("T")


class NanoResult:
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
                self.error, self.error_code if self.error_code else "UNKNOWN_ERROR"
            )
        return self.value


def reload_after(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            result = await func(self, *args, **kwargs)
            await self.reload()
            return result
        except Exception as e:
            raise e

    return wrapper


def handle_errors(
    func: Callable[..., Awaitable[R]]
) -> Callable[..., Awaitable[NanoResult]]:
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            result = await func(self, *args, **kwargs)
            return NanoResult(value=result)
        except NanoException as e:
            # Known Nano-related exception
            logger.error(
                "NanoException in %s: %s", func.__name__, e.message, exc_info=True
            )
            return NanoResult(error=e.message, error_code=e.code)
        except Exception as e:
            # For any other exception, preserve the original message so existing tests pass.
            # The test expects the original error message (e.g. ValueError("No funds available to refund."))
            logger.error(
                "Unexpected error in %s: %s", func.__name__, str(e), exc_info=True
            )
            return NanoResult(error=str(e), error_code="UNEXPECTED_ERROR")

    return wrapper
