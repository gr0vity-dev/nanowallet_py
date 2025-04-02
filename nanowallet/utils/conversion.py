from decimal import Decimal
from typing import Union, List, Dict
from nanowallet.errors import InvalidAmountError
from .validation import validate_nano_amount


RAW_PER_NANO = Decimal("10") ** 30


def _raw_to_nano(raw_amount: Union[int, str, Decimal], decimal_places=30) -> Decimal:
    """
    Convert raw amount to nano with configurable decimal places precision.
    1 nano = 10^30 raw
    """
    raw_decimal = Decimal(str(raw_amount))
    nano_amount = raw_decimal / RAW_PER_NANO

    # Convert to string with full precision
    nano_str = format(nano_amount, "f")

    # Split into integer and decimal parts
    if "." in nano_str:
        int_part, dec_part = nano_str.split(".")
        # Truncate decimal part to specified places
        dec_part = dec_part[:decimal_places]
        # Pad with zeros if needed
        dec_part = dec_part.ljust(decimal_places, "0")
        truncated_str = f"{int_part}.{dec_part}"
    else:
        # Handle whole numbers
        truncated_str = f"{nano_str}.{'0' * decimal_places}"

    # Convert back to Decimal
    return Decimal(
        truncated_str.rstrip("0").rstrip(".") if "." in truncated_str else truncated_str
    )


def _nano_to_raw(nano_amount: Union[str, Decimal, int]) -> int:
    """
    Convert nano amount to raw
    1 nano = 10^30 raw
    """
    nano_decimal = Decimal(str(nano_amount))
    if nano_decimal < 0:
        raise InvalidAmountError("Negative values are not allowed")
    raw_amount = nano_decimal * RAW_PER_NANO
    return int(raw_amount)


def raw_to_nano(amount_raw: int, decimal_places=6) -> Decimal:
    """
    Converts raw amount to Nano, truncating to 6 decimal places.

    Args:
        amount_raw: Amount in raw units

    Returns:
        Decimal: Amount in NANO, truncated to 6 decimal places
    """
    return _raw_to_nano(amount_raw, decimal_places=decimal_places)


def nano_to_raw(amount_nano: Decimal | str | int, precision=30) -> int:
    """
    Converts Nano amount to raw amount.

    Args:
        amount_nano: The amount in Nano (as Decimal, string, or int)

    Returns:
        int: The amount in raw

    Raises:
        TypeError: If amount is float or invalid type
        ValueError: If amount is negative or invalid format
    """
    amount_decimal = validate_nano_amount(amount_nano)
    return _nano_to_raw(
        _raw_to_nano(_nano_to_raw(amount_decimal), decimal_places=precision)
    )
