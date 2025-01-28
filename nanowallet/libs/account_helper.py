from nano_lib_py.accounts import (
    validate_account_id,
    get_account_public_key,
    generate_account_private_key,
    get_account_id,
    AccountIDPrefix,
)


class AccountHelper:
    """Encapsulates all account-related nano_lib_py operations"""

    @staticmethod
    def validate_account(account_id: str) -> bool:
        """Validate a Nano account ID"""
        return validate_account_id(account_id)

    @staticmethod
    def get_account_address(private_key: str) -> str:
        """Get account ID from private key"""
        return get_account_id(private_key=private_key)

    @staticmethod
    def get_public_key(account_id: str) -> str:
        """Get public key from account ID"""
        return get_account_public_key(account_id=account_id)

    @staticmethod
    def generate_private_key(seed: str, index: int) -> str:
        """Generate private key from seed and index"""
        return generate_account_private_key(seed, index)

    @staticmethod
    def get_account(*, public_key=None, private_key=None) -> str:
        """Get account ID from public key"""
        return get_account_id(
            public_key=public_key,
            private_key=private_key,
            prefix=AccountIDPrefix.NANO,
        )
