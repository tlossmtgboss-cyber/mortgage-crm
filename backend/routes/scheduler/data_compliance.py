"""
Scheduler Data Compliance Routes - GDPR/CCPA data export and deletion.

Enterprise mortgage lenders need data portability and right-to-erasure
capabilities for borrower appointment data.

Endpoints (all admin-only, tenant-isolated):
  - GET    /data-export/{borrower_email}       Export all appointment data for a borrower
  - DELETE /data-delete/{borrower_email}        Anonymize/delete borrower PII
  - GET    /data-retention/report               Data retention status report
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
import logging
import re

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
        },
        "counts": {
            "appointments": len(exported_appointments),
            "cancellations": len(cancellations),
            "reminder_logs": len(exported_reminders),
            "survey_responses": len(exported_surveys),
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
        f"{counts['appointments_anonymized']} anonymized, "
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
            f"deleted {counts['survey_responses_deleted']} survey responses and "
            f"{counts['reminder_logs_deleted']} reminder logs, "
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

    report = {
        "organization_id": org_id,
        "retention_period_days": retention_days,
        "retention_cutoff_date": retention_cutoff.date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "appointments": {
            "total": total_appointments,
            "older_than_retention": stale_appointments,
            "older_with_pii": stale_with_pii,
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
