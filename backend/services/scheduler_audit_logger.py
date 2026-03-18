"""
Scheduler Audit Logger

Domain-specific structured logging for the appointment scheduling system.
Writes audit events as JSON to both the main application log and a
separate audit log file (logs/scheduler_audit.log) for compliance and
debugging.

All entries include an event_type field for easy filtering in log
aggregation systems (DataDog, Splunk, CloudWatch).

Enterprise compliance fields on every entry:
- event_type: machine-readable event name
- appointment_id, loan_id, lead_id: entity linkage
- organization_id: tenant isolation
- user_id: who performed the action
- timestamp: server UTC (via StructuredFormatter)
- ip_address: client IP
- user_agent: client User-Agent header
- request_id: correlation ID for the HTTP request

Usage:
    from services.scheduler_audit_logger import scheduler_audit

    scheduler_audit.log_appointment_created(appointment, user, request=request)
    scheduler_audit.log_appointment_updated(
        appointment, changes={"title": {"old": "A", "new": "B"}},
        user=user, request=request,
    )
    scheduler_audit.log_appointment_cancelled(
        appointment, user, reason="schedule conflict", request=request,
        within_policy=True,
    )
    scheduler_audit.log_appointment_rescheduled(
        appointment, old_time, new_time, user, request=request,
    )
    scheduler_audit.log_no_show(appointment, detected_by="system", request=request)
    scheduler_audit.log_reminder_sent(appointment, channel="email", request=request)
    scheduler_audit.log_booking_page_access(booking_link_id=42, visitor_ip="1.2.3.4")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from logging_config import StructuredFormatter, get_request_id

logger = logging.getLogger("perennia.scheduler.audit")


# ---------------------------------------------------------------------------
# Audit file handler setup
# ---------------------------------------------------------------------------

import threading

_audit_handler_lock = threading.Lock()
_audit_handler_installed = False


def _ensure_audit_handler() -> None:
    """
    Install a dedicated file handler on the scheduler audit logger.

    Writes to SCHEDULER_AUDIT_LOG env var or logs/scheduler_audit.log
    (if the logs/ directory exists). If neither is available, audit
    entries still flow through the main log via the parent logger.

    Safe to call multiple times; installs at most once. Thread-safe.
    """
    global _audit_handler_installed
    if _audit_handler_installed:
        return
    with _audit_handler_lock:
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
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    booking_link_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build a consistent extra dict for audit log entries.

    Every audit entry includes the following when available:
    - event_type, appointment_id, user_id, org_id
    - loan_id, lead_id (entity linkage for enterprise compliance)
    - ip_address, user_agent (client provenance)
    - request_id (correlation)
    """
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
    if loan_id is not None:
        extra["loan_id"] = loan_id
    if lead_id is not None:
        extra["lead_id"] = lead_id
    if booking_link_id is not None:
        extra["booking_link_id"] = booking_link_id
    if ip_address is not None:
        extra["ip_address"] = ip_address
    if user_agent is not None:
        extra["user_agent"] = user_agent[:255]
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


def _extract_request_info(request: Any) -> Dict[str, Optional[str]]:
    """Extract ip_address and user_agent from a FastAPI Request object.

    Returns a dict with 'ip_address' and 'user_agent' keys (may be None).
    Safe to call with None request.
    """
    if request is None:
        return {"ip_address": None, "user_agent": None}
    ip = None
    ua = None
    try:
        if hasattr(request, "client") and request.client:
            ip = request.client.host
    except Exception:
        pass
    try:
        if hasattr(request, "headers"):
            ua = str(request.headers.get("user-agent", ""))[:255] or None
    except Exception:
        pass
    return {"ip_address": ip, "user_agent": ua}


