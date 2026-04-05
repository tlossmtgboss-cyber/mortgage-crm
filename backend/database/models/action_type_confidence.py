"""
Action Type Confidence Model

Tracks per-action-type confidence scores that drive the autonomous agent
graduation system.  As agents execute actions and humans approve/reject them,
the confidence score for each (org, action_type) pair moves toward or away
from the auto-execute threshold.

When confidence >= AI_AUTO_EXECUTE_THRESHOLD (0.950), new AgentActions of
that type are created with requires_approval=False — the agent acts
autonomously.

Tables:
- action_type_confidence: Per-org, per-action-type confidence tracking
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, Numeric, String,
    Boolean, UniqueConstraint,
)

from db import Base


class ActionTypeConfidence(Base):
    """
    Tracks confidence for a specific action type within an organization.

    The graduation loop:
    1. Agent proposes an action → AgentAction(requires_approval=True)
    2. Human approves or rejects
    3. ConfidenceGraduationService updates this record
    4. When approval_rate >= threshold AND total_decisions >= min_sample,
       the action type graduates → future actions auto-execute
    """

    __tablename__ = "action_type_confidence"
    __table_args__ = (
        UniqueConstraint("organization_id", "action_type", name="uq_atc_org_action"),
        Index("ix_atc_org_graduated", "organization_id", "is_graduated"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True,
    )

    # Action classification — matches AgentAction.action_type values
    action_type = Column(String(50), nullable=False, index=True)

    # Confidence tracking
    confidence_score = Column(
        Numeric(5, 4), nullable=False, default=0.0,
    )  # 0.0000 – 1.0000

    # Decision counters
    total_proposed = Column(Integer, nullable=False, default=0)
    total_approved = Column(Integer, nullable=False, default=0)
    total_rejected = Column(Integer, nullable=False, default=0)
    total_auto_executed = Column(Integer, nullable=False, default=0)

    # Graduation state
    is_graduated = Column(Boolean, nullable=False, default=False)
    graduated_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Bookkeeping
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def total_decisions(self) -> int:
        return (self.total_approved or 0) + (self.total_rejected or 0)

    @property
    def approval_rate(self) -> float:
        if self.total_decisions == 0:
            return 0.0
        return (self.total_approved or 0) / self.total_decisions

    def __repr__(self) -> str:
        return (
            f"<ActionTypeConfidence org={self.organization_id} "
            f"action={self.action_type!r} score={self.confidence_score} "
            f"graduated={self.is_graduated}>"
        )


def create_tables_if_needed(engine):
    """Create action_type_confidence table if it doesn't exist."""
    ActionTypeConfidence.__table__.create(engine, checkfirst=True)
