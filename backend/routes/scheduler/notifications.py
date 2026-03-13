"""
Scheduler Notification Routes - Calendar notification feed for appointment events.

Generates notifications from recent appointment activity (bookings, cancellations,
reschedule requests) and upcoming appointment reminders.

Endpoints:
  - GET  /notifications            List notifications for current user
  - PUT  /notifications/{id}/read  Mark single notification as read
  - PUT  /notifications/read-all   Mark all notifications as read
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import logging

from routes.scheduler._helpers import get_current_user, get_models, _get_org_id
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# NOTIFICATION GENERATION — derives notifications from appointment events
# ============================================================================

def _generate_notifications_for_user(db: Session, user_id: int, org_id: int,
                                      limit: int = 50, since_hours: int = 72):
    """
    Generate a notification feed by querying recent appointment events.

    Sources:
      1. Recent bookings (created in the last N hours, assigned to this user)
      2. Cancellations (status changed to cancelled in the last N hours)
      3. Upcoming reminders (appointments starting within the next 60 minutes)
      4. Reschedule-related updates (appointments modified after creation)

    Each notification is assigned a deterministic ID derived from
    (source_type + appointment_id + relevant_timestamp) so the frontend
    can persist read state in localStorage without needing a server-side
    notification table.
    """
    models = get_models()
    Appointment = models.get("Appointment")
    if not Appointment:
        return []

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=since_hours)
    notifications = []

    # ------------------------------------------------------------------
    # 1. New bookings (created recently, assigned to this user)
    # ------------------------------------------------------------------
    try:
        recent_bookings = (
            db.query(Appointment)
            .filter(
                Appointment.assigned_user_id == user_id,
                Appointment.organization_id == org_id,
                Appointment.created_at >= cutoff,
                Appointment.status.notin_(["cancelled", "CANCELLED"]),
            )
            .order_by(desc(Appointment.created_at))
            .limit(limit)
            .all()
        )

        for appt in recent_bookings:
            notif_id = _stable_id("booking", appt.id, appt.created_at)
            attendee = getattr(appt, "attendee_name", None) or "Someone"
            title_text = getattr(appt, "title", None) or "Appointment"
            start = getattr(appt, "scheduled_start", None)
            start_str = _format_datetime(start) if start else ""

            notifications.append({
                "id": notif_id,
                "type": "booking",
                "appointment_id": appt.id,
                "title": "New booking",
                "description": f"{attendee} booked \"{title_text}\" for {start_str}" if start_str else f"{attendee} booked \"{title_text}\"",
                "created_at": (appt.created_at or now).isoformat() + "Z",
            })
    except Exception as e:
        logger.warning(f"Error generating booking notifications: {e}")

    # ------------------------------------------------------------------
    # 2. Cancellations
    # ------------------------------------------------------------------
    try:
        cancellations = (
            db.query(Appointment)
            .filter(
                Appointment.assigned_user_id == user_id,
                Appointment.organization_id == org_id,
                Appointment.status.in_(["cancelled", "CANCELLED"]),
                Appointment.updated_at >= cutoff,
            )
            .order_by(desc(Appointment.updated_at))
            .limit(limit)
            .all()
        )

        for appt in cancellations:
            notif_id = _stable_id("cancellation", appt.id, appt.updated_at)
            attendee = getattr(appt, "attendee_name", None) or "Someone"
            title_text = getattr(appt, "title", None) or "Appointment"

            notifications.append({
                "id": notif_id,
                "type": "cancellation",
                "appointment_id": appt.id,
                "title": "Cancellation",
                "description": f"{attendee} cancelled \"{title_text}\"",
                "created_at": (appt.updated_at or now).isoformat() + "Z",
            })
    except Exception as e:
        logger.warning(f"Error generating cancellation notifications: {e}")

    # ------------------------------------------------------------------
    # 3. Upcoming reminders (appointments starting within 60 min)
    # ------------------------------------------------------------------
    try:
        reminder_window = now + timedelta(minutes=60)
        upcoming = (
            db.query(Appointment)
            .filter(
                Appointment.assigned_user_id == user_id,
                Appointment.organization_id == org_id,
                Appointment.status.notin_(["cancelled", "CANCELLED"]),
                Appointment.scheduled_start >= now,
                Appointment.scheduled_start <= reminder_window,
            )
            .order_by(Appointment.scheduled_start)
            .limit(10)
            .all()
        )

        for appt in upcoming:
            notif_id = _stable_id("reminder", appt.id, appt.scheduled_start)
            title_text = getattr(appt, "title", None) or "Appointment"
            start = getattr(appt, "scheduled_start", None)
            minutes_until = int((start - now).total_seconds() / 60) if start else 0
            attendee = getattr(appt, "attendee_name", None) or ""
            desc_parts = [f"\"{title_text}\""]
            if attendee:
                desc_parts.append(f"with {attendee}")
            desc_parts.append(f"in {minutes_until} minutes")

            notifications.append({
                "id": notif_id,
                "type": "reminder",
                "appointment_id": appt.id,
                "title": "Upcoming appointment",
                "description": " ".join(desc_parts),
                "created_at": now.isoformat() + "Z",
            })
    except Exception as e:
        logger.warning(f"Error generating reminder notifications: {e}")

    # ------------------------------------------------------------------
    # 4. Reschedule requests (appointments updated after initial creation)
    # ------------------------------------------------------------------
    try:
        reschedules = (
            db.query(Appointment)
            .filter(
                Appointment.assigned_user_id == user_id,
                Appointment.organization_id == org_id,
                Appointment.status.notin_(["cancelled", "CANCELLED"]),
                Appointment.updated_at >= cutoff,
                Appointment.updated_at > Appointment.created_at + timedelta(minutes=1),
            )
            .order_by(desc(Appointment.updated_at))
            .limit(limit)
            .all()
        )

        for appt in reschedules:
            notif_id = _stable_id("reschedule", appt.id, appt.updated_at)
            attendee = getattr(appt, "attendee_name", None) or "Someone"
            title_text = getattr(appt, "title", None) or "Appointment"
            start = getattr(appt, "scheduled_start", None)
            start_str = _format_datetime(start) if start else ""

            notifications.append({
                "id": notif_id,
                "type": "reschedule",
                "appointment_id": appt.id,
                "title": "Reschedule request",
                "description": f"{attendee} rescheduled \"{title_text}\" to {start_str}" if start_str else f"{attendee} rescheduled \"{title_text}\"",
                "created_at": (appt.updated_at or now).isoformat() + "Z",
            })
    except Exception as e:
        logger.warning(f"Error generating reschedule notifications: {e}")

    # ------------------------------------------------------------------
    # Deduplicate by ID (a single appointment may appear in multiple categories)
    # and sort by created_at descending
    # ------------------------------------------------------------------
    seen = set()
    unique = []
    for n in notifications:
        if n["id"] not in seen:
            seen.add(n["id"])
            unique.append(n)

    unique.sort(key=lambda x: x["created_at"], reverse=True)
    return unique[:limit]


# ============================================================================
# HELPERS
# ============================================================================

def _stable_id(notif_type: str, appointment_id: int, timestamp) -> str:
    """
    Generate a deterministic notification ID from type + appointment_id + timestamp.
    This allows the frontend to persist read state in localStorage across page reloads.
    """
    ts_str = ""
    if timestamp:
        if hasattr(timestamp, 'isoformat'):
            ts_str = timestamp.isoformat()
        else:
            ts_str = str(timestamp)
    raw = f"{notif_type}:{appointment_id}:{ts_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _format_datetime(dt) -> str:
    """Format a datetime for notification description text."""
    if dt is None:
        return ""
    try:
        return dt.strftime("%b %d at %I:%M %p")
    except Exception:
        return str(dt)


# ============================================================================
# ROUTES
# ============================================================================

@router.get("/notifications")
async def get_notifications(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Max notifications to return"),
    since_hours: int = Query(72, ge=1, le=720, description="Look back window in hours"),
    db: Session = Depends(get_db),
):
    """Get notifications for the authenticated user.

    Notifications are derived from recent appointment activity (bookings,
    cancellations, reschedules) and upcoming appointment reminders.
    Each notification has a deterministic ID for client-side read-state tracking.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    notifications = _generate_notifications_for_user(
        db, user_id, org_id, limit=limit, since_hours=since_hours,
    )

    return {
        "notifications": notifications,
        "total": len(notifications),
    }


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Mark a single notification as read.

    Since notifications are derived (not stored in a dedicated table), this
    endpoint is a no-op acknowledgement. The frontend persists read state
    in localStorage. This endpoint exists for future server-side persistence.
    """
    user = await get_current_user(request, db)
    _get_org_id(user)  # Validate org context

    return {
        "success": True,
        "notification_id": notification_id,
        "status": "read",
    }


@router.put("/notifications/read-all")
async def mark_all_notifications_read(
    request: Request,
    db: Session = Depends(get_db),
):
    """Mark all notifications as read.

    Like the single-read endpoint, this is currently a no-op acknowledgement.
    Read state is tracked client-side in localStorage.
    """
    user = await get_current_user(request, db)
    _get_org_id(user)  # Validate org context

    return {
        "success": True,
        "status": "all_read",
    }
