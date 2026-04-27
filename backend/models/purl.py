"""
PURL (Persistent URL) System Models

SQLAlchemy ORM models and Pydantic schemas for the PURL borrower portal system.

Tables defined:
- PURLWorkspace: Persistent household identity
- PURLContact: People associated with workspace
- PURLWorkspaceMember: Internal team access
- PURLAccessToken: Secure borrower access tokens
- PURLApplication: Pre-qual and full applications
- PURLLoan: Transaction records within workspace
- PURLDocument: File storage and tracking
- PURLPortalModule: Configurable borrower experience
- PURLMilestoneDefinition: SLA templates
- PURLLoanMilestone: Actual milestone tracking
- PURLTask: Action items
- PURLMessage: Communication
- PURLEventsOutbox: Event sourcing
- PURLAuditLog: Immutable audit trail
- PURLDocumentRequest: Document request tracking
"""

from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
import enum
import secrets
import hashlib
import re
import uuid

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Numeric, Index, CheckConstraint, UniqueConstraint, Float, Date, BigInteger
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func

from pydantic import BaseModel, Field, validator, EmailStr

from database import Base


# =============================================================================
# ENUM DEFINITIONS
# =============================================================================

class WorkspaceStatus(str, enum.Enum):
    """Workspace lifecycle status"""
    LEAD = "lead"
    APPLICATION = "application"
    ACTIVE_LOAN = "active_loan"
    CLOSING = "closing"
    POST_CLOSE = "post_close"


class ContactType(str, enum.Enum):
    """Types of contacts in a workspace"""
    BORROWER = "borrower"
    CO_BORROWER = "co_borrower"
    REALTOR = "realtor"
    PARTNER = "partner"
    OTHER = "other"


class MemberRole(str, enum.Enum):
    """Internal team member roles"""
    OWNER = "owner"
    PROCESSOR = "processor"
    CLOSER = "closer"
    VIEWER = "viewer"


class TokenScope(str, enum.Enum):
    """Access token scope levels"""
    READ = "read"
    WRITE = "write"
    FULL = "full"
    VOICE_REVIEW_SUBMIT = "voice_review_submit"


class TokenStatus(str, enum.Enum):
    """Access token status"""
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ApplicationType(str, enum.Enum):
    """Types of loan applications"""
    PRE_QUAL = "pre_qual"
    FORM_1003 = "1003"
    FULL = "full"


class ApplicationStatus(str, enum.Enum):
    """Application status"""
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"


class LoanStatus(str, enum.Enum):
    """Loan status"""
    ACTIVE = "active"
    PROCESSING = "processing"
    UNDERWRITING = "underwriting"
    CLOSING = "closing"
    CLOSED = "closed"
    DENIED = "denied"
    CANCELLED = "cancelled"
    WITHDRAWN = "withdrawn"


class LoanPurpose(str, enum.Enum):
    """Loan purpose types"""
    PURCHASE = "purchase"
    REFINANCE = "refinance"
    CASH_OUT = "cash_out"
    HELOC = "heloc"
    CONSTRUCTION = "construction"


class DocumentCategory(str, enum.Enum):
    """Document categories"""
    APPLICATION = "application"
    ASSET = "asset"
    INCOME = "income"
    IDENTITY = "identity"
    PROPERTY = "property"
    CLOSING = "closing"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    """Document status"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class PortalModule(str, enum.Enum):
    """Available portal modules"""
    APPLICATION = "application"
    DOCUMENTS = "documents"
    TIMELINE = "timeline"
    MESSAGES = "messages"
    TASKS = "tasks"
    RATE_LOCK = "rate_lock"
    CLOSING_VAULT = "closing_vault"
    RESOURCES = "resources"
    PAYMENTS = "payments"
    CHECKLIST = "checklist"


class MilestoneStage(str, enum.Enum):
    """Milestone stages"""
    LEAD = "lead"
    APPLICATION = "application"
    PROCESSING = "processing"
    UNDERWRITING = "underwriting"
    CLOSING = "closing"
    POST_CLOSE = "post_close"


class MilestoneSLAType(str, enum.Enum):
    """SLA types"""
    HARD = "hard"
    SOFT = "soft"
    ESTIMATED = "estimated"


class MilestoneStatus(str, enum.Enum):
    """Milestone status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELAYED = "delayed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TaskStatus(str, enum.Enum):
    """Task status"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskPriority(str, enum.Enum):
    """Task priority"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class MessageType(str, enum.Enum):
    """Message types"""
    TEXT = "text"
    SYSTEM = "system"
    DOCUMENT = "document"
    MILESTONE = "milestone"
    TASK = "task"


