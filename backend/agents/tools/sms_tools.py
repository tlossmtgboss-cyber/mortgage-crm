"""
agents/tools/sms_tools.py
Perennia AI — SMS Tools for Aria Voice Agent

@mortgage_tool registrations for SMS sending, conversation retrieval,
and scheduling-via-SMS workflows.
"""

import json
import logging
import os
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

# Telnyx config — matches CommunicationTools and SMSClient
TELNYX_FROM_NUMBER = os.environ.get("TELNYX_FROM_NUMBER", os.environ.get("TELNYX_PHONE_NUMBER", ""))
TELNYX_MESSAGING_PROFILE = os.environ.get("TELNYX_MESSAGING_PROFILE_ID", "")


def _normalize_e164(phone: str) -> str:
    """Normalize phone to E.164 format."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if digits.startswith("+"):
        return digits
    return "+" + digits


def _send_telnyx_sms(
    to_phone: str,
    message: str,
    organization_id: Optional[int] = None,
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Send SMS via the centralized compliance chokepoint.

    Routes through telephony.sms.send_sms_verified() which enforces
    TCPA/DNC compliance, appends STOP footer, and logs delivery.
    """
    from telephony.sms import send_sms_verified

    result = send_sms_verified(
        to=to_phone,
        from_=TELNYX_FROM_NUMBER,
        text=message,
        messaging_profile_id=TELNYX_MESSAGING_PROFILE or None,
        user_id=user_id,
        lead_id=lead_id,
        organization_id=organization_id,
    )

    if result.get("status") == "sent":
        return {
            "success": True,
            "message_id": result.get("id", ""),
            "to": _normalize_e164(to_phone),
            "status": "sent",
        }
    elif result.get("status") == "blocked":
        return {"success": False, "error": f"Blocked: {result.get('reason', 'compliance')}"}
    else:
        return {"success": False, "error": result.get("reason", "SMS send failed")}


# =============================================================================
# Tool: send_sms_message
# =============================================================================

