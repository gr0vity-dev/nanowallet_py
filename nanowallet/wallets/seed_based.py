from typing import Optional
from nano_lib_py import generate_account_private_key
from nanorpc.client import NanoRpcTyped
from ..models import WalletConfig
from ..errors import InvalidSeedError, InvalidIndexError
from .key_based import NanoWalletKey

# Constants
SEED_LENGTH = 64  # Length of hex seed
MAX_INDEX = 4294967295  # Maximum index value (2^32 - 1)


class NanoWallet(NanoWalletKey):
    """Full implementation of NanoWallet with seed-based initialization"""

    def __init__(
        self,
        rpc: NanoRpcTyped,
        seed: str,
        index: int,
        config: Optional[WalletConfig] = None,
    ):
        """
        Initialize wallet with a seed and index.

        :param rpc: RPC client
        :param seed: Wallet seed (64 character hex string)
        :param index: Account index
        :param config: Optional wallet configuration
        """
        # Validate seed
        if (
            not isinstance(seed, str)
            or len(seed) != SEED_LENGTH
            or not all(c in "0123456789abcdefABCDEF" for c in seed)
        ):
            raise InvalidSeedError("Seed must be a 64 character hex string")

        # Validate index
        if not isinstance(index, int) or index < 0 or index > MAX_INDEX:
            raise InvalidIndexError(f"Index must be between 0 and {MAX_INDEX}")

        # Generate private key from seed and index
        private_key = generate_account_private_key(seed.lower(), index)

        # Initialize with the generated private key
        super().__init__(rpc, private_key, config)

        # Store seed and index for reference
        self.seed = seed.lower()
        self.index = index
