import logging
import asyncio
import time
from typing import Optional, Dict, Any

from .rpc_component import RpcComponent
from ...models import WalletConfig, UnsignedBlockDetails
from ...errors import NanoException, TimeoutException, BlockNotFoundError

logger = logging.getLogger(__name__)


class BlockSubmissionComponent:
    """Component responsible for generating work, assembling, submitting signed blocks
    and waiting for confirmation."""

    def __init__(self, rpc_component: RpcComponent, config: WalletConfig):
        self._rpc_component = rpc_component
        self.config = config
        logger.debug("BlockSubmissionComponent initialized.")

    async def submit(
        self,
        unsigned_details: UnsignedBlockDetails,
        signature: str,
        wait_confirmation: bool = False,
        timeout: int = 30,
    ) -> str:
        """
        Generates work, assembles the final block JSON using prepared data and signature,
        submits it, and optionally waits for confirmation.
        """
        logger.debug(
            "BlockSubmissionComponent: Starting submission for hash_to_sign: %s",
            unsigned_details.hash_to_sign,
        )

        # --- Generate Work ---
        try:
            logger.debug(
                "BlockSubmissionComponent: Generating work for hash_for_work: %s",
                unsigned_details.hash_for_work,
            )
            work = await self._rpc_component.generate_work(
                pow_hash=unsigned_details.hash_for_work,
                use_peers=self.config.use_work_peers,
            )
            logger.info("BlockSubmissionComponent: Work generated: %s", work)
        except NanoException as e:
            logger.error("BlockSubmissionComponent: Failed to generate work: %s", e)
            raise  # Re-raise RPC/Nano exceptions
        except Exception as e:
            logger.exception(
                "BlockSubmissionComponent: Unexpected error during work generation."
            )
            raise NanoException(
                f"Failed during work generation: {e}", "SUBMIT_WORK_GEN_ERROR"
            ) from e

        # --- Assemble Final Block JSON ---
        # Note: balance needs to be stringified for JSON RPC
        block_json = {
            "type": "state",  # State blocks are standard
            "account": unsigned_details.account,
            "previous": unsigned_details.previous,
            "representative": unsigned_details.representative,
            "balance": str(unsigned_details.balance_raw),
            "link": unsigned_details.link,
            "signature": signature,
            "work": work,
        }
        logger.debug(
            "BlockSubmissionComponent: Assembled block JSON for processing."
        )  # Avoid logging full JSON unless needed

        # --- Process Block ---
        try:
            block_hash = await self._rpc_component.process_block(block_json)
            logger.info(
                "BlockSubmissionComponent: Block processed successfully. Final Hash: %s",
                block_hash,
            )

            # Optional: Verify final_hash against expected hash_to_sign if desired
            if block_hash != unsigned_details.hash_to_sign:
                logger.warning(
                    "BlockSubmissionComponent: Processed hash %s differs from prepared hash_to_sign %s!",
                    block_hash,
                    unsigned_details.hash_to_sign,
                )
                # This shouldn't happen if logic is correct, but worth noting.
                # The hash returned by process is the definitive one.

        except Exception as e:
            logger.error("BlockSubmissionComponent: Failed to process block: %s", e)
            if isinstance(e, NanoException):
                raise
            raise NanoException(f"Block submission failed: {e}", "SUBMIT_ERROR") from e

        # --- Wait for Confirmation (Optional) ---
        if wait_confirmation:
            logger.info(
                "BlockSubmissionComponent: Waiting for confirmation for block %s (timeout=%ds)...",
                block_hash,
                timeout,
            )
            confirmed = await self._wait_for_confirmation(
                block_hash, timeout=timeout, raise_on_timeout=True
            )
            if confirmed:
                logger.info("BlockSubmissionComponent: Block %s confirmed.", block_hash)
            # else: _wait_for_confirmation raises TimeoutException

        return block_hash

    async def _wait_for_confirmation(
        self, block_hash: str, timeout: int = 30, raise_on_timeout: bool = False
    ) -> bool:
        """Waits for a block to be confirmed by the network."""
        start_time = time.time()
        delay = 0.5
        max_delay = 5
        attempt = 1
        logger.debug(
            "BlockSubmissionComponent: Starting confirmation wait for %s timeout=%s",
            block_hash,
            timeout,
        )

        while time.time() - start_time < timeout:
            try:
                block_info = await self._rpc_component.block_info(block_hash)
                confirmed = block_info.get("confirmed", "false") == "true"
                elapsed = time.time() - start_time

                if confirmed:
                    logger.info(
                        "BlockSubmissionComponent: Confirmed %s after %.2fs",
                        block_hash,
                        elapsed,
                    )
                    return True

                logger.debug(
                    "BlockSubmissionComponent: Check %d: %s confirmed=%s, elapsed=%.2fs",
                    attempt,
                    block_hash[:10],
                    confirmed,
                    elapsed,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                attempt += 1

            except BlockNotFoundError:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(
                        "Block %s not found & timeout (%.2fs)", block_hash, elapsed
                    )
                    break

                logger.debug(
                    "Block %s not found, retrying in %.2fs", block_hash[:10], delay
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                attempt += 1

            except Exception as e:
                elapsed = time.time() - start_time
                logger.exception(
                    "Error confirming %s (attempt %d, elapsed %.2fs): %s",
                    block_hash,
                    attempt,
                    elapsed,
                    e,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                attempt += 1

        elapsed = time.time() - start_time
        logger.warning(
            "Confirmation wait timed out after %.2fs for %s", elapsed, block_hash
        )
        if raise_on_timeout:
            raise TimeoutException(
                f"Block {block_hash} not confirmed within {timeout}s"
            )
        return False
