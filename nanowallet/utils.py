from __future__ import annotations
import functools
from typing import TypeVar, Callable, Awaitable, Any, Dict, Generic
from dataclasses import dataclass


def nano_to_raw(nano_amount: float) -> int:
    """
    Converts Nano amount to raw.
    """
    return int(nano_amount * (10 ** 30))


def raw_to_nano(raw_amount: int) -> float:
    """
    Converts raw amount to Nano.
    """
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
            return NanoResult(error=e.message, error_code=e.code)
        except Exception as e:
            return NanoResult(error=str(e), error_code="UNEXPECTED_ERROR")
    return wrapper
