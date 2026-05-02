"""BlueBubbles health monitoring."""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_consecutive_failures = 0
_last_check: datetime | None = None
_last_status: str = "unknown"


async def check_bluebubbles_health(client) -> dict:
    """Ping BB server and return health status."""
    global _consecutive_failures, _last_check, _last_status
    try:
        ok = await client.ping()
        _consecutive_failures = 0 if ok else _consecutive_failures + 1
        _last_status = "healthy" if ok else "degraded"
    except Exception as e:
        _consecutive_failures += 1
        _last_status = "unreachable"
        logger.warning("imessage.health.ping_failed", extra={"error": str(e), "consecutive": _consecutive_failures})

    _last_check = datetime.now(timezone.utc)

    if _consecutive_failures >= 3:
        logger.error("imessage.health.critical", extra={"consecutive_failures": _consecutive_failures})

    return {
        "status": _last_status,
        "consecutive_failures": _consecutive_failures,
        "last_check": _last_check.isoformat() if _last_check else None,
    }


def get_health_status() -> dict:
    return {
        "status": _last_status,
        "consecutive_failures": _consecutive_failures,
        "last_check": _last_check.isoformat() if _last_check else None,
    }
