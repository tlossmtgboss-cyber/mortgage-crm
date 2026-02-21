"""
Conversation Intelligence Platform Models

SQLAlchemy and Pydantic models for:
- Call recordings and transcriptions
- QA scoring with rubrics
- Real-time assist sessions
- Coaching workflows
- Compliance monitoring
- Agent metrics
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    ForeignKey, Numeric, Index, Float, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any

# Try to import Base from the project
try:
    from database import Base
except ImportError:
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()


# =============================================================================
# ENUMS
# =============================================================================

class CallType(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class CallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class RecordingStatus(str, Enum):
    RECORDED = "recorded"
    PROCESSING = "processing"
    TRANSCRIBED = "transcribed"
    ANALYZED = "analyzed"
    FAILED = "failed"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptionProvider(str, Enum):
    DEEPGRAM = "deepgram"
    ASSEMBLYAI = "assemblyai"
    WHISPER = "whisper"


class Speaker(str, Enum):
    AGENT = "agent"
    CUSTOMER = "customer"
    UNKNOWN = "unknown"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class QAGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class ScorecardStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    DISPUTED = "disputed"


class RubricCategory(str, Enum):
    GREETING = "greeting"
    DISCOVERY = "discovery"
    PRESENTATION = "presentation"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"
    COMPLIANCE = "compliance"
    SOFT_SKILLS = "soft_skills"


class SuggestionType(str, Enum):
    TIP = "tip"
    WARNING = "warning"
    SCRIPT = "script"
    OBJECTION_RESPONSE = "objection_response"
    COMPLIANCE_ALERT = "compliance_alert"


class SuggestionPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class ClipType(str, Enum):
    EXAMPLE = "example"
    IMPROVEMENT = "improvement"
    COMPLIANCE_ISSUE = "compliance_issue"
    OBJECTION_HANDLED = "objection_handled"


class AssignmentType(str, Enum):
    REVIEW_CALL = "review_call"
    WATCH_CLIP = "watch_clip"
    PRACTICE_SKILL = "practice_skill"
    COMPLETE_QUIZ = "complete_quiz"


class AssignmentStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class ViolationStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    FALSE_POSITIVE = "false_positive"
    RESOLVED = "resolved"


class MetricPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# =============================================================================
# SQLALCHEMY MODELS
# =============================================================================

class CICallRecording(Base):
    """Call recording with metadata."""
    __tablename__ = "ci_call_recordings"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Call identification
    external_call_id = Column(String(100), unique=True)
    call_type = Column(String(20), nullable=False, default='inbound')
    direction = Column(String(10), nullable=False, default='inbound')

    # Participants
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    contact_id = Column(UUID(as_uuid=True))
    loan_id = Column(UUID(as_uuid=True))
    lead_id = Column(UUID(as_uuid=True))

    # Call metadata
    phone_from = Column(String(20))
    phone_to = Column(String(20))
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)

    # Recording info
    recording_url = Column(Text)
    recording_storage_path = Column(Text)
    recording_size_bytes = Column(BigInteger)
    recording_format = Column(String(20), default='mp3')

    # Processing status
    status = Column(String(30), nullable=False, default='recorded')
    transcription_status = Column(String(20), default='pending')
    analysis_status = Column(String(20), default='pending')
    qa_status = Column(String(20), default='pending')

    # Metadata (Python attr 'meta_data' avoids conflict with SQLAlchemy's reserved .metadata)
    meta_data = Column('metadata', JSONB, default={})
    tags = Column(ARRAY(Text), default=[])

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    transcription = relationship("CICallTranscription", back_populates="recording", uselist=False)
    analysis = relationship("CICallAnalysis", back_populates="recording", uselist=False)
    scorecard = relationship("CIQAScorecard", back_populates="recording", uselist=False)
    clips = relationship("CICoachingClip", back_populates="recording")
    comments = relationship("CICoachingComment", back_populates="recording")


class CICallTranscription(Base):
    """Full transcription of a call."""
    __tablename__ = "ci_call_transcriptions"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id', ondelete='CASCADE'), nullable=False)

    # Provider info
    provider = Column(String(30), nullable=False, default='deepgram')
    provider_job_id = Column(String(100))
    model_version = Column(String(50))

    # Transcription content
    full_text = Column(Text)
    confidence_score = Column(Numeric(5, 4))

    # Metadata
    language = Column(String(10), default='en')
    word_count = Column(Integer)
    duration_seconds = Column(Numeric(10, 2))

    # Processing info
    processing_time_ms = Column(Integer)
    cost_cents = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    recording = relationship("CICallRecording", back_populates="transcription")
    segments = relationship("CITranscriptionSegment", back_populates="transcription", order_by="CITranscriptionSegment.segment_index")


class CITranscriptionSegment(Base):
    """Individual speaker segments within a transcription."""
    __tablename__ = "ci_transcription_segments"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcription_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_transcriptions.id', ondelete='CASCADE'), nullable=False)

    # Segment info
    segment_index = Column(Integer, nullable=False)
    speaker = Column(String(20), nullable=False)
    speaker_label = Column(String(50))

    # Timing
    start_time_ms = Column(Integer, nullable=False)
    end_time_ms = Column(Integer, nullable=False)

    # Content
    text = Column(Text, nullable=False)
    confidence = Column(Numeric(5, 4))

    # Word-level timing
    words = Column(JSONB)

    # Detected info
    sentiment = Column(String(20))
    intent = Column(String(50))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    transcription = relationship("CICallTranscription", back_populates="segments")


class CICallAnalysis(Base):
    """AI-generated analysis of a call."""
    __tablename__ = "ci_call_analyses"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id', ondelete='CASCADE'), nullable=False)

    # Analysis provider
    analysis_model = Column(String(50), default='claude-3-sonnet')
    analysis_version = Column(String(20), default='1.0')

    # Summary
    summary = Column(Text)
    summary_bullets = Column(JSONB)

    # Call outcome
    call_disposition = Column(String(50))
    call_purpose = Column(String(50))
    call_outcome = Column(String(50))

    # Extracted information
    topics_discussed = Column(JSONB)
    action_items = Column(JSONB)
    follow_ups_needed = Column(JSONB)

    # Customer insights
    customer_sentiment = Column(String(20))
    customer_intent = Column(String(50))
    objections_raised = Column(JSONB)
    questions_asked = Column(JSONB)

    # Agent performance insights
    agent_performance = Column(JSONB)
    coaching_opportunities = Column(JSONB)

    # Compliance
    compliance_flags = Column(JSONB)
    required_disclosures_given = Column(JSONB)

    # Mortgage-specific
    loan_details_discussed = Column(JSONB)
    property_details = Column(JSONB)
    borrower_info_collected = Column(JSONB)

    # Processing metadata
    processing_time_ms = Column(Integer)
    tokens_used = Column(Integer)
    cost_cents = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    recording = relationship("CICallRecording", back_populates="analysis")


class CIQARubric(Base):
    """QA scoring rubric definition."""
    __tablename__ = "ci_qa_rubrics"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identification
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)

    # Scoring
    max_points = Column(Integer, nullable=False, default=10)
    weight = Column(Numeric(5, 2), nullable=False, default=1.0)

    # Criteria
    criteria = Column(JSONB, nullable=False)
    scoring_guide = Column(Text)

    # Auto-scoring
    auto_score_enabled = Column(Boolean, default=False)
    auto_score_keywords = Column(JSONB)
    auto_score_rules = Column(JSONB)

    # Applicability
    call_types = Column(ARRAY(Text), default=['inbound', 'outbound'])
    required = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CIQAScorecard(Base):
    """QA scorecard for a call."""
    __tablename__ = "ci_qa_scorecards"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id', ondelete='CASCADE'), nullable=False)

    # Scoring metadata
    scored_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    scoring_method = Column(String(20), nullable=False, default='auto')

    # Overall scores
    total_score = Column(Numeric(6, 2))
    max_possible_score = Column(Numeric(6, 2))
    percentage_score = Column(Numeric(5, 2))
    grade = Column(String(2))

    # Category scores
    category_scores = Column(JSONB)

    # Flags
    critical_failures = Column(JSONB)
    improvement_areas = Column(JSONB)
    strengths = Column(JSONB)

    # Review status
    status = Column(String(20), default='pending')
    reviewed_at = Column(DateTime(timezone=True))
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    # Agent acknowledgment
    agent_acknowledged = Column(Boolean, default=False)
    agent_acknowledged_at = Column(DateTime(timezone=True))
    agent_comments = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    recording = relationship("CICallRecording", back_populates="scorecard")
    items = relationship("CIQAScorecardItem", back_populates="scorecard")


class CIQAScorecardItem(Base):
    """Individual rubric score within a scorecard."""
    __tablename__ = "ci_qa_scorecard_items"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scorecard_id = Column(UUID(as_uuid=True), ForeignKey('ci_qa_scorecards.id', ondelete='CASCADE'), nullable=False)
    rubric_id = Column(UUID(as_uuid=True), ForeignKey('ci_qa_rubrics.id'), nullable=False)

    # Score
    score = Column(Numeric(5, 2))
    max_score = Column(Numeric(5, 2))
    percentage = Column(Numeric(5, 2))

    # Evidence
    evidence_text = Column(Text)
    evidence_timestamps = Column(JSONB)

    # Scoring details
    auto_score = Column(Numeric(5, 2))
    manual_score = Column(Numeric(5, 2))
    final_score = Column(Numeric(5, 2))

    # Feedback
    evaluator_notes = Column(Text)
    improvement_suggestions = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    scorecard = relationship("CIQAScorecard", back_populates="items")


class CIRealtimeSession(Base):
    """Real-time assist session during a live call."""
    __tablename__ = "ci_realtime_sessions"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id'))

    # Session info
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    call_id = Column(String(100))

    # Status
    status = Column(String(20), nullable=False, default='active')
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))

    # WebSocket
    connection_id = Column(String(100))

    # Metadata
    meta_data = Column('metadata', JSONB, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    suggestions = relationship("CIRealtimeSuggestion", back_populates="session")


class CIRealtimeSuggestion(Base):
    """Real-time coaching suggestion during a live call."""
    __tablename__ = "ci_realtime_suggestions"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('ci_realtime_sessions.id', ondelete='CASCADE'), nullable=False)

    # Suggestion info
    suggestion_type = Column(String(30), nullable=False)
    priority = Column(String(10), default='normal')

    # Content
    title = Column(String(200))
    content = Column(Text, nullable=False)

    # Context
    triggered_by = Column(Text)
    trigger_timestamp_ms = Column(Integer)

    # Agent interaction
    was_displayed = Column(Boolean, default=False)
    displayed_at = Column(DateTime(timezone=True))
    was_dismissed = Column(Boolean, default=False)
    was_helpful = Column(Boolean)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("CIRealtimeSession", back_populates="suggestions")


class CICoachingClip(Base):
    """Coaching clip from a call recording."""
    __tablename__ = "ci_coaching_clips"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id', ondelete='CASCADE'), nullable=False)

    # Clip info
    title = Column(String(200), nullable=False)
    description = Column(Text)

    # Timing
    start_time_ms = Column(Integer, nullable=False)
    end_time_ms = Column(Integer, nullable=False)

    # Content
    transcript_excerpt = Column(Text)

    # Classification
    clip_type = Column(String(30), nullable=False)
    skill_tags = Column(ARRAY(Text), default=[])
    rubric_id = Column(UUID(as_uuid=True), ForeignKey('ci_qa_rubrics.id'))

    # Usage
    is_public = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)

    # Creator
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    recording = relationship("CICallRecording", back_populates="clips")
    comments = relationship("CICoachingComment", back_populates="clip")


class CICoachingAssignment(Base):
    """Coaching assignment for an agent."""
    __tablename__ = "ci_coaching_assignments"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Assignment target
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Content
    title = Column(String(200), nullable=False)
    description = Column(Text)
    assignment_type = Column(String(30), nullable=False)

    # Related items
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id'))
    clip_id = Column(UUID(as_uuid=True), ForeignKey('ci_coaching_clips.id'))
    rubric_id = Column(UUID(as_uuid=True), ForeignKey('ci_qa_rubrics.id'))

    # Due date
    due_date = Column(DateTime(timezone=True))

    # Status
    status = Column(String(20), default='pending')

    # Completion
    completed_at = Column(DateTime(timezone=True))
    agent_notes = Column(Text)

    # Manager review
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    reviewed_at = Column(DateTime(timezone=True))
    review_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CICoachingComment(Base):
    """Comment on a recording, clip, or scorecard."""
    __tablename__ = "ci_coaching_comments"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Comment target (one of these)
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id', ondelete='CASCADE'))
    clip_id = Column(UUID(as_uuid=True), ForeignKey('ci_coaching_clips.id', ondelete='CASCADE'))
    scorecard_id = Column(UUID(as_uuid=True), ForeignKey('ci_qa_scorecards.id', ondelete='CASCADE'))

    # Comment info
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    content = Column(Text, nullable=False)

    # Timestamp reference
    timestamp_ms = Column(Integer)

    # Threading
    parent_comment_id = Column(UUID(as_uuid=True), ForeignKey('ci_coaching_comments.id'))

    # Visibility
    is_private = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    recording = relationship("CICallRecording", back_populates="comments")
    clip = relationship("CICoachingClip", back_populates="comments")


class CIComplianceRule(Base):
    """Compliance rule definition."""
    __tablename__ = "ci_compliance_rules"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identification
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)

    # Rule definition
    rule_type = Column(String(30), nullable=False)
    rule_config = Column(JSONB, nullable=False)

    # Severity
    severity = Column(String(20), default='medium')
    is_auto_fail = Column(Boolean, default=False)

    # Applicability
    states = Column(ARRAY(Text))
    loan_types = Column(ARRAY(Text))
    call_types = Column(ARRAY(Text), default=['inbound', 'outbound'])

    # Status
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CIComplianceViolation(Base):
    """Detected compliance violation."""
    __tablename__ = "ci_compliance_violations"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recording_id = Column(UUID(as_uuid=True), ForeignKey('ci_call_recordings.id', ondelete='CASCADE'), nullable=False)
    rule_id = Column(UUID(as_uuid=True), ForeignKey('ci_compliance_rules.id'), nullable=False)

    # Violation details
    violation_type = Column(String(50), nullable=False)
    description = Column(Text)
    evidence_text = Column(Text)
    timestamp_ms = Column(Integer)

    # Severity
    severity = Column(String(20), nullable=False)

    # Resolution
    status = Column(String(20), default='open')
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    reviewed_at = Column(DateTime(timezone=True))
    resolution_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CIAgentMetrics(Base):
    """Aggregated agent metrics."""
    __tablename__ = "ci_agent_metrics"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Time period
    period_type = Column(String(10), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Call volume
    total_calls = Column(Integer, default=0)
    inbound_calls = Column(Integer, default=0)
    outbound_calls = Column(Integer, default=0)

    # Duration
    total_talk_time_seconds = Column(Integer, default=0)
    avg_call_duration_seconds = Column(Integer, default=0)

    # QA scores
    calls_scored = Column(Integer, default=0)
    avg_qa_score = Column(Numeric(5, 2))
    calls_grade_a = Column(Integer, default=0)
    calls_grade_b = Column(Integer, default=0)
    calls_grade_c = Column(Integer, default=0)
    calls_grade_d = Column(Integer, default=0)
    calls_grade_f = Column(Integer, default=0)

    # Outcomes
    successful_calls = Column(Integer, default=0)
    callbacks_scheduled = Column(Integer, default=0)
    escalations = Column(Integer, default=0)

    # Compliance
    compliance_violations = Column(Integer, default=0)

    # Coaching
    coaching_assignments_completed = Column(Integer, default=0)
    coaching_assignments_pending = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

# --- Request/Response Schemas ---

class CallRecordingCreate(BaseModel):
    """Schema for creating a call recording."""
    external_call_id: Optional[str] = None
    call_type: CallType = CallType.INBOUND
    direction: CallDirection = CallDirection.INBOUND
    agent_user_id: Optional[str] = None
    contact_id: Optional[str] = None
    loan_id: Optional[str] = None
    lead_id: Optional[str] = None
    phone_from: Optional[str] = None
    phone_to: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    recording_url: Optional[str] = None
    recording_storage_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class CallRecordingResponse(BaseModel):
    """Schema for call recording response."""
    id: str
    external_call_id: Optional[str]
    call_type: str
    direction: str
    agent_user_id: Optional[str]
    contact_id: Optional[str]
    loan_id: Optional[str]
    phone_from: Optional[str]
    phone_to: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    recording_url: Optional[str]
    status: str
    transcription_status: str
    analysis_status: str
    qa_status: str
    tags: Optional[List[str]]
    created_at: datetime

    class Config:
        from_attributes = True


class TranscriptionSegmentResponse(BaseModel):
    """Schema for transcription segment response."""
    id: str
    segment_index: int
    speaker: str
    start_time_ms: int
    end_time_ms: int
    text: str
    confidence: Optional[float]
    sentiment: Optional[str]

    class Config:
        from_attributes = True


class TranscriptionResponse(BaseModel):
    """Schema for transcription response."""
    id: str
    recording_id: str
    provider: str
    full_text: Optional[str]
    confidence_score: Optional[float]
    language: str
    word_count: Optional[int]
    segments: Optional[List[TranscriptionSegmentResponse]] = []
    created_at: datetime

    class Config:
        from_attributes = True


class CallAnalysisResponse(BaseModel):
    """Schema for call analysis response."""
    id: str
    recording_id: str
    summary: Optional[str]
    summary_bullets: Optional[List[str]]
    call_disposition: Optional[str]
    call_purpose: Optional[str]
    call_outcome: Optional[str]
    customer_sentiment: Optional[str]
    customer_intent: Optional[str]
    objections_raised: Optional[List[Dict[str, Any]]]
    action_items: Optional[List[Dict[str, Any]]]
    compliance_flags: Optional[List[Dict[str, Any]]]
    coaching_opportunities: Optional[List[Dict[str, Any]]]
    created_at: datetime

    class Config:
        from_attributes = True


class QARubricResponse(BaseModel):
    """Schema for QA rubric response."""
    id: str
    name: str
    description: Optional[str]
    category: str
    max_points: int
    weight: float
    criteria: Dict[str, Any]
    auto_score_enabled: bool
    required: bool
    is_active: bool

    class Config:
        from_attributes = True


class QAScorecardItemResponse(BaseModel):
    """Schema for QA scorecard item response."""
    id: str
    rubric_id: str
    score: Optional[float]
    max_score: Optional[float]
    percentage: Optional[float]
    evidence_text: Optional[str]
    evaluator_notes: Optional[str]
    improvement_suggestions: Optional[str]

    class Config:
        from_attributes = True


class QAScorecardResponse(BaseModel):
    """Schema for QA scorecard response."""
    id: str
    recording_id: str
    scored_by: Optional[str]
    scoring_method: str
    total_score: Optional[float]
    max_possible_score: Optional[float]
    percentage_score: Optional[float]
    grade: Optional[str]
    category_scores: Optional[Dict[str, Any]]
    critical_failures: Optional[List[Dict[str, Any]]]
    improvement_areas: Optional[List[str]]
    strengths: Optional[List[str]]
    status: str
    agent_acknowledged: bool
    items: Optional[List[QAScorecardItemResponse]] = []
    created_at: datetime

    class Config:
        from_attributes = True


class CoachingClipCreate(BaseModel):
    """Schema for creating a coaching clip."""
    recording_id: str
    title: str
    description: Optional[str] = None
    start_time_ms: int
    end_time_ms: int
    clip_type: ClipType
    skill_tags: Optional[List[str]] = None
    rubric_id: Optional[str] = None
    is_public: bool = False


class CoachingClipResponse(BaseModel):
    """Schema for coaching clip response."""
    id: str
    recording_id: str
    title: str
    description: Optional[str]
    start_time_ms: int
    end_time_ms: int
    transcript_excerpt: Optional[str]
    clip_type: str
    skill_tags: Optional[List[str]]
    is_public: bool
    view_count: int
    created_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CoachingAssignmentCreate(BaseModel):
    """Schema for creating a coaching assignment."""
    agent_user_id: str
    title: str
    description: Optional[str] = None
    assignment_type: AssignmentType
    recording_id: Optional[str] = None
    clip_id: Optional[str] = None
    rubric_id: Optional[str] = None
    due_date: Optional[datetime] = None


class CoachingAssignmentResponse(BaseModel):
    """Schema for coaching assignment response."""
    id: str
    agent_user_id: str
    assigned_by: str
    title: str
    description: Optional[str]
    assignment_type: str
    recording_id: Optional[str]
    clip_id: Optional[str]
    due_date: Optional[datetime]
    status: str
    completed_at: Optional[datetime]
    agent_notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AgentMetricsResponse(BaseModel):
    """Schema for agent metrics response."""
    agent_user_id: str
    period_type: str
    period_start: date
    period_end: date
    total_calls: int
    total_talk_time_seconds: int
    avg_call_duration_seconds: int
    calls_scored: int
    avg_qa_score: Optional[float]
    calls_grade_a: int
    calls_grade_b: int
    calls_grade_c: int
    calls_grade_d: int
    calls_grade_f: int
    compliance_violations: int
    coaching_assignments_completed: int
    coaching_assignments_pending: int

    class Config:
        from_attributes = True


class RealtimeSuggestionResponse(BaseModel):
    """Schema for real-time suggestion response."""
    id: str
    session_id: str
    suggestion_type: str
    priority: str
    title: Optional[str]
    content: str
    triggered_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ComplianceViolationResponse(BaseModel):
    """Schema for compliance violation response."""
    id: str
    recording_id: str
    rule_id: str
    violation_type: str
    description: Optional[str]
    evidence_text: Optional[str]
    timestamp_ms: Optional[int]
    severity: str
    status: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Dashboard/Summary Schemas ---

class CallSummary(BaseModel):
    """Summary of a call with key metrics."""
    id: str
    external_call_id: Optional[str]
    agent_name: Optional[str]
    call_type: str
    direction: str
    started_at: datetime
    duration_seconds: Optional[int]
    status: str
    summary: Optional[str]
    call_disposition: Optional[str]
    customer_sentiment: Optional[str]
    qa_score: Optional[float]
    qa_grade: Optional[str]


class AgentPerformanceSummary(BaseModel):
    """Summary of agent performance."""
    agent_id: str
    agent_name: str
    period: str
    total_calls: int
    avg_call_duration: int
    avg_qa_score: Optional[float]
    grade_distribution: Dict[str, int]
    compliance_issues: int
    coaching_completion_rate: float


class TeamDashboardData(BaseModel):
    """Data for the team manager dashboard."""
    total_calls_today: int
    total_talk_time_today: int
    avg_qa_score_today: Optional[float]
    active_agents: int
    calls_needing_review: int
    compliance_alerts: int
    agent_rankings: List[AgentPerformanceSummary]
    recent_calls: List[CallSummary]
