"""
agents/tools/outreach_tools.py
Perennia AI — Outreach & Campaign Tools for Aria Voice Agent

@mortgage_tool registrations for bulk SMS campaigns, client segmentation
queries, mortgage review outreach, and mass communication workflows.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sa_text

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    db_session,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Helper: send SMS through compliance chokepoint
# =============================================================================

def _send_sms(to_phone: str, message: str, user_id=None, lead_id=None, organization_id=None):
    """Send a single SMS through the TCPA compliance chokepoint."""
    from telephony.sms import send_sms_verified
    import os

    from_number = os.environ.get("TELNYX_FROM_NUMBER", os.environ.get("TELNYX_PHONE_NUMBER", ""))
    profile_id = os.environ.get("TELNYX_MESSAGING_PROFILE_ID", "")

    return send_sms_verified(
        to=to_phone,
        from_=from_number,
        text=message,
        messaging_profile_id=profile_id,
        user_id=user_id,
        lead_id=lead_id,
        organization_id=organization_id,
    )


# =============================================================================
# Tool: find_clients_for_outreach
# =============================================================================

@mortgage_tool(
    name="find_clients_for_outreach",
    description=(
        "Find clients matching criteria for outreach campaigns. "
        "Can filter by loan stage (funded, active, etc.), days since last contact, "
        "loan type, and more. Returns clients with phone numbers for SMS campaigns."
    ),
    agent_roles=["voice_os", "lead_nurturer", "ai_receptionist", "smart_scheduler"],
    risk_level="LOW",
    parameters={
        "loan_stage": "Filter by loan stage: funded, active, processing, closed, all (default: funded)",
        "days_since_contact": "Minimum days since last contact (default: 0 = all clients)",
        "loan_type": "Filter by loan type: conventional, fha, va, usda, jumbo, all (default: all)",
        "limit": "Maximum number of clients to return (default: 50, max: 200)",
        "has_phone": "Only return clients with phone numbers (default: true)",
        "has_email": "Only return clients with email addresses (default: false)",
    },
)
def find_clients_for_outreach(
    loan_stage: str = "funded",
    days_since_contact: int = 0,
    loan_type: str = "all",
    limit: int = 50,
    has_phone: str = "true",
    has_email: str = "false",
) -> ToolResult:
    """Find clients matching criteria for outreach."""
    limit = min(int(limit), 200)

    # Build WHERE clauses
    conditions = ["l.stage IS NOT NULL"]
    params: Dict[str, Any] = {"limit": limit}

    # Loan stage filter
    stage = str(loan_stage).upper()
    if stage == "FUNDED":
        conditions.append("UPPER(l.stage) = 'FUNDED'")
    elif stage == "ACTIVE":
        conditions.append("UPPER(l.stage) NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY', 'NURTURE')")
    elif stage == "PROCESSING":
        conditions.append("UPPER(l.stage) IN ('PROCESSING', 'SUBMITTED', 'UNDERWRITING', 'UW_RECEIVED')")
    elif stage == "CLOSED":
        conditions.append("UPPER(l.stage) IN ('FUNDED', 'CLEAR_TO_CLOSE', 'CLOSING', 'DOCS', 'DOCS_OUT')")
    elif stage != "ALL":
        conditions.append("UPPER(l.stage) = :stage")
        params["stage"] = stage

    # Days since contact filter
    if int(days_since_contact) > 0:
        conditions.append(
            "(l.last_contact IS NULL OR l.last_contact < NOW() - INTERVAL :days_interval)"
        )
        params["days_interval"] = f"{int(days_since_contact)} days"

    # Loan type filter
    lt = str(loan_type).upper()
    if lt != "ALL":
        conditions.append("UPPER(COALESCE(l.loan_type, '')) = :loan_type")
        params["loan_type"] = lt

    # Phone/email filter
    if str(has_phone).lower() == "true":
        conditions.append("l.phone IS NOT NULL AND l.phone != ''")
    if str(has_email).lower() == "true":
        conditions.append("l.email IS NOT NULL AND l.email != ''")

    where_clause = " AND ".join(conditions)

    clients = execute_query(
        f"""SELECT l.id, l.first_name, l.last_name, l.phone, l.email,
                   l.stage, l.loan_type, l.last_contact, l.created_at
            FROM leads l
            WHERE {where_clause}
            ORDER BY l.last_contact ASC NULLS FIRST
            LIMIT :limit""",
        params,
    )

    if not clients:
        return ToolResult.no_data(
            f"No clients found matching criteria: stage={loan_stage}, "
            f"days_since_contact={days_since_contact}, loan_type={loan_type}"
        )

    formatted = []
    for c in clients:
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        formatted.append({
            "id": c.get("id"),
            "name": name,
            "phone": c.get("phone", ""),
            "email": c.get("email", ""),
            "stage": c.get("stage", ""),
            "loan_type": c.get("loan_type", ""),
            "last_contact": str(c.get("last_contact_date", "Never")),
        })

    return ToolResult.success(
        data={"clients": formatted, "count": len(formatted), "criteria": {
            "loan_stage": loan_stage, "days_since_contact": days_since_contact,
            "loan_type": loan_type, "has_phone": has_phone,
        }},
        message=f"Found {len(formatted)} clients matching criteria",
    )


# =============================================================================
# Tool: send_bulk_sms_outreach
# =============================================================================

@mortgage_tool(
    name="send_bulk_sms_outreach",
    description=(
        "Send a bulk SMS message to multiple clients. Personalizes each message "
        "with the client's first name. Enforces TCPA compliance, DNC checks, "
        "and rate limiting. Use find_clients_for_outreach first to get the client list."
    ),
    agent_roles=["voice_os", "lead_nurturer", "ai_receptionist"],
    risk_level="HIGH",
    requires_confirmation=True,
    parameters={
        "client_ids": "Comma-separated list of lead IDs to message",
        "message_template": "Message text. Use {first_name} for personalization. Example: 'Hi {first_name}, it's time for your annual mortgage review!'",
        "campaign_name": "Optional name for this campaign (for tracking)",
        "user_id": "Optional LO user ID sending the campaign",
        "organization_id": "Optional organization ID",
    },
)
def send_bulk_sms_outreach(
    client_ids: str,
    message_template: str,
    campaign_name: str = "Aria Outreach",
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> ToolResult:
    """Send bulk SMS to a list of clients with personalization."""
    if not client_ids or not message_template:
        return ToolResult.error("client_ids and message_template are required")

    # Parse client IDs
    try:
        ids = [int(x.strip()) for x in str(client_ids).split(",") if x.strip()]
    except ValueError:
        return ToolResult.error("client_ids must be comma-separated integers")

    if len(ids) > 200:
        return ToolResult.error("Maximum 200 recipients per campaign")

    if len(ids) == 0:
        return ToolResult.error("No client IDs provided")

    # Look up client details
    placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
    id_params = {f"id_{i}": cid for i, cid in enumerate(ids)}
    clients = execute_query(
        f"""SELECT id, first_name, last_name, phone, email
            FROM leads
            WHERE id IN ({placeholders})
              AND phone IS NOT NULL AND phone != ''""",
        id_params,
    )

    if not clients:
        return ToolResult.no_data("No clients found with phone numbers for the given IDs")

    # Send messages with rate limiting
    sent = 0
    failed = 0
    skipped = 0
    results = []

    _org_id = int(organization_id) if organization_id else None
    _user_id = int(user_id) if user_id else None

    for client in clients:
        first_name = client.get("first_name", "there")
        phone = client.get("phone", "")
        lead_id = client.get("id")

        if not phone:
            skipped += 1
            continue

        # Personalize message
        personalized = message_template.replace("{first_name}", first_name)
        personalized = personalized.replace("{name}", f"{first_name} {client.get('last_name', '')}".strip())

        try:
            result = _send_sms(
                to_phone=phone,
                message=personalized,
                user_id=_user_id,
                lead_id=lead_id,
                organization_id=_org_id,
            )
            if result.get("status") == "sent":
                sent += 1
                results.append({"lead_id": lead_id, "name": first_name, "status": "sent"})
            elif result.get("status") == "blocked":
                skipped += 1
                results.append({"lead_id": lead_id, "name": first_name, "status": "blocked", "reason": result.get("reason", "")})
            else:
                failed += 1
                results.append({"lead_id": lead_id, "name": first_name, "status": "failed"})
        except Exception as e:
            failed += 1
            results.append({"lead_id": lead_id, "name": first_name, "status": "error", "error": str(e)})
            logger.error("Bulk SMS send failed for lead %s: %s", lead_id, e)

        # Rate limit: 150ms between messages (10DLC compliance)
        time.sleep(0.15)

    # Log campaign
    try:
        with db_session() as db:
            db.execute(sa_text("""
                INSERT INTO sms_campaign_records
                (id, name, status, total_recipients, sent_count, failed_count,
                 message_template, created_at)
                VALUES (:id, :name, 'completed', :total, :sent, :failed,
                        :template, NOW())
                ON CONFLICT DO NOTHING
            """), {
                "id": str(uuid.uuid4()),
                "name": campaign_name,
                "total": len(clients),
                "sent": sent,
                "failed": failed,
                "template": message_template[:500],
            })
    except Exception as e:
        logger.warning("Campaign record save failed: %s", e)

    return ToolResult.success(
        data={
            "campaign_name": campaign_name,
            "total_recipients": len(clients),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "results": results[:20],  # First 20 for readback
        },
        message=f"Campaign '{campaign_name}': {sent} sent, {failed} failed, {skipped} skipped out of {len(clients)} recipients",
    )


# =============================================================================
# Tool: send_mortgage_review_outreach
# =============================================================================

@mortgage_tool(
    name="send_mortgage_review_outreach",
    description=(
        "Send SMS outreach to funded/closed clients inviting them to schedule "
        "an annual mortgage review. Automatically finds clients who haven't been "
        "contacted recently and sends a personalized scheduling message."
    ),
    agent_roles=["voice_os", "lead_nurturer", "ai_receptionist", "smart_scheduler"],
    risk_level="HIGH",
    requires_confirmation=True,
    parameters={
        "days_since_contact": "Minimum days since last contact (default: 90)",
        "limit": "Maximum number of clients to reach out to (default: 25)",
        "lo_name": "Loan officer's name for the message",
        "custom_message": "Optional custom message override. Use {first_name} for personalization",
        "user_id": "Optional LO user ID",
        "organization_id": "Optional organization ID",
    },
)
def send_mortgage_review_outreach(
    days_since_contact: int = 90,
    limit: int = 25,
    lo_name: str = "",
    custom_message: str = "",
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> ToolResult:
    """Find funded clients and send mortgage review scheduling SMS."""
    limit = min(int(limit), 100)

    # Find funded clients not contacted recently
    clients = execute_query(
        """SELECT id, first_name, last_name, phone, email,
                  loan_type, last_contact_date
           FROM leads
           WHERE UPPER(stage) IN ('FUNDED', 'CLEAR_TO_CLOSE')
             AND phone IS NOT NULL AND phone != ''
             AND (last_contact_date IS NULL
                  OR last_contact_date < NOW() - INTERVAL :days_interval)
           ORDER BY last_contact_date ASC NULLS FIRST
           LIMIT :limit""",
        {"days_interval": f"{int(days_since_contact)} days", "limit": limit},
    )

    if not clients:
        return ToolResult.no_data(
            f"No funded clients found who haven't been contacted in {days_since_contact}+ days"
        )

    # Build message template
    if custom_message:
        template = custom_message
    else:
        lo_part = f" with {lo_name}" if lo_name else ""
        template = (
            "Hi {first_name}! This is Aria from Perennia AI"
            f"{lo_part}. It's time for your annual mortgage review — "
            "rates and options may have changed since we last spoke. "
            "Would you like to schedule a quick call this week? "
            "Just reply with a day and time that works!"
        )

    # Send messages
    sent = 0
    failed = 0
    skipped = 0
    _org_id = int(organization_id) if organization_id else None
    _user_id = int(user_id) if user_id else None

    for client in clients:
        first_name = client.get("first_name", "there")
        phone = client.get("phone", "")
        lead_id = client.get("id")

        if not phone:
            skipped += 1
            continue

        personalized = template.replace("{first_name}", first_name)
        personalized = personalized.replace("{name}", f"{first_name} {client.get('last_name', '')}".strip())

        try:
            result = _send_sms(
                to_phone=phone,
                message=personalized,
                user_id=_user_id,
                lead_id=lead_id,
                organization_id=_org_id,
            )
            if result.get("status") == "sent":
                sent += 1

                # Create an active SMS AI conversation for auto-reply
                try:
                    conv_id = str(uuid.uuid4())
                    phone_e164 = phone if phone.startswith("+") else ("+" + "".join(c for c in phone if c.isdigit()))
                    with db_session() as db:
                        db.execute(sa_text("""
                            INSERT INTO sms_ai_conversations
                            (id, phone_number, lead_id, organization_id, status,
                             current_stage, context_data, last_message_at, message_count,
                             created_at)
                            VALUES (:id, :phone, :lead_id, :org_id, 'active',
                                    'scheduling', CAST(:ctx AS jsonb), NOW(), 1,
                                    NOW())
                            ON CONFLICT DO NOTHING
                        """), {
                            "id": conv_id,
                            "phone": phone_e164,
                            "lead_id": lead_id,
                            "org_id": _org_id,
                            "ctx": f'{{"borrower_name": "{first_name}", "lo_name": "{lo_name}", "appointment_type": "mortgage_review"}}',
                        })
                        db.execute(sa_text("""
                            INSERT INTO sms_ai_conversation_messages
                            (id, conversation_id, direction, content, ai_generated, created_at)
                            VALUES (:id, :conv_id, 'outbound', :content, true, NOW())
                            ON CONFLICT DO NOTHING
                        """), {
                            "id": str(uuid.uuid4()),
                            "conv_id": conv_id,
                            "content": personalized,
                        })
                except Exception as e:
                    logger.warning("Mortgage review conversation record failed for lead %s: %s", lead_id, e)
            elif result.get("status") == "blocked":
                skipped += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.error("Mortgage review SMS failed for lead %s: %s", lead_id, e)

        time.sleep(0.15)  # 10DLC rate limit

    return ToolResult.success(
        data={
            "campaign": "Annual Mortgage Review",
            "total_clients_found": len(clients),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        },
        message=(
            f"Mortgage review outreach: {sent} SMS sent to funded clients "
            f"not contacted in {days_since_contact}+ days. "
            f"Clients who reply will get auto-responses from Aria to schedule."
        ),
    )


# =============================================================================
# Tool: send_bulk_email_outreach
# =============================================================================

@mortgage_tool(
    name="send_bulk_email_outreach",
    description=(
        "Send a personalized email to multiple clients. Personalizes each email "
        "with the client's first name. Use {first_name} in subject or body. "
        "Sends via Microsoft Graph if the LO has a connected Outlook account."
    ),
    agent_roles=["voice_os", "lead_nurturer", "email_intelligence"],
    risk_level="HIGH",
    requires_confirmation=True,
    parameters={
        "client_ids": "Comma-separated list of lead IDs",
        "subject": "Email subject line. Use {first_name} for personalization",
        "body_template": "Email body. Use {first_name} for personalization",
        "user_id": "LO user ID sending the emails",
        "organization_id": "Organization ID for tenant scoping",
    },
)
def send_bulk_email_outreach(
    client_ids: str,
    subject: str,
    body_template: str,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> ToolResult:
    """Send personalized emails to a list of clients."""
    if not client_ids or not subject or not body_template:
        return ToolResult.error("client_ids, subject, and body_template are required")

    try:
        ids = [int(x.strip()) for x in str(client_ids).split(",") if x.strip()]
    except ValueError:
        return ToolResult.error("client_ids must be comma-separated integers")

    if len(ids) > 200:
        return ToolResult.error("Maximum 200 recipients per campaign")
    if not ids:
        return ToolResult.error("No client IDs provided")

    placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
    id_params = {f"id_{i}": cid for i, cid in enumerate(ids)}
    clients = execute_query(
        f"""SELECT id, first_name, last_name, email
            FROM leads
            WHERE id IN ({placeholders})
              AND email IS NOT NULL AND email != ''""",
        id_params,
    )

    if not clients:
        return ToolResult.no_data("No clients found with valid email addresses")

    sent = 0
    failed = 0
    skipped = 0
    _uid = int(user_id) if user_id else None

    for client in clients:
        first = client.get("first_name", "there")
        email = client.get("email", "")
        if not email:
            skipped += 1
            continue

        personalized_subject = subject.replace("{first_name}", first)
        personalized_body = body_template.replace("{first_name}", first)

        try:
            from agents.tools.email_intel import send_email as _send_email_tool
            result = _send_email_tool(
                to_email=email,
                subject=personalized_subject,
                body=personalized_body,
                contact_id=str(client["id"]),
                contact_type="lead",
                user_id=_uid,
            )
            if hasattr(result, "success") and result.success:
                sent += 1
            else:
                failed += 1
        except Exception as e:
            logger.warning("Bulk email send failed for lead %s: %s", client["id"], e)
            failed += 1

        time.sleep(0.2)

    return ToolResult.success(
        data={"sent": sent, "failed": failed, "skipped": skipped, "total": len(clients)},
        message=f"Email campaign complete: {sent} sent, {failed} failed, {skipped} skipped",
    )


# =============================================================================
# Tool: send_calendar_invite_email
# =============================================================================

@mortgage_tool(
    name="send_calendar_invite_email",
    description=(
        "Send a calendar invite email with an ICS attachment to one or more "
        "email addresses. Used after confirming an appointment to ensure "
        "it appears on the recipient's calendar."
    ),
    agent_roles=["voice_os", "smart_scheduler", "ai_receptionist"],
    risk_level="MEDIUM",
    parameters={
        "emails": "Comma-separated email addresses to send the invite to",
        "date": "Appointment date in YYYY-MM-DD format",
        "appointment_time": "Appointment time in HH:MM format (24-hour)",
        "appointment_type": "Type: consultation, mortgage_review, document_review, closing_prep, callback",
        "borrower_name": "Name of the borrower/attendee",
        "lo_name": "Loan officer's name",
        "duration_minutes": "Duration in minutes (default: 30)",
    },
)
def send_calendar_invite_email(
    emails: str,
    date: str,
    appointment_time: str = "",
    appointment_type: str = "consultation",
    borrower_name: str = "there",
    lo_name: str = "your loan officer",
    duration_minutes: int = 30,
) -> ToolResult:
    """Send calendar invite email with ICS attachment."""
    appt_time = appointment_time
    if not emails or not date or not appt_time:
        return ToolResult.error("emails, date, and time are required")

    email_list = [e.strip() for e in str(emails).split(",") if "@" in e.strip()]
    if not email_list:
        return ToolResult.error("No valid email addresses provided")

    # Parse datetime
    try:
        from datetime import timezone as tz
        start_dt = datetime.strptime(f"{date} {appt_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz.utc)
    except ValueError:
        return ToolResult.error(f"Invalid date/time format: {date} {appt_time}. Use YYYY-MM-DD HH:MM")

    # Generate ICS
    try:
        from services.ics_generator import generate_ics_content

        appt_label = appointment_type.replace("_", " ").title()
        ics_title = f"{appt_label} with {lo_name}"
        ics_content = generate_ics_content(
            appointment_title=ics_title,
            start_datetime=start_dt,
            duration_minutes=int(duration_minutes),
            attendee_email=email_list[0],
            attendee_name=borrower_name,
            organizer_email="aria@perenniaai.com",
            organizer_name=f"Aria (on behalf of {lo_name})",
            description=(
                f"Scheduled by Aria AI assistant.\n"
                f"Type: {appt_label}\n"
                f"Attendee: {borrower_name}"
            ),
        )
    except Exception as e:
        return ToolResult.error(f"ICS generation failed: {e}")

    # Send via SMTP (reliable path)
    import os
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_pass:
        return ToolResult.error("SMTP credentials not configured — cannot send email")

    email_html = (
        f"<h2>Appointment Confirmed</h2>"
        f"<p>Hi {borrower_name},</p>"
        f"<p>Your <strong>{appt_label}</strong> with "
        f"<strong>{lo_name}</strong> has been confirmed.</p>"
        f"<p><strong>Date:</strong> {start_dt.strftime('%A, %B %d, %Y')}<br>"
        f"<strong>Time:</strong> {start_dt.strftime('%I:%M %p')}</p>"
        f"<p>A calendar invite is attached. Please add it to your calendar.</p>"
        f"<p>If you need to reschedule, just reply to the text message "
        f"thread or call us.</p>"
        f"<br><p>Best regards,<br>Aria — Perennia AI</p>"
    )

    sent_to = []
    failed_to = []
    for addr in email_list:
        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = f"Aria — Perennia AI <{smtp_user}>"
            msg["To"] = addr
            msg["Subject"] = f"Appointment Confirmed: {ics_title}"
            msg.attach(MIMEText(email_html, "html"))

            ics_part = MIMEBase("text", "calendar", method="REQUEST")
            ics_part.set_payload(ics_content.encode("utf-8"))
            encoders.encode_base64(ics_part)
            ics_part.add_header("Content-Disposition", "attachment", filename="appointment.ics")
            msg.attach(ics_part)

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, addr, msg.as_string())
            sent_to.append(addr)
        except Exception as e:
            failed_to.append({"email": addr, "error": str(e)})
            logger.error("Calendar invite email to %s failed: %s", addr, e)

    if not sent_to:
        return ToolResult.error(f"Failed to send calendar invite to all recipients: {failed_to}")

    return ToolResult.success(
        data={
            "sent_to": sent_to,
            "failed": failed_to,
            "appointment": {
                "title": ics_title,
                "date": date,
                "time": appt_time,
                "duration": duration_minutes,
                "type": appointment_type,
            },
        },
        message=f"Calendar invite sent to {', '.join(sent_to)}",
    )
