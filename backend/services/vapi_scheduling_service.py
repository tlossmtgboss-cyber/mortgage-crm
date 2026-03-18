"""
Vapi AI Receptionist - Native Appointment Scheduling Service

Replaces Calendly integration with direct booking through the Smart Scheduler.
Provides real availability checking, conflict-free booking, slot holds, and
confirmation workflows for the Vapi AI receptionist.
"""

import logging
import uuid as uuid_lib
from datetime import datetime, timedelta, date, time, timezone
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode,
    DEFAULT_WORKING_HOURS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# MODEL LOADING
# =============================================================================

def _load_scheduler_models():
    """Lazy-load scheduler models to avoid circular imports."""
    try:
        from smart_scheduler_models import create_smart_scheduler_models
        from database import Base
        models = create_smart_scheduler_models(Base)
        return models
    except ImportError:
        logger.warning("Smart scheduler models not available via factory, trying direct import")

    # Fallback: try importing from where they're registered
    try:
        import main
        return {
            'SchedulerConfig': getattr(main, 'SchedulerConfig', None),
            'Appointment': getattr(main, 'Appointment', None),
            'BlockedTime': getattr(main, 'BlockedTime', None),
            'AppointmentType': getattr(main, 'AppointmentType', None),
            'BookingLink': getattr(main, 'BookingLink', None),
        }
    except Exception as e:
        logger.error(f"Failed to load scheduler models from main: {e}")
        return {}


def _get_models():
    """Get scheduler models, caching on module level."""
    global _cached_models
    if '_cached_models' not in globals() or _cached_models is None:
        _cached_models = _load_scheduler_models()
    return _cached_models

_cached_models = None


# =============================================================================
# AVAILABILITY / SLOT GENERATION
# =============================================================================

