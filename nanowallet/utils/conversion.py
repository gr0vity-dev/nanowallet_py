from decimal import Decimal
from typing import Union
from nanowallet.errors import InvalidAmountError


RAW_PER_NANO = Decimal("10") ** 30


def raw_to_nano(raw_amount: Union[int, str, Decimal], decimal_places=30) -> Decimal:
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
