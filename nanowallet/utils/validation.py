# nanowallet/utils/validation.py
from decimal import Decimal
from typing import Union
from ..errors import InvalidAmountError
from ..libs.account_helper import AccountHelper


def validate_account(account: str) -> bool:
    """
    Validate a Nano account ID.

    Args:
        account: The account ID to validate

    Returns:
        bool: True if valid, False otherwise
    """
    return AccountHelper.validate_account(account)


def validate_nano_amount(amount: Union[str, Decimal, int]) -> Decimal:
    """
    Validate and convert a Nano amount to Decimal.

    Args:
        amount: The amount to validate (as string, Decimal or int)

    Returns:
        Decimal: The validated amount as a Decimal

    Raises:
        InvalidAmountError: If amount is invalid
    """
    if isinstance(amount, float):
        raise InvalidAmountError(
            f"Float values [{amount}] are not allowed to avoid precision loss"
        )

    try:
        amount_decimal = Decimal(str(amount))
        if amount_decimal < 0:
            raise InvalidAmountError("Negative values are not allowed")
        return amount_decimal
    except (ValueError, TypeError, ArithmeticError) as e:
        raise InvalidAmountError(f"Invalid amount format: {e}") from e
