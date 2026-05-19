"""
Call Queue Statistics (CQ-001, CQ-002)
======================================

Lightweight stub service that exposes the queue-position/wait-time/queue-depth
read API expected by the call routing dashboard.

When a real queue (Twilio TaskRouter, Telnyx, etc.) is wired this module should
be swapped for a provider-backed implementation. Until then, statistics are
derived from `VoiceCallSession` rows in `queued` / `ringing` state — this gives
operators a directionally-correct number without depending on an external
service.

All functions are defensive: if the DB is unavailable or the model is missing
they return sensible defaults so the call-routing UI never explodes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Average handle-time used for wait-time estimation when no historical data
# exists. Tuned for inbound mortgage support calls.
DEFAULT_AVG_HANDLE_SECONDS: int = 180  # 3 minutes
QUEUED_STATUSES = {"queued", "ringing", "pending"}


def _safe_session():
    """Lazy-import a DB session so this module is importable in unit tests
    without the full backend bootstrap."""
    try:
        from database import SessionLocal
        return SessionLocal()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("call_queue_stats: SessionLocal unavailable (%s)", exc)
        return None


def _safe_model():
    try:
        from database.models.voice_call_session import VoiceCallSession
        return VoiceCallSession
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("call_queue_stats: VoiceCallSession model unavailable (%s)", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_queue_depth(organization_id: Optional[int] = None) -> int:
    """Return the number of calls currently waiting in queue.

    Falls back to 0 if the DB layer is not available.
    """
    Session = _safe_session()
    Model = _safe_model()
    if Session is None or Model is None:
        return 0
    try:
        q = Session.query(Model).filter(Model.status.in_(list(QUEUED_STATUSES)))
        if organization_id is not None:
            q = q.filter(Model.organization_id == organization_id)
        return int(q.count())
    except Exception as exc:
        logger.warning("get_queue_depth fallback: %s", exc)
        return 0
    finally:
        try:
            Session.close()
        except Exception as _exc:  # noqa: BLE001
            pass


def get_queue_position(
    call_id: str, organization_id: Optional[int] = None
) -> Dict[str, Any]:
    """Return queue position info for the given call.

    Position is 1-indexed (1 = next in line). Returns position=0 and
    in_queue=False if the call is not currently queued.
    """
    Session = _safe_session()
    Model = _safe_model()
    if Session is None or Model is None:
        return {"call_id": call_id, "position": 0, "in_queue": False, "queue_depth": 0}

    try:
        q = Session.query(Model).filter(Model.status.in_(list(QUEUED_STATUSES)))
        if organization_id is not None:
            q = q.filter(Model.organization_id == organization_id)
        queued = q.order_by(Model.started_at.asc()).all()

        position = 0
        for idx, row in enumerate(queued, start=1):
            if str(getattr(row, "session_uuid", "")) == str(call_id) or str(
                getattr(row, "id", "")
            ) == str(call_id):
                position = idx
                break

        return {
            "call_id": call_id,
            "position": position,
            "in_queue": position > 0,
            "queue_depth": len(queued),
        }
    except Exception as exc:
        logger.warning("get_queue_position fallback: %s", exc)
        return {"call_id": call_id, "position": 0, "in_queue": False, "queue_depth": 0}
    finally:
        try:
            Session.close()
        except Exception as _exc:  # noqa: BLE001
            pass


def get_wait_time_estimate(
    organization_id: Optional[int] = None,
    avg_handle_seconds: int = DEFAULT_AVG_HANDLE_SECONDS,
) -> Dict[str, Any]:
    """Estimate caller wait time using `queue_depth * avg_handle_seconds`.

    Returns a dict with seconds + a humanised string for UI consumption.
    """
    depth = get_queue_depth(organization_id=organization_id)
    seconds = int(depth * avg_handle_seconds)
    return {
        "queue_depth": depth,
        "avg_handle_seconds": avg_handle_seconds,
        "estimated_wait_seconds": seconds,
        "estimated_wait_minutes": round(seconds / 60.0, 1),
    }


__all__ = [
    "DEFAULT_AVG_HANDLE_SECONDS",
    "QUEUED_STATUSES",
    "get_queue_depth",
    "get_queue_position",
    "get_wait_time_estimate",
]
