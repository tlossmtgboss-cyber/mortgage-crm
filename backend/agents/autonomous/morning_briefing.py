"""
Morning Pipeline Briefing Agent

Runs at 7:00 AM ET for each organization.
Analyzes every LO's pipeline, drafts a priority-ordered daily plan,
and delivers it via email before they open the app.

This single feature does more for LO productivity than 50 on-demand tools.
"""

import logging
import os
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytz
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


@autonomous_agent(
    name="morning_pipeline_briefing",
    description="Daily pipeline analysis and priority plan for each LO",
    frequency=AgentFrequency.DAILY_7AM,
    max_runtime_seconds=180,
)
def morning_pipeline_briefing(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Analyze pipeline for all LOs in the org, generate priority plans, deliver via email."""

    # Get all active LOs in this organization
    loan_officers = _get_active_loan_officers(db, organization_id)
    if not loan_officers:
        return {"summary": "No active loan officers found", "actions_taken": 0, "notifications_sent": 0}

    actions_taken = 0
    notifications_sent = 0
    lo_summaries = []

    for lo in loan_officers:
        try:
            # Gather pipeline data for this LO
            pipeline = _get_lo_pipeline(db, lo["id"])
            tasks = _get_pending_tasks(db, lo["id"])
            stale_leads = _get_stale_leads(db, lo["id"])
            expiring_locks = _get_expiring_locks(db, lo["id"])
            upcoming_appointments = _get_todays_appointments(db, lo["id"])
            compliance_alerts = _get_open_compliance_alerts(db, lo["id"])

            # Build the priority plan
            priority_items = _build_priority_plan(
                pipeline=pipeline,
                tasks=tasks,
                stale_leads=stale_leads,
                expiring_locks=expiring_locks,
                appointments=upcoming_appointments,
                compliance_alerts=compliance_alerts,
            )
            actions_taken += 1

            # Format and send the briefing email
            if lo.get("email") and priority_items:
                html = _format_briefing_email(
                    lo_name=lo["name"],
                    priority_items=priority_items,
                    pipeline=pipeline,
                    appointments=upcoming_appointments,
                    org_timezone=org_timezone,
                )

                sent = _send_briefing(
                    db=db,
                    lo_id=lo["id"],
                    lo_email=lo["email"],
                    lo_name=lo["name"],
                    organization_id=organization_id,
                    html_content=html,
                    priority_count=len(priority_items),
                )
                if sent:
                    notifications_sent += 1

            lo_summaries.append({
                "lo_id": lo["id"],
                "lo_name": lo["name"],
                "pipeline_count": pipeline["active_count"],
                "priority_items": len(priority_items),
            })

        except Exception as e:
            logger.error(f"Morning briefing failed for LO {lo['id']}: {e}")

    return {
        "summary": f"Briefed {notifications_sent}/{len(loan_officers)} LOs",
        "actions_taken": actions_taken,
        "notifications_sent": notifications_sent,
        "lo_summaries": lo_summaries,
    }


# =============================================================================
# DATA GATHERING
# =============================================================================

def _get_active_loan_officers(db: Session, org_id: int) -> List[Dict]:
    """Get all active LOs who should receive briefings."""
    result = db.execute(text("""
        SELECT u.id, u.first_name, u.last_name, u.email,
               COALESCE(us.daily_briefing_enabled, true) as briefing_enabled
        FROM users u
        LEFT JOIN user_settings us ON us.user_id = u.id
        WHERE u.organization_id = :org_id
          AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'admin', 'branch_manager')
    """), {"org_id": org_id})

    return [
        {
            "id": row[0],
            "name": f"{row[1] or ''} {row[2] or ''}".strip(),
            "email": row[3],
        }
        for row in result.fetchall()
        if row[4]  # briefing_enabled
    ]


def _get_lo_pipeline(db: Session, lo_id) -> Dict[str, Any]:
    """Get pipeline summary for a single LO."""
    result = db.execute(text("""
        SELECT
            COUNT(*) as active_count,
            COALESCE(SUM(amount), 0) as total_volume,
            COUNT(CASE WHEN stage IN ('CTC', 'CLEAR_TO_CLOSE', 'DOCS', 'DOCS_OUT', 'CLOSING') THEN 1 END) as closing_soon,
            COUNT(CASE WHEN stage IN ('UNDERWRITING', 'UW_RECEIVED', 'CONDITIONAL_APPROVAL') THEN 1 END) as in_underwriting,
            COUNT(CASE WHEN stage = 'APPLICATION' THEN 1 END) as new_applications,
            COUNT(CASE WHEN stage IN ('PROCESSING', 'SUBMITTED') THEN 1 END) as in_processing
        FROM loans
        WHERE loan_officer_id = :lo_id
          AND stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
    """), {"lo_id": str(lo_id)})

    row = result.fetchone()
    return {
        "active_count": row[0] or 0,
        "total_volume": float(row[1] or 0),
        "closing_soon": row[2] or 0,
        "in_underwriting": row[3] or 0,
        "new_applications": row[4] or 0,
        "in_processing": row[5] or 0,
    }


def _get_pending_tasks(db: Session, lo_id) -> List[Dict]:
    """Get tasks due today or overdue."""
    result = db.execute(text("""
        SELECT t.id, t.title, t.due_date, t.priority,
               l.borrower_name, l.loan_number
        FROM tasks t
        LEFT JOIN loans l ON l.id = t.loan_id
        WHERE t.assigned_to_id = :lo_id
          AND t.status IN ('pending', 'in_progress')
          AND (t.due_date IS NULL OR t.due_date <= CURRENT_DATE + 1)
        ORDER BY
            CASE t.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
            t.due_date ASC NULLS LAST
        LIMIT 15
    """), {"lo_id": str(lo_id)})

    return [
        {
            "id": row[0],
            "title": row[1],
            "due_date": row[2],
            "priority": row[3],
            "borrower": row[4],
            "loan_number": row[5],
        }
        for row in result.fetchall()
    ]


def _get_stale_leads(db: Session, lo_id) -> List[Dict]:
    """Get leads with no contact in 3+ days that need follow-up."""
    result = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.stage, l.ai_score,
               l.last_contact, l.loan_purpose,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.last_contact)) as days_stale
        FROM leads l
        WHERE l.owner_id = :lo_id
          AND l.stage NOT IN ('Closed', 'Dead', 'Disqualified', 'Converted')
          AND (l.last_contact IS NULL OR l.last_contact < CURRENT_TIMESTAMP - INTERVAL '3 days')
        ORDER BY l.ai_score DESC NULLS LAST
        LIMIT 10
    """), {"lo_id": str(lo_id)})

    return [
        {
            "id": row[0],
            "name": f"{row[1] or ''} {row[2] or ''}".strip(),
            "stage": row[3],
            "score": row[4],
            "last_contact": row[5],
            "loan_purpose": row[6],
            "days_stale": int(row[7]) if row[7] else None,
        }
        for row in result.fetchall()
    ]


