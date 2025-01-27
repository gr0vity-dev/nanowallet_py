# nanowallet/wallets/seed_based.py
from typing import Optional
from ..models import WalletConfig
from ..libs.account_helper import AccountHelper
from ..errors import InvalidSeedError, InvalidIndexError
from .key_based import NanoWalletKey
from ..libs.rpc import NanoWalletRpc

# Constants
SEED_LENGTH = 64  # Length of hex seed
MAX_INDEX = 4294967295  # Maximum index value (2^32 - 1)


class NanoWallet(NanoWalletKey):
    """Seed-based implementation of NanoWallet"""

    def __init__(
        self,
        rpc: NanoWalletRpc,
        seed: str,
        index: int,
        config: Optional[WalletConfig] = None,
    ):
        """
        Initialize wallet with a seed and index.

        :param rpc: RPC client
        :param seed: Seed for generating private key (64 character hex string)
        :param index: Index for generating private key (0 to 2^32-1)
        :param config: Optional wallet configuration
        :raises InvalidSeedError: If seed is invalid
        :raises InvalidIndexError: If index is invalid
        """
        # Validate seed
        if not isinstance(seed, str) or len(seed) != 64:
            raise InvalidSeedError("Seed must be a 64 character hex string")
        try:
            int(seed, 16)
        except ValueError:
            raise InvalidSeedError("Seed must be a valid hex string")

        # Validate index
        if not isinstance(index, int) or index < 0 or index > MAX_INDEX:
            raise InvalidIndexError(f"Index must be between 0 and {MAX_INDEX}")

        private_key = AccountHelper.generate_private_key(seed.lower(), index)
        super().__init__(rpc, private_key, config)

        # Store seed and index for reference
        self.seed = seed.lower()
        self.index = index
