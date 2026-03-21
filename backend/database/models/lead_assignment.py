"""
Lead Assignment Configuration Models

Configurable rule-based lead assignment with multiple distribution strategies.
Supports round-robin, weighted, geographic, load-balanced, and rule-based routing
with capacity management, PTO exceptions, and full audit trail.

Models:
    - LeadAssignmentConfig: Organization-level assignment strategy settings
    - LeadAssignmentRule: Condition-based routing rules with priority ordering
    - LeadAssignmentPool: Pool of LOs eligible for automatic assignment
    - LeadAssignmentException: Temporary blocks (PTO, capacity override)
    - LeadAssignmentAuditLog: Append-only audit trail for every assignment decision

Usage:
    from database.models.lead_assignment import LeadAssignmentConfig, LeadAssignmentRule

    config = db.query(LeadAssignmentConfig).filter(
        LeadAssignmentConfig.organization_id == org_id,
    ).first()
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
    Numeric,
)

from db import Base


def utcnow():
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class LeadAssignmentConfig(Base):
    """Organization-level lead assignment configuration.

    Stores the active assignment strategy and global settings for how new
    leads are distributed to loan officers within the organization.

    Strategies:
        round_robin   - Rotate evenly through pool members
        weighted      - Distribute based on weight percentages
        geographic    - Route by lead state/zip to specific LOs
        load_balanced - Assign to LO with fewest active leads
        rule_based    - Evaluate LeadAssignmentRules in priority order
        manual        - No auto-assignment; leads land in unassigned queue
    """

    __tablename__ = "lead_assignment_configs"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, unique=True
    )

    # Active strategy
    strategy = Column(String(30), nullable=False, default="round_robin")

    # Global settings
    fallback_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    respect_capacity = Column(Boolean, default=True)
    max_daily_leads_per_user = Column(Integer, default=50)
    business_hours_only = Column(Boolean, default=False)
    business_hours_start = Column(String(5), default="08:00")  # HH:MM
    business_hours_end = Column(String(5), default="18:00")
    business_hours_timezone = Column(String(50), default="America/New_York")

    # Speed-to-lead: auto-notify assigned LO
    notify_on_assignment = Column(Boolean, default=True)
    notification_channels = Column(JSON, default=["email"])  # email, sms, push

    # Round-robin state (last assigned index)
    round_robin_index = Column(Integer, default=0)

    # Deduplication
    dedup_enabled = Column(Boolean, default=True)
    dedup_match_fields = Column(JSON, default=["email", "phone"])
    dedup_window_days = Column(Integer, default=30)
    dedup_action = Column(String(20), default="merge")  # merge, update, reject

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("ix_lead_assign_config_org", "organization_id", unique=True),
    )


class LeadAssignmentRule(Base):
    """Condition-based lead assignment rule.

    Rules are evaluated in priority order (lower number = higher priority).
    When a lead matches all conditions in a rule, the lead is assigned
    according to the rule's target configuration.

    Conditions JSON schema:
        [
            {"field": "loan_amount", "op": "gte", "value": 500000},
            {"field": "state", "op": "in", "value": ["CA", "TX", "NY"]},
            {"field": "source", "op": "eq", "value": "zillow"},
            {"field": "credit_score", "op": "gte", "value": 700},
            {"field": "loan_purpose", "op": "eq", "value": "purchase"},
            {"field": "property_type", "op": "eq", "value": "multi_family"},
        ]

    Supported operators: eq, neq, in, not_in, gt, gte, lt, lte, contains

    Target config JSON schema (varies by target_type):
        USER:       {"user_id": 123}
        POOL:       {"pool_id": 5}
        ROUND_ROBIN: {"user_ids": [1, 2, 3]}
        ROLE:       {"role": "senior_lo"}
    """

    __tablename__ = "lead_assignment_rules"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    rule_name = Column(String(200), nullable=False)
    description = Column(String(500))
    priority = Column(Integer, default=100)  # Lower = higher priority
    conditions = Column(JSON, nullable=False)  # [{field, op, value}]
    match_type = Column(String(10), default="ALL")  # ALL or ANY

    # Target assignment
    target_type = Column(String(30), nullable=False)  # USER, POOL, ROUND_ROBIN, ROLE
    target_config = Column(JSON, nullable=False)

    is_active = Column(Boolean, default=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_lead_assign_rules_org_priority", "organization_id", "priority"),
        Index("ix_lead_assign_rules_org_active", "organization_id", "is_active"),
    )


class LeadAssignmentPool(Base):
    """Pool of loan officers eligible for lead assignment.

    Each pool member has a weight (for weighted distribution) and
    capacity tracking. Members can be temporarily deactivated without
    removing them from the pool.
    """

    __tablename__ = "lead_assignment_pool"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    weight = Column(Integer, default=100)  # Relative weight (higher = more leads)
    max_daily_leads = Column(Integer, default=50)
    is_active = Column(Boolean, default=True)
    geographic_states = Column(JSON)  # ["CA", "TX"] or null for all
    specialties = Column(JSON)  # ["jumbo", "va", "fha"] or null for all
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_lead_assign_pool_org_user", "organization_id", "user_id", unique=True),
        Index("ix_lead_assign_pool_org_active", "organization_id", "is_active"),
    )


class LeadAssignmentException(Base):
    """Temporary assignment exception (PTO, capacity override, blocked).

    When an exception is active for a user, that user is excluded from
    automatic assignment during the exception period.
    """

    __tablename__ = "lead_assignment_exceptions"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exception_type = Column(String(30), nullable=False)
    # PTO, CAPACITY_OVERRIDE, BLOCKED, TRAINING
    reason = Column(String(500))
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)  # null = indefinite
    is_active = Column(Boolean, default=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_lead_assign_exc_org_user", "organization_id", "user_id"),
        Index("ix_lead_assign_exc_active", "organization_id", "is_active"),
    )


class LeadAssignmentAuditLog(Base):
    """Append-only audit trail for lead assignment decisions.

    Every assignment (auto or manual) is recorded for compliance,
    analytics, and debugging.
    """

    __tablename__ = "lead_assignment_audit_log"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)

    action = Column(String(50), nullable=False)
    # ASSIGNED, REASSIGNED, AUTO_ASSIGNED, MANUAL_OVERRIDE, RULE_MATCH, FALLBACK

    strategy_used = Column(String(30))  # round_robin, weighted, etc.
    rule_id = Column(Integer, ForeignKey("lead_assignment_rules.id"), nullable=True)
    rule_name = Column(String(200))

    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    decision_reason = Column(Text)  # Human-readable explanation
    event_data = Column(JSON)  # Full snapshot: conditions evaluated, candidates, scores

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_lead_assign_audit_org", "organization_id", "created_at"),
        Index("ix_lead_assign_audit_lead", "lead_id", "created_at"),
    )
