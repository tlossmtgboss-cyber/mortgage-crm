"""
Surveying & Feedback Models
Comprehensive client surveying platform for customer satisfaction measurement.
"""

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float,
    ForeignKey, Enum as SQLEnum, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from database import Base


# =============================================================================
# Enums
# =============================================================================

class SurveyType(str, Enum):
    """Types of surveys available."""
    CSAT = "csat"                    # Customer Satisfaction Score
    NPS = "nps"                      # Net Promoter Score
    CES = "ces"                      # Customer Effort Score
    CUSTOM = "custom"                # Custom survey
    POST_CLOSE = "post_close"        # Post-closing feedback
    MILESTONE = "milestone"          # Milestone-triggered
    SAVINGS_VALIDATION = "savings"   # Validate promised savings


class SurveyStatus(str, Enum):
    """Survey lifecycle status."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class QuestionType(str, Enum):
    """Types of survey questions."""
    NPS_SCALE = "nps_scale"          # 0-10 scale
    CSAT_SCALE = "csat_scale"        # 1-5 scale
    LIKERT = "likert"                # Strongly disagree to Strongly agree
    RATING = "rating"                # Star rating
    YES_NO = "yes_no"                # Binary
    MULTIPLE_CHOICE = "multiple_choice"
    CHECKBOX = "checkbox"            # Multiple selection
    TEXT = "text"                    # Open-ended
    TEXT_LONG = "text_long"          # Long-form response


class ResponseStatus(str, Enum):
    """Status of survey response."""
    PENDING = "pending"              # Survey sent, not started
    IN_PROGRESS = "in_progress"      # Partially completed
    COMPLETED = "completed"          # Fully completed
    EXPIRED = "expired"              # Past deadline
    BOUNCED = "bounced"              # Delivery failed


class TriggerType(str, Enum):
    """When to trigger a survey."""
    MANUAL = "manual"
    LOAN_FUNDED = "loan_funded"
    LOAN_CLOSED = "loan_closed"
    APPLICATION_SUBMITTED = "application_submitted"
    MILESTONE_REACHED = "milestone_reached"
    DAYS_AFTER_CLOSE = "days_after_close"
    ANNIVERSARY = "anniversary"


class SentimentLevel(str, Enum):
    """Sentiment classification."""
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


# =============================================================================
# Database Models
# =============================================================================

class SurveyTemplate(Base):
    """Survey template definition."""
    __tablename__ = "survey_templates"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False, default=1)

    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text)
    survey_type = Column(SQLEnum(SurveyType), nullable=False, default=SurveyType.CSAT)
    status = Column(SQLEnum(SurveyStatus), nullable=False, default=SurveyStatus.DRAFT)

    # Trigger configuration
    trigger_type = Column(SQLEnum(TriggerType), default=TriggerType.MANUAL)
    trigger_config = Column(JSON, default={})  # e.g., {"days_after": 7, "milestone": "funded"}

    # Settings
    is_anonymous = Column(Boolean, default=False)
    expires_days = Column(Integer, default=30)  # Days until survey expires
    reminder_enabled = Column(Boolean, default=True)
    reminder_days = Column(Integer, default=3)  # Days before sending reminder
    max_reminders = Column(Integer, default=2)

    # Branding
    intro_message = Column(Text)
    thank_you_message = Column(Text)
    logo_url = Column(String(500))
    primary_color = Column(String(20), default="#319795")

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    questions = relationship("SurveyQuestion", back_populates="template", cascade="all, delete-orphan")
    responses = relationship("SurveyResponse", back_populates="template")

    __table_args__ = (
        Index('ix_survey_templates_org_status', 'organization_id', 'status'),
        Index('ix_survey_templates_org_type', 'organization_id', 'survey_type'),
    )


class SurveyQuestion(Base):
    """Individual survey question."""
    __tablename__ = "survey_questions"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("survey_templates.id", ondelete="CASCADE"), nullable=False)

    # Question content
    question_text = Column(Text, nullable=False)
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    help_text = Column(Text)

    # Options for choice questions
    options = Column(JSON, default=[])  # ["Option 1", "Option 2", ...]

    # Validation
    is_required = Column(Boolean, default=True)
    min_value = Column(Integer)  # For scale questions
    max_value = Column(Integer)  # For scale questions
    min_length = Column(Integer)  # For text questions
    max_length = Column(Integer)  # For text questions

    # Display
    order = Column(Integer, default=0)
    conditional_logic = Column(JSON)  # {"show_if": {"question_id": 1, "value": "yes"}}

    # Scoring
    weight = Column(Float, default=1.0)  # Weight for overall score calculation

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    template = relationship("SurveyTemplate", back_populates="questions")
    answers = relationship("SurveyAnswer", back_populates="question")

    __table_args__ = (
        Index('ix_survey_questions_template_order', 'template_id', 'order'),
    )


class SurveyResponse(Base):
    """Individual survey response (one per respondent)."""
    __tablename__ = "survey_responses"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False, default=1)
    template_id = Column(Integer, ForeignKey("survey_templates.id"), nullable=False)

    # Respondent info
    borrower_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, index=True)
    email = Column(String(255))
    phone = Column(String(50))

    # Access
    access_token = Column(String(100), unique=True, index=True)

    # Status tracking
    status = Column(SQLEnum(ResponseStatus), default=ResponseStatus.PENDING)
    sent_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))

    # Reminders
    reminder_count = Column(Integer, default=0)
    last_reminder_at = Column(DateTime(timezone=True))

    # Scores (calculated after completion)
    nps_score = Column(Integer)  # 0-10 for NPS
    csat_score = Column(Float)   # Calculated average
    overall_score = Column(Float)
    sentiment = Column(SQLEnum(SentimentLevel))

    # Context
    trigger_event = Column(String(100))  # What triggered this survey
    loan_officer_id = Column(Integer, ForeignKey("users.id"))

    # Metadata
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    completion_time_seconds = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    template = relationship("SurveyTemplate", back_populates="responses")
    answers = relationship("SurveyAnswer", back_populates="response", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_survey_responses_org_status', 'organization_id', 'status'),
        Index('ix_survey_responses_template_status', 'template_id', 'status'),
        Index('ix_survey_responses_loan', 'loan_id'),
    )


class SurveyAnswer(Base):
    """Individual answer to a survey question."""
    __tablename__ = "survey_answers"

    id = Column(Integer, primary_key=True, index=True)
    response_id = Column(Integer, ForeignKey("survey_responses.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("survey_questions.id"), nullable=False)

    # Answer content
    answer_text = Column(Text)
    answer_numeric = Column(Float)
    answer_json = Column(JSON)  # For multi-select, etc.

    # Sentiment analysis (for text responses)
    sentiment = Column(SQLEnum(SentimentLevel))
    sentiment_score = Column(Float)  # -1 to 1
    key_phrases = Column(JSON, default=[])

    answered_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    response = relationship("SurveyResponse", back_populates="answers")
    question = relationship("SurveyQuestion", back_populates="answers")

    __table_args__ = (
        Index('ix_survey_answers_response_question', 'response_id', 'question_id'),
    )


class SurveyAnalytics(Base):
    """Aggregated survey analytics (daily snapshots)."""
    __tablename__ = "survey_analytics"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)
    template_id = Column(Integer, ForeignKey("survey_templates.id"))

    # Time period
    date = Column(DateTime(timezone=True), nullable=False)

    # Volume metrics
    sent_count = Column(Integer, default=0)
    started_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    expired_count = Column(Integer, default=0)

    # Response rate
    response_rate = Column(Float)  # completed / sent
    completion_rate = Column(Float)  # completed / started

    # Score metrics
    avg_nps_score = Column(Float)
    avg_csat_score = Column(Float)
    avg_overall_score = Column(Float)

    # NPS breakdown
    nps_promoters = Column(Integer, default=0)   # 9-10
    nps_passives = Column(Integer, default=0)    # 7-8
    nps_detractors = Column(Integer, default=0)  # 0-6
    nps_calculated = Column(Float)  # (promoters - detractors) / total * 100

    # Sentiment breakdown
    sentiment_very_positive = Column(Integer, default=0)
    sentiment_positive = Column(Integer, default=0)
    sentiment_neutral = Column(Integer, default=0)
    sentiment_negative = Column(Integer, default=0)
    sentiment_very_negative = Column(Integer, default=0)

    # Timing
    avg_completion_time = Column(Integer)  # seconds

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_survey_analytics_org_date', 'organization_id', 'date'),
        Index('ix_survey_analytics_template_date', 'template_id', 'date'),
    )


class SavingsValidation(Base):
    """Track and validate promised savings vs actual."""
    __tablename__ = "savings_validations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)
    loan_id = Column(Integer, index=True, nullable=False)
    borrower_id = Column(Integer, ForeignKey("leads.id"))

    # Promised savings
    promised_monthly_savings = Column(Float)
    promised_total_savings = Column(Float)
    promised_rate_reduction = Column(Float)
    savings_source = Column(String(100))  # estimate_comparison, rate_advisory, etc.

    # Actual (from survey)
    reported_monthly_savings = Column(Float)
    reported_satisfied = Column(Boolean)
    discrepancy_amount = Column(Float)

    # Survey link
    survey_response_id = Column(Integer, ForeignKey("survey_responses.id"))

    # Follow-up
    follow_up_required = Column(Boolean, default=False)
    follow_up_notes = Column(Text)
    resolved_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# =============================================================================
# Pydantic Schemas
# =============================================================================

class QuestionCreate(BaseModel):
    """Create a survey question."""
    question_text: str
    question_type: QuestionType
    help_text: Optional[str] = None
    options: Optional[List[str]] = []
    is_required: bool = True
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    order: int = 0
    weight: float = 1.0
    conditional_logic: Optional[dict] = None


class SurveyTemplateCreate(BaseModel):
    """Create a survey template."""
    name: str
    description: Optional[str] = None
    survey_type: SurveyType = SurveyType.CSAT
    trigger_type: TriggerType = TriggerType.MANUAL
    trigger_config: Optional[dict] = {}
    is_anonymous: bool = False
    expires_days: int = 30
    reminder_enabled: bool = True
    reminder_days: int = 3
    max_reminders: int = 2
    intro_message: Optional[str] = None
    thank_you_message: Optional[str] = None
    questions: List[QuestionCreate] = []


class SurveyTemplateUpdate(BaseModel):
    """Update a survey template."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[SurveyStatus] = None
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[dict] = None
    is_anonymous: Optional[bool] = None
    expires_days: Optional[int] = None
    reminder_enabled: Optional[bool] = None
    intro_message: Optional[str] = None
    thank_you_message: Optional[str] = None


class SendSurveyRequest(BaseModel):
    """Request to send a survey."""
    template_id: int
    email: str
    borrower_id: Optional[int] = None
    loan_id: Optional[int] = None
    loan_officer_id: Optional[int] = None
    trigger_event: Optional[str] = None


class SubmitAnswerRequest(BaseModel):
    """Submit an answer to a question."""
    question_id: int
    answer_text: Optional[str] = None
    answer_numeric: Optional[float] = None
    answer_json: Optional[dict] = None


class SurveyResponseSubmit(BaseModel):
    """Submit complete survey response."""
    answers: List[SubmitAnswerRequest]


class AnalyticsFilter(BaseModel):
    """Filter for analytics queries."""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    template_id: Optional[int] = None
    survey_type: Optional[SurveyType] = None
    loan_officer_id: Optional[int] = None