def get_available_slots_for_vapi(
    db: Session,
    org_id: int,
    target_date: date,
    duration_minutes: int = 30,
    user_id: Optional[int] = None,
    num_days: int = 3,
) -> List[Dict[str, Any]]:
    """
    Generate available time slots for a date range, respecting:
    - Working hours from SchedulerConfig
    - Blocked times (PTO, holidays)
    - Existing booked/tentative appointments (with buffer)
    - Cross-source calendar conflicts
    - Lunch break enforcement
    - Minimum notice period
    - Existing soft holds

    Returns a list of slot dicts formatted for Vapi conversation.
    """
    models = _get_models()
    SchedulerConfig = models.get('SchedulerConfig')
    BlockedTime = models.get('BlockedTime')
    Appointment = models.get('Appointment')

    if not SchedulerConfig or not Appointment:
        logger.error("Scheduler models not available for slot generation")
        return []

    # Determine user IDs to check
    if user_id:
        user_ids = [user_id]
    else:
        # Get all active LOs/users with scheduler configs for this org
        configs = db.query(SchedulerConfig).filter(
            SchedulerConfig.organization_id == org_id,
            SchedulerConfig.is_active == True,
            SchedulerConfig.user_id.isnot(None),
        ).all()
        user_ids = [c.user_id for c in configs]

        if not user_ids:
            # Fallback: try to get any user in the org
            try:
                from database.models import User
                users = db.query(User).filter(
                    User.organization_id == org_id,
                    User.is_active == True,
                ).limit(5).all()
                user_ids = [u.id for u in users]
            except Exception as e:
                logger.debug(f"User fallback lookup failed for org {org_id}: {e}")

    if not user_ids:
        logger.warning(f"No users found for org {org_id}")
        return []

    end_date = target_date + timedelta(days=num_days - 1)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    all_slots = []

    for uid in user_ids:
        # Load user config
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == uid,
            SchedulerConfig.organization_id == org_id,
        ).first()

        working_hours = config.working_hours if config and config.working_hours else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else 5
        buffer_after = config.buffer_after_minutes if config else 5
        min_notice = config.min_notice_hours if config else 2
        max_per_day = config.max_meetings_per_day if config else 8
        enforce_lunch = getattr(config, 'enforce_lunch_break', True) if config else True
        lunch_start_t = getattr(config, 'lunch_break_start', time(12, 0)) if config else time(12, 0)
        lunch_end_t = getattr(config, 'lunch_break_end', time(13, 0)) if config else time(13, 0)

        min_booking_time = now + timedelta(hours=min_notice)
        start_dt = datetime.combine(target_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        # Query blocked times
        blocked_filters = [
            BlockedTime.is_active == True,
            or_(
                BlockedTime.user_id == uid,
                BlockedTime.applies_to_all_users == True,
            ),
            BlockedTime.start_datetime <= end_dt,
            BlockedTime.end_datetime >= start_dt,
        ]
        if BlockedTime:
            blocked_query = db.query(BlockedTime).filter(
                *blocked_filters,
                BlockedTime.organization_id == org_id,
            )
            blocked_times = blocked_query.all()
        else:
            blocked_times = []

        # Query existing appointments
        appt_query = db.query(Appointment).filter(
            Appointment.assigned_user_id == uid,
            Appointment.status.in_([
                AppointmentStatus.BOOKED.value if hasattr(AppointmentStatus.BOOKED, 'value') else 'booked',
                AppointmentStatus.TENTATIVE.value if hasattr(AppointmentStatus.TENTATIVE, 'value') else 'tentative',
            ]),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt,
            Appointment.organization_id == org_id,
        )
        existing_appts = appt_query.all()

        # Cross-source conflicts
        cross_source_busy = _get_cross_source_conflicts(db, uid, start_dt, end_dt, org_id)

        current_date = target_date
        while current_date <= end_date:
            day_name = current_date.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            # Check max meetings per day
            if max_per_day:
                day_appts = [a for a in existing_appts
                             if a.scheduled_start and a.scheduled_start.date() == current_date]
                if len(day_appts) >= max_per_day:
                    current_date += timedelta(days=1)
                    continue

            try:
                work_start = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                work_end = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_date += timedelta(days=1)
                continue

            slot_start = datetime.combine(current_date, work_start)
            day_end = datetime.combine(current_date, work_end)
            lunch_start = datetime.combine(current_date, lunch_start_t) if enforce_lunch else None
            lunch_end = datetime.combine(current_date, lunch_end_t) if enforce_lunch else None

            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                # Skip past/too-soon slots
                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Skip lunch break
                if lunch_start and lunch_end and slot_start < lunch_end and slot_end > lunch_start:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check blocked times
                is_blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked_times
                )
                if is_blocked:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check appointment conflicts (with buffers)
                has_conflict = any(
                    slot_start < (appt.scheduled_end + timedelta(minutes=buffer_after)) and
                    slot_end > (appt.scheduled_start - timedelta(minutes=buffer_before))
                    for appt in existing_appts
                )

                # Check cross-source conflicts
                if not has_conflict and cross_source_busy:
                    has_conflict = any(
                        slot_start < (busy_end + timedelta(minutes=buffer_after)) and
                        slot_end > (busy_start - timedelta(minutes=buffer_before))
                        for busy_start, busy_end in cross_source_busy
                    )

                # Check soft holds
                if not has_conflict:
                    has_conflict = _is_slot_held(uid, slot_start, slot_end, db=db, org_id=org_id)

                if not has_conflict:
                    all_slots.append({
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                        "date": current_date.isoformat(),
                        "display_time": slot_start.strftime("%-I:%M %p"),
                        "display_date": current_date.strftime("%A, %B %-d"),
                        "user_id": uid,
                    })

                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

    # Deduplicate and sort
    unique_slots = list({s["start"]: s for s in all_slots}.values())
    unique_slots.sort(key=lambda x: x["start"])
    return unique_slots


def format_slots_for_voice(slots: List[Dict], max_slots: int = 6) -> str:
    """
    Format available slots into a conversational string for the AI to read.
    Groups by date for natural conversation flow.
    """
    if not slots:
        return "I don't have any available slots for that time period."

    limited = slots[:max_slots]
    by_date = {}
    for slot in limited:
        d = slot.get("display_date", slot.get("date", ""))
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(slot.get("display_time", ""))

    parts = []
    for display_date, times in by_date.items():
        time_list = ", ".join(times[:-1]) + (f" and {times[-1]}" if len(times) > 1 else times[0])
        parts.append(f"On {display_date}, I have {time_list}")

    result = ". ".join(parts) + "."

    remaining = len(slots) - max_slots
    if remaining > 0:
        result += f" I also have {remaining} more slots available if none of those work."

    return result


