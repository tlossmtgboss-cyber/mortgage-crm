"""
LangGraph checkpoint persistence.

Uses PostgreSQL (via the existing Railway database) to persist agent state
at every node boundary. Enables:
- Crash recovery (restart continues from last checkpoint)
- Human-in-the-loop (pause → approve → resume)
- Audit trail of intermediate reasoning steps

Gated by ENABLE_CHECKPOINTING=true to avoid connection pressure until verified.
"""

import asyncio
import atexit
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_checkpointer = None
_init_lock = threading.Lock()

_SETUP_TIMEOUT_SECONDS = 15


async def get_checkpointer() -> Optional[object]:
    """Return async LangGraph checkpointer if enabled, else None.

    Returns None (no checkpointing) unless ENABLE_CHECKPOINTING=true.
    Uses AsyncPostgresSaver to avoid blocking the event loop during ainvoke().
    Thread-safe singleton initialization via lock.
    """
    global _checkpointer

    if os.getenv("ENABLE_CHECKPOINTING", "false").lower() != "true":
        return None

    if _checkpointer is not None:
        return _checkpointer

    with _init_lock:
        if _checkpointer is not None:
            return _checkpointer

        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                logger.warning("[CHECKPOINT] DATABASE_URL not set — checkpointing disabled")
                return None

            cp = AsyncPostgresSaver.from_conn_string(database_url)
            await asyncio.wait_for(cp.setup(), timeout=_SETUP_TIMEOUT_SECONDS)
            _checkpointer = cp
            atexit.register(_cleanup_sync)
            logger.info("[CHECKPOINT] AsyncPostgresSaver initialized — durable execution enabled")
            return _checkpointer
        except asyncio.TimeoutError:
            logger.warning(f"[CHECKPOINT] setup() timed out after {_SETUP_TIMEOUT_SECONDS}s — checkpointing disabled")
            return None
        except ImportError:
            logger.info("[CHECKPOINT] langgraph-checkpoint-postgres not installed — checkpointing disabled")
            return None
        except Exception as e:
            logger.warning(f"[CHECKPOINT] Failed to initialize checkpointer: {e}")
            return None


def _cleanup_sync():
    """Best-effort cleanup of checkpointer connections on process exit."""
    global _checkpointer
    if _checkpointer is None:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_checkpointer.conn.close())
        else:
            loop.run_until_complete(_checkpointer.conn.close())
    except Exception as e:
        logger.debug(f"[CHECKPOINT] Cleanup error (non-critical): {e}")
    _checkpointer = None
