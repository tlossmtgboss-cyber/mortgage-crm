"""
Soft Hold / Slot Reservation Service

During AI phone conversations or multi-step booking flows, temporarily reserve
time slots to prevent double-booking.

Flow:
1. AI discusses a time with caller -> place 5-minute soft hold
2. Caller confirms -> convert hold to real appointment
3. Caller doesn't confirm / hold expires -> auto-release

Holds are:
- TTL-based (default 5 minutes, max 15 minutes)
- Visible to other booking paths as "tentative"
- Automatically cleaned up by background task
- Tracked for analytics (hold conversion rate)
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, func as sa_func
from sqlalchemy.exc import OperationalError
import logging

from smart_scheduler_models import AppointmentStatus, SlotHoldStatus

logger = logging.getLogger(__name__)

# TTL constraints
DEFAULT_HOLD_TTL_SECONDS = 300   # 5 minutes
MAX_HOLD_TTL_SECONDS = 900       # 15 minutes
MAX_ACTIVE_HOLDS_PER_LO = 5     # prevent abuse


class SlotHoldError(Exception):
    """Custom exception for slot hold operations."""
    def __init__(self, message: str, code: str = "HOLD_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


async def create_hold(
    lo_id: int,
    start_time: datetime,
    end_time: datetime,
    held_by: str,
    organization_id: int,
    db: Session,
    models: dict,
    ttl_seconds: int = DEFAULT_HOLD_TTL_SECONDS,
    held_for_name: Optional[str] = None,
    held_for_phone: Optional[str] = None,
    held_for_email: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> dict:
    """
    Create a soft hold on a time slot.

    Uses SELECT FOR UPDATE to prevent race conditions when checking
    for existing appointments and holds at the same time.

    Args:
        lo_id: The loan officer whose calendar is being held
        start_time: Hold start (timezone-aware datetime)
        end_time: Hold end (timezone-aware datetime)
        held_by: Source of the hold ('ai_conversation', 'public_booking', 'manual')
        organization_id: Tenant ID
        db: SQLAlchemy session
        models: Model dictionary from factory
        ttl_seconds: Time-to-live in seconds (default 5 min, max 15 min)
        held_for_name: Name of the person the slot is held for
        held_for_phone: Phone of the person
        held_for_email: Email of the person
        conversation_id: Vapi conversation ID or booking session ID

    Returns:
        Dict with hold details

    Raises:
        SlotHoldError: If slot is unavailable or constraints violated
    """
    SlotHold = models.get('SlotHold')
    Appointment = models.get('Appointment')

    if not SlotHold or not Appointment:
        raise SlotHoldError("Scheduler models not available", "MODELS_UNAVAILABLE")

    # Enforce TTL bounds
    ttl_seconds = max(30, min(ttl_seconds, MAX_HOLD_TTL_SECONDS))
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)

    # Validate time range
    if start_time >= end_time:
        raise SlotHoldError("start_time must be before end_time", "INVALID_TIME_RANGE")

    if start_time < now - timedelta(minutes=1):
        raise SlotHoldError("Cannot hold a slot in the past", "PAST_SLOT")

    # Validate held_by
    valid_sources = ('ai_conversation', 'public_booking', 'manual')
    if held_by not in valid_sources:
        raise SlotHoldError(f"held_by must be one of: {', '.join(valid_sources)}", "INVALID_SOURCE")

    # Check active hold count for this LO to prevent abuse
    active_hold_count = db.query(sa_func.count(SlotHold.id)).filter(
        SlotHold.lo_id == lo_id,
        SlotHold.organization_id == organization_id,
        SlotHold.status == SlotHoldStatus.ACTIVE.value,
        SlotHold.expires_at > now,
    ).scalar() or 0

    if active_hold_count >= MAX_ACTIVE_HOLDS_PER_LO:
        raise SlotHoldError(
            f"Maximum {MAX_ACTIVE_HOLDS_PER_LO} active holds per loan officer",
            "MAX_HOLDS_EXCEEDED"
        )

    # Check for existing appointments at this time (SELECT FOR UPDATE)
    try:
        appointment_conflict = db.query(Appointment).filter(
            Appointment.assigned_user_id == lo_id,
            Appointment.organization_id == organization_id,
            Appointment.status.notin_([
                AppointmentStatus.CANCELLED.value,
                'cancelled', 'no_show'
            ]),
            Appointment.scheduled_start < end_time,
            Appointment.scheduled_end > start_time,
        ).with_for_update(nowait=True).first()
    except OperationalError:
        raise SlotHoldError(
            "This time slot is being booked by another user. Please try a different time.",
            "CONCURRENT_BOOKING"
        )

    if appointment_conflict:
        raise SlotHoldError(
            "This time slot already has an appointment booked.",
            "APPOINTMENT_CONFLICT"
        )

    # Check for existing active holds at this time (SELECT FOR UPDATE)
    try:
        hold_conflict = db.query(SlotHold).filter(
            SlotHold.lo_id == lo_id,
            SlotHold.organization_id == organization_id,
            SlotHold.status == SlotHoldStatus.ACTIVE.value,
            SlotHold.expires_at > now,
            SlotHold.start_time < end_time,
            SlotHold.end_time > start_time,
        ).with_for_update(nowait=True).first()
    except OperationalError:
        raise SlotHoldError(
            "This time slot is being held by another session. Please try a different time.",
            "CONCURRENT_HOLD"
        )

    if hold_conflict:
        raise SlotHoldError(
            "This time slot is currently held by another booking session.",
            "HOLD_CONFLICT"
        )

    # Create the hold
    hold = SlotHold(
        organization_id=organization_id,
        lo_id=lo_id,
        start_time=start_time,
        end_time=end_time,
        held_by=held_by,
        held_for_name=held_for_name,
        held_for_phone=held_for_phone,
        held_for_email=held_for_email,
        conversation_id=conversation_id,
        expires_at=expires_at,
        status=SlotHoldStatus.ACTIVE.value,
    )

    db.add(hold)
    db.flush()  # Get the ID without committing (caller manages transaction)

    logger.info(
        f"Slot hold created: id={hold.id} lo={lo_id} "
        f"{start_time.isoformat()}-{end_time.isoformat()} "
        f"expires={expires_at.isoformat()} held_by={held_by}"
    )

    return _hold_to_dict(hold)


async def extend_hold(
    hold_id: int,
    additional_seconds: int,
    organization_id: int,
    db: Session,
    models: dict,
) -> dict:
    """
    Extend an active hold's TTL.

    Total hold duration (from creation to new expiry) cannot exceed MAX_HOLD_TTL_SECONDS.

    Args:
        hold_id: The hold to extend
        additional_seconds: Seconds to add to the current expiry
        organization_id: Tenant ID
        db: SQLAlchemy session
        models: Model dictionary

    Returns:
        Dict with updated hold details

    Raises:
        SlotHoldError: If hold not found, expired, or max TTL exceeded
    """
    SlotHold = models.get('SlotHold')
    if not SlotHold:
        raise SlotHoldError("Scheduler models not available", "MODELS_UNAVAILABLE")

    now = datetime.now(timezone.utc)

    hold = db.query(SlotHold).filter(
        SlotHold.id == hold_id,
        SlotHold.organization_id == organization_id,
    ).with_for_update().first()

    if not hold:
        raise SlotHoldError("Hold not found", "NOT_FOUND")

    if hold.status != SlotHoldStatus.ACTIVE.value:
        raise SlotHoldError(f"Hold is {hold.status}, cannot extend", "INVALID_STATUS")

    if hold.expires_at <= now:
        hold.status = SlotHoldStatus.EXPIRED.value
        db.flush()
        raise SlotHoldError("Hold has expired", "EXPIRED")

    # Calculate new expiry, capped at MAX_HOLD_TTL_SECONDS from creation
    new_expires = hold.expires_at + timedelta(seconds=additional_seconds)
    max_expires = hold.created_at + timedelta(seconds=MAX_HOLD_TTL_SECONDS)

    if new_expires > max_expires:
        new_expires = max_expires

    if new_expires <= hold.expires_at:
        raise SlotHoldError(
            f"Hold already at maximum duration ({MAX_HOLD_TTL_SECONDS} seconds)",
            "MAX_TTL_REACHED"
        )

    hold.expires_at = new_expires

    logger.info(f"Slot hold extended: id={hold_id} new_expires={new_expires.isoformat()}")

    return _hold_to_dict(hold)


async def convert_hold_to_appointment(
    hold_id: int,
    appointment_data: dict,
    organization_id: int,
    user_id: int,
    db: Session,
    models: dict,
) -> dict:
    """
    Atomically convert a hold into a real appointment.

    Creates the appointment and marks the hold as converted in the same
    transaction to prevent any window for double-booking.

    Args:
        hold_id: The hold to convert
        appointment_data: Dict with appointment fields (title, meeting_type, etc.)
        organization_id: Tenant ID
        user_id: ID of user performing the conversion
        db: SQLAlchemy session
        models: Model dictionary

    Returns:
        Dict with appointment ID and hold ID

    Raises:
        SlotHoldError: If hold not found, expired, or already converted
    """
    SlotHold = models.get('SlotHold')
    Appointment = models.get('Appointment')

    if not SlotHold or not Appointment:
        raise SlotHoldError("Scheduler models not available", "MODELS_UNAVAILABLE")

    now = datetime.now(timezone.utc)

    # Lock the hold row
    hold = db.query(SlotHold).filter(
        SlotHold.id == hold_id,
        SlotHold.organization_id == organization_id,
    ).with_for_update().first()

    if not hold:
        raise SlotHoldError("Hold not found", "NOT_FOUND")

    if hold.status == SlotHoldStatus.CONVERTED.value and hold.converted_to_appointment_id:
        # Idempotent: hold already converted — return the existing appointment
        existing = db.query(Appointment).filter(
            Appointment.id == hold.converted_to_appointment_id,
            Appointment.organization_id == organization_id,
        ).first()
        if existing:
            logger.info(
                "Hold %s already converted to appointment %s — returning existing (idempotent)",
                hold_id, existing.id,
            )
            return {'hold_id': hold.id, 'appointment_id': existing.id, 'idempotent': True}

    if hold.status != SlotHoldStatus.ACTIVE.value:
        raise SlotHoldError(f"Hold is {hold.status}, cannot convert", "INVALID_STATUS")

    if hold.expires_at <= now:
        hold.status = SlotHoldStatus.EXPIRED.value
        db.flush()
        raise SlotHoldError("Hold has expired. Please create a new hold.", "EXPIRED")

    # Import MeetingType/MeetingMode for enum parsing
    from smart_scheduler_models import MeetingType, MeetingMode

    # Parse meeting enums with safe fallback
    meeting_type = MeetingType.CUSTOM
    if appointment_data.get('meeting_type'):
        try:
            meeting_type = MeetingType(appointment_data['meeting_type'])
        except ValueError:
            pass

    meeting_mode = MeetingMode.PHONE
    if appointment_data.get('meeting_mode'):
        try:
            meeting_mode = MeetingMode(appointment_data['meeting_mode'])
        except ValueError:
            pass

    # Calculate duration
    duration_minutes = appointment_data.get('duration_minutes')
    if not duration_minutes:
        delta = hold.end_time - hold.start_time
        duration_minutes = int(delta.total_seconds() / 60)

    # Create appointment using the hold's time slot
    appointment = Appointment(
        organization_id=organization_id,
        assigned_user_id=hold.lo_id,
        created_by_user_id=user_id,
        appointment_type_id=appointment_data.get('appointment_type_id'),
        lead_id=appointment_data.get('lead_id'),
        loan_id=appointment_data.get('loan_id'),
        contact_id=appointment_data.get('contact_id'),
        title=appointment_data.get('title', f"Appointment with {hold.held_for_name or 'Client'}"),
        description=appointment_data.get('description'),
        meeting_type=meeting_type,
        meeting_mode=meeting_mode,
        scheduled_start=hold.start_time,
        scheduled_end=hold.end_time,
        duration_minutes=duration_minutes,
        timezone=appointment_data.get('timezone', 'America/Chicago'),
        attendee_name=hold.held_for_name or appointment_data.get('attendee_name'),
        attendee_email=hold.held_for_email or appointment_data.get('attendee_email'),
        attendee_phone=hold.held_for_phone or appointment_data.get('attendee_phone'),
        attendee_notes=appointment_data.get('attendee_notes'),
        intake_responses=appointment_data.get('intake_responses', {}),
        idempotency_key=f"hold-{hold_id}",
        status=AppointmentStatus.BOOKED,
        status_changed_at=now,
        booked_by_ai=hold.held_by == 'ai_conversation',
        ai_booking_context=appointment_data.get('ai_booking_context', {
            'converted_from_hold': hold.id,
            'hold_source': hold.held_by,
            'conversation_id': hold.conversation_id,
        }),
    )

    db.add(appointment)
    db.flush()  # Get appointment.id

    # Mark hold as converted
    hold.status = SlotHoldStatus.CONVERTED.value
    hold.converted_to_appointment_id = appointment.id
    hold.converted_at = now

    logger.info(
        f"Hold {hold_id} converted to appointment {appointment.id} "
        f"for LO {hold.lo_id}"
    )

    return {
        'hold_id': hold.id,
        'appointment_id': appointment.id,
        'status': 'converted',
        'scheduled_start': appointment.scheduled_start.isoformat(),
        'scheduled_end': appointment.scheduled_end.isoformat(),
        'attendee_name': appointment.attendee_name,
    }


async def release_hold(
    hold_id: int,
    organization_id: int,
    db: Session,
    models: dict,
) -> dict:
    """
    Explicitly release a hold before it expires.

    Args:
        hold_id: The hold to release
        organization_id: Tenant ID
        db: SQLAlchemy session
        models: Model dictionary

    Returns:
        Dict confirming release
    """
    SlotHold = models.get('SlotHold')
    if not SlotHold:
        raise SlotHoldError("Scheduler models not available", "MODELS_UNAVAILABLE")

    now = datetime.now(timezone.utc)

    hold = db.query(SlotHold).filter(
        SlotHold.id == hold_id,
        SlotHold.organization_id == organization_id,
    ).first()

    if not hold:
        raise SlotHoldError("Hold not found", "NOT_FOUND")

    if hold.status != SlotHoldStatus.ACTIVE.value:
        # Idempotent: if already released/expired/converted, just return
        return {
            'hold_id': hold.id,
            'status': hold.status,
            'message': f'Hold was already {hold.status}',
        }

    hold.status = SlotHoldStatus.RELEASED.value
    hold.released_at = now

    logger.info(f"Slot hold released: id={hold_id}")

    return {
        'hold_id': hold.id,
        'status': 'released',
        'message': 'Hold released successfully',
    }


async def cleanup_expired_holds(
    db: Session,
    models: dict,
) -> dict:
    """
    Mark all expired holds as expired. Designed to run every minute via
    background task or scheduler.

    Returns:
        Dict with count of expired holds
    """
    SlotHold = models.get('SlotHold')
    if not SlotHold:
        return {'expired_count': 0}

    now = datetime.now(timezone.utc)

    # Bulk update in a single query
    expired_count = db.query(SlotHold).filter(
        SlotHold.status == SlotHoldStatus.ACTIVE.value,
        SlotHold.expires_at <= now,
    ).update(
        {SlotHold.status: SlotHoldStatus.EXPIRED.value},
        synchronize_session='fetch'
    )

    if expired_count > 0:
        logger.info(f"Cleaned up {expired_count} expired slot holds")

    return {'expired_count': expired_count}


async def get_active_holds(
    lo_id: int,
    organization_id: int,
    db: Session,
    models: dict,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[dict]:
    """
    Get active (non-expired) holds for a loan officer within an optional date range.

    Args:
        lo_id: Loan officer ID
        organization_id: Tenant ID
        db: SQLAlchemy session
        models: Model dictionary
        start_date: Optional filter start
        end_date: Optional filter end

    Returns:
        List of hold dicts
    """
    SlotHold = models.get('SlotHold')
    if not SlotHold:
        return []

    now = datetime.now(timezone.utc)

    query = db.query(SlotHold).filter(
        SlotHold.lo_id == lo_id,
        SlotHold.organization_id == organization_id,
        SlotHold.status == SlotHoldStatus.ACTIVE.value,
        SlotHold.expires_at > now,
    )

    if start_date:
        query = query.filter(SlotHold.start_time >= start_date)
    if end_date:
        query = query.filter(SlotHold.end_time <= end_date)

    holds = query.order_by(SlotHold.start_time).all()
    return [_hold_to_dict(h) for h in holds]


async def is_slot_held(
    lo_id: int,
    start_time: datetime,
    end_time: datetime,
    organization_id: int,
    db: Session,
    models: dict,
    exclude_hold_id: Optional[int] = None,
) -> bool:
    """
    Check whether a time slot is currently held by an active, non-expired hold.

    Args:
        lo_id: Loan officer ID
        start_time: Slot start
        end_time: Slot end
        organization_id: Tenant ID
        db: SQLAlchemy session
        models: Model dictionary
        exclude_hold_id: Optional hold to exclude (for extending/checking own hold)

    Returns:
        True if the slot has an active hold
    """
    SlotHold = models.get('SlotHold')
    if not SlotHold:
        return False

    now = datetime.now(timezone.utc)

    filters = [
        SlotHold.lo_id == lo_id,
        SlotHold.organization_id == organization_id,
        SlotHold.status == SlotHoldStatus.ACTIVE.value,
        SlotHold.expires_at > now,
        SlotHold.start_time < end_time,
        SlotHold.end_time > start_time,
    ]

    if exclude_hold_id is not None:
        filters.append(SlotHold.id != exclude_hold_id)

    return db.query(SlotHold).filter(and_(*filters)).first() is not None


async def get_hold_stats(
    organization_id: int,
    db: Session,
    models: dict,
    days: int = 30,
) -> dict:
    """
    Get hold analytics for an organization.

    Returns conversion rate, average hold duration, expiry rate, etc.

    Args:
        organization_id: Tenant ID
        db: SQLAlchemy session
        models: Model dictionary
        days: Lookback period in days

    Returns:
        Dict with analytics
    """
    SlotHold = models.get('SlotHold')
    if not SlotHold:
        return {
            'period_days': days,
            'total_holds': 0,
            'converted': 0,
            'expired': 0,
            'released': 0,
            'active': 0,
            'conversion_rate': 0.0,
            'expiry_rate': 0.0,
            'avg_hold_duration_seconds': 0.0,
        }

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Aggregate counts by status
    stats = db.query(
        SlotHold.status,
        sa_func.count(SlotHold.id).label('count'),
    ).filter(
        SlotHold.organization_id == organization_id,
        SlotHold.created_at >= cutoff,
    ).group_by(SlotHold.status).all()

    counts = {row.status: row.count for row in stats}
    total = sum(counts.values())
    converted = counts.get(SlotHoldStatus.CONVERTED.value, 0)
    expired = counts.get(SlotHoldStatus.EXPIRED.value, 0)
    released = counts.get(SlotHoldStatus.RELEASED.value, 0)
    active = counts.get(SlotHoldStatus.ACTIVE.value, 0)

    # Conversion rate = converted / (converted + expired + released)
    resolved = converted + expired + released
    conversion_rate = (converted / resolved * 100) if resolved > 0 else 0.0
    expiry_rate = (expired / resolved * 100) if resolved > 0 else 0.0

    # Average hold duration for converted holds (creation to conversion)
    avg_duration = db.query(
        sa_func.avg(
            sa_func.extract('epoch', SlotHold.converted_at - SlotHold.created_at)
        )
    ).filter(
        SlotHold.organization_id == organization_id,
        SlotHold.status == SlotHoldStatus.CONVERTED.value,
        SlotHold.created_at >= cutoff,
        SlotHold.converted_at.isnot(None),
    ).scalar()

    return {
        'period_days': days,
        'total_holds': total,
        'converted': converted,
        'expired': expired,
        'released': released,
        'active': active,
        'conversion_rate': round(conversion_rate, 1),
        'expiry_rate': round(expiry_rate, 1),
        'avg_hold_duration_seconds': round(float(avg_duration or 0), 1),
    }


def get_active_holds_for_availability(
    user_ids: list,
    start_dt: datetime,
    end_dt: datetime,
    organization_id: int,
    db: Session,
    models: dict,
) -> list:
    """
    Synchronous helper for the availability engine to get active holds.

    Returns a list of (lo_id, start_time, end_time) tuples representing
    currently held time slots, suitable for the slot generation loop.

    This is NOT async because _generate_available_slots is synchronous.
    """
    SlotHold = models.get('SlotHold')
    if not SlotHold:
        return []

    now = datetime.now(timezone.utc)

    # Strip timezone info if datetimes are naive (to match the naive UTC
    # used in _generate_available_slots)
    if start_dt.tzinfo is not None:
        start_dt_query = start_dt
    else:
        start_dt_query = start_dt.replace(tzinfo=timezone.utc)

    if end_dt.tzinfo is not None:
        end_dt_query = end_dt
    else:
        end_dt_query = end_dt.replace(tzinfo=timezone.utc)

    holds = db.query(
        SlotHold.lo_id,
        SlotHold.start_time,
        SlotHold.end_time,
    ).filter(
        SlotHold.lo_id.in_(user_ids),
        SlotHold.organization_id == organization_id,
        SlotHold.status == SlotHoldStatus.ACTIVE.value,
        SlotHold.expires_at > now,
        SlotHold.start_time < end_dt_query,
        SlotHold.end_time > start_dt_query,
    ).all()

    return [(h.lo_id, h.start_time, h.end_time) for h in holds]


def _hold_to_dict(hold) -> dict:
    """Convert a SlotHold ORM instance to a response dict."""
    return {
        'id': hold.id,
        'organization_id': hold.organization_id,
        'lo_id': hold.lo_id,
        'start_time': hold.start_time.isoformat() if hold.start_time else None,
        'end_time': hold.end_time.isoformat() if hold.end_time else None,
        'held_by': hold.held_by,
        'held_for_name': hold.held_for_name,
        'held_for_phone': hold.held_for_phone,
        'held_for_email': hold.held_for_email,
        'conversation_id': hold.conversation_id,
        'created_at': hold.created_at.isoformat() if hold.created_at else None,
        'expires_at': hold.expires_at.isoformat() if hold.expires_at else None,
        'status': hold.status,
        'converted_to_appointment_id': hold.converted_to_appointment_id,
        'converted_at': hold.converted_at.isoformat() if hold.converted_at else None,
        'released_at': hold.released_at.isoformat() if hold.released_at else None,
    }