def _get_expiring_locks(db: Session, lo_id) -> List[Dict]:
    """Get rate locks expiring within 7 days."""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.rate,
               l.lock_expiration_date,
               (l.lock_expiration_date - CURRENT_DATE) as days_remaining
        FROM loans l
        WHERE l.loan_officer_id = :lo_id
          AND l.lock_expiration_date IS NOT NULL
          AND l.lock_expiration_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7
          AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
        ORDER BY l.lock_expiration_date ASC
    """), {"lo_id": str(lo_id)})

    return [
        {
            "loan_number": row[1],
            "borrower": row[2],
            "rate": float(row[3]) if row[3] else None,
            "expires": row[4],
            "days_remaining": int(row[5]) if row[5] else None,
        }
        for row in result.fetchall()
    ]


def _get_todays_appointments(db: Session, lo_id) -> List[Dict]:
    """Get today's appointments."""
    result = db.execute(text("""
        SELECT sa.id, sa.title, sa.start_time, sa.end_time,
               sa.appointment_type, sa.status,
               l.first_name || ' ' || l.last_name as lead_name
        FROM scheduler_appointments sa
        LEFT JOIN leads l ON l.id = sa.lead_id
        WHERE sa.user_id = :lo_id
          AND sa.start_time >= CURRENT_DATE
          AND sa.start_time < CURRENT_DATE + 1
          AND sa.status NOT IN ('cancelled', 'no_show')
        ORDER BY sa.start_time ASC
    """), {"lo_id": str(lo_id)})

    return [
        {
            "id": row[0],
            "title": row[1],
            "start_time": row[2],
            "end_time": row[3],
            "type": row[4],
            "status": row[5],
            "lead_name": row[6],
        }
        for row in result.fetchall()
    ]


def _get_open_compliance_alerts(db: Session, lo_id) -> List[Dict]:
    """Get open compliance alerts for the LO's loans."""
    result = db.execute(text("""
        SELECT ca.id, ca.alert_type, ca.severity, ca.title,
               ca.deadline_date, l.loan_number, l.borrower_name
        FROM compliance_alerts ca
        JOIN loans l ON l.id = ca.loan_id
        WHERE l.loan_officer_id = :lo_id
          AND ca.status = 'open'
        ORDER BY
            CASE ca.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,
            ca.deadline_date ASC NULLS LAST
        LIMIT 5
    """), {"lo_id": str(lo_id)})

    return [
        {
            "type": row[1],
            "severity": row[2],
            "title": row[3],
            "deadline": row[4],
            "loan_number": row[5],
            "borrower": row[6],
        }
        for row in result.fetchall()
    ]


