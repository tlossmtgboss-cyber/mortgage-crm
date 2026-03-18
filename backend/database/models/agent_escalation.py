"""
Agent Escalation Model

Tracks AI agent → human handoff escalations with full context preservation,
priority-based routing, and resolution lifecycle management.

Distinct from:
- EscalationRecord (task.py): CRM workflow task escalations (SLA breaches, etc.)
- live_agent_escalation_service.py: Real-time voice call AI → human transfers

This model covers AI agent *tool/role* escalations — when an AI agent operating
on behalf of a pipeline_analyst, compliance_checker, lead_nurturer, or
document_tracker encounters a situation it cannot resolve autonomously.

Usage:
    from database.models.agent_escalation import AgentEscalation
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship
import enum

from db import Base


# ============================================================================
# ENUMS
# ============================================================================

class EscalationReason(str, enum.Enum):
    """Why the AI agent escalated to a human."""
    CONFIDENCE_LOW = "confidence_low"
    SENSITIVE_DATA = "sensitive_data"
    COMPLIANCE_REQUIRED = "compliance_required"
    USER_REQUESTED = "user_requested"
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"


class EscalationPriority(str, enum.Enum):
    """Urgency level of the escalation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationStatus(str, enum.Enum):
    """Lifecycle status of the escalation."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    EXPIRED = "expired"


# ============================================================================
# MODEL
# ============================================================================

class AgentEscalation(Base):
    """AI agent escalation record for AI → human handoff tracking.

    Created when an AI agent determines it cannot handle a request autonomously
    and needs human intervention. Captures the full context of the AI's partial
    work so the human assignee can pick up without requiring the user to repeat
    information.
    """
    __tablename__ = "agent_escalations"
    __table_args__ = (
        Index("ix_agent_esc_org_id", "organization_id"),
        Index("ix_agent_esc_status", "status"),
        Index("ix_agent_esc_priority", "priority"),
        Index("ix_agent_esc_assigned_to", "assigned_to"),
        Index("ix_agent_esc_org_status", "organization_id", "status"),
        Index("ix_agent_esc_agent_role", "agent_role"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    # AI agent context
    agent_role = Column(String(100), nullable=False)  # pipeline_analyst, compliance_checker, etc.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # User who was interacting with the AI

    # Escalation details
    reason = Column(String(50), nullable=False)   # EscalationReason value
    priority = Column(String(20), nullable=False, default="medium")  # EscalationPriority value
    status = Column(String(20), nullable=False, default="pending")   # EscalationStatus value

    # Context payload — everything the human needs to continue
    context = Column(JSON, nullable=True)
    # Expected shape:
    # {
    #   "partial_response": str,       # AI's incomplete answer (for CONFIDENCE_LOW)
    #   "tools_attempted": [str],      # Tools the AI tried
    #   "error_details": str,          # For TOOL_FAILURE
    #   "loan_id": int | None,         # Active loan if applicable
    #   "lead_id": int | None,         # Active lead if applicable
    #   "user_query": str,             # Original user question
    #   "conversation_summary": str,   # Conversation context
    # }

    # Assignment
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    suggested_assignee_role = Column(String(100), nullable=True)  # compliance_officer, branch_manager, etc.

    # Resolution
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc),
                        nullable=False)

    # Relationships
    organization = relationship("Organization", foreign_keys=[organization_id])
    requesting_user = relationship("User", foreign_keys=[user_id])
    assignee = relationship("User", foreign_keys=[assigned_to])
    resolver = relationship("User", foreign_keys=[resolved_by])


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "AgentEscalation",
    "EscalationReason",
    "EscalationPriority",
    "EscalationStatus",
]
