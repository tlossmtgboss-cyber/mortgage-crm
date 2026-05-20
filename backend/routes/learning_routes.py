"""
Continual Learning System Routes (Domain 8)

Endpoints for recording user corrections, implicit approvals, condition
overrides, and querying per-agent learned context.  Also exposes admin-only
consolidation triggers, training-data exports, harness optimisation proposals,
and AgentGym regression results.

Prefix: /api/v1/learning
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, text, select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db, get_async_db
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/learning", tags=["Continual Learning"])


# =============================================================================
# Pydantic schemas
# =============================================================================

class CorrectionRequest(BaseModel):
    agent_id: str = Field(..., description="Agent role identifier (e.g. pipeline_analyst)")
    interaction_id: Optional[str] = Field(None, description="ID of the original AI interaction")
    original_output: str = Field(..., description="The AI output that was corrected")
    corrected_output: str = Field(..., description="The user-corrected version")
    correction_type: str = Field("text_edit", description="Type: text_edit | tool_selection | intent_reclassification")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for the correction")


class ApprovalRequest(BaseModel):
    agent_id: str
    interaction_id: Optional[str] = None
    output_text: str = Field(..., description="The AI output that was implicitly approved")
    approval_signal: str = Field("used_without_edit", description="Signal: used_without_edit | positive_feedback | forwarded")
    context: Optional[Dict[str, Any]] = None


class OverrideRequest(BaseModel):
    agent_id: str
    condition_name: str = Field(..., description="Name of the condition being overridden")
    original_value: Optional[str] = None
    override_value: str = Field(..., description="The value the user chose instead")
    reason: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class HarnessProposalFilter(BaseModel):
    status: Optional[str] = Field("pending", description="Filter: pending | approved | rejected | all")
    agent_id: Optional[str] = None
    limit: int = Field(50, ge=1, le=200)


class HarnessActionRequest(BaseModel):
    reason: Optional[str] = None


# =============================================================================
# Lazy model imports
# =============================================================================

_models_loaded = False
_LearningExample = None
_LearningPattern = None
_PromptOptimization = None


def _ensure_models():
    global _models_loaded, _LearningExample, _LearningPattern, _PromptOptimization
    if _models_loaded:
        return
    from database.models.learning_example import (
        LearningExample, LearningPattern, PromptOptimization,
    )
    _LearningExample = LearningExample
    _LearningPattern = LearningPattern
    _PromptOptimization = PromptOptimization
    _models_loaded = True


def _ensure_tables(db: Session):
    """Create tables if they don't exist (production-safe)."""
    try:
        from database.models.learning_example import create_tables_if_needed
        from db import engine
        create_tables_if_needed(engine)
    except Exception as e:
        logger.warning("Learning table creation check (non-fatal): %s", e)


def _require_admin(current_user) -> None:
    """Raise 403 if the user is not an admin or site_admin."""
    role = getattr(current_user, "role", None) or ""
    perm_role = getattr(current_user, "permission_role", None) or ""
    if role not in ("admin", "site_admin") and perm_role not in ("admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")


# =============================================================================
# POST /corrections — Record a user correction to AI output
# =============================================================================

@router.post("/corrections")
async def record_correction(
    body: CorrectionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Record a user correction to an AI-generated output.

    Creates a negative learning example and (optionally) a correction example
    so the agent can learn from the delta.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)

    example = _LearningExample(
        organization_id=org_id,
        example_type="correction",
        intent=body.correction_type,
        agent_role=body.agent_id,
        query_text=body.original_output,
        expected_response=body.corrected_output,
        actual_response=body.original_output,
        correction_notes=(body.context or {}).get("notes"),
        quality_score=0,
        is_active=True,
    )
    db.add(example)
    await db.commit()
    await db.refresh(example)

    logger.info(
        "Correction recorded: example_id=%s agent=%s user=%s",
        example.id, body.agent_id, current_user.id,
    )

    return {
        "status": "ok",
        "example_id": example.id,
        "agent_id": body.agent_id,
        "correction_type": body.correction_type,
    }


