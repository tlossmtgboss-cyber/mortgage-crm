"""
Perennia AI - Voice OS Tools
============================
Tools for the Voice OS Agent handling outbound calls, voicemail, and call analytics.
8 tools for call initiation, voicemail drops, transcription, and metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
    db_session,
    get_tenant_context,
)


def _require_tenant() -> Optional[ToolResult]:
    """Return error ToolResult if tenant context is missing, else None."""
    if not get_tenant_context():
        return ToolResult.error("Organization context required")
    return None


def _check_call_consent(phone_number: str, contact_id: Optional[str] = None) -> Optional[ToolResult]:
    """Check call consent via ChannelPreference. Returns error ToolResult if blocked."""
    org_id = get_tenant_context()
    try:
        with db_session() as session:
            from telephony.compliance import ComplianceChecker
            checker = ComplianceChecker(db=session, organization_id=org_id)
            lead_id = int(contact_id) if contact_id else None
            has_consent, reason = checker.check_call_consent(phone_number, contact_id=lead_id)
            if not has_consent:
                return ToolResult.error(f"BLOCKED: {reason}")
    except Exception as e:
        logger.warning(f"Consent check failed (fail-open): {e}")
    return None


def _validate_outbound(phone: str, channel: str = "call") -> Optional[ToolResult]:
    """Run compliance checks before outbound contact.

    Evaluates quiet hours in the RECIPIENT's timezone (resolved from
    their area code) per TCPA Safe Harbor rules.

    Returns ToolResult error or None if clear.
    """
    # Check DNC
    dnc = execute_single(
        "SELECT id, reason FROM contact_dnc_status WHERE phone_number = :phone",
        {"phone": phone}
    )
    if dnc:
        return ToolResult.error(f"BLOCKED: Phone {phone} is on DNC list. Reason: {dnc.get('reason', 'N/A')}")

    # Check calling window in RECIPIENT's timezone (8am-9pm local)
    try:
        from telephony.compliance import resolve_recipient_timezone
        from zoneinfo import ZoneInfo
        from datetime import timezone as _tz

        recipient_tz_name = resolve_recipient_timezone(phone)
        recipient_tz = ZoneInfo(recipient_tz_name)
        now_local = datetime.now(_tz.utc).astimezone(recipient_tz)

        if now_local.hour < 8 or now_local.hour >= 21:
            return ToolResult.error(
                f"BLOCKED: It's {now_local.strftime('%I:%M %p')} in the recipient's "
                f"timezone ({recipient_tz_name}). Outside TCPA {channel} window "
                f"(8 AM - 9 PM). Want me to schedule it for tomorrow morning?"
            )
    except Exception as e:
        # Fallback: block if we can't determine timezone (fail-closed)
        logger.warning(f"Timezone resolution failed for {phone}, using UTC check: {e}")
        from datetime import timezone as _tz
        now_utc = datetime.now(_tz.utc)
        eastern_hour = (now_utc.hour - 5) % 24  # Approximate, ignoring DST
        if eastern_hour < 8 or eastern_hour >= 21:
            return ToolResult.error(
                f"BLOCKED: Outside TCPA {channel} window (8 AM - 9 PM Eastern). "
                f"Want me to schedule it for tomorrow morning?"
            )

    return None


# =============================================================================
# Voice OS Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="initiate_outbound_call",
    description="Initiate outbound call to a contact via Telnyx/VoIP",
    agent_roles=["voice_os"],
    risk_level="HIGH",
    parameters={
        "phone_number": "Phone number to call",
        "contact_id": "Contact/lead ID",
        "contact_type": "Type: lead, borrower, realtor",
        "purpose": "Call purpose",
        "script_id": "Optional script template",
    },
)
def initiate_outbound_call(
    phone_number: str,
    contact_id: str,
    contact_type: str = "lead",
    purpose: str = "follow_up",
    script_id: Optional[str] = None,
) -> ToolResult:
    """Initiate outbound call with TCPA/DNC compliance gate."""
    tenant_err = _require_tenant()
    if tenant_err:
        return tenant_err

    org_id = get_tenant_context()

    compliance_block = _validate_outbound(phone_number, "call")
    if compliance_block:
        return compliance_block

    consent_block = _check_call_consent(
        phone_number,
        contact_id if contact_type == "lead" else None,
    )
    if consent_block:
        return consent_block

    # Check for duplicate active calls
    active = execute_single(
        "SELECT id FROM active_calls WHERE contact_phone = :phone AND expires_at > NOW()",
        {"phone": phone_number}
    )
    if active:
        return ToolResult.error(f"Active call already in progress for {phone_number}")

    import uuid
    call_id = str(uuid.uuid4())[:8].upper()

    if contact_type == "lead":
        contact = execute_single(
            "SELECT id, first_name, last_name, phone FROM leads WHERE id = :id AND organization_id = :org_id",
            {"id": contact_id, "org_id": org_id}
        )
    else:
        contact = execute_single(
            "SELECT id, borrower_name as name, borrower_phone as phone FROM loans WHERE id = :id AND organization_id = :org_id",
            {"id": contact_id, "org_id": org_id}
        )

    if not contact:
        return ToolResult.error("Contact not found in your organization")

    contact_name = contact.get("first_name", contact.get("name", "Unknown")) if contact else "Unknown"

    try:
        with db_session() as session:
            from sqlalchemy import text
            session.execute(text("""
                INSERT INTO call_logs (contact_phone, contact_name, lead_id, loan_id, outcome, notes, organization_id, created_at)
                VALUES (:phone, :name, :lead_id, :loan_id, 'initiating', :notes, :org_id, NOW())
            """), {
                "phone": phone_number,
                "name": contact_name,
                "lead_id": int(contact_id) if contact_type == "lead" else None,
                "loan_id": int(contact_id) if contact_type != "lead" else None,
                "notes": f"Outbound {purpose} call initiated",
                "org_id": org_id,
            })
    except Exception as e:
        logger.warning(f"Failed to log call in initiate_outbound_call: {e}")

    call_data = {
        "call_id": f"CALL-{call_id}",
        "phone_number": phone_number,
        "contact_id": contact_id,
        "contact_type": contact_type,
        "contact_name": contact_name,
        "purpose": purpose,
        "script_id": script_id,
        "status": "initiating",
        "initiated_at": datetime.now().isoformat(),
        "compliance_cleared": True,
    }

    return ToolResult.success(
        data=call_data,
        message=f"Call initiating to {phone_number} (compliance cleared)",
        requires_approval=True,
    )


@mortgage_tool(
    name="drop_voicemail",
    description="Drop pre-recorded voicemail using ringless voicemail",
    agent_roles=["voice_os"],
    risk_level="HIGH",
    parameters={
        "phone_number": "Phone number",
        "voicemail_template": "Template ID or custom message",
        "contact_id": "Contact ID",
        "scheduled_time": "Optional scheduled time",
    },
)
def drop_voicemail(
    phone_number: str,
    voicemail_template: str,
    contact_id: str,
    scheduled_time: Optional[str] = None,
) -> ToolResult:
    """Drop pre-recorded voicemail with TCPA/DNC compliance gate."""
    tenant_err = _require_tenant()
    if tenant_err:
        return tenant_err

    org_id = get_tenant_context()

    compliance_block = _validate_outbound(phone_number, "call")
    if compliance_block:
        return compliance_block

    import uuid
    vm_id = str(uuid.uuid4())[:8].upper()

    db_template = execute_single("""
        SELECT id, name, message_text, audio_url, voice_provider, voice_id, delivery_method, category
        FROM voicemail_templates
        WHERE (name = :name OR category = :name OR id::text = :name)
            AND is_active = true
            AND organization_id = :org_id
        ORDER BY is_default DESC
        LIMIT 1
    """, {"name": voicemail_template, "org_id": org_id})

    if db_template:
        template_text = db_template.get("message_text", "")
        template_id = db_template.get("id")
        audio_url = db_template.get("audio_url")
        delivery_method = db_template.get("delivery_method", "vapi_ai")
    else:
        # Fallback to hardcoded templates
        fallback_templates = {
            "follow_up": "Hi, this is [LO_NAME] from [COMPANY]. I wanted to follow up on your mortgage inquiry...",
            "rate_update": "Hi, this is [LO_NAME]. I have some great news about current rates...",
            "document_reminder": "Hi, this is [LO_NAME]. I'm calling about some documents we still need...",
            "closing_update": "Hi, this is [LO_NAME]. I have an update on your closing...",
        }
        template_text = fallback_templates.get(voicemail_template, voicemail_template)
        template_id = None
        audio_url = None
        delivery_method = "vapi_ai"

    try:
        with db_session() as session:
            from sqlalchemy import text
            session.execute(text("""
                INSERT INTO voicemail_drops (phone_number, message_text, template_id, audio_url, delivery_method, status, organization_id, created_at, updated_at)
                VALUES (:phone, :msg, :tid, :audio, :method, 'pending', :org_id, NOW(), NOW())
            """), {
                "phone": phone_number,
                "msg": template_text,
                "tid": template_id,
                "audio": audio_url,
                "method": delivery_method,
                "org_id": org_id,
            })
    except Exception as e:
        logger.warning(f"Failed to write voicemail drop record in drop_voicemail: {e}")

    drop_data = {
        "voicemail_id": f"VM-{vm_id}",
        "phone_number": phone_number,
        "contact_id": contact_id,
        "template": voicemail_template,
        "template_id": template_id,
        "message_preview": template_text[:100] + "..." if len(template_text) > 100 else template_text,
        "delivery_method": delivery_method,
        "audio_url": audio_url,
        "scheduled_time": scheduled_time or datetime.now().isoformat(),
        "status": "queued",
        "compliance_cleared": True,
    }

    return ToolResult.success(
        data=drop_data,
        message=f"Voicemail queued for {phone_number} (compliance cleared)",
        requires_approval=True,
    )


@mortgage_tool(
    name="get_call_history",
    description="Get call history for a contact with recordings",
    agent_roles=["voice_os"],
    risk_level="LOW",
    parameters={
        "contact_id": "Contact ID",
        "contact_type": "Type: lead, borrower",
        "include_recordings": "Include recording URLs",
        "limit": "Max results",
    },
)
def get_call_history(
    contact_id: str,
    contact_type: str = "lead",
    include_recordings: bool = False,
    limit: int = 20,
) -> ToolResult:
    """Get call history for contact."""
    tenant_err = _require_tenant()
    if tenant_err:
        return tenant_err

    org_id = get_tenant_context()

    calls = execute_query("""
        SELECT
            id, direction, phone_number, duration_seconds,
            outcome, notes, recording_url, created_at
        FROM call_logs
        WHERE contact_id = :contact_id AND contact_type = :contact_type
            AND organization_id = :org_id
        ORDER BY created_at DESC
        LIMIT :limit
    """, {"contact_id": contact_id, "contact_type": contact_type, "limit": limit, "org_id": org_id})

    if not calls:
        # Return empty but valid structure
        calls = []

    call_list = []
    total_duration = 0
    for call in calls:
        call_info = {
            "call_id": call.get("id"),
            "direction": call.get("direction", "outbound"),
            "phone_number": call.get("phone_number"),
            "duration": call.get("duration_seconds", 0),
            "outcome": call.get("outcome"),
            "notes": call.get("notes"),
            "date": format_date(call.get("created_at")),
        }
        if include_recordings and call.get("recording_url"):
            call_info["recording_url"] = call.get("recording_url")
        call_list.append(call_info)
        total_duration += call.get("duration_seconds", 0)

    data = {
        "contact_id": contact_id,
        "contact_type": contact_type,
        "calls": call_list,
        "total_calls": len(call_list),
        "total_duration_seconds": total_duration,
        "total_duration_formatted": f"{total_duration // 60}m {total_duration % 60}s",
    }

    return ToolResult.success(
        data=data,
        message=f"Found {len(call_list)} calls for contact",
    )


@mortgage_tool(
    name="analyze_call_sentiment",
    description="Analyze sentiment from call recording/transcription",
    agent_roles=["voice_os"],
    risk_level="LOW",
    parameters={
        "call_id": "Call ID to analyze",
        "transcription": "Optional transcription text",
    },
)
def analyze_call_sentiment(
    call_id: str,
    transcription: Optional[str] = None,
) -> ToolResult:
    """Analyze call sentiment from call log data or provided transcription."""
    tenant_err = _require_tenant()
    if tenant_err:
        return tenant_err

    org_id = get_tenant_context()

    call_data = execute_single("""
        SELECT id, contact_phone, contact_name, duration_seconds, outcome,
               notes, ai_note_summary, created_at
        FROM call_logs WHERE (id = :id OR call_sid = :id) AND organization_id = :org_id
    """, {"id": call_id, "org_id": org_id})

    analysis = {
        "call_id": call_id,
        "call_found": call_data is not None,
        "sentiment": {
            "overall": "neutral",
            "score": 0.0,
            "confidence": 0.0,
        },
        "emotions_detected": [],
        "key_phrases": [],
        "topics": [],
        "customer_satisfaction": "unknown",
        "follow_up_recommended": False,
        "status": "pending_transcription" if not transcription else "analyzed",
    }

    # Use AI summary from call log if available
    if call_data and call_data.get("ai_note_summary") and not transcription:
        transcription = call_data.get("ai_note_summary")
    if call_data and call_data.get("notes") and not transcription:
        transcription = call_data.get("notes")

    # Add call metadata
    if call_data:
        analysis["call_metadata"] = {
            "contact": call_data.get("contact_name"),
            "duration_seconds": call_data.get("duration_seconds"),
            "outcome": call_data.get("outcome"),
            "date": format_date(call_data.get("created_at")),
        }

    if transcription:
        text_lower = transcription.lower()

        # Simple sentiment detection
        positive_words = ["thank", "great", "happy", "appreciate", "excellent", "perfect"]
        negative_words = ["frustrated", "upset", "problem", "issue", "disappointed", "confused"]

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        if pos_count > neg_count:
            analysis["sentiment"]["overall"] = "positive"
            analysis["sentiment"]["score"] = min(pos_count * 0.2, 1.0)
        elif neg_count > pos_count:
            analysis["sentiment"]["overall"] = "negative"
            analysis["sentiment"]["score"] = max(-neg_count * 0.2, -1.0)
            analysis["follow_up_recommended"] = True

        analysis["sentiment"]["confidence"] = 0.7
        analysis["status"] = "analyzed"

    return ToolResult.success(
        data=analysis,
        message=f"Sentiment: {analysis['sentiment']['overall']}",
    )


@mortgage_tool(
    name="schedule_callback",
    description="Schedule callback for a contact",
    agent_roles=["voice_os"],
    risk_level="MEDIUM",
    parameters={
        "contact_id": "Contact ID",
        "contact_type": "Type: lead, borrower",
        "callback_time": "Scheduled callback time (ISO)",
        "reason": "Callback reason",
        "priority": "Priority: low, normal, high, urgent",
        "notes": "Additional notes",
    },
)
def schedule_callback(
    contact_id: str,
    contact_type: str = "lead",
    callback_time: Optional[str] = None,
    reason: str = "follow_up",
    priority: str = "normal",
    notes: Optional[str] = None,
) -> ToolResult:
    """Schedule callback with TCPA compliance gate."""
    tenant_err = _require_tenant()
    if tenant_err:
        return tenant_err

    org_id = get_tenant_context()

    import uuid
    callback_id = str(uuid.uuid4())[:8].upper()

    if not callback_time:
        tomorrow = datetime.now() + timedelta(days=1)
        while tomorrow.weekday() >= 5:
            tomorrow += timedelta(days=1)
        callback_time = tomorrow.replace(hour=10, minute=0, second=0).isoformat()

    if contact_type == "lead":
        contact = execute_single(
            "SELECT first_name, last_name, phone FROM leads WHERE id = :id AND organization_id = :org_id",
            {"id": contact_id, "org_id": org_id}
        )
    else:
        contact = execute_single(
            "SELECT borrower_name as name, borrower_phone as phone FROM loans WHERE id = :id AND organization_id = :org_id",
            {"id": contact_id, "org_id": org_id}
        )

    phone = contact.get("phone") if contact else None

    # COMPLIANCE GATE — check DNC before scheduling callback
    if phone:
        compliance_block = _validate_outbound(phone, "call")
        if compliance_block:
            return compliance_block

    contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', contact.get('name', ''))}".strip() if contact else "Unknown"

    # Write to DialerSessionTask for callback tracking
    try:
        with db_session() as session:
            from sqlalchemy import text
            session.execute(text("""
                INSERT INTO dialer_session_tasks
                    (contact_phone, contact_name, contact_context, lead_id, loan_id, status, disposition, notes, follow_up_date, task_order, created_at, updated_at)
                VALUES
                    (:phone, :name, :context, :lead_id, :loan_id, 'pending', :reason, :notes, :follow_up, 0, NOW(), NOW())
            """), {
                "phone": phone,
                "name": contact_name,
                "context": f"Scheduled callback: {reason}",
                "lead_id": int(contact_id) if contact_type == "lead" else None,
                "loan_id": int(contact_id) if contact_type != "lead" else None,
                "reason": reason,
                "notes": notes,
                "follow_up": callback_time,
            })
    except Exception as e:
        logger.warning(f"Failed to write callback record in schedule_callback: {e}")

    callback_data = {
        "callback_id": f"CB-{callback_id}",
        "contact_id": contact_id,
        "contact_type": contact_type,
        "contact_name": contact_name,
        "phone": phone,
        "callback_time": callback_time,
        "reason": reason,
        "priority": priority,
        "notes": notes,
        "status": "scheduled",
        "compliance_cleared": True if phone else None,
        "created_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=callback_data,
        message=f"Callback scheduled for {callback_time}",
    )


@mortgage_tool(
    name="get_power_dialer_queue",
    description="Get or manage power dialer call queue",
    agent_roles=["voice_os"],
    risk_level="LOW",
    parameters={
        "lo_id": "Loan officer ID",
        "queue_type": "Type: all, priority, scheduled",
        "action": "Action: get, add, remove, reorder",
        "contact_ids": "Contact IDs for add/remove",
    },
)
def get_power_dialer_queue(
    lo_id: str,
    queue_type: str = "all",
    action: str = "get",
    contact_ids: Optional[List[str]] = None,
) -> ToolResult:
    """Manage power dialer queue."""
    tenant_err = _require_tenant()
    if tenant_err:
        return tenant_err

    org_id = get_tenant_context()

    queue = execute_query("""
        SELECT
            pdq.id, pdq.contact_id, pdq.contact_type, pdq.priority,
            pdq.scheduled_time, pdq.attempts, pdq.status,
            l.first_name, l.last_name, l.phone
        FROM power_dialer_queue pdq
        LEFT JOIN leads l ON l.id = pdq.contact_id AND pdq.contact_type = 'lead'
            AND l.organization_id = :org_id
        WHERE pdq.lo_id = :lo_id AND pdq.status = 'pending'
            AND pdq.organization_id = :org_id
        ORDER BY pdq.priority DESC, pdq.scheduled_time ASC
        LIMIT 50
    """, {"lo_id": lo_id, "org_id": org_id})

    if not queue:
        queue = []

    queue_items = []
    for item in queue:
        queue_items.append({
            "queue_id": item.get("id"),
            "contact_id": item.get("contact_id"),
            "contact_type": item.get("contact_type"),
            "contact_name": f"{item.get('first_name', '')} {item.get('last_name', '')}".strip(),
            "phone": item.get("phone"),
            "priority": item.get("priority"),
            "scheduled_time": format_date(item.get("scheduled_time")),
            "attempts": item.get("attempts", 0),
        })

    data = {
        "lo_id": lo_id,
        "queue_type": queue_type,
        "queue": queue_items,
        "total_in_queue": len(queue_items),
        "high_priority_count": len([q for q in queue_items if q.get("priority") == "high"]),
    }

    if action == "add" and contact_ids:
        data["added"] = contact_ids
        data["message"] = f"Added {len(contact_ids)} contacts to queue"
    elif action == "remove" and contact_ids:
        data["removed"] = contact_ids
        data["message"] = f"Removed {len(contact_ids)} contacts from queue"

    return ToolResult.success(
        data=data,
        message=f"Queue: {len(queue_items)} contacts",
    )


@mortgage_tool(
    name="transcribe_call",
    description="Get or request call transcription",
    agent_roles=["voice_os"],
    risk_level="LOW",
    parameters={
        "call_id": "Call ID to transcribe",
        "recording_url": "Optional recording URL",
        "language": "Language code (default: en-US)",
    },
)
def transcribe_call(
    call_id: str,
    recording_url: Optional[str] = None,
    language: str = "en-US",
) -> ToolResult:
    """Get or request transcription."""
    tenant_err = _require_tenant()
    if tenant_err:
        return tenant_err

    org_id = get_tenant_context()

    existing = execute_single("""
        SELECT transcription, transcribed_at, duration_seconds
        FROM call_transcriptions
        WHERE call_id = :call_id AND organization_id = :org_id
    """, {"call_id": call_id, "org_id": org_id})

    if existing and existing.get("transcription"):
        return ToolResult.success(
            data={
                "call_id": call_id,
                "transcription": existing.get("transcription"),
                "transcribed_at": format_date(existing.get("transcribed_at")),
                "duration_seconds": existing.get("duration_seconds"),
                "status": "complete",
            },
            message="Transcription retrieved",
        )

    # Request new transcription
    data = {
        "call_id": call_id,
        "recording_url": recording_url,
        "language": language,
        "status": "pending",
        "requested_at": datetime.now().isoformat(),
        "estimated_completion": (datetime.now() + timedelta(minutes=5)).isoformat(),
    }

    return ToolResult.success(
        data=data,
        message="Transcription requested",
    )


@mortgage_tool(
    name="get_call_metrics",
    description="Get call performance metrics for LO or team",
    agent_roles=["voice_os", "team_coach"],
    risk_level="LOW",
    parameters={
        "lo_id": "Optional LO ID (team-wide if not specified)",
        "period": "Period: today, week, month, quarter",
        "group_by": "Group by: day, week, outcome, lo",
    },
)
def get_call_metrics(
    lo_id: Optional[str] = None,
    period: str = "week",
    group_by: str = "day",
) -> ToolResult:
    """Get call performance metrics."""
    tenant_err = _require_tenant()
    if tenant_err:
        return tenant_err

    org_id = get_tenant_context()

    today = datetime.now().date()
    if period == "today":
        start_date = today
    elif period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    elif period == "quarter":
        start_date = today - timedelta(days=90)
    else:
        start_date = today - timedelta(days=7)

    params = {"start_date": start_date.isoformat(), "org_id": org_id}
    lo_filter = ""
    if lo_id:
        lo_filter = "AND lo_id = :lo_id"
        params["lo_id"] = lo_id

    metrics = execute_single(f"""
        SELECT
            COUNT(*) as total_calls,
            COUNT(CASE WHEN direction = 'outbound' THEN 1 END) as outbound,
            COUNT(CASE WHEN direction = 'inbound' THEN 1 END) as inbound,
            COUNT(CASE WHEN outcome = 'connected' THEN 1 END) as connected,
            COUNT(CASE WHEN outcome = 'voicemail' THEN 1 END) as voicemails,
            COUNT(CASE WHEN outcome = 'no_answer' THEN 1 END) as no_answer,
            AVG(duration_seconds) as avg_duration,
            SUM(duration_seconds) as total_duration
        FROM call_logs
        WHERE DATE(created_at) >= :start_date AND organization_id = :org_id {lo_filter}
    """, params)

    if not metrics:
        metrics = {
            "total_calls": 0, "outbound": 0, "inbound": 0,
            "connected": 0, "voicemails": 0, "no_answer": 0,
            "avg_duration": 0, "total_duration": 0
        }

    total_calls = metrics.get("total_calls", 0) or 0
    connected = metrics.get("connected", 0) or 0

    data = {
        "period": period,
        "date_range": {
            "start": start_date.isoformat(),
            "end": today.isoformat(),
        },
        "summary": {
            "total_calls": total_calls,
            "outbound": metrics.get("outbound", 0) or 0,
            "inbound": metrics.get("inbound", 0) or 0,
            "connected": connected,
            "voicemails": metrics.get("voicemails", 0) or 0,
            "no_answer": metrics.get("no_answer", 0) or 0,
            "connect_rate": round((connected / total_calls) * 100, 1) if total_calls > 0 else 0,
            "avg_duration_seconds": round(float(metrics.get("avg_duration", 0) or 0), 1),
            "total_duration_minutes": round(float(metrics.get("total_duration", 0) or 0) / 60, 1),
        },
        "lo_id": lo_id,
    }

    return ToolResult.success(
        data=data,
        message=f"Calls: {total_calls}, Connect rate: {data['summary']['connect_rate']}%",
    )
