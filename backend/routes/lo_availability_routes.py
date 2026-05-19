"""
LO Availability Routes — Real-time presence and transfer readiness.

Endpoints for managing loan officer availability status, weekly schedules,
and querying which LOs are ready to receive live call transfers.

Prefix: /api/v1/availability
"""

import logging
import threading
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PERF-011: In-memory TTL cache for LO availability lookups (30s TTL)
# ---------------------------------------------------------------------------

_avail_cache: Dict[int, Tuple[bool, float]] = {}  # user_id -> (is_available, expires_ts)
_avail_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 30


def _cache_get(user_id: int) -> Optional[bool]:
    """Return cached availability or None if miss/expired."""
    with _avail_cache_lock:
        entry = _avail_cache.get(user_id)
        if entry is None:
            return None
        is_available, expires_at = entry
        if datetime.now(timezone.utc).timestamp() > expires_at:
            del _avail_cache[user_id]
            return None
        return is_available


def _cache_set(user_id: int, is_available: bool) -> None:
    """Store availability in cache with TTL."""
    with _avail_cache_lock:
        expires_at = datetime.now(timezone.utc).timestamp() + _CACHE_TTL_SECONDS
        _avail_cache[user_id] = (is_available, expires_at)


def _cache_invalidate(user_id: int) -> None:
    """Invalidate cached entry for a user (call on status change)."""
    with _avail_cache_lock:
        _avail_cache.pop(user_id, None)