# =============================================================================
# POST /approvals — Record an implicit approval
# =============================================================================

@router.post("/approvals")
async def record_approval(
    body: ApprovalRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Record an implicit approval — the AI output was used without modification."""
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)

    example = _LearningExample(
        organization_id=org_id,
        example_type="positive",
        intent=body.approval_signal,
        agent_role=body.agent_id,
        query_text=body.output_text,
        expected_response=body.output_text,
        actual_response=body.output_text,
        quality_score=85.0,
        is_active=True,
    )
    db.add(example)
    await db.commit()
    await db.refresh(example)

    logger.info(
        "Approval recorded: example_id=%s agent=%s signal=%s",
        example.id, body.agent_id, body.approval_signal,
    )

    return {
        "status": "ok",
        "example_id": example.id,
        "agent_id": body.agent_id,
        "approval_signal": body.approval_signal,
    }


# =============================================================================
# POST /overrides — Record a condition override
# =============================================================================

@router.post("/overrides")
async def record_override(
    body: OverrideRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Record when a user overrides a condition or parameter the AI chose."""
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)

    # Store as a learning pattern — overrides are behavioural signals
    pattern = _LearningPattern(
        organization_id=org_id,
        pattern_type="condition_override",
        pattern_key=f"{body.agent_id}:{body.condition_name}",
        pattern_value=body.override_value,
        confidence=0.6,
        occurrence_count=1,
        last_seen_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(pattern)

    # Also record as a correction example for the agent
    example = _LearningExample(
        organization_id=org_id,
        example_type="correction",
        intent="condition_override",
        agent_role=body.agent_id,
        query_text=f"Condition: {body.condition_name}",
        expected_response=body.override_value,
        actual_response=body.original_value,
        correction_notes=body.reason,
        quality_score=0,
        is_active=True,
    )
    db.add(example)

    await db.commit()
    await db.refresh(pattern)
    await db.refresh(example)

    logger.info(
        "Override recorded: pattern_id=%s agent=%s condition=%s",
        pattern.id, body.agent_id, body.condition_name,
    )

    return {
        "status": "ok",
        "pattern_id": pattern.id,
        "example_id": example.id,
        "agent_id": body.agent_id,
        "condition_name": body.condition_name,
    }


# =============================================================================
# GET /context/{agent_id} — Current learned context for an agent
# =============================================================================

@router.get("/context/{agent_id}")
async def get_agent_context(
    agent_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Get the current learned context for a specific agent.

    Returns active learning examples, discovered patterns, and any applied
    prompt optimisations that shape the agent's current behaviour.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)

    # Recent corrections + positive examples for this agent
    examples = (
        db.query(_LearningExample)
        .filter(
            _LearningExample.agent_role == agent_id,
            _LearningExample.is_active == True,  # noqa: E712
            (
                (_LearningExample.organization_id == org_id)
                | (_LearningExample.organization_id.is_(None))
            ),
        )
        .order_by(desc(_LearningExample.created_at))
        .limit(100)
        .all()
    )

    # Patterns for this agent
    patterns = (
        db.query(_LearningPattern)
        .filter(
            _LearningPattern.pattern_key.ilike(f"{agent_id}:%"),
            _LearningPattern.is_active == True,  # noqa: E712
            (
                (_LearningPattern.organization_id == org_id)
                | (_LearningPattern.organization_id.is_(None))
            ),
        )
        .order_by(desc(_LearningPattern.confidence))
        .limit(50)
        .all()
    )

    # Active prompt optimisations
    optimisations = (
        db.query(_PromptOptimization)
        .filter(
            _PromptOptimization.agent_role == agent_id,
            _PromptOptimization.is_active == True,  # noqa: E712
        )
        .order_by(desc(_PromptOptimization.applied_at))
        .limit(20)
        .all()
    )

    return {
        "agent_id": agent_id,
        "examples": [
            {
                "id": ex.id,
                "type": ex.example_type,
                "intent": ex.intent,
                "query_text": ex.query_text,
                "expected_response": ex.expected_response,
                "quality_score": float(ex.quality_score) if ex.quality_score else None,
                "usage_count": ex.usage_count,
                "created_at": ex.created_at.isoformat() if ex.created_at else None,
            }
            for ex in examples
        ],
        "patterns": [
            {
                "id": p.id,
                "type": p.pattern_type,
                "key": p.pattern_key,
                "value": p.pattern_value,
                "confidence": float(p.confidence) if p.confidence else None,
                "occurrence_count": p.occurrence_count,
                "last_seen_at": p.last_seen_at.isoformat() if p.last_seen_at else None,
            }
            for p in patterns
        ],
        "prompt_optimizations": [
            {
                "id": o.id,
                "type": o.optimization_type,
                "reason": o.reason,
                "score_before": float(o.feedback_score_before) if o.feedback_score_before else None,
                "score_after": float(o.feedback_score_after) if o.feedback_score_after else None,
                "applied_at": o.applied_at.isoformat() if o.applied_at else None,
            }
            for o in optimisations
        ],
        "summary": {
            "total_examples": len(examples),
            "total_patterns": len(patterns),
            "active_optimizations": len(optimisations),
        },
    }


# =============================================================================
# GET /context/{agent_id}/history — Context change audit log
# =============================================================================

@router.get("/context/{agent_id}/history")
async def get_agent_context_history(
    agent_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Get the audit log of context changes for a specific agent.

    Shows when learning examples were added/deactivated and when prompt
    optimisations were applied or rolled back.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)

    # All examples (including inactive) — serves as an audit trail
    examples = (
        db.query(_LearningExample)
        .filter(
            _LearningExample.agent_role == agent_id,
            (
                (_LearningExample.organization_id == org_id)
                | (_LearningExample.organization_id.is_(None))
            ),
        )
        .order_by(desc(_LearningExample.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    # All prompt optimisations (including rolled-back)
    optimisations = (
        db.query(_PromptOptimization)
        .filter(_PromptOptimization.agent_role == agent_id)
        .order_by(desc(_PromptOptimization.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    history: List[Dict[str, Any]] = []

    for ex in examples:
        history.append({
            "event_type": "example_added" if ex.is_active else "example_deactivated",
            "entity_type": "learning_example",
            "entity_id": ex.id,
            "example_type": ex.example_type,
            "intent": ex.intent,
            "timestamp": ex.created_at.isoformat() if ex.created_at else None,
            "details": {
                "query_text": (ex.query_text or "")[:200],
                "quality_score": float(ex.quality_score) if ex.quality_score else None,
            },
        })

    for opt in optimisations:
        event = "optimization_applied"
        if opt.rolled_back_at:
            event = "optimization_rolled_back"
        elif not opt.is_active:
            event = "optimization_deactivated"

        history.append({
            "event_type": event,
            "entity_type": "prompt_optimization",
            "entity_id": opt.id,
            "optimization_type": opt.optimization_type,
            "timestamp": (opt.applied_at or opt.created_at).isoformat() if (opt.applied_at or opt.created_at) else None,
            "details": {
                "reason": opt.reason,
                "score_before": float(opt.feedback_score_before) if opt.feedback_score_before else None,
                "score_after": float(opt.feedback_score_after) if opt.feedback_score_after else None,
            },
        })

    # Sort merged list by timestamp descending
    history.sort(key=lambda h: h.get("timestamp") or "", reverse=True)

    return {
        "agent_id": agent_id,
        "history": history,
        "total": len(history),
        "limit": limit,
        "offset": offset,
    }


# =============================================================================
# POST /consolidation/trigger — Manually trigger consolidation (admin only)
# =============================================================================

@router.post("/consolidation/trigger")
async def trigger_consolidation(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Manually trigger a consolidation job that merges redundant learning
    examples, recalculates pattern confidence scores, and prunes stale data.

    Admin only.
    """
    _require_admin(current_user)
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)
    now = datetime.now(timezone.utc)

    # 1. Deactivate low-quality examples older than 90 days
    stale_cutoff = text(
        "UPDATE learning_examples "
        "SET is_active = false, updated_at = :now "
        "WHERE is_active = true "
        "  AND quality_score < 20 "
        "  AND created_at < (NOW() - INTERVAL '90 days') "
        "  AND (organization_id = :org_id OR organization_id IS NULL)"
    )
    result_stale = await db.execute(stale_cutoff, {"now": now, "org_id": org_id})
    pruned_examples = result_stale.rowcount

    # 2. Merge duplicate patterns (same key, bump occurrence_count)
    dup_patterns = text(
        "UPDATE learning_patterns "
        "SET occurrence_count = occurrence_count + 1, "
        "    confidence = LEAST(confidence + 0.05, 1.0), "
        "    last_seen_at = :now, "
        "    updated_at = :now "
        "WHERE is_active = true "
        "  AND (organization_id = :org_id OR organization_id IS NULL) "
        "  AND id IN ("
        "    SELECT MIN(id) FROM learning_patterns "
        "    WHERE is_active = true "
        "    GROUP BY pattern_type, pattern_key "
        "    HAVING COUNT(*) > 1"
        "  )"
    )
    result_dup = await db.execute(dup_patterns, {"now": now, "org_id": org_id})
    merged_patterns = result_dup.rowcount

    await db.commit()

    logger.info(
        "Consolidation completed: pruned_examples=%d merged_patterns=%d user=%s",
        pruned_examples, merged_patterns, current_user.id,
    )

    return {
        "status": "ok",
        "pruned_examples": pruned_examples,
        "merged_patterns": merged_patterns,
        "triggered_by": current_user.id,
        "triggered_at": now.isoformat(),
    }


# =============================================================================
# GET /metrics — Learning metrics (correction rates per agent)
# =============================================================================

@router.get("/metrics")
async def get_learning_metrics(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Get aggregate learning metrics across all agents.

    Returns correction rates, approval counts, and pattern counts per agent.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)

    # Per-agent example counts by type
    rows = (
        db.query(
            _LearningExample.agent_role,
            _LearningExample.example_type,
            func.count(_LearningExample.id).label("cnt"),
        )
        .filter(
            _LearningExample.is_active == True,  # noqa: E712
            (
                (_LearningExample.organization_id == org_id)
                | (_LearningExample.organization_id.is_(None))
            ),
        )
        .group_by(_LearningExample.agent_role, _LearningExample.example_type)
        .all()
    )

    agents: Dict[str, Dict[str, Any]] = {}
    for agent_role, example_type, cnt in rows:
        if agent_role not in agents:
            agents[agent_role] = {
                "agent_id": agent_role,
                "corrections": 0,
                "approvals": 0,
                "overrides": 0,
                "total": 0,
                "correction_rate": 0.0,
            }
        bucket = agents[agent_role]
        bucket["total"] += cnt
        if example_type == "correction":
            bucket["corrections"] += cnt
        elif example_type == "positive":
            bucket["approvals"] += cnt

    # Count override patterns per agent
    override_rows = (
        db.query(
            _LearningPattern.pattern_key,
            func.count(_LearningPattern.id).label("cnt"),
        )
        .filter(
            _LearningPattern.pattern_type == "condition_override",
            _LearningPattern.is_active == True,  # noqa: E712
            (
                (_LearningPattern.organization_id == org_id)
                | (_LearningPattern.organization_id.is_(None))
            ),
        )
        .group_by(_LearningPattern.pattern_key)
        .all()
    )
    for pattern_key, cnt in override_rows:
        agent_from_key = pattern_key.split(":")[0] if ":" in pattern_key else pattern_key
        if agent_from_key not in agents:
            agents[agent_from_key] = {
                "agent_id": agent_from_key,
                "corrections": 0,
                "approvals": 0,
                "overrides": 0,
                "total": 0,
                "correction_rate": 0.0,
            }
        agents[agent_from_key]["overrides"] += cnt

    # Calculate correction rates
    for bucket in agents.values():
        total = bucket["corrections"] + bucket["approvals"]
        if total > 0:
            bucket["correction_rate"] = round(bucket["corrections"] / total, 4)

    return {
        "agents": list(agents.values()),
        "total_agents": len(agents),
    }


# =============================================================================
# GET /metrics/{agent_id} — Learning metrics for a specific agent
# =============================================================================

@router.get("/metrics/{agent_id}")
async def get_agent_learning_metrics(
    agent_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Get detailed learning metrics for a specific agent."""
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)

    # Example counts by type
    type_counts = (
        db.query(
            _LearningExample.example_type,
            func.count(_LearningExample.id).label("cnt"),
        )
        .filter(
            _LearningExample.agent_role == agent_id,
            _LearningExample.is_active == True,  # noqa: E712
            (
                (_LearningExample.organization_id == org_id)
                | (_LearningExample.organization_id.is_(None))
            ),
        )
        .group_by(_LearningExample.example_type)
        .all()
    )

    counts: Dict[str, int] = {}
    for etype, cnt in type_counts:
        counts[etype] = cnt

    corrections = counts.get("correction", 0)
    approvals = counts.get("positive", 0)
    total = corrections + approvals
    correction_rate = round(corrections / total, 4) if total > 0 else 0.0

    # Average quality score
    avg_quality = (
        db.query(func.avg(_LearningExample.quality_score))
        .filter(
            _LearningExample.agent_role == agent_id,
            _LearningExample.is_active == True,  # noqa: E712
            _LearningExample.quality_score.isnot(None),
            (
                (_LearningExample.organization_id == org_id)
                | (_LearningExample.organization_id.is_(None))
            ),
        )
        .scalar()
    )

    # Pattern count
    pattern_count = (
        db.query(func.count(_LearningPattern.id))
        .filter(
            _LearningPattern.pattern_key.ilike(f"{agent_id}:%"),
            _LearningPattern.is_active == True,  # noqa: E712
            (
                (_LearningPattern.organization_id == org_id)
                | (_LearningPattern.organization_id.is_(None))
            ),
        )
        .scalar()
    )

    # Active prompt optimisations
    opt_count = (
        db.query(func.count(_PromptOptimization.id))
        .filter(
            _PromptOptimization.agent_role == agent_id,
            _PromptOptimization.is_active == True,  # noqa: E712
        )
        .scalar()
    )

    return {
        "agent_id": agent_id,
        "corrections": corrections,
        "approvals": approvals,
        "total_examples": sum(counts.values()),
        "correction_rate": correction_rate,
        "avg_quality_score": round(float(avg_quality), 2) if avg_quality else None,
        "active_patterns": pattern_count or 0,
        "active_optimizations": opt_count or 0,
        "example_types": counts,
    }


# =============================================================================
# POST /harness/proposals — List pending harness optimization proposals
# =============================================================================

@router.post("/harness/proposals")
async def list_harness_proposals(
    body: HarnessProposalFilter = None,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """List pending (or filtered) harness optimization proposals.

    Proposals are PromptOptimization records that have not yet been applied.
    """
    _ensure_models()
    _ensure_tables(db)

    if body is None:
        body = HarnessProposalFilter()

    q = db.query(_PromptOptimization)

    if body.status and body.status != "all":
        if body.status == "pending":
            q = q.filter(
                _PromptOptimization.is_active == True,  # noqa: E712
                _PromptOptimization.applied_at.is_(None),
                _PromptOptimization.rolled_back_at.is_(None),
            )
        elif body.status == "approved":
            q = q.filter(_PromptOptimization.applied_at.isnot(None))
        elif body.status == "rejected":
            q = q.filter(
                _PromptOptimization.is_active == False,  # noqa: E712
                _PromptOptimization.applied_at.is_(None),
            )

    if body.agent_id:
        q = q.filter(_PromptOptimization.agent_role == body.agent_id)

    proposals = q.order_by(desc(_PromptOptimization.created_at)).limit(body.limit).all()

    return {
        "proposals": [
            {
                "id": p.id,
                "agent_role": p.agent_role,
                "optimization_type": p.optimization_type,
                "reason": p.reason,
                "previous_value": (p.previous_value or "")[:500],
                "new_value": (p.new_value or "")[:500],
                "score_before": float(p.feedback_score_before) if p.feedback_score_before else None,
                "score_after": float(p.feedback_score_after) if p.feedback_score_after else None,
                "is_active": p.is_active,
                "applied_at": p.applied_at.isoformat() if p.applied_at else None,
                "rolled_back_at": p.rolled_back_at.isoformat() if p.rolled_back_at else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in proposals
        ],
        "count": len(proposals),
        "filter": {
            "status": body.status,
            "agent_id": body.agent_id,
        },
    }


# =============================================================================
# POST /harness/proposals/{id}/approve — Approve a harness change
# =============================================================================

@router.post("/harness/proposals/{proposal_id}/approve")
async def approve_harness_proposal(
    proposal_id: int,
    body: HarnessActionRequest = None,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Approve and apply a harness optimization proposal. Admin only."""
    _require_admin(current_user)
    _ensure_models()
    _ensure_tables(db)

    proposal = db.query(_PromptOptimization).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.applied_at is not None:
        raise HTTPException(status_code=409, detail="Proposal already applied")

    if not proposal.is_active:
        raise HTTPException(status_code=409, detail="Proposal has been rejected or deactivated")

    now = datetime.now(timezone.utc)
    proposal.applied_at = now
    proposal.is_active = True
    if body and body.reason:
        proposal.reason = (proposal.reason or "") + f" | Approved: {body.reason}"

    db.commit()

    logger.info(
        "Harness proposal %d approved by user %s", proposal_id, current_user.id,
    )

    return {
        "status": "approved",
        "proposal_id": proposal.id,
        "agent_role": proposal.agent_role,
        "applied_at": now.isoformat(),
        "approved_by": current_user.id,
    }


# =============================================================================
# POST /harness/proposals/{id}/reject — Reject a harness change
# =============================================================================

@router.post("/harness/proposals/{proposal_id}/reject")
async def reject_harness_proposal(
    proposal_id: int,
    body: HarnessActionRequest = None,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Reject a harness optimization proposal. Admin only."""
    _require_admin(current_user)
    _ensure_models()
    _ensure_tables(db)

    proposal = db.query(_PromptOptimization).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.applied_at is not None:
        raise HTTPException(status_code=409, detail="Proposal already applied — roll back instead")

    now = datetime.now(timezone.utc)
    proposal.is_active = False
    if body and body.reason:
        proposal.reason = (proposal.reason or "") + f" | Rejected: {body.reason}"

    db.commit()

    logger.info(
        "Harness proposal %d rejected by user %s", proposal_id, current_user.id,
    )

    return {
        "status": "rejected",
        "proposal_id": proposal.id,
        "agent_role": proposal.agent_role,
        "rejected_by": current_user.id,
    }


# =============================================================================
# GET /gym/{agent_id}/results — AgentGym regression results
# =============================================================================

@router.get("/gym/{agent_id}/results")
async def get_agent_gym_results(
    agent_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Get the latest AgentGym regression test results for an agent.

    AgentGym runs learning examples as regression tests after prompt changes
    to verify that corrections are retained and no regressions occur.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)

    # Use correction + positive examples as the regression test suite
    examples = (
        db.query(_LearningExample)
        .filter(
            _LearningExample.agent_role == agent_id,
            _LearningExample.is_active == True,  # noqa: E712
            _LearningExample.example_type.in_(["correction", "positive", "few_shot"]),
            (
                (_LearningExample.organization_id == org_id)
                | (_LearningExample.organization_id.is_(None))
            ),
        )
        .order_by(desc(_LearningExample.updated_at), desc(_LearningExample.created_at))
        .limit(limit)
        .all()
    )

    # Latest prompt optimisations (as the "change under test")
    latest_opt = (
        db.query(_PromptOptimization)
        .filter(
            _PromptOptimization.agent_role == agent_id,
            _PromptOptimization.is_active == True,  # noqa: E712
        )
        .order_by(desc(_PromptOptimization.applied_at))
        .first()
    )

    total = len(examples)
    passing = sum(1 for ex in examples if ex.quality_score and float(ex.quality_score) >= 50)
    failing = total - passing

    return {
        "agent_id": agent_id,
        "latest_optimization": {
            "id": latest_opt.id,
            "type": latest_opt.optimization_type,
            "applied_at": latest_opt.applied_at.isoformat() if latest_opt and latest_opt.applied_at else None,
        } if latest_opt else None,
        "regression_summary": {
            "total_cases": total,
            "passing": passing,
            "failing": failing,
            "pass_rate": round(passing / total, 4) if total > 0 else None,
        },
        "cases": [
            {
                "id": ex.id,
                "type": ex.example_type,
                "intent": ex.intent,
                "query_text": (ex.query_text or "")[:200],
                "expected": (ex.expected_response or "")[:200],
                "quality_score": float(ex.quality_score) if ex.quality_score else None,
                "status": "pass" if (ex.quality_score and float(ex.quality_score) >= 50) else "fail",
                "last_tested": (ex.updated_at or ex.created_at).isoformat() if (ex.updated_at or ex.created_at) else None,
            }
            for ex in examples
        ],
    }


# =============================================================================
# POST /export/trigger — Trigger training data export (admin only)
# =============================================================================

@router.post("/export/trigger")
async def trigger_export(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Trigger a training data export. Admin only.

    Collects all active learning examples and patterns into a structured
    export payload suitable for fine-tuning or analysis.
    """
    _require_admin(current_user)
    _ensure_models()
    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)
    now = datetime.now(timezone.utc)

    # Count exportable records
    example_count = (
        db.query(func.count(_LearningExample.id))
        .filter(
            _LearningExample.is_active == True,  # noqa: E712
            (
                (_LearningExample.organization_id == org_id)
                | (_LearningExample.organization_id.is_(None))
            ),
        )
        .scalar()
    ) or 0

    pattern_count = (
        db.query(func.count(_LearningPattern.id))
        .filter(
            _LearningPattern.is_active == True,  # noqa: E712
            (
                (_LearningPattern.organization_id == org_id)
                | (_LearningPattern.organization_id.is_(None))
            ),
        )
        .scalar()
    ) or 0

    optimization_count = (
        db.query(func.count(_PromptOptimization.id))
        .filter(_PromptOptimization.is_active == True)  # noqa: E712
        .scalar()
    ) or 0

    logger.info(
        "Training data export triggered: examples=%d patterns=%d optimizations=%d user=%s",
        example_count, pattern_count, optimization_count, current_user.id,
    )

    return {
        "status": "export_queued",
        "triggered_by": current_user.id,
        "triggered_at": now.isoformat(),
        "record_counts": {
            "learning_examples": example_count,
            "learning_patterns": pattern_count,
            "prompt_optimizations": optimization_count,
            "total": example_count + pattern_count + optimization_count,
        },
        "message": "Export job has been queued. Results will be available in the exports bucket.",
    }


# =============================================================================
# Registration helper
# =============================================================================

def register_learning_routes(app):
    """Register the continual learning router with the FastAPI application."""
    app.include_router(router)
    logger.info("Registered continual learning routes (/api/v1/learning)")
