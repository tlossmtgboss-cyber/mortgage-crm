"""
Scheduler Audit Logger

Domain-specific structured logging for the appointment scheduling system.
Writes audit events as JSON to both the main application log and a
separate audit log file (logs/scheduler_audit.log) for compliance and
debugging.

All entries include an event_type field for easy filtering in log
aggregation systems (DataDog, Splunk, CloudWatch).

Usage:
    from services.scheduler_audit_logger import scheduler_audit

    scheduler_audit.log_appointment_created(appointment, user)
    scheduler_audit.log_appointment_cancelled(appointment, user, reason="no show")
    scheduler_audit.log_appointment_rescheduled(
        appointment, old_time, new_time, user
    )
    scheduler_audit.log_booking_page_access(booking_link_id=42, visitor_ip="1.2.3.4")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from logging_config import StructuredFormatter, get_request_id

logger = logging.getLogger("perennia.scheduler.audit")


# ---------------------------------------------------------------------------
# Audit file handler setup
# ---------------------------------------------------------------------------

_audit_handler_installed = False


def _ensure_audit_handler() -> None:
    """
    Install a dedicated file handler on the scheduler audit logger.

    Writes to SCHEDULER_AUDIT_LOG env var or logs/scheduler_audit.log
    (if the logs/ directory exists). If neither is available, audit
    entries still flow through the main log via the parent logger.

    Safe to call multiple times; installs at most once.
    """
    global _audit_handler_installed
    if _audit_handler_installed:
        return
    _audit_handler_installed = True

    audit_log_path = os.getenv("SCHEDULER_AUDIT_LOG")
    if not audit_log_path:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs",
        )
        if os.path.isdir(log_dir):
            audit_log_path = os.path.join(log_dir, "scheduler_audit.log")

    if not audit_log_path:
        return

    try:
        log_dir = os.path.dirname(audit_log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Check if handler already exists
        for h in logger.handlers:
            if isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(audit_log_path):
                return

        file_handler = logging.FileHandler(audit_log_path, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
    except OSError:
        logging.getLogger(__name__).warning(
            f"Could not create scheduler audit log at {audit_log_path}"
        )


# ---------------------------------------------------------------------------
# Helper to build consistent audit entries
# ---------------------------------------------------------------------------

def _build_extra(
    event_type: str,
    *,
    appointment_id: Optional[int] = None,
    user_id: Optional[int] = None,
    org_id: Optional[int] = None,
    booking_link_id: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build a consistent extra dict for audit log entries."""
    extra: Dict[str, Any] = {
        "event_type": event_type,
        "audit": True,
    }
    request_id = get_request_id()
    if request_id:
        extra["request_id"] = request_id
    if appointment_id is not None:
        extra["appointment_id"] = appointment_id
    if user_id is not None:
        extra["user_id"] = user_id
    if org_id is not None:
        extra["org_id"] = org_id
    if booking_link_id is not None:
        extra["booking_link_id"] = booking_link_id
    extra.update(kwargs)
    return extra


