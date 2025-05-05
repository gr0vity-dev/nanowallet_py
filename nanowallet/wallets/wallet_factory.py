from typing import Optional
from ..models import WalletConfig
from ..libs.account_helper import AccountHelper
from ..errors import InvalidSeedError, InvalidIndexError, InvalidPrivateKeyError
from ..libs.rpc import INanoRpc
from .protocols import IAuthenticatedWallet
from .authenticated_impl import NanoWalletAuthenticated
from .read_only_impl import NanoWalletReadOnly

# Constants
SEED_LENGTH = 64  # Length of hex seed
MAX_INDEX = 4294967295  # Maximum index value (2^32 - 1)


def create_wallet_from_account(
    rpc: INanoRpc, account: str, config: Optional[WalletConfig] = None
) -> IAuthenticatedWallet:
    """
    Creates an authenticated wallet instance from an account address.
    """
    return NanoWalletReadOnly(rpc=rpc, account=account, config=config)


def create_wallet_from_seed(
    rpc: INanoRpc, seed: str, index: int, config: Optional[WalletConfig] = None
) -> IAuthenticatedWallet:
    """
    Creates an authenticated wallet instance from a seed and index.

    Args:
        rpc: RPC client for blockchain interaction
        seed: Seed for generating private key (64 character hex string)
        index: Index for generating private key (0 to 2^32-1)
        config: Optional wallet configuration

    Returns:
        An authenticated wallet implementation

    Raises:
        InvalidSeedError: If seed is invalid
        InvalidIndexError: If index is invalid
        ValueError: If private key generation fails
    """
    # Validate seed
    if not isinstance(seed, str) or len(seed) != SEED_LENGTH:
        raise InvalidSeedError("Seed must be a 64 character hex string")
    try:
        int(seed, 16)  # Validate hex
    except ValueError as e:
        raise InvalidSeedError("Seed must be a valid hex string") from e

    # Validate index
    if not isinstance(index, int) or not (0 <= index <= MAX_INDEX):
        raise InvalidIndexError(f"Index must be an integer between 0 and {MAX_INDEX}")

    # Convert seed to lowercase for consistency
    seed_lower = seed.lower()

    try:
        # Generate private key from seed and index
        private_key = AccountHelper.generate_private_key(seed_lower, index)
    except Exception as e:
        # Handle potential errors during key generation
        raise ValueError(f"Failed to generate private key from seed/index: {e}") from e

    # Create and return the authenticated wallet implementation
    return NanoWalletAuthenticated(rpc=rpc, private_key=private_key, config=config)


def create_wallet_from_private_key(
    rpc: INanoRpc, private_key: str, config: Optional[WalletConfig] = None
) -> IAuthenticatedWallet:
    """
    Creates an authenticated wallet instance from a private key.

    Args:
        rpc: RPC client for blockchain interaction
        private_key: Private key for generating wallet (64 character hex string)
        config: Optional wallet configuration

    Returns:
        An authenticated wallet implementation

    Raises:
        ValueError: If the private key is invalid
    """
    # Validate private key
    if not isinstance(private_key, str) or len(private_key) != SEED_LENGTH:
        raise InvalidPrivateKeyError("Invalid private key")
    try:
        int(private_key, 16)  # Validate hex
    except ValueError as e:
        raise InvalidPrivateKeyError("Invalid private key") from e

    # Convert private key to lowercase for consistency
    private_key_lower = private_key.lower()

    # Create and return the authenticated wallet implementation
    return NanoWalletAuthenticated(
        rpc=rpc, private_key=private_key_lower, config=config
    )