def parse_date_reference(text: str) -> Tuple[date, date]:
    """
    Parse natural language date references into a date range.
    Supports: 'today', 'tomorrow', 'this week', 'next week', 'Monday', etc.
    Returns (start_date, end_date).
    """
    today = date.today()
    text_lower = (text or "").strip().lower()

    if not text_lower or text_lower == "today":
        return today, today

    if text_lower == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow

    if text_lower in ("this week", "this week please"):
        # Rest of this week (today through Friday/Sunday)
        days_until_sunday = 6 - today.weekday()
        end = today + timedelta(days=max(days_until_sunday, 1))
        return today, end

    if text_lower in ("next week", "next week please"):
        # Monday through Friday of next week
        days_until_monday = 7 - today.weekday()
        if today.weekday() == 0:  # Today is Monday
            days_until_monday = 7
        start = today + timedelta(days=days_until_monday)
        end = start + timedelta(days=4)  # Through Friday
        return start, end

    # Day names: "monday", "tuesday", etc.
    day_names = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    for day_name, day_num in day_names.items():
        if day_name in text_lower:
            days_ahead = (day_num - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next occurrence
            target = today + timedelta(days=days_ahead)
            return target, target

    # Try ISO date parse
    try:
        parsed = datetime.fromisoformat(text_lower.replace('Z', '+00:00'))
        return parsed.date(), parsed.date()
    except (ValueError, TypeError):
        pass

    # Default: next 3 business days
    return today + timedelta(days=1), today + timedelta(days=3)


# =============================================================================
# SLOT HOLDS
# =============================================================================

def hold_slot(
    user_id: int,
    start: datetime,
    end: datetime,
    caller_phone: str,
    db: Session,
    org_id: int,
) -> Dict[str, Any]:
    """
    Place a soft hold on a time slot during conversation.
    DB-backed via SlotHold model for multi-worker safety.
    Prevents double-booking while AI confirms with caller.
    Auto-expires after 5 minutes (TTL enforced at DB level).
    """
    from smart_scheduler_models import SlotHoldStatus

    models = _get_models()
    SlotHold = models.get('SlotHold') if models else None

    if not SlotHold:
        # Fallback: log warning, return a transient hold ID (no persistence)
        logger.warning("SlotHold model not available — hold is not persisted")
        hold_id = str(uuid_lib.uuid4())[:12].upper()
        return {
            "hold_id": hold_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat(),
            "expires_in_seconds": 300,
            "persisted": False,
        }

    now = datetime.now(timezone.utc)
    ttl_seconds = 300
    expires_at = now + timedelta(seconds=ttl_seconds)

    hold = SlotHold(
        organization_id=org_id,
        lo_id=user_id,
        start_time=start,
        end_time=end,
        held_by="ai_conversation",
        held_for_phone=caller_phone,
        expires_at=expires_at,
        status=SlotHoldStatus.ACTIVE.value,
    )

    db.add(hold)
    db.flush()

    logger.info(
        f"Slot hold {hold.id} created: user={user_id}, "
        f"{start.strftime('%m/%d %H:%M')}-{end.strftime('%H:%M')}, "
        f"expires={expires_at.strftime('%H:%M:%S')}"
    )

    return {
        "hold_id": hold.id,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": ttl_seconds,
        "persisted": True,
    }


def release_hold(hold_id, db: Optional[Session] = None, org_id: Optional[int] = None) -> bool:
    """Release a held slot. DB-backed."""
    if db is None:
        logger.warning(f"Cannot release hold {hold_id} — no DB session")
        return False

    from smart_scheduler_models import SlotHoldStatus

    models = _get_models()
    SlotHold = models.get('SlotHold') if models else None

    if not SlotHold:
        logger.warning(f"SlotHold model not available — cannot release hold {hold_id}")
        return False

    hold = db.query(SlotHold).filter(SlotHold.id == hold_id).first()
    if not hold:
        logger.info(f"Hold {hold_id} not found (may have expired)")
        return False

    hold.status = SlotHoldStatus.RELEASED.value
    hold.released_at = datetime.now(timezone.utc)
    logger.info(f"Slot hold {hold_id} released")
    return True


def get_hold(hold_id, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    """Get hold details from DB, returning None if expired or not found."""
    if db is None:
        return None

    from smart_scheduler_models import SlotHoldStatus

    models = _get_models()
    SlotHold = models.get('SlotHold') if models else None

    if not SlotHold:
        return None

    now = datetime.now(timezone.utc)
    hold = db.query(SlotHold).filter(
        SlotHold.id == hold_id,
        SlotHold.status == SlotHoldStatus.ACTIVE.value,
        SlotHold.expires_at > now,
    ).first()

    if not hold:
        return None

    return {
        "user_id": hold.lo_id,
        "start": hold.start_time,
        "end": hold.end_time,
        "expires_at": hold.expires_at,
        "phone": hold.held_for_phone,
        "created_at": hold.created_at,
    }


def _is_slot_held(user_id: int, slot_start: datetime, slot_end: datetime,
                  db: Optional[Session] = None, org_id: Optional[int] = None) -> bool:
    """Check if a slot overlaps with any active DB-backed hold."""
    if db is None:
        return False

    from smart_scheduler_models import SlotHoldStatus

    models = _get_models()
    SlotHold = models.get('SlotHold') if models else None

    if not SlotHold:
        return False

    now = datetime.now(timezone.utc)
    filters = [
        SlotHold.lo_id == user_id,
        SlotHold.status == SlotHoldStatus.ACTIVE.value,
        SlotHold.expires_at > now,
        SlotHold.start_time < slot_end,
        SlotHold.end_time > slot_start,
    ]
    if org_id:
        filters.append(SlotHold.organization_id == org_id)

    return db.query(SlotHold).filter(*filters).first() is not None


# =============================================================================
# BOOKING
# =============================================================================

def book_appointment(
    db: Session,
    org_id: int,
    assigned_user_id: int,
    start_time: datetime,
    duration_minutes: int,
    attendee_name: str,
    attendee_email: Optional[str],
    attendee_phone: Optional[str],
    meeting_type_str: str = "discovery_call",
    notes: Optional[str] = None,
    lead_id: Optional[int] = None,
    hold_id: Optional[str] = None,
    vapi_call_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a real Appointment record with double-booking prevention.

    Uses SELECT FOR UPDATE to prevent race conditions.
    Creates lead record if caller is new.
    Returns appointment details for Vapi confirmation.
    """
    from sqlalchemy.exc import OperationalError

    models = _get_models()
    Appointment = models.get('Appointment')

    if not Appointment:
        raise ValueError("Appointment model not available")

    end_time = start_time + timedelta(minutes=duration_minutes)

    # Map meeting type string to enum
    meeting_type_map = {
        "discovery_call": MeetingType.DISCOVERY_CALL,
        "pre_approval_review": MeetingType.PRE_APPROVAL_REVIEW,
        "application_walkthrough": MeetingType.APPLICATION_WALKTHROUGH,
        "document_review": MeetingType.DOCUMENT_REVIEW,
        "rate_lock_discussion": MeetingType.RATE_LOCK_DISCUSSION,
        "closing_prep": MeetingType.CLOSING_PREP,
        "general": MeetingType.CUSTOM,
    }
    meeting_type = meeting_type_map.get(meeting_type_str, MeetingType.DISCOVERY_CALL)

    # Double-booking check with row locking
    try:
        conflict = db.query(Appointment).filter(
            and_(
                Appointment.assigned_user_id == assigned_user_id,
                Appointment.organization_id == org_id,
                Appointment.status.notin_(['cancelled', 'no_show']),
                Appointment.scheduled_start < end_time,
                Appointment.scheduled_end > start_time,
            )
        ).with_for_update(nowait=True).first()
    except OperationalError:
        raise ValueError("This time slot is being booked by another caller. Please select a different time.")

    if conflict:
        raise ValueError("This time slot is no longer available. Please select a different time.")

    # Ensure lead exists
    if not lead_id and (attendee_email or attendee_phone):
        lead_id = _ensure_lead_for_ai_booking(
            db, org_id, assigned_user_id,
            attendee_name, attendee_email, attendee_phone
        )

    # Build title
    title = f"Discovery Call with {attendee_name}" if attendee_name else "AI-Booked Appointment"

    appointment = Appointment(
        organization_id=org_id,
        assigned_user_id=assigned_user_id,
        lead_id=lead_id,
        title=title,
        description=notes or "Appointment booked via AI receptionist",
        meeting_type=meeting_type,
        meeting_mode=MeetingMode.PHONE,
        scheduled_start=start_time,
        scheduled_end=end_time,
        duration_minutes=duration_minutes,
        attendee_name=attendee_name,
        attendee_email=attendee_email,
        attendee_phone=attendee_phone,
        status=AppointmentStatus.BOOKED,
        status_changed_at=datetime.now(timezone.utc),
        booked_by_ai=True,
        auto_confirmed=True,
        external_source="ai_booked",
        ai_booking_context={
            "source": "vapi_receptionist",
            "vapi_call_id": vapi_call_id,
            "booked_at": datetime.now(timezone.utc).isoformat(),
        },
        intake_responses={"notes": notes} if notes else {},
    )

    db.add(appointment)

    # Release hold if one was used
    if hold_id:
        release_hold(hold_id, db=db, org_id=org_id)

    # Log CRM activity
    _log_ai_booking_activity(
        db, org_id, assigned_user_id, lead_id,
        title, start_time, attendee_name
    )

    db.flush()  # Get the appointment ID

    # Get assigned user name for confirmation
    user_name = _get_user_display_name(db, assigned_user_id)

    return {
        "appointment_id": appointment.id,
        "title": title,
        "scheduled_start": start_time.isoformat(),
        "scheduled_end": end_time.isoformat(),
        "duration_minutes": duration_minutes,
        "display_date": start_time.strftime("%A, %B %-d"),
        "display_time": start_time.strftime("%-I:%M %p"),
        "assigned_to": user_name,
        "attendee_name": attendee_name,
        "attendee_email": attendee_email,
        "meeting_type": meeting_type_str,
        "status": "booked",
        "lead_id": lead_id,
    }


def confirm_booking(
    db: Session,
    hold_id: str,
    org_id: int,
    attendee_name: str,
    attendee_email: Optional[str],
    attendee_phone: Optional[str],
    notes: Optional[str] = None,
    vapi_call_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert a soft hold into a confirmed appointment.
    This is the final step after the caller verbally agrees.
    """
    hold = get_hold(hold_id, db=db)
    if not hold:
        raise ValueError(
            "The held time slot has expired. Let me check for new availability."
        )

    result = book_appointment(
        db=db,
        org_id=org_id,
        assigned_user_id=hold["user_id"],
        start_time=hold["start"],
        duration_minutes=int((hold["end"] - hold["start"]).total_seconds() / 60),
        attendee_name=attendee_name,
        attendee_email=attendee_email,
        attendee_phone=attendee_phone,
        notes=notes,
        hold_id=hold_id,
        vapi_call_id=vapi_call_id,
    )

    # Send confirmation notifications in background
    _send_booking_confirmations(
        db=db,
        appointment_data=result,
        attendee_email=attendee_email,
        attendee_phone=attendee_phone,
    )

    return result


# =============================================================================
# CALLER IDENTIFICATION
# =============================================================================

def classify_caller(db: Session, phone_number: str) -> Dict[str, Any]:
    """
    Enhanced caller classification:
    - new_lead: No record found
    - active_client: Has active loan in pipeline
    - mum_client: Has funded/closed loan (past client)
    - referral_partner: Is a registered referral partner
    - prospect: Has a lead record but no loan
    """
    from sqlalchemy import or_

    cleaned_phone = ''.join(filter(str.isdigit, phone_number))
    if len(cleaned_phone) >= 10:
        cleaned_phone = cleaned_phone[-10:]

    result = {
        "caller_type": "new_lead",
        "found": False,
        "lead_id": None,
        "lead_name": None,
        "lead_stage": None,
        "active_loan": None,
        "funded_loans_count": 0,
        "assigned_lo_id": None,
        "assigned_lo_name": None,
        "last_contact": None,
        "context": "New caller - no existing record found",
    }

    # 1. Check leads
    try:
        from database.models.lead_loan import Lead
        lead = db.query(Lead).filter(
            Lead.phone.ilike(f"%{cleaned_phone}")
        ).first()

        if lead:
            result["found"] = True
            result["lead_id"] = lead.id
            result["lead_name"] = getattr(lead, 'name', None) or f"{lead.first_name or ''} {lead.last_name or ''}".strip()
            result["lead_stage"] = str(lead.stage) if lead.stage else None
            result["assigned_lo_id"] = lead.owner_id
            result["last_contact"] = lead.last_contact.isoformat() if lead.last_contact else None

            # Get LO name
            if lead.owner_id:
                result["assigned_lo_name"] = _get_user_display_name(db, lead.owner_id)
    except Exception as e:
        logger.warning(f"Lead lookup failed: {e}")

    # 2. Check loans (active and funded)
    try:
        from database.models.lead_loan import Loan

        # Active loans
        active_loan = db.query(Loan).filter(
            or_(
                Loan.borrower_phone.ilike(f"%{cleaned_phone}"),
                Loan.co_borrower_phone.ilike(f"%{cleaned_phone}"),
            ),
            Loan.stage.notin_([
                'FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY'
            ]),
        ).first()

        if active_loan:
            result["caller_type"] = "active_client"
            result["found"] = True
            result["active_loan"] = {
                "id": active_loan.id,
                "loan_number": active_loan.loan_number,
                "stage": str(active_loan.stage),
                "amount": float(active_loan.amount) if active_loan.amount else None,
                "borrower_name": active_loan.borrower_name,
                "closing_date": active_loan.closing_date.isoformat() if active_loan.closing_date else None,
            }
            if active_loan.loan_officer_id:
                result["assigned_lo_id"] = active_loan.loan_officer_id
                result["assigned_lo_name"] = _get_user_display_name(db, active_loan.loan_officer_id)
            result["context"] = (
                f"Active client: {active_loan.borrower_name}, "
                f"Loan #{active_loan.loan_number}, Stage: {active_loan.stage}"
            )
        else:
            # Check funded loans (MUM - past clients)
            funded_count = db.query(Loan).filter(
                or_(
                    Loan.borrower_phone.ilike(f"%{cleaned_phone}"),
                    Loan.co_borrower_phone.ilike(f"%{cleaned_phone}"),
                ),
                Loan.stage == 'FUNDED',
            ).count()

            if funded_count > 0:
                result["caller_type"] = "mum_client"
                result["found"] = True
                result["funded_loans_count"] = funded_count
                result["context"] = f"Past client with {funded_count} funded loan(s)"
    except Exception as e:
        logger.warning(f"Loan lookup failed: {e}")

    # 3. Check referral partners
    if not result["found"] or result["caller_type"] == "new_lead":
        try:
            from database.models.referral import ReferralPartner
            partner = db.query(ReferralPartner).filter(
                ReferralPartner.phone.ilike(f"%{cleaned_phone}")
            ).first()

            if partner:
                result["caller_type"] = "referral_partner"
                result["found"] = True
                result["lead_name"] = partner.name
                result["context"] = f"Referral partner: {partner.name}"
        except Exception as e:
            logger.debug(f"Referral partner lookup skipped: {e}")

    # 4. If found as lead but no active loan, classify as prospect
    if result["found"] and result["caller_type"] == "new_lead":
        result["caller_type"] = "prospect"
        result["context"] = f"Existing prospect: {result['lead_name']}, Stage: {result['lead_stage']}"

    return result


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_cross_source_conflicts(
    db: Session, user_id: int,
    start_dt: datetime, end_dt: datetime,
    org_id: int,
) -> List[Tuple[datetime, datetime]]:
    """Gather busy times from all calendar sources."""
    conflicts = []

    # Source 1: ScheduledAppointment (legacy AI-booked)
    try:
        from services.smart_scheduler_service import ScheduledAppointment as SAModel
        sa_query = db.query(SAModel).filter(
            SAModel.loan_officer_id == user_id,
            SAModel.status.in_(["scheduled", "confirmed"]),
            SAModel.start_time >= start_dt,
            SAModel.start_time <= end_dt,
        )
        if org_id:
            sa_query = sa_query.filter(SAModel.organization_id == org_id)
        for a in sa_query.all():
            if a.start_time and a.end_time:
                conflicts.append((a.start_time, a.end_time))
    except Exception as e:
        logger.debug(f"ScheduledAppointment cross-source lookup skipped: {e}")

    # Source 2: CalendarEvent
    try:
        import main
        CalendarEvent = main.CalendarEvent
        cal_query = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.status != "cancelled",
            CalendarEvent.start_time >= start_dt,
            CalendarEvent.start_time <= end_dt,
        )
        if org_id:
            cal_query = cal_query.filter(CalendarEvent.organization_id == org_id)
        for e in cal_query.all():
            if e.start_time and e.end_time:
                conflicts.append((e.start_time, e.end_time))
    except Exception as e:
        logger.debug(f"CalendarEvent cross-source lookup skipped: {e}")

    # Source 3: CRMCalendarEvent (Salesforce-synced)
    try:
        from models.calendar_sync_models import CRMCalendarEvent
        crm_query = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.status != "canceled",
            CRMCalendarEvent.start_at >= start_dt,
            CRMCalendarEvent.start_at <= end_dt,
        )
        if org_id:
            crm_query = crm_query.filter(CRMCalendarEvent.organization_id == org_id)
        for e in crm_query.all():
            if e.start_at and e.end_at:
                conflicts.append((e.start_at, e.end_at))
    except Exception as e:
        logger.debug(f"CRMCalendarEvent cross-source lookup skipped: {e}")

    return conflicts


def _ensure_lead_for_ai_booking(
    db: Session, org_id: int, assigned_user_id: int,
    name: str, email: Optional[str], phone: Optional[str],
) -> Optional[int]:
    """Find or create a lead for an AI-booked appointment."""
    try:
        from database.models.lead_loan import Lead
    except ImportError:
        return None

    # Try to find existing lead by phone or email
    if phone:
        cleaned = ''.join(filter(str.isdigit, phone))
        if len(cleaned) >= 10:
            cleaned = cleaned[-10:]
        existing = db.query(Lead).filter(
            Lead.phone.ilike(f"%{cleaned}"),
            Lead.organization_id == org_id,
        ).first()
        if existing:
            existing.last_contact = datetime.now(timezone.utc)
            return existing.id

    if email:
        existing = db.query(Lead).filter(
            Lead.email == email,
            Lead.organization_id == org_id,
        ).first()
        if existing:
            existing.last_contact = datetime.now(timezone.utc)
            return existing.id

    # Create new lead
    name_parts = (name or "").strip().split(None, 1)
    first_name = name_parts[0] if name_parts else "Unknown"
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    new_lead = Lead(
        organization_id=org_id,
        name=name or "AI Call Lead",
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        stage="New",
        source="AI Phone Call",
        owner_id=assigned_user_id,
        last_contact=datetime.now(timezone.utc),
        lead_received_date=datetime.now(timezone.utc),
    )
    db.add(new_lead)
    db.flush()

    logger.info(f"Created new lead {new_lead.id} from AI booking")
    return new_lead.id


def _log_ai_booking_activity(
    db: Session, org_id: int, user_id: int,
    lead_id: Optional[int], title: str,
    start_time: datetime, attendee_name: str,
):
    """Log appointment activity to CRM."""
    try:
        from database.models.communication import Activity
        from database.enums import ActivityType

        content = (
            f"AI Receptionist booked appointment: {title} "
            f"for {start_time.strftime('%B %-d at %-I:%M %p')}"
        )

        activity = Activity(
            organization_id=org_id,
            type=ActivityType.MEETING,
            content=content[:2000],
            lead_id=lead_id,
            user_id=user_id,
        )
        db.add(activity)
    except Exception as e:
        logger.warning(f"Failed to log booking activity: {e}")


def _get_user_display_name(db: Session, user_id: int) -> str:
    """Get display name for a user."""
    try:
        from database.models import User
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return f"{user.first_name or ''} {user.last_name or ''}".strip() or "Loan Officer"
    except Exception as e:
        logger.debug(f"User display name lookup failed for user {user_id}: {e}")
    return "Loan Officer"


def _send_booking_confirmations(
    db: Session,
    appointment_data: Dict[str, Any],
    attendee_email: Optional[str],
    attendee_phone: Optional[str],
):
    """Send confirmation email and SMS for a booking."""
    try:
        from scheduler_email_service import (
            send_appointment_confirmation_email,
            send_appointment_confirmation_sms,
            send_team_member_notification_email,
        )

        start_time = datetime.fromisoformat(appointment_data["scheduled_start"])

        # Email confirmation to attendee
        if attendee_email:
            try:
                send_appointment_confirmation_email(
                    attendee_email=attendee_email,
                    attendee_name=appointment_data.get("attendee_name", ""),
                    appointment_title=appointment_data.get("title", "Appointment"),
                    appointment_date=appointment_data.get("display_date", ""),
                    appointment_time=appointment_data.get("display_time", ""),
                    duration=f"{appointment_data.get('duration_minutes', 30)} minutes",
                    meeting_mode="Phone Call",
                    team_member_name=appointment_data.get("assigned_to"),
                )
                logger.info(f"Confirmation email sent to {attendee_email}")
            except Exception as e:
                logger.warning(f"Failed to send confirmation email: {e}")

        # SMS confirmation to attendee
        if attendee_phone:
            try:
                send_appointment_confirmation_sms(
                    attendee_phone=attendee_phone,
                    attendee_name=appointment_data.get("attendee_name", ""),
                    appointment_date=appointment_data.get("display_date", ""),
                    appointment_time=appointment_data.get("display_time", ""),
                    team_member_name=appointment_data.get("assigned_to"),
                )
                logger.info(f"Confirmation SMS sent to attendee")
            except Exception as e:
                logger.warning(f"Failed to send confirmation SMS: {e}")

        # Notify team member
        try:
            send_team_member_notification_email(
                team_member_email=None,  # Will be looked up from user
                team_member_name=appointment_data.get("assigned_to", ""),
                attendee_name=appointment_data.get("attendee_name", ""),
                appointment_date=appointment_data.get("display_date", ""),
                appointment_time=appointment_data.get("display_time", ""),
                duration=f"{appointment_data.get('duration_minutes', 30)} minutes",
                meeting_mode="Phone Call",
                attendee_email=attendee_email,
                attendee_phone=attendee_phone,
            )
        except Exception as e:
            logger.warning(f"Failed to send team notification: {e}")

    except ImportError:
        logger.warning("Email service not available for booking confirmations")
    except Exception as e:
        logger.error(f"Error sending booking confirmations: {e}")


def get_default_org_id(db: Session) -> Optional[int]:
    """Get a default organization ID for single-tenant setups."""
    try:
        from database.models import Organization
        org = db.query(Organization).filter(
            Organization.is_active == True
        ).first()
        return org.id if org else 1
    except Exception as e:
        logger.debug(f"Organization lookup failed for default org: {e}")
        return 1


def get_default_user_id(db: Session, org_id: int) -> Optional[int]:
    """Get a default user (LO) for booking assignment."""
    try:
        models = _get_models()
        SchedulerConfig = models.get('SchedulerConfig')
        if SchedulerConfig:
            config = db.query(SchedulerConfig).filter(
                SchedulerConfig.organization_id == org_id,
                SchedulerConfig.is_active == True,
                SchedulerConfig.user_id.isnot(None),
            ).first()
            if config:
                return config.user_id
    except Exception as e:
        logger.debug(f"SchedulerConfig lookup failed for default user: {e}")

    try:
        from database.models import User
        user = db.query(User).filter(
            User.organization_id == org_id,
            User.is_active == True,
        ).first()
        return user.id if user else 1
    except Exception as e:
        logger.debug(f"User lookup failed for default user in org {org_id}: {e}")
        return 1
