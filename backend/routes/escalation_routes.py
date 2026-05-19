"""
Agent Escalation Routes

REST API for managing AI agent → human handoff escalations.

Endpoints:
    GET  /api/v1/escalations              List pending/assigned escalations
    PUT  /api/v1/escalations/{id}/assign   Assign escalation to a team member
    PUT  /api/v1/escalations/{id}/resolve  Mark escalation as resolved
    POST /api/v1/escalations              Create an escalation (internal/AI use)
"""

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

VALID_REASONS = frozenset({
    "confidence_low", "sensitive_data", "compliance_required",
    "user_requested", "tool_failure", "timeout",
})

VALID_PRIORITIES = frozenset({"low", "medium", "high", "critical"})


class EscalationCreateRequest(BaseModel):
    """Request body for creating an agent escalation."""
    agent_role: str = Field(..., min_length=1, max_length=100, description="AI agent role that is escalating")
    reason: str = Field(..., min_length=1, max_length=50, description="Escalation reason code")
    priority: str = Field(default="medium", max_length=20, description="Initial priority (may be overridden by rules)")
    context: Optional[Dict[str, Any]] = Field(default=None, description="JSON context for the handoff")
    suggested_assignee: Optional[int] = Field(default=None, description="User ID to directly assign to")


class EscalationAssignRequest(BaseModel):
    """Request body for assigning an escalation."""
    assignee_id: Optional[int] = Field(
        default=None,
        description="User ID to assign to. If omitted, auto-assigns based on role."
    )


class EscalationResolveRequest(BaseModel):
    """Request body for resolving an escalation."""
    resolution_notes: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Description of how the escalation was resolved",
    )


# =============================================================================
# ROUTE REGISTRATION
# =============================================================================

