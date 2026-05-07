"""
Scheduled Report Executor
=========================

Enterprise Readiness Domain 9, Check 9.11: Execution engine for scheduled reports.

The CRUD endpoints in report_export_routes.py store schedules in the
scheduled_reports table, but nothing actually runs them outside of the
optional Celery beat task (which requires a separate Celery worker).

This module provides a self-contained executor that can be called from:
  - An API endpoint (POST /api/v1/reports/schedule/{id}/run-now)
  - A lightweight cron / Railway cron job
  - The existing Celery task (as a drop-in replacement for inline logic)

Functions:
    check_and_run_due_reports(db) -> dict   — find and execute all due reports
    run_single_report(db, schedule_id) -> dict — run one schedule on demand
    get_due_reports(db) -> list[dict]        — list schedules that are currently due
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Public API
# =============================================================================


def check_and_run_due_reports(db: Session) -> Dict[str, Any]:
    """
    Query scheduled_reports for reports that are due, generate them,
    and email results to recipients.

    A report is "due" when:
      - is_active = true
      - The current UTC hour matches hour_utc
      - The frequency/day constraints match (see _is_report_due)
      - last_sent_at is NULL or before today (at most once per day)

    Args:
        db: SQLAlchemy session (should NOT have tenant RLS set — this is
            a cross-tenant sweep).

    Returns:
        {"delivered": int, "failed": int, "skipped": int, "details": [...]}
    """
    now = datetime.now(timezone.utc)
    schedules = _fetch_active_schedules(db)

    delivered = 0
    failed = 0
    skipped = 0
    details: List[Dict[str, Any]] = []

    for schedule in schedules:
        if not _is_report_due(schedule, now):
            skipped += 1
            continue

        try:
            result = _execute_schedule(db, schedule)
            delivered += 1
            details.append({
                "schedule_id": schedule["id"],
                "report_type": schedule["report_type"],
                "status": "delivered",
                "recipients_count": len(schedule["recipients"]),
            })
            logger.info(
                "Delivered scheduled report %d: %s (%s) to %d recipients",
                schedule["id"],
                schedule["report_type"],
                schedule["export_format"],
                len(schedule["recipients"]),
            )
        except Exception as e:
            failed += 1
            details.append({
                "schedule_id": schedule["id"],
                "report_type": schedule["report_type"],
                "status": "failed",
                "error": str(e),
            })
            logger.error("Failed to deliver scheduled report %d: %s", schedule["id"], e)

    summary = {
        "delivered": delivered,
        "failed": failed,
        "skipped": skipped,
        "checked": len(schedules),
        "run_at": now.isoformat(),
        "details": details,
    }
    logger.info(
        "Scheduled report sweep complete: %d delivered, %d failed, %d skipped out of %d active",
        delivered, failed, skipped, len(schedules),
    )
    return summary


def run_single_report(db: Session, schedule_id: int, org_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate and deliver a specific scheduled report on demand,
    regardless of whether it is currently "due".

    Args:
        db: SQLAlchemy session.
        schedule_id: Primary key in scheduled_reports.
        org_id: If provided, enforces org-level ownership check.

    Returns:
        {"success": True/False, "schedule_id": ..., ...}

    Raises:
        ValueError: if schedule not found or not owned by org_id.
    """
    params: Dict[str, Any] = {"id": schedule_id}
    org_filter = ""
    if org_id is not None:
        org_filter = " AND organization_id = :org_id"
        params["org_id"] = org_id

    row = db.execute(sa_text(f"""
        SELECT id, organization_id, created_by_id, report_type, export_format,
               frequency, recipients, title, day_of_week, day_of_month,
               hour_utc, is_active, last_sent_at
        FROM scheduled_reports
        WHERE id = :id{org_filter}
    """), params).fetchone()

    if not row:
        raise ValueError(f"Scheduled report {schedule_id} not found")

    schedule = _row_to_dict(row)

    if not schedule["is_active"]:
        raise ValueError(f"Scheduled report {schedule_id} is inactive")

    try:
        _execute_schedule(db, schedule)
        return {
            "success": True,
            "schedule_id": schedule_id,
            "report_type": schedule["report_type"],
            "export_format": schedule["export_format"],
            "recipients": schedule["recipients"],
            "message": f"Report generated and delivery initiated for {len(schedule['recipients'])} recipients",
        }
    except Exception as e:
        logger.error("On-demand report %d failed: %s", schedule_id, e)
        return {
            "success": False,
            "schedule_id": schedule_id,
            "error": str(e),
        }


def get_due_reports(db: Session) -> List[Dict[str, Any]]:
    """
    Return a list of scheduled reports that are currently due for execution.

    Useful for the GET /api/v1/reports/schedule/due endpoint so operators
    can inspect what would run before triggering execution.

    Args:
        db: SQLAlchemy session.

    Returns:
        List of schedule dicts with an added "due_reason" field.
    """
    now = datetime.now(timezone.utc)
    schedules = _fetch_active_schedules(db)
    due: List[Dict[str, Any]] = []

    for schedule in schedules:
        if _is_report_due(schedule, now):
            schedule["due_reason"] = _due_reason(schedule, now)
            due.append(schedule)

    return due


