
def account_not_found(response):
    if 'error' in response:
        if response['error'] == 'Account not found':
            return True
    return False


def zero_balance(response):
    if 'balance' in response:
        if response['balance'] == '0':
            return True
    return False