# =============================================================================
# PRIORITY PLAN BUILDER
# =============================================================================

def _build_priority_plan(
    pipeline: Dict,
    tasks: List[Dict],
    stale_leads: List[Dict],
    expiring_locks: List[Dict],
    appointments: List[Dict],
    compliance_alerts: List[Dict],
) -> List[Dict[str, Any]]:
    """Build a priority-ordered daily plan.

    Priority hierarchy:
    1. COMPLIANCE: Alerts with deadlines (legal exposure)
    2. LOCKS: Expiring rate locks (financial exposure)
    3. CLOSING: Loans close to funding (revenue)
    4. APPOINTMENTS: Today's scheduled meetings
    5. TASKS: Overdue and due-today tasks
    6. LEADS: Stale high-score leads (pipeline growth)
    """
    items = []

    # 1. Compliance alerts (critical first)
    for alert in compliance_alerts:
        urgency = "critical" if alert["severity"] in ("critical", "high") else "high"
        items.append({
            "priority": 1,
            "urgency": urgency,
            "category": "Compliance",
            "title": alert["title"],
            "detail": f"{alert['borrower']} ({alert['loan_number']})",
            "deadline": str(alert["deadline"]) if alert["deadline"] else None,
            "action": "Review and resolve compliance alert",
        })

    # 2. Expiring rate locks
    for lock in expiring_locks:
        days = lock["days_remaining"]
        urgency = "critical" if days and days <= 2 else "high"
        items.append({
            "priority": 2,
            "urgency": urgency,
            "category": "Rate Lock",
            "title": f"Lock expires in {days} day{'s' if days != 1 else ''}" if days else "Lock expiring",
            "detail": f"{lock['borrower']} ({lock['loan_number']}) — {lock['rate']}%",
            "action": "Extend lock or push to close",
        })

    # 3. Today's appointments
    for appt in appointments:
        start = appt["start_time"]
        time_str = start.strftime("%-I:%M %p") if start else "TBD"
        items.append({
            "priority": 3,
            "urgency": "medium",
            "category": "Appointment",
            "title": f"{time_str} — {appt['title'] or appt['type'] or 'Meeting'}",
            "detail": appt["lead_name"] or "",
            "action": "Prepare and attend",
        })

    # 4. Overdue/due-today tasks
    for task in tasks[:8]:
        is_overdue = task["due_date"] and task["due_date"] < date.today()
        urgency = "high" if is_overdue or task["priority"] in ("critical", "high") else "medium"
        items.append({
            "priority": 4,
            "urgency": urgency,
            "category": "Task",
            "title": task["title"] or "Untitled task",
            "detail": f"{task['borrower'] or ''} ({task['loan_number'] or ''})".strip(" ()"),
            "action": "Complete task" + (" (OVERDUE)" if is_overdue else ""),
        })

    # 5. Stale leads (high-score first)
    for lead in stale_leads[:5]:
        score_label = f"Score {lead['score']}" if lead["score"] else ""
        days = lead["days_stale"]
        items.append({
            "priority": 5,
            "urgency": "low",
            "category": "Follow Up",
            "title": f"{lead['name']} — {days}d no contact" if days else lead["name"],
            "detail": f"{lead['loan_purpose'] or 'Lead'} {score_label}".strip(),
            "action": "Call or text to re-engage",
        })

    # Sort by priority, then urgency
    urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda x: (x["priority"], urgency_order.get(x["urgency"], 9)))

    return items


# =============================================================================
# EMAIL FORMATTING
# =============================================================================

