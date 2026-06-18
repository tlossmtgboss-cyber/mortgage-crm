"""
Scheduler Import Routes - Bulk data import for Smart Calendar.

Endpoints:
  - POST /import/appointments/csv   Bulk import appointments from a CSV file
  - POST /import/appointments/ics   Bulk import appointments from an ICS/iCalendar file

Both endpoints support a preview mode (validate without committing) and three
duplicate strategies: skip, error, or update. Max file size: 5 MB. Max rows: 500.

Admin only.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from routes.scheduler._helpers import (
    _audit_log,
    _check_duplicate_booking,
    _ensure_lead_for_booking,
    _get_org_id,
    _is_scheduler_admin,
    _log_appointment_activity,
    get_current_user,
    get_models,
)
from routes.scheduler.constants import (
    DEFAULT_APPOINTMENT_DURATION_MINUTES,
    DEFAULT_TIMEZONE,
    MAX_APPOINTMENT_DURATION_MINUTES,
    MIN_APPOINTMENT_DURATION_MINUTES,
)
from smart_scheduler_models import AppointmentStatus, MeetingMode, MeetingType

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_IMPORT_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_IMPORT_ROWS = 500

# Datetime formats tried in order when parsing CSV start_time / end_time values
_DATETIME_FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z",   # ISO 8601 with timezone
    "%Y-%m-%dT%H:%M:%S",      # ISO 8601 without timezone
    "%Y-%m-%dT%H:%M%z",       # ISO 8601 HH:MM with timezone
    "%Y-%m-%dT%H:%M",         # ISO 8601 HH:MM without timezone
    "%Y-%m-%d %H:%M:%S",      # "YYYY-MM-DD HH:MM:SS"
    "%Y-%m-%d %H:%M",         # "YYYY-MM-DD HH:MM"
    "%m/%d/%Y %H:%M:%S",      # US format with seconds
    "%m/%d/%Y %H:%M",         # US format
    "%m/%d/%Y %I:%M %p",      # US 12-hour
]


# ---------------------------------------------------------------------------
# Response / helper models
# ---------------------------------------------------------------------------

class ImportError(BaseModel):
    row: int
    field: Optional[str] = None
    message: str


class ImportResponse(BaseModel):
    imported: int = 0
    skipped: int = 0
    updated: int = 0
    errors: List[ImportError] = Field(default_factory=list)


class PreviewRow(BaseModel):
    row: int
    title: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    scheduled_start: Optional[str] = None
    duration_minutes: Optional[int] = None
    status: Optional[str] = None


class PreviewResponse(BaseModel):
    valid: int
    errors: List[ImportError] = Field(default_factory=list)
    preview_rows: List[PreviewRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _parse_datetime(value: str) -> Optional[datetime]:
    """Try all known datetime formats; return None if nothing matches."""
    if not value:
        return None
    value = value.strip()
    for fmt in _DATETIME_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            # Ensure timezone-aware (assume UTC for naive datetimes)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _check_file_size(content: bytes) -> None:
    """Raise HTTP 413 if the file exceeds MAX_IMPORT_FILE_BYTES."""
    if len(content) > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_IMPORT_FILE_BYTES // (1024 * 1024)} MB.",
        )


def _parse_ics_manual(content: str) -> List[Dict[str, str]]:
    """Minimal VEVENT parser for when icalendar library is unavailable.

    Returns a list of dicts with raw ICS property names as keys. Multi-line
    (folded) property values are unfolded before splitting. Property parameters
    (e.g. DTSTART;TZID=America/New_York) are stripped so only the base key is
    kept.
    """
    # Unfold RFC 5545 line continuations (CRLF / LF followed by whitespace)
    unfolded = content.replace("\r\n ", "").replace("\r\n\t", "")
    unfolded = unfolded.replace("\n ", "").replace("\n\t", "")

    events: List[Dict[str, str]] = []
    current_event: Dict[str, str] = {}
    in_event = False

    for raw_line in unfolded.splitlines():
        line = raw_line.rstrip()
        if line == "BEGIN:VEVENT":
            in_event = True
            current_event = {}
        elif line == "END:VEVENT":
            in_event = False
            if current_event:
                events.append(current_event)
        elif in_event and ":" in line:
            key_part, _, value = line.partition(":")
            # Strip parameters (e.g. DTSTART;TZID=America/New_York → DTSTART)
            base_key = key_part.split(";")[0].strip().upper()
            current_event[base_key] = value.strip()

    return events


def _parse_ics_datetime(raw: str) -> Optional[datetime]:
    """Parse an ICS DTSTART/DTEND value to a timezone-aware datetime.

    Handles: UTC suffix (Z), YYYYMMDDTHHMMSSZ, YYYYMMDDTHHMMSS (naive),
    and YYYYMMDD (all-day — treated as midnight UTC).
    """
    if not raw:
        return None
    raw = raw.strip()

    # All-day: YYYYMMDD
    if len(raw) == 8 and raw.isdigit():
        try:
            return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # UTC: ends with Z
    if raw.endswith("Z"):
        try:
            return datetime.strptime(raw.rstrip("Z"), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # Local (naive) — treat as UTC
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def _handle_duplicate(
    db,
    Appointment,
    attendee_email: Optional[str],
    assigned_user_id: int,
    scheduled_start: datetime,
    org_id: int,
    duplicate_strategy: str,
    new_data: Dict[str, Any],
) -> Tuple[str, Optional[Any]]:
    """Check for a duplicate and act according to strategy.

    Returns (action, existing_appointment_or_None):
      - ("ok", None)         → no duplicate found
      - ("skip", appt)       → duplicate found, strategy=skip → caller should skip
      - ("error", appt)      → duplicate found, strategy=error → caller should record error
      - ("update", appt)     → duplicate found, strategy=update → caller should update appt
    """
    if not attendee_email:
        return ("ok", None)

    from routes.scheduler.constants import DEFAULT_APPOINTMENT_DURATION_MINUTES
    window_minutes = DEFAULT_APPOINTMENT_DURATION_MINUTES
    window_start = scheduled_start - timedelta(minutes=window_minutes)
    window_end = scheduled_start + timedelta(minutes=window_minutes)

    from sqlalchemy import and_
    existing = (
        db.query(Appointment)
        .filter(and_(
            Appointment.attendee_email == attendee_email,
            Appointment.assigned_user_id == assigned_user_id,
            Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
            Appointment.scheduled_start >= window_start,
            Appointment.scheduled_start <= window_end,
            Appointment.organization_id == org_id,
        ))
        .first()
    )

    if existing is None:
        return ("ok", None)

    if duplicate_strategy == "skip":
        return ("skip", existing)
    elif duplicate_strategy == "error":
        return ("error", existing)
    else:  # "update"
        return ("update", existing)


def _apply_update(appointment, new_data: Dict[str, Any]) -> None:
    """Apply import fields to an existing appointment (update strategy)."""
    updatable = [
        "title", "description", "scheduled_start", "scheduled_end",
        "duration_minutes", "timezone", "location", "attendee_name",
        "attendee_phone", "attendee_notes",
    ]
    for field in updatable:
        if field in new_data and new_data[field] is not None:
            setattr(appointment, field, new_data[field])


# ---------------------------------------------------------------------------
# CSV Import
# ---------------------------------------------------------------------------

@router.post("/import/appointments/csv")
async def import_appointments_csv(
    request: Request,
    file: UploadFile = File(..., description="CSV file to import"),
    preview: bool = Query(False, description="Validate all rows without committing"),
    duplicate_strategy: str = Query("skip", description="How to handle duplicates: skip|error|update"),
    db: Session = Depends(get_db),
):
    """Import appointments from a CSV file.

    The CSV must include ``start_time`` and either ``duration_minutes`` or
    ``end_time``. All other columns are optional.

    Column names are case-insensitive. Unknown columns are silently ignored.

    When ``preview=true``, all rows are validated but nothing is committed.
    Returns ``{valid, errors, preview_rows}`` (first 5 valid rows).

    When ``preview=false``, each row is written inside its own savepoint so
    partial failures do not block successful rows. Returns
    ``{imported, skipped, updated, errors}``.

    Requires admin privileges.
    """
    # Auth
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="CSV import requires admin privileges")

    if duplicate_strategy not in ("skip", "error", "update"):
        raise HTTPException(
            status_code=422,
            detail="duplicate_strategy must be one of: skip, error, update",
        )

    # File size guard
    content_bytes = await file.read()
    _check_file_size(content_bytes)

    # Decode
    try:
        raw_text = content_bytes.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        try:
            raw_text = content_bytes.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=422, detail="Could not decode CSV file (expected UTF-8 or Latin-1)")

    reader = csv.DictReader(io.StringIO(raw_text))
    rows = list(reader)

    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"CSV contains {len(rows)} rows; maximum allowed is {MAX_IMPORT_ROWS}.",
        )

    # Normalise column names to lowercase
    def _norm(row: dict) -> dict:
        return {k.strip().lower(): v for k, v in row.items()}

    rows = [_norm(r) for r in rows]

    _models = get_models()
    Appointment = _models["Appointment"]
    AppointmentType = _models.get("SchedulerAppointmentType")

    # --- Parse and validate all rows first ---
    parsed_rows: List[Dict[str, Any]] = []
    errors: List[ImportError] = []

    for idx, row in enumerate(rows):
        row_num = idx + 2  # 1-based, +1 for header

        # Required: start_time
        raw_start = row.get("start_time", "").strip()
        if not raw_start:
            errors.append(ImportError(row=row_num, field="start_time", message="start_time is required"))
            continue

        scheduled_start = _parse_datetime(raw_start)
        if scheduled_start is None:
            errors.append(ImportError(
                row=row_num, field="start_time",
                message=f"Could not parse start_time: {raw_start!r}. Use ISO 8601 or YYYY-MM-DD HH:MM",
            ))
            continue

        # Required: duration_minutes or end_time
        duration_minutes: Optional[int] = None
        scheduled_end: Optional[datetime] = None

        raw_duration = row.get("duration_minutes", "").strip()
        raw_end = row.get("end_time", "").strip()

        if raw_duration:
            try:
                duration_minutes = int(float(raw_duration))
            except (ValueError, TypeError):
                errors.append(ImportError(row=row_num, field="duration_minutes", message=f"Invalid duration_minutes: {raw_duration!r}"))
                continue
            if not (MIN_APPOINTMENT_DURATION_MINUTES <= duration_minutes <= MAX_APPOINTMENT_DURATION_MINUTES):
                errors.append(ImportError(
                    row=row_num, field="duration_minutes",
                    message=f"duration_minutes must be between {MIN_APPOINTMENT_DURATION_MINUTES} and {MAX_APPOINTMENT_DURATION_MINUTES}",
                ))
                continue
            scheduled_end = scheduled_start + timedelta(minutes=duration_minutes)
        elif raw_end:
            scheduled_end = _parse_datetime(raw_end)
            if scheduled_end is None:
                errors.append(ImportError(row=row_num, field="end_time", message=f"Could not parse end_time: {raw_end!r}"))
                continue
            delta = (scheduled_end - scheduled_start).total_seconds() / 60
            if delta <= 0:
                errors.append(ImportError(row=row_num, field="end_time", message="end_time must be after start_time"))
                continue
            duration_minutes = int(delta)
        else:
            errors.append(ImportError(
                row=row_num, field="duration_minutes",
                message="Either duration_minutes or end_time is required",
            ))
            continue

        # Optional fields
        attendee_name = row.get("attendee_name", "").strip() or None
        attendee_email = row.get("attendee_email", "").strip() or None
        attendee_phone = row.get("attendee_phone", "").strip() or None
        appointment_type_name = row.get("appointment_type", "").strip() or None
        notes = row.get("notes", "").strip() or None
        location = row.get("location", "").strip() or None

        # Derive title from appointment_type name or attendee
        title = appointment_type_name or (
            f"Appointment with {attendee_name}" if attendee_name else "Imported Appointment"
        )

        # Validate / look up appointment type
        appointment_type_id: Optional[int] = None
        if appointment_type_name and AppointmentType:
            at = (
                db.query(AppointmentType)
                .filter(
                    AppointmentType.type_name.ilike(appointment_type_name),
                    AppointmentType.organization_id == org_id,
                )
                .first()
            )
            if at:
                appointment_type_id = at.id
            # Unknown type is not fatal — just skip the FK

        parsed_rows.append({
            "row_num": row_num,
            "title": title[:255],
            "attendee_name": attendee_name,
            "attendee_email": attendee_email,
            "attendee_phone": attendee_phone,
            "attendee_notes": notes,
            "location": location,
            "appointment_type_id": appointment_type_id,
            "scheduled_start": scheduled_start,
            "scheduled_end": scheduled_end,
            "duration_minutes": duration_minutes,
            "timezone": DEFAULT_TIMEZONE,
        })

    # --- Preview mode: return validation summary ---
    if preview:
        valid_count = len(parsed_rows)
        preview_rows = [
            PreviewRow(
                row=r["row_num"],
                title=r["title"],
                attendee_name=r["attendee_name"],
                attendee_email=r["attendee_email"],
                scheduled_start=r["scheduled_start"].isoformat() if r["scheduled_start"] else None,
                duration_minutes=r["duration_minutes"],
            )
            for r in parsed_rows[:5]
        ]
        return PreviewResponse(valid=valid_count, errors=errors, preview_rows=preview_rows)

    # --- Import mode: write rows using savepoints ---
    imported = 0
    skipped = 0
    updated = 0

    for parsed in parsed_rows:
        row_num = parsed["row_num"]
        assigned_user_id = user.id  # CSV imports default to the current user

        savepoint = db.begin_nested()
        try:
            dup_action, dup_appt = _handle_duplicate(
                db, Appointment,
                parsed["attendee_email"],
                assigned_user_id,
                parsed["scheduled_start"],
                org_id,
                duplicate_strategy,
                parsed,
            )

            if dup_action == "skip":
                savepoint.rollback()
                skipped += 1
                logger.info(
                    "CSV import row %d: duplicate skipped (existing appointment %d)",
                    row_num, dup_appt.id,
                )
                continue

            if dup_action == "error":
                savepoint.rollback()
                errors.append(ImportError(
                    row=row_num,
                    field="attendee_email",
                    message=(
                        f"Duplicate booking: appointment {dup_appt.id} already exists "
                        f"for this attendee near this time"
                    ),
                ))
                continue

            if dup_action == "update" and dup_appt is not None:
                _apply_update(dup_appt, parsed)
                _audit_log(
                    db, org_id, user.id, "csv_import_updated", "appointment",
                    entity_id=dup_appt.id,
                    changes={
                        "scheduled_start": parsed["scheduled_start"].isoformat(),
                        "attendee_email": parsed["attendee_email"],
                        "source": "csv_import",
                    },
                    request=request,
                )
                savepoint.commit()
                db.flush()
                updated += 1
                continue

            # dup_action == "ok" → create new appointment
            appointment = Appointment(
                organization_id=org_id,
                appointment_type_id=parsed["appointment_type_id"],
                assigned_user_id=assigned_user_id,
                created_by_user_id=user.id,
                title=parsed["title"],
                description=parsed["attendee_notes"],
                meeting_type=MeetingType.CUSTOM,
                meeting_mode=MeetingMode.VIDEO,
                scheduled_start=parsed["scheduled_start"],
                scheduled_end=parsed["scheduled_end"],
                duration_minutes=parsed["duration_minutes"],
                timezone=parsed["timezone"],
                location=parsed["location"],
                attendee_name=parsed["attendee_name"],
                attendee_email=parsed["attendee_email"],
                attendee_phone=parsed["attendee_phone"],
                attendee_notes=parsed["attendee_notes"],
                status=AppointmentStatus.BOOKED,
                status_changed_at=datetime.now(timezone.utc),
                external_source="csv_import",
            )

            db.add(appointment)
            db.flush()  # get appointment.id

            # CRM: link or create lead
            if not appointment.lead_id and parsed["attendee_email"]:
                lead_id = _ensure_lead_for_booking(
                    db, parsed["attendee_email"], parsed["attendee_name"],
                    parsed["attendee_phone"], assigned_user_id, org_id,
                )
                if lead_id:
                    appointment.lead_id = lead_id

            # CRM: activity log
            _log_appointment_activity(
                db, org_id, user.id, appointment.lead_id, None,
                f"Appointment imported (CSV): {appointment.title} on "
                f"{appointment.scheduled_start.strftime('%m/%d/%Y %I:%M %p')}",
            )

            # Audit
            _audit_log(
                db, org_id, user.id, "csv_import_created", "appointment",
                entity_id=appointment.id,
                changes={
                    "title": parsed["title"],
                    "attendee_email": parsed["attendee_email"],
                    "scheduled_start": parsed["scheduled_start"].isoformat(),
                    "source": "csv_import",
                },
                request=request,
            )

            savepoint.commit()
            db.flush()
            imported += 1

        except HTTPException as exc:
            savepoint.rollback()
            errors.append(ImportError(
                row=row_num,
                message=f"Conflict: {exc.detail}",
            ))
        except Exception as exc:
            savepoint.rollback()
            logger.error("CSV import row %d failed: %s", row_num, exc, exc_info=True)
            errors.append(ImportError(
                row=row_num,
                message="Failed to create appointment — see server logs",
            ))

    db.commit()

    logger.info(
        "CSV import complete: %d imported, %d skipped, %d updated, %d errors — user %d org %d",
        imported, skipped, updated, len(errors), user.id, org_id,
    )

    return ImportResponse(imported=imported, skipped=skipped, updated=updated, errors=errors)


# ---------------------------------------------------------------------------
# ICS Import
# ---------------------------------------------------------------------------

@router.post("/import/appointments/ics")
async def import_appointments_ics(
    request: Request,
    file: UploadFile = File(..., description=".ics / iCalendar file to import"),
    preview: bool = Query(False, description="Validate all events without committing"),
    duplicate_strategy: str = Query("skip", description="How to handle duplicates: skip|error|update"),
    assigned_user_id: Optional[int] = Query(None, description="Assign imported appointments to this user (defaults to current user)"),
    db: Session = Depends(get_db),
):
    """Import appointments from an ICS / iCalendar file.

    Parses VEVENT components and converts them to appointments. Uses the
    ``icalendar`` library when available; falls back to a minimal built-in
    VEVENT parser otherwise.

    DTSTART / DTEND drive scheduling. SUMMARY → title. DESCRIPTION → notes.
    LOCATION → location. The first ATTENDEE value is used as attendee email.

    When ``preview=true``, events are parsed and validated but not committed.
    Returns ``{valid, errors, preview_rows}``.

    Requires admin privileges.
    """
    # Auth
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="ICS import requires admin privileges")

    if duplicate_strategy not in ("skip", "error", "update"):
        raise HTTPException(
            status_code=422,
            detail="duplicate_strategy must be one of: skip, error, update",
        )

    target_user_id = assigned_user_id or user.id

    # File size guard
    content_bytes = await file.read()
    _check_file_size(content_bytes)

    try:
        raw_text = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            raw_text = content_bytes.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=422, detail="Could not decode ICS file")

    # Try icalendar library first, fall back to manual parser
    parsed_events: List[Dict[str, Any]] = []

    try:
        from icalendar import Calendar as ICalendar
        _use_icalendar = True
    except ImportError:
        _use_icalendar = False
        logger.warning("icalendar library not installed — using built-in VEVENT parser")

    if _use_icalendar:
        try:
            cal = ICalendar.from_ical(raw_text)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Failed to parse ICS file: {exc}")

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            dtstart = component.get("DTSTART")
            dtend = component.get("DTEND")
            summary = str(component.get("SUMMARY", "")) or "Imported Event"
            description = str(component.get("DESCRIPTION", "")) or None
            location = str(component.get("LOCATION", "")) or None

            # Attendee may be a single value or a list
            raw_attendee = component.get("ATTENDEE")
            attendee_email: Optional[str] = None
            if raw_attendee is not None:
                attendee_vals = raw_attendee if isinstance(raw_attendee, list) else [raw_attendee]
                for av in attendee_vals:
                    addr = str(av).replace("mailto:", "").strip()
                    if "@" in addr:
                        attendee_email = addr
                        break

            start_dt: Optional[datetime] = None
            end_dt: Optional[datetime] = None

            if dtstart:
                val = dtstart.dt
                if hasattr(val, "hour"):  # datetime
                    start_dt = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
                else:  # date-only
                    start_dt = datetime(val.year, val.month, val.day, tzinfo=timezone.utc)

            if dtend:
                val = dtend.dt
                if hasattr(val, "hour"):
                    end_dt = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
                else:
                    end_dt = datetime(val.year, val.month, val.day, tzinfo=timezone.utc)

            parsed_events.append({
                "title": summary[:255],
                "description": description,
                "location": location,
                "attendee_email": attendee_email,
                "scheduled_start": start_dt,
                "scheduled_end": end_dt,
            })

    else:
        # Manual fallback parser
        raw_events = _parse_ics_manual(raw_text)
        for evt in raw_events:
            start_dt = _parse_ics_datetime(evt.get("DTSTART", ""))
            end_dt = _parse_ics_datetime(evt.get("DTEND", ""))
            summary = evt.get("SUMMARY", "Imported Event")[:255]
            description = evt.get("DESCRIPTION") or None
            location = evt.get("LOCATION") or None

            # ATTENDEE:mailto:someone@example.com
            raw_attendee = evt.get("ATTENDEE", "")
            attendee_email = raw_attendee.replace("mailto:", "").strip() or None
            if attendee_email and "@" not in attendee_email:
                attendee_email = None

            parsed_events.append({
                "title": summary,
                "description": description,
                "location": location,
                "attendee_email": attendee_email,
                "scheduled_start": start_dt,
                "scheduled_end": end_dt,
            })

    if len(parsed_events) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"ICS file contains {len(parsed_events)} events; maximum allowed is {MAX_IMPORT_ROWS}.",
        )

    _models = get_models()
    Appointment = _models["Appointment"]

    # --- Validate all events ---
    valid_events: List[Dict[str, Any]] = []
    errors: List[ImportError] = []

    for idx, evt in enumerate(parsed_events):
        event_num = idx + 1  # 1-based event counter

        if not evt.get("scheduled_start"):
            errors.append(ImportError(
                row=event_num, field="DTSTART",
                message="Missing or unparseable DTSTART",
            ))
            continue

        start_dt = evt["scheduled_start"]
        end_dt = evt.get("scheduled_end")

        if end_dt and end_dt <= start_dt:
            errors.append(ImportError(
                row=event_num, field="DTEND",
                message="DTEND must be after DTSTART",
            ))
            continue

        if end_dt:
            duration_minutes = max(1, int((end_dt - start_dt).total_seconds() / 60))
        else:
            duration_minutes = DEFAULT_APPOINTMENT_DURATION_MINUTES
            end_dt = start_dt + timedelta(minutes=duration_minutes)

        # Cap duration at max
        if duration_minutes > MAX_APPOINTMENT_DURATION_MINUTES:
            duration_minutes = MAX_APPOINTMENT_DURATION_MINUTES
            end_dt = start_dt + timedelta(minutes=duration_minutes)

        valid_events.append({
            "event_num": event_num,
            "title": evt.get("title", "Imported Event"),
            "description": evt.get("description"),
            "location": evt.get("location"),
            "attendee_email": evt.get("attendee_email"),
            "attendee_name": None,
            "attendee_phone": None,
            "scheduled_start": start_dt,
            "scheduled_end": end_dt,
            "duration_minutes": duration_minutes,
            "timezone": DEFAULT_TIMEZONE,
        })

    # --- Preview mode ---
    if preview:
        preview_rows = [
            PreviewRow(
                row=e["event_num"],
                title=e["title"],
                attendee_email=e.get("attendee_email"),
                scheduled_start=e["scheduled_start"].isoformat() if e["scheduled_start"] else None,
                duration_minutes=e["duration_minutes"],
            )
            for e in valid_events[:5]
        ]
        return PreviewResponse(valid=len(valid_events), errors=errors, preview_rows=preview_rows)

    # --- Import mode ---
    imported = 0
    skipped = 0
    updated = 0

    for evt in valid_events:
        event_num = evt["event_num"]

        savepoint = db.begin_nested()
        try:
            dup_action, dup_appt = _handle_duplicate(
                db, Appointment,
                evt["attendee_email"],
                target_user_id,
                evt["scheduled_start"],
                org_id,
                duplicate_strategy,
                evt,
            )

            if dup_action == "skip":
                savepoint.rollback()
                skipped += 1
                logger.info(
                    "ICS import event %d: duplicate skipped (existing appointment %d)",
                    event_num, dup_appt.id,
                )
                continue

            if dup_action == "error":
                savepoint.rollback()
                errors.append(ImportError(
                    row=event_num,
                    field="attendee_email",
                    message=(
                        f"Duplicate booking: appointment {dup_appt.id} already exists "
                        f"for this attendee near this time"
                    ),
                ))
                continue

            if dup_action == "update" and dup_appt is not None:
                _apply_update(dup_appt, evt)
                _audit_log(
                    db, org_id, user.id, "ics_import_updated", "appointment",
                    entity_id=dup_appt.id,
                    changes={
                        "scheduled_start": evt["scheduled_start"].isoformat(),
                        "attendee_email": evt.get("attendee_email"),
                        "source": "ics_import",
                    },
                    request=request,
                )
                savepoint.commit()
                db.flush()
                updated += 1
                continue

            # Create new
            title = evt["title"] or "Imported Event"
            appointment = Appointment(
                organization_id=org_id,
                assigned_user_id=target_user_id,
                created_by_user_id=user.id,
                title=title,
                description=evt.get("description"),
                meeting_type=MeetingType.CUSTOM,
                meeting_mode=MeetingMode.VIDEO,
                scheduled_start=evt["scheduled_start"],
                scheduled_end=evt["scheduled_end"],
                duration_minutes=evt["duration_minutes"],
                timezone=evt["timezone"],
                location=evt.get("location"),
                attendee_email=evt.get("attendee_email"),
                status=AppointmentStatus.BOOKED,
                status_changed_at=datetime.now(timezone.utc),
                external_source="ics_import",
            )

            db.add(appointment)
            db.flush()

            # CRM: link or create lead if attendee email is present
            if not appointment.lead_id and evt.get("attendee_email"):
                lead_id = _ensure_lead_for_booking(
                    db, evt["attendee_email"], None, None, target_user_id, org_id,
                )
                if lead_id:
                    appointment.lead_id = lead_id

            # CRM: activity
            _log_appointment_activity(
                db, org_id, user.id, appointment.lead_id, None,
                f"Appointment imported (ICS): {appointment.title} on "
                f"{appointment.scheduled_start.strftime('%m/%d/%Y %I:%M %p')}",
            )

            # Audit
            _audit_log(
                db, org_id, user.id, "ics_import_created", "appointment",
                entity_id=appointment.id,
                changes={
                    "title": title,
                    "attendee_email": evt.get("attendee_email"),
                    "scheduled_start": evt["scheduled_start"].isoformat(),
                    "source": "ics_import",
                },
                request=request,
            )

            savepoint.commit()
            db.flush()
            imported += 1

        except HTTPException as exc:
            savepoint.rollback()
            errors.append(ImportError(
                row=event_num,
                message=f"Conflict: {exc.detail}",
            ))
        except Exception as exc:
            savepoint.rollback()
            logger.error("ICS import event %d failed: %s", event_num, exc, exc_info=True)
            errors.append(ImportError(
                row=event_num,
                message="Failed to create appointment — see server logs",
            ))

    db.commit()

    logger.info(
        "ICS import complete: %d imported, %d skipped, %d updated, %d errors — user %d org %d",
        imported, skipped, updated, len(errors), user.id, org_id,
    )

    return ImportResponse(imported=imported, skipped=skipped, updated=updated, errors=errors)
