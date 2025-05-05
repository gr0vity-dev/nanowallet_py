import logging
from typing import List

from .rpc_component import RpcComponent
from ...models import WalletBalance, AccountInfo, Receivable
from ...utils.state_utils import StateUtils
from ...errors import NanoException

logger = logging.getLogger(__name__)


class StateManager:
    """Manages the wallet's state (balance, account info, receivables)."""

    def __init__(self, account: str, rpc_component: RpcComponent):
        if not account:
            # Handle case where account might be invalid initially (e.g., bad private key)
            # StateUtils.init_account_state handles None gracefully
            logger.warning(
                "StateManager initialized with invalid/empty account: %s", account
            )
            account = None  # Ensure StateUtils receives None if invalid

        self.account = account
        self._rpc_component = rpc_component
        # Initialize state using StateUtils
        self._balance_info, self._account_info, self._receivable_blocks = (
            StateUtils.init_account_state(self.account)
        )
        logger.debug("StateManager initialized for account: %s", self.account)

    async def reload(self) -> None:
        """Reloads the wallet state from the network via RPC."""
        if not self.account:
            logger.warning(
                "StateManager: Cannot reload, account is invalid or not set."
            )
            # Ensure state remains initialized but empty/default
            self._balance_info, self._account_info, self._receivable_blocks = (
                StateUtils.init_account_state(self.account)
            )
            return

        logger.debug("StateManager: Reloading state for account %s", self.account)
        try:
            # Use the component's RPC interface
            balance, account_info, receivables = await StateUtils.reload_state(
                rpc=self._rpc_component.rpc, account=self.account
            )
            # Update internal state
            self._balance_info = balance
            self._account_info = account_info
            self._receivable_blocks = receivables
            logger.debug("StateManager: State reload complete for %s", self.account)
        except Exception as e:
            logger.error(
                "StateManager: Exception during state reload for %s: %s",
                self.account,
                e,
                exc_info=True,
            )
            # Fallback to initial state on error to maintain a consistent state object
            init_balance, init_account_info, init_receivables = (
                StateUtils.init_account_state(self.account)
            )
            self._balance_info = init_balance
            self._account_info = init_account_info
            self._receivable_blocks = init_receivables
            # Re-raise as NanoException for higher layers (like @handle_errors)
            raise NanoException(f"Failed state reload: {e}", "RELOAD_ERROR") from e

    # --- State Access Properties ---

    @property
    def balance_info(self) -> WalletBalance:
        """Returns the current balance information."""
        return self._balance_info

    @property
    def account_info(self) -> AccountInfo:
        """Returns the current account information."""
        return self._account_info

    @property
    def receivable_blocks(self) -> List[Receivable]:
        """Returns the current receivable blocks mapping (hash -> amount_raw str)."""
        # Return a copy to prevent external modification? For now, return direct ref.
        return self._receivable_blocks
