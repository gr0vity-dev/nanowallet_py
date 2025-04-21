import functools
import logging
from typing import Generic, TypeVar, Callable, Awaitable, Optional
from ..errors import NanoException

logger = logging.getLogger(__name__)

T = TypeVar("T")


class NanoResult(Generic[T]):
    """
    Represents the result of an operation with optional value and error details.
    """

    def __init__(
        self,
        value: Optional[T] = None,  # Allow None but preserve type T
        error: Optional[str] = None,
        error_code: Optional[str] = None,
    ):
        self.value = value
        self.error = error
        self.error_code = error_code

    @property
    def success(self) -> bool:
        """
        Checks if the operation was successful.
        """
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
        return self.value  # Type checker knows this is T now


R = TypeVar("R")


def reload_after(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
    """
    Decorator to reload the wallet after the operation.
    """

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
    func: Callable[..., Awaitable[R]],
) -> Callable[..., Awaitable[NanoResult[R]]]:  # Return NanoResult parameterized with R
    """
    Decorator to handle errors and return a NanoResult.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> NanoResult[R]:
        try:
            result = await func(*args, **kwargs)
            return NanoResult[R](value=result)  # Explicitly set type parameter
        except NanoException as e:
            return NanoResult[R](
                error=e.message, error_code=e.code
            )  # Still R as type param
        except Exception as e:
            return NanoResult[R](error=str(e), error_code="UNEXPECTED_ERROR")

    return wrapper
