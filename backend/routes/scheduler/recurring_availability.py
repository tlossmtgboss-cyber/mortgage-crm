"""
Recurring Availability Routes

Endpoints for managing weekly recurring availability patterns, date exceptions,
and org-level templates.

Endpoints:
  - GET    /availability/schedule                  Get weekly schedule
  - PUT    /availability/schedule                  Update weekly schedule
  - GET    /availability/exceptions                List date exceptions
  - POST   /availability/exceptions                Add date exception
  - DELETE /availability/exceptions/{id}           Remove date exception
  - GET    /availability/templates                 List org templates
  - POST   /availability/templates                 Create template
  - POST   /availability/templates/{id}/apply      Apply template to user
  - GET    /availability/effective                 Get effective schedule for a date
  - GET    /availability/slots                     Get computed available slots

NOTE: Availability Source of Truth — Dual System
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
These structured availability tables (RecurringAvailability, AvailabilityException,
AvailabilityTemplate) are the PREFERRED source of truth for the slot generator.

The unified slot generator in _helpers._generate_available_slots() checks for
RecurringAvailability rows FIRST. If any exist for the user, they take precedence
over the SchedulerConfig.working_hours JSON blob. If none exist, the JSON blob
is used as a fallback.

This means:
- Users who have ONLY used the settings UI (working_hours JSON) will continue
  to work via the JSON fallback path.
- Users who have EVER saved a recurring schedule via these endpoints will have
  that schedule used instead of the JSON blob, even if the JSON blob is later
  updated through the settings UI.

When migrating to a single source of truth, update _generate_available_slots
to query RecurringAvailability as the sole source and remove the JSON fallback.
Until then, any update to the recurring schedule here should ideally also sync
back to SchedulerConfig.working_hours for UI consistency (see sync logic in
the update_weekly_schedule endpoint).

Availability Dual-Source Migration Plan
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Phase 1 (DONE): One-way sync. RecurringAvailability writes -> SchedulerConfig.working_hours
    JSON blob via _sync_recurring_to_working_hours_json(). JSON blob writes
    (settings UI) did NOT sync to RecurringAvailability.
Phase 2 (DONE): Reverse sync. working_hours JSON writes -> RecurringAvailability rows
    via _sync_working_hours_json_to_recurring(). Called from settings.py whenever
    PUT /settings/availability, POST /settings/reset, or POST /settings/import
    updates the working_hours JSON blob. Both directions now stay in sync.
Phase 3 (FUTURE): Deprecate JSON blob. Update the settings UI to read from
    RecurringAvailability endpoints. Remove SchedulerConfig.working_hours column
    and delete all sync code.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date, time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import logging

from routes.scheduler._helpers import get_current_user, _get_org_id, _audit_log
from routes.scheduler.constants import DEFAULT_TIMEZONE
from db import get_db
from services.recurring_availability_service import RecurringAvailabilityService

logger = logging.getLogger(__name__)

try:
    from database.models.recurring_availability import (
        RecurringAvailability as _RA,
        AvailabilityException as _AE,
        AvailabilityTemplate as _AT,
    )
    from db import engine as _engine
    _RA.__table__.create(_engine, checkfirst=True)
    _AE.__table__.create(_engine, checkfirst=True)
    _AT.__table__.create(_engine, checkfirst=True)
except Exception as _e:
    logger.warning(f"Could not create recurring availability tables: {_e}")

router = APIRouter()


# ==================================================================
# PYDANTIC SCHEMAS
# ==================================================================

class TimeBlock(BaseModel):
    start: str = Field(..., description="Start time HH:MM")
    end: str = Field(..., description="End time HH:MM")
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None


class WeeklyScheduleUpdate(BaseModel):
    schedule: Dict[str, List[TimeBlock]] = Field(
        ..., description="Map of day_of_week (0-6) to list of time blocks"
    )
    timezone: str = DEFAULT_TIMEZONE


class ExceptionCreate(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    start_time: Optional[str] = Field(None, description="Start time HH:MM (null = full day)")
    end_time: Optional[str] = Field(None, description="End time HH:MM (null = full day)")
    is_blocked: bool = Field(True, description="True=unavailable, False=extra availability")
    reason: Optional[str] = Field(None, max_length=500)


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    schedule: Dict[str, List[TimeBlock]]
    is_default: bool = False
    timezone: str = DEFAULT_TIMEZONE


# ==================================================================
# WEEKLY SCHEDULE ENDPOINTS
# ==================================================================

@router.get("/availability/schedule")
async def get_weekly_schedule(
    request: Request,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get the weekly recurring availability schedule for a user."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_user_id = user_id or user.id

    # Validate target user belongs to same org
    if user_id and user_id != user.id:
        _validate_same_org(db, user_id, org_id)

    service = RecurringAvailabilityService(db)
    schedule = service.get_weekly_schedule(target_user_id, org_id)

    return {
        "user_id": target_user_id,
        "schedule": schedule,
        "total_blocks": len(schedule),
    }


@router.put("/availability/schedule")
async def update_weekly_schedule(
    body: WeeklyScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Bulk-replace the weekly recurring schedule for the authenticated user.

    Accepts a schedule dict mapping day_of_week (0-6) to list of time blocks.
    Previous schedule rows are deactivated (soft delete).
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Convert Pydantic models to plain dicts
    schedule_dict = {}
    for dow, blocks in body.schedule.items():
        schedule_dict[int(dow)] = [b.model_dump(exclude_none=True) for b in blocks]

    service = RecurringAvailabilityService(db)
    try:
        new_schedule = service.set_weekly_schedule(
            user_id=user.id,
            org_id=org_id,
            schedule=schedule_dict,
            tz=body.timezone,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Sync: mirror the recurring schedule back to SchedulerConfig.working_hours
    # JSON blob so the settings UI stays consistent. This is a backward-compat
    # bridge — once the settings UI reads from RecurringAvailability directly,
    # this sync block can be removed.
    _sync_recurring_to_working_hours_json(db, user.id, org_id, schedule_dict)

    _audit_log(
        db, org_id, user.id, "updated",
        "recurring_availability", None,
        changes={"days_updated": list(schedule_dict.keys()), "timezone": body.timezone},
        request=request,
    )
    db.commit()

    return {
        "message": "Weekly schedule updated",
        "schedule": new_schedule,
        "total_blocks": len(new_schedule),
    }


# ==================================================================
# EXCEPTION ENDPOINTS
# ==================================================================

@router.get("/availability/exceptions")
async def list_exceptions(
    request: Request,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """List availability exceptions, optionally filtered by date range."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Validate date range bounds to prevent unbounded queries
    if start_date and end_date:
        if end_date < start_date:
            raise HTTPException(status_code=400, detail="end_date must be >= start_date")
        if (end_date - start_date).days > 365:
            raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

    service = RecurringAvailabilityService(db)
    exceptions = service.get_exceptions(
        user_id=user.id,
        org_id=org_id,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "exceptions": exceptions,
        "total": len(exceptions),
    }


