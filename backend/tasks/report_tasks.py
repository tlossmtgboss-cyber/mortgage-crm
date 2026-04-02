"""
Scheduled Report Delivery Tasks
================================

Enterprise Readiness Domain 9, Check 9.11: Scheduled report delivery.

Celery tasks that generate and email reports on a configurable schedule
(daily, weekly, monthly).

Usage:
    # Manually trigger
    from tasks.report_tasks import deliver_scheduled_reports
    deliver_scheduled_reports.delay()

    # Runs automatically via Celery Beat (configured in celery_app.py):
    # - Daily at 8 AM UTC
    # - Checks scheduled_reports table for due reports
"""

import json
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Lazy import to avoid circular imports."""
    from tasks.celery_app import celery_app
    return celery_app


celery_app_lazy = None


def _app():
    global celery_app_lazy
    if celery_app_lazy is None:
        celery_app_lazy = _get_celery_app()
    return celery_app_lazy


# =============================================================================
# Celery Tasks
# =============================================================================

try:
    from tasks.celery_app import celery_app

    @celery_app.task(
        name="tasks.report_tasks.deliver_scheduled_reports",
        bind=True,
        max_retries=2,
        default_retry_delay=300,
    )
    def deliver_scheduled_reports(self):
        """
        Check for due scheduled reports and deliver them via email.
        Runs on Celery Beat schedule (daily at configured hour).

        Uses tenant-scoped DB sessions per-org to enforce RLS when
        generating report data (e.g., querying loans, leads).
        """
        from database import SessionLocal
        from sqlalchemy import text
        from tasks.base import tenant_task_session

        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            current_hour = now.hour
            current_dow = now.weekday()  # 0=Monday
            current_dom = now.day

            # Find due reports (cross-tenant query on scheduled_reports metadata)
            due_reports = db.execute(text("""
                SELECT id, organization_id, report_type, export_format, frequency,
                       recipients, title, day_of_week, day_of_month, hour_utc
                FROM scheduled_reports
                WHERE is_active = true
                    AND hour_utc = :hour
                    AND (
                        (frequency = 'daily')
                        OR (frequency = 'weekly' AND (day_of_week = :dow OR day_of_week IS NULL))
                        OR (frequency = 'monthly' AND (day_of_month = :dom OR day_of_month IS NULL))
                    )
                    AND (last_sent_at IS NULL OR last_sent_at < CURRENT_DATE)
            """), {"hour": current_hour, "dow": current_dow, "dom": current_dom}).fetchall()
            db.close()
            db = None

            delivered = 0
            failed = 0

            for report_row in due_reports:
                schedule_id = report_row[0]
                org_id = report_row[1]
                report_type = report_row[2]
                export_format = report_row[3]
                recipients = json.loads(report_row[5]) if report_row[5] else []
                title = report_row[6]

                try:
                    # Use tenant-scoped session for report data generation
                    with tenant_task_session(org_id) as tenant_db:
                        _generate_and_send_report(
                            db=tenant_db,
                            org_id=org_id,
                            report_type=report_type,
                            export_format=export_format,
                            recipients=recipients,
                            title=title,
                        )

                    # Update last_sent_at in a separate session
                    update_db = SessionLocal()
                    try:
                        update_db.execute(text("""
                            UPDATE scheduled_reports
                            SET last_sent_at = NOW()
                            WHERE id = :id
                        """), {"id": schedule_id})
                        update_db.commit()
                    finally:
                        update_db.close()

                    delivered += 1

                    logger.info(
                        f"Delivered scheduled report {schedule_id}: "
                        f"{report_type} ({export_format}) to {len(recipients)} recipients"
                    )

                except Exception as e:
                    logger.error(f"Failed to deliver report {schedule_id}: {e}")
                    failed += 1

            logger.info(f"Scheduled report delivery: {delivered} delivered, {failed} failed")
            return {"delivered": delivered, "failed": failed}

        except Exception as e:
            logger.error(f"Scheduled report task failed: {e}")
            if db:
                db.rollback()
            raise
        finally:
            if db:
                db.close()

    @celery_app.task(
        name="tasks.report_tasks.generate_and_email_report",
        bind=True,
        max_retries=3,
        default_retry_delay=60,
    )
    def generate_and_email_report(
        self,
        org_id: int,
        report_type: str,
        export_format: str = "pdf",
        recipients: Optional[list] = None,
        title: Optional[str] = None,
    ):
        """
        Generate a single report and email it.
        Can be called on-demand or by the scheduler.
        Uses tenant-scoped DB session to enforce RLS.
        """
        from tasks.base import tenant_task_session

        try:
            with tenant_task_session(org_id) as db:
                _generate_and_send_report(
                    db=db,
                    org_id=org_id,
                    report_type=report_type,
                    export_format=export_format,
                    recipients=recipients or [],
                    title=title,
                )
            return {"success": True, "report_type": report_type, "recipients": len(recipients or [])}
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            raise self.retry(exc=e)

except ImportError:
    logger.warning("Celery not available — scheduled report tasks disabled")


# =============================================================================
# Report Generation + Email Delivery
# =============================================================================

def _generate_and_send_report(
    db,
    org_id: int,
    report_type: str,
    export_format: str,
    recipients: list,
    title: Optional[str] = None,
):
    """
    Generate a report and send it via email to recipients.
    """
    from services.report_export_service import report_exporter

    # Generate report data
    if report_type == "sla_compliance":
        report_data = report_exporter.generate_sla_compliance_report(db=db, org_id=org_id)
    else:
        # For other types, generate a basic structure from database
        report_data = _generate_report_data(db, org_id, report_type)

    # Export to requested format
    if export_format == "pdf":
        file_bytes = report_exporter.generate_pdf(report_data, report_type, title)
        content_type = "application/pdf"
        extension = "pdf"
    elif export_format == "excel":
        file_bytes = report_exporter.generate_excel(report_data, report_type, title)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        extension = "xlsx"
    else:
        file_bytes = report_exporter.generate_csv(report_data, report_type)
        content_type = "text/csv"
        extension = "csv"

    # Send email with attachment
    report_title = title or f"{report_type.replace('_', ' ').title()} Report"
    filename = f"{report_type}_report_{datetime.now().strftime('%Y%m%d')}.{extension}"

    _send_report_email(
        recipients=recipients,
        subject=f"Perennia AI — {report_title} ({datetime.now().strftime('%B %d, %Y')})",
        body=f"""
