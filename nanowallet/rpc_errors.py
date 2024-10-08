
def account_not_found(response):
    if 'error' in response:
        if response['error'] == 'Account not found':
            return True
    return False


def no_error(response):
    if 'error' in response:
        return False
    return True


def raise_error(response, more=""):
    if 'error' in response:
        raise ValueError(f"Error raised by RPC : {response['error']}{more}")


def get_error(response):
    if 'error' in response:
        return response['error']
    return None


def zero_balance(response):
    if 'balance' in response:
        if response['balance'] == '0':
            return True
    return False


def block_not_found(response):
    if 'error' in response:
        if response['error'] == 'Block not found':
            return True
    return False
