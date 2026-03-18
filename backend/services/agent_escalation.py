"""
Agent Escalation Service

Handles the lifecycle of AI agent → human handoff escalations:
- Creating escalations with automatic priority/assignee rules
- Querying pending escalations for an org or assignee
- Resolving escalations with audit trail
- Auto-assigning escalations based on role and availability

Escalation Rules:
- COMPLIANCE_REQUIRED → always CRITICAL priority, auto-assign to compliance officer
- TOOL_FAILURE → HIGH priority if the context references an active loan
- CONFIDENCE_LOW → MEDIUM priority, context must include the AI's partial response

Usage:
    from services.agent_escalation import (
        create_escalation,
        get_pending_escalations,
        resolve_escalation,
        auto_assign_escalation,
    )
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

logger = logging.getLogger(__name__)


# ============================================================================
# LAZY MODEL IMPORTS (avoid circular import at module load time)
# ============================================================================

_AgentEscalation = None
_User = None


def _ensure_models():
    """Lazy-load ORM models on first use."""
    global _AgentEscalation, _User
    if _AgentEscalation is None:
        from database.models.agent_escalation import AgentEscalation
        from database.models.core import User
        _AgentEscalation = AgentEscalation
        _User = User


# ============================================================================
# ESCALATION RULES
# ============================================================================

# Maps agent_role → the human role that should receive escalations
ROLE_ASSIGNMENT_MAP: Dict[str, str] = {
    "pipeline_analyst": "branch_manager",
    "compliance_checker": "compliance_officer",
    "lead_nurturer": "loan_officer",
    "document_tracker": "processor",
    "team_coach": "branch_manager",
}

# Role hierarchy for fallback assignment
ROLE_FALLBACK_CHAIN: Dict[str, List[str]] = {
    "compliance_officer": ["compliance_officer", "branch_manager", "admin"],
    "branch_manager": ["branch_manager", "admin"],
    "loan_officer": ["loan_officer", "branch_manager", "admin"],
    "processor": ["processor", "loan_officer", "branch_manager"],
}


def _apply_escalation_rules(
    reason: str,
    priority: str,
    context: Optional[Dict[str, Any]],
    agent_role: str,
) -> tuple:
    """Apply business rules to determine final priority and suggested assignee role.

    Returns:
        (final_priority, suggested_assignee_role)
    """
    suggested_role = ROLE_ASSIGNMENT_MAP.get(agent_role, "branch_manager")

    # Rule 1: COMPLIANCE_REQUIRED → always CRITICAL, always compliance officer
    if reason == "compliance_required":
        priority = "critical"
        suggested_role = "compliance_officer"

    # Rule 2: TOOL_FAILURE → HIGH if active loan is involved
    elif reason == "tool_failure":
        if context and context.get("loan_id"):
            priority = "high"
        else:
            # Keep the provided priority or default to medium
            priority = priority if priority != "low" else "medium"

    # Rule 3: CONFIDENCE_LOW → MEDIUM, must include partial_response
    elif reason == "confidence_low":
        if priority == "low":
            priority = "medium"
        # Ensure partial_response is captured (log if missing, don't block)
        if context and not context.get("partial_response"):
            logger.warning(
                "CONFIDENCE_LOW escalation created without partial_response in context. "
                "Human assignee may lack AI's preliminary analysis."
            )

    # Rule 4: SENSITIVE_DATA → at least HIGH
    elif reason == "sensitive_data":
        if priority in ("low", "medium"):
            priority = "high"

    return priority, suggested_role


# ============================================================================
# PUBLIC API
# ============================================================================

def create_escalation(
    db: Session,
    agent_role: str,
    user_id: int,
    org_id: int,
    reason: str,
    priority: str = "medium",
    context: Optional[Dict[str, Any]] = None,
    suggested_assignee: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a new agent escalation record.

    Applies business rules to adjust priority and determine the suggested
    assignee role. If a specific suggested_assignee (user ID) is provided,
    the escalation is immediately assigned to that user.

    Args:
        db: SQLAlchemy session.
        agent_role: AI agent role that is escalating (e.g. "compliance_checker").
        user_id: ID of the user who was interacting with the AI.
        org_id: Organization ID (multi-tenant isolation).
        reason: One of EscalationReason values.
        priority: Initial priority (may be overridden by rules).
        context: JSON-serializable dict with escalation context.
        suggested_assignee: Optional user ID to directly assign to.

    Returns:
        Dict with the created escalation details.
    """
    _ensure_models()

    # Apply business rules
    final_priority, suggested_role = _apply_escalation_rules(
        reason=reason,
        priority=priority,
        context=context,
        agent_role=agent_role,
    )

    escalation = _AgentEscalation(
        organization_id=org_id,
        agent_role=agent_role,
        user_id=user_id,
        reason=reason,
        priority=final_priority,
        status="assigned" if suggested_assignee else "pending",
        context=context,
        assigned_to=suggested_assignee,
        assigned_at=datetime.now(timezone.utc) if suggested_assignee else None,
        suggested_assignee_role=suggested_role,
    )

    db.add(escalation)
    db.flush()  # Get the ID without committing (caller controls transaction)

    logger.info(
        f"Agent escalation created: id={escalation.id} "
        f"agent_role={agent_role} reason={reason} priority={final_priority} "
        f"org_id={org_id} assigned_to={suggested_assignee}"
    )

    return _escalation_to_dict(escalation)