def _safe_attr(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get an attribute from an object that may be a dict or ORM model."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _format_dt(dt: Any) -> Optional[str]:
    """Format a datetime to ISO 8601, handling None and naive datetimes."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return str(dt)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SchedulerAuditLogger:
    """
    Structured audit logger for scheduler / appointment events.

    Each method logs a JSON-formatted audit entry with a consistent
    event_type field. Entries go to both the main application log
    (via the root logger hierarchy) and the dedicated audit log file.
    """

    def __init__(self) -> None:
        _ensure_audit_handler()
        # Ensure this logger propagates to root so entries appear
        # in the main application log as well
        logger.propagate = True
        logger.setLevel(logging.DEBUG)

    def log_appointment_created(
        self,
        appointment: Any,
        user: Any,
    ) -> None:
        """
        Log that a new appointment was created.

        Args:
            appointment: Appointment ORM instance or dict with id,
                         scheduled_start, scheduled_end, appointment_type,
                         organization_id, assigned_user_id
            user: User ORM instance or dict with id, first_name, last_name
        """
        user_id = _safe_attr(user, "id")
        user_name = None
        first = _safe_attr(user, "first_name", "")
        last = _safe_attr(user, "last_name", "")
        if first or last:
            user_name = f"{first} {last}".strip()

        extra = _build_extra(
            "appointment_created",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=user_id,
            org_id=_safe_attr(appointment, "organization_id"),
            scheduled_start=_format_dt(_safe_attr(appointment, "scheduled_start")),
            scheduled_end=_format_dt(_safe_attr(appointment, "scheduled_end")),
            appointment_type=_safe_attr(appointment, "appointment_type"),
            assigned_user_id=_safe_attr(appointment, "assigned_user_id"),
            created_by=user_name,
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
            booking_link_id=_safe_attr(appointment, "booking_link_id"),
        )

        logger.info(
            "Appointment created",
            extra=extra,
        )

    def log_appointment_cancelled(
        self,
        appointment: Any,
        user: Any,
        reason: Optional[str] = None,
    ) -> None:
        """
        Log that an appointment was cancelled.

        Args:
            appointment: Appointment ORM instance or dict
            user: User who performed the cancellation
            reason: Free-text cancellation reason
        """
        user_id = _safe_attr(user, "id")
        user_name = None
        first = _safe_attr(user, "first_name", "")
        last = _safe_attr(user, "last_name", "")
        if first or last:
            user_name = f"{first} {last}".strip()

        extra = _build_extra(
            "appointment_cancelled",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=user_id,
            org_id=_safe_attr(appointment, "organization_id"),
            scheduled_start=_format_dt(_safe_attr(appointment, "scheduled_start")),
            cancelled_by=user_name,
            cancellation_reason=reason,
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
        )

        logger.info(
            "Appointment cancelled",
            extra=extra,
        )

    def log_appointment_rescheduled(
        self,
        appointment: Any,
        old_time: Any,
        new_time: Any,
        user: Any,
    ) -> None:
        """
        Log that an appointment was rescheduled.

        Args:
            appointment: Appointment ORM instance or dict
            old_time: Previous scheduled_start (datetime or ISO string)
            new_time: New scheduled_start (datetime or ISO string)
            user: User who performed the reschedule
        """
        user_id = _safe_attr(user, "id")
        user_name = None
        first = _safe_attr(user, "first_name", "")
        last = _safe_attr(user, "last_name", "")
        if first or last:
            user_name = f"{first} {last}".strip()

        extra = _build_extra(
            "appointment_rescheduled",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=user_id,
            org_id=_safe_attr(appointment, "organization_id"),
            old_scheduled_start=_format_dt(old_time),
            new_scheduled_start=_format_dt(new_time),
            rescheduled_by=user_name,
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
        )

        logger.info(
            "Appointment rescheduled",
            extra=extra,
        )

    def log_booking_page_access(
        self,
        booking_link_id: int,
        visitor_ip: Optional[str] = None,
        *,
        user_agent: Optional[str] = None,
        referrer: Optional[str] = None,
        booking_slug: Optional[str] = None,
    ) -> None:
        """
        Log that a public booking page was accessed.

        Args:
            booking_link_id: ID of the BookingLink being viewed
            visitor_ip: IP address of the visitor
            user_agent: Visitor's User-Agent header (truncated)
            referrer: HTTP Referer header
            booking_slug: URL slug for the booking link
        """
        extra = _build_extra(
            "booking_page_access",
            booking_link_id=booking_link_id,
            visitor_ip=visitor_ip,
            user_agent=(user_agent or "")[:200] if user_agent else None,
            referrer=(referrer or "")[:500] if referrer else None,
            booking_slug=booking_slug,
        )

        logger.info(
            "Booking page accessed",
            extra=extra,
        )

    def log_reminder_sent(
        self,
        appointment: Any,
        channel: str,
        *,
        recipient: Optional[str] = None,
        reminder_type: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """
        Log that an appointment reminder was sent.

        Args:
            appointment: Appointment ORM instance or dict
            channel: "email", "sms", or "push"
            recipient: Masked recipient identifier
            reminder_type: "confirmation", "24h", "1h", etc.
            success: Whether send succeeded
            error: Error message if send failed
        """
        extra = _build_extra(
            "reminder_sent",
            appointment_id=_safe_attr(appointment, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            channel=channel,
            recipient=recipient,
            reminder_type=reminder_type,
            success=success,
            error=error,
        )

        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            f"Reminder {'sent' if success else 'failed'} via {channel}",
            extra=extra,
        )

    def log_no_show(
        self,
        appointment: Any,
        *,
        detected_by: str = "system",
    ) -> None:
        """
        Log that an appointment was marked as a no-show.

        Args:
            appointment: Appointment ORM instance or dict
            detected_by: "system" (auto-detection) or user name
        """
        extra = _build_extra(
            "appointment_no_show",
            appointment_id=_safe_attr(appointment, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            scheduled_start=_format_dt(_safe_attr(appointment, "scheduled_start")),
            attendee_name=_safe_attr(appointment, "attendee_name"),
            detected_by=detected_by,
        )

        logger.warning(
            "Appointment no-show",
            extra=extra,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

scheduler_audit = SchedulerAuditLogger()
