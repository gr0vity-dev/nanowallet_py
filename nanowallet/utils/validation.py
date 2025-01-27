from decimal import Decimal
from typing import Union
from nano_lib_py import validate_account_id
from nanowallet.errors import InvalidAmountError


def validate_nano_amount(amount: Union[Decimal, str, int]) -> Decimal:
    """
    Validate and convert a Nano amount to Decimal.

    Args:
        amount: Amount in NANO (as Decimal, string, or int)

    Returns:
        Decimal: Validated amount

    Raises:
        TypeError: If amount is float or invalid type
        ValueError: If amount is negative or invalid format
    """
    if isinstance(amount, float):
        raise InvalidAmountError("Amount cannot be float, use Decimal/str/int")

    # Convert to Decimal
    if isinstance(amount, (str, int)):
        try:
            amount_decimal = Decimal(str(amount))
        except:
            raise InvalidAmountError("Invalid amount format")
    elif isinstance(amount, Decimal):
        amount_decimal = amount
    else:
        raise InvalidAmountError("Amount must be Decimal, string or integer")

    if amount_decimal < 0:
        raise InvalidAmountError("Negative values are not allowed")

    return amount_decimal


def validate_account(account: str) -> bool:
    """
    Validate a Nano account address.

    Args:
        account: Nano account address to validate

    Returns:
        bool: True if valid, False otherwise
    """
    return validate_account_id(account)