def get_pending_escalations(
    db: Session,
    org_id: int,
    assignee_id: Optional[int] = None,
    include_assigned: bool = True,
) -> List[Dict[str, Any]]:
    """Get pending (and optionally assigned) escalations for an organization.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID.
        assignee_id: If provided, filter to escalations assigned to this user.
        include_assigned: If True, include both 'pending' and 'assigned' statuses.

    Returns:
        List of escalation dicts, ordered by priority (critical first) then age.
    """
    _ensure_models()

    statuses = ["pending"]
    if include_assigned:
        statuses.append("assigned")

    query = (
        db.query(_AgentEscalation)
        .filter(
            _AgentEscalation.organization_id == org_id,
            _AgentEscalation.status.in_(statuses),
        )
    )

    if assignee_id is not None:
        query = query.filter(_AgentEscalation.assigned_to == assignee_id)

    # Order: critical first, then by creation date (oldest first)
    priority_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    escalations = query.order_by(
        # SQLAlchemy CASE for priority ordering
        _case_priority_order(),
        _AgentEscalation.created_at.asc(),
    ).all()

    return [_escalation_to_dict(e) for e in escalations]


def resolve_escalation(
    db: Session,
    escalation_id: int,
    resolver_id: int,
    resolution_notes: str,
) -> Dict[str, Any]:
    """Mark an escalation as resolved.

    Args:
        db: SQLAlchemy session.
        escalation_id: ID of the escalation to resolve.
        resolver_id: User ID of the person resolving it.
        resolution_notes: Free-text description of how it was resolved.

    Returns:
        Updated escalation dict.

    Raises:
        ValueError: If escalation not found or already resolved/expired.
    """
    _ensure_models()

    escalation = (
        db.query(_AgentEscalation)
        .filter(_AgentEscalation.id == escalation_id)
        .first()
    )

    if not escalation:
        raise ValueError(f"Escalation {escalation_id} not found")

    if escalation.status in ("resolved", "expired"):
        raise ValueError(
            f"Escalation {escalation_id} is already {escalation.status}"
        )

    now = datetime.now(timezone.utc)
    escalation.status = "resolved"
    escalation.resolved_at = now
    escalation.resolved_by = resolver_id
    escalation.resolution_notes = resolution_notes
    escalation.updated_at = now

    db.flush()

    logger.info(
        f"Agent escalation resolved: id={escalation_id} "
        f"resolver_id={resolver_id} reason={escalation.reason}"
    )

    return _escalation_to_dict(escalation)


