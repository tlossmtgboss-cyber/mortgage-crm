"""
Approval Chain Models (Smart Docs V2 Enterprise)

Multi-step approval workflow configuration with delegation support,
timeout handling, and separation-of-duties enforcement.

Key tables:
    smart_docs_approval_chains    - Configurable approval chain definitions
    smart_docs_approval_requests  - In-flight approval requests
    smart_docs_approval_decisions - Individual step decisions (append-only audit)
    smart_docs_approval_delegations - Temporary/permanent delegation rules

Usage:
    from database.models.approval_chain import (
        ApprovalChainConfig,
        ApprovalRequest,
        ApprovalDecision,
        ApprovalDelegation,
        ApprovalType,
        ApprovalRequestStatus,
        DecisionVerdict,
        TimeoutAction,
        DelegationType,
    )
"""

from datetime import datetime, timezone
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum

from db import Base


__all__ = [
    # Enums
    "ApprovalType",
    "ApprovalRequestStatus",
    "DecisionVerdict",
    "TimeoutAction",
    "DelegationType",
    # Models
    "ApprovalChainConfig",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalDelegation",
]


def utcnow():
    return datetime.now(timezone.utc)


# =============================================================================
# ENUMS
# =============================================================================

class ApprovalType(str, enum.Enum):
    """Categories of approval chains."""
    INCOME_APPROVAL = "INCOME_APPROVAL"
    DOCUMENT_APPROVAL = "DOCUMENT_APPROVAL"
    EXCEPTION_APPROVAL = "EXCEPTION_APPROVAL"
    FRAUD_CLEARANCE = "FRAUD_CLEARANCE"
    CONDITION_WAIVER = "CONDITION_WAIVER"
    PACKAGE_APPROVAL = "PACKAGE_APPROVAL"
    HIGH_VALUE_APPROVAL = "HIGH_VALUE_APPROVAL"


class ApprovalRequestStatus(str, enum.Enum):
    """Lifecycle of an approval request."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class DecisionVerdict(str, enum.Enum):
    """Possible decisions at each approval step."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"


class TimeoutAction(str, enum.Enum):
    """What happens when a step times out."""
    ESCALATE = "escalate"
    AUTO_APPROVE = "auto_approve"
    AUTO_REJECT = "auto_reject"


class DelegationType(str, enum.Enum):
    """Delegation scope."""
    OUT_OF_OFFICE = "out_of_office"
    PERMANENT = "permanent"


# =============================================================================
# APPROVAL CHAIN CONFIG
# =============================================================================

class ApprovalChainConfig(Base):
    """Per-organization approval chain definition.

    Each chain has ordered steps, optional conditional triggers, and
    auto-approve rules for low-risk items.

    Steps JSON format:
        [
            {
                "step": 1,
                "approver_type": "role",       # "role" or "user"
                "approver": "processor",        # role name or user ID
                "required": true,               # skip if false and auto-approve conditions met
                "parallel_approvers": null,      # list of additional approvers for parallel mode
                "timeout_hours": 24,            # step-level override
                "condition": null               # e.g. {"min_loan_amount": 500000}
            }
        ]

    Conditions JSON format:
        {
            "min_loan_amount": 500000,
            "max_loan_amount": null,
            "doc_types": ["TAX_RETURN", "BANK_STATEMENT"],
            "loan_types": ["jumbo", "non_qm"],
            "property_types": ["multi_family"]
        }

    Auto-approve conditions JSON format:
        {
            "ai_confidence_above": 0.95,
            "amount_below": 100000,
            "doc_types": ["paystubs"]
        }
    """
    __tablename__ = "smart_docs_approval_chains"
    __table_args__ = (
        Index("ix_approval_chains_org_type", "organization_id", "approval_type"),
        Index("ix_approval_chains_org_active", "organization_id", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True,
    )
    chain_name = Column(String(200), nullable=False)
    approval_type = Column(String(50), nullable=False)
    conditions = Column(JSON)
    steps = Column(JSON, nullable=False)
    auto_approve_conditions = Column(JSON)
    timeout_hours = Column(Integer, default=24)
    timeout_action = Column(String(30), default="escalate")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# =============================================================================
# APPROVAL REQUEST
# =============================================================================

class ApprovalRequest(Base):
    """In-flight approval request tied to a chain, loan, and entity.

    request_data JSON holds context the approver needs to make a decision:
        {
            "justification": "Borrower submitted amended tax return...",
            "ai_confidence": 0.87,
            "income_variance_pct": 12.3,
            "document_ids": [101, 102],
            "flags": ["declining_income"],
        }
    """
    __tablename__ = "smart_docs_approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_org_status", "organization_id", "status"),
        Index("ix_approval_requests_loan", "loan_id", "status"),
        Index("ix_approval_requests_chain", "chain_id"),
        Index("ix_approval_requests_requested_by", "requested_by_user_id"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True,
    )
    chain_id = Column(
        Integer, ForeignKey("smart_docs_approval_chains.id"), nullable=False,
    )
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    current_step = Column(Integer, default=1)
    status = Column(String(20), default="PENDING")
    request_data = Column(JSON)
    requested_by_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime)


# =============================================================================
# APPROVAL DECISION
# =============================================================================

class ApprovalDecision(Base):
    """Individual approval step decision (append-only audit trail).

    conditions_added JSON captures conditions attached to a conditional approval:
        [
            {"description": "Provide additional VOE within 5 business days"},
            {"description": "Verbal VOE required before CTC"},
        ]
    """
    __tablename__ = "smart_docs_approval_decisions"
    __table_args__ = (
        Index("ix_approval_decisions_request", "approval_request_id"),
        Index("ix_approval_decisions_approver", "approver_user_id"),
    )

    id = Column(Integer, primary_key=True)
    approval_request_id = Column(
        Integer,
        ForeignKey("smart_docs_approval_requests.id"),
        nullable=False,
        index=True,
    )
    step_number = Column(Integer, nullable=False)
    approver_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    decision = Column(String(20), nullable=False)
    comments = Column(Text)
    conditions_added = Column(JSON)
    decided_at = Column(DateTime, default=utcnow)


# =============================================================================
# APPROVAL DELEGATION
# =============================================================================

class ApprovalDelegation(Base):
    """Delegation rules for approval authority.

    Supports out-of-office (time-bounded) and permanent delegation.
    approval_types JSON is a list of ApprovalType values this delegation
    covers, or null for all types.
    """
    __tablename__ = "smart_docs_approval_delegations"
    __table_args__ = (
        Index("ix_approval_delegations_from", "organization_id", "from_user_id"),
        Index("ix_approval_delegations_to", "organization_id", "to_user_id"),
        Index("ix_approval_delegations_active", "organization_id", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True,
    )
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    delegation_type = Column(String(30), nullable=False, default="out_of_office")
    approval_types = Column(JSON)  # null = all types
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime)  # null for permanent
    reason = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