@mortgage_tool(
    name="send_sms_message",
    description="Send an SMS text message to a phone number via Telnyx. Records the message for conversation tracking.",
    agent_roles=["voice_os", "ai_receptionist", "lead_nurturer", "smart_scheduler"],
    risk_level="MEDIUM",
    parameters={
        "to_phone": "Recipient phone number (any format, normalized to E.164)",
        "message": "Text message body to send",
        "lead_id": "Optional lead ID for CRM tracking",
        "user_id": "Optional user/LO ID sending the message",
        "organization_id": "Optional organization ID for tenant isolation",
    },
)
def send_sms_message(
    to_phone: str,
    message: str,
    lead_id: Optional[str] = None,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> ToolResult:
    """Send SMS via Telnyx and record in the conversation panel."""
    if not to_phone or not message:
        return ToolResult.error("Both to_phone and message are required")

    if len(message) > 1600:
        return ToolResult.error("Message too long (max 1600 characters)")

    _org_id = int(organization_id) if organization_id else None
    _user_id = int(user_id) if user_id else None
    _lead_id = int(lead_id) if lead_id else None

    result = _send_telnyx_sms(
        to_phone, message,
        organization_id=_org_id, user_id=_user_id, lead_id=_lead_id,
    )

    if not result.get("success"):
        return ToolResult.error(f"SMS send failed: {result.get('error', 'Unknown error')}")

    # Record in sms_panel_messages for conversation tracking
    try:
        import uuid
        to_e164 = _normalize_e164(to_phone)
        phone_digits = to_e164

        with db_session() as db:
            db.execute(
                sa_text("""INSERT INTO sms_panel_messages
                   (id, phone, contact_id, organization_id, direction, body,
                    sender_name, sender_role, status,
                    telnyx_message_id, created_at)
                   VALUES (:id, :phone, :contact_id, :org_id, 'outbound', :body,
                           'Aria', 'ai_assistant', 'sent',
                           :msg_id, NOW())
                   ON CONFLICT DO NOTHING"""),
                {
                    "id": result.get("message_id", "") or str(uuid.uuid4()),
                    "phone": phone_digits,
                    "contact_id": lead_id or "",
                    "org_id": int(organization_id) if organization_id else None,
                    "body": message,
                    "msg_id": result.get("message_id", ""),
                },
            )
    except Exception as e:
        logger.warning(f"SMS sent but panel record failed: {e}")

    return ToolResult.success(
        data={
            "message_id": result.get("message_id", ""),
            "to": result.get("to", to_phone),
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "status": "sent",
        },
        message=f"SMS sent to {to_phone}",
    )


# =============================================================================
# Tool: get_sms_conversation_history
# =============================================================================

@mortgage_tool(
    name="get_sms_conversation_history",
    description="Retrieve SMS conversation history for a phone number. Returns recent messages (inbound + outbound) in chronological order.",
    agent_roles=["voice_os", "ai_receptionist", "lead_nurturer", "smart_scheduler"],
    risk_level="LOW",
    parameters={
        "phone_number": "Phone number to look up conversation for",
        "limit": "Maximum number of messages to return (default 20)",
    },
)
def get_sms_conversation_history(
    phone_number: str,
    limit: int = 20,
) -> ToolResult:
    """Get SMS conversation thread for a phone number."""
    if not phone_number:
        return ToolResult.error("phone_number is required")

    digits = "".join(c for c in phone_number if c.isdigit())
    if len(digits) >= 10:
        digits = digits[-10:]
    phone_pattern = f"%{digits}"

    # Query panel messages (two-way)
    messages = execute_query(
        """SELECT id, direction, body, sender_name, status, created_at,
                  telnyx_message_id
           FROM sms_panel_messages
           WHERE phone LIKE :pattern
           ORDER BY created_at DESC
           LIMIT :limit""",
        {"pattern": phone_pattern, "limit": limit},
    )

    if not messages:
        # Fallback: check delivery log for outbound-only history
        try:
            messages = execute_query(
                """SELECT telnyx_message_id as id, 'outbound' as direction,
                          message_body as body, 'LO' as sender_name,
                          status, sent_at as created_at,
                          telnyx_message_id
                   FROM sms_delivery_log
                   WHERE to_phone LIKE :pattern
                   ORDER BY sent_at DESC
                   LIMIT :limit""",
                {"pattern": phone_pattern, "limit": limit},
            )
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            messages = []

    if not messages:
        return ToolResult.no_data(f"No SMS conversation found for {phone_number}")

    # Format for voice readback
    formatted = []
    for msg in reversed(messages):  # chronological order
        direction = msg.get("direction", "unknown")
        body = msg.get("body", "")
        sender = msg.get("sender_name", "Unknown")
        ts = msg.get("created_at", "")
        formatted.append({
            "direction": direction,
            "from": sender if direction == "outbound" else "Borrower",
            "message": body[:500],
            "timestamp": str(ts),
        })

    return ToolResult.success(
        data={"phone": phone_number, "messages": formatted, "count": len(formatted)},
        message=f"Found {len(formatted)} messages with {phone_number}",
    )


# =============================================================================
# Tool: start_scheduling_sms
# =============================================================================

@mortgage_tool(
    name="start_scheduling_sms",
    description="Initiate an SMS conversation with a borrower to schedule an appointment. Sends the first message proposing times and tracks the conversation. The borrower's reply will be auto-handled by Aria.",
    agent_roles=["smart_scheduler", "voice_os", "ai_receptionist"],
    risk_level="MEDIUM",
    parameters={
        "to_phone": "Borrower's phone number",
        "borrower_name": "Borrower's first name for personalized greeting",
        "lo_name": "Loan officer's name",
        "proposed_times": "Optional comma-separated proposed times (e.g., 'Monday 2pm, Tuesday 10am')",
        "appointment_type": "Type: consultation, document_review, closing_prep, callback",
        "organization_id": "Organization ID for tenant isolation",
        "lead_id": "Optional lead ID for CRM tracking",
        "user_id": "Optional LO user ID for calendar availability lookup",
    },
)
def start_scheduling_sms(
    to_phone: str,
    borrower_name: str,
    lo_name: str = "",
    proposed_times: str = "",
    appointment_type: str = "consultation",
    organization_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> ToolResult:
    """Send initial scheduling SMS and create AI conversation record."""
    if not to_phone or not borrower_name:
        return ToolResult.error("to_phone and borrower_name are required")

    # Build the scheduling message
    greeting = f"Hi {borrower_name}! This is Aria from Perennia AI"
    if lo_name:
        greeting += f" on behalf of {lo_name}"
    greeting += "."

    if proposed_times:
        body = (
            f"{greeting} I'd like to schedule a {appointment_type.replace('_', ' ')} for you. "
            f"Would any of these times work? {proposed_times} "
            f"Just reply with your preferred time, or suggest another that works better!"
        )
    else:
        body = (
            f"{greeting} I'd like to schedule a {appointment_type.replace('_', ' ')} for you. "
            f"What day and time works best for you this week? "
            f"Just text back and we'll get you set up!"
        )

    # Send the SMS via compliance chokepoint
    _org_id = int(organization_id) if organization_id else None
    _lead_id_int = int(lead_id) if lead_id else None
    result = _send_telnyx_sms(to_phone, body, organization_id=_org_id, lead_id=_lead_id_int)
    if not result.get("success"):
        return ToolResult.error(f"Failed to send scheduling SMS: {result.get('error')}")

    # Create AI conversation record for tracking (critical — must persist)
    import uuid
    conv_id = str(uuid.uuid4())
    to_e164 = _normalize_e164(to_phone)
    phone_digits = "".join(c for c in to_e164 if c.isdigit())[-10:]

    try:
        with db_session() as db:
            db.execute(
                sa_text("""INSERT INTO sms_ai_conversations
                   (id, phone_number, lead_id, organization_id, status,
                    current_stage, context_data, last_message_at, message_count, created_at)
                   VALUES (:id, :phone, :lead_id, :org_id, 'active',
                           'scheduling', CAST(:context AS jsonb), NOW(), 1, NOW())
                   ON CONFLICT DO NOTHING"""),
                {
                    "id": conv_id,
                    "phone": to_e164,
                    "lead_id": int(lead_id) if lead_id else None,
                    "org_id": int(organization_id) if organization_id else None,
                    "context": json.dumps({
                        "borrower_name": borrower_name,
                        "lo_name": lo_name,
                        "appointment_type": appointment_type,
                        "proposed_times": proposed_times,
                        "user_id": user_id,
                        "lead_id": lead_id,
                    }),
                },
            )
            db.execute(
                sa_text("""INSERT INTO sms_ai_conversation_messages
                   (id, conversation_id, direction, content, ai_generated, created_at)
                   VALUES (:id, :conv_id, 'outbound', :content, true, NOW())
                   ON CONFLICT DO NOTHING"""),
                {
                    "id": str(uuid.uuid4()),
                    "conv_id": conv_id,
                    "content": body,
                },
            )
    except Exception as e:
        logger.error(f"Scheduling SMS sent but conversation record failed: {e}")

    # Panel record for UI visibility (non-critical — separate transaction)
    try:
        with db_session() as db:
            db.execute(
                sa_text("""INSERT INTO sms_panel_messages
                   (id, phone, contact_id, organization_id, direction, body,
                    sender_name, sender_role, status, telnyx_message_id, created_at)
                   VALUES (:id, :phone, :contact_id, :org_id, 'outbound', :body,
                           'Aria', 'ai_assistant', 'sent', :msg_id, NOW())
                   ON CONFLICT DO NOTHING"""),
                {
                    "id": result.get("message_id", "") or str(uuid.uuid4()),
                    "phone": to_e164,
                    "contact_id": lead_id or "",
                    "org_id": int(organization_id) if organization_id else None,
                    "body": body,
                    "msg_id": result.get("message_id", ""),
                },
            )
    except Exception as e:
        logger.warning(f"Scheduling SMS panel record failed (non-critical): {e}")

    return ToolResult.success(
        data={
            "conversation_id": conv_id if "conv_id" in dir() else None,
            "message_id": result.get("message_id", ""),
            "to": to_phone,
            "message_sent": body,
            "appointment_type": appointment_type,
            "status": "scheduling_initiated",
        },
        message=f"Scheduling SMS sent to {borrower_name} at {to_phone}. They'll text back with their preferred time.",
    )