@router.post("/availability/exceptions")
async def add_exception(
    body: ExceptionCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Add a date-specific availability exception (block or extra availability)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Parse date
    try:
        exc_date = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Parse times if provided
    start_time = None
    end_time = None
    if body.start_time:
        try:
            start_time = datetime.strptime(body.start_time, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_time format. Use HH:MM.")
    if body.end_time:
        try:
            end_time = datetime.strptime(body.end_time, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_time format. Use HH:MM.")

    service = RecurringAvailabilityService(db)
    try:
        exception = service.add_exception(
            user_id=user.id,
            org_id=org_id,
            exc_date=exc_date,
            start_time=start_time,
            end_time=end_time,
            is_blocked=body.is_blocked,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()

    return {
        "message": "Exception added",
        "exception": exception,
    }


@router.delete("/availability/exceptions/{exception_id}")
async def remove_exception(
    exception_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Remove a date-specific availability exception."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = RecurringAvailabilityService(db)
    deleted = service.remove_exception(exception_id, user.id, org_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Exception not found")

    db.commit()

    return {"message": "Exception removed", "id": exception_id}


# ==================================================================
# TEMPLATE ENDPOINTS
# ==================================================================

@router.get("/availability/templates")
async def list_templates(
    request: Request,
    db: Session = Depends(get_db),
):
    """List all availability templates for the user's organization."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = RecurringAvailabilityService(db)
    templates = service.get_templates(org_id)

    return {
        "templates": templates,
        "total": len(templates),
    }


@router.post("/availability/templates")
async def create_template(
    body: TemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a reusable availability template for the organization."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Convert Pydantic blocks to plain dicts for JSON storage
    schedule_dict = {}
    for dow, blocks in body.schedule.items():
        schedule_dict[dow] = [b.model_dump(exclude_none=True) for b in blocks]

    service = RecurringAvailabilityService(db)
    template = service.create_template(
        org_id=org_id,
        name=body.name,
        description=body.description,
        schedule=schedule_dict,
        is_default=body.is_default,
        tz=body.timezone,
    )

    db.commit()

    return {
        "message": "Template created",
        "template": template,
    }


@router.post("/availability/templates/{template_id}/apply")
async def apply_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Apply an org template to the authenticated user's schedule."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = RecurringAvailabilityService(db)
    try:
        new_schedule = service.apply_template(
            user_id=user.id,
            org_id=org_id,
            template_id=template_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Sync: convert the applied template's recurring rows back to working_hours JSON.
    # We reconstruct a schedule_dict from the new_schedule rows returned by the service.
    schedule_dict = {}
    for row in new_schedule:
        dow = row.get("day_of_week")
        if dow is not None:
            schedule_dict.setdefault(dow, []).append({
                "start": row.get("start_time", "09:00"),
                "end": row.get("end_time", "17:00"),
            })
    _sync_recurring_to_working_hours_json(db, user.id, org_id, schedule_dict)

    db.commit()

    return {
        "message": "Template applied",
        "schedule": new_schedule,
        "total_blocks": len(new_schedule),
    }


# ==================================================================
# EFFECTIVE SCHEDULE & SLOT COMPUTATION
# ==================================================================

@router.get("/availability/effective")
async def get_effective_schedule(
    request: Request,
    target_date: date = Query(...),
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Get the effective availability schedule for a specific date.
    Merges recurring schedule with date exceptions.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_user_id = user_id or user.id

    if user_id and user_id != user.id:
        _validate_same_org(db, user_id, org_id)

    service = RecurringAvailabilityService(db)
    schedule = service.get_effective_schedule(target_user_id, org_id, target_date)

    return {
        "user_id": target_user_id,
        "date": target_date.isoformat(),
        "day_of_week": target_date.weekday(),
        "available_blocks": schedule,
        "total_blocks": len(schedule),
    }


@router.get("/availability/slots")
async def get_computed_slots(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    duration_minutes: int = Query(30, ge=15, le=480),
    user_id: Optional[int] = None,
    buffer_before: int = Query(0, ge=0, le=60),
    buffer_after: int = Query(0, ge=0, le=60),
    max_per_day: Optional[int] = Query(None, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Compute available time slots for booking.
    Merges recurring schedule + exceptions - existing appointments.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_user_id = user_id or user.id

    if user_id and user_id != user.id:
        _validate_same_org(db, user_id, org_id)

    # Validate date range
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")

    service = RecurringAvailabilityService(db)
    slots = service.get_available_slots(
        user_id=target_user_id,
        org_id=org_id,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=duration_minutes,
        buffer_before=buffer_before,
        buffer_after=buffer_after,
        max_per_day=max_per_day,
    )

    return {
        "user_id": target_user_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "duration_minutes": duration_minutes,
        "available_slots": slots,
        "total_slots": len(slots),
    }


# ==================================================================
# SYNC: RecurringAvailability -> SchedulerConfig.working_hours JSON
# ==================================================================

# Day-of-week index (ISO: 0=Monday) to day name mapping used by working_hours JSON.
_DOW_TO_NAME = {
    0: "monday", 1: "tuesday", 2: "wednesday",
    3: "thursday", 4: "friday", 5: "saturday", 6: "sunday",
}


def _sync_recurring_to_working_hours_json(
    db: Session,
    user_id: int,
    org_id: int,
    schedule_dict: Dict[int, List[Dict[str, str]]],
) -> None:
    """
    Mirror a RecurringAvailability schedule change into the SchedulerConfig.working_hours
    JSON blob so the settings UI stays consistent.

    The JSON blob format is:
        {"monday": {"start": "09:00", "end": "17:00", "enabled": true}, ...}

    Because the JSON blob only supports a SINGLE start/end per day (no multi-block),
    we approximate by using the earliest start and latest end across all blocks
    for that day. Days with zero blocks are marked enabled=false.

    This is a backward-compatibility bridge. Once the settings UI reads from
    RecurringAvailability directly, this function can be removed.

    Migration plan (full):
    ~~~~~~~~~~~~~~~~~~~~~~~
    Phase 1 (DONE): Dual-write. Recurring schedule writes sync to JSON blob
        via this function.
    Phase 2 (DONE): Reverse sync via _sync_working_hours_json_to_recurring().
        JSON blob writes now also sync to RecurringAvailability tables.
    Phase 3 (FUTURE): Update the settings UI to read from RecurringAvailability
        endpoints instead of the JSON blob. Remove the JSON blob column
        from SchedulerConfig and delete all sync code.
    """
    try:
        from routes.scheduler._helpers import get_models

        models = get_models()
        SchedulerConfig = models.get("SchedulerConfig") if models else None
        if not SchedulerConfig:
            return

        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == user_id,
            SchedulerConfig.organization_id == org_id,
        ).first()

        if not config:
            return

        # Build the JSON blob from the schedule_dict
        from smart_scheduler_models import DEFAULT_WORKING_HOURS

        working_hours = dict(DEFAULT_WORKING_HOURS)  # start with defaults
        # Mark all days disabled first, then enable days that have blocks
        for day_name in working_hours:
            working_hours[day_name] = dict(working_hours[day_name])
            working_hours[day_name]["enabled"] = False

        for dow_int, blocks in schedule_dict.items():
            dow_int = int(dow_int)
            day_name = _DOW_TO_NAME.get(dow_int)
            if not day_name or not blocks:
                continue
            # Use earliest start and latest end across all blocks for this day
            starts = [b.get("start", "09:00") for b in blocks]
            ends = [b.get("end", "17:00") for b in blocks]
            working_hours[day_name] = {
                "start": min(starts),
                "end": max(ends),
                "enabled": True,
            }

        config.working_hours = working_hours
        logger.debug(
            f"Synced RecurringAvailability -> working_hours JSON for user {user_id}"
        )

    except Exception as e:
        # Non-fatal: log and continue. The recurring schedule is the primary
        # source of truth; failing to sync the JSON blob is not critical.
        logger.warning(
            f"Failed to sync recurring schedule to working_hours JSON: {e}"
        )


# ==================================================================
# SYNC: SchedulerConfig.working_hours JSON -> RecurringAvailability
# Phase 2 of the Availability Dual-Source Migration
# ==================================================================

# Reverse mapping: day name to ISO day-of-week index (0=Monday).
_NAME_TO_DOW = {v: k for k, v in _DOW_TO_NAME.items()}


def _sync_working_hours_json_to_recurring(
    db: Session,
    user_id: int,
    org_id: int,
    working_hours_json: Dict[str, dict],
    timezone_str: str = DEFAULT_TIMEZONE,
) -> None:
    """
    Phase 2 reverse sync: propagate a working_hours JSON blob update into the
    RecurringAvailability structured table so both data sources stay consistent.

    Called from settings.py whenever an endpoint writes to
    SchedulerConfig.working_hours directly (PUT /settings/availability,
    POST /settings/reset, POST /settings/import).

    The working_hours JSON format is:
        {
            "monday": {"start": "09:00", "end": "17:00", "enabled": true},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": true},
            ...
        }

    For each day:
    - If enabled=true with valid start/end, upsert a single RecurringAvailability
      row for that day. (The JSON blob only supports one block per day.)
    - If enabled=false or the day is missing, deactivate any existing
      RecurringAvailability rows for that day.

    All operations run within the caller's existing transaction to ensure
    atomicity. The caller is responsible for calling db.commit().

    Args:
        db: SQLAlchemy session (caller manages transaction).
        user_id: User whose availability is being updated.
        org_id: Organization ID for tenant isolation.
        working_hours_json: The working_hours dict being written to SchedulerConfig.
        timezone_str: Timezone for the new RecurringAvailability rows.
    """
    if not working_hours_json or not isinstance(working_hours_json, dict):
        logger.debug(
            f"Skipping reverse sync for user {user_id}: "
            f"working_hours_json is empty or not a dict"
        )
        return

    try:
        from database.models.recurring_availability import RecurringAvailability
        from datetime import datetime as _dt

        changes_log = {"activated": [], "deactivated": [], "unchanged": []}

        for day_name, day_config in working_hours_json.items():
            day_name_lower = day_name.lower()
            dow = _NAME_TO_DOW.get(day_name_lower)
            if dow is None:
                # Unknown day name (e.g. typo) -- skip silently
                continue

            if not isinstance(day_config, dict):
                continue

            enabled = day_config.get("enabled", False)
            start_str = day_config.get("start")
            end_str = day_config.get("end")

            # Fetch all active rows for this user + day
            existing_rows = (
                db.query(RecurringAvailability)
                .filter(
                    RecurringAvailability.user_id == user_id,
                    RecurringAvailability.organization_id == org_id,
                    RecurringAvailability.day_of_week == dow,
                    RecurringAvailability.is_active == True,
                )
                .order_by(RecurringAvailability.start_time)
                .all()
            )

            if not enabled:
                # Day is disabled -- deactivate all existing rows for this day
                if existing_rows:
                    for row in existing_rows:
                        row.is_active = False
                    changes_log["deactivated"].append(
                        f"{day_name_lower} ({len(existing_rows)} rows)"
                    )
                else:
                    changes_log["unchanged"].append(day_name_lower)
                continue

            # Day is enabled -- ensure exactly one active row with the correct times
            if not start_str or not end_str:
                # Enabled but no times -- skip (malformed data)
                logger.warning(
                    f"Reverse sync: {day_name_lower} enabled but missing "
                    f"start/end times for user {user_id}, skipping"
                )
                continue

            try:
                target_start = _dt.strptime(start_str, "%H:%M").time()
                target_end = _dt.strptime(end_str, "%H:%M").time()
            except ValueError:
                logger.warning(
                    f"Reverse sync: invalid time format for {day_name_lower} "
                    f"(start={start_str!r}, end={end_str!r}) for user {user_id}, skipping"
                )
                continue

            if target_start >= target_end:
                logger.warning(
                    f"Reverse sync: start >= end for {day_name_lower} "
                    f"({start_str} >= {end_str}) for user {user_id}, skipping"
                )
                continue

            if len(existing_rows) == 1:
                # Exactly one row exists -- check if it already matches
                row = existing_rows[0]
                if row.start_time == target_start and row.end_time == target_end:
                    changes_log["unchanged"].append(day_name_lower)
                    continue
                # Update in place
                row.start_time = target_start
                row.end_time = target_end
                row.timezone = timezone_str
                changes_log["activated"].append(
                    f"{day_name_lower} updated {start_str}-{end_str}"
                )
            elif len(existing_rows) > 1:
                # Multiple blocks exist (e.g. morning + afternoon from recurring
                # schedule). The JSON blob can only represent one block per day,
                # so we deactivate all existing rows and create a single new one.
                for row in existing_rows:
                    row.is_active = False
                new_row = RecurringAvailability(
                    user_id=user_id,
                    organization_id=org_id,
                    day_of_week=dow,
                    start_time=target_start,
                    end_time=target_end,
                    is_active=True,
                    timezone=timezone_str,
                )
                db.add(new_row)
                changes_log["activated"].append(
                    f"{day_name_lower} replaced {len(existing_rows)} blocks "
                    f"with {start_str}-{end_str}"
                )
            else:
                # No existing rows -- create a new one
                new_row = RecurringAvailability(
                    user_id=user_id,
                    organization_id=org_id,
                    day_of_week=dow,
                    start_time=target_start,
                    end_time=target_end,
                    is_active=True,
                    timezone=timezone_str,
                )
                db.add(new_row)
                changes_log["activated"].append(
                    f"{day_name_lower} created {start_str}-{end_str}"
                )

        # Handle days present in the model but missing from the JSON blob.
        # If a day is absent from the JSON, we leave existing RecurringAvailability
        # rows untouched (the JSON update was a partial update, not a full replace).

        db.flush()

        if changes_log["activated"] or changes_log["deactivated"]:
            logger.info(
                f"Phase 2 reverse sync for user {user_id}: "
                f"activated=[{', '.join(changes_log['activated'])}], "
                f"deactivated=[{', '.join(changes_log['deactivated'])}]"
            )
        else:
            logger.debug(
                f"Phase 2 reverse sync for user {user_id}: no changes needed"
            )

    except Exception as e:
        # Non-fatal: log and continue. The JSON blob is the primary write target
        # in the settings UI flow; failing to sync to RecurringAvailability rows
        # degrades the structured table but does not break the settings UI.
        logger.warning(
            f"Failed to reverse-sync working_hours JSON to "
            f"RecurringAvailability for user {user_id}: {e}"
        )


# ==================================================================
# HELPERS
# ==================================================================

def _validate_same_org(db: Session, target_user_id: int, org_id: int):
    """Validate that the target user belongs to the same organization."""
    try:
        from database.models.core import User
        target_user = db.query(User).filter(
            User.id == target_user_id,
            User.organization_id == org_id,
        ).first()
        if not target_user:
            raise HTTPException(
                status_code=403, detail="User not found in your organization"
            )
    except ImportError:
        pass
