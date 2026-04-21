"""
SMS Scheduler Webhook — Handle inbound SMS replies for appointment management.

Processes Telnyx inbound SMS webhooks for appointment-related keywords:
- CONFIRM: Mark upcoming appointment as confirmed
- CANCEL: Cancel upcoming appointment
- RESCHEDULE: Reply with reschedule link

Webhook URL: POST /api/v1/scheduler/sms/webhook
Configure this URL in Telnyx messaging profile inbound settings.

Security: Validates Telnyx webhook signature when TELNYX_PUBLIC_KEY is set.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from middleware.webhook_verification import require_telnyx_webhook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Scheduler SMS Webhook"])


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

_get_db = None
_models = None


def set_dependencies(get_db_func, models_dict):
    """Set dependencies from parent module.

    Args:
        get_db_func: Database session dependency.
        models_dict: Dict of model classes (Appointment, AppointmentReminder,
                     AppointmentStatusHistory, etc.)
    """
    global _get_db, _models
    _get_db = get_db_func
    _models = models_dict


from db import get_db


# ============================================================================
# SMS REPLY HANDLER
# ============================================================================

@router.post("/api/v1/scheduler/sms/webhook")
async def handle_sms_reply(
    request: Request,
    raw_body: bytes = Depends(require_telnyx_webhook),
    db: Session = Depends(get_db),
):
    """Handle inbound SMS replies for appointment management.

    Telnyx sends inbound messages with this payload structure:
    {
      "data": {
        "event_type": "message.received",
        "payload": {
          "from": {"phone_number": "+1234567890"},
          "to": [{"phone_number": "+18438838956"}],
          "text": "CONFIRM",
          "id": "msg_xxx"
        }
      }
    }

    Recognized keywords (case-insensitive):
    - CONFIRM / YES / Y: Confirm the next upcoming appointment
    - CANCEL / NO / N: Cancel the next upcoming appointment
    - RESCHEDULE: Reply with instructions to reschedule
    - HELP: Reply with available commands
    - STOP: Acknowledge opt-out (Telnyx handles actual DNC)

    Signature verification is handled by the require_telnyx_webhook dependency.
    """
    import json

    # Parse payload from the already-verified raw body
    try:
        body = json.loads(raw_body)
    except Exception as e:
        logger.error(f"Failed to parse SMS webhook JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Extract fields from Telnyx payload
    data = body.get("data", {})
    payload = data.get("payload", {})

    # Some Telnyx events have event_type at data level
    event_type = data.get("event_type", "")

    # Only process inbound messages
    if event_type and event_type != "message.received":
        # Delivery status or other event — acknowledge silently
        return JSONResponse(content={"status": "ignored", "event_type": event_type})

    from_info = payload.get("from", {})
    from_number = from_info.get("phone_number", "") if isinstance(from_info, dict) else str(from_info)
    text = (payload.get("text", "") or "").strip()
    message_id = payload.get("id", "")

    if not from_number:
        logger.warning("SMS webhook: no from_number in payload")
        return JSONResponse(content={"status": "error", "detail": "No from number"})

    if not text:
        logger.debug(f"SMS webhook: empty text from {from_number}")
        return JSONResponse(content={"status": "ignored", "detail": "Empty message"})

    logger.info(f"SMS reply from {from_number}: '{text[:50]}' (msg_id: {message_id})")

    # --- Tenant isolation: resolve org_id from the receiving phone number ---
    # Telnyx "to" is a list of dicts: [{"phone_number": "+1..."}]
    to_list = payload.get("to", [])
    to_number = ""
    if isinstance(to_list, list) and to_list:
        first_to = to_list[0]
        to_number = first_to.get("phone_number", "") if isinstance(first_to, dict) else str(first_to)
    elif isinstance(to_list, str):
        to_number = to_list

    org_id = _resolve_org_from_receiving_number(db, to_number)
    if org_id:
        logger.info(f"SMS webhook: resolved org_id={org_id} from receiving number {to_number}")
    else:
        logger.warning(
            f"SMS webhook: could not resolve org_id from receiving number '{to_number}'. "
            "Appointment lookup will proceed without tenant filter."
        )

    # Normalize keyword
    keyword = text.upper().split()[0] if text.split() else ""

    # Route to handler
    if keyword in ("CONFIRM", "YES", "Y"):
        return await _handle_confirm(db, from_number, org_id)
    elif keyword in ("CANCEL", "NO", "N"):
        return await _handle_cancel(db, from_number, org_id)
    elif keyword == "RESCHEDULE":
        return await _handle_reschedule(db, from_number, org_id)
    elif keyword == "HELP":
        return await _handle_help(from_number)
    elif keyword == "STOP":
        # Telnyx handles STOP/opt-out at the platform level.
        # We just acknowledge.
        logger.info(f"STOP received from {from_number} — Telnyx handles opt-out")
        return JSONResponse(content={"status": "acknowledged", "action": "stop"})
    else:
        # Unrecognized — send help text
        return await _handle_help(from_number)


# ============================================================================
# ACTION HANDLERS
# ============================================================================

async def _handle_confirm(db: Session, phone: str, org_id: Optional[int] = None) -> JSONResponse:
    """Confirm the next upcoming appointment for this phone number."""
    from smart_scheduler_models import AppointmentStatus

    Appointment = _models.get("Appointment") if _models else None
    StatusHistory = _models.get("AppointmentStatusHistory") if _models else None

    if not Appointment:
        logger.error("Appointment model not available for SMS confirm")
        return JSONResponse(content={"status": "error", "detail": "Service unavailable"})

    appointment = _find_upcoming_appointment(db, Appointment, phone, org_id)
    if not appointment:
        await _send_reply(phone, "We couldn't find an upcoming appointment for this number. Please contact us directly.")
        return JSONResponse(content={"status": "not_found"})

    # Update status to confirmed
    old_status = appointment.status
    appointment.status = AppointmentStatus.CONFIRMED
    appointment.status_changed_at = datetime.now(timezone.utc)
    appointment.auto_confirmed = True

    # Record status history
    if StatusHistory:
        try:
            history = StatusHistory(
                organization_id=appointment.organization_id,
                appointment_id=appointment.id,
                previous_status=old_status.value if old_status else None,
                new_status=AppointmentStatus.CONFIRMED.value,
                change_source="sms_reply",
                notes=f"Confirmed via SMS reply from {phone}",
            )
            db.add(history)
        except Exception as e:
            logger.warning(f"Failed to record status history: {e}")

    # Update any pending reminder to acknowledged
    _acknowledge_reminders(db, appointment.id)

    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit SMS confirmation: {e}")
        db.rollback()
        return JSONResponse(content={"status": "error", "detail": "Database error"})

    await _send_reply(
        phone,
        f"Your appointment on {appointment.scheduled_start.strftime('%B %d at %I:%M %p')} "
        f"is confirmed. See you then!"
    )

    logger.info(f"Appointment {appointment.id} confirmed via SMS from ...{phone[-4:] if phone else '????'}")
    return JSONResponse(content={"status": "confirmed", "appointment_id": appointment.id})


async def _handle_cancel(db: Session, phone: str, org_id: Optional[int] = None) -> JSONResponse:
    """Cancel the next upcoming appointment for this phone number."""
    from smart_scheduler_models import AppointmentStatus

    Appointment = _models.get("Appointment") if _models else None
    StatusHistory = _models.get("AppointmentStatusHistory") if _models else None

    if not Appointment:
        logger.error("Appointment model not available for SMS cancel")
        return JSONResponse(content={"status": "error", "detail": "Service unavailable"})

    appointment = _find_upcoming_appointment(db, Appointment, phone, org_id)
    if not appointment:
        await _send_reply(phone, "We couldn't find an upcoming appointment for this number. Please contact us directly.")
        return JSONResponse(content={"status": "not_found"})

    # Update status to cancelled
    old_status = appointment.status
    appointment.status = AppointmentStatus.CANCELLED
    appointment.status_changed_at = datetime.now(timezone.utc)
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancellation_reason = "Cancelled via SMS reply"

    # Record status history
    if StatusHistory:
        try:
            history = StatusHistory(
                organization_id=appointment.organization_id,
                appointment_id=appointment.id,
                previous_status=old_status.value if old_status else None,
                new_status=AppointmentStatus.CANCELLED.value,
                change_source="sms_reply",
                notes=f"Cancelled via SMS reply from {phone}",
            )
            db.add(history)
        except Exception as e:
            logger.warning(f"Failed to record status history: {e}")

    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit SMS cancellation: {e}")
        db.rollback()
        return JSONResponse(content={"status": "error", "detail": "Database error"})

    await _send_reply(
        phone,
        f"Your appointment on {appointment.scheduled_start.strftime('%B %d at %I:%M %p')} "
        f"has been cancelled. Contact us if you'd like to reschedule."
    )

    logger.info(f"Appointment {appointment.id} cancelled via SMS from ...{phone[-4:] if phone else '????'}")
    return JSONResponse(content={"status": "cancelled", "appointment_id": appointment.id})


async def _handle_reschedule(db: Session, phone: str, org_id: Optional[int] = None) -> JSONResponse:
    """Reply with reschedule instructions."""
    from smart_scheduler_models import AppointmentStatus

    Appointment = _models.get("Appointment") if _models else None

    if not Appointment:
        await _send_reply(phone, "Please contact us directly to reschedule your appointment.")
        return JSONResponse(content={"status": "error", "detail": "Service unavailable"})

    appointment = _find_upcoming_appointment(db, Appointment, phone, org_id)
    if not appointment:
        await _send_reply(phone, "We couldn't find an upcoming appointment for this number. Please contact us directly.")
        return JSONResponse(content={"status": "not_found"})

    # Generate reschedule URL if possible
    try:
        from scheduler_email_service import generate_reschedule_url

        reschedule_url = generate_reschedule_url(appointment.id)
        if reschedule_url:
            await _send_reply(
                phone,
                f"To reschedule your appointment, please visit:\n{reschedule_url}\n"
                f"Or contact us directly for assistance."
            )
        else:
            await _send_reply(
                phone,
                "Please contact us directly to reschedule your appointment."
            )
    except (ImportError, Exception) as e:
        logger.debug(f"Reschedule URL generation failed: {e}")
        await _send_reply(
            phone,
            "Please contact us directly to reschedule your appointment."
        )

    return JSONResponse(content={"status": "reschedule_info_sent", "appointment_id": appointment.id})


async def _handle_help(phone: str) -> JSONResponse:
    """Send available commands to the user."""
    await _send_reply(
        phone,
        "Available commands:\n"
        "CONFIRM - Confirm your appointment\n"
        "CANCEL - Cancel your appointment\n"
        "RESCHEDULE - Get reschedule link\n"
        "STOP - Opt out of messages"
    )
    return JSONResponse(content={"status": "help_sent"})


# ============================================================================
# HELPERS
# ============================================================================

def _resolve_org_from_receiving_number(db: Session, to_number: str) -> Optional[int]:
    """Resolve organization_id from the receiving (to) phone number.

    Uses the verified_caller_ids table to map the Telnyx receiving
    number to an organization. Same pattern as telnyx_webhook_routes.py.
    """
    if not to_number:
        return None

    try:
        row = db.execute(
            sa_text("""
                SELECT organization_id FROM verified_caller_ids
                WHERE phone_number = :to_phone AND organization_id IS NOT NULL
                LIMIT 1
            """),
            {"to_phone": to_number},
        ).fetchone()
        if row:
            return row[0]
    except Exception as e:
        logger.warning(f"Failed to resolve org from receiving number {to_number}: {e}")

    return None


def _find_upcoming_appointment(db: Session, Appointment, phone: str, org_id: Optional[int] = None):
    """Find the next upcoming appointment for a phone number.

    Matches on attendee_phone, looking for active appointments
    scheduled in the future (within the next 30 days).
    Normalizes the phone number for matching.

    When org_id is provided, restricts the search to that organization
    for proper tenant isolation.
    """
    from smart_scheduler_models import AppointmentStatus

    now = datetime.now(timezone.utc)
    max_future = now + timedelta(days=30)

    # Normalize phone to last 10 digits for flexible matching
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) > 10:
        digits = digits[-10:]

    query = (
        db.query(Appointment)
        .filter(
            Appointment.attendee_phone.isnot(None),
            Appointment.status.in_([
                AppointmentStatus.BOOKED,
                AppointmentStatus.CONFIRMED,
                AppointmentStatus.REMINDED,
                AppointmentStatus.TENTATIVE,
            ]),
            Appointment.scheduled_start > now,
            Appointment.scheduled_start < max_future,
        )
        .filter(
            Appointment.attendee_phone.ilike(f"%{digits}")
        )
    )

    # Apply tenant isolation when org_id is known
    if org_id is not None:
        query = query.filter(Appointment.organization_id == org_id)

    appointment = query.order_by(Appointment.scheduled_start.asc()).first()

    if appointment:
        logger.debug(f"Found upcoming appointment {appointment.id} for phone ending {digits[-4:]}")

    return appointment


def _acknowledge_reminders(db: Session, appointment_id: int):
    """Mark pending reminders as acknowledged for this appointment."""
    try:
        from smart_scheduler_models import ReminderStatus

        AppointmentReminder = _models.get("AppointmentReminder") if _models else None
        if not AppointmentReminder:
            return

        pending = (
            db.query(AppointmentReminder)
            .filter(
                AppointmentReminder.appointment_id == appointment_id,
                AppointmentReminder.status.in_([
                    ReminderStatus.PENDING,
                    ReminderStatus.SENT,
                ]),
            )
            .all()
        )

        now = datetime.now(timezone.utc)
        for reminder in pending:
            reminder.status = ReminderStatus.ACKNOWLEDGED
            reminder.acknowledged_at = now
            reminder.response_action = "confirmed"

    except Exception as e:
        logger.warning(f"Failed to acknowledge reminders for appointment {appointment_id}: {e}")


async def _send_reply(to_number: str, message: str) -> bool:
    """Send an SMS reply via the SMSConfirmationService."""
    try:
        from services.sms_confirmation_service import get_sms_confirmation_service

        service = get_sms_confirmation_service()
        result = await service._send(to_number=to_number, message=message)
        return result.get("sent", False)
    except Exception as e:
        logger.error(f"Failed to send SMS reply to {to_number}: {e}")
        return False