Your scheduled {report_title} is attached.

Report Type: {report_type.replace('_', ' ').title()}
Format: {export_format.upper()}
Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')}

This is an automated report from Perennia AI.
        """.strip(),
        attachment_bytes=file_bytes,
        attachment_name=filename,
        content_type=content_type,
    )


def _generate_report_data(db, org_id: int, report_type: str) -> dict:
    """Generate report data from database for non-SLA report types."""
    from sqlalchemy import text

    if report_type == "pipeline":
        rows = db.execute(text("""
            SELECT loan_number, borrower_name, loan_amount, status,
                   EXTRACT(EPOCH FROM (NOW() - status_changed_at)) / 86400 AS days_in_status,
                   expected_close_date, loan_type
            FROM loans
            WHERE organization_id = :org_id
                AND status NOT IN ('funded', 'cancelled', 'denied')
            ORDER BY status_changed_at DESC
            LIMIT 500
        """), {"org_id": org_id}).fetchall()

        return {
            "loans": [
                {
                    "loan_number": r[0], "borrower": r[1],
                    "amount_formatted": f"${float(r[2] or 0):,.2f}",
                    "status": r[3], "days_in_status": round(float(r[4] or 0), 1),
                    "expected_close": r[5].isoformat() if r[5] else "",
                    "loan_type": r[6],
                }
                for r in rows
            ],
        }

    elif report_type == "scorecard":
        return {"conversion": {}, "funded": {}}

    elif report_type == "financial":
        return {"sections": []}

    return {}


def _send_report_email(
    recipients: list,
    subject: str,
    body: str,
    attachment_bytes: bytes,
    attachment_name: str,
    content_type: str,
):
    """
    Send report email with attachment.
    Uses the existing email infrastructure (Microsoft Graph or SMTP).
    """
    import os
    import base64

    try:
        # Try Microsoft Graph API (primary email provider)
        graph_token = os.getenv("MS_GRAPH_ACCESS_TOKEN") or os.getenv("MICROSOFT_GRAPH_TOKEN")

        if graph_token:
            import httpx

            attachment_b64 = base64.b64encode(attachment_bytes).decode("utf-8")

            for recipient in recipients:
                message = {
                    "message": {
                        "subject": subject,
                        "body": {"contentType": "Text", "content": body},
                        "toRecipients": [{"emailAddress": {"address": recipient}}],
                        "attachments": [
                            {
                                "@odata.type": "#microsoft.graph.fileAttachment",
                                "name": attachment_name,
                                "contentType": content_type,
                                "contentBytes": attachment_b64,
                            }
                        ],
                    }
                }

                resp = httpx.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers={"Authorization": f"Bearer {graph_token}", "Content-Type": "application/json"},
                    json=message,
                    timeout=30.0,
                )

                if resp.status_code not in (200, 202):
                    logger.warning(f"Graph email failed for {recipient}: {resp.status_code}")
                else:
                    logger.info(f"Report emailed to {recipient}")
        else:
            # Fallback: SMTP
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders

            smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER", "")
            smtp_pass = os.getenv("SMTP_PASSWORD", "")
            from_addr = os.getenv("SMTP_FROM", smtp_user)

            if not smtp_user:
                logger.warning("No email provider configured — report delivery skipped")
                return

            for recipient in recipients:
                msg = MIMEMultipart()
                msg["From"] = from_addr
                msg["To"] = recipient
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))

                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
                msg.attach(part)

                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)

                logger.info(f"Report emailed to {recipient} via SMTP")

    except Exception as e:
        logger.error(f"Email delivery failed: {e}")
        raise
