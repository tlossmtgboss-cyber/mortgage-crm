"""
Scheduler Data Compliance Routes
==================================

GDPR/CCPA data export and deletion, plus TCPA, DNC, and contact hours
compliance monitoring across all scheduling communication channels.

Enterprise mortgage lenders need data portability, right-to-erasure
capabilities, and real-time compliance dashboards for borrower
appointment data.

Endpoints (all admin-only, tenant-isolated):

  GDPR / CCPA:
  - GET    /data-export/{borrower_email}       Export all appointment data for a borrower
  - DELETE /data-delete/{borrower_email}        Anonymize/delete borrower PII
  - GET    /data-retention/report               Data retention status report

  Audit:
  - GET    /audit-export                        Export audit log entries as JSON (admin)

  TCPA / DNC / Contact Hours:
  - GET    /compliance/status                   Overall compliance health dashboard
  - GET    /compliance/opt-outs                 Recent opt-out requests
  - GET    /compliance/consent-audit            SMS consent coverage for scheduler contacts
  - GET    /compliance/contact-hours-violations Contact-hours violation detail
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_, text
from datetime import datetime, timedelta, timezone
import logging
import re

import pytz

from routes.scheduler._helpers import (
    get_current_user,
    get_models,
    _get_org_id,
    _is_scheduler_admin,
    _audit_log,
    _mask_email,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# Anonymization constant used to replace PII fields
_REDACTED = "[REDACTED]"
_ANON_EMAIL = "redacted@anonymized.invalid"

# Simple email validation pattern
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# TCPA Safe Harbor calling/texting hours
_TCPA_START_HOUR = 8   # 8 AM local
_TCPA_END_HOUR = 21    # 9 PM local


# ============================================================================
# HELPERS
# ============================================================================

def _validate_email_param(email: str) -> str:
    """Validate and normalize the borrower_email path parameter."""
    email = (email or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address format")
    if len(email) > 320:
        raise HTTPException(status_code=400, detail="Email address too long")
    return email


def _require_admin(user):
    """Raise 403 if the user is not a scheduler admin."""
    if not _is_scheduler_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Data compliance operations require admin privileges",
        )


def _check_pii_retention(db: Session, organization_id: int, retention_days: int = 365) -> int:
    """Find appointments with PII beyond retention period.

    Returns the count of completed/cancelled/no-show appointments older than
    *retention_days* that still contain non-anonymized PII (attendee_email
    is not the anonymization sentinel).

    This helper supports COMP-006: automated PII data retention monitoring.
    """
    models = get_models()
    Appointment = models["Appointment"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    stale = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.organization_id == organization_id,
            Appointment.created_at < cutoff,
            Appointment.status.in_(["completed", "cancelled", "no_show"]),
            Appointment.attendee_email.isnot(None),
            Appointment.attendee_email != _ANON_EMAIL,
        )
        .scalar()
    ) or 0
    return stale


# ============================================================================
# DATA EXPORT
# ============================================================================

@router.get("/data-export/{borrower_email}")
async def export_borrower_data(
    borrower_email: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Export all scheduler data for a borrower (GDPR Article 20 / CCPA right of access).

    Returns a portable JSON bundle containing all appointment records,
    cancellation history, reminder delivery logs, and survey responses
    linked to the given email address within the caller's organization.

    Requires admin-level authentication.
    """
    user = await get_current_user(request, db)
    _require_admin(user)
    org_id = _get_org_id(user)
    email = _validate_email_param(borrower_email)

    models = get_models()
    Appointment = models["Appointment"]

    # ---- Appointments (past and future) ----
    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.organization_id == org_id,
            func.lower(Appointment.attendee_email) == email,
        )
        .order_by(Appointment.scheduled_start.desc())
        .limit(1000)
        .all()
    )

    appointment_ids = [a.id for a in appointments]

    exported_appointments = []
    for a in appointments:
        exported_appointments.append({
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "meeting_type": a.meeting_type.value if a.meeting_type else None,
            "meeting_mode": a.meeting_mode.value if a.meeting_mode else None,
            "scheduled_start": a.scheduled_start.isoformat() if a.scheduled_start else None,
            "scheduled_end": a.scheduled_end.isoformat() if a.scheduled_end else None,
            "duration_minutes": a.duration_minutes,
            "timezone": a.timezone,
            "location": a.location,
            "attendee_name": a.attendee_name,
            "attendee_email": a.attendee_email,
            "attendee_phone": a.attendee_phone,
            "attendee_notes": a.attendee_notes,
            "intake_responses": a.intake_responses,
            "status": a.status.value if a.status else None,
            "cancelled_at": a.cancelled_at.isoformat() if a.cancelled_at else None,
            "cancellation_reason": a.cancellation_reason,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            "no_show_at": a.no_show_at.isoformat() if a.no_show_at else None,
            "reschedule_count": a.reschedule_count,
            "booked_by_ai": a.booked_by_ai,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    # ---- Cancellation records (subset of appointments) ----
    cancellations = [
        {
            "appointment_id": a["id"],
            "cancelled_at": a["cancelled_at"],
            "cancellation_reason": a["cancellation_reason"],
            "original_start": a["scheduled_start"],
        }
        for a in exported_appointments
        if a["cancelled_at"] is not None
    ]

    # ---- Reminder delivery log ----
    exported_reminders = []
    if appointment_ids:
        from database.models.reminder_config import ReminderLog

        reminder_logs = (
            db.query(ReminderLog)
            .filter(ReminderLog.appointment_id.in_(appointment_ids))
            .order_by(ReminderLog.sent_at.desc())
            .all()
        )
        exported_reminders = [
            {
                "id": rl.id,
                "appointment_id": rl.appointment_id,
                "channel": rl.channel,
                "status": rl.status,
                "sent_at": rl.sent_at.isoformat() if rl.sent_at else None,
                "recipient_email": rl.recipient_email,
                "recipient_phone": rl.recipient_phone,
            }
            for rl in reminder_logs
        ]

    # ---- Survey responses ----
    exported_surveys = []
    try:
        from database.models.appointment_survey import AppointmentSurvey

        surveys = (
            db.query(AppointmentSurvey)
            .filter(
                AppointmentSurvey.organization_id == org_id,
                func.lower(AppointmentSurvey.borrower_email) == email,
            )
            .order_by(AppointmentSurvey.created_at.desc())
            .all()
        )
        exported_surveys = [
            {
                "id": s.id,
                "appointment_id": s.appointment_id,
                "overall_rating": s.overall_rating,
                "communication_rating": s.communication_rating,
                "knowledge_rating": s.knowledge_rating,
                "feedback_text": s.feedback_text,
                "would_recommend": s.would_recommend,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in surveys
        ]
    except Exception as e:
        logger.warning(f"Could not export surveys for {_mask_email(email)}: {e}")

    # ---- Slot holds (COMP-010: include PII fields for GDPR export) ----
    exported_slot_holds = []
    try:
        slot_holds = db.execute(text("""
            SELECT id, start_time, end_time, status, created_at,
                   held_for_name, held_for_phone, held_for_email
            FROM slot_holds WHERE held_for_email = :email AND organization_id = :org_id
        """), {"email": email, "org_id": org_id}).fetchall()
        exported_slot_holds = [dict(row._mapping) for row in slot_holds]
    except Exception as e:
        logger.warning("Failed to export slot_holds for %s: %s", _mask_email(email), e, exc_info=True)
        exported_slot_holds = []

    export_payload = {
        "export_type": "scheduler_data_export",
        "borrower_email": email,
        "organization_id": org_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by_user_id": getattr(user, "id", None),
        "data": {
            "appointments": exported_appointments,
            "cancellations": cancellations,
            "reminder_logs": exported_reminders,
            "survey_responses": exported_surveys,
            "slot_holds": exported_slot_holds,
        },
        "counts": {
            "appointments": len(exported_appointments),
            "cancellations": len(cancellations),
            "reminder_logs": len(exported_reminders),
            "survey_responses": len(exported_surveys),
            "slot_holds": len(exported_slot_holds),
        },
    }

    _audit_log(
        db, org_id, getattr(user, "id", None), "data_export",
        "borrower_data", None,
        changes={"borrower_email_masked": _mask_email(email), "counts": export_payload["counts"]},
        request=request,
    )
    db.commit()

    logger.info(
        f"Data export completed for {_mask_email(email)} in org {org_id}: "
        f"{len(exported_appointments)} appointments, {len(exported_reminders)} reminders, "
        f"{len(exported_surveys)} surveys"
    )

    return export_payload


# ============================================================================
# DATA DELETION (right to erasure)
# ============================================================================

@router.delete("/data-delete/{borrower_email}")
async def delete_borrower_data(
    borrower_email: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Delete/anonymize all borrower PII from scheduler data (GDPR Article 17).

    This endpoint:
    - Anonymizes appointment records (preserves aggregate stats but removes PII)
    - Deletes survey responses entirely
    - Deletes reminder log entries (recipient PII)
    - Keeps audit trail entries but redacts PII fields (required for compliance)

    Returns a summary of records affected.

    Requires admin-level authentication. This action is irreversible.
    """
    user = await get_current_user(request, db)
    _require_admin(user)
    org_id = _get_org_id(user)
    email = _validate_email_param(borrower_email)

    models = get_models()
    Appointment = models["Appointment"]
    SchedulerAuditLog = models.get("SchedulerAuditLog")

    counts = {
        "appointments_anonymized": 0,
        "slot_holds_anonymized": 0,
        "status_history_anonymized": 0,
        "reminders_anonymized": 0,
        "survey_responses_deleted": 0,
        "reminder_logs_deleted": 0,
        "audit_entries_redacted": 0,
    }

    # ---- 1. Anonymize appointments ----
    # Keep the record for aggregate stats (completion rates, no-show rates, duration)
    # but strip all PII fields.
    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.organization_id == org_id,
            func.lower(Appointment.attendee_email) == email,
        )
        .all()
    )

    appointment_ids = [a.id for a in appointments]

    for a in appointments:
        a.attendee_name = _REDACTED
        a.attendee_email = _ANON_EMAIL
        a.attendee_phone = None
        a.attendee_notes = None
        a.intake_responses = {}
        a.internal_notes = None
        a.meeting_notes = None
        # Keep: title, status, scheduled_start/end, duration, meeting_type/mode
        # These are operational/statistical, not PII
        counts["appointments_anonymized"] += 1

    # ---- 1b. Cascade anonymize related tables (COMP-008) ----
    # Slot holds: held_for_name, held_for_phone, held_for_email
    try:
        result = db.execute(text("""
            UPDATE slot_holds SET held_for_name = :redacted, held_for_phone = NULL,
            held_for_email = :anon_email
            WHERE held_for_email = :email AND organization_id = :org_id
        """), {"redacted": _REDACTED, "anon_email": _ANON_EMAIL, "email": email, "org_id": org_id})
        counts["slot_holds_anonymized"] = result.rowcount
    except Exception as e:
        logger.warning("Could not anonymize slot_holds for %s: %s", _mask_email(email), e)

    # Appointment status history: changed_by_name
    if appointment_ids:
        try:
            result = db.execute(text("""
                UPDATE appointment_status_history SET changed_by_name = :redacted
                WHERE appointment_id = ANY(:ids)
            """), {"redacted": _REDACTED, "ids": appointment_ids})
            counts["status_history_anonymized"] = result.rowcount
        except Exception as e:
            logger.warning("Could not anonymize appointment_status_history for %s: %s", _mask_email(email), e)

    # Scheduler reminders: anonymize recipient PII fields
    if appointment_ids:
        try:
            result = db.execute(text("""
                UPDATE scheduler_reminders
                SET recipient_email = :anon_email,
                    recipient_phone = NULL,
                    recipient_name = :redacted
                WHERE appointment_id = ANY(:ids)
            """), {"anon_email": _ANON_EMAIL, "redacted": _REDACTED, "ids": appointment_ids})
            counts["reminders_anonymized"] = result.rowcount
        except Exception as e:
            logger.warning("Could not anonymize scheduler_reminders for %s: %s", _mask_email(email), e)

    # ---- 2. Delete survey responses ----
    try:
        from database.models.appointment_survey import AppointmentSurvey

        survey_count = (
            db.query(AppointmentSurvey)
            .filter(
                AppointmentSurvey.organization_id == org_id,
                func.lower(AppointmentSurvey.borrower_email) == email,
            )
            .delete(synchronize_session="fetch")
        )
        counts["survey_responses_deleted"] = survey_count
    except Exception as e:
        logger.warning(f"Could not delete surveys for {_mask_email(email)}: {e}")

    # ---- 3. Delete reminder logs (contain recipient PII) ----
    if appointment_ids:
        try:
            from database.models.reminder_config import ReminderLog

            reminder_count = (
                db.query(ReminderLog)
                .filter(ReminderLog.appointment_id.in_(appointment_ids))
                .delete(synchronize_session="fetch")
            )
            counts["reminder_logs_deleted"] = reminder_count
        except Exception as e:
            logger.warning(f"Could not delete reminder logs for {_mask_email(email)}: {e}")

    # ---- 4. Redact PII in audit trail entries ----
    # Audit entries are legally required for compliance, so we keep the record
    # but scrub any PII from the changes JSON.
    if SchedulerAuditLog and appointment_ids:
        try:
            audit_entries = (
                db.query(SchedulerAuditLog)
                .filter(
                    SchedulerAuditLog.organization_id == org_id,
                    SchedulerAuditLog.entity_type.in_(["appointment", "borrower_data"]),
                    SchedulerAuditLog.entity_id.in_(appointment_ids),
                )
                .all()
            )

            for entry in audit_entries:
                if entry.changes and isinstance(entry.changes, dict):
                    redacted_changes = {}
                    for k, v in entry.changes.items():
                        if isinstance(v, str) and ("@" in v or email in v.lower()):
                            redacted_changes[k] = _REDACTED
                        elif isinstance(v, dict):
                            redacted_changes[k] = {
                                ik: _REDACTED if isinstance(iv, str) and ("@" in iv or email in iv.lower()) else iv
                                for ik, iv in v.items()
                            }
                        else:
                            redacted_changes[k] = v
                    entry.changes = redacted_changes
                    counts["audit_entries_redacted"] += 1

                # Redact IP address from audit entries related to this borrower
                entry.ip_address = None
        except Exception as e:
            logger.warning(f"Could not redact audit entries for {_mask_email(email)}: {e}")

    # ---- Write audit entry for the deletion itself ----
    _audit_log(
        db, org_id, getattr(user, "id", None), "data_deletion",
        "borrower_data", None,
        changes={
            "borrower_email_masked": _mask_email(email),
            "records_affected": counts,
        },
        request=request,
    )

    db.commit()

    logger.info(
        f"Data deletion completed for {_mask_email(email)} in org {org_id}: "
        f"{counts['appointments_anonymized']} appointments anonymized, "
        f"{counts['slot_holds_anonymized']} slot holds anonymized, "
        f"{counts['status_history_anonymized']} status history entries anonymized, "
        f"{counts['reminders_anonymized']} reminders anonymized, "
        f"{counts['survey_responses_deleted']} surveys deleted, "
        f"{counts['reminder_logs_deleted']} reminder logs deleted, "
        f"{counts['audit_entries_redacted']} audit entries redacted"
    )

    return {
        "success": True,
        "borrower_email_masked": _mask_email(email),
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "deleted_by_user_id": getattr(user, "id", None),
        "records_affected": counts,
        "message": (
            f"Anonymized {counts['appointments_anonymized']} appointments, "
            f"{counts['slot_holds_anonymized']} slot holds, "
            f"{counts['status_history_anonymized']} status history entries, "
            f"{counts['reminders_anonymized']} reminders; "
            f"deleted {counts['survey_responses_deleted']} survey responses and "
            f"{counts['reminder_logs_deleted']} reminder logs; "
            f"redacted {counts['audit_entries_redacted']} audit entries."
        ),
    }


# ============================================================================
# DATA RETENTION REPORT
# ============================================================================

@router.get("/data-retention/report")
async def get_data_retention_report(
    request: Request,
    retention_days: int = Query(730, ge=30, le=3650, description="Retention period in days (default 2 years)"),
    db: Session = Depends(get_db),
):
    """
    Data retention status report for the organization.

    Shows counts of records that exceed the retention period, pending
    deletion requests, and the last purge timestamp. Useful for
    compliance dashboards and periodic review.

    Requires admin-level authentication.
    """
    user = await get_current_user(request, db)
    _require_admin(user)
    org_id = _get_org_id(user)

    models = get_models()
    Appointment = models["Appointment"]
    SchedulerAuditLog = models.get("SchedulerAuditLog")

    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    # ---- Appointments older than retention period ----
    stale_appointments = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.organization_id == org_id,
            Appointment.created_at < retention_cutoff,
        )
        .scalar()
    ) or 0

    total_appointments = (
        db.query(func.count(Appointment.id))
        .filter(Appointment.organization_id == org_id)
        .scalar()
    ) or 0

    # ---- Stale appointments with PII still present ----
    stale_with_pii = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.organization_id == org_id,
            Appointment.created_at < retention_cutoff,
            Appointment.attendee_email != _ANON_EMAIL,
            Appointment.attendee_email.isnot(None),
        )
        .scalar()
    ) or 0

    # ---- Count of deletion requests (from audit log) ----
    deletion_requests = 0
    last_purge_date = None
    if SchedulerAuditLog:
        try:
            deletion_requests = (
                db.query(func.count(SchedulerAuditLog.id))
                .filter(
                    SchedulerAuditLog.organization_id == org_id,
                    SchedulerAuditLog.action == "data_deletion",
                )
                .scalar()
            ) or 0

            last_purge_row = (
                db.query(SchedulerAuditLog.created_at)
                .filter(
                    SchedulerAuditLog.organization_id == org_id,
                    SchedulerAuditLog.action == "data_deletion",
                )
                .order_by(SchedulerAuditLog.created_at.desc())
                .first()
            )
            if last_purge_row:
                last_purge_date = last_purge_row[0].isoformat() if last_purge_row[0] else None
        except Exception as e:
            logger.warning(f"Could not query audit log for retention report: {e}")

    # ---- Stale survey responses ----
    stale_surveys = 0
    try:
        from database.models.appointment_survey import AppointmentSurvey

        stale_surveys = (
            db.query(func.count(AppointmentSurvey.id))
            .filter(
                AppointmentSurvey.organization_id == org_id,
                AppointmentSurvey.created_at < retention_cutoff,
            )
            .scalar()
        ) or 0
    except Exception as e:
        logger.warning(f"Could not count stale surveys: {e}")

    # ---- Stale reminder logs ----
    stale_reminder_logs = 0
    try:
        from database.models.reminder_config import ReminderLog

        stale_reminder_logs = (
            db.query(func.count(ReminderLog.id))
            .join(Appointment, Appointment.id == ReminderLog.appointment_id)
            .filter(
                Appointment.organization_id == org_id,
                ReminderLog.sent_at < retention_cutoff,
            )
            .scalar()
        ) or 0
    except Exception as e:
        logger.warning(f"Could not count stale reminder logs: {e}")

    # ---- Terminal appointments with PII beyond retention (COMP-006) ----
    stale_terminal_with_pii = _check_pii_retention(db, org_id, retention_days)

    report = {
        "organization_id": org_id,
        "retention_period_days": retention_days,
        "retention_cutoff_date": retention_cutoff.date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "appointments": {
            "total": total_appointments,
            "older_than_retention": stale_appointments,
            "older_with_pii": stale_with_pii,
            "terminal_with_pii_past_retention": stale_terminal_with_pii,
        },
        "survey_responses": {
            "older_than_retention": stale_surveys,
        },
        "reminder_logs": {
            "older_than_retention": stale_reminder_logs,
        },
        "deletion_history": {
            "total_deletion_requests": deletion_requests,
            "last_purge_date": last_purge_date,
        },
        "recommendations": [],
    }

    # Build actionable recommendations
    if stale_terminal_with_pii > 0:
        report["recommendations"].append(
            f"{stale_terminal_with_pii} completed/cancelled/no-show appointment(s) older than "
            f"{retention_days} days still retain PII. These should be anonymized per retention policy."
        )
    if stale_with_pii > 0:
        report["recommendations"].append(
            f"{stale_with_pii} appointment(s) older than {retention_days} days still contain PII. "
            f"Consider running data deletion for affected borrowers."
        )
    if stale_surveys > 0:
        report["recommendations"].append(
            f"{stale_surveys} survey response(s) are older than the retention period."
        )
    if stale_reminder_logs > 0:
        report["recommendations"].append(
            f"{stale_reminder_logs} reminder log(s) are older than the retention period."
        )
    if not report["recommendations"]:
        report["recommendations"].append("All data is within the configured retention period.")

    _audit_log(
        db, org_id, getattr(user, "id", None), "viewed",
        "data_retention_report", None,
        changes={"retention_days": retention_days},
        request=request,
    )
    db.commit()

    return report


# ============================================================================
# AUDIT LOG EXPORT
# ============================================================================

@router.get("/audit-export")
async def export_audit_log(
    request: Request,
    days: int = Query(90, ge=1, le=3650, description="Lookback period in days"),
    entity_type: str = Query(None, description="Filter by entity type (e.g., appointment, booking_link)"),
    action: str = Query(None, description="Filter by action (e.g., created, updated, deleted)"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum entries to return"),
    db: Session = Depends(get_db),
):
    """
    Export audit log entries for the organization.

    Returns structured JSON suitable for compliance review, SOC 2 evidence,
    and regulatory audit responses. PII is already masked at write time.

    Requires admin-level authentication.
    """
    user = await get_current_user(request, db)
    _require_admin(user)
    org_id = _get_org_id(user)

    models = get_models()
    AuditLog = models.get("SchedulerAuditLog")

    if not AuditLog:
        raise HTTPException(status_code=501, detail="Audit log not available")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        db.query(AuditLog)
        .filter(
            AuditLog.organization_id == org_id,
            AuditLog.created_at >= cutoff,
        )
    )

    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(AuditLog.action == action)

    entries = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    _audit_log(
        db, org_id, getattr(user, "id", None), "exported",
        "audit_log", None,
        changes={"days": days, "count": len(entries)},
        request=request,
    )
    db.commit()

    return {
        "organization_id": org_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "period_days": days,
        "total_entries": len(entries),
        "entries": [
            {
                "id": e.id,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "user_id": e.user_id,
                "changes": e.changes,
                "booking_source": getattr(e, "booking_source", None),
                # SEC-005: IP addresses removed from API response to prevent data leakage
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
    }


# ============================================================================
# TCPA / DNC / CONTACT HOURS COMPLIANCE
# ============================================================================

def _normalize_phone(phone: str) -> str:
    """Strip a phone string to its last 10 digits for consistent matching."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _check_reminder_contact_hours(sent_at, recipient_tz_name: str = None):
    """
    Evaluate whether a reminder was sent within TCPA 8am-9pm local time.

    Returns (is_within_hours: bool, local_hour: int, tz_used: str).
    """
    tz_name = recipient_tz_name or "America/New_York"
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("America/New_York")
        tz_name = "America/New_York"

    if sent_at.tzinfo is None:
        sent_at = pytz.utc.localize(sent_at)

    local_time = sent_at.astimezone(tz)
    local_hour = local_time.hour
    return (_TCPA_START_HOUR <= local_hour < _TCPA_END_HOUR, local_hour, tz_name)


@router.get("/compliance/status")
async def get_compliance_status(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Lookback period in days"),
    db: Session = Depends(get_db),
):
    """
    Overall TCPA/DNC/contact hours compliance dashboard for scheduling.

    Runs four checks against the organization's recent scheduler
    communications and returns a per-check pass/warning/fail status plus
    an overall compliance verdict.

    Checks performed:
      1. **SMS consent coverage** -- What percentage of SMS reminder
         recipients have an active consent record (ChannelPreference
         sms_consent or TCPAConsent).
      2. **Contact hours enforcement** -- Were any SMS reminders sent
         outside the TCPA 8am-9pm window in the recipient's local time?
      3. **DNC list compliance** -- Were any SMS reminders sent to phone
         numbers on the internal Do Not Call list?
      4. **Opt-out handling** -- Are opt-outs being honoured (no sends
         to contacts with do_not_sms=True)?

    Requires admin-level authentication.
    """
    user = await get_current_user(request, db)
    _require_admin(user)
    org_id = _get_org_id(user)

    models = get_models()
    Appointment = models["Appointment"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    checks = []

    # ---- Gather recent SMS reminder logs ----
    sms_reminders = []
    try:
        from database.models.reminder_config import ReminderLog

        sms_reminders = (
            db.query(
                ReminderLog.id,
                ReminderLog.recipient_phone,
                ReminderLog.sent_at,
                ReminderLog.status,
                Appointment.timezone,
                Appointment.attendee_phone,
            )
            .join(Appointment, Appointment.id == ReminderLog.appointment_id)
            .filter(
                Appointment.organization_id == org_id,
                ReminderLog.channel == "sms",
                ReminderLog.sent_at >= cutoff,
            )
            .all()
        )
    except Exception as e:
        logger.warning(f"Could not query SMS reminder logs for compliance status: {e}")

    total_sms = len(sms_reminders)

    # ------------------------------------------------------------------
    # CHECK 1: SMS consent coverage
    # ------------------------------------------------------------------
    consent_verified = 0
    consent_missing = 0

    if total_sms > 0:
        # Collect unique phone numbers from SMS reminders
        unique_phones = set()
        for r in sms_reminders:
            phone = _normalize_phone(r.recipient_phone or r.attendee_phone or "")
            if phone:
                unique_phones.add(phone)

        # Look up consent via ChannelPreference
        consented_phones = set()
        try:
            from database.models.communication import ChannelPreference
            from database.models.lead_loan import Lead

            for phone in unique_phones:
                if len(phone) < 10:
                    continue
                lead = (
                    db.query(Lead.id)
                    .filter(
                        Lead.phone.ilike(f"%{phone[-10:]}"),
                        Lead.organization_id == org_id,
                    )
                    .first()
                )
                if lead:
                    pref = (
                        db.query(ChannelPreference)
                        .filter(ChannelPreference.lead_id == lead.id)
                        .first()
                    )
                    if pref and getattr(pref, "sms_consent", False):
                        consented_phones.add(phone)
                        continue

                # Fallback: check TCPAConsent table
                try:
                    from database.models.tcpa_consent import TCPAConsent

                    tcpa = (
                        db.query(TCPAConsent.id)
                        .filter(
                            TCPAConsent.phone_number.ilike(f"%{phone[-10:]}"),
                            TCPAConsent.organization_id == org_id,
                            TCPAConsent.is_active == True,  # noqa: E712
                            TCPAConsent.consent_channel.in_(["sms", "both"]),
                        )
                        .first()
                    )
                    if tcpa:
                        consented_phones.add(phone)
                except Exception as e:
                    logger.warning("Failed to check TCPAConsent for phone in consent audit: %s", e, exc_info=True)

            consent_verified = len(consented_phones)
            consent_missing = len(unique_phones) - consent_verified
            pct = (consent_verified / len(unique_phones) * 100) if unique_phones else 100

            checks.append({
                "check": "sms_consent",
                "status": "pass" if pct >= 99 else "warning" if pct >= 90 else "fail",
                "detail": f"{pct:.0f}% of SMS recipient phones ({consent_verified}/{len(unique_phones)}) have consent on file",
                "total_unique_phones": len(unique_phones),
                "with_consent": consent_verified,
                "without_consent": consent_missing,
            })
        except Exception as e:
            logger.warning(f"Consent coverage check error: {e}")
            checks.append({
                "check": "sms_consent",
                "status": "error",
                "detail": f"Could not verify consent records: {e}",
            })
    else:
        checks.append({
            "check": "sms_consent",
            "status": "pass",
            "detail": "No SMS reminders sent in this period",
            "total_unique_phones": 0,
        })

    # ------------------------------------------------------------------
    # CHECK 2: Contact hours enforcement (8am-9pm local)
    # ------------------------------------------------------------------
    outside_hours_count = 0
    outside_hours_examples = []

    for r in sms_reminders:
        if r.sent_at is None:
            continue
        tz_name = r.timezone if r.timezone else None
        within, local_hour, tz_used = _check_reminder_contact_hours(r.sent_at, tz_name)
        if not within:
            outside_hours_count += 1
            if len(outside_hours_examples) < 5:
                outside_hours_examples.append({
                    "reminder_id": r.id,
                    "sent_at_utc": r.sent_at.isoformat() if r.sent_at else None,
                    "local_hour": local_hour,
                    "timezone": tz_used,
                })

    checks.append({
        "check": "contact_hours",
        "status": "pass" if outside_hours_count == 0 else "fail",
        "detail": (
            f"{outside_hours_count} SMS reminder(s) sent outside 8am-9pm local time"
            if outside_hours_count > 0
            else "All SMS reminders sent within TCPA 8am-9pm window"
        ),
        "violations": outside_hours_count,
        "total_sms": total_sms,
        "examples": outside_hours_examples,
    })

    # ------------------------------------------------------------------
    # CHECK 3: DNC list compliance
    # ------------------------------------------------------------------
    dnc_violations = 0
    dnc_examples = []

    try:
        from database.models.dialer import ContactDNCStatus

        # Get all DNC phone numbers
        dnc_phones = set()
        dnc_entries = db.query(ContactDNCStatus.phone_number).all()
        for entry in dnc_entries:
            dnc_phones.add(_normalize_phone(entry.phone_number))

        if dnc_phones:
            for r in sms_reminders:
                phone = _normalize_phone(r.recipient_phone or "")
                if phone and phone in dnc_phones:
                    dnc_violations += 1
                    if len(dnc_examples) < 5:
                        dnc_examples.append({
                            "reminder_id": r.id,
                            "sent_at_utc": r.sent_at.isoformat() if r.sent_at else None,
                            "phone_last4": phone[-4:] if len(phone) >= 4 else "****",
                        })
    except Exception as e:
        logger.warning(f"DNC compliance check error: {e}")

    checks.append({
        "check": "dnc_compliance",
        "status": "pass" if dnc_violations == 0 else "fail",
        "detail": (
            f"{dnc_violations} SMS reminder(s) sent to DNC-listed numbers"
            if dnc_violations > 0
            else "No SMS reminders sent to DNC-listed numbers"
        ),
        "violations": dnc_violations,
        "examples": dnc_examples,
    })

    # ------------------------------------------------------------------
    # CHECK 4: Opt-out handling (do_not_sms honoured)
    # ------------------------------------------------------------------
    optout_violations = 0

    try:
        from database.models.communication import ChannelPreference
        from database.models.lead_loan import Lead

        # Find leads with do_not_sms=True who still received SMS
        opted_out_phones = set()
        opted_out_leads = (
            db.query(Lead.phone)
            .join(ChannelPreference, ChannelPreference.lead_id == Lead.id)
            .filter(
                Lead.organization_id == org_id,
                ChannelPreference.do_not_sms == True,  # noqa: E712
                Lead.phone.isnot(None),
            )
            .all()
        )
        for row in opted_out_leads:
            norm = _normalize_phone(row.phone)
            if norm:
                opted_out_phones.add(norm)

        if opted_out_phones:
            for r in sms_reminders:
                phone = _normalize_phone(r.recipient_phone or "")
                if phone and phone in opted_out_phones:
                    optout_violations += 1
    except Exception as e:
        logger.warning(f"Opt-out compliance check error: {e}")

    checks.append({
        "check": "opt_out_handling",
        "status": "pass" if optout_violations == 0 else "fail",
        "detail": (
            f"{optout_violations} SMS sent to contacts who opted out"
            if optout_violations > 0
            else "All opt-out preferences honoured"
        ),
        "violations": optout_violations,
    })

    # ------------------------------------------------------------------
    # Overall verdict
    # ------------------------------------------------------------------
    statuses = [c["status"] for c in checks]
    if "fail" in statuses:
        overall = "non_compliant"
    elif "warning" in statuses or "error" in statuses:
        overall = "review_required"
    else:
        overall = "compliant"

    _audit_log(
        db, org_id, getattr(user, "id", None), "viewed",
        "compliance_status", None,
        changes={"period_days": days, "overall": overall},
        request=request,
    )
    db.commit()

    return {
        "overall_status": overall,
        "period_days": days,
        "total_sms_checked": total_sms,
        "checks": checks,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/compliance/opt-outs")
async def get_opt_outs(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
):
    """
    Get recent opt-out events relevant to scheduler communications.

    Aggregates opt-out signals from three sources:
      1. ChannelPreference records with do_not_sms=True
      2. ContactDNCStatus entries (internal DNC list)
      3. TCPAConsent revocations (is_active=False with revoked_at set)

    All results are scoped to the caller's organization.
    Requires admin-level authentication.
    """
    user = await get_current_user(request, db)
    _require_admin(user)
    org_id = _get_org_id(user)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    opt_outs = []

    # 1. ChannelPreference opt-outs (do_not_sms flipped to True)
    try:
        from database.models.communication import ChannelPreference
        from database.models.lead_loan import Lead

        pref_optouts = (
            db.query(
                Lead.id.label("lead_id"),
                func.concat(Lead.first_name, " ", Lead.last_name).label("name"),
                Lead.phone,
                ChannelPreference.updated_at,
            )
            .join(ChannelPreference, ChannelPreference.lead_id == Lead.id)
            .filter(
                Lead.organization_id == org_id,
                ChannelPreference.do_not_sms == True,  # noqa: E712
                ChannelPreference.updated_at >= cutoff,
            )
            .order_by(ChannelPreference.updated_at.desc())
            .limit(100)
            .all()
        )

        for row in pref_optouts:
            opt_outs.append({
                "source": "channel_preference",
                "lead_id": row.lead_id,
                "name": row.name,
                "phone_last4": row.phone[-4:] if row.phone and len(row.phone) >= 4 else None,
                "opted_out_at": row.updated_at.isoformat() if row.updated_at else None,
                "channel": "sms",
            })
    except Exception as e:
        logger.warning(f"ChannelPreference opt-out query failed: {e}")

    # 2. DNC list entries
    try:
        from database.models.dialer import ContactDNCStatus

        dnc_entries = (
            db.query(ContactDNCStatus)
            .filter(ContactDNCStatus.created_at >= cutoff)
            .order_by(ContactDNCStatus.created_at.desc())
            .limit(100)
            .all()
        )

        for entry in dnc_entries:
            opt_outs.append({
                "source": "dnc_list",
                "phone_last4": entry.phone_number[-4:] if entry.phone_number and len(entry.phone_number) >= 4 else None,
                "reason": entry.reason,
                "opted_out_at": entry.created_at.isoformat() if entry.created_at else None,
                "channel": "call_and_sms",
            })
    except Exception as e:
        logger.warning(f"DNC opt-out query failed: {e}")

    # 3. TCPAConsent revocations
    try:
        from database.models.tcpa_consent import TCPAConsent

        revocations = (
            db.query(TCPAConsent)
            .filter(
                TCPAConsent.organization_id == org_id,
                TCPAConsent.is_active == False,  # noqa: E712
                TCPAConsent.revoked_at >= cutoff,
            )
            .order_by(TCPAConsent.revoked_at.desc())
            .limit(100)
            .all()
        )

        for rev in revocations:
            opt_outs.append({
                "source": "tcpa_consent_revoked",
                "phone_last4": rev.phone_number[-4:] if rev.phone_number and len(rev.phone_number) >= 4 else None,
                "consent_channel": rev.consent_channel,
                "revocation_method": getattr(rev, "revocation_method", None),
                "opted_out_at": rev.revoked_at.isoformat() if rev.revoked_at else None,
                "channel": rev.consent_channel,
            })
    except Exception as e:
        logger.warning(f"TCPAConsent revocation query failed: {e}")

    # Sort all opt-outs by date descending
    opt_outs.sort(
        key=lambda x: x.get("opted_out_at") or "",
        reverse=True,
    )

    return {
        "period_days": days,
        "total": len(opt_outs),
        "opt_outs": opt_outs,
    }


@router.get("/compliance/consent-audit")
async def get_consent_audit(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Audit SMS consent coverage for contacts who have scheduler appointments.

    Scans all contacts with upcoming or recent appointments that include
    a phone number and checks whether each has a valid consent record.
    This supports proactive remediation before reminders are sent.

    Requires admin-level authentication.
    """
    user = await get_current_user(request, db)
    _require_admin(user)
    org_id = _get_org_id(user)

    models = get_models()
    Appointment = models["Appointment"]

    # Get distinct phones from upcoming/recent appointments (last 30 days + future)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    appointments_with_phone = (
        db.query(
            Appointment.attendee_phone,
            Appointment.attendee_name,
            Appointment.attendee_email,
            func.count(Appointment.id).label("appointment_count"),
            func.min(Appointment.scheduled_start).label("next_appointment"),
        )
        .filter(
            Appointment.organization_id == org_id,
            Appointment.attendee_phone.isnot(None),
            Appointment.attendee_phone != "",
            Appointment.attendee_email != _ANON_EMAIL,
            Appointment.scheduled_start >= cutoff,
        )
        .group_by(
            Appointment.attendee_phone,
            Appointment.attendee_name,
            Appointment.attendee_email,
        )
        .all()
    )

    contacts = []
    with_consent = 0
    without_consent = 0

    for row in appointments_with_phone:
        phone = _normalize_phone(row.attendee_phone)
        if len(phone) < 10:
            continue

        has_consent = False
        consent_source = None

        # Check ChannelPreference
        try:
            from database.models.communication import ChannelPreference
            from database.models.lead_loan import Lead

            lead = (
                db.query(Lead.id)
                .filter(
                    Lead.phone.ilike(f"%{phone[-10:]}"),
                    Lead.organization_id == org_id,
                )
                .first()
            )
            if lead:
                pref = (
                    db.query(ChannelPreference)
                    .filter(ChannelPreference.lead_id == lead.id)
                    .first()
                )
                if pref:
                    if getattr(pref, "do_not_sms", False):
                        consent_source = "opted_out"
                    elif getattr(pref, "sms_consent", False):
                        has_consent = True
                        consent_source = "channel_preference"
        except Exception as e:
            logger.warning("Failed to check ChannelPreference for consent verification: %s", e, exc_info=True)

        # Fallback: TCPAConsent table
        if not has_consent and consent_source != "opted_out":
            try:
                from database.models.tcpa_consent import TCPAConsent

                tcpa = (
                    db.query(TCPAConsent.id, TCPAConsent.consent_type, TCPAConsent.consent_source)
                    .filter(
                        TCPAConsent.phone_number.ilike(f"%{phone[-10:]}"),
                        TCPAConsent.organization_id == org_id,
                        TCPAConsent.is_active == True,  # noqa: E712
                        TCPAConsent.consent_channel.in_(["sms", "both"]),
                    )
                    .first()
                )
                if tcpa:
                    has_consent = True
                    consent_source = f"tcpa_consent ({tcpa.consent_type})"
            except Exception as e:
                logger.warning("Failed to check TCPAConsent for consent verification: %s", e, exc_info=True)

        if has_consent:
            with_consent += 1
        elif consent_source != "opted_out":
            without_consent += 1

        contacts.append({
            "phone_last4": phone[-4:] if len(phone) >= 4 else "****",
            "name": row.attendee_name,
            "appointment_count": row.appointment_count,
            "next_appointment": row.next_appointment.isoformat() if row.next_appointment else None,
            "has_sms_consent": has_consent,
            "consent_source": consent_source,
            "opted_out": consent_source == "opted_out",
        })

    # Sort: contacts without consent first (actionable items at top)
    contacts.sort(key=lambda c: (c["has_sms_consent"], c["opted_out"]))

    total = with_consent + without_consent
    coverage_pct = (with_consent / total * 100) if total > 0 else 100.0

    return {
        "organization_id": org_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_contacts_with_phone": len(contacts),
            "with_consent": with_consent,
            "without_consent": without_consent,
            "opted_out": len([c for c in contacts if c["opted_out"]]),
            "coverage_percent": round(coverage_pct, 1),
        },
        "contacts": contacts,
    }


@router.get("/compliance/contact-hours-violations")
async def get_contact_hours_violations(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
):
    """
    Detailed report of scheduler SMS reminders sent outside the TCPA
    8am-9pm window in the recipient's local timezone.

    Each violation includes the send time, the local hour, and the
    timezone used for evaluation. This helps compliance officers
    investigate and remediate contact-hours issues.

    Requires admin-level authentication.
    """
    user = await get_current_user(request, db)
    _require_admin(user)
    org_id = _get_org_id(user)

    models = get_models()
    Appointment = models["Appointment"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    violations = []
    total_sms = 0

    try:
        from database.models.reminder_config import ReminderLog

        sms_reminders = (
            db.query(
                ReminderLog.id,
                ReminderLog.recipient_phone,
                ReminderLog.sent_at,
                ReminderLog.status,
                ReminderLog.appointment_id,
                Appointment.timezone,
                Appointment.attendee_name,
                Appointment.scheduled_start,
            )
            .join(Appointment, Appointment.id == ReminderLog.appointment_id)
            .filter(
                Appointment.organization_id == org_id,
                ReminderLog.channel == "sms",
                ReminderLog.sent_at >= cutoff,
            )
            .order_by(ReminderLog.sent_at.desc())
            .all()
        )

        total_sms = len(sms_reminders)

        for r in sms_reminders:
            if r.sent_at is None:
                continue
            within, local_hour, tz_used = _check_reminder_contact_hours(
                r.sent_at, r.timezone
            )
            if not within:
                violations.append({
                    "reminder_id": r.id,
                    "appointment_id": r.appointment_id,
                    "attendee_name": r.attendee_name,
                    "phone_last4": (
                        r.recipient_phone[-4:]
                        if r.recipient_phone and len(r.recipient_phone) >= 4
                        else "****"
                    ),
                    "sent_at_utc": r.sent_at.isoformat(),
                    "local_hour": local_hour,
                    "timezone": tz_used,
                    "appointment_start": (
                        r.scheduled_start.isoformat() if r.scheduled_start else None
                    ),
                    "status": r.status,
                })
    except Exception as e:
        logger.warning(f"Contact hours violation query failed: {e}")

    return {
        "period_days": days,
        "total_sms_checked": total_sms,
        "violation_count": len(violations),
        "violations": violations,
        "tcpa_window": f"{_TCPA_START_HOUR}:00 - {_TCPA_END_HOUR}:00 local time",
    }
