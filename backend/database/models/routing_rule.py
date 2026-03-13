"""
Smart Docs Document Routing Rule & Processing Queue Models

Configurable rule-based routing for document assignments. Supports multiple
routing strategies (auto-assign, round-robin, load-balanced, skill-based,
escalation), condition matching on document and loan attributes, and named
processing queues with capacity management.

Models:
    - RoutingRule: Defines conditions and target for document assignment
    - ProcessingQueue: Named queue with assigned users and capacity limits
    - RoutingAuditLog: Append-only audit trail for every routing decision

Usage:
    from database.models.routing_rule import RoutingRule, ProcessingQueue

    rules = db.query(RoutingRule).filter(
        RoutingRule.organization_id == org_id,
        RoutingRule.is_active == True,
    ).order_by(RoutingRule.priority.asc()).all()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    JSON,
    Text,
    ForeignKey,
    Index,
)

from db import Base


def utcnow():
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class RoutingRule(Base):
    """Configurable document routing rule.

    Rule types:
        AUTO_ASSIGN   - Direct assignment to specific user/role based on conditions
        ROUND_ROBIN   - Distribute evenly across team members
        LOAD_BALANCED - Assign to person with lightest current workload
        SKILL_BASED   - Route complex docs to experienced processors
        ESCALATION    - Route based on urgency/priority level

    Conditions JSON schema:
        [
            {"field": "doc_type", "op": "in", "value": ["TAX_RETURN", "SCHEDULE_C"]},
            {"field": "loan_amount", "op": "gt", "value": 500000},
            {"field": "loan_type", "op": "eq", "value": "FHA"},
            {"field": "loan_stage", "op": "in", "value": ["UNDERWRITING", "SUBMITTED"]},
            {"field": "borrower_language", "op": "eq", "value": "es"},
            {"field": "complexity_score", "op": "gte", "value": 7},
            {"field": "branch_id", "op": "eq", "value": 42},
        ]

    Supported operators: eq, neq, in, not_in, gt, gte, lt, lte, contains

    Target config JSON schema (varies by target_type):
        USER:  {"user_id": 123}
        ROLE:  {"role": "senior_processor"}
        TEAM:  {"team_id": 5}
        QUEUE: {"queue_name": "complex_income"}
    """

    __tablename__ = "smart_docs_routing_rules"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    rule_name = Column(String(200), nullable=False)
    rule_type = Column(String(50), nullable=False)
    # AUTO_ASSIGN, ROUND_ROBIN, LOAD_BALANCED, SKILL_BASED, ESCALATION
    priority = Column(Integer, default=100)  # Lower number = higher priority
    conditions = Column(JSON)
    target_type = Column(String(30), nullable=False)  # USER, ROLE, TEAM, QUEUE
    target_config = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # System-provided default rules
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_routing_rules_org_priority", "organization_id", "priority"),
        Index("ix_routing_rules_org_active", "organization_id", "is_active"),
    )


class ProcessingQueue(Base):
    """Named processing queue with capacity limits and assigned users.

    Queues represent logical work buckets (income_review, bank_analysis,
    fraud_check, esign_closing, etc.) that documents flow into before
    being picked up by a processor.
    """

    __tablename__ = "smart_docs_processing_queues"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    queue_name = Column(String(100), nullable=False)
    description = Column(String(500))
    assigned_users = Column(JSON)  # [user_id, ...]
    max_items = Column(Integer, default=50)
    current_count = Column(Integer, default=0)
    avg_processing_time_hours = Column(Integer, default=4)
    priority_weight = Column(Integer, default=100)  # Lower = higher queue priority
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index(
            "ix_queues_org_name",
            "organization_id",
            "queue_name",
            unique=True,
        ),
    )


class RoutingAuditLog(Base):
    """Append-only audit trail for routing decisions.

    Every routing decision (assignment, reassignment, queue placement,
    dry-run test) is recorded here for analytics and compliance.
    """

    __tablename__ = "smart_docs_routing_audit_log"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    document_id = Column(Integer, nullable=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True, index=True)

    action = Column(String(50), nullable=False)
    # ROUTED, REASSIGNED, QUEUED, DEQUEUED, REBALANCED, DRY_RUN, RULE_CONFLICT

    rule_id = Column(Integer, ForeignKey("smart_docs_routing_rules.id"), nullable=True)
    rule_name = Column(String(200))
    rule_type = Column(String(50))

    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    queue_name = Column(String(100))

    event_data = Column(JSON)  # Full snapshot of conditions evaluated
    decision_reason = Column(Text)
    is_dry_run = Column(Boolean, default=False)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_routing_audit_org_action", "organization_id", "action"),
        Index("ix_routing_audit_doc", "document_id", "created_at"),
    )
