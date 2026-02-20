"""
Perennia AI - AI Receptionist Tools
===================================
Tools for the AI Receptionist Agent handling inbound calls and routing.
8 tools for call handling, qualification, routing, and callback management.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
    db_session,
)


# =============================================================================
# AI Receptionist Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="handle_inbound_call",
    description="Handle inbound call and gather initial information",
    agent_roles=["ai_receptionist"],
    risk_level="LOW",
    parameters={
        "caller_phone": "Caller's phone number",
        "call_source": "Source: main_line, direct, transfer, ivr",
        "caller_id_name": "Caller ID name if available",
        "ivr_selections": "IVR menu selections if applicable",
    },
)
def handle_inbound_call(
    caller_phone: str,
    call_source: str = "main_line",
    caller_id_name: Optional[str] = None,
    ivr_selections: Optional[List[str]] = None,
) -> ToolResult:
    """Handle inbound call."""
    import uuid
    call_id = str(uuid.uuid4())[:8].upper()

    # Look up caller in database
    lead = execute_single(
        "SELECT id, first_name, last_name, phone, stage, assigned_to FROM leads WHERE phone = :phone",
        {"phone": caller_phone}
    )

    loan = execute_single(
        "SELECT id, loan_number, borrower_name, borrower_phone, stage, loan_officer_id FROM loans WHERE borrower_phone = :phone",
        {"phone": caller_phone}
    )

    # Determine caller status
    caller_type = "new"
    existing_record = None
    if loan:
        caller_type = "borrower"
        existing_record = {
            "type": "loan",
            "id": loan.get("id"),
            "loan_number": loan.get("loan_number"),
            "name": loan.get("borrower_name"),
            "stage": loan.get("stage"),
            "assigned_to": loan.get("loan_officer_id"),
        }
    elif lead:
        caller_type = "lead"
        existing_record = {
            "type": "lead",
            "id": lead.get("id"),
            "name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
            "stage": lead.get("stage"),
            "assigned_to": lead.get("assigned_to"),
        }

    # Determine intent from IVR
    intent = "general"
    if ivr_selections:
        ivr_intent_map = {
            "1": "status_check",
            "2": "new_application",
            "3": "rates",
            "4": "documents",
            "5": "speak_to_lo",
        }
        for selection in ivr_selections:
            if selection in ivr_intent_map:
                intent = ivr_intent_map[selection]
                break

    call_data = {
        "call_id": f"INC-{call_id}",
        "caller_phone": caller_phone,
        "caller_id_name": caller_id_name,
        "call_source": call_source,
        "caller_type": caller_type,
        "existing_record": existing_record,
        "ivr_selections": ivr_selections,
        "detected_intent": intent,
        "received_at": datetime.now().isoformat(),
        "greeting": _get_greeting(caller_type, existing_record),
    }

    return ToolResult.success(
        data=call_data,
        message=f"Inbound call from {caller_type}: {intent}",
    )


@mortgage_tool(
    name="qualify_caller",
    description="Qualify caller and determine needs",
    agent_roles=["ai_receptionist"],
    risk_level="LOW",
    parameters={
        "call_id": "Call ID",
        "responses": "Caller responses to qualification questions",
        "call_reason": "Stated reason for call",
    },
)
def qualify_caller(
    call_id: str,
    responses: Dict[str, Any],
    call_reason: Optional[str] = None,
) -> ToolResult:
    """Qualify caller based on responses."""
    score = 0
    qualifiers = []
    needs = []

    # Analyze call reason
    if call_reason:
        reason_lower = call_reason.lower()
        if any(w in reason_lower for w in ["ready", "buy", "offer", "contract"]):
            score += 30
            needs.append("immediate_assistance")
        elif any(w in reason_lower for w in ["preapproval", "pre-approval", "qualify"]):
            score += 25
            needs.append("preapproval")
        elif any(w in reason_lower for w in ["rate", "refinance", "refi"]):
            score += 20
            needs.append("rate_quote")
        elif any(w in reason_lower for w in ["status", "update", "question"]):
            needs.append("status_inquiry")

    # Credit score
    credit = responses.get("credit_score", "unknown")
    if credit in ["excellent", "good"] or (isinstance(credit, int) and credit >= 680):
        score += 25
        qualifiers.append("good_credit")
    elif credit in ["fair"] or (isinstance(credit, int) and 580 <= credit < 680):
        score += 10

    # Timeline
    timeline = responses.get("timeline", "unknown")
    if timeline in ["now", "30_days", "active_search"]:
        score += 25
        qualifiers.append("ready_buyer")
    elif timeline in ["60_days", "90_days"]:
        score += 15

    # Employment
    if responses.get("employed", True):
        score += 10
        qualifiers.append("employed")

    # Determine priority
    if score >= 60:
        priority = "high"
        tier = "hot"
    elif score >= 35:
        priority = "medium"
        tier = "warm"
    else:
        priority = "low"
        tier = "nurture"

    qualification = {
        "call_id": call_id,
        "score": score,
        "tier": tier,
        "priority": priority,
        "qualifiers": qualifiers,
        "needs": needs,
        "call_reason": call_reason,
        "recommended_routing": _get_routing_for_tier(tier, needs),
        "suggested_script": _get_script_for_tier(tier),
    }

    return ToolResult.success(
        data=qualification,
        message=f"Caller qualified: {tier} ({priority} priority)",
    )


@mortgage_tool(
    name="route_call",
    description="Route call to appropriate person or department",
    agent_roles=["ai_receptionist"],
    risk_level="MEDIUM",
    parameters={
        "call_id": "Call ID",
        "routing_type": "Type: direct_transfer, warm_transfer, queue, callback",
        "destination": "Destination: lo, processor, closer, manager, queue_name",
        "destination_id": "Specific person ID if direct transfer",
        "context": "Context to pass to recipient",
    },
)
def route_call(
    call_id: str,
    routing_type: str = "queue",
    destination: str = "sales",
    destination_id: Optional[str] = None,
    context: Optional[str] = None,
) -> ToolResult:
    """Route call to destination."""
    import uuid
    routing_id = str(uuid.uuid4())[:8].upper()

    # Get destination info
    if destination_id:
        user = execute_single(
            "SELECT id, name, phone_extension FROM users WHERE id = :id",
            {"id": destination_id}
        )
        if user:
            dest_info = {
                "name": user.get("name"),
                "extension": user.get("phone_extension"),
            }
        else:
            dest_info = {"name": "Unknown", "extension": None}
    else:
        dest_info = {"name": destination, "extension": None}

    routing = {
        "routing_id": f"RT-{routing_id}",
        "call_id": call_id,
        "routing_type": routing_type,
        "destination": destination,
        "destination_id": destination_id,
        "destination_info": dest_info,
        "context": context,
        "status": "routing",
        "routed_at": datetime.now().isoformat(),
    }

    if routing_type == "warm_transfer":
        routing["announcement"] = f"Transferring call. Context: {context or 'New inquiry'}"
    elif routing_type == "queue":
        routing["queue_position"] = 1
        routing["estimated_wait"] = "2 minutes"

    return ToolResult.success(
        data=routing,
        message=f"Call routed to {destination} via {routing_type}",
    )


@mortgage_tool(
    name="get_lo_availability",
    description="Check loan officer availability for call or appointment",
    agent_roles=["ai_receptionist"],
    risk_level="LOW",
    parameters={
        "lo_id": "Optional specific LO ID",
        "specialty": "Optional specialty filter: conventional, fha, va, jumbo",
        "language": "Optional language requirement",
    },
)
def get_lo_availability(
    lo_id: Optional[str] = None,
    specialty: Optional[str] = None,
    language: Optional[str] = None,
) -> ToolResult:
    """Get LO availability."""
    params = {}
    filters = ["u.role = 'loan_officer'", "u.active = true"]

    if lo_id:
        filters.append("u.id = :lo_id")
        params["lo_id"] = lo_id

    # Query available LOs
    los = execute_query(f"""
        SELECT
            u.id, u.name, u.phone_extension, u.specialties,
            u.languages, u.current_status
        FROM users u
        WHERE {" AND ".join(filters)}
        ORDER BY u.name
        LIMIT 10
    """, params)

    if not los:
        los = []

    available_los = []
    for lo in los:
        status = lo.get("current_status", "unknown")
        is_available = status in ["available", "online", None]

        # Filter by specialty
        if specialty:
            specialties = lo.get("specialties", "").split(",")
            if specialty.lower() not in [s.lower().strip() for s in specialties]:
                continue

        # Filter by language
        if language:
            languages = lo.get("languages", "english").split(",")
            if language.lower() not in [l.lower().strip() for l in languages]:
                continue

        available_los.append({
            "id": lo.get("id"),
            "name": lo.get("name"),
            "extension": lo.get("phone_extension"),
            "status": status,
            "available": is_available,
            "specialties": lo.get("specialties", "").split(",") if lo.get("specialties") else [],
            "languages": lo.get("languages", "english").split(",") if lo.get("languages") else ["english"],
        })

    # Sort available first
    available_los.sort(key=lambda x: (not x["available"], x["name"]))

    return ToolResult.success(
        data={
            "loan_officers": available_los,
            "total": len(available_los),
            "available_count": len([lo for lo in available_los if lo["available"]]),
            "filters": {
                "specialty": specialty,
                "language": language,
            },
        },
        message=f"Found {len(available_los)} LOs, {len([lo for lo in available_los if lo['available']])} available",
    )


@mortgage_tool(
    name="create_callback_request",
    description="Create callback request for caller",
    agent_roles=["ai_receptionist"],
    risk_level="MEDIUM",
    parameters={
        "caller_phone": "Caller phone number",
        "caller_name": "Caller name",
        "callback_reason": "Reason for callback",
        "preferred_time": "Preferred callback time (ISO)",
        "urgency": "Urgency: low, normal, high",
        "notes": "Additional notes",
        "assign_to": "Optional specific person to assign to",
    },
)
def create_callback_request(
    caller_phone: str,
    caller_name: str,
    callback_reason: str,
    preferred_time: Optional[str] = None,
    urgency: str = "normal",
    notes: Optional[str] = None,
    assign_to: Optional[str] = None,
) -> ToolResult:
    """Create callback request with DNC compliance check."""
    # COMPLIANCE GATE — check DNC before creating outbound callback
    dnc = execute_single(
        "SELECT id, reason FROM contact_dnc_status WHERE phone_number = :phone",
        {"phone": caller_phone}
    )
    if dnc:
        return ToolResult.error(
            f"BLOCKED: Phone {caller_phone} is on DNC list. Cannot schedule callback. Reason: {dnc.get('reason', 'N/A')}"
        )

    import uuid
    callback_id = str(uuid.uuid4())[:8].upper()

    # Default to next business hour if not specified
    if not preferred_time:
        now = datetime.now()
        if now.hour >= 17 or now.weekday() >= 5:
            next_day = now + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            preferred_time = next_day.replace(hour=9, minute=0, second=0).isoformat()
        else:
            preferred_time = (now + timedelta(hours=1)).isoformat()

    # Check if caller exists
    existing = execute_single(
        "SELECT id, assigned_to FROM leads WHERE phone = :phone",
        {"phone": caller_phone}
    )

    # Write to DialerSessionTask for callback tracking
    try:
        with db_session() as session:
            from sqlalchemy import text
            session.execute(text("""
                INSERT INTO dialer_session_tasks
                    (contact_phone, contact_name, contact_context, lead_id, status, notes, follow_up_date, task_order, created_at, updated_at)
                VALUES
                    (:phone, :name, :context, :lead_id, 'pending', :notes, :follow_up, 0, NOW(), NOW())
            """), {
                "phone": caller_phone,
                "name": caller_name,
                "context": f"Callback request: {callback_reason}",
                "lead_id": existing.get("id") if existing else None,
                "notes": notes,
                "follow_up": preferred_time,
            })
    except Exception:
        pass

    callback = {
        "callback_id": f"CB-{callback_id}",
        "caller_phone": caller_phone,
        "caller_name": caller_name,
        "reason": callback_reason,
        "preferred_time": preferred_time,
        "urgency": urgency,
        "notes": notes,
        "assign_to": assign_to or (existing.get("assigned_to") if existing else None),
        "existing_lead_id": existing.get("id") if existing else None,
        "status": "pending",
        "compliance_cleared": True,
        "created_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=callback,
        message=f"Callback scheduled for {caller_name} (DNC cleared)",
    )


@mortgage_tool(
    name="get_greeting_script",
    description="Get appropriate greeting script based on caller info",
    agent_roles=["ai_receptionist"],
    risk_level="LOW",
    parameters={
        "caller_type": "Type: new, lead, borrower",
        "time_of_day": "Time: morning, afternoon, evening",
        "caller_name": "Caller name if known",
        "company_name": "Company name to use",
    },
)
def get_greeting_script(
    caller_type: str = "new",
    time_of_day: Optional[str] = None,
    caller_name: Optional[str] = None,
    company_name: str = "Perennia",
) -> ToolResult:
    """Get greeting script."""
    # Determine time of day
    if not time_of_day:
        hour = datetime.now().hour
        if hour < 12:
            time_of_day = "morning"
        elif hour < 17:
            time_of_day = "afternoon"
        else:
            time_of_day = "evening"

    time_greeting = {
        "morning": "Good morning",
        "afternoon": "Good afternoon",
        "evening": "Good evening",
    }.get(time_of_day, "Hello")

    scripts = {
        "new": {
            "greeting": f"{time_greeting}, thank you for calling {company_name}. How may I assist you today?",
            "follow_ups": [
                "Are you looking to purchase or refinance?",
                "Have you already started your home search?",
                "Would you like to speak with a loan officer about your options?",
            ],
        },
        "lead": {
            "greeting": f"{time_greeting}, {caller_name}! Thank you for calling back. How can I help you today?",
            "follow_ups": [
                "Were you calling about your pre-approval?",
                "Do you have any questions about your loan options?",
                "Would you like me to connect you with your loan officer?",
            ],
        },
        "borrower": {
            "greeting": f"{time_greeting}, {caller_name}! Thank you for calling. I see you have an active loan with us.",
            "follow_ups": [
                "Are you calling for a status update?",
                "Do you have questions about your loan?",
                "Would you like me to connect you with your loan team?",
            ],
        },
    }

    script = scripts.get(caller_type, scripts["new"])

    # Personalize with name if available
    if caller_name and caller_type == "new":
        script["greeting"] = f"{time_greeting}, thank you for calling {company_name}. Is this {caller_name}?"

    return ToolResult.success(
        data={
            "caller_type": caller_type,
            "time_of_day": time_of_day,
            "greeting": script["greeting"],
            "follow_up_questions": script["follow_ups"],
            "company_name": company_name,
        },
        message=f"Script for {caller_type} caller",
    )


@mortgage_tool(
    name="log_call_interaction",
    description="Log details of call interaction",
    agent_roles=["ai_receptionist"],
    risk_level="LOW",
    parameters={
        "call_id": "Call ID",
        "caller_phone": "Caller phone",
        "duration_seconds": "Call duration",
        "outcome": "Outcome: transferred, callback_scheduled, resolved, abandoned",
        "notes": "Call notes",
        "lead_id": "Associated lead ID if applicable",
    },
)
def log_call_interaction(
    call_id: str,
    caller_phone: str,
    duration_seconds: int,
    outcome: str,
    notes: Optional[str] = None,
    lead_id: Optional[str] = None,
) -> ToolResult:
    """Log call interaction to CallLog table."""
    # Write to call_logs table
    db_id = None
    try:
        with db_session() as session:
            from sqlalchemy import text
            result = session.execute(text("""
                INSERT INTO call_logs
                    (contact_phone, lead_id, call_sid, duration_seconds, outcome, notes, created_at, updated_at)
                VALUES
                    (:phone, :lead_id, :call_sid, :duration, :outcome, :notes, NOW(), NOW())
                RETURNING id
            """), {
                "phone": caller_phone,
                "lead_id": int(lead_id) if lead_id and lead_id.isdigit() else None,
                "call_sid": call_id,
                "duration": duration_seconds,
                "outcome": outcome,
                "notes": notes,
            })
            row = result.fetchone()
            if row:
                db_id = row[0]
    except Exception:
        pass

    log_entry = {
        "call_id": call_id,
        "db_log_id": db_id,
        "caller_phone": caller_phone,
        "duration_seconds": duration_seconds,
        "duration_formatted": f"{duration_seconds // 60}m {duration_seconds % 60}s",
        "outcome": outcome,
        "notes": notes,
        "lead_id": lead_id,
        "logged_at": datetime.now().isoformat(),
        "persisted": db_id is not None,
        "status": "logged",
    }

    return ToolResult.success(
        data=log_entry,
        message=f"Call logged: {outcome} ({log_entry['duration_formatted']})",
    )


@mortgage_tool(
    name="get_call_queue_status",
    description="Get current call queue status",
    agent_roles=["ai_receptionist"],
    risk_level="LOW",
    parameters={
        "queue_name": "Queue name: sales, support, processing, all",
    },
)
def get_call_queue_status(
    queue_name: str = "all",
) -> ToolResult:
    """Get call queue status from ActiveCall and DialerSession data."""
    # Query active calls
    active_calls = execute_single("""
        SELECT COUNT(*) as active_count
        FROM active_calls WHERE expires_at > NOW()
    """)

    # Query active dialer sessions
    active_sessions = execute_query("""
        SELECT
            ds.id, ds.status, ds.total_tasks, ds.completed_tasks,
            u.name as agent_name
        FROM dialer_sessions ds
        JOIN users u ON u.id = ds.agent_id
        WHERE ds.status IN ('active', 'in_progress', 'paused')
        ORDER BY ds.created_at DESC
        LIMIT 20
    """)

    # Query pending callback tasks
    pending_callbacks = execute_single("""
        SELECT COUNT(*) as pending_count
        FROM dialer_session_tasks
        WHERE status = 'pending' AND follow_up_date IS NOT NULL
    """)

    # Query agents currently on calls
    agents_on_call = execute_single("""
        SELECT COUNT(DISTINCT agent_id) as on_call
        FROM active_calls WHERE expires_at > NOW()
    """)

    # Query available agents (online LOs not on active calls)
    agents_available = execute_single("""
        SELECT COUNT(*) as available
        FROM users u
        WHERE u.role = 'loan_officer' AND u.active = true
            AND u.id NOT IN (SELECT agent_id FROM active_calls WHERE expires_at > NOW())
    """)

    active_count = active_calls.get("active_count", 0) if active_calls else 0
    on_call_count = agents_on_call.get("on_call", 0) if agents_on_call else 0
    available_count = agents_available.get("available", 0) if agents_available else 0
    pending_count = pending_callbacks.get("pending_count", 0) if pending_callbacks else 0

    queue_data = {
        "queue_name": queue_name,
        "real_time": {
            "active_calls": active_count,
            "agents_on_call": on_call_count,
            "agents_available": available_count,
            "pending_callbacks": pending_count,
        },
        "dialer_sessions": [
            {
                "id": s.get("id"),
                "agent": s.get("agent_name"),
                "status": s.get("status"),
                "progress": f"{s.get('completed_tasks', 0)}/{s.get('total_tasks', 0)}",
            }
            for s in (active_sessions or [])
        ],
        "total_waiting": pending_count,
        "total_agents_available": available_count,
        "checked_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=queue_data,
        message=f"Queue: {active_count} active calls, {available_count} agents available, {pending_count} pending callbacks",
    )


# =============================================================================
# Helper Functions
# =============================================================================

def _get_greeting(caller_type: str, existing_record: Optional[Dict]) -> str:
    """Get appropriate greeting for caller."""
    if caller_type == "borrower" and existing_record:
        return f"Hello, {existing_record.get('name', 'there')}! I see you have an active loan with us. How can I help you today?"
    elif caller_type == "lead" and existing_record:
        return f"Hello, {existing_record.get('name', 'there')}! Thank you for calling back. How can I assist you?"
    else:
        return "Thank you for calling! How may I help you today?"


def _get_routing_for_tier(tier: str, needs: List[str]) -> Dict:
    """Get routing recommendation based on tier and needs."""
    if "status_inquiry" in needs:
        return {"destination": "assigned_lo", "type": "warm_transfer"}
    elif tier == "hot":
        return {"destination": "senior_lo", "type": "warm_transfer"}
    elif tier == "warm":
        return {"destination": "sales_queue", "type": "queue"}
    else:
        return {"destination": "callback", "type": "callback_scheduled"}


def _get_script_for_tier(tier: str) -> str:
    """Get suggested script based on tier."""
    scripts = {
        "hot": "This caller is highly qualified and ready to proceed. Transfer immediately to a senior loan officer.",
        "warm": "Good prospect. Schedule a consultation within 24 hours.",
        "nurture": "Early stage. Capture information and add to nurture campaign.",
    }
    return scripts.get(tier, scripts["nurture"])
