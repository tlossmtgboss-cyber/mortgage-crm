"""
AI Activity Feed Routes — Per-loan AI agent activity log.

Records and retrieves structured events from all 22 AI agents
(guidelines, deal-breaker, call-intel, marketing, etc.) for display
in the loan-detail Activity Feed panel.

Prefix: /api/v1/loans/{loan_id}/ai-activity
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import Session

from db import get_db, Base, engine
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/loans", tags=["AI Activity Feed"])


# =============================================================================
# SQLAlchemy Model
# =============================================================================

class AIActivityLog(Base):
    __tablename__ = "ai_activity_log"
    __table_args__ = (
        Index("ix_ai_activity_loan_created", "loan_id", "created_at"),
        Index("ix_ai_activity_org_id", "organization_id"),
        Index("ix_ai_activity_agent_type", "agent_type"),
        Index("ix_ai_activity_outcome", "outcome"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)
    agent_type = Column(String, nullable=False)
    agent_label = Column(String, nullable=False)
    action_title = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    outcome = Column(String, nullable=False)
    outcome_label = Column(String, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    detail_sections = Column(JSON, nullable=True)
    stats = Column(JSON, nullable=True)
    is_live = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# =============================================================================
# Pydantic Schemas
# =============================================================================

VALID_AGENT_TYPES = {
    "guidelines", "deal-breaker", "call-intel", "marketing", "bulletin",
    "smart-docs", "turn-down", "aria", "underwriting", "lead-assignment",
}

VALID_OUTCOMES = {"success", "warning", "critical", "info", "pending"}


class DetailSection(BaseModel):
    label: str
    content: str


class StatItem(BaseModel):
    value: str
    label: str


class AIActivityCreate(BaseModel):
    agent_type: str = Field(..., description="Agent identifier: guidelines, deal-breaker, call-intel, etc.")
    agent_label: str = Field(..., max_length=255, description="Display name for the agent")
    action_title: str = Field(..., max_length=500, description="Short action description")
    summary: str = Field(..., description="Detailed summary of what the agent did")
    outcome: str = Field(..., description="success, warning, critical, info, or pending")
    outcome_label: str = Field(..., max_length=255, description="Human-readable outcome label")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Arbitrary key-value metadata")
    detail_sections: Optional[List[DetailSection]] = Field(None, description="Expandable detail sections")
    stats: Optional[List[StatItem]] = Field(None, description="Key metric cards")
    is_live: bool = Field(False, description="Whether this is a live/streaming event")


class AIActivityResponse(BaseModel):
    id: int
    loan_id: int
    agent_type: str
    agent_label: str
    action_title: str
    summary: str
    outcome: str
    outcome_label: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None
    detail_sections: Optional[List[DetailSection]] = None
    stats: Optional[List[StatItem]] = None
    is_live: bool = False

    class Config:
        from_attributes = True


class AIActivityListResponse(BaseModel):
    items: List[AIActivityResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# Table creation helper
# =============================================================================

_table_ensured = False


def _ensure_table():
    """Create ai_activity_log table if it doesn't exist (production-safe)."""
    global _table_ensured
    if _table_ensured:
        return
    try:
        AIActivityLog.__table__.create(engine, checkfirst=True)
        _table_ensured = True
    except Exception as e:
        logger.warning(f"AI activity table creation check failed (non-fatal): {e}")


# =============================================================================
# Helper — row to dict
# =============================================================================

def _row_to_dict(row: AIActivityLog) -> dict:
    return {
        "id": row.id,
        "loan_id": row.loan_id,
        "agent_type": row.agent_type,
        "agent_label": row.agent_label,
        "action_title": row.action_title,
        "summary": row.summary,
        "outcome": row.outcome,
        "outcome_label": row.outcome_label,
        "created_at": row.created_at,
        "metadata": row.metadata_,
        "detail_sections": row.detail_sections,
        "stats": row.stats,
        "is_live": row.is_live,
    }


# =============================================================================
# Routes
# =============================================================================

@router.get("/{loan_id}/ai-activity", response_model=AIActivityListResponse)
async def list_ai_activity(
    loan_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    agent_type: Optional[str] = Query(default=None, description="Filter by agent type"),
    outcome: Optional[str] = Query(default=None, description="Filter by outcome"),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    List AI activity events for a loan, ordered newest first.

    Supports filtering by agent_type and outcome. Results are
    scoped to the current user's organization for tenant isolation.
    """
    _ensure_table()
    org_id = current_user.organization_id

    # Validate filter values
    if agent_type and agent_type not in VALID_AGENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent_type. Must be one of: {', '.join(sorted(VALID_AGENT_TYPES))}",
        )
    if outcome and outcome not in VALID_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome. Must be one of: {', '.join(sorted(VALID_OUTCOMES))}",
        )

    # Build query with tenant isolation
    query = db.query(AIActivityLog).filter(
        AIActivityLog.loan_id == loan_id,
        AIActivityLog.organization_id == org_id,
    )

    if agent_type:
        query = query.filter(AIActivityLog.agent_type == agent_type)
    if outcome:
        query = query.filter(AIActivityLog.outcome == outcome)

    total = query.count()

    rows = (
        query
        .order_by(AIActivityLog.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{loan_id}/ai-activity", response_model=AIActivityResponse, status_code=201)
async def create_ai_activity(
    loan_id: int,
    body: AIActivityCreate,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Log a new AI activity event for a loan.

    Called by AI agents after completing an action. The event is
    automatically scoped to the current user's organization.
    """
    _ensure_table()
    org_id = current_user.organization_id

    # Validate agent_type
    if body.agent_type not in VALID_AGENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent_type '{body.agent_type}'. Must be one of: {', '.join(sorted(VALID_AGENT_TYPES))}",
        )

    # Validate outcome
    if body.outcome not in VALID_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome '{body.outcome}'. Must be one of: {', '.join(sorted(VALID_OUTCOMES))}",
        )

    # Verify loan belongs to the user's organization
    from database.models.lead_loan import Loan
    loan = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.organization_id == org_id,
    ).first()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Serialize nested Pydantic models to dicts for JSON storage
    detail_sections_data = (
        [s.model_dump() for s in body.detail_sections]
        if body.detail_sections else None
    )
    stats_data = (
        [s.model_dump() for s in body.stats]
        if body.stats else None
    )

    record = AIActivityLog(
        organization_id=org_id,
        loan_id=loan_id,
        agent_type=body.agent_type,
        agent_label=body.agent_label,
        action_title=body.action_title,
        summary=body.summary,
        outcome=body.outcome,
        outcome_label=body.outcome_label,
        metadata_=body.metadata,
        detail_sections=detail_sections_data,
        stats=stats_data,
        is_live=body.is_live,
        created_at=datetime.now(timezone.utc),
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    logger.info(
        "AI activity logged: loan_id=%s agent=%s outcome=%s",
        loan_id, body.agent_type, body.outcome,
    )

    return _row_to_dict(record)


# =============================================================================
# Registration
# =============================================================================

def register_ai_activity_routes(app):
    """Register AI activity feed routes with the FastAPI app."""
    _ensure_table()
    app.include_router(router)
    logger.info("AI activity feed routes registered")