def register_escalation_routes(app, get_db, get_current_user, **kwargs):
    """
    Register agent escalation routes.

    Args:
        app: FastAPI application instance.
        get_db: Database session dependency.
        get_current_user: Auth dependency returning current User.
    """

    # Lazy imports to avoid circular dependencies
    from services.agent_escalation import (
        create_escalation,
        get_pending_escalations,
        resolve_escalation,
        auto_assign_escalation,
    )
    from database.models.agent_escalation import AgentEscalation

    # Ensure table exists in production
    try:
        from db import engine
        AgentEscalation.__table__.create(engine, checkfirst=True)
        logger.info("Agent escalation table verified")
    except Exception as e:
        logger.warning(f"Agent escalation table creation skipped: {e}")

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _get_org_id(user) -> int:
        """Extract organization_id from authenticated user."""
        org_id = getattr(user, "organization_id", None)
        if org_id is None:
            raise HTTPException(status_code=403, detail="No organization context")
        return org_id

    # =========================================================================
    # GET /api/v1/escalations — List pending escalations
    # =========================================================================

    @app.get("/api/v1/escalations", tags=["Agent Escalations"])
    async def list_escalations(
        assignee_id: Optional[int] = Query(default=None, description="Filter by assigned user"),
        include_assigned: bool = Query(default=True, description="Include assigned (not just pending)"),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """List pending and assigned agent escalations for the current organization.

        Returns escalations ordered by priority (critical first) then by age
        (oldest first). Use assignee_id to filter to a specific team member's queue.
        """
        org_id = _get_org_id(current_user)

        try:
            escalations = get_pending_escalations(
                db=db,
                org_id=org_id,
                assignee_id=assignee_id,
                include_assigned=include_assigned,
            )
            return {
                "status": "success",
                "count": len(escalations),
                "escalations": escalations,
            }
        except Exception as e:
            logger.exception(f"Failed to list escalations for org {org_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve escalations")

    # =========================================================================
    # POST /api/v1/escalations — Create an escalation
    # =========================================================================

    @app.post("/api/v1/escalations", tags=["Agent Escalations"], status_code=201)
    async def create_escalation_endpoint(
        body: EscalationCreateRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Create a new agent escalation.

        Business rules are automatically applied:
        - COMPLIANCE_REQUIRED reason → CRITICAL priority, assigned to compliance officer
        - TOOL_FAILURE with active loan → HIGH priority
        - CONFIDENCE_LOW → MEDIUM priority (include partial_response in context)
        """
        org_id = _get_org_id(current_user)

        # Validate reason
        if body.reason not in VALID_REASONS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid reason: '{body.reason}'. Valid reasons: {sorted(VALID_REASONS)}",
            )

        # Validate priority
        if body.priority not in VALID_PRIORITIES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid priority: '{body.priority}'. Valid priorities: {sorted(VALID_PRIORITIES)}",
            )

        try:
            result = create_escalation(
                db=db,
                agent_role=body.agent_role,
                user_id=current_user.id,
                org_id=org_id,
                reason=body.reason,
                priority=body.priority,
                context=body.context,
                suggested_assignee=body.suggested_assignee,
            )
            await db.commit()
            return {"status": "success", "escalation": result}
        except Exception as e:
            await db.rollback()
            logger.exception(f"Failed to create escalation: {e}")
            raise HTTPException(status_code=500, detail="Failed to create escalation")

    # =========================================================================
    # PUT /api/v1/escalations/{id}/assign — Assign to team member
    # =========================================================================

    @app.put("/api/v1/escalations/{escalation_id}/assign", tags=["Agent Escalations"])
    async def assign_escalation(
        escalation_id: int,
        body: EscalationAssignRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Assign an escalation to a team member.

        If assignee_id is provided, assigns directly to that user.
        If omitted, auto-assigns based on the escalation's suggested role
        and available team members.
        """
        org_id = _get_org_id(current_user)

        # Verify the escalation belongs to this org
        esc = (
            db.query(AgentEscalation)
            .filter(
                AgentEscalation.id == escalation_id,
                AgentEscalation.organization_id == org_id,
            )
            .first()
        )
        if not esc:
            raise HTTPException(status_code=404, detail="Escalation not found")

        try:
            if body.assignee_id is not None:
                # Direct assignment
                from datetime import datetime, timezone as tz
                esc.assigned_to = body.assignee_id
                esc.assigned_at = datetime.now(tz.utc)
                esc.status = "assigned"
                await db.flush()
                await db.commit()

                from services.agent_escalation import _escalation_to_dict
                result = _escalation_to_dict(esc)
            else:
                # Auto-assign
                result = auto_assign_escalation(db=db, escalation_id=escalation_id)
                await db.commit()

            return {"status": "success", "escalation": result}

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            await db.rollback()
            logger.exception(f"Failed to assign escalation {escalation_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to assign escalation")

    # =========================================================================
    # PUT /api/v1/escalations/{id}/resolve — Mark as resolved
    # =========================================================================

    @app.put("/api/v1/escalations/{escalation_id}/resolve", tags=["Agent Escalations"])
    async def resolve_escalation_endpoint(
        escalation_id: int,
        body: EscalationResolveRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Mark an escalation as resolved with resolution notes.

        The resolver is recorded as the currently authenticated user.
        """
        org_id = _get_org_id(current_user)

        # Verify the escalation belongs to this org
        esc = (
            db.query(AgentEscalation)
            .filter(
                AgentEscalation.id == escalation_id,
                AgentEscalation.organization_id == org_id,
            )
            .first()
        )
        if not esc:
            raise HTTPException(status_code=404, detail="Escalation not found")

        try:
            result = resolve_escalation(
                db=db,
                escalation_id=escalation_id,
                resolver_id=current_user.id,
                resolution_notes=body.resolution_notes,
            )
            await db.commit()
            return {"status": "success", "escalation": result}

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            await db.rollback()
            logger.exception(f"Failed to resolve escalation {escalation_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to resolve escalation")

    logger.info("Agent escalation routes registered")
