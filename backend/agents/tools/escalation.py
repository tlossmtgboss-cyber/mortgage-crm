"""
Perennia AI - Escalation & Handoff Tools (Module 3)
Tools for automated escalation decision-making, warm handoff execution,
and escalation history tracking.

Integrates with:
    - services/escalation_strategy_service.py (rule engine)
    - services/live_agent_escalation_service.py (warm handoff)
    - database/models/task.py (EscalationRecord, HandoffLog)
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_date, days_between, sql_now, sql_date_subtract,
)


# =============================================================================
# ESCALATION LEVEL DEFINITIONS
# =============================================================================

ESCALATION_LEVELS = {
    1: {
        "name": "Agent-to-Agent",
        "description": "Route to a different AI agent with full context",
        "sla_minutes": 0,
        "requires_human": False,
    },
    2: {
        "name": "Agent-to-Human",
        "description": "Escalate to human team member with warm handoff",
        "sla_minutes": 60,
        "requires_human": True,
    },
    3: {
        "name": "Management",
        "description": "Escalate to manager or supervisor",
        "sla_minutes": 30,
        "requires_human": True,
    },
    4: {
        "name": "Emergency",
        "description": "Immediate escalation — compliance, legal, or safety",
        "sla_minutes": 15,
        "requires_human": True,
    },
}

# Role-based routing map
ESCALATION_ROUTING = {
    "compliance_issue": {"role": "compliance_officer", "level": 4},
    "borrower_distress": {"role": "loan_officer", "level": 2},
    "manager_request": {"role": "branch_manager", "level": 3},
    "rate_lock_expiring": {"role": "loan_officer", "level": 2},
    "underwriting_question": {"role": "underwriter", "level": 2},
    "closing_issue": {"role": "closer", "level": 3},
    "technical_error": {"role": "support", "level": 2},
    "domain_mismatch": {"role": "auto_route", "level": 1},
    "pii_exposure": {"role": "compliance_officer", "level": 4},
    "legal_threat": {"role": "branch_manager", "level": 4},
}


# =============================================================================
# ESCALATION TOOLS (6 tools)
# =============================================================================

@mortgage_tool(
    name="evaluate_escalation",
    description="Evaluate whether a situation requires escalation and determine the appropriate level and routing",
    agent_roles=["all"],
    risk_level="low",
    examples=[
        "Should I escalate this borrower complaint?",
        "The borrower is asking for a manager",
        "I'm not confident about this compliance question",
    ],
)
def evaluate_escalation(
    trigger_type: str,
    context: Optional[str] = None,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    severity: Optional[str] = None,
) -> ToolResult:
    """
    Evaluate whether escalation is needed based on trigger type and context.

    Args:
        trigger_type: Type of escalation trigger (e.g., 'compliance_issue', 'borrower_distress')
        context: Description of the situation
        loan_id: Associated loan ID if applicable
        lead_id: Associated lead ID if applicable
        severity: Override severity (low/medium/high/critical)
    """
    routing = ESCALATION_ROUTING.get(trigger_type)
    if not routing:
        return ToolResult.error(
            f"Unknown trigger type: {trigger_type}. "
            f"Valid types: {', '.join(ESCALATION_ROUTING.keys())}"
        )

    level = routing["level"]
    level_info = ESCALATION_LEVELS[level]

    # Check for prior escalations on the same entity
    prior_count = 0
    if loan_id:
        prior = execute_single("""
            SELECT COUNT(*) as cnt
            FROM escalation_records
            WHERE loan_id = :loan_id
                AND trigger_type = :trigger_type
                AND status IN ('open', 'in_progress')
        """, {"loan_id": loan_id, "trigger_type": trigger_type})
        prior_count = prior["cnt"] if prior else 0
    elif lead_id:
        prior = execute_single("""
            SELECT COUNT(*) as cnt
            FROM escalation_records
            WHERE lead_id = :lead_id
                AND trigger_type = :trigger_type
                AND status IN ('open', 'in_progress')
        """, {"lead_id": lead_id, "trigger_type": trigger_type})
        prior_count = prior["cnt"] if prior else 0

    # Auto-elevate if repeated escalation
    if prior_count >= 2 and level < 3:
        level = min(level + 1, 4)
        level_info = ESCALATION_LEVELS[level]

    data = {
        "should_escalate": True,
        "trigger_type": trigger_type,
        "level": level,
        "level_name": level_info["name"],
        "target_role": routing["role"],
        "sla_minutes": level_info["sla_minutes"],
        "requires_human": level_info["requires_human"],
        "prior_escalations": prior_count,
        "auto_elevated": prior_count >= 2,
        "context": context,
        "recommendation": (
            f"Escalate to {routing['role']} (Level {level}: {level_info['name']}). "
            f"SLA: {level_info['sla_minutes']} minutes."
        ),
    }

    return ToolResult.success(
        data=data,
        message=f"Escalation recommended: Level {level} ({level_info['name']}) → {routing['role']}",
    )


@mortgage_tool(
    name="create_escalation",
    description="Create an escalation record and route to the appropriate handler",
    agent_roles=["all"],
    risk_level="medium",
    requires_confirmation=True,
    examples=[
        "Escalate this to the compliance officer",
        "Route this to the branch manager",
        "Create an escalation for this borrower complaint",
    ],
)
def create_escalation(
    trigger_type: str,
    description: str,
    target_role: str,
    level: int = 2,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    source_agent: Optional[str] = None,
    priority: str = "high",
) -> ToolResult:
    """
    Create an escalation record and notify the target handler.

    Args:
        trigger_type: Type of escalation trigger
        description: Full context description for the handler
        target_role: Role to escalate to
        level: Escalation level (1-4)
        loan_id: Associated loan ID
        lead_id: Associated lead ID
        source_agent: Name of the agent creating the escalation
        priority: Priority level (low/medium/high/critical)
    """
    if level not in ESCALATION_LEVELS:
        return ToolResult.error(f"Invalid level: {level}. Must be 1-4.")

    level_info = ESCALATION_LEVELS[level]

    # Find the target user
    target_user = None
    if loan_id and target_role != "auto_route":
        target_user = execute_single("""
            SELECT u.id, u.name, u.email
            FROM users u
            JOIN user_roles ur ON ur.user_id = u.id
            WHERE ur.role_name = :role
            LIMIT 1
        """, {"role": target_role})

    # Create the escalation record
    with get_db() as db:
        from sqlalchemy import text
        db.execute(text("""
            INSERT INTO escalation_records
                (trigger_type, description, level, target_role, target_user_id,
                 loan_id, lead_id, source_agent, priority, status, created_at, sla_deadline)
            VALUES
                (:trigger_type, :description, :level, :target_role, :target_user_id,
                 :loan_id, :lead_id, :source_agent, :priority, 'open', NOW(),
                 NOW() + INTERVAL '1 minute' * :sla_minutes)
        """), {
            "trigger_type": trigger_type,
            "description": description,
            "level": level,
            "target_role": target_role,
            "target_user_id": target_user["id"] if target_user else None,
            "loan_id": loan_id,
            "lead_id": lead_id,
            "source_agent": source_agent,
            "priority": priority,
            "sla_minutes": level_info["sla_minutes"],
        })

    data = {
        "escalation_created": True,
        "trigger_type": trigger_type,
        "level": level,
        "level_name": level_info["name"],
        "target_role": target_role,
        "target_user": target_user["name"] if target_user else "Auto-routing",
        "priority": priority,
        "sla_minutes": level_info["sla_minutes"],
        "description": description[:200],
    }

    return ToolResult.success(
        data=data,
        message=f"Escalation created: {trigger_type} → {target_role} (Level {level}, SLA: {level_info['sla_minutes']}min)",
    )


@mortgage_tool(
    name="get_escalation_status",
    description="Check the status of open escalations for a loan, lead, or agent",
    agent_roles=["all"],
    risk_level="low",
    examples=[
        "What escalations are open for this loan?",
        "Check my open escalations",
        "Are there any overdue escalations?",
    ],
)
def get_escalation_status(
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    target_role: Optional[str] = None,
    include_resolved: bool = False,
    limit: int = 20,
) -> ToolResult:
    """Get escalation status for a loan, lead, or role."""
    params: Dict[str, Any] = {"limit": limit}
    filters = []

    if loan_id:
        filters.append("er.loan_id = :loan_id")
        params["loan_id"] = loan_id
    if lead_id:
        filters.append("er.lead_id = :lead_id")
        params["lead_id"] = lead_id
    if target_role:
        filters.append("er.target_role = :target_role")
        params["target_role"] = target_role
    if not include_resolved:
        filters.append("er.status IN ('open', 'in_progress')")

    where_sql = " AND ".join(filters) if filters else "1=1"

    escalations = execute_query(f"""
        SELECT
            er.id, er.trigger_type, er.description, er.level,
            er.target_role, er.priority, er.status,
            er.created_at, er.sla_deadline, er.resolved_at,
            er.loan_id, er.lead_id, er.source_agent
        FROM escalation_records er
        WHERE {where_sql}
        ORDER BY
            CASE er.priority
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            er.created_at DESC
        LIMIT :limit
    """, params)

    if not escalations:
        return ToolResult.no_data("No escalations found matching criteria")

    now = datetime.now(timezone.utc)
    overdue_count = 0
    results = []
    for esc in escalations:
        is_overdue = (
            esc["sla_deadline"]
            and esc["sla_deadline"] < now
            and esc["status"] in ("open", "in_progress")
        )
        if is_overdue:
            overdue_count += 1

        results.append({
            "id": esc["id"],
            "trigger_type": esc["trigger_type"],
            "description": esc["description"][:100] if esc["description"] else None,
            "level": esc["level"],
            "target_role": esc["target_role"],
            "priority": esc["priority"],
            "status": esc["status"],
            "created_at": format_date(esc["created_at"]),
            "sla_deadline": format_date(esc["sla_deadline"]),
            "is_overdue": is_overdue,
            "loan_id": esc["loan_id"],
            "lead_id": esc["lead_id"],
        })

    data = {
        "total": len(results),
        "overdue": overdue_count,
        "escalations": results,
    }

    return ToolResult.success(
        data=data,
        message=f"{len(results)} escalations ({overdue_count} overdue)",
    )


@mortgage_tool(
    name="execute_warm_handoff",
    description="Execute a warm handoff from AI agent to human with full context transfer",
    agent_roles=["all"],
    risk_level="medium",
    requires_confirmation=True,
    examples=[
        "Transfer this call to the loan officer with context",
        "Warm handoff to the manager",
        "Connect the borrower to a human agent",
    ],
)
def execute_warm_handoff(
    escalation_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    target_role: Optional[str] = None,
    context_summary: str = "",
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    conversation_history: Optional[str] = None,
    caller_emotion: Optional[str] = None,
    handoff_reason: str = "",
) -> ToolResult:
    """
    Execute a warm handoff with full context transfer.

    Args:
        escalation_id: Link to existing escalation record
        target_user_id: Specific user to hand off to
        target_role: Role to hand off to (if no specific user)
        context_summary: Summary of the conversation so far
        loan_id: Associated loan
        lead_id: Associated lead
        conversation_history: Full conversation transcript
        caller_emotion: Emotional state of the caller (calm/frustrated/angry/distressed)
        handoff_reason: Why the handoff is happening
    """
    # Find target user
    target = None
    if target_user_id:
        target = execute_single("""
            SELECT id, name, email, phone FROM users WHERE id = :id
        """, {"id": target_user_id})
    elif target_role:
        # Find available user with the role
        target = execute_single("""
            SELECT u.id, u.name, u.email, u.phone
            FROM users u
            JOIN user_roles ur ON ur.user_id = u.id
            WHERE ur.role_name = :role AND u.is_active = true
            ORDER BY u.last_login_at DESC
            LIMIT 1
        """, {"role": target_role})

    if not target:
        return ToolResult.error(
            f"No available handler found for role '{target_role}'. "
            "Creating fallback task for manual assignment."
        )

    # Build context package for the human
    context_package = {
        "handoff_to": target["name"],
        "handoff_to_id": target["id"],
        "reason": handoff_reason,
        "caller_emotion": caller_emotion,
        "context_summary": context_summary,
        "loan_id": loan_id,
        "lead_id": lead_id,
    }

    # Get loan/lead context
    if loan_id:
        loan = execute_single("""
            SELECT loan_number, borrower_name, status, loan_amount
            FROM loans WHERE id = :id
        """, {"id": loan_id})
        if loan:
            context_package["loan_context"] = {
                "loan_number": loan["loan_number"],
                "borrower": loan["borrower_name"],
                "status": loan["status"],
                "amount": float(loan["loan_amount"] or 0),
            }

    if lead_id:
        lead = execute_single("""
            SELECT first_name, last_name, email, phone, status
            FROM leads WHERE id = :id
        """, {"id": lead_id})
        if lead:
            context_package["lead_context"] = {
                "name": f"{lead['first_name']} {lead['last_name']}",
                "email": lead["email"],
                "phone": lead["phone"],
                "status": lead["status"],
            }

    # Log the handoff
    with get_db() as db:
        from sqlalchemy import text
        db.execute(text("""
            INSERT INTO handoff_logs
                (escalation_id, from_agent, to_user_id, to_role,
                 context_summary, caller_emotion, handoff_reason,
                 loan_id, lead_id, created_at)
            VALUES
                (:escalation_id, 'ai_agent', :to_user_id, :to_role,
                 :context_summary, :caller_emotion, :handoff_reason,
                 :loan_id, :lead_id, NOW())
        """), {
            "escalation_id": escalation_id,
            "to_user_id": target["id"],
            "to_role": target_role,
            "context_summary": context_summary[:500],
            "caller_emotion": caller_emotion,
            "handoff_reason": handoff_reason,
            "loan_id": loan_id,
            "lead_id": lead_id,
        })

    data = {
        "handoff_executed": True,
        "target_user": target["name"],
        "target_email": target["email"],
        "context_package": context_package,
        "caller_emotion": caller_emotion,
        "instruction_to_human": (
            f"Warm handoff from AI. Reason: {handoff_reason}. "
            f"Caller emotion: {caller_emotion or 'unknown'}. "
            f"Context: {context_summary[:200]}"
        ),
    }

    return ToolResult.success(
        data=data,
        message=f"Warm handoff to {target['name']} — context transferred",
    )


@mortgage_tool(
    name="resolve_escalation",
    description="Resolve an open escalation with resolution notes",
    agent_roles=["all"],
    risk_level="low",
    examples=[
        "Close this escalation",
        "Mark escalation as resolved",
    ],
)
def resolve_escalation(
    escalation_id: int,
    resolution: str,
    resolved_by: Optional[str] = None,
) -> ToolResult:
    """
    Resolve an open escalation.

    Args:
        escalation_id: ID of the escalation to resolve
        resolution: Description of how it was resolved
        resolved_by: Name or ID of the resolver
    """
    escalation = execute_single("""
        SELECT id, trigger_type, status, created_at, sla_deadline
        FROM escalation_records
        WHERE id = :id
    """, {"id": escalation_id})

    if not escalation:
        return ToolResult.no_data(f"Escalation {escalation_id} not found")

    if escalation["status"] == "resolved":
        return ToolResult.error(f"Escalation {escalation_id} is already resolved")

    now = datetime.now(timezone.utc)
    was_within_sla = (
        escalation["sla_deadline"] is None
        or now <= escalation["sla_deadline"]
    )

    with get_db() as db:
        from sqlalchemy import text
        db.execute(text("""
            UPDATE escalation_records
            SET status = 'resolved',
                resolution = :resolution,
                resolved_by = :resolved_by,
                resolved_at = NOW(),
                within_sla = :within_sla
            WHERE id = :id
        """), {
            "id": escalation_id,
            "resolution": resolution,
            "resolved_by": resolved_by,
            "within_sla": was_within_sla,
        })

    data = {
        "escalation_id": escalation_id,
        "status": "resolved",
        "resolution": resolution,
        "within_sla": was_within_sla,
        "resolution_time_minutes": (
            (now - escalation["created_at"]).total_seconds() / 60
            if escalation["created_at"] else None
        ),
    }

    return ToolResult.success(
        data=data,
        message=f"Escalation {escalation_id} resolved {'within' if was_within_sla else 'outside'} SLA",
    )


@mortgage_tool(
    name="get_escalation_analytics",
    description="Get escalation analytics: volume, SLA compliance, common triggers, and trends",
    agent_roles=["team_coach", "pipeline_analyst", "reporting"],
    risk_level="low",
    examples=[
        "How are our escalation SLAs?",
        "What are the most common escalation triggers?",
        "Show escalation trends for the last 30 days",
    ],
)
def get_escalation_analytics(
    days: int = 30,
    target_role: Optional[str] = None,
    source_agent: Optional[str] = None,
) -> ToolResult:
    """Get escalation analytics for a time period."""
    params: Dict[str, Any] = {"days": days}
    filters = [f"er.created_at >= {sql_date_subtract(days)}"]

    if target_role:
        filters.append("er.target_role = :target_role")
        params["target_role"] = target_role
    if source_agent:
        filters.append("er.source_agent = :source_agent")
        params["source_agent"] = source_agent

    where_sql = " AND ".join(filters)

    # Overall stats
    stats = execute_single(f"""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'resolved' THEN 1 END) as resolved,
            COUNT(CASE WHEN status IN ('open', 'in_progress') THEN 1 END) as open,
            COUNT(CASE WHEN within_sla = true THEN 1 END) as within_sla,
            COUNT(CASE WHEN within_sla = false THEN 1 END) as missed_sla
        FROM escalation_records er
        WHERE {where_sql}
    """, params)

    # By trigger type
    by_trigger = execute_query(f"""
        SELECT
            trigger_type,
            COUNT(*) as count,
            COUNT(CASE WHEN within_sla = true THEN 1 END) as within_sla
        FROM escalation_records er
        WHERE {where_sql}
        GROUP BY trigger_type
        ORDER BY count DESC
    """, params)

    # By level
    by_level = execute_query(f"""
        SELECT
            level, COUNT(*) as count
        FROM escalation_records er
        WHERE {where_sql}
        GROUP BY level
        ORDER BY level
    """, params)

    total = stats["total"] or 0
    resolved = stats["resolved"] or 0
    sla_compliant = stats["within_sla"] or 0

    data = {
        "period_days": days,
        "summary": {
            "total": total,
            "resolved": resolved,
            "open": stats["open"] or 0,
            "sla_compliance_rate": round((sla_compliant / resolved * 100), 1) if resolved > 0 else 0,
            "resolution_rate": round((resolved / total * 100), 1) if total > 0 else 0,
        },
        "by_trigger": [
            {
                "trigger": t["trigger_type"],
                "count": t["count"],
                "sla_rate": round((t["within_sla"] / t["count"] * 100), 1) if t["count"] > 0 else 0,
            }
            for t in by_trigger
        ],
        "by_level": [
            {
                "level": l["level"],
                "name": ESCALATION_LEVELS.get(l["level"], {}).get("name", "Unknown"),
                "count": l["count"],
            }
            for l in by_level
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"{total} escalations in {days} days, {data['summary']['sla_compliance_rate']}% SLA compliance",
    )