router = APIRouter(prefix="/api/v1/availability", tags=["LO Availability"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class StatusUpdate(BaseModel):
    status: str = Field(..., description="One of: available, busy, on_call, dnd, offline, away")
    status_reason: Optional[str] = Field(None, max_length=255)
    auto_status: Optional[bool] = None
    max_concurrent_transfers: Optional[int] = Field(None, ge=1, le=10)


class ScheduleSlot(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday ... 6=Sunday")
    start_time: str = Field(..., description="HH:MM format")
    end_time: str = Field(..., description="HH:MM format")
    is_available: bool = True


class ScheduleUpdate(BaseModel):
    slots: List[ScheduleSlot]
    timezone: Optional[str] = None


class CallEvent(BaseModel):
    user_id: int
    event_type: str = Field(..., description="call_start or call_end")
    call_id: Optional[str] = None


class AvailabilityResponse(BaseModel):
    user_id: int
    status: str
    status_reason: Optional[str] = None
    auto_status: bool = True
    in_schedule_window: bool = False
    active_transfer_count: int = 0
    max_concurrent_transfers: int = 1
    can_receive_transfer: bool = False
    last_heartbeat_at: Optional[str] = None
    updated_at: Optional[str] = None


class AvailableLOResponse(BaseModel):
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    status: str = "available"
    active_transfer_count: int = 0
    max_concurrent_transfers: int = 1


# =============================================================================
# Helpers — lazy model imports to avoid circular imports at load time
# =============================================================================

_models_loaded = False
_LOAvailability = None
_LOAvailabilitySchedule = None
_User = None

VALID_STATUSES = {"available", "busy", "on_call", "dnd", "offline", "away"}
HEARTBEAT_STALE_MINUTES = 5


def _ensure_models():
    """Lazy-import models on first use."""
    global _models_loaded, _LOAvailability, _LOAvailabilitySchedule, _User
    if _models_loaded:
        return
    from database.models.lo_availability import LOAvailability, LOAvailabilitySchedule
    from database.models.core import User
    _LOAvailability = LOAvailability
    _LOAvailabilitySchedule = LOAvailabilitySchedule
    _User = User
    _models_loaded = True


def _ensure_table(db: Session):
    """Create the tables if they don't exist (production-safe)."""
    try:
        from database.models.lo_availability import LOAvailability, LOAvailabilitySchedule
        from db import engine
        LOAvailability.__table__.create(engine, checkfirst=True)
        LOAvailabilitySchedule.__table__.create(engine, checkfirst=True)
    except Exception as e:
        logger.warning("Table creation check failed (non-fatal): %s", e)


def _parse_time(t: str) -> time:
    """Parse 'HH:MM' string to time object."""
    parts = t.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {t}")
    return time(int(parts[0]), int(parts[1]))


def _verify_lo_belongs_to_org(db: Session, user_id: int, organization_id: int) -> None:
    """
    TENANT-011: Verify that the target LO belongs to the authenticated user's org.

    Raises HTTPException 403 if the user does not belong to the org.
    """
    _ensure_models()
    user = db.query(_User).filter(_User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.organization_id != organization_id:
        logger.warning(
            "Tenant isolation violation: user %s (org %s) tried to modify LO %s (org %s)",
            organization_id, organization_id, user_id, user.organization_id,
            extra={
                "user_id": user_id,
                "target_org": user.organization_id,
                "requesting_org": organization_id,
            },
        )
        raise HTTPException(
            status_code=403,
            detail="LO does not belong to your organization",
        )


def _get_or_create_availability(db: Session, user_id: int, organization_id: int):
    """Get existing availability row or create a new one."""
    _ensure_models()
    avail = db.query(_LOAvailability).filter(
        _LOAvailability.user_id == user_id,
    ).first()
    if avail is None:
        avail = _LOAvailability(
            user_id=user_id,
            organization_id=organization_id,
            status="offline",
            auto_status=True,
            max_concurrent_transfers=1,
            active_transfer_count=0,
        )
        db.add(avail)
        db.flush()
    return avail


def _is_within_schedule(db: Session, user_id: int, now_time: time, now_weekday: int) -> bool:
    """Check if current time falls within any schedule window for the user.

    If no schedule rows exist, assume always in-schedule (LO has not
    configured a weekly schedule yet).
    """
    _ensure_models()
    slots = db.query(_LOAvailabilitySchedule).filter(
        _LOAvailabilitySchedule.user_id == user_id,
        _LOAvailabilitySchedule.day_of_week == now_weekday,
        _LOAvailabilitySchedule.is_available == True,  # noqa: E712
    ).all()

    # No schedule configured — treat as always in-window
    if not slots:
        any_slots = db.query(_LOAvailabilitySchedule).filter(
            _LOAvailabilitySchedule.user_id == user_id,
        ).first()
        if any_slots is None:
            return True
        # Has schedule rows but none for today — not in window
        return False

    for slot in slots:
        if slot.start_time <= now_time <= slot.end_time:
            return True
    return False


def _is_lo_available(db: Session, user_id: int) -> bool:
    """Full availability check: status + schedule + transfer capacity.

    Public helper for use by other modules (e.g., telephony transfer logic).
    Uses PERF-011 in-memory cache with 30-second TTL.
    """
    # PERF-011: Check cache first
    cached = _cache_get(user_id)
    if cached is not None:
        return cached

    _ensure_models()
    avail = db.query(_LOAvailability).filter(
        _LOAvailability.user_id == user_id,
    ).first()
    if avail is None:
        _cache_set(user_id, False)
        return False

    result = True

    # Status check
    if avail.status != "available":
        result = False

    # Heartbeat freshness
    elif avail.last_heartbeat_at:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=HEARTBEAT_STALE_MINUTES)
        hb_utc = avail.last_heartbeat_at
        if hb_utc.tzinfo is None:
            hb_utc = hb_utc.replace(tzinfo=timezone.utc)
        if hb_utc < stale_cutoff:
            result = False

    # Transfer capacity
    if result and avail.active_transfer_count >= avail.max_concurrent_transfers:
        result = False

    # Schedule window
    if result:
        try:
            import pytz
            tz = pytz.timezone(avail.timezone or "America/Chicago")
            now_in_tz = datetime.now(tz)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            now_in_tz = datetime.now(timezone.utc)
        now_time_val = now_in_tz.time()
        now_weekday = now_in_tz.weekday()  # 0=Monday

        if not _is_within_schedule(db, user_id, now_time_val, now_weekday):
            result = False

    _cache_set(user_id, result)
    return result


def get_available_los(db: Session, organization_id: int) -> list:
    """Return list of user IDs that are currently available for transfers.

    Public helper for use by telephony transfer / routing modules.
    """
    _ensure_models()
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=HEARTBEAT_STALE_MINUTES)

    rows = (
        db.query(_LOAvailability)
        .filter(
            _LOAvailability.organization_id == organization_id,
            _LOAvailability.status == "available",
        )
        .order_by(
            _LOAvailability.active_transfer_count.asc(),
            _LOAvailability.last_heartbeat_at.desc().nullslast(),
        )
        .all()
    )

    available_ids = []
    for avail in rows:
        if avail.active_transfer_count >= avail.max_concurrent_transfers:
            continue
        if avail.last_heartbeat_at:
            hb_utc = avail.last_heartbeat_at
            if hb_utc.tzinfo is None:
                hb_utc = hb_utc.replace(tzinfo=timezone.utc)
            if hb_utc < stale_cutoff:
                continue
        try:
            import pytz
            tz = pytz.timezone(avail.timezone or "America/Chicago")
            now_in_tz = datetime.now(tz)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            now_in_tz = datetime.now(timezone.utc)
        if not _is_within_schedule(db, avail.user_id, now_in_tz.time(), now_in_tz.weekday()):
            continue
        available_ids.append(avail.user_id)

    return available_ids


def update_status_from_call(db: Session, user_id: int, event_type: str):
    """Auto-manage LO status from telephony events.

    Public helper callable from voice/telephony routes without going
    through the HTTP endpoint.

    Args:
        event_type: 'call_start' or 'call_end'
    """
    _ensure_models()
    avail = db.query(_LOAvailability).filter(
        _LOAvailability.user_id == user_id,
    ).first()
    if avail is None or not avail.auto_status:
        return

    if event_type == "call_start":
        avail.active_transfer_count = (avail.active_transfer_count or 0) + 1
        avail.status = "on_call"
    elif event_type == "call_end":
        avail.active_transfer_count = max((avail.active_transfer_count or 1) - 1, 0)
        if avail.active_transfer_count == 0:
            avail.status = "available"
            avail.status_reason = None

    avail.updated_at = datetime.now(timezone.utc)
    db.flush()
    _cache_invalidate(user_id)


# =============================================================================
# Routes
# =============================================================================

# IMPORTANT: Static paths must be registered BEFORE the /{user_id} path
# parameter route so FastAPI matches them first.

@router.put("/status")
async def update_own_status(
    body: StatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """LO manually sets their own status (available, dnd, away, etc.)."""
    _ensure_models()
    _ensure_table(db)

    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    avail = _get_or_create_availability(db, current_user.id, current_user.organization_id)
    avail.status = body.status
    avail.status_reason = body.status_reason
    avail.updated_at = datetime.now(timezone.utc)

    if body.auto_status is not None:
        avail.auto_status = body.auto_status
    if body.max_concurrent_transfers is not None:
        avail.max_concurrent_transfers = body.max_concurrent_transfers

    db.commit()
    _cache_invalidate(current_user.id)

    logger.info(
        "LO %s status -> %s (reason=%s)",
        current_user.id, body.status, body.status_reason,
        extra={
            "user_id": current_user.id,
            "organization_id": current_user.organization_id,
            "new_status": body.status,
        },
    )

    return {
        "status": "ok",
        "user_id": current_user.id,
        "new_status": avail.status,
        "status_reason": avail.status_reason,
    }


@router.put("/schedule")
async def set_schedule(
    body: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Set or replace the current LO's weekly availability schedule."""
    _ensure_models()
    _ensure_table(db)

    user_tz = body.timezone or current_user.timezone or "America/Chicago"

    # Validate time formats up-front
    parsed_slots = []
    for slot in body.slots:
        try:
            st = _parse_time(slot.start_time)
            et = _parse_time(slot.end_time)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if st >= et:
            raise HTTPException(
                status_code=400,
                detail=f"start_time ({slot.start_time}) must be before end_time ({slot.end_time})",
            )
        parsed_slots.append((slot, st, et))

    # Delete existing schedule for this user
    db.query(_LOAvailabilitySchedule).filter(
        _LOAvailabilitySchedule.user_id == current_user.id,
    ).delete(synchronize_session="fetch")

    # Insert new schedule
    for slot, st, et in parsed_slots:
        row = _LOAvailabilitySchedule(
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            day_of_week=slot.day_of_week,
            start_time=st,
            end_time=et,
            is_available=slot.is_available,
        )
        db.add(row)

    # Also update the timezone on the availability record
    avail = _get_or_create_availability(db, current_user.id, current_user.organization_id)
    avail.timezone = user_tz

    db.commit()
    _cache_invalidate(current_user.id)

    logger.info(
        "LO %s schedule updated: %d slots",
        current_user.id, len(body.slots),
        extra={
            "user_id": current_user.id,
            "organization_id": current_user.organization_id,
            "slots_count": len(body.slots),
            "timezone": user_tz,
        },
    )

    return {
        "status": "ok",
        "user_id": current_user.id,
        "slots_saved": len(body.slots),
        "timezone": user_tz,
    }


@router.get("/schedule", response_model=None)
async def get_schedule(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Get the current LO's weekly availability schedule."""
    _ensure_models()
    _ensure_table(db)

    slots = db.query(_LOAvailabilitySchedule).filter(
        _LOAvailabilitySchedule.user_id == current_user.id,
    ).order_by(
        _LOAvailabilitySchedule.day_of_week,
        _LOAvailabilitySchedule.start_time,
    ).all()

    avail = db.query(_LOAvailability).filter(
        _LOAvailability.user_id == current_user.id,
    ).first()

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    return {
        "user_id": current_user.id,
        "timezone": avail.timezone if avail else (current_user.timezone or "America/Chicago"),
        "slots": [
            {
                "id": s.id,
                "day_of_week": s.day_of_week,
                "day_name": day_names[s.day_of_week] if 0 <= s.day_of_week <= 6 else "Unknown",
                "start_time": s.start_time.strftime("%H:%M") if s.start_time else None,
                "end_time": s.end_time.strftime("%H:%M") if s.end_time else None,
                "is_available": s.is_available,
            }
            for s in slots
        ],
    }


@router.get("/available", response_model=List[AvailableLOResponse])
async def find_available_los(
    organization_id: Optional[int] = Query(None, description="Filter by org (defaults to current user's org)"),
    skill: Optional[str] = Query(None, description="Reserved for future skill-based routing"),
    language: Optional[str] = Query(None, description="Reserved for future language-based routing"),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Find LOs currently available to receive a live call transfer.

    Checks: status == available, within schedule window, under max
    concurrent transfers, heartbeat is fresh.  Results are sorted by
    fewest active transfers (most available first), then by most recent
    heartbeat (most recently active first).
    """
    _ensure_models()
    _ensure_table(db)

    org_id = organization_id or current_user.organization_id

    # Tenant isolation — only allow querying own org unless admin
    if org_id != current_user.organization_id:
        if current_user.role not in ("admin", "site_admin") and \
           current_user.permission_role not in ("admin", "site_admin"):
            raise HTTPException(
                status_code=403,
                detail="Cannot query another organization's availability",
            )

    # Heartbeat freshness cutoff
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=HEARTBEAT_STALE_MINUTES)

    # Query all "available" LOs in the org
    rows = (
        db.query(_LOAvailability, _User)
        .join(_User, _User.id == _LOAvailability.user_id)
        .filter(
            _LOAvailability.organization_id == org_id,
            _LOAvailability.status == "available",
            _User.is_active == True,  # noqa: E712
        )
        .order_by(
            _LOAvailability.active_transfer_count.asc(),
            _LOAvailability.last_heartbeat_at.desc().nullslast(),
        )
        .all()
    )

    results: List[AvailableLOResponse] = []
    for avail, user in rows:
        # Transfer capacity check
        if avail.active_transfer_count >= avail.max_concurrent_transfers:
            continue

        # Heartbeat freshness check
        if avail.last_heartbeat_at:
            hb_utc = avail.last_heartbeat_at
            if hb_utc.tzinfo is None:
                hb_utc = hb_utc.replace(tzinfo=timezone.utc)
            if hb_utc < stale_cutoff:
                continue

        # Schedule window check
        try:
            import pytz
            tz = pytz.timezone(avail.timezone or "America/Chicago")
            now_in_tz = datetime.now(tz)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            now_in_tz = datetime.now(timezone.utc)

        if not _is_within_schedule(db, user.id, now_in_tz.time(), now_in_tz.weekday()):
            continue

        results.append(AvailableLOResponse(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=None,  # PII: do not expose LO email in availability listing
            status=avail.status,
            active_transfer_count=avail.active_transfer_count,
            max_concurrent_transfers=avail.max_concurrent_transfers,
        ))

    return results


# Path-parameter route MUST come after all static GET paths above
@router.get("/{user_id}", response_model=AvailabilityResponse)
async def get_lo_availability(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Get a specific LO's current availability status."""
    _ensure_models()
    _ensure_table(db)

    avail = db.query(_LOAvailability).filter(
        _LOAvailability.user_id == user_id,
        _LOAvailability.organization_id == current_user.organization_id,
    ).first()

    if avail is None:
        # Return a default offline response rather than 404 — the LO simply
        # has no availability record yet.
        return AvailabilityResponse(
            user_id=user_id,
            status="offline",
            in_schedule_window=False,
            can_receive_transfer=False,
        )

    # Schedule window check
    try:
        import pytz
        tz = pytz.timezone(avail.timezone or "America/Chicago")
        now_in_tz = datetime.now(tz)
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        now_in_tz = datetime.now(timezone.utc)
    in_schedule = _is_within_schedule(db, user_id, now_in_tz.time(), now_in_tz.weekday())

    can_transfer = (
        avail.status == "available"
        and in_schedule
        and avail.active_transfer_count < avail.max_concurrent_transfers
    )

    # Heartbeat staleness
    if avail.last_heartbeat_at:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=HEARTBEAT_STALE_MINUTES)
        hb_utc = avail.last_heartbeat_at
        if hb_utc.tzinfo is None:
            hb_utc = hb_utc.replace(tzinfo=timezone.utc)
        if hb_utc < stale_cutoff:
            can_transfer = False

    return AvailabilityResponse(
        user_id=avail.user_id,
        status=avail.status,
        status_reason=avail.status_reason,
        auto_status=avail.auto_status,
        in_schedule_window=in_schedule,
        active_transfer_count=avail.active_transfer_count,
        max_concurrent_transfers=avail.max_concurrent_transfers,
        can_receive_transfer=can_transfer,
        last_heartbeat_at=avail.last_heartbeat_at.isoformat() if avail.last_heartbeat_at else None,
        updated_at=avail.updated_at.isoformat() if avail.updated_at else None,
    )


@router.post("/call-event")
async def call_event_webhook(
    body: CallEvent,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Auto-update LO status from telephony call events.

    Called by the telephony layer when a call starts or ends.
    Requires internal API key via X-API-Key header.
    """
    import os
    expected_key = os.getenv("INTERNAL_API_KEY", "")
    provided_key = request.headers.get("X-API-Key", "")
    if not expected_key or provided_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    _ensure_models()
    _ensure_table(db)

    if body.event_type not in ("call_start", "call_end"):
        raise HTTPException(
            status_code=400,
            detail="event_type must be 'call_start' or 'call_end'",
        )

    call_log_extra = {
        "user_id": body.user_id,
        "event_type": body.event_type,
        "call_id": body.call_id,
    }

    avail = db.query(_LOAvailability).filter(
        _LOAvailability.user_id == body.user_id,
    ).first()

    if avail is None:
        logger.warning(
            "Call event for user %s but no availability record exists",
            body.user_id,
            extra=call_log_extra,
        )
        return {"status": "ignored", "reason": "no_availability_record"}

    if not avail.auto_status:
        logger.debug(
            "Call event for user %s ignored — auto_status is disabled",
            body.user_id,
            extra=call_log_extra,
        )
        return {"status": "ignored", "reason": "auto_status_disabled"}

    if body.event_type == "call_start":
        avail.active_transfer_count = (avail.active_transfer_count or 0) + 1
        avail.status = "on_call"
        avail.status_reason = f"On call ({body.call_id})" if body.call_id else "On call"
        logger.info(
            "LO %s -> on_call (transfers=%d)",
            body.user_id, avail.active_transfer_count,
            extra={**call_log_extra, "organization_id": avail.organization_id},
        )

    elif body.event_type == "call_end":
        avail.active_transfer_count = max((avail.active_transfer_count or 1) - 1, 0)
        if avail.active_transfer_count == 0:
            avail.status = "available"
            avail.status_reason = None
            logger.info(
                "LO %s -> available (all calls ended)",
                body.user_id,
                extra={**call_log_extra, "organization_id": avail.organization_id},
            )
        else:
            logger.info(
                "LO %s still on_call (transfers=%d)",
                body.user_id, avail.active_transfer_count,
                extra={**call_log_extra, "organization_id": avail.organization_id},
            )

    avail.updated_at = datetime.now(timezone.utc)
    db.commit()
    _cache_invalidate(body.user_id)

    return {
        "status": "ok",
        "user_id": body.user_id,
        "new_status": avail.status,
        "active_transfer_count": avail.active_transfer_count,
    }


@router.post("/heartbeat")
async def heartbeat(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    LO client pings periodically to confirm they are online.

    If no heartbeat is received for 5 minutes, the LO is considered
    offline and will not receive call transfers.
    """
    _ensure_models()
    _ensure_table(db)

    avail = _get_or_create_availability(db, current_user.id, current_user.organization_id)
    avail.last_heartbeat_at = datetime.now(timezone.utc)

    # If LO was offline and heartbeat arrives, transition to available
    # (only if auto_status is on and they were previously offline)
    if avail.status == "offline" and avail.auto_status:
        avail.status = "available"
        avail.status_reason = None
        logger.info(
            "LO %s heartbeat received — status -> available",
            current_user.id,
            extra={
                "user_id": current_user.id,
                "organization_id": current_user.organization_id,
            },
        )

    avail.updated_at = datetime.now(timezone.utc)
    db.commit()
    _cache_invalidate(current_user.id)

    return {
        "status": "ok",
        "user_id": current_user.id,
        "current_status": avail.status,
        "heartbeat_at": avail.last_heartbeat_at.isoformat(),
    }
