"""
Smart Docs Escalation Rule & Event Models

Tracks rule-based escalation chains and individual escalation events
for document overdue, fraud detection, SLA breaches, and more.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON, Text,
    ForeignKey, Index, Float,
)
from db import Base


def utcnow():
    return datetime.now(timezone.utc)


class EscalationRule(Base):
    """Configurable escalation rule with multi-level chain."""
    __tablename__ = "smart_docs_escalation_rules"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    rule_name = Column(String(200), nullable=False)
    trigger_type = Column(String(50), nullable=False)
    # Triggers: DOC_OVERDUE, CONDITION_OVERDUE, SLA_BREACH, FRAUD_DETECTED,
    #           INCOME_DISCREPANCY, APPROVAL_TIMEOUT, BORROWER_UNRESPONSIVE
    trigger_config = Column(JSON, nullable=False)  # {threshold_days: 5, severity: "high"}
    escalation_chain = Column(JSON, nullable=False)
    # [{level: 1, notify: "loan_officer", after_hours: 0},
    #  {level: 2, notify: "processor_manager", after_hours: 24},
    #  {level: 3, notify: "branch_manager", after_hours: 48}]
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


class EscalationEvent(Base):
    """Individual escalation event tied to a rule and loan."""
    __tablename__ = "smart_docs_escalation_events"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("smart_docs_escalation_rules.id"), nullable=False)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)
    trigger_type = Column(String(50), nullable=False)
    trigger_details = Column(JSON)
    current_level = Column(Integer, default=1)
    status = Column(String(20), default="ACTIVE")  # ACTIVE, RESOLVED, EXPIRED, SUPPRESSED
    escalated_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime)
    acknowledged_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text)
    next_escalation_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index('ix_escalation_events_status', 'organization_id', 'status'),
        Index('ix_escalation_events_next', 'status', 'next_escalation_at'),
    )