def _format_briefing_email(
    lo_name: str,
    priority_items: List[Dict],
    pipeline: Dict,
    appointments: List[Dict],
    org_timezone: str,
) -> str:
    """Format the morning briefing as an HTML email."""

    today_str = datetime.now().strftime("%A, %B %-d")
    volume_str = f"${pipeline['total_volume']:,.0f}" if pipeline["total_volume"] else "$0"

    # Build priority items HTML
    items_html = ""
    current_category = None
    for i, item in enumerate(priority_items[:15]):
        if item["category"] != current_category:
            current_category = item["category"]

        urgency_colors = {
            "critical": "#dc2626",
            "high": "#ea580c",
            "medium": "#2563eb",
            "low": "#6b7280",
        }
        color = urgency_colors.get(item["urgency"], "#6b7280")
        urgency_badge = f'<span style="color:{color};font-weight:600;font-size:11px;text-transform:uppercase;">{item["category"]}</span>'

        items_html += f"""
        <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;vertical-align:top;">
                <div style="font-size:11px;margin-bottom:2px;">{urgency_badge}</div>
                <div style="font-size:14px;font-weight:500;color:#111827;">{item['title']}</div>
                <div style="font-size:12px;color:#6b7280;margin-top:2px;">{item.get('detail', '')}</div>
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;vertical-align:top;text-align:right;">
                <span style="font-size:12px;color:#6b7280;">{item.get('action', '')}</span>
            </td>
        </tr>
        """

    appt_count = len(appointments)
    appt_text = f"{appt_count} appointment{'s' if appt_count != 1 else ''}" if appt_count else "No appointments"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:20px;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e40af 0%,#7c3aed 100%);color:white;padding:24px;border-radius:12px 12px 0 0;">
    <div style="font-size:13px;opacity:0.8;margin-bottom:4px;">Good morning, {lo_name.split()[0] if lo_name else 'there'}</div>
    <div style="font-size:22px;font-weight:700;">{today_str}</div>
    <div style="font-size:13px;opacity:0.8;margin-top:8px;">Your daily pipeline briefing from Perennia AI</div>
  </div>

  <!-- Pipeline Snapshot -->
  <div style="background:white;padding:20px;border-bottom:1px solid #e5e7eb;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="text-align:center;padding:8px;">
          <div style="font-size:28px;font-weight:800;color:#111827;">{pipeline['active_count']}</div>
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;">Active Loans</div>
        </td>
        <td style="text-align:center;padding:8px;">
          <div style="font-size:28px;font-weight:800;color:#111827;">{volume_str}</div>
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;">Pipeline Volume</div>
        </td>
        <td style="text-align:center;padding:8px;">
          <div style="font-size:28px;font-weight:800;color:#059669;">{pipeline['closing_soon']}</div>
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;">Closing Soon</div>
        </td>
        <td style="text-align:center;padding:8px;">
          <div style="font-size:28px;font-weight:800;color:#2563eb;">{appt_count}</div>
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;">Appointments</div>
        </td>
      </tr>
    </table>
  </div>

  <!-- Priority Plan -->
  <div style="background:white;padding:20px 16px;border-radius:0 0 12px 12px;">
    <div style="font-size:16px;font-weight:700;color:#111827;margin-bottom:16px;">
      Today's Priority Plan ({len(priority_items)} items)
    </div>
    <table width="100%" cellpadding="0" cellspacing="0">
      {items_html}
    </table>
  </div>

  <!-- Footer -->
  <div style="text-align:center;padding:20px;font-size:12px;color:#9ca3af;">
    Sent by Perennia AI at {datetime.now().strftime('%-I:%M %p')} ET<br>
    <a href="https://app.perenniaai.com/pipeline" style="color:#6366f1;">Open Pipeline</a> &middot;
    <a href="https://app.perenniaai.com/settings" style="color:#6366f1;">Manage Briefings</a>
  </div>

</div>
</body>
</html>"""


# =============================================================================
# DELIVERY
# =============================================================================

def _send_briefing(
    db: Session,
    lo_id,
    lo_email: str,
    lo_name: str,
    organization_id: int,
    html_content: str,
    priority_count: int,
) -> bool:
    """Send the briefing email via Microsoft Graph (from LO's Outlook) or SMTP fallback."""

    today_str = datetime.now().strftime("%A, %B %-d")
    subject = f"Your Pipeline Briefing — {today_str} ({priority_count} priorities)"

    # Try Microsoft Graph first (sends from LO's own email, more professional)
    try:
        from services.dre_helpers import send_email_via_graph
        sent = send_email_via_graph(
            db=db,
            user_id=lo_id,
            to_email=lo_email,
            subject=subject,
            html_body=html_content,
        )
        if sent:
            logger.info(f"Morning briefing sent via Graph to {lo_email}")
            return True
    except Exception as e:
        logger.debug(f"Graph send failed for {lo_email}, trying SMTP: {e}")

    # SMTP fallback
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = os.getenv("SMTP_HOST")
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASS")
        from_email = os.getenv("FROM_EMAIL", "briefing@perenniaai.com")

        if not all([smtp_host, smtp_user, smtp_pass]):
            logger.warning("SMTP not configured, skipping briefing email")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Perennia AI <{from_email}>"
        msg["To"] = lo_email
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_host, 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        logger.info(f"Morning briefing sent via SMTP to {lo_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send briefing to {lo_email}: {e}")
        return False