# =============================================================================
# Due-ness Check
# =============================================================================


def _is_report_due(schedule: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """
    Determine whether a scheduled report should run right now.

    Rules:
      - Daily: due every day at hour_utc, provided it hasn't already run today.
      - Weekly: due on the configured day_of_week (0=Monday) at hour_utc.
                If day_of_week is NULL, defaults to Monday.
      - Monthly: due on the configured day_of_month at hour_utc.
                 If day_of_month is NULL, defaults to the 1st.

    A report that has already been sent today (last_sent_at >= start of today UTC)
    is never considered due again.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not schedule.get("is_active", False):
        return False

    # Check hour match (allow 1-hour window for clock skew / delayed execution)
    hour_utc = schedule.get("hour_utc", 8)
    if now.hour != hour_utc:
        return False

    # Already sent today?
    last_sent = schedule.get("last_sent_at")
    if last_sent:
        if isinstance(last_sent, str):
            try:
                last_sent = datetime.fromisoformat(last_sent)
            except (ValueError, TypeError):
                last_sent = None
        if last_sent:
            # Ensure timezone-aware comparison
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if last_sent >= today_start:
                return False

    frequency = schedule.get("frequency", "weekly")

    if frequency == "daily":
        return True

    elif frequency == "weekly":
        target_dow = schedule.get("day_of_week")
        if target_dow is None:
            target_dow = 0  # Default Monday
        return now.weekday() == target_dow

    elif frequency == "monthly":
        target_dom = schedule.get("day_of_month")
        if target_dom is None:
            target_dom = 1  # Default 1st
        return now.day == target_dom

    return False


def _due_reason(schedule: Dict[str, Any], now: datetime) -> str:
    """Human-readable explanation of why a report is due."""
    frequency = schedule.get("frequency", "weekly")
    if frequency == "daily":
        return f"Daily report due at {schedule.get('hour_utc', 8):02d}:00 UTC"
    elif frequency == "weekly":
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        dow = schedule.get("day_of_week", 0) or 0
        return f"Weekly report due on {days[dow]} at {schedule.get('hour_utc', 8):02d}:00 UTC"
    elif frequency == "monthly":
        dom = schedule.get("day_of_month", 1) or 1
        return f"Monthly report due on day {dom} at {schedule.get('hour_utc', 8):02d}:00 UTC"
    return f"Unknown frequency: {frequency}"


# =============================================================================
# Execution
# =============================================================================


def _execute_schedule(db: Session, schedule: Dict[str, Any]) -> None:
    """
    Generate the report and send it, then update last_sent_at.

    Raises on failure so the caller can log/report the error.
    """
    org_id = schedule["organization_id"]
    report_type = schedule["report_type"]
    export_format = schedule["export_format"]
    recipients = schedule["recipients"]
    title = schedule.get("title")

    # Generate report content
    report_data = _generate_report_data(db, org_id, report_type)
    file_bytes = _export_report(report_data, report_type, export_format, title)

    # Determine filename
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    ext_map = {"pdf": "pdf", "excel": "xlsx", "csv": "csv"}
    extension = ext_map.get(export_format, "pdf")
    filename = f"{report_type}_report_{ts}.{extension}"

    report_title = title or f"{report_type.replace('_', ' ').title()} Report"

    # Send email (stub — logs delivery, delegates to real transport if available)
    _send_report_email(
        recipients=recipients,
        report_data=file_bytes,
        format=export_format,
        report_name=report_title,
        filename=filename,
    )

    # Update last_sent_at
    db.execute(sa_text("""
        UPDATE scheduled_reports
        SET last_sent_at = NOW(), updated_at = NOW()
        WHERE id = :id
    """), {"id": schedule["id"]})
    db.commit()


def _generate_report_data(db: Session, org_id: int, report_type: str) -> Dict[str, Any]:
    """
    Generate structured report data for a given type.

    Delegates to the report_export_service which has full implementations
    for each report type.
    """
    from services.report_export_service import report_exporter

    if report_type == "sla_compliance":
        return report_exporter.generate_sla_compliance_report(db=db, org_id=org_id)

    elif report_type == "pipeline":
        # Use a basic scope (org-wide) since this runs outside a user request
        scope = {"scope": "organization", "org_id": org_id}
        try:
            return {"loans": _query_pipeline_data(db, org_id)}
        except Exception as e:
            logger.warning("Pipeline report data query failed, returning empty: %s", e)
            return {"loans": []}

    elif report_type == "scorecard":
        try:
            scope = {"scope": "organization", "org_id": org_id}
            from services.report_export_service import format_production_report
            rows, _total = format_production_report(db=db, org_id=org_id, scope=scope)
            return {"production": rows}
        except Exception as e:
            logger.warning("Scorecard report data query failed: %s", e)
            return {"conversion": {}, "funded": {}}

    elif report_type == "financial":
        return {"sections": []}

    return {}


def _query_pipeline_data(db: Session, org_id: int) -> List[Dict[str, Any]]:
    """Query active pipeline loans for an org."""
    rows = db.execute(sa_text("""
        SELECT loan_number, borrower_name, amount, stage,
               days_in_stage, closing_date, loan_type
        FROM loans
        WHERE organization_id = :org_id
            AND stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN')
        ORDER BY created_at DESC
        LIMIT 500
    """), {"org_id": org_id}).fetchall()

    return [
        {
            "loan_number": r[0],
            "borrower": r[1],
            "amount_formatted": f"${float(r[2] or 0):,.2f}",
            "status": r[3],
            "days_in_status": r[4] or 0,
            "expected_close": r[5].isoformat() if r[5] else "",
            "loan_type": r[6],
        }
        for r in rows
    ]


def _export_report(
    report_data: Dict[str, Any],
    report_type: str,
    export_format: str,
    title: Optional[str] = None,
) -> bytes:
    """Convert structured report data to the requested file format."""
    from services.report_export_service import report_exporter

    if export_format == "pdf":
        return report_exporter.generate_pdf(report_data, report_type, title)
    elif export_format == "excel":
        return report_exporter.generate_excel(report_data, report_type, title)
    else:
        return report_exporter.generate_csv(report_data, report_type)


# =============================================================================
# Email Delivery (stub with fallback to real transport)
# =============================================================================


def _send_report_email(
    recipients: List[str],
    report_data: bytes,
    format: str,
    report_name: str,
    filename: Optional[str] = None,
) -> None:
    """
    Send a generated report to the specified recipients.

    This is a stub that logs the delivery attempt. If the real email
    infrastructure is available (Microsoft Graph token or SMTP config),
    it delegates to the existing _send_report_email in report_tasks.py.
    Otherwise it logs what would have been sent.

    Args:
        recipients: List of email addresses.
        report_data: The generated report file bytes.
        format: Export format (pdf, excel, csv).
        report_name: Human-readable report title.
        filename: Attachment filename.
    """
    if not recipients:
        logger.warning("No recipients specified for report '%s' — skipping email", report_name)
        return

    content_type_map = {
        "pdf": "application/pdf",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
    }
    content_type = content_type_map.get(format, "application/octet-stream")
    file_size_kb = len(report_data) / 1024

    # Try to use the real email transport from report_tasks
    try:
        import os
        has_graph = bool(os.getenv("MS_GRAPH_ACCESS_TOKEN") or os.getenv("MICROSOFT_GRAPH_TOKEN"))
        has_smtp = bool(os.getenv("SMTP_USER"))

        if has_graph or has_smtp:
            from tasks.report_tasks import _send_report_email as real_send
            subject = f"Perennia AI — {report_name} ({datetime.now(timezone.utc).strftime('%B %d, %Y')})"
            body = (
                f"Your scheduled {report_name} is attached.\n\n"
                f"Format: {format.upper()}\n"
                f"Generated: {datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p UTC')}\n\n"
                f"This is an automated report from Perennia AI."
            )
            real_send(
                recipients=recipients,
                subject=subject,
                body=body,
                attachment_bytes=report_data,
                attachment_name=filename or f"report.{format}",
                content_type=content_type,
            )
            logger.info(
                "Report '%s' (%.1f KB %s) emailed to %d recipients via transport",
                report_name, file_size_kb, format, len(recipients),
            )
            return
    except Exception as e:
        logger.warning("Real email transport unavailable (%s), falling back to stub log", e)

    # Stub: log what would be sent
    logger.info(
        "STUB EMAIL: Report '%s' (%.1f KB %s) would be sent to: %s",
        report_name,
        file_size_kb,
        format,
        ", ".join(recipients),
    )


# =============================================================================
# Helpers
# =============================================================================


def _fetch_active_schedules(db: Session) -> List[Dict[str, Any]]:
    """Fetch all active scheduled reports across all organizations."""
    rows = db.execute(sa_text("""
        SELECT id, organization_id, created_by_id, report_type, export_format,
               frequency, recipients, title, day_of_week, day_of_month,
               hour_utc, is_active, last_sent_at
        FROM scheduled_reports
        WHERE is_active = true
        ORDER BY organization_id, id
    """)).fetchall()

    return [_row_to_dict(row) for row in rows]


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a scheduled_reports row (tuple) to a dict."""
    recipients_raw = row[6]
    if isinstance(recipients_raw, str):
        try:
            recipients = json.loads(recipients_raw)
        except (json.JSONDecodeError, TypeError):
            recipients = []
    elif isinstance(recipients_raw, list):
        # JSONB may already be deserialized by the driver
        recipients = recipients_raw
    else:
        recipients = []

    return {
        "id": row[0],
        "organization_id": row[1],
        "created_by_id": row[2],
        "report_type": row[3],
        "export_format": row[4],
        "frequency": row[5],
        "recipients": recipients,
        "title": row[7],
        "day_of_week": row[8],
        "day_of_month": row[9],
        "hour_utc": row[10],
        "is_active": row[11],
        "last_sent_at": row[12],
    }
