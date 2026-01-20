"""
Call Monitoring AI System Models

SQLAlchemy and Pydantic models for:
- Call sessions with multi-party support
- AI agent runs (Scribe, Junior LO, Underwriter)
- Agent event logging
- Generated artifacts (summaries, tasks, doc requests, risk flags)
- Intake field updates for 1003 extraction
- Risk flags for underwriter insights
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    ForeignKey, Numeric, Index, Float, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from pydantic import BaseModel, Field

# Try to import Base from the project
try:
    from database import Base
except ImportError:
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()


# =============================================================================
# ENUMS
# =============================================================================

class CaptureMode(str, Enum):
    """Call capture modes."""
    MOBILE_APP = "mobile_app"
    CRM_WEB_CALL = "crm_web_call"
    AMBIENT_MIC = "ambient_mic"
    VIDEO_CALL = "video_call"


class CallSessionStatus(str, Enum):
    """Call session processing status."""
    ACTIVE = "active"
    PROCESSING = "processing"
    REVIEW_PENDING = "review_pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ParticipantRole(str, Enum):
    """Call participant roles."""
    LOAN_OFFICER = "loan_officer"
    BORROWER = "borrower"
    CO_BORROWER = "co_borrower"
    REALTOR = "realtor"
    TITLE_AGENT = "title_agent"
    INSURANCE_AGENT = "insurance_agent"
    OTHER = "other"


class AgentType(str, Enum):
    """AI agent types."""
    SCRIBE = "scribe"
    JUNIOR_LO = "junior_lo"
    UNDERWRITER = "underwriter"


class AgentRunStatus(str, Enum):
    """Agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactType(str, Enum):
    """Generated artifact types."""
    SUMMARY = "summary"
    ACTION_ITEM = "action_item"
    TASK = "task"
    DOCUMENT_REQUEST = "document_request"
    RISK_FLAG = "risk_flag"
    INTAKE_FIELD = "intake_field"
    UW_NOTE = "uw_note"
    FOLLOW_UP_DRAFT = "follow_up_draft"
    PRICING_SCENARIO = "pricing_scenario"


class ApprovalStatus(str, Enum):
    """Artifact approval status."""
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    APPROVED = "approved"
    REJECTED = "rejected"


class ExecutionStatus(str, Enum):
    """Artifact execution status."""
    PENDING = "pending"
    EXECUTED = "executed"
    SKIPPED = "skipped"
    FAILED = "failed"


class RiskCategory(str, Enum):
    """Risk flag categories."""
    CREDIT = "credit"
    INCOME = "income"
    EMPLOYMENT = "employment"
    PROPERTY = "property"
    COMPLIANCE = "compliance"
    ASSETS = "assets"
    DTI = "dti"


