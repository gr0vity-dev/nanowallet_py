from nano_lib_py.accounts import (
    validate_account_id,
    get_account_public_key,
    generate_account_private_key,
    get_account_id,
    AccountIDPrefix,
)
from ..errors import InvalidAccountError


class AccountHelper:
    """Encapsulates all account-related nano_lib_py operations"""

    @staticmethod
    def validate_account(account_id: str) -> bool:
        """Validate a Nano account ID"""
        try:
            if validate_account_id(account_id):
                return True
            else:
                return False
        except Exception as e:
            raise InvalidAccountError(f"Invalid account ID: {account_id}") from e

    @staticmethod
    def get_account_address(private_key: str) -> str:
        """Get account ID from private key"""
        try:
            return get_account_id(private_key=private_key)
        except Exception as e:
            raise ValueError(f"Invalid private key: {private_key[:10]}...") from e

    @staticmethod
    def get_public_key(account_id: str) -> str:
        """Get public key from account ID"""
        try:
            return get_account_public_key(account_id=account_id)
        except Exception as e:
            raise InvalidAccountError(f"Invalid account ID: {account_id}") from e

    @staticmethod
    def generate_private_key(seed: str, index: int) -> str:
        """Generate private key from seed and index"""
        try:
            return generate_account_private_key(seed, index)
        except Exception as e:
            raise ValueError(f"Invalid seed: {seed[:10]}... or index: {index}") from e

    @staticmethod
    def get_account(*, public_key=None, private_key=None) -> str:
        """Get account ID from public key"""
        try:
            return get_account_id(
                public_key=public_key,
                private_key=private_key,
                prefix=AccountIDPrefix.NANO,
            )
        except Exception as e:
            public_key = public_key or ""
            private_key = private_key or ""
            raise InvalidAccountError(
                f"Invalid public key: {public_key} or private key: {private_key[:10]}..."
            ) from e