def auto_assign_escalation(
    db: Session,
    escalation_id: int,
) -> Dict[str, Any]:
    """Auto-assign an escalation to an available team member based on role.

    Looks up the suggested_assignee_role and finds an active user in the
    same organization with a matching role. Falls back through the role
    chain if no match is found.

    Args:
        db: SQLAlchemy session.
        escalation_id: ID of the escalation to assign.

    Returns:
        Updated escalation dict with assignment details.

    Raises:
        ValueError: If escalation not found or already assigned/resolved.
    """
    _ensure_models()

    escalation = (
        db.query(_AgentEscalation)
        .filter(_AgentEscalation.id == escalation_id)
        .first()
    )

    if not escalation:
        raise ValueError(f"Escalation {escalation_id} not found")

    if escalation.status in ("resolved", "expired"):
        raise ValueError(
            f"Escalation {escalation_id} is already {escalation.status}"
        )

    if escalation.assigned_to is not None:
        raise ValueError(
            f"Escalation {escalation_id} is already assigned to user {escalation.assigned_to}"
        )

    # Determine role chain to search
    target_role = escalation.suggested_assignee_role or "branch_manager"
    role_chain = ROLE_FALLBACK_CHAIN.get(target_role, [target_role, "admin"])

    assigned_user = None

    for role in role_chain:
        # Find an active user in the org with the matching role
        # Users have a 'role' column (String) on the users table
        candidate = (
            db.query(_User)
            .filter(
                _User.organization_id == escalation.organization_id,
                _User.role == role,
                _User.is_active == True,  # noqa: E712
            )
            .order_by(_User.id.asc())  # Deterministic: pick lowest-ID matching user
            .first()
        )
        if candidate:
            assigned_user = candidate
            break

    if not assigned_user:
        logger.warning(
            f"Auto-assign failed for escalation {escalation_id}: "
            f"no active user with roles {role_chain} in org {escalation.organization_id}"
        )
        return _escalation_to_dict(escalation)

    now = datetime.now(timezone.utc)
    escalation.assigned_to = assigned_user.id
    escalation.assigned_at = now
    escalation.status = "assigned"
    escalation.updated_at = now

    db.flush()

    logger.info(
        f"Agent escalation auto-assigned: id={escalation_id} "
        f"assigned_to={assigned_user.id} (role={assigned_user.role})"
    )

    return _escalation_to_dict(escalation)


# ============================================================================
# HELPERS
# ============================================================================

def _case_priority_order():
    """Build a SQL CASE expression for ordering by priority."""
    from sqlalchemy import case
    _ensure_models()
    return case(
        ((_AgentEscalation.priority == "critical"), 0),
        ((_AgentEscalation.priority == "high"), 1),
        ((_AgentEscalation.priority == "medium"), 2),
        ((_AgentEscalation.priority == "low"), 3),
        else_=4,
    )


def _escalation_to_dict(escalation) -> Dict[str, Any]:
    """Convert an AgentEscalation ORM object to a plain dict."""
    return {
        "id": escalation.id,
        "organization_id": escalation.organization_id,
        "agent_role": escalation.agent_role,
        "user_id": escalation.user_id,
        "reason": escalation.reason,
        "priority": escalation.priority,
        "status": escalation.status,
        "context": escalation.context,
        "assigned_to": escalation.assigned_to,
        "assigned_at": escalation.assigned_at.isoformat() if escalation.assigned_at else None,
        "suggested_assignee_role": escalation.suggested_assignee_role,
        "resolved_at": escalation.resolved_at.isoformat() if escalation.resolved_at else None,
        "resolved_by": escalation.resolved_by,
        "resolution_notes": escalation.resolution_notes,
        "created_at": escalation.created_at.isoformat() if escalation.created_at else None,
        "updated_at": escalation.updated_at.isoformat() if escalation.updated_at else None,
    }
