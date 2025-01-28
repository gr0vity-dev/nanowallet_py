from typing import List
from ..models import ReceivedBlock, AmountReceived


def sum_received_amount(receive_all_response: List[ReceivedBlock]) -> AmountReceived:
    """
    Sums the amount_raw values from a list of receivable responses.
    Args:
        receive_all_response: A list of dictionaries containing 'amount_raw'
    Returns:
        dict: A dictionary with the total amount in raw and Nano
    """
    total_amount_raw = sum(item.amount_raw for item in receive_all_response)
    return AmountReceived(total_amount_raw)