def _get_user_name(user: Any) -> Optional[str]:
    """Extract display name from a User ORM instance or dict."""
    if user is None:
        return None
    first = _safe_attr(user, "first_name", "")
    last = _safe_attr(user, "last_name", "")
    name = f"{first} {last}".strip() if (first or last) else None
    return name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SchedulerAuditLogger:
    """
    Structured audit logger for scheduler / appointment events.

    Each method logs a JSON-formatted audit entry with a consistent
    event_type field. Entries go to both the main application log
    (via the root logger hierarchy) and the dedicated audit log file.

    All methods accept an optional ``request`` parameter (FastAPI Request)
    from which ip_address and user_agent are extracted automatically.
    """

    def __init__(self) -> None:
        _ensure_audit_handler()
        # Ensure this logger propagates to root so entries appear
        # in the main application log as well
        logger.propagate = True
        logger.setLevel(logging.DEBUG)

    # ------------------------------------------------------------------
    # appointment_created
    # ------------------------------------------------------------------

    def log_appointment_created(
        self,
        appointment: Any,
        user: Any,
        *,
        request: Any = None,
    ) -> None:
        """
        Log that a new appointment was created.

        Args:
            appointment: Appointment ORM instance or dict with id,
                         scheduled_start, scheduled_end, appointment_type,
                         organization_id, assigned_user_id, lead_id, loan_id
            user: User ORM instance or dict with id, first_name, last_name
            request: FastAPI Request (for ip_address, user_agent)
        """
        req_info = _extract_request_info(request)

        extra = _build_extra(
            "appointment_created",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=_safe_attr(user, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            scheduled_start=_format_dt(_safe_attr(appointment, "scheduled_start")),
            scheduled_end=_format_dt(_safe_attr(appointment, "scheduled_end")),
            appointment_type=_safe_attr(appointment, "appointment_type"),
            meeting_type=(
                _safe_attr(appointment, "meeting_type").value
                if hasattr(_safe_attr(appointment, "meeting_type"), "value")
                else _safe_attr(appointment, "meeting_type")
            ),
            meeting_mode=(
                _safe_attr(appointment, "meeting_mode").value
                if hasattr(_safe_attr(appointment, "meeting_mode"), "value")
                else _safe_attr(appointment, "meeting_mode")
            ),
            duration_minutes=_safe_attr(appointment, "duration_minutes"),
            assigned_user_id=_safe_attr(appointment, "assigned_user_id"),
            created_by=_get_user_name(user),
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
            booking_link_id=_safe_attr(appointment, "booking_link_id"),
            booked_by_ai=_safe_attr(appointment, "booked_by_ai"),
        )

        logger.info(
            "Appointment created",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # appointment_updated
    # ------------------------------------------------------------------

    def log_appointment_updated(
        self,
        appointment: Any,
        user: Any,
        *,
        changes: Optional[Dict[str, Dict[str, Any]]] = None,
        request: Any = None,
    ) -> None:
        """
        Log that an appointment was updated (field-level changes).

        Args:
            appointment: Appointment ORM instance or dict
            user: User who performed the update
            changes: Dict of {field_name: {"old": ..., "new": ...}} showing
                     what changed. Only changed fields should be included.
            request: FastAPI Request (for ip_address, user_agent)
        """
        req_info = _extract_request_info(request)

        # Summarize changed fields for the log message
        changed_fields = list((changes or {}).keys())

        extra = _build_extra(
            "appointment_updated",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=_safe_attr(user, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            updated_by=_get_user_name(user),
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
            changed_fields=changed_fields,
            changes=changes or {},
        )

        logger.info(
            f"Appointment updated: {', '.join(changed_fields) if changed_fields else 'no field changes'}",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # appointment_cancelled
    # ------------------------------------------------------------------

    def log_appointment_cancelled(
        self,
        appointment: Any,
        user: Any,
        reason: Optional[str] = None,
        *,
        request: Any = None,
        within_policy: Optional[bool] = None,
        is_late_cancellation: Optional[bool] = None,
        cancellation_fee_applied: Optional[bool] = None,
    ) -> None:
        """
        Log that an appointment was cancelled.

        Args:
            appointment: Appointment ORM instance or dict
            user: User who performed the cancellation
            reason: Free-text cancellation reason
            request: FastAPI Request (for ip_address, user_agent)
            within_policy: Whether the cancellation was within the org's
                           cancellation policy window
            is_late_cancellation: Whether this is a late cancellation
            cancellation_fee_applied: Whether a cancellation fee was charged
        """
        req_info = _extract_request_info(request)

        extra = _build_extra(
            "appointment_cancelled",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=_safe_attr(user, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            scheduled_start=_format_dt(_safe_attr(appointment, "scheduled_start")),
            cancelled_by=_get_user_name(user),
            cancellation_reason=reason,
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
            within_policy=within_policy,
            is_late_cancellation=is_late_cancellation,
            cancellation_fee_applied=cancellation_fee_applied,
        )

        logger.info(
            "Appointment cancelled",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # appointment_rescheduled
    # ------------------------------------------------------------------

    def log_appointment_rescheduled(
        self,
        appointment: Any,
        old_time: Any,
        new_time: Any,
        user: Any,
        *,
        request: Any = None,
        old_end: Any = None,
        new_end: Any = None,
        reschedule_count: Optional[int] = None,
        initiated_by: Optional[str] = None,
    ) -> None:
        """
        Log that an appointment was rescheduled.

        Args:
            appointment: Appointment ORM instance or dict
            old_time: Previous scheduled_start (datetime or ISO string)
            new_time: New scheduled_start (datetime or ISO string)
            user: User who performed the reschedule (or dict with id)
            request: FastAPI Request (for ip_address, user_agent)
            old_end: Previous scheduled_end
            new_end: New scheduled_end
            reschedule_count: Total reschedule count after this operation
            initiated_by: "lo", "borrower", "admin", or "system"
        """
        req_info = _extract_request_info(request)

        extra = _build_extra(
            "appointment_rescheduled",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=_safe_attr(user, "id") if user else None,
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            old_scheduled_start=_format_dt(old_time),
            new_scheduled_start=_format_dt(new_time),
            old_scheduled_end=_format_dt(old_end),
            new_scheduled_end=_format_dt(new_end),
            reschedule_count=reschedule_count,
            initiated_by=initiated_by,
            rescheduled_by=_get_user_name(user) if user else initiated_by,
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
        )

        logger.info(
            "Appointment rescheduled",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # booking_page_access
    # ------------------------------------------------------------------

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
            ip_address=visitor_ip,
            user_agent=(user_agent or "")[:200] if user_agent else None,
            referrer=(referrer or "")[:500] if referrer else None,
            booking_slug=booking_slug,
        )

        logger.info(
            "Booking page accessed",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # reminder_sent
    # ------------------------------------------------------------------

    def log_reminder_sent(
        self,
        appointment: Any,
        channel: str,
        *,
        recipient: Optional[str] = None,
        reminder_type: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        request: Any = None,
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
            request: FastAPI Request (for ip_address, user_agent)
        """
        req_info = _extract_request_info(request)

        extra = _build_extra(
            "reminder_sent",
            appointment_id=_safe_attr(appointment, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            channel=channel,
            recipient=recipient,
            reminder_type=reminder_type,
            success=success,
            error=error,
            attendee_name=_safe_attr(appointment, "attendee_name"),
        )

        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            f"Reminder {'sent' if success else 'failed'} via {channel}",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # no_show
    # ------------------------------------------------------------------

    def log_no_show(
        self,
        appointment: Any,
        *,
        detected_by: str = "system",
        user: Any = None,
        request: Any = None,
    ) -> None:
        """
        Log that an appointment was marked as a no-show.

        Args:
            appointment: Appointment ORM instance or dict
            detected_by: "system" (auto-detection) or user name
            user: User who marked the no-show (if manual)
            request: FastAPI Request (for ip_address, user_agent)
        """
        req_info = _extract_request_info(request)

        extra = _build_extra(
            "appointment_no_show",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=_safe_attr(user, "id") if user else None,
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            scheduled_start=_format_dt(_safe_attr(appointment, "scheduled_start")),
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
            detected_by=detected_by,
            marked_by=_get_user_name(user) if user else detected_by,
        )

        logger.warning(
            "Appointment no-show",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # reschedule_link_generated
    # ------------------------------------------------------------------

    def log_reschedule_link_generated(
        self,
        appointment: Any,
        user: Any,
        *,
        request: Any = None,
    ) -> None:
        """
        Log that a borrower reschedule link was generated.

        Args:
            appointment: Appointment ORM instance or dict
            user: User who generated the link
            request: FastAPI Request (for ip_address, user_agent)
        """
        req_info = _extract_request_info(request)

        extra = _build_extra(
            "reschedule_link_generated",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=_safe_attr(user, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            generated_by=_get_user_name(user),
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
        )

        logger.info(
            "Reschedule link generated",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # reschedule_initiated
    # ------------------------------------------------------------------

    def log_reschedule_initiated(
        self,
        appointment: Any,
        user: Any,
        *,
        reason: Optional[str] = None,
        reschedule_count: Optional[int] = None,
        request: Any = None,
    ) -> None:
        """
        Log that a reschedule was initiated (before new time is chosen).

        Args:
            appointment: Appointment ORM instance or dict
            user: User who initiated the reschedule
            reason: Reason for the reschedule
            reschedule_count: Total reschedule count after initiation
            request: FastAPI Request (for ip_address, user_agent)
        """
        req_info = _extract_request_info(request)

        extra = _build_extra(
            "reschedule_initiated",
            appointment_id=_safe_attr(appointment, "id"),
            user_id=_safe_attr(user, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            initiated_by=_get_user_name(user),
            reason=reason,
            reschedule_count=reschedule_count,
            scheduled_start=_format_dt(_safe_attr(appointment, "scheduled_start")),
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
        )

        logger.info(
            "Reschedule initiated",
            extra=extra,
        )

    # ------------------------------------------------------------------
    # borrower_reschedule_confirmed
    # ------------------------------------------------------------------

    def log_borrower_reschedule_confirmed(
        self,
        appointment: Any,
        old_start: Any,
        new_start: Any,
        *,
        old_end: Any = None,
        new_end: Any = None,
        request: Any = None,
    ) -> None:
        """
        Log that a borrower confirmed a reschedule via self-service link.

        Args:
            appointment: Appointment ORM instance or dict (post-reschedule)
            old_start: Previous scheduled_start
            new_start: New scheduled_start
            old_end: Previous scheduled_end
            new_end: New scheduled_end
            request: FastAPI Request (for ip_address, user_agent)
        """
        req_info = _extract_request_info(request)

        extra = _build_extra(
            "borrower_reschedule_confirmed",
            appointment_id=_safe_attr(appointment, "id"),
            org_id=_safe_attr(appointment, "organization_id"),
            loan_id=_safe_attr(appointment, "loan_id"),
            lead_id=_safe_attr(appointment, "lead_id"),
            ip_address=req_info["ip_address"],
            user_agent=req_info["user_agent"],
            old_scheduled_start=_format_dt(old_start),
            new_scheduled_start=_format_dt(new_start),
            old_scheduled_end=_format_dt(old_end),
            new_scheduled_end=_format_dt(new_end),
            reschedule_count=_safe_attr(appointment, "reschedule_count"),
            attendee_name=_safe_attr(appointment, "attendee_name"),
            attendee_email=_safe_attr(appointment, "attendee_email"),
            confirmed_by="borrower",
        )

        logger.info(
            "Borrower confirmed reschedule via self-service link",
            extra=extra,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

scheduler_audit = SchedulerAuditLogger()
