"""
AI Receptionist Dashboard Database Models
Tracks activity, metrics, skills, errors, and system health
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, Date, Index
from datetime import datetime, timezone
from database import Base
import uuid


class AIReceptionistActivity(Base):
    """
    Real-time activity feed - all AI receptionist actions
    Displays in chronological feed for monitoring
    """
    __tablename__ = "ai_receptionist_activity"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    # Client information
    client_id = Column(String(255), index=True)
    client_name = Column(String(255))
    client_phone = Column(String(50))
    client_email = Column(String(255))

    # Action details
    action_type = Column(String(100), nullable=False, index=True)
    # Action types: 'incoming_call', 'incoming_text', 'outbound_followup',
    # 'appointment_booked', 'faq_answered', 'lead_prescreened', 'crm_updated',
    # 'escalated', 'conversation_summary', 'ai_uncertainty', 'error'

    channel = Column(String(50))  # 'sms', 'voice', 'email'
    message_in = Column(Text)
    message_out = Column(Text)

    # AI performance
    confidence_score = Column(Float)  # 0-1 scale
    ai_version = Column(String(50))

    # Business context
    lead_stage = Column(String(100))  # 'prospect', 'application', 'processing', 'closed'
    assigned_to = Column(String(255))  # Loan Officer assigned
    outcome_status = Column(String(100))  # 'success', 'failed', 'escalated', 'pending'

    # Conversation tracking
    conversation_id = Column(String(255))
    transcript_url = Column(String(500))

    # Additional data
    extra_data = Column(JSON)  # Flexible field for extra context (renamed from 'metadata' to avoid SQLAlchemy reserved word)

    # Indices for performance
    __table_args__ = (
        Index('idx_activity_timestamp_desc', timestamp.desc()),
        Index('idx_activity_client_timestamp', client_id, timestamp.desc()),
        Index('idx_activity_type_timestamp', action_type, timestamp.desc()),
    )


class AIReceptionistMetricsDaily(Base):
    """
    Daily aggregated metrics for performance tracking
    Updated via cron job at end of each day
    """
    __tablename__ = "ai_receptionist_metrics_daily"

    date = Column(Date, primary_key=True)

    # Volume metrics
    total_conversations = Column(Integer, default=0)
    inbound_calls = Column(Integer, default=0)
    inbound_texts = Column(Integer, default=0)
    outbound_messages = Column(Integer, default=0)

    # Performance metrics
    response_time_avg_seconds = Column(Float)  # Average response time
    response_time_p95_seconds = Column(Float)  # 95th percentile

    # Business outcomes
    appointments_scheduled = Column(Integer, default=0)
    forms_completed = Column(Integer, default=0)
    loan_apps_initiated = Column(Integer, default=0)
    lead_updates = Column(Integer, default=0)
    task_updates = Column(Integer, default=0)
    documents_requested = Column(Integer, default=0)

    # AI behavior
    escalations = Column(Integer, default=0)  # Times AI escalated to human
    ai_confusion_count = Column(Integer, default=0)  # Low confidence responses
    successful_resolutions = Column(Integer, default=0)

    # Conversion metrics
    lead_qualification_rate = Column(Float)  # % of leads qualified
    appointment_show_rate = Column(Float)  # % of appointments attended
    ai_coverage_percentage = Column(Float)  # % handled without human

    # Financial metrics
    estimated_revenue_created = Column(Float)  # Applications × avg commission
    saved_labor_hours = Column(Float)  # Staff time saved
    cost_per_interaction = Column(Float)

    # Quality metrics
    avg_confidence_score = Column(Float)
    error_rate = Column(Float)  # % of interactions with errors

    # Additional data
    extra_data = Column(JSON)  # Renamed from 'metadata' to avoid SQLAlchemy reserved word


class AIReceptionistSkill(Base):
    """
    Tracks performance of specific AI skills/intents
    Used for heatmap visualization and retraining prioritization
    """
    __tablename__ = "ai_receptionist_skills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_name = Column(String(255), nullable=False, unique=True, index=True)

    # Skill categories: 'appointment_scheduling', 'lead_inquiry', 'document_request',
    # 'rate_question', 'existing_borrower', 'builder_update', 'contract_update',
    # 'underwriting_condition', 'faq_routing', 'tone_appropriateness'

    skill_category = Column(String(100))  # Group related skills
    description = Column(Text)

    # Performance metrics
    accuracy_score = Column(Float)  # Current accuracy (0-1)
    accuracy_score_7day = Column(Float)  # 7-day average
    accuracy_score_30day = Column(Float)  # 30-day average

    # Trend indicators
    trend_7day = Column(Float)  # +/- % change from previous 7 days
    trend_30day = Column(Float)  # +/- % change from previous 30 days
    trend_direction = Column(String(20))  # 'improving', 'declining', 'stable'

    # Usage statistics
    usage_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

    # Training status
    needs_retraining = Column(Boolean, default=False)
    last_trained_at = Column(DateTime(timezone=True))
    last_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Additional data
    extra_data = Column(JSON)  # Renamed from 'metadata' to avoid SQLAlchemy reserved word


class AIReceptionistError(Base):
    """
    Error tracking and self-learning log
    Captures what AI couldn't handle for continuous improvement
    """
    __tablename__ = "ai_receptionist_errors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    # Error classification
    error_type = Column(String(100), index=True)
    # Error types: 'unrecognized_request', 'missing_context', 'model_uncertainty',
    # 'out_of_scope', 'api_failure', 'integration_error', 'timeout'

    severity = Column(String(20))  # 'low', 'medium', 'high', 'critical'

    # Context
    context = Column(Text)  # Full context of what happened
    conversation_snippet = Column(Text)  # Relevant conversation excerpt
    conversation_id = Column(String(255))

    # Diagnosis
    root_cause = Column(Text)  # Auto-diagnosed root cause
    recommended_fix = Column(Text)  # System-recommended solution
    auto_fix_proposed = Column(Text)  # AI-generated fix (for approval)

    # Resolution
    needs_human_review = Column(Boolean, default=False)
    reviewed_by = Column(String(255))
    reviewed_at = Column(DateTime(timezone=True))
    resolution_status = Column(String(50), default='unresolved')
    # Status: 'unresolved', 'auto_fixed', 'manually_fixed', 'wont_fix', 'investigating'

    resolution_notes = Column(Text)

    # Learning
    trained_into_model = Column(Boolean, default=False)
    training_data_id = Column(String(255))

    # Additional data
    extra_data = Column(JSON)  # Renamed from 'metadata' to avoid SQLAlchemy reserved word

    # Indices
    __table_args__ = (
        Index('idx_error_timestamp_desc', timestamp.desc()),
        Index('idx_error_type_status', error_type, resolution_status),
        Index('idx_error_needs_review', needs_human_review),
    )


class AIReceptionistSystemHealth(Base):
    """
    Real-time system health monitoring
    Tracks status of all integrated components
    """
    __tablename__ = "ai_receptionist_system_health"

    component_name = Column(String(255), primary_key=True)
    # Components: 'sms_integration', 'voice_endpoint', 'calendly_api',
    # 'crm_pipeline', 'outlook_sync', 'teams_sync', 'zapier_triggers',
    # 'document_module', 'openai_api', 'claude_api', 'pinecone_db'

    status = Column(String(50), nullable=False, default='unknown')
    # Status: 'active', 'degraded', 'down', 'maintenance', 'unknown'

    # Performance metrics
    latency_ms = Column(Integer)  # Response time in milliseconds
    error_rate = Column(Float)  # % of failed requests
    uptime_percentage = Column(Float)  # % uptime in last 24 hours

    # Status tracking
    last_checked = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_success = Column(DateTime(timezone=True))
    last_failure = Column(DateTime(timezone=True))
    consecutive_failures = Column(Integer, default=0)

    # Alert tracking
    alert_sent = Column(Boolean, default=False)
    alert_sent_at = Column(DateTime(timezone=True))

    # Additional info
    notes = Column(Text)
    endpoint_url = Column(String(500))
    extra_data = Column(JSON)  # Renamed from 'metadata' to avoid SQLAlchemy reserved word


class AIReceptionistConversation(Base):
    """
    Full conversation transcripts for detailed review
    Links to activity feed items
    """
    __tablename__ = "ai_receptionist_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    ended_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)

    # Participant info
    client_id = Column(String(255), index=True)
    client_name = Column(String(255))
    client_phone = Column(String(50))
    client_email = Column(String(255))

    # Conversation details
    channel = Column(String(50))  # 'sms', 'voice', 'email'
    direction = Column(String(20))  # 'inbound', 'outbound'

    # Full transcript
    transcript = Column(Text)  # Complete conversation text
    transcript_json = Column(JSON)  # Structured format with timestamps

    # AI analysis
    summary = Column(Text)  # AI-generated summary
    intent_detected = Column(String(100))  # Primary intent
    sentiment = Column(String(50))  # 'positive', 'neutral', 'negative'
    key_topics = Column(JSON)  # List of topics discussed

    # Outcome
    outcome = Column(String(100))  # 'appointment_booked', 'info_provided', 'escalated', etc.
    escalated_to = Column(String(255))  # If escalated, who to
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(DateTime(timezone=True))

    # Quality metrics
    avg_confidence_score = Column(Float)
    total_turns = Column(Integer)  # Number of back-and-forth exchanges

    # Recording (for voice calls)
    recording_url = Column(String(500))

    # Additional data
    extra_data = Column(JSON)  # Renamed from 'metadata' to avoid SQLAlchemy reserved word

    # Indices
    __table_args__ = (
        Index('idx_conversation_started_desc', started_at.desc()),
        Index('idx_conversation_client', client_id, started_at.desc()),
        Index('idx_conversation_outcome', outcome),
    )


# Create all tables when this module is imported
def create_dashboard_tables():
    """
    Create all AI Receptionist Dashboard tables
    Call this from a migration endpoint
    """
    from database import engine
    Base.metadata.create_all(engine, tables=[
        AIReceptionistActivity.__table__,
        AIReceptionistMetricsDaily.__table__,
        AIReceptionistSkill.__table__,
        AIReceptionistError.__table__,
        AIReceptionistSystemHealth.__table__,
        AIReceptionistConversation.__table__,
    ])