class RiskSeverity(str, Enum):
    """Risk flag severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntakeFieldStatus(str, Enum):
    """Intake field update status."""
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    CONFLICT = "conflict"


# =============================================================================
# SQLALCHEMY MODELS
# =============================================================================

class CallSession(Base):
    """
    Central call session tracking.
    Links capture source to processing and artifacts.
    """
    __tablename__ = "call_sessions"
    __table_args__ = (
        Index('ix_call_sessions_status', 'status'),
        Index('ix_call_sessions_loan_id', 'loan_id'),
        Index('ix_call_sessions_lead_id', 'lead_id'),
        Index('ix_call_sessions_started_at', 'started_at'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Capture source
    capture_mode = Column(String(30), nullable=False)
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id'))

    # Linked entities
    loan_id = Column(UUID(as_uuid=True), index=True)
    lead_id = Column(UUID(as_uuid=True), index=True)
    contact_id = Column(UUID(as_uuid=True))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))  # LO conducting call

    # Session status
    status = Column(String(30), nullable=False, default='active')

    # Transcript state
    transcript_state = Column(String(30), default='pending')  # pending, partial, complete
    full_transcript = Column(Text)
    transcript_word_count = Column(Integer)

    # Participants summary (for quick display)
    participants = Column(JSONB, default=[])

    # Call metadata
    metadata = Column(JSONB, default={})
    tags = Column(ARRAY(Text), default=[])

    # Confidence (for ambient mic mode)
    overall_confidence = Column(Numeric(5, 4))

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)

    # Processing timing
    processing_started_at = Column(DateTime(timezone=True))
    processing_completed_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    participant_records = relationship("CallParticipant", back_populates="session", cascade="all, delete-orphan")
    agent_runs = relationship("AgentRun", back_populates="session", cascade="all, delete-orphan")
    events = relationship("AgentEvent", back_populates="session", cascade="all, delete-orphan")
    artifacts = relationship("CallArtifact", back_populates="session", cascade="all, delete-orphan")


class CallParticipant(Base):
    """
    Multi-party call participant tracking.
    Supports diarization and speaker identification.
    """
    __tablename__ = "call_participants"
    __table_args__ = (
        Index('ix_call_participants_session', 'session_id'),
        Index('ix_call_participants_role', 'role'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('call_sessions.id', ondelete='CASCADE'), nullable=False)

    # Participant identification
    role = Column(String(30), nullable=False)  # loan_officer, borrower, co_borrower, realtor, etc.
    name = Column(String(200))
    phone = Column(String(20))
    email = Column(String(255))

    # Speaker diarization
    speaker_label = Column(String(50))  # From transcription (Speaker_1, Speaker_2, etc.)

    # Link to existing entities
    contact_id = Column(UUID(as_uuid=True))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    # Participation timing
    joined_at = Column(DateTime(timezone=True))
    left_at = Column(DateTime(timezone=True))

    # Talk metrics
    talk_time_seconds = Column(Integer)
    word_count = Column(Integer)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("CallSession", back_populates="participant_records")


class AgentRun(Base):
    """
    Track each AI agent execution.
    Records inputs, outputs, and processing metrics.
    """
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index('ix_agent_runs_session', 'session_id'),
        Index('ix_agent_runs_type', 'agent_type'),
        Index('ix_agent_runs_status', 'status'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('call_sessions.id', ondelete='CASCADE'), nullable=False)

    # Agent identification
    agent_type = Column(String(30), nullable=False)  # scribe, junior_lo, underwriter

    # Execution status
    status = Column(String(30), nullable=False, default='pending')

    # Input context provided to agent
    input_context = Column(JSONB, default={})

    # Generated artifacts summary
    artifacts = Column(JSONB, default=[])

    # Raw LLM output (for debugging/audit)
    raw_output = Column(Text)

    # Processing metrics
    model_used = Column(String(100))
    tokens_used = Column(Integer)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    processing_time_ms = Column(Integer)
    cost_cents = Column(Integer)

    # Error tracking
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    session = relationship("CallSession", back_populates="agent_runs")
    events = relationship("AgentEvent", back_populates="run")
    generated_artifacts = relationship("CallArtifact", back_populates="run")


class AgentEvent(Base):
    """
    Append-only audit log for agent processing.
    Tracks all events during call monitoring.
    """
    __tablename__ = "agent_events"
    __table_args__ = (
        Index('ix_agent_events_session', 'session_id'),
        Index('ix_agent_events_run', 'run_id'),
        Index('ix_agent_events_type', 'event_type'),
        Index('ix_agent_events_time', 'event_time'),
        {'extend_existing': True}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey('call_sessions.id', ondelete='CASCADE'), nullable=False)
    run_id = Column(UUID(as_uuid=True), ForeignKey('agent_runs.id', ondelete='SET NULL'))

    # Event identification
    event_type = Column(String(50), nullable=False)  # transcript_chunk, agent_started, artifact_created, etc.
    agent_type = Column(String(30))

    # Event data
    payload = Column(JSONB, default={})

    # Timing
    event_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    transcript_timestamp_ms = Column(Integer)  # Position in transcript

    # Relationships
    session = relationship("CallSession", back_populates="events")
    run = relationship("AgentRun", back_populates="events")


class CallArtifact(Base):
    """
    Generated outputs from AI agents.
    Uniform model for all artifact types with approval workflow.
    """
    __tablename__ = "call_artifacts"
    __table_args__ = (
        Index('ix_call_artifacts_session', 'session_id'),
        Index('ix_call_artifacts_type', 'artifact_type'),
        Index('ix_call_artifacts_approval', 'approval_status'),
        Index('ix_call_artifacts_linked', 'linked_entity_type', 'linked_entity_id'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('call_sessions.id', ondelete='CASCADE'), nullable=False)
    run_id = Column(UUID(as_uuid=True), ForeignKey('agent_runs.id', ondelete='SET NULL'))

    # Artifact type
    artifact_type = Column(String(50), nullable=False)  # summary, action_item, task, document_request, etc.

    # Content
    title = Column(String(500))
    content = Column(Text)  # Human-readable content
    structured_data = Column(JSONB, default={})  # Machine-readable data

    # Approval workflow
    approval_status = Column(String(30), default='pending')  # pending, auto_approved, approved, rejected
    requires_approval = Column(Boolean, default=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    approved_at = Column(DateTime(timezone=True))
    rejection_reason = Column(Text)

    # Execution status (for actionable artifacts like tasks)
    execution_status = Column(String(30), default='pending')  # pending, executed, skipped, failed
    executed_at = Column(DateTime(timezone=True))
    execution_result = Column(JSONB)

    # Link to created entity (after execution)
    linked_entity_type = Column(String(50))  # task, document_request, loan_condition, etc.
    linked_entity_id = Column(UUID(as_uuid=True))

    # Confidence and evidence
    confidence = Column(Numeric(5, 4))
    source_evidence = Column(Text)  # Transcript excerpt that led to this artifact
    source_timestamp_ms = Column(Integer)  # Position in transcript

    # Metadata
    metadata = Column(JSONB, default={})
    priority = Column(String(20))  # low, medium, high, critical

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    session = relationship("CallSession", back_populates="artifacts")
    run = relationship("AgentRun", back_populates="generated_artifacts")


class IntakeFieldUpdate(Base):
    """
    1003/URLA field extraction from calls.
    Tracks proposed updates to loan/lead data.
    """
    __tablename__ = "intake_field_updates"
    __table_args__ = (
        Index('ix_intake_field_session', 'session_id'),
        Index('ix_intake_field_entity', 'entity_type', 'entity_id'),
        Index('ix_intake_field_status', 'status'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('call_sessions.id', ondelete='CASCADE'), nullable=False)
    artifact_id = Column(UUID(as_uuid=True), ForeignKey('call_artifacts.id', ondelete='SET NULL'))

    # Target entity
    entity_type = Column(String(50), nullable=False)  # loan, lead, borrower
    entity_id = Column(UUID(as_uuid=True), nullable=False)

    # Field identification
    field_name = Column(String(200), nullable=False)  # Display name
    field_path = Column(String(500))  # JSON path or column name

    # Values
    current_value = Column(JSONB)  # Current value in system
    proposed_value = Column(JSONB)  # Value extracted from call

    # Confidence
    confidence = Column(Numeric(5, 4))
    evidence_text = Column(Text)  # Transcript excerpt

    # Conflict handling
    has_conflict = Column(Boolean, default=False)
    conflict_resolution = Column(String(50))  # use_current, use_proposed, manual

    # Status
    status = Column(String(30), default='pending')  # pending, applied, rejected
    applied_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    applied_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RiskFlag(Base):
    """
    Underwriter risk identification from calls.
    Tracks potential issues and suggested conditions.
    """
    __tablename__ = "risk_flags"
    __table_args__ = (
        Index('ix_risk_flags_session', 'session_id'),
        Index('ix_risk_flags_category', 'risk_category'),
        Index('ix_risk_flags_severity', 'severity'),
        Index('ix_risk_flags_loan', 'loan_id'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('call_sessions.id', ondelete='CASCADE'), nullable=False)
    artifact_id = Column(UUID(as_uuid=True), ForeignKey('call_artifacts.id', ondelete='SET NULL'))

    # Risk classification
    risk_category = Column(String(50), nullable=False)  # credit, income, employment, property, compliance
    severity = Column(String(20), nullable=False)  # low, medium, high, critical

    # Content
    title = Column(String(500), nullable=False)
    description = Column(Text)
    evidence = Column(Text)  # Transcript excerpt
    recommended_action = Column(Text)

    # Condition suggestion
    condition_type = Column(String(50))  # prior_to_docs, prior_to_funding, informational

    # Status
    status = Column(String(30), default='open')  # open, acknowledged, resolved, dismissed
    resolution_notes = Column(Text)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    resolved_at = Column(DateTime(timezone=True))

    # Links
    loan_id = Column(UUID(as_uuid=True), index=True)
    condition_id = Column(UUID(as_uuid=True))  # Link to created loan_condition

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

# --- Call Session Schemas ---

class CallSessionCreate(BaseModel):
    """Schema for creating a call session."""
    capture_mode: CaptureMode
    recording_id: Optional[str] = None
    loan_id: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    user_id: Optional[str] = None
    participants: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None


class CallSessionUpdate(BaseModel):
    """Schema for updating a call session."""
    status: Optional[CallSessionStatus] = None
    ended_at: Optional[datetime] = None
    full_transcript: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class CallParticipantCreate(BaseModel):
    """Schema for adding a participant."""
    role: ParticipantRole
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    speaker_label: Optional[str] = None
    contact_id: Optional[str] = None
    user_id: Optional[str] = None


class CallParticipantResponse(BaseModel):
    """Schema for participant response."""
    id: str
    role: str
    name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    speaker_label: Optional[str]
    talk_time_seconds: Optional[int]

    class Config:
        from_attributes = True


class CallSessionResponse(BaseModel):
    """Schema for call session response."""
    id: str
    capture_mode: str
    recording_id: Optional[str]
    loan_id: Optional[str]
    lead_id: Optional[str]
    status: str
    transcript_state: Optional[str]
    participants: Optional[List[Dict[str, Any]]]
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Agent Run Schemas ---

class AgentRunResponse(BaseModel):
    """Schema for agent run response."""
    id: str
    session_id: str
    agent_type: str
    status: str
    artifacts: Optional[List[Dict[str, Any]]]
    tokens_used: Optional[int]
    processing_time_ms: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# --- Artifact Schemas ---

class ArtifactApproveRequest(BaseModel):
    """Schema for approving artifacts."""
    artifact_ids: List[str]
    action: str = Field(..., description="approve or reject")
    rejection_reason: Optional[str] = None


class CallArtifactResponse(BaseModel):
    """Schema for artifact response."""
    id: str
    session_id: str
    artifact_type: str
    title: Optional[str]
    content: Optional[str]
    structured_data: Optional[Dict[str, Any]]
    approval_status: str
    requires_approval: bool
    execution_status: str
    confidence: Optional[float]
    source_evidence: Optional[str]
    priority: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Review Screen Schema ---

class ReviewScreenResponse(BaseModel):
    """Schema for the review screen data."""
    session: CallSessionResponse
    participants: List[CallParticipantResponse]
    agent_runs: List[AgentRunResponse]
    artifacts: List[CallArtifactResponse]
    transcript: Optional[str]
    summary: Optional[Dict[str, Any]]
    pending_approvals: int
    auto_approved: int


# --- Intake Field Schemas ---

class IntakeFieldUpdateResponse(BaseModel):
    """Schema for intake field update response."""
    id: str
    entity_type: str
    entity_id: str
    field_name: str
    current_value: Optional[Any]
    proposed_value: Optional[Any]
    confidence: Optional[float]
    has_conflict: bool
    status: str

    class Config:
        from_attributes = True


# --- Risk Flag Schemas ---

class RiskFlagResponse(BaseModel):
    """Schema for risk flag response."""
    id: str
    session_id: str
    risk_category: str
    severity: str
    title: str
    description: Optional[str]
    evidence: Optional[str]
    recommended_action: Optional[str]
    status: str
    loan_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Dashboard/Summary Schemas ---

class CallIntelligenceSummary(BaseModel):
    """Summary for Call Intelligence tab."""
    total_calls: int
    total_duration_minutes: int
    artifacts_generated: int
    pending_approvals: int
    tasks_created: int
    documents_requested: int
    risk_flags_open: int


class CallTimelineEntry(BaseModel):
    """Entry in call timeline."""
    id: str
    started_at: datetime
    duration_seconds: Optional[int]
    capture_mode: str
    status: str
    summary_preview: Optional[str]
    participant_count: int
    artifact_count: int
