"""
AI Models

AI-related models for tracking AI actions, learning, and autonomy.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.ai import AIAction, AIDelegatedTask, AIFeedbackLog

    # Query AI actions
    actions = db.query(AIAction).filter(AIAction.status == "pending").all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index, Numeric
)
from sqlalchemy.orm import relationship

# Import Base from the db module
from db import Base


# ============================================================================
# AI DELEGATION & APPROVAL
# ============================================================================

class AIDelegatedTask(Base):
    """Tracks delegated tasks from AI for user approval"""
    __tablename__ = "ai_delegated_tasks"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email_intent = Column(String, nullable=False)  # "Clear to Close", "Rate Lock", etc.
    action_type = Column(String, nullable=False)  # "status_update", "field_update", etc.
    action_value = Column(String)  # "Clear to Close", "rate_lock_data", etc.
    action_title = Column(String)  # Human-readable action title
    action_description = Column(Text)  # Description of what AI will do
    approval_count = Column(Integer, default=1)  # Number of times user approved this
    last_approved_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)  # Can be revoked by setting to False


class AIFeedbackLog(Base):
    """Tracks user feedback on AI responses for continuous improvement"""
    __tablename__ = "ai_feedback_logs"
    __table_args__ = (
        Index('ix_ai_feedback_user_id', 'user_id'),
        Index('ix_ai_feedback_created_at', 'created_at'),
        Index('ix_ai_feedback_status', 'status'),
        Index('ix_ai_feedback_category', 'category'),
        Index('ix_ai_feedback_organization_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # The original question/prompt from the user
    user_question = Column(Text, nullable=False)

    # The AI's response that was unsatisfactory
    ai_response = Column(Text, nullable=False)

    # User's feedback on why it was wrong
    feedback_type = Column(String, nullable=False)  # 'wrong_answer', 'incomplete', 'outdated', 'irrelevant', 'other'
    user_feedback = Column(Text)  # Optional detailed feedback from user

    # Category for organizing feedback
    category = Column(String)  # 'sla', 'pipeline', 'tasks', 'loans', 'leads', 'general', etc.

    # Status for tracking resolution
    status = Column(String, default='pending')  # 'pending', 'reviewed', 'fixed', 'dismissed'

    # Resolution notes from admin
    resolution_notes = Column(Text)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    resolved_at = Column(DateTime)

    # Metadata
    session_id = Column(String)  # Link to chat session
    tools_used = Column(JSON)  # Which AI tools were invoked
    request_id = Column(String)  # For debugging

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    resolver = relationship("User", foreign_keys=[resolved_by])


class AIAction(Base):
    """Stores AI-suggested actions for user approval"""
    __tablename__ = "ai_actions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    email_id = Column(Integer, ForeignKey("emails.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"))  # Associated approval task

    # Action Details
    action_type = Column(String, index=True)  # "create_lead", "update_field", "change_stage", "create_response"
    entity_type = Column(String)  # "lead", "loan", "client"
    entity_id = Column(Integer)  # ID of the entity to update
    field_name = Column(String)  # Which field to update
    old_value = Column(String)  # Current value (if update)
    new_value = Column(String)  # Suggested value
    suggested_changes = Column(JSON)  # Full change details
    reasoning = Column(Text)  # AI's explanation
    confidence = Column(Float)  # 0-100 confidence score

    # Approval Status
    status = Column(String, default="pending")  # pending, approved, rejected, auto_approved
    approved_by_user = Column(Boolean)
    auto_applied = Column(Boolean, default=False)
    applied_at = Column(DateTime)
    rejected_reason = Column(Text)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    reviewed_at = Column(DateTime)


class AILearningMetric(Base):
    """Tracks AI learning and auto-approval thresholds"""
    __tablename__ = "ai_learning_metrics"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    action_type = Column(String, index=True)  # "create_lead", "update_field", etc.
    field_name = Column(String)  # Specific field if applicable

    # Metrics
    total_suggestions = Column(Integer, default=0)
    approved_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    auto_approved_count = Column(Integer, default=0)
    accuracy_rate = Column(Float, default=0.0)  # approved / total

    # Thresholds
    confidence_threshold = Column(Float, default=0.95)  # Min confidence for auto-approve
    auto_approve_enabled = Column(Boolean, default=False)
    min_suggestions_before_auto = Column(Integer, default=10)  # Need 10 approvals first

    # Timestamps
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# AI KNOWLEDGE BASE
# ============================================================================

class AIKnowledgeBase(Base):
    """AI Knowledge Base - Documents and content for AI to learn from"""
    __tablename__ = "ai_knowledge_base"
    __table_args__ = (
        Index('ix_ai_knowledge_base_category', 'category'),
        Index('ix_ai_knowledge_base_is_active', 'is_active'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False)  # loan_products, compliance, underwriting, sales_scripts, company_policies, workflows, other
    content = Column(Text, nullable=False)  # The actual knowledge content
    summary = Column(Text)  # AI-generated summary for quick reference
    source_type = Column(String, default="manual")  # manual, document_upload, email, url
    source_url = Column(String)  # Original URL if from web
    source_filename = Column(String)  # Original filename if uploaded
    file_type = Column(String)  # pdf, docx, txt, etc.
    tags = Column(JSON)  # List of tags for categorization
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=5)  # 1-10, higher = more important to reference
    last_reviewed = Column(DateTime)  # When content was last verified
    created_by = Column(Integer, ForeignKey("users.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    creator = relationship("User", backref="knowledge_entries")


# ============================================================================
# AI AUDIT & LOGGING
# ============================================================================

class AIAuditLog(Base):
    """Comprehensive audit trail for all AI actions"""
    __tablename__ = "ai_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    agent_name = Column(String, nullable=False, index=True)
    action_type = Column(String, nullable=False, index=True)  # email_sent, task_created, lead_updated, etc.
    action_category = Column(String)  # communication, data_update, analysis, automation
    autonomy_level = Column(String)  # autonomous, assisted, manual
    target_type = Column(String)  # lead, loan, borrower, task
    target_id = Column(Integer)
    input_data = Column(JSON)  # What triggered the action
    output_data = Column(JSON)  # Result of the action
    status = Column(String, default="completed")  # completed, failed, pending, rolled_back
    error_message = Column(Text)
    compliance_checked = Column(Boolean, default=False)
    compliance_passed = Column(Boolean)
    compliance_notes = Column(Text)
    execution_time_ms = Column(Integer)
    model_used = Column(String)  # gpt-4o, whisper-1, etc.
    tokens_used = Column(Integer)
    cost_estimate = Column(Numeric(18, 2))
    session_id = Column(String, index=True)  # Group related actions
    parent_action_id = Column(Integer, ForeignKey("ai_audit_logs.id"))  # For action chains
    is_reversible = Column(Boolean, default=False)
    reversed_at = Column(DateTime)
    reversed_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


# ============================================================================
# AI COLLEAGUE / MISSION CONTROL
# ============================================================================

class AIColleagueAction(Base):
    """Tracks every AI Colleague action for Mission Control dashboard"""
    __tablename__ = "ai_colleague_actions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    action_id = Column(String(100), unique=True, nullable=False, index=True)
    agent_name = Column(String(100), nullable=False, index=True)
    action_type = Column(String(100), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    user_id = Column(Integer, ForeignKey("users.id"))

    # Context
    context = Column(JSON)
    trigger_type = Column(String(50))
    trigger_data = Column(JSON)

    # Decision Making
    confidence_score = Column(Float)
    reasoning = Column(Text)
    alternatives_considered = Column(JSON)

    # Autonomy
    autonomy_level = Column(String(50))
    required_approval = Column(Boolean, default=False)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)

    # Execution
    status = Column(String(50), default='pending', index=True)
    executed_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Results
    outcome = Column(String(50))
    impact_score = Column(Float)
    business_metrics = Column(JSON)

    # Learning
    customer_response = Column(String(50))
    response_time_minutes = Column(Integer)
    follow_up_occurred = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    action_metadata = Column(JSON)


class AIColleagueLearningMetric(Base):
    """Tracks AI learning and improvement metrics"""
    __tablename__ = "ai_colleague_learning_metrics"

    id = Column(Integer, primary_key=True, index=True)
    action_id = Column(String(100), ForeignKey("ai_colleague_actions.action_id", ondelete="CASCADE"))
    metric_type = Column(String(100), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    baseline_value = Column(Float)
    improvement_percentage = Column(Float)

    # Context
    context = Column(JSON)
    segment = Column(String(100))

    # Time
    measured_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    period_start = Column(DateTime)
    period_end = Column(DateTime)

    # Metadata
    metric_metadata = Column(JSON)


class AIPerformanceDaily(Base):
    """Daily rollup of AI performance metrics"""
    __tablename__ = "ai_performance_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    agent_name = Column(String(100), nullable=False, index=True)

    # Volume
    total_actions = Column(Integer, default=0)
    autonomous_actions = Column(Integer, default=0)
    approved_actions = Column(Integer, default=0)
    rejected_actions = Column(Integer, default=0)

    # Success
    successful_actions = Column(Integer, default=0)
    failed_actions = Column(Integer, default=0)
    success_rate = Column(Float)

    # Response
    avg_customer_response_time = Column(Float)
    positive_responses = Column(Integer, default=0)
    negative_responses = Column(Integer, default=0)
    neutral_responses = Column(Integer, default=0)

    # Impact
    avg_impact_score = Column(Float)
    total_business_value = Column(Numeric(18, 2))

    # Confidence
    avg_confidence_score = Column(Float)
    high_confidence_actions = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AIJourneyInsight(Base):
    """Cross-channel pattern insights"""
    __tablename__ = "ai_journey_insights"

    id = Column(Integer, primary_key=True, index=True)
    insight_id = Column(String(100), unique=True, nullable=False)
    insight_type = Column(String(100), nullable=False, index=True)

    # Scope
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    segment = Column(String(100))

    # Pattern
    pattern_description = Column(Text, nullable=False)
    pattern_frequency = Column(Integer)
    pattern_confidence = Column(Float)

    # Context
    related_actions = Column(JSON)
    touchpoints = Column(JSON)
    customer_signals = Column(JSON)

    # Recommendation
    recommended_action = Column(Text)
    expected_impact = Column(Float)
    priority = Column(String(50))

    # Status
    status = Column(String(50), default='active', index=True)
    actioned_at = Column(DateTime)
    outcome = Column(String(50))

    # Metadata
    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expires_at = Column(DateTime)
    insight_metadata = Column(JSON)


class AIHealthScore(Base):
    """Overall AI health calculations"""
    __tablename__ = "ai_health_score"

    id = Column(Integer, primary_key=True, index=True)
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Overall Health
    overall_score = Column(Float, nullable=False)
    health_status = Column(String(50))

    # Component Scores
    autonomy_score = Column(Float)
    accuracy_score = Column(Float)
    efficiency_score = Column(Float)
    learning_score = Column(Float)
    impact_score = Column(Float)

    # Metrics
    total_actions = Column(Integer)
    autonomous_rate = Column(Float)
    approval_rate = Column(Float)
    success_rate = Column(Float)
    avg_confidence = Column(Float)
    learning_velocity = Column(Float)

    # Trends
    score_trend = Column(String(50))
    previous_score = Column(Float)
    score_change = Column(Float)

    # Metadata
    health_metadata = Column(JSON)


class AIMetricsDaily(Base):
    """Daily AI performance metrics for Mission Control"""
    __tablename__ = "ai_metrics_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    tasks_total = Column(Integer, default=0)
    tasks_auto_completed = Column(Integer, default=0)
    tasks_escalated_to_humans = Column(Integer, default=0)
    automation_rate = Column(Float, default=0.0)  # Percentage
    escalation_rate = Column(Float, default=0.0)  # Percentage
    avg_ai_resolution_time_seconds = Column(Float, default=0.0)
    total_time_saved_seconds = Column(Float, default=0.0)
    ai_improvement_index = Column(Float, default=100.0)  # Composite score
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AIChangelogDaily(Base):
    """Daily AI improvements changelog for Mission Control"""
    __tablename__ = "ai_changelog_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    summary = Column(Text, nullable=True)
    improvements = Column(JSON, nullable=True)  # Array of improvement descriptions
    issues = Column(JSON, nullable=True)  # Array of issues identified
    ai_generated = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AITrainingEvent(Base):
    """Training events for AI model improvement"""
    __tablename__ = "ai_training_events"

    id = Column(Integer, primary_key=True, index=True)
    extracted_data_id = Column(Integer, ForeignKey("extracted_data.id"))
    field_name = Column(String)
    original_value = Column(String)
    corrected_value = Column(String)
    label = Column(String)  # 'correct', 'incorrect', 'overridden'
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Delegation & Approval
    "AIDelegatedTask",
    "AIFeedbackLog",
    "AIAction",
    "AILearningMetric",
    # Knowledge Base
    "AIKnowledgeBase",
    # Audit
    "AIAuditLog",
    # Mission Control
    "AIColleagueAction",
    "AIColleagueLearningMetric",
    "AIPerformanceDaily",
    "AIJourneyInsight",
    "AIHealthScore",
    "AIMetricsDaily",
    "AIChangelogDaily",
    "AITrainingEvent",
]