class EventStatus(str, enum.Enum):
    """Event processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class ActorType(str, enum.Enum):
    """Audit log actor types"""
    USER = "user"
    CONTACT = "contact"
    SYSTEM = "system"
    API = "api"


class DocumentRequestStatus(str, enum.Enum):
    """Document request status"""
    PENDING = "pending"
    RECEIVED = "received"
    VERIFIED = "verified"
    EXPIRED = "expired"
    WAIVED = "waived"


# =============================================================================
# SQLALCHEMY ORM MODELS
# =============================================================================

class PURLWorkspace(Base):
    """Persistent workspace for a household/client"""
    __tablename__ = "purl_workspaces"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)

    slug = Column(String(255), nullable=False, index=True)
    status = Column(String(50), default=WorkspaceStatus.LEAD.value, nullable=False)
    display_name = Column(String(500), nullable=False)
    source = Column(String(255))
    owner_user_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_workspaces_owner_user_id"))

    # Lifecycle timestamps
    lead_at = Column(DateTime(timezone=True))
    application_at = Column(DateTime(timezone=True))
    active_loan_at = Column(DateTime(timezone=True))
    closing_at = Column(DateTime(timezone=True))
    post_close_at = Column(DateTime(timezone=True))

    meta_data = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    contacts = relationship("PURLContact", back_populates="workspace", cascade="all, delete-orphan")
    members = relationship("PURLWorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    tokens = relationship("PURLAccessToken", back_populates="workspace", cascade="all, delete-orphan")
    applications = relationship("PURLApplication", back_populates="workspace", cascade="all, delete-orphan")
    loans = relationship("PURLLoan", back_populates="workspace", cascade="all, delete-orphan")
    documents = relationship("PURLDocument", back_populates="workspace", cascade="all, delete-orphan")
    modules = relationship("PURLPortalModule", back_populates="workspace", cascade="all, delete-orphan")
    tasks = relationship("PURLTask", back_populates="workspace", cascade="all, delete-orphan")
    messages = relationship("PURLMessage", back_populates="workspace", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('organization_id', 'slug', name='uq_workspace_org_slug'),
    )


class PURLContact(Base):
    """Contact associated with a workspace"""
    __tablename__ = "purl_contacts"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)

    contact_type = Column(String(50), nullable=False)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(50))

    auth_user_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_contacts_auth_user_id"))
    auth_provider = Column(String(50))

    meta_data = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="contacts")
    tokens = relationship("PURLAccessToken", back_populates="contact")


class PURLWorkspaceMember(Base):
    """Internal team member with access to workspace"""
    __tablename__ = "purl_workspace_members"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE", use_alter=True, name="fk_purl_workspace_members_user_id"), nullable=False)

    role = Column(String(50), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="members")

    __table_args__ = (
        UniqueConstraint('workspace_id', 'user_id', name='uq_member_workspace_user'),
    )


class PURLAccessToken(Base):
    """Access token for borrower portal"""
    __tablename__ = "purl_access_tokens"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)

    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    token_prefix = Column(String(50), nullable=False)

    scope = Column(String(20), nullable=False)
    status = Column(String(20), default=TokenStatus.ACTIVE.value, nullable=False)

    contact_id = Column(Integer, ForeignKey("purl_contacts.id", ondelete="SET NULL"))

    expires_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    revoked_by = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_access_tokens_revoked_by"))
    revoked_reason = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_access_tokens_created_by"))

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="tokens")
    contact = relationship("PURLContact", back_populates="tokens")


class PURLApplication(Base):
    """Loan application"""
    __tablename__ = "purl_applications"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)

    application_type = Column(String(20), nullable=False)
    status = Column(String(30), default=ApplicationStatus.IN_PROGRESS.value, nullable=False)
    version = Column(Integer, default=1, nullable=False)

    data = Column(JSONB, default={})
    derived = Column(JSONB, default={})
    validation_errors = Column(JSONB, default=[])
    completeness_pct = Column(Integer, default=0)

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    submitted_at = Column(DateTime(timezone=True))
    approved_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="applications")
    loans = relationship("PURLLoan", back_populates="application")

    __table_args__ = (
        UniqueConstraint('workspace_id', 'application_type', 'version', name='uq_app_workspace_type_version'),
    )


class PURLLoan(Base):
    """Loan record within workspace"""
    __tablename__ = "purl_loans"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)
    application_id = Column(Integer, ForeignKey("purl_applications.id"))
    main_loan_id = Column(Integer)  # Link to main loans table

    loan_number = Column(String(100))
    status = Column(String(30), default=LoanStatus.ACTIVE.value, nullable=False)

    loan_purpose = Column(String(50))
    product_type = Column(String(100))
    loan_amount = Column(Numeric(15, 2))
    interest_rate = Column(Numeric(6, 4))

    property_address = Column(JSONB)
    property_type = Column(String(50))

    target_close_date = Column(Date)
    actual_close_date = Column(Date)

    los_loan_id = Column(String(100))

    meta_data = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="loans")
    application = relationship("PURLApplication", back_populates="loans")
    documents = relationship("PURLDocument", back_populates="loan")
    milestones = relationship("PURLLoanMilestone", back_populates="loan", cascade="all, delete-orphan")
    tasks = relationship("PURLTask", back_populates="loan")


class PURLDocument(Base):
    """Document in workspace"""
    __tablename__ = "purl_documents"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)
    loan_id = Column(Integer, ForeignKey("purl_loans.id", ondelete="CASCADE"))

    doc_type = Column(String(100), nullable=False)
    doc_category = Column(String(50), nullable=False)
    status = Column(String(30), default=DocumentStatus.UPLOADED.value, nullable=False)

    file_name = Column(String(500), nullable=False)
    storage_key = Column(String(1000), nullable=False, unique=True)
    size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(255), nullable=False)
    sha256 = Column(String(64))

    uploaded_by_contact_id = Column(Integer, ForeignKey("purl_contacts.id"))
    # Use use_alter=True to defer FK constraint creation (avoids circular import with User model)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_documents_uploaded_by_user_id"))

    ocr_text = Column(Text)
    extracted_data = Column(JSONB)

    # Use use_alter=True to defer FK constraint creation (avoids circular import with User model)
    reviewed_by = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_documents_reviewed_by"))
    reviewed_at = Column(DateTime(timezone=True))
    review_notes = Column(Text)

    retention_policy = Column(String(50), default="standard", nullable=False)
    legal_hold = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True))
    delete_after = Column(DateTime(timezone=True))

    meta_data = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="documents")
    loan = relationship("PURLLoan", back_populates="documents")


class PURLPortalModule(Base):
    """Configurable portal module for workspace"""
    __tablename__ = "purl_portal_modules"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)

    module_key = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    is_visible = Column(Boolean, default=True, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)

    config_version = Column(Integer, default=1, nullable=False)
    config = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="modules")

    __table_args__ = (
        UniqueConstraint('workspace_id', 'module_key', name='uq_module_workspace_key'),
    )


class PURLMilestoneDefinition(Base):
    """Milestone definition template (org-level)"""
    __tablename__ = "purl_milestone_definitions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)

    code = Column(String(100), nullable=False)
    stage = Column(String(50), nullable=False)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)

    order_index = Column(Integer, nullable=False)
    sla_days = Column(Integer)
    sla_type = Column(String(20), nullable=False)
    grace_percent = Column(Integer, default=75, nullable=False)

    notify_on_start = Column(Boolean, default=False)
    notify_on_complete = Column(Boolean, default=True)
    notify_on_delay = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    milestones = relationship("PURLLoanMilestone", back_populates="definition")

    __table_args__ = (
        UniqueConstraint('organization_id', 'code', name='uq_milestone_def_org_code'),
    )


class PURLLoanMilestone(Base):
    """Actual milestone tracking for a loan"""
    __tablename__ = "purl_loan_milestones"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    loan_id = Column(Integer, ForeignKey("purl_loans.id", ondelete="CASCADE"), nullable=False)
    milestone_definition_id = Column(Integer, ForeignKey("purl_milestone_definitions.id"), nullable=False)

    status = Column(String(30), default=MilestoneStatus.PENDING.value, nullable=False)

    due_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    assigned_to = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_loan_milestones_assigned_to"))
    completion_notes = Column(Text)
    delay_reason = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    loan = relationship("PURLLoan", back_populates="milestones")
    definition = relationship("PURLMilestoneDefinition", back_populates="milestones")

    __table_args__ = (
        UniqueConstraint('loan_id', 'milestone_definition_id', name='uq_milestone_loan_def'),
    )


class PURLTask(Base):
    """Task/action item"""
    __tablename__ = "purl_tasks"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"))
    loan_id = Column(Integer, ForeignKey("purl_loans.id", ondelete="CASCADE"))

    title = Column(String(500), nullable=False)
    description = Column(Text)
    task_type = Column(String(50), default="general")
    status = Column(String(30), default=TaskStatus.OPEN.value, nullable=False)
    priority = Column(String(20), default=TaskPriority.MEDIUM.value, nullable=False)

    assigned_to_user_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_tasks_assigned_to_user_id"))
    assigned_to_contact_id = Column(Integer, ForeignKey("purl_contacts.id"))

    related_document_id = Column(Integer, ForeignKey("purl_documents.id"))
    related_milestone_id = Column(Integer, ForeignKey("purl_loan_milestones.id"))

    due_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    completed_by_user_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_tasks_completed_by_user_id"))
    completed_by_contact_id = Column(Integer, ForeignKey("purl_contacts.id"))

    meta_data = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="tasks")
    loan = relationship("PURLLoan", back_populates="tasks")


class PURLMessage(Base):
    """Message in workspace"""
    __tablename__ = "purl_messages"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)

    message_type = Column(String(30), default=MessageType.TEXT.value, nullable=False)
    content = Column(Text, nullable=False)

    sender_type = Column(String(20), nullable=False)
    sender_user_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_messages_sender_user_id"))
    sender_contact_id = Column(Integer, ForeignKey("purl_contacts.id"))

    related_document_id = Column(Integer, ForeignKey("purl_documents.id"))
    related_task_id = Column(Integer, ForeignKey("purl_tasks.id"))

    is_read_by_borrower = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True))

    meta_data = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    workspace = relationship("PURLWorkspace", back_populates="messages")


class PURLEventsOutbox(Base):
    """Event outbox for async processing"""
    __tablename__ = "purl_events_outbox"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)

    event_key = Column(String(100), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id"))
    loan_id = Column(Integer, ForeignKey("purl_loans.id"))

    payload = Column(JSONB, nullable=False)
    status = Column(String(30), default=EventStatus.PENDING.value, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)

    locked_at = Column(DateTime(timezone=True))
    locked_by = Column(String(255))
    processed_duration_ms = Column(Integer)
    error_message = Column(Text)

    scheduled_for = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PURLAuditLog(Base):
    """Audit log for PURL actions"""
    __tablename__ = "purl_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)

    actor_type = Column(String(20), nullable=False)
    actor_id = Column(Integer)

    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id"))
    loan_id = Column(Integer, ForeignKey("purl_loans.id"))

    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(Integer)

    changes = Column(JSONB)
    meta_data = Column(JSONB, default={})

    ip_address = Column(String(45))
    user_agent = Column(Text)
    request_id = Column(String(100))

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PURLDocumentRequest(Base):
    """Document request tracking"""
    __tablename__ = "purl_document_requests"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE", use_alter=True), nullable=False)
    workspace_id = Column(Integer, ForeignKey("purl_workspaces.id", ondelete="CASCADE"), nullable=False)
    loan_id = Column(Integer, ForeignKey("purl_loans.id", ondelete="CASCADE"))

    document_type = Column(String(100), nullable=False)
    document_category = Column(String(50), nullable=False)
    description = Column(Text)

    status = Column(String(30), default=DocumentRequestStatus.PENDING.value, nullable=False)
    is_required = Column(Boolean, default=True)

    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    requested_by = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_purl_document_requests_requested_by"))
    due_date = Column(Date)

    reminder_count = Column(Integer, default=0)
    last_reminder_at = Column(DateTime(timezone=True))

    received_document_id = Column(Integer, ForeignKey("purl_documents.id"))
    received_at = Column(DateTime(timezone=True))

    meta_data = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =============================================================================
# PYDANTIC SCHEMAS - Request/Response Models
# =============================================================================

# -------------------- WORKSPACE SCHEMAS --------------------

class WorkspaceCreate(BaseModel):
    """Request model for creating a workspace"""
    display_name: str = Field(..., min_length=1, max_length=500)
    slug: Optional[str] = Field(None, max_length=255)
    source: Optional[str] = Field(None, max_length=255)
    owner_user_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class WorkspaceUpdate(BaseModel):
    """Request model for updating a workspace"""
    display_name: Optional[str] = Field(None, max_length=500)
    status: Optional[WorkspaceStatus] = None
    owner_user_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class WorkspaceResponse(BaseModel):
    """Response model for workspace"""
    id: int
    organization_id: int
    slug: str
    status: str
    display_name: str
    source: Optional[str]
    owner_user_id: Optional[int]
    lead_at: Optional[datetime]
    application_at: Optional[datetime]
    active_loan_at: Optional[datetime]
    closing_at: Optional[datetime]
    post_close_at: Optional[datetime]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# -------------------- CONTACT SCHEMAS --------------------

class ContactCreate(BaseModel):
    """Request model for creating a contact"""
    contact_type: ContactType
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContactUpdate(BaseModel):
    """Request model for updating a contact"""
    first_name: Optional[str] = Field(None, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    metadata: Optional[Dict[str, Any]] = None


class ContactResponse(BaseModel):
    """Response model for contact"""
    id: int
    organization_id: int
    workspace_id: int
    contact_type: str
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]
    auth_user_id: Optional[int]
    auth_provider: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# -------------------- TOKEN SCHEMAS --------------------

class TokenCreate(BaseModel):
    """Request model for creating a token"""
    scope: TokenScope = TokenScope.WRITE
    contact_id: Optional[int] = None
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class TokenResponse(BaseModel):
    """Response model for token"""
    id: int
    workspace_id: int
    token_prefix: str
    scope: str
    status: str
    contact_id: Optional[int]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    token: Optional[str] = None  # Only returned on creation

    class Config:
        from_attributes = True


class TokenVerifyRequest(BaseModel):
    """Request to verify a token"""
    token: str = Field(..., min_length=1)


class TokenVerifyResponse(BaseModel):
    """Response from token verification"""
    valid: bool
    workspace_id: Optional[int] = None
    workspace_slug: Optional[str] = None
    scope: Optional[str] = None
    contact_id: Optional[int] = None


# -------------------- APPLICATION SCHEMAS --------------------

class ApplicationCreate(BaseModel):
    """Request model for creating an application"""
    application_type: ApplicationType = ApplicationType.FULL
    data: Dict[str, Any] = Field(default_factory=dict)


class ApplicationUpdate(BaseModel):
    """Request model for updating/saving application data"""
    data: Dict[str, Any]


class ApplicationSubmit(BaseModel):
    """Request to submit an application"""
    pass  # No additional data needed


class ApplicationResponse(BaseModel):
    """Response model for application"""
    id: int
    organization_id: int
    workspace_id: int
    application_type: str
    status: str
    version: int
    data: Dict[str, Any]
    derived: Dict[str, Any]
    validation_errors: List[str]
    completeness_pct: int
    started_at: datetime
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# -------------------- LOAN SCHEMAS --------------------

class PropertyAddress(BaseModel):
    """Property address model"""
    street: str
    city: str
    state: str
    zip_code: str
    county: Optional[str] = None


class LoanCreate(BaseModel):
    """Request model for creating a loan"""
    loan_purpose: Optional[LoanPurpose] = None
    product_type: Optional[str] = None
    loan_amount: Optional[float] = None
    property_address: Optional[PropertyAddress] = None
    target_close_date: Optional[date] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LoanUpdate(BaseModel):
    """Request model for updating a loan"""
    status: Optional[LoanStatus] = None
    loan_number: Optional[str] = None
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    product_type: Optional[str] = None
    target_close_date: Optional[date] = None
    actual_close_date: Optional[date] = None
    los_loan_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LoanResponse(BaseModel):
    """Response model for loan"""
    id: int
    organization_id: int
    workspace_id: int
    application_id: Optional[int]
    loan_number: Optional[str]
    status: str
    loan_purpose: Optional[str]
    product_type: Optional[str]
    loan_amount: Optional[float]
    interest_rate: Optional[float]
    property_address: Optional[Dict[str, Any]]
    property_type: Optional[str]
    target_close_date: Optional[date]
    actual_close_date: Optional[date]
    los_loan_id: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# -------------------- DOCUMENT SCHEMAS --------------------

class DocumentUploadInit(BaseModel):
    """Request to initialize document upload"""
    file_name: str = Field(..., min_length=1, max_length=500)
    file_size: int = Field(..., gt=0, le=104857600)  # Max 100MB
    mime_type: str
    doc_type: str = Field(..., min_length=1, max_length=100)
    doc_category: DocumentCategory
    loan_id: Optional[int] = None


class DocumentUploadComplete(BaseModel):
    """Request to complete document upload"""
    upload_id: str
    storage_key: str
    sha256: Optional[str] = None


class DocumentResponse(BaseModel):
    """Response model for document"""
    id: int
    organization_id: int
    workspace_id: int
    loan_id: Optional[int]
    doc_type: str
    doc_category: str
    status: str
    file_name: str
    size_bytes: int
    mime_type: str
    sha256: Optional[str]
    uploaded_by_contact_id: Optional[int]
    uploaded_by_user_id: Optional[int]
    retention_policy: str
    legal_hold: bool
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# -------------------- TASK SCHEMAS --------------------

class TaskCreate(BaseModel):
    """Request model for creating a task"""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    task_type: str = "general"
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to_user_id: Optional[int] = None
    assigned_to_contact_id: Optional[int] = None
    due_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    """Request model for updating a task"""
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    """Response model for task"""
    id: int
    organization_id: int
    workspace_id: Optional[int]
    loan_id: Optional[int]
    title: str
    description: Optional[str]
    task_type: str
    status: str
    priority: str
    assigned_to_user_id: Optional[int]
    assigned_to_contact_id: Optional[int]
    due_at: Optional[datetime]
    completed_at: Optional[datetime]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# -------------------- MILESTONE SCHEMAS --------------------

class MilestoneResponse(BaseModel):
    """Response model for milestone"""
    id: int
    code: str
    display_name: str
    stage: str
    order_index: int
    status: str
    due_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    delay_reason: Optional[str]

    class Config:
        from_attributes = True


# -------------------- TIMELINE SCHEMAS --------------------

class TimelineEvent(BaseModel):
    """Timeline event"""
    id: int
    event_type: str
    title: str
    description: Optional[str] = None
    timestamp: datetime
    actor: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    """Complete timeline response"""
    milestones: List[MilestoneResponse]
    events: List[TimelineEvent]


# -------------------- MESSAGE SCHEMAS --------------------

class MessageCreate(BaseModel):
    """Request model for creating a message"""
    content: str = Field(..., min_length=1)
    message_type: MessageType = MessageType.TEXT
    related_document_id: Optional[int] = None
    related_task_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    """Response model for message"""
    id: int
    workspace_id: int
    message_type: str
    content: str
    sender_type: str
    sender_user_id: Optional[int]
    sender_contact_id: Optional[int]
    is_read_by_borrower: bool
    read_at: Optional[datetime]
    metadata: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


# -------------------- PORTAL MODULE SCHEMAS --------------------

class PortalModuleConfig(BaseModel):
    """Portal module configuration"""
    title: Optional[str] = None
    description: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)


class PortalModuleResponse(BaseModel):
    """Response model for portal module"""
    id: int
    module_key: str
    is_enabled: bool
    is_visible: bool
    order_index: int
    config: Dict[str, Any]
    config_version: int

    class Config:
        from_attributes = True


# -------------------- COMPLETE WORKSPACE DATA --------------------

class PURLWorkspaceData(BaseModel):
    """Complete workspace data for borrower portal"""
    workspace: WorkspaceResponse
    contacts: List[ContactResponse]
    current_loan: Optional[LoanResponse]
    all_loans: List[LoanResponse]
    modules: List[PortalModuleResponse]
    pending_tasks: List[TaskResponse]
    recent_documents: List[DocumentResponse]
    unread_messages_count: int = 0


# =============================================================================
# UTILITY CLASSES
# =============================================================================

class PURLTokenGenerator:
    """Utility class for generating and verifying PURL tokens"""

    TOKEN_PREFIX = "purl_live_"
    TOKEN_LENGTH = 32  # bytes = 64 hex chars

    @classmethod
    def generate_token(cls) -> Tuple[str, str, str]:
        """
        Generate a secure token.
        Returns: (full_token, token_hash, token_prefix)
        """
        random_bytes = secrets.token_bytes(cls.TOKEN_LENGTH)
        token_hex = random_bytes.hex()
        full_token = f"{cls.TOKEN_PREFIX}{token_hex}"

        # Hash the token
        token_hash = hashlib.sha256(full_token.encode()).hexdigest()

        # First 16 chars for display (includes prefix)
        display_prefix = full_token[:16]

        return full_token, token_hash, display_prefix

    @classmethod
    def hash_token(cls, token: str) -> str:
        """Hash a token for storage/verification"""
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def is_valid_format(cls, token: str) -> bool:
        """Check if token has valid format"""
        return (
            token.startswith(cls.TOKEN_PREFIX) and
            len(token) == len(cls.TOKEN_PREFIX) + cls.TOKEN_LENGTH * 2
        )


class SlugGenerator:
    """Utility class for generating URL-safe slugs"""

    @classmethod
    def generate(cls, display_name: str, suffix_length: int = 8) -> str:
        """
        Generate URL-safe slug from display name.
        Adds random suffix for uniqueness.
        """
        # Remove special chars, convert to lowercase, replace spaces
        slug = re.sub(r'[^a-z0-9\s-]', '', display_name.lower())
        slug = re.sub(r'[\s]+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')

        # Truncate if too long
        if len(slug) > 50:
            slug = slug[:50].rstrip('-')

        # Add random suffix
        suffix = secrets.token_hex(suffix_length // 2)
        return f"{slug}-{suffix}"

    @classmethod
    def generate_from_name(cls, first_name: str, last_name: str) -> str:
        """
        Generate URL-safe slug from first and last name.
        Format: firstname.lastname (e.g., timothy.loss)
        """
        # Clean first name - remove special chars, convert to lowercase
        clean_first = re.sub(r'[^a-z0-9]', '', first_name.lower().strip())
        # Clean last name - remove special chars, convert to lowercase
        clean_last = re.sub(r'[^a-z0-9]', '', last_name.lower().strip())

        # Handle empty names
        if not clean_first and not clean_last:
            # Fall back to random slug
            return secrets.token_hex(8)
        elif not clean_first:
            return clean_last
        elif not clean_last:
            return clean_first

        return f"{clean_first}.{clean_last}"

    @classmethod
    def generate_unique_from_name(
        cls,
        first_name: str,
        last_name: str,
        existing_slugs: List[str]
    ) -> str:
        """
        Generate a unique slug from first and last name.
        If firstname.lastname exists, adds a number suffix (e.g., timothy.loss2)

        Args:
            first_name: Borrower's first name
            last_name: Borrower's last name
            existing_slugs: List of existing slugs to check against

        Returns:
            A unique slug in format firstname.lastname or firstname.lastnameN
        """
        base_slug = cls.generate_from_name(first_name, last_name)

        # If base slug doesn't exist, use it
        if base_slug not in existing_slugs:
            return base_slug

        # Find the next available number
        counter = 2
        while True:
            candidate = f"{base_slug}{counter}"
            if candidate not in existing_slugs:
                return candidate
            counter += 1
            # Safety limit to prevent infinite loop
            if counter > 1000:
                # Fall back to random suffix
                return f"{base_slug}-{secrets.token_hex(4)}"
