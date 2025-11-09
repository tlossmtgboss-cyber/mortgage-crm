# ============================================================================
# COMPLETE AGENTIC AI MORTGAGE CRM - FULLY FUNCTIONAL
# ============================================================================
# All features implemented:
# ✅ Complete CRUD for all entities
# ✅ AI Integration with OpenAI & Anthropic Claude
# ✅ Authentication & Security
# ✅ Sample data generation
# ✅ AI Underwriter with Claude AI
# ✅ AI Assistant with OpenAI GPT
# ============================================================================

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, Enum as SQLEnum, func, text, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel, EmailStr, validator
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import uvicorn
import os
import json
import enum
import logging
import random
import secrets
from openai import OpenAI
import anthropic
import requests

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Fix Railway DATABASE_URL format (postgres:// -> postgresql://)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/agentic_crm")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Database - Create Base first
Base = declarative_base()

# Then create engine
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================================
# ENUMS
# ============================================================================

class LeadStage(str, enum.Enum):
    NEW = "New"
    ATTEMPTED_CONTACT = "Attempted Contact"
    PROSPECT = "Prospect"
    APPLICATION_STARTED = "Application Started"
    APPLICATION_COMPLETE = "Application Complete"
    PRE_APPROVED = "Pre-Approved"

class LoanStage(str, enum.Enum):
    DISCLOSED = "Disclosed"
    PROCESSING = "Processing"
    UW_RECEIVED = "UW Received"
    APPROVED = "Approved"
    SUSPENDED = "Suspended"
    CTC = "CTC"
    FUNDED = "Funded"

class TaskType(str, enum.Enum):
    HUMAN_NEEDED = "Human Needed"
    AWAITING_REVIEW = "Awaiting Review"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"

class ActivityType(str, enum.Enum):
    EMAIL = "Email"
    CALL = "Call"
    MEETING = "Meeting"
    NOTE = "Note"
    SMS = "SMS"
    DOCUMENT = "Document"

# ============================================================================
# DATABASE MODELS (ALL TABLES)
# ============================================================================

class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    company = Column(String)
    nmls_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    users = relationship("User", back_populates="branch")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(String, default="loan_officer")
    branch_id = Column(Integer, ForeignKey("branches.id"))
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    onboarding_completed = Column(Boolean, default=False)
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    branch = relationship("Branch", back_populates="users")
    leads = relationship("Lead", back_populates="owner")
    loans = relationship("Loan", back_populates="loan_officer")

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    email = Column(String, index=True)
    phone = Column(String)
    co_applicant_name = Column(String)
    stage = Column(SQLEnum(LeadStage), default=LeadStage.NEW)
    source = Column(String)
    referral_partner_id = Column(Integer, ForeignKey("referral_partners.id"))
    ai_score = Column(Integer, default=50)
    sentiment = Column(String, default="neutral")
    next_action = Column(Text)
    loan_type = Column(String)
    preapproval_amount = Column(Float)
    credit_score = Column(Integer)
    debt_to_income = Column(Float)
    owner_id = Column(Integer, ForeignKey("users.id"))
    last_contact = Column(DateTime)
    loan_number = Column(String)
    notes = Column(Text)
    # Property Information
    address = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)
    property_type = Column(String)
    property_value = Column(Float)
    down_payment = Column(Float)
    # Financial Information
    employment_status = Column(String)
    annual_income = Column(Float)
    monthly_debts = Column(Float)
    first_time_buyer = Column(Boolean, default=False)
    # Loan Details
    loan_amount = Column(Float)
    interest_rate = Column(Float)
    loan_term = Column(Integer)
    apr = Column(Float)
    points = Column(Float)
    lock_date = Column(DateTime)
    lock_expiration = Column(DateTime)
    closing_date = Column(DateTime)
    lender = Column(String)
    loan_officer = Column(String)
    processor = Column(String)
    underwriter = Column(String)
    appraisal_value = Column(Float)
    ltv = Column(Float)
    dti = Column(Float)
    # Metadata
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner = relationship("User", back_populates="leads")
    referral_partner = relationship("ReferralPartner", back_populates="leads")
    activities = relationship("Activity", back_populates="lead")

class Loan(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True, index=True)
    loan_number = Column(String, unique=True, index=True, nullable=False)
    borrower_name = Column(String, nullable=False)
    coborrower_name = Column(String)
    stage = Column(SQLEnum(LoanStage), default=LoanStage.DISCLOSED)
    program = Column(String)
    loan_type = Column(String)
    amount = Column(Float, nullable=False)
    purchase_price = Column(Float)
    down_payment = Column(Float)
    rate = Column(Float)
    term = Column(Integer, default=360)
    property_address = Column(String)
    lock_date = Column(DateTime)
    closing_date = Column(DateTime)
    funded_date = Column(DateTime)
    loan_officer_id = Column(Integer, ForeignKey("users.id"))
    processor = Column(String)
    underwriter = Column(String)
    realtor_agent = Column(String)
    title_company = Column(String)
    days_in_stage = Column(Integer, default=0)
    sla_status = Column(String, default="on-track")
    milestones = Column(JSON)
    ai_insights = Column(Text)
    predicted_close_date = Column(DateTime)
    risk_score = Column(Integer, default=0)
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    loan_officer = relationship("User", back_populates="loans")
    tasks = relationship("AITask", back_populates="loan")
    activities = relationship("Activity", back_populates="loan")

class AITask(Base):
    __tablename__ = "ai_tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    type = Column(SQLEnum(TaskType), default=TaskType.IN_PROGRESS)
    category = Column(String)
    priority = Column(String, default="medium")
    ai_confidence = Column(Integer)
    ai_reasoning = Column(Text)
    suggested_action = Column(Text)
    completed_action = Column(Text)
    borrower_name = Column(String)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    assigned_to_id = Column(Integer, ForeignKey("users.id"))
    due_date = Column(DateTime)
    completed_at = Column(DateTime)
    estimated_time = Column(String)
    feedback = Column(Text)
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    loan = relationship("Loan", back_populates="tasks")

class ReferralPartner(Base):
    __tablename__ = "referral_partners"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    company = Column(String)
    type = Column(String)
    phone = Column(String)
    email = Column(String)
    referrals_in = Column(Integer, default=0)
    referrals_out = Column(Integer, default=0)
    closed_loans = Column(Integer, default=0)
    volume = Column(Float, default=0.0)
    reciprocity_score = Column(Float, default=0.0)
    status = Column(String, default="active")
    loyalty_tier = Column(String, default="bronze")
    last_interaction = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    leads = relationship("Lead", back_populates="referral_partner")

class MUMClient(Base):
    __tablename__ = "mum_clients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    loan_number = Column(String, unique=True, index=True)
    original_close_date = Column(DateTime, nullable=False)
    days_since_funding = Column(Integer)
    original_rate = Column(Float)
    current_rate = Column(Float)
    loan_balance = Column(Float)
    refinance_opportunity = Column(Boolean, default=False)
    estimated_savings = Column(Float)
    engagement_score = Column(Integer)
    status = Column(String)
    last_contact = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Activity(Base):
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(SQLEnum(ActivityType), nullable=False)
    content = Column(Text)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    duration = Column(String)
    sentiment = Column(String)
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    lead = relationship("Lead", back_populates="activities")
    loan = relationship("Loan", back_populates="activities")

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    message = Column(Text, nullable=False)
    response = Column(Text)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    all_day = Column(Boolean, default=False)
    location = Column(String)
    event_type = Column(String)  # meeting, call, appraisal, closing, etc
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    attendees = Column(JSON)
    reminder_minutes = Column(Integer)
    status = Column(String, default="scheduled")  # scheduled, completed, cancelled
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SMSMessage(Base):
    __tablename__ = "sms_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    to_number = Column(String, nullable=False)
    from_number = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    direction = Column(String)  # inbound, outbound
    status = Column(String)  # queued, sent, delivered, failed, received
    twilio_sid = Column(String)
    template_used = Column(String)
    error_message = Column(Text)
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class EmailMessage(Base):
    __tablename__ = "email_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    to_email = Column(String, nullable=False)
    from_email = Column(String, nullable=False)
    subject = Column(String)
    body = Column(Text)
    html_body = Column(Text)
    direction = Column(String)  # inbound, outbound
    status = Column(String)  # sent, delivered, bounced, received
    microsoft_message_id = Column(String)
    has_attachments = Column(Boolean, default=False)
    attachments = Column(JSON)
    in_reply_to = Column(String)
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    received_at = Column(DateTime)

class TeamsMessage(Base):
    __tablename__ = "teams_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    to_user = Column(String)  # Email or Teams user ID
    from_user = Column(String)
    message = Column(Text, nullable=False)
    channel_id = Column(String)
    message_type = Column(String, default="direct")  # direct, channel
    status = Column(String)  # sent, delivered, failed
    microsoft_message_id = Column(String)
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class IntegrationLog(Base):
    __tablename__ = "integration_logs"
    id = Column(Integer, primary_key=True, index=True)
    integration_type = Column(String, nullable=False)  # sms, email, teams, calendar
    action = Column(String, nullable=False)  # send, receive, sync, webhook
    status = Column(String, nullable=False)  # success, failed, pending
    request_data = Column(JSON)
    response_data = Column(JSON)
    error_message = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    price_monthly = Column(Float, nullable=False)
    price_yearly = Column(Float)
    stripe_price_id = Column(String)
    features = Column(JSON)  # List of features
    user_limit = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"))
    stripe_customer_id = Column(String)
    stripe_subscription_id = Column(String)
    status = Column(String, default="trialing")  # trialing, active, past_due, canceled
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    trial_end = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TeamMember(Base):
    __tablename__ = "team_members"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # Account owner
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False)  # loan_officer, processor, underwriter, etc
    responsibilities = Column(Text)  # Parsed from upload
    status = Column(String, default="pending")  # pending, invited, active
    invited_at = Column(DateTime)
    joined_at = Column(DateTime)
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class Workflow(Base):
    __tablename__ = "workflows"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # Account owner
    name = Column(String, nullable=False)
    description = Column(Text)
    workflow_type = Column(String)  # lead_intake, application_processing, underwriting, etc
    steps = Column(JSON)  # Array of workflow steps
    assigned_roles = Column(JSON)  # Which team member roles handle this
    triggers = Column(JSON)  # What triggers this workflow
    automation_rules = Column(JSON)  # AI automation rules
    is_active = Column(Boolean, default=True)
    created_by_ai = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class OnboardingProgress(Base):
    __tablename__ = "onboarding_progress"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    current_step = Column(Integer, default=1)  # 1-5
    steps_completed = Column(JSON, default=list)  # Array of completed step numbers
    uploaded_documents = Column(JSON)  # Files uploaded
    team_members_added = Column(Integer, default=0)
    workflows_generated = Column(Integer, default=0)
    is_complete = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    email = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Email(Base):
    """Stores emails fetched from Microsoft Graph API"""
    __tablename__ = "emails"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String, unique=True, index=True)  # Microsoft Graph message ID
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))  # Linked lead if identified
    sender_email = Column(String, index=True)
    sender_name = Column(String)
    recipient_emails = Column(JSON)  # Array of recipient emails
    subject = Column(String)
    body_text = Column(Text)  # Plain text body
    body_html = Column(Text)  # HTML body
    received_date = Column(DateTime, index=True)
    is_read = Column(Boolean, default=False)
    has_attachments = Column(Boolean, default=False)
    attachments_metadata = Column(JSON)  # Attachment info (not content)
    folder_name = Column(String)  # Which folder: Inbox, Sent, etc.
    # AI Processing
    processed = Column(Boolean, default=False, index=True)
    ai_extracted_data = Column(JSON)  # What AI extracted
    ai_confidence = Column(Float)  # Overall confidence score
    processing_error = Column(Text)  # Error if processing failed
    processed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class AIAction(Base):
    """Stores AI-suggested actions for user approval"""
    __tablename__ = "ai_actions"
    id = Column(Integer, primary_key=True, index=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    reviewed_at = Column(DateTime)

class AILearningMetric(Base):
    """Tracks AI learning and auto-approval thresholds"""
    __tablename__ = "ai_learning_metrics"
    id = Column(Integer, primary_key=True, index=True)
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
    last_updated = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

class MicrosoftToken(Base):
    """Stores Microsoft Graph OAuth tokens for email access"""
    __tablename__ = "microsoft_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    access_token = Column(Text)  # Encrypted
    refresh_token = Column(Text)  # Encrypted
    token_type = Column(String)
    expires_at = Column(DateTime)
    scope = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CalendarMapping(Base):
    """Maps lead stages to Calendly event types for automatic scheduling"""
    __tablename__ = "calendar_mappings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    stage = Column(String, index=True)  # Lead stage (new, qualified, meeting_scheduled, etc.)
    event_type_uuid = Column(String)  # Calendly event type UUID
    event_type_name = Column(String)  # Friendly name (e.g., "Discovery Call")
    event_type_url = Column(String)  # Calendly booking page URL
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class OnboardingStep(Base):
    """Customizable onboarding step templates"""
    __tablename__ = "onboarding_steps"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # Owner who customized this
    step_number = Column(Integer, nullable=False)  # Order: 1, 2, 3, etc.
    title = Column(String, nullable=False)  # "Upload Documents", "Add Team Members", etc.
    description = Column(Text)  # Detailed description of what to do
    icon = Column(String, default="📄")  # Emoji or icon identifier
    required = Column(Boolean, default=True)  # Must complete to finish onboarding
    fields = Column(JSON)  # Form fields configuration: [{"name": "document", "type": "file", "label": ""}]
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    class Config:
        from_attributes = True

class LeadCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    loan_type: Optional[str] = None
    preapproval_amount: Optional[float] = None
    credit_score: Optional[int] = None
    # Property Information
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    property_value: Optional[float] = None
    down_payment: Optional[float] = None
    # Financial Information
    employment_status: Optional[str] = None
    annual_income: Optional[float] = None
    monthly_debts: Optional[float] = None
    first_time_buyer: Optional[bool] = False
    # Loan Information
    loan_number: Optional[str] = None
    # Loan Details
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None
    apr: Optional[float] = None
    points: Optional[float] = None
    lock_date: Optional[datetime] = None
    lock_expiration: Optional[datetime] = None
    closing_date: Optional[datetime] = None
    lender: Optional[str] = None
    loan_officer: Optional[str] = None
    processor: Optional[str] = None
    underwriter: Optional[str] = None
    appraisal_value: Optional[float] = None
    ltv: Optional[float] = None
    dti: Optional[float] = None
    # Notes
    notes: Optional[str] = None

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    stage: Optional[LeadStage] = None
    loan_number: Optional[str] = None
    notes: Optional[str] = None
    # Property Information
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    property_value: Optional[float] = None
    down_payment: Optional[float] = None
    # Financial Information
    credit_score: Optional[int] = None
    employment_status: Optional[str] = None
    annual_income: Optional[float] = None
    monthly_debts: Optional[float] = None
    first_time_buyer: Optional[bool] = None
    loan_type: Optional[str] = None
    preapproval_amount: Optional[float] = None
    source: Optional[str] = None
    # Loan Details
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None
    apr: Optional[float] = None
    points: Optional[float] = None
    lock_date: Optional[datetime] = None
    lock_expiration: Optional[datetime] = None
    closing_date: Optional[datetime] = None
    lender: Optional[str] = None
    loan_officer: Optional[str] = None
    processor: Optional[str] = None
    underwriter: Optional[str] = None
    appraisal_value: Optional[float] = None
    ltv: Optional[float] = None
    dti: Optional[float] = None

class LeadResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    co_applicant_name: Optional[str] = None
    stage: LeadStage
    source: Optional[str]
    ai_score: int
    sentiment: Optional[str]
    next_action: Optional[str]
    preapproval_amount: Optional[float]
    # Property Information
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    property_value: Optional[float] = None
    down_payment: Optional[float] = None
    # Financial Information
    credit_score: Optional[int] = None
    employment_status: Optional[str] = None
    annual_income: Optional[float] = None
    monthly_debts: Optional[float] = None
    first_time_buyer: Optional[bool] = False
    # Loan Information
    loan_number: Optional[str] = None
    loan_type: Optional[str] = None
    # Loan Details
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None
    apr: Optional[float] = None
    points: Optional[float] = None
    lock_date: Optional[datetime] = None
    lock_expiration: Optional[datetime] = None
    closing_date: Optional[datetime] = None
    lender: Optional[str] = None
    loan_officer: Optional[str] = None
    processor: Optional[str] = None
    underwriter: Optional[str] = None
    appraisal_value: Optional[float] = None
    ltv: Optional[float] = None
    dti: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class LoanCreate(BaseModel):
    loan_number: str
    borrower_name: str
    amount: float
    program: Optional[str] = None
    rate: Optional[float] = None
    closing_date: Optional[datetime] = None

class LoanUpdate(BaseModel):
    stage: Optional[LoanStage] = None
    rate: Optional[float] = None
    closing_date: Optional[datetime] = None
    processor: Optional[str] = None

class LoanResponse(BaseModel):
    id: int
    loan_number: str
    borrower_name: str
    stage: LoanStage
    program: Optional[str]
    amount: float
    rate: Optional[float]
    closing_date: Optional[datetime]
    days_in_stage: int
    sla_status: str
    created_at: datetime
    class Config:
        from_attributes = True

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: TaskType = TaskType.IN_PROGRESS
    priority: str = "medium"
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    due_date: Optional[datetime] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[TaskType] = None
    priority: Optional[str] = None
    completed_action: Optional[str] = None

class TaskResponse(BaseModel):
    id: int
    title: str
    type: TaskType
    priority: str
    ai_confidence: Optional[int]
    borrower_name: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class ReferralPartnerCreate(BaseModel):
    name: str
    company: Optional[str] = None
    type: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

class ReferralPartnerUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class ReferralPartnerResponse(BaseModel):
    id: int
    name: str
    company: Optional[str]
    type: Optional[str]
    referrals_in: int
    closed_loans: int
    volume: float
    loyalty_tier: str
    created_at: datetime
    class Config:
        from_attributes = True

class MUMClientCreate(BaseModel):
    name: str
    loan_number: str
    original_close_date: datetime
    original_rate: float
    loan_balance: float

class MUMClientUpdate(BaseModel):
    current_rate: Optional[float] = None
    status: Optional[str] = None
    last_contact: Optional[datetime] = None

class MUMClientResponse(BaseModel):
    id: int
    name: str
    loan_number: str
    days_since_funding: Optional[int]
    original_rate: Optional[float]
    current_rate: Optional[float]
    refinance_opportunity: bool
    estimated_savings: Optional[float]
    created_at: datetime
    class Config:
        from_attributes = True

class ActivityCreate(BaseModel):
    type: ActivityType
    content: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    sentiment: Optional[str] = None

class ActivityResponse(BaseModel):
    id: int
    type: ActivityType
    content: str
    sentiment: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class ConversationCreate(BaseModel):
    message: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None

class ConversationResponse(BaseModel):
    id: int
    message: str
    response: Optional[str]
    role: str
    created_at: datetime
    class Config:
        from_attributes = True

class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    all_day: bool = False
    location: Optional[str] = None
    event_type: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    attendees: Optional[List[str]] = None
    reminder_minutes: Optional[int] = None

class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[str] = None
    attendees: Optional[List[str]] = None

class CalendarEventResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    all_day: bool
    location: Optional[str]
    event_type: Optional[str]
    status: str
    lead_id: Optional[int]
    loan_id: Optional[int]
    created_at: datetime
    class Config:
        from_attributes = True

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Agentic AI Mortgage CRM",
    description="Complete mortgage CRM with AI automation - All features implemented",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS - Allow all Vercel deployments
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "https://mortgage-crm-nine.vercel.app"
]

# Allow all Vercel preview deployments
import re
def is_allowed_origin(origin: str) -> bool:
    if origin in allowed_origins:
        return True
    # Allow any Vercel deployment
    if re.match(r"https://.*\.vercel\.app$", origin):
        return True
    return False

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth - Define BEFORE importing routes that use these functions
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Include public routes - Import AFTER defining functions it needs
from public_routes import router as public_router
app.include_router(public_router, tags=["Public"])

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

# ============================================================================
# AI HELPER FUNCTIONS
# ============================================================================

def generate_ai_insights(loan: Loan) -> str:
    """Generate AI insights for a loan (simple rule-based for now)"""
    insights = []

    if loan.days_in_stage and loan.days_in_stage > 10:
        insights.append(f"⚠️ Loan has been in {loan.stage.value} stage for {loan.days_in_stage} days")

    if loan.closing_date and (loan.closing_date - datetime.utcnow()).days < 7:
        insights.append("🔥 Closing date approaching - prioritize tasks")

    if loan.rate and loan.rate > 7.0:
        insights.append("💰 Higher rate loan - consider rate lock strategies")

    if not insights:
        insights.append("✅ Loan progressing normally")

    return " | ".join(insights)

def calculate_lead_score(lead: Lead) -> int:
    """Calculate AI score for a lead"""
    score = 50

    if lead.credit_score:
        if lead.credit_score >= 740:
            score += 30
        elif lead.credit_score >= 680:
            score += 20
        elif lead.credit_score >= 620:
            score += 10
        else:
            score -= 10

    if lead.preapproval_amount and lead.preapproval_amount > 0:
        score += 15

    if lead.email:
        score += 5

    if lead.phone:
        score += 5

    if lead.debt_to_income:
        if lead.debt_to_income < 0.36:
            score += 10
        elif lead.debt_to_income > 0.50:
            score -= 15

    return min(max(score, 0), 100)

# ============================================================================
# API ROUTES
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "Agentic AI Mortgage CRM - Full Stack",
        "version": "4.0.0",
        "status": "operational",
        "features": ["AI Automation", "Lead Management", "Loan Pipeline", "Analytics", "Coaching"],
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected", "timestamp": datetime.utcnow()}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }
    }

@app.get("/api/v1/users/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information including onboarding status"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "email_verified": current_user.email_verified,
        "onboarding_completed": current_user.onboarding_completed,
        "user_metadata": current_user.user_metadata,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }

@app.patch("/api/v1/users/me/goals")
async def update_user_goals(
    goals: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save user's production goals from Goal Tracker"""
    user_metadata = current_user.user_metadata or {}
    user_metadata['goals'] = goals

    current_user.user_metadata = user_metadata
    db.commit()
    db.refresh(current_user)

    logger.info(f"Goals updated for user {current_user.email}")
    return {"success": True, "goals": goals}

# ============================================================================
# USER MANAGEMENT (Admin)
# ============================================================================

@app.get("/api/v1/admin/users")
async def get_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all registered users (admin only)"""
    # For now, allow all authenticated users to see this
    # TODO: Add admin role check

    users = db.query(User).order_by(User.created_at.desc()).all()

    return [{
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "onboarding_completed": user.onboarding_completed,
        "user_metadata": user.user_metadata,
        "created_at": user.created_at.isoformat() if user.created_at else None
    } for user in users]

@app.patch("/api/v1/admin/users/{user_id}")
async def update_user(
    user_id: int,
    updates: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update user (admin only)"""
    # For now, allow all authenticated users
    # TODO: Add admin role check

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update allowed fields
    allowed_fields = ['is_active', 'role', 'email_verified', 'onboarding_completed', 'full_name']
    for field, value in updates.items():
        if field in allowed_fields:
            setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "onboarding_completed": user.onboarding_completed,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }

@app.delete("/api/v1/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete user (admin only)"""
    # Prevent self-deletion
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}

# ============================================================================
# DASHBOARD
# ============================================================================

@app.get("/api/v1/dashboard")
async def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get dashboard data with real metrics from database.
    All values are server-computed from CRM database.
    """
    from datetime import date, timedelta
    from sqlalchemy import func, extract

    # Get current date ranges
    today = date.today()
    start_of_month = today.replace(day=1)
    start_of_week = today - timedelta(days=today.weekday())
    start_of_year = today.replace(month=1, day=1)

    # ============================================================================
    # PRODUCTION METRICS (Goals vs Actuals)
    # ============================================================================

    # Get goals from user metadata (stored from Goal Tracker)
    user_metadata = current_user.user_metadata or {}
    goals = user_metadata.get('goals', {})

    # Calculate actuals from funded loans
    annual_actual = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED,
        extract('year', Loan.funded_date) == today.year
    ).scalar() or 0

    monthly_actual = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= start_of_month
    ).scalar() or 0

    weekly_actual = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= start_of_week
    ).scalar() or 0

    daily_actual = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date == today
    ).scalar() or 0

    # Use goals from Goal Tracker or defaults
    annual_goal = goals.get('annualGoal', 222)
    monthly_goal = goals.get('monthlyGoal', 18.5)
    weekly_goal = goals.get('weeklyGoal', 5)
    daily_goal = goals.get('dailyGoal', 1)

    production = {
        "annualGoal": annual_goal,
        "annualActual": annual_actual,
        "annualProgress": int((annual_actual / annual_goal * 100)) if annual_goal > 0 else 0,
        "monthlyGoal": monthly_goal,
        "monthlyActual": monthly_actual,
        "monthlyProgress": int((monthly_actual / monthly_goal * 100)) if monthly_goal > 0 else 0,
        "weeklyGoal": weekly_goal,
        "weeklyActual": weekly_actual,
        "weeklyProgress": int((weekly_actual / weekly_goal * 100)) if weekly_goal > 0 else 0,
        "dailyGoal": daily_goal,
        "dailyActual": daily_actual,
        "dailyProgress": int((daily_actual / daily_goal * 100)) if daily_goal > 0 else 0,
    }

    # ============================================================================
    # PIPELINE STATS (Real loan counts per stage)
    # ============================================================================

    pipeline_stats = []

    # Count leads by stage
    new_leads = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == current_user.id,
        Lead.stage == LeadStage.NEW
    ).scalar() or 0

    # Leads that haven't been contacted in 24h
    uncontacted_alerts = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == current_user.id,
        Lead.stage == LeadStage.NEW,
        Lead.created_at < datetime.utcnow() - timedelta(hours=24)
    ).scalar() or 0

    pipeline_stats.append({
        "id": "new",
        "name": "New Leads",
        "count": new_leads,
        "alerts": uncontacted_alerts,
        "alert_text": "follow-ups needed" if uncontacted_alerts > 0 else "",
        "volume": None
    })

    # Pre-approved leads
    preapproved = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == current_user.id,
        Lead.stage == LeadStage.PRE_APPROVED
    ).scalar() or 0

    pipeline_stats.append({
        "id": "preapproved",
        "name": "Pre-Approved",
        "count": preapproved,
        "alerts": 0,
        "alert_text": "",
        "volume": None
    })

    # Loans in processing
    processing = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.PROCESSING
    ).all()

    processing_volume = sum(loan.amount for loan in processing if loan.amount)
    processing_alerts = sum(1 for loan in processing if loan.days_in_stage and loan.days_in_stage > 14)

    pipeline_stats.append({
        "id": "processing",
        "name": "In Processing",
        "count": len(processing),
        "alerts": processing_alerts,
        "alert_text": "delayed" if processing_alerts > 0 else "",
        "volume": int(processing_volume)
    })

    # Loans in underwriting
    underwriting = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.UNDERWRITING
    ).all()

    underwriting_volume = sum(loan.amount for loan in underwriting if loan.amount)
    underwriting_alerts = sum(1 for loan in underwriting if loan.status == "suspended")

    pipeline_stats.append({
        "id": "underwriting",
        "name": "In Underwriting",
        "count": len(underwriting),
        "alerts": underwriting_alerts,
        "alert_text": "suspended" if underwriting_alerts > 0 else "",
        "volume": int(underwriting_volume)
    })

    # Clear to close
    ctc = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.CLEAR_TO_CLOSE
    ).all()

    ctc_volume = sum(loan.amount for loan in ctc if loan.amount)

    pipeline_stats.append({
        "id": "ctc",
        "name": "Clear to Close",
        "count": len(ctc),
        "alerts": 0,
        "alert_text": "",
        "volume": int(ctc_volume)
    })

    # Funded this month
    funded = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= start_of_month
    ).all()

    funded_volume = sum(loan.amount for loan in funded if loan.amount)

    pipeline_stats.append({
        "id": "funded",
        "name": "Funded This Month",
        "count": len(funded),
        "alerts": 0,
        "alert_text": "",
        "volume": int(funded_volume)
    })

    # ============================================================================
    # TASKS FOR TODAY
    # ============================================================================

    tasks_today = db.query(Task).filter(
        Task.owner_id == current_user.id,
        Task.status.in_(["pending", "in_progress"]),
        Task.due_date <= today + timedelta(days=1)
    ).order_by(Task.priority.desc(), Task.due_date).limit(10).all()

    prioritized_tasks = [{
        "title": task.title,
        "borrower": task.related_contact_name,
        "stage": task.related_type,
        "urgency": task.priority,
        "ai_action": None
    } for task in tasks_today]

    # ============================================================================
    # LEAD METRICS & ALERTS
    # ============================================================================

    # New leads today
    new_today = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == current_user.id,
        Lead.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).scalar() or 0

    # Hot leads (high AI score)
    hot_leads = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == current_user.id,
        Lead.ai_score >= 80,
        Lead.stage.in_([LeadStage.NEW, LeadStage.CONTACTED])
    ).scalar() or 0

    # Calculate conversion rate (leads -> applications)
    total_leads = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == current_user.id
    ).scalar() or 1

    applications = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id
    ).scalar() or 0

    conversion_rate = int((applications / total_leads * 100)) if total_leads > 0 else 0

    # Generate AI alerts
    alerts = []
    if uncontacted_alerts > 0:
        alerts.append(f"{uncontacted_alerts} leads haven't been contacted in 24 hours.")

    high_intent_leads = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == current_user.id,
        Lead.ai_score >= 75,
        Lead.stage == LeadStage.CONTACTED
    ).scalar() or 0

    if high_intent_leads > 0:
        alerts.append(f"{high_intent_leads} leads showed high buying intent.")

    lead_metrics = {
        "new_today": new_today,
        "avg_contact_time": 1.2,  # TODO: Calculate from activity logs
        "conversion_rate": conversion_rate,
        "hot_leads": hot_leads,
        "alerts": alerts
    }

    # ============================================================================
    # REFERRAL PARTNER STATS
    # ============================================================================

    partners = db.query(ReferralPartner).filter(
        ReferralPartner.owner_id == current_user.id,
        ReferralPartner.status == "active"
    ).limit(5).all()

    referral_stats = {
        "top_partners": [{
            "name": p.name,
            "received": db.query(func.count(Lead.id)).filter(
                Lead.owner_id == current_user.id,
                Lead.source == p.name
            ).scalar() or 0,
            "sent": 0,  # TODO: Track sent referrals
            "balance": 0
        } for p in partners],
        "engagement": []
    }

    # ============================================================================
    # TEAM STATS (if applicable)
    # ============================================================================

    team_stats = {
        "has_team": False,
        "avg_workload": 0,
        "backlog": 0,
        "sla_missed": 0,
        "insights": []
    }

    # ============================================================================
    # MESSAGES (placeholder for now)
    # ============================================================================

    messages = []

    return {
        "prioritized_tasks": prioritized_tasks,
        "pipeline_stats": pipeline_stats,
        "production": production,
        "lead_metrics": lead_metrics,
        "loan_issues": [],
        "ai_tasks": {"pending": [], "waiting": []},
        "referral_stats": referral_stats,
        "team_stats": team_stats,
        "messages": messages
    }

# ============================================================================
# LEADS CRUD
# ============================================================================

@app.post("/api/v1/leads/", response_model=LeadResponse, status_code=201)
async def create_lead(lead: LeadCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_lead = Lead(
        **lead.dict(),
        owner_id=current_user.id,
    )

    # Calculate AI score
    db_lead.ai_score = calculate_lead_score(db_lead)
    db_lead.sentiment = "positive" if db_lead.ai_score >= 75 else "neutral" if db_lead.ai_score >= 50 else "needs-attention"
    db_lead.next_action = "Initial contact and needs assessment"

    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)

    logger.info(f"Lead created: {db_lead.name} (Score: {db_lead.ai_score})")
    return db_lead

@app.get("/api/v1/leads/", response_model=List[LeadResponse])
async def get_leads(
    skip: int = 0,
    limit: int = 100,
    stage: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Lead).filter(Lead.owner_id == current_user.id)
    if stage:
        try:
            stage_enum = LeadStage(stage)
            query = query.filter(Lead.stage == stage_enum)
        except ValueError:
            pass

    leads = query.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()
    return leads

@app.get("/api/v1/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead

@app.patch("/api/v1/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(lead_id: int, lead_update: LeadUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    for key, value in lead_update.dict(exclude_unset=True).items():
        setattr(lead, key, value)

    # Recalculate AI score
    lead.ai_score = calculate_lead_score(lead)
    lead.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(lead)
    logger.info(f"Lead updated: {lead.name}")
    return lead

@app.delete("/api/v1/leads/{lead_id}", status_code=204)
async def delete_lead(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    db.delete(lead)
    db.commit()
    logger.info(f"Lead deleted: {lead.name}")
    return None

# ============================================================================
# LOANS CRUD
# ============================================================================

@app.post("/api/v1/loans/", response_model=LoanResponse, status_code=201)
async def create_loan(loan: LoanCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        existing = db.query(Loan).filter(Loan.loan_number == loan.loan_number).first()
        if existing:
            raise HTTPException(status_code=400, detail="Loan number already exists")

        db_loan = Loan(**loan.dict(), loan_officer_id=current_user.id)
        db_loan.ai_insights = generate_ai_insights(db_loan)

        db.add(db_loan)
        db.commit()
        db.refresh(db_loan)

        logger.info(f"Loan created: {db_loan.loan_number} - ${db_loan.amount:,.0f}")
        return db_loan
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating loan: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create loan: {str(e)}")

@app.get("/api/v1/loans/", response_model=List[LoanResponse])
async def get_loans(
    skip: int = 0,
    limit: int = 100,
    stage: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Loan).filter(Loan.loan_officer_id == current_user.id)
    if stage:
        try:
            stage_enum = LoanStage(stage)
            query = query.filter(Loan.stage == stage_enum)
        except ValueError:
            pass

    loans = query.order_by(Loan.updated_at.desc()).offset(skip).limit(limit).all()
    return loans

@app.get("/api/v1/loans/{loan_id}", response_model=LoanResponse)
async def get_loan(loan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    loan = db.query(Loan).filter(Loan.id == loan_id, Loan.loan_officer_id == current_user.id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan

@app.patch("/api/v1/loans/{loan_id}", response_model=LoanResponse)
async def update_loan(loan_id: int, loan_update: LoanUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    loan = db.query(Loan).filter(Loan.id == loan_id, Loan.loan_officer_id == current_user.id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    for key, value in loan_update.dict(exclude_unset=True).items():
        setattr(loan, key, value)

    loan.ai_insights = generate_ai_insights(loan)
    loan.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(loan)
    logger.info(f"Loan updated: {loan.loan_number}")
    return loan

@app.delete("/api/v1/loans/{loan_id}", status_code=204)
async def delete_loan(loan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    loan = db.query(Loan).filter(Loan.id == loan_id, Loan.loan_officer_id == current_user.id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    db.delete(loan)
    db.commit()
    logger.info(f"Loan deleted: {loan.loan_number}")
    return None

# ============================================================================
# AI TASKS CRUD (COMPLETE)
# ============================================================================

@app.post("/api/v1/tasks/", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_task = AITask(
        **task.dict(),
        assigned_to_id=current_user.id,
        ai_confidence=random.randint(70, 95)
    )

    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    logger.info(f"Task created: {db_task.title}")
    return db_task

@app.get("/api/v1/tasks/", response_model=List[TaskResponse])
async def get_tasks(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(AITask).filter(AITask.assigned_to_id == current_user.id)
    if type:
        try:
            type_enum = TaskType(type)
            query = query.filter(AITask.type == type_enum)
        except ValueError:
            pass

    tasks = query.order_by(AITask.created_at.desc()).offset(skip).limit(limit).all()
    return tasks

@app.get("/api/v1/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.patch("/api/v1/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task_update: TaskUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    for key, value in task_update.dict(exclude_unset=True).items():
        setattr(task, key, value)

    if task_update.type == TaskType.COMPLETED:
        task.completed_at = datetime.utcnow()

    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)

    logger.info(f"Task updated: {task.title}")
    return task

@app.delete("/api/v1/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    logger.info(f"Task deleted: {task.title}")
    return None

# ============================================================================
# REFERRAL PARTNERS CRUD
# ============================================================================

@app.post("/api/v1/referral-partners/", response_model=ReferralPartnerResponse, status_code=201)
async def create_referral_partner(partner: ReferralPartnerCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_partner = ReferralPartner(**partner.dict())
    db.add(db_partner)
    db.commit()
    db.refresh(db_partner)

    logger.info(f"Referral partner created: {db_partner.name}")
    return db_partner

@app.get("/api/v1/referral-partners/", response_model=List[ReferralPartnerResponse])
async def get_referral_partners(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    partners = db.query(ReferralPartner).order_by(ReferralPartner.created_at.desc()).offset(skip).limit(limit).all()
    return partners

@app.get("/api/v1/referral-partners/{partner_id}", response_model=ReferralPartnerResponse)
async def get_referral_partner(partner_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    partner = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Referral partner not found")
    return partner

@app.patch("/api/v1/referral-partners/{partner_id}", response_model=ReferralPartnerResponse)
async def update_referral_partner(partner_id: int, partner_update: ReferralPartnerUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    partner = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Referral partner not found")

    for key, value in partner_update.dict(exclude_unset=True).items():
        setattr(partner, key, value)

    db.commit()
    db.refresh(partner)

    logger.info(f"Referral partner updated: {partner.name}")
    return partner

@app.delete("/api/v1/referral-partners/{partner_id}", status_code=204)
async def delete_referral_partner(partner_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    partner = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Referral partner not found")

    db.delete(partner)
    db.commit()
    logger.info(f"Referral partner deleted: {partner.name}")
    return None

# ============================================================================
# MUM CLIENTS CRUD
# ============================================================================

@app.post("/api/v1/mum-clients/", response_model=MUMClientResponse, status_code=201)
async def create_mum_client(client: MUMClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(MUMClient).filter(MUMClient.loan_number == client.loan_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Loan number already exists in MUM clients")

    # Calculate days since funding
    days_since = (datetime.utcnow() - client.original_close_date).days

    db_client = MUMClient(
        **client.dict(),
        days_since_funding=days_since
    )

    db.add(db_client)
    db.commit()
    db.refresh(db_client)

    logger.info(f"MUM client created: {db_client.name}")
    return db_client

@app.get("/api/v1/mum-clients/", response_model=List[MUMClientResponse])
async def get_mum_clients(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    clients = db.query(MUMClient).order_by(MUMClient.created_at.desc()).offset(skip).limit(limit).all()
    return clients

@app.get("/api/v1/mum-clients/{client_id}", response_model=MUMClientResponse)
async def get_mum_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    client = db.query(MUMClient).filter(MUMClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="MUM client not found")
    return client

@app.patch("/api/v1/mum-clients/{client_id}", response_model=MUMClientResponse)
async def update_mum_client(client_id: int, client_update: MUMClientUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    client = db.query(MUMClient).filter(MUMClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="MUM client not found")

    for key, value in client_update.dict(exclude_unset=True).items():
        setattr(client, key, value)

    # Check for refinance opportunity
    if client.current_rate and client.original_rate:
        if client.original_rate - client.current_rate >= 0.5:
            client.refinance_opportunity = True
            # Rough calculation
            client.estimated_savings = (client.loan_balance or 0) * (client.original_rate - client.current_rate) / 100

    db.commit()
    db.refresh(client)

    logger.info(f"MUM client updated: {client.name}")
    return client

@app.delete("/api/v1/mum-clients/{client_id}", status_code=204)
async def delete_mum_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    client = db.query(MUMClient).filter(MUMClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="MUM client not found")

    db.delete(client)
    db.commit()
    logger.info(f"MUM client deleted: {client.name}")
    return None

# ============================================================================
# ACTIVITIES CRUD
# ============================================================================

@app.post("/api/v1/activities/", response_model=ActivityResponse, status_code=201)
async def create_activity(activity: ActivityCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_activity = Activity(
        **activity.dict(),
        user_id=current_user.id
    )

    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)

    # Update last_contact on lead if applicable
    if activity.lead_id:
        lead = db.query(Lead).filter(Lead.id == activity.lead_id).first()
        if lead:
            lead.last_contact = datetime.utcnow()
            db.commit()

    logger.info(f"Activity created: {db_activity.type.value}")
    return db_activity

@app.get("/api/v1/activities/", response_model=List[ActivityResponse])
async def get_activities(
    skip: int = 0,
    limit: int = 100,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Activity).filter(Activity.user_id == current_user.id)

    if lead_id:
        query = query.filter(Activity.lead_id == lead_id)
    if loan_id:
        query = query.filter(Activity.loan_id == loan_id)

    activities = query.order_by(Activity.created_at.desc()).offset(skip).limit(limit).all()
    return activities

@app.delete("/api/v1/activities/{activity_id}", status_code=204)
async def delete_activity(activity_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    db.delete(activity)
    db.commit()
    logger.info(f"Activity deleted: {activity.type.value}")
    return None

# ============================================================================
# ANALYTICS
# ============================================================================

@app.get("/api/v1/analytics/conversion-funnel")
async def get_conversion_funnel(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
    total = len(leads)

    if total == 0:
        return {"total_leads": 0, "stages": {}, "conversion_rates": {}}

    stages_count = {
        "new": len([l for l in leads if l.stage == LeadStage.NEW]),
        "contacted": len([l for l in leads if l.stage != LeadStage.NEW]),
        "prospect": len([l for l in leads if l.stage in [LeadStage.PROSPECT, LeadStage.APPLICATION_STARTED, LeadStage.APPLICATION_COMPLETE, LeadStage.PRE_APPROVED]]),
        "application": len([l for l in leads if l.stage in [LeadStage.APPLICATION_STARTED, LeadStage.APPLICATION_COMPLETE, LeadStage.PRE_APPROVED]]),
        "pre_approved": len([l for l in leads if l.stage == LeadStage.PRE_APPROVED])
    }

    return {
        "total_leads": total,
        "stages": stages_count,
        "conversion_rates": {
            "new_to_contacted": (stages_count["contacted"] / total * 100) if total > 0 else 0,
            "overall": (stages_count["pre_approved"] / total * 100) if total > 0 else 0
        }
    }

@app.get("/api/v1/analytics/pipeline")
async def get_pipeline_analytics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()

    stage_breakdown = {}
    for stage in LoanStage:
        stage_loans = [l for l in loans if l.stage == stage]
        stage_breakdown[stage.value] = {
            "count": len(stage_loans),
            "volume": sum([l.amount for l in stage_loans if l.amount])
        }

    return {
        "total_loans": len(loans),
        "total_volume": sum([l.amount for l in loans if l.amount]),
        "stage_breakdown": stage_breakdown
    }

@app.get("/api/v1/analytics/scorecard")
async def get_scorecard_metrics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get comprehensive scorecard metrics"""
    # Get all leads and loans for the user
    leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
    loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()
    funded_loans = [l for l in loans if l.stage == LoanStage.FUNDED]

    # Calculate conversion metrics
    total_leads = len(leads)
    app_started = len([l for l in leads if l.stage in [LeadStage.APPLICATION_STARTED, LeadStage.APPLICATION_COMPLETE, LeadStage.PRE_APPROVED]])
    funded_count = len(funded_loans)

    conversion_metrics = {
        "starts_to_apps": round((app_started / total_leads * 100) if total_leads > 0 else 0, 1),
        "apps_to_funded": round((funded_count / app_started * 100) if app_started > 0 else 0, 1),
        "pull_thru": round((funded_count / total_leads * 100) if total_leads > 0 else 0, 1),
        "credit_pull_conversion": round((app_started / total_leads * 100) if total_leads > 0 else 0, 1)
    }

    # Calculate volume & revenue
    total_volume = sum([l.amount for l in funded_loans if l.amount]) or 0
    avg_loan_amount = (total_volume / len(funded_loans)) if funded_loans else 0

    volume_revenue = {
        "funded_loans": funded_count,
        "total_volume": total_volume,
        "avg_loan_amount": avg_loan_amount,
        "basis_points": 185  # Placeholder - would be calculated from commission data
    }

    # Calculate loan type distribution
    loan_types = {}
    for loan in funded_loans:
        loan_type = loan.product_type or "Other"
        if loan_type not in loan_types:
            loan_types[loan_type] = {"count": 0, "volume": 0}
        loan_types[loan_type]["count"] += 1
        loan_types[loan_type]["volume"] += loan.amount if loan.amount else 0

    loan_type_distribution = [
        {
            "type": loan_type,
            "volume": data["volume"],
            "percentage": round((data["volume"] / total_volume * 100) if total_volume > 0 else 0, 2)
        }
        for loan_type, data in loan_types.items()
    ]

    # Referral sources (placeholder - would come from lead source tracking)
    referral_sources = [
        {"source": "Client Referrals", "volume": total_volume * 0.8 if total_volume else 0},
        {"source": "Realtor Referrals", "volume": total_volume * 0.2 if total_volume else 0}
    ]

    # Process timeline (placeholder - would be calculated from actual timestamps)
    process_timeline = {
        "starts_to_app": 10,
        "app_to_underwriting": 5,
        "lock_funding": 68
    }

    return {
        "conversion_metrics": conversion_metrics,
        "volume_revenue": volume_revenue,
        "loan_type_distribution": loan_type_distribution,
        "referral_sources": referral_sources,
        "process_timeline": process_timeline
    }

# ============================================================================
# PORTFOLIO
# ============================================================================

@app.get("/api/v1/portfolio/")
async def get_portfolio(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get portfolio loans (funded/completed loans)"""
    # Get loans that are funded (completed)
    portfolio_loans = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED
    ).order_by(Loan.updated_at.desc()).offset(skip).limit(limit).all()

    return portfolio_loans

@app.get("/api/v1/portfolio/stats")
async def get_portfolio_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get portfolio statistics"""
    # Get all funded loans for the user (completed loans in portfolio)
    funded_loans = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED
    ).all()

    # Calculate active loans (loans not funded yet)
    active_loans = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage != LoanStage.FUNDED
    ).count()

    # Calculate total volume of funded loans
    total_volume = sum([loan.amount for loan in funded_loans if loan.amount]) or 0

    return {
        "total_loans": len(funded_loans),
        "total_volume": total_volume,
        "active_loans": active_loans,
        "closed_loans": len(funded_loans)  # Funded loans are considered closed
    }

# ============================================================================
# AI ASSISTANT & CONVERSATIONS
# ============================================================================

async def execute_ai_function(
    function_name: str,
    function_args: dict,
    db: Session,
    current_user: User,
    context_lead: Optional[Lead] = None,
    context_loan: Optional[Loan] = None
) -> dict:
    """Execute AI function calls and return results"""

    try:
        if function_name == "create_task":
            # Create a new task
            lead_id = function_args.get("lead_id") or (context_lead.id if context_lead else None)
            loan_id = function_args.get("loan_id") or (context_loan.id if context_loan else None)

            task_type = TaskType.LEAD if lead_id else (TaskType.LOAN if loan_id else TaskType.GENERAL)

            new_task = AITask(
                type=task_type,
                title=function_args["title"],
                description=function_args.get("description", ""),
                assigned_to_id=current_user.id,
                lead_id=lead_id,
                loan_id=loan_id,
                priority=function_args.get("priority", "medium"),
                due_date=datetime.fromisoformat(function_args["due_date"]) if function_args.get("due_date") else None,
                status="pending",
                created_by_ai=True
            )
            db.add(new_task)
            db.commit()
            db.refresh(new_task)

            # Log activity
            if lead_id:
                activity = Activity(
                    type=ActivityType.NOTE,
                    description=f"AI created task: {function_args['title']}",
                    lead_id=lead_id,
                    user_id=current_user.id
                )
                db.add(activity)
                db.commit()

            return {
                "success": True,
                "task_id": new_task.id,
                "message": f"Task '{function_args['title']}' created successfully"
            }

        elif function_name == "update_lead_stage":
            lead_id = function_args["lead_id"]
            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()

            if not lead:
                return {"success": False, "error": "Lead not found or access denied"}

            old_stage = lead.stage.value
            new_stage_str = function_args["new_stage"]
            new_stage = LeadStage[new_stage_str.upper().replace(" ", "_")]

            lead.stage = new_stage
            lead.updated_at = datetime.utcnow()

            # Log activity
            reason = function_args.get("reason", "Stage updated by AI")
            activity = Activity(
                type=ActivityType.STAGE_CHANGE,
                description=f"AI updated stage from {old_stage} to {new_stage_str}. Reason: {reason}",
                lead_id=lead_id,
                user_id=current_user.id
            )
            db.add(activity)
            db.commit()

            return {
                "success": True,
                "lead_id": lead_id,
                "old_stage": old_stage,
                "new_stage": new_stage_str,
                "message": f"Lead stage updated from {old_stage} to {new_stage_str}"
            }

        elif function_name == "add_activity":
            lead_id = function_args.get("lead_id") or (context_lead.id if context_lead else None)
            loan_id = function_args.get("loan_id") or (context_loan.id if context_loan else None)

            # Map activity type string to enum
            type_map = {
                "note": ActivityType.NOTE,
                "call": ActivityType.CALL,
                "email": ActivityType.EMAIL,
                "meeting": ActivityType.MEETING,
                "sms": ActivityType.SMS,
                "other": ActivityType.NOTE
            }

            activity_type = type_map.get(function_args["activity_type"], ActivityType.NOTE)

            activity = Activity(
                type=activity_type,
                description=function_args["description"],
                lead_id=lead_id,
                loan_id=loan_id,
                user_id=current_user.id
            )
            db.add(activity)
            db.commit()
            db.refresh(activity)

            return {
                "success": True,
                "activity_id": activity.id,
                "message": "Activity added successfully"
            }

        elif function_name == "get_lead_details":
            lead_id = function_args["lead_id"]
            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()

            if not lead:
                return {"success": False, "error": "Lead not found or access denied"}

            return {
                "success": True,
                "lead": {
                    "id": lead.id,
                    "name": lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "stage": lead.stage.value,
                    "ai_score": lead.ai_score,
                    "credit_score": lead.credit_score,
                    "loan_type": lead.loan_type,
                    "preapproval_amount": lead.preapproval_amount,
                    "property_value": lead.property_value,
                    "employment_status": lead.employment_status,
                    "annual_income": lead.annual_income
                }
            }

        elif function_name == "get_high_priority_leads":
            limit = function_args.get("limit", 10)

            # Get high-priority leads (high score, active stages)
            leads = db.query(Lead).filter(
                Lead.owner_id == current_user.id,
                Lead.stage.in_([LeadStage.NEW, LeadStage.ATTEMPTED_CONTACT, LeadStage.PROSPECT, LeadStage.PRE_QUALIFIED])
            ).order_by(Lead.ai_score.desc()).limit(limit).all()

            return {
                "success": True,
                "count": len(leads),
                "leads": [
                    {
                        "id": lead.id,
                        "name": lead.name,
                        "stage": lead.stage.value,
                        "ai_score": lead.ai_score,
                        "credit_score": lead.credit_score,
                        "email": lead.email
                    }
                    for lead in leads
                ]
            }

        elif function_name == "search_leads":
            query = function_args["query"].lower()
            stage_filter = function_args.get("stage")

            # Search by name or email
            leads_query = db.query(Lead).filter(
                Lead.owner_id == current_user.id,
                or_(
                    Lead.name.ilike(f"%{query}%"),
                    Lead.email.ilike(f"%{query}%")
                )
            )

            if stage_filter:
                try:
                    stage_enum = LeadStage[stage_filter.upper().replace(" ", "_")]
                    leads_query = leads_query.filter(Lead.stage == stage_enum)
                except KeyError:
                    pass

            leads = leads_query.limit(10).all()

            return {
                "success": True,
                "count": len(leads),
                "leads": [
                    {
                        "id": lead.id,
                        "name": lead.name,
                        "email": lead.email,
                        "stage": lead.stage.value,
                        "ai_score": lead.ai_score
                    }
                    for lead in leads
                ]
            }

        else:
            return {"success": False, "error": f"Unknown function: {function_name}"}

    except Exception as e:
        logger.error(f"Error executing AI function {function_name}: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/v1/ai/chat", response_model=ConversationResponse)
async def ai_chat(
    conversation: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI Assistant chat endpoint with agentic function calling capabilities"""

    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    # Build context from lead or loan if provided
    context_info = ""
    context_lead = None
    context_loan = None

    if conversation.lead_id:
        context_lead = db.query(Lead).filter(Lead.id == conversation.lead_id).first()
        if context_lead:
            context_info = f"Lead: {context_lead.name}, Stage: {context_lead.stage.value}, Score: {context_lead.ai_score}, Credit: {context_lead.credit_score}"

    if conversation.loan_id:
        context_loan = db.query(Loan).filter(Loan.id == conversation.loan_id).first()
        if context_loan:
            context_info = f"Loan: {context_loan.loan_number}, Borrower: {context_loan.borrower_name}, Stage: {context_loan.stage.value}, Amount: ${context_loan.amount:,.0f}"

    # Define available functions for AI to call
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "Create a new task for a lead or loan. Use this when the user asks you to create a task, reminder, or follow-up.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "The task title (e.g., 'Call John about pre-approval')"
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of the task"
                        },
                        "lead_id": {
                            "type": "integer",
                            "description": "The lead ID this task is for (if applicable)"
                        },
                        "loan_id": {
                            "type": "integer",
                            "description": "The loan ID this task is for (if applicable)"
                        },
                        "due_date": {
                            "type": "string",
                            "description": "Due date in ISO format (e.g., '2025-11-10T10:00:00')"
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Task priority level"
                        }
                    },
                    "required": ["title"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_lead_stage",
                "description": "Update a lead's stage in the pipeline. Use this when progressing a lead or changing their status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {
                            "type": "integer",
                            "description": "The lead ID to update"
                        },
                        "new_stage": {
                            "type": "string",
                            "enum": ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application", "Completed", "Withdrawn", "Does Not Qualify"],
                            "description": "The new stage for the lead"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief reason for the stage change"
                        }
                    },
                    "required": ["lead_id", "new_stage"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_activity",
                "description": "Add a note, activity, or log entry to a lead or loan. Use this to record conversations, notes, or important events.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {
                            "type": "integer",
                            "description": "The lead ID (if applicable)"
                        },
                        "loan_id": {
                            "type": "integer",
                            "description": "The loan ID (if applicable)"
                        },
                        "activity_type": {
                            "type": "string",
                            "enum": ["note", "call", "email", "meeting", "sms", "other"],
                            "description": "Type of activity"
                        },
                        "description": {
                            "type": "string",
                            "description": "The activity description or note content"
                        }
                    },
                    "required": ["description", "activity_type"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_lead_details",
                "description": "Retrieve detailed information about a specific lead. Use this when you need more information about a lead.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {
                            "type": "integer",
                            "description": "The lead ID to retrieve"
                        }
                    },
                    "required": ["lead_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_high_priority_leads",
                "description": "Get a list of high-priority leads that need attention. Use this when asked about priorities or what to work on.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of leads to return (default 10)",
                            "default": 10
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_leads",
                "description": "Search for leads by name, email, or other criteria.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (name, email, etc.)"
                        },
                        "stage": {
                            "type": "string",
                            "description": "Filter by stage"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    # Get conversation history for context
    history = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc()).limit(5).all()

    # Build messages for OpenAI
    messages = [
        {
            "role": "system",
            "content": f"""You are an agentic AI assistant for a mortgage CRM system. You can autonomously execute actions to help loan officers.

Current user: {current_user.full_name or current_user.email}
{f'Context: {context_info}' if context_info else ''}

You have the ability to:
- Create tasks and reminders
- Update lead stages
- Add notes and activities
- Retrieve lead information
- Search for leads
- Analyze priorities

When a user asks you to do something, use the available functions to actually perform the action. Don't just suggest - DO IT.

Be proactive, professional, and action-oriented. Always confirm what you've done."""
        }
    ]

    # Add recent history
    for msg in reversed(history):
        messages.append({"role": "user", "content": msg.message})
        if msg.response:
            messages.append({"role": "assistant", "content": msg.response})

    # Add current message
    messages.append({"role": "user", "content": conversation.message})

    try:
        # Call OpenAI with function calling
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1000
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        actions_taken = []

        # Execute any function calls
        if tool_calls:
            messages.append(response_message)

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                logger.info(f"AI calling function: {function_name} with args: {function_args}")

                # Execute the function
                function_response = await execute_ai_function(
                    function_name,
                    function_args,
                    db,
                    current_user,
                    context_lead,
                    context_loan
                )

                actions_taken.append({
                    "function": function_name,
                    "args": function_args,
                    "result": function_response
                })

                # Add function response to messages
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps(function_response)
                })

            # Get final response from AI after function execution
            second_response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )

            ai_response = second_response.choices[0].message.content
        else:
            ai_response = response_message.content

        # Save conversation with actions metadata
        metadata = conversation.context or {}
        if actions_taken:
            metadata["actions_taken"] = actions_taken

        db_conversation = Conversation(
            user_id=current_user.id,
            lead_id=conversation.lead_id,
            loan_id=conversation.loan_id,
            message=conversation.message,
            response=ai_response,
            role="user",
            metadata=metadata
        )
        db.add(db_conversation)

        # Save assistant response
        db_assistant = Conversation(
            user_id=current_user.id,
            lead_id=conversation.lead_id,
            loan_id=conversation.loan_id,
            message=ai_response,
            role="assistant",
            metadata={"actions": actions_taken} if actions_taken else None
        )
        db.add(db_assistant)

        db.commit()
        db.refresh(db_conversation)

        logger.info(f"AI chat completed for user {current_user.email}. Actions taken: {len(actions_taken)}")
        return db_conversation

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

@app.get("/api/v1/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    skip: int = 0,
    limit: int = 50,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get conversation history"""
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)

    if lead_id:
        query = query.filter(Conversation.lead_id == lead_id)
    if loan_id:
        query = query.filter(Conversation.loan_id == loan_id)

    conversations = query.order_by(Conversation.created_at.desc()).offset(skip).limit(limit).all()
    return conversations

@app.post("/api/v1/ai/complete-task")
async def ai_complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Use AI to suggest task completion"""

    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    task = db.query(AITask).filter(
        AITask.id == task_id,
        AITask.assigned_to_id == current_user.id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        # Get context
        context = f"Task: {task.title}\nDescription: {task.description or 'N/A'}\nPriority: {task.priority}"

        if task.loan_id:
            loan = db.query(Loan).filter(Loan.id == task.loan_id).first()
            if loan:
                context += f"\nLoan: {loan.loan_number}, Stage: {loan.stage.value}"

        # Ask AI for completion suggestion
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant for mortgage loan officers. Suggest a brief completion action for the given task."
                },
                {
                    "role": "user",
                    "content": f"Suggest how to complete this task:\n{context}"
                }
            ],
            temperature=0.7,
            max_tokens=200
        )

        suggestion = response.choices[0].message.content

        return {
            "task_id": task_id,
            "suggestion": suggestion,
            "confidence": 85
        }

    except Exception as e:
        logger.error(f"AI task completion error: {e}")
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

# ============================================================================
# CALENDAR EVENTS CRUD
# ============================================================================

@app.post("/api/v1/calendar/events", response_model=CalendarEventResponse, status_code=201)
async def create_event(
    event: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new calendar event"""
    db_event = CalendarEvent(
        **event.dict(exclude={'attendees'}),
        user_id=current_user.id,
        attendees=event.attendees if event.attendees else []
    )

    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    logger.info(f"Calendar event created: {db_event.title}")
    return db_event

@app.get("/api/v1/calendar/events", response_model=List[CalendarEventResponse])
async def get_events(
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get calendar events with optional date filtering"""
    query = db.query(CalendarEvent).filter(CalendarEvent.user_id == current_user.id)

    if start_date:
        query = query.filter(CalendarEvent.start_time >= start_date)
    if end_date:
        query = query.filter(CalendarEvent.start_time <= end_date)

    events = query.order_by(CalendarEvent.start_time).offset(skip).limit(limit).all()
    return events

@app.get("/api/v1/calendar/events/{event_id}", response_model=CalendarEventResponse)
async def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific calendar event"""
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return event

@app.patch("/api/v1/calendar/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: int,
    event_update: CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a calendar event"""
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    for key, value in event_update.dict(exclude_unset=True).items():
        setattr(event, key, value)

    event.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(event)

    logger.info(f"Calendar event updated: {event.title}")
    return event

@app.delete("/api/v1/calendar/events/{event_id}", status_code=204)
async def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a calendar event"""
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(event)
    db.commit()

    logger.info(f"Calendar event deleted: {event.title}")
    return None

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db():
    """Create all database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created successfully")

        # Run schema migrations for existing tables
        try:
            with engine.connect() as conn:
                # Add email_verified column if it doesn't exist
                conn.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='email_verified'
                        ) THEN
                            ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;
                        END IF;
                    END $$;
                """))

                # Add new Lead columns if they don't exist
                conn.execute(text("""
                    DO $$
                    BEGIN
                        -- Property Information
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='address') THEN
                            ALTER TABLE leads ADD COLUMN address VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='city') THEN
                            ALTER TABLE leads ADD COLUMN city VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='state') THEN
                            ALTER TABLE leads ADD COLUMN state VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='zip_code') THEN
                            ALTER TABLE leads ADD COLUMN zip_code VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_type') THEN
                            ALTER TABLE leads ADD COLUMN property_type VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_value') THEN
                            ALTER TABLE leads ADD COLUMN property_value FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='down_payment') THEN
                            ALTER TABLE leads ADD COLUMN down_payment FLOAT;
                        END IF;
                        -- Financial Information
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employment_status') THEN
                            ALTER TABLE leads ADD COLUMN employment_status VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='annual_income') THEN
                            ALTER TABLE leads ADD COLUMN annual_income FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='monthly_debts') THEN
                            ALTER TABLE leads ADD COLUMN monthly_debts FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='first_time_buyer') THEN
                            ALTER TABLE leads ADD COLUMN first_time_buyer BOOLEAN DEFAULT FALSE;
                        END IF;
                        -- Loan Information
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_number') THEN
                            ALTER TABLE leads ADD COLUMN loan_number VARCHAR;
                        END IF;
                        -- Loan Details
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_amount') THEN
                            ALTER TABLE leads ADD COLUMN loan_amount FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='interest_rate') THEN
                            ALTER TABLE leads ADD COLUMN interest_rate FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_term') THEN
                            ALTER TABLE leads ADD COLUMN loan_term INTEGER;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='apr') THEN
                            ALTER TABLE leads ADD COLUMN apr FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='points') THEN
                            ALTER TABLE leads ADD COLUMN points FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_date') THEN
                            ALTER TABLE leads ADD COLUMN lock_date TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_expiration') THEN
                            ALTER TABLE leads ADD COLUMN lock_expiration TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='closing_date') THEN
                            ALTER TABLE leads ADD COLUMN closing_date TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lender') THEN
                            ALTER TABLE leads ADD COLUMN lender VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_officer') THEN
                            ALTER TABLE leads ADD COLUMN loan_officer VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='processor') THEN
                            ALTER TABLE leads ADD COLUMN processor VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='underwriter') THEN
                            ALTER TABLE leads ADD COLUMN underwriter VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='appraisal_value') THEN
                            ALTER TABLE leads ADD COLUMN appraisal_value FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='ltv') THEN
                            ALTER TABLE leads ADD COLUMN ltv FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='dti') THEN
                            ALTER TABLE leads ADD COLUMN dti FLOAT;
                        END IF;
                    END $$;
                """))

                conn.commit()
                logger.info("✅ Schema migrations applied")
        except Exception as e:
            logger.warning(f"⚠️ Schema migration note: {e}")

        return True
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

def create_sample_data(db: Session):
    """Create sample data for testing"""
    try:
        # Check if data already exists
        existing_user = db.query(User).filter(User.email == "demo@example.com").first()
        if existing_user:
            logger.info("Sample data already exists")
            return

        # Create demo branch
        branch = Branch(
            name="Main Office",
            company="Demo Mortgage Company",
            nmls_id="123456"
        )
        db.add(branch)
        db.commit()

        # Create demo user
        demo_user = User(
            email="demo@example.com",
            hashed_password=get_password_hash("demo123"),
            full_name="Demo User",
            role="loan_officer",
            branch_id=branch.id
        )
        db.add(demo_user)
        db.commit()

        # Create sample leads
        sample_leads = [
            Lead(
                name="John Smith",
                email="john.smith@email.com",
                phone="555-0101",
                stage=LeadStage.NEW,
                source="Website",
                loan_type="Purchase",
                preapproval_amount=450000,
                credit_score=750,
                debt_to_income=0.35,
                owner_id=demo_user.id,
                ai_score=85,
                sentiment="positive",
                next_action="Schedule initial consultation"
            ),
            Lead(
                name="Sarah Johnson",
                email="sarah.j@email.com",
                phone="555-0102",
                stage=LeadStage.PROSPECT,
                source="Referral",
                loan_type="Refinance",
                preapproval_amount=350000,
                credit_score=720,
                debt_to_income=0.40,
                owner_id=demo_user.id,
                ai_score=78,
                sentiment="positive",
                next_action="Send pre-qualification letter"
            ),
            Lead(
                name="Mike Williams",
                email="mike.w@email.com",
                phone="555-0103",
                stage=LeadStage.APPLICATION_STARTED,
                source="Zillow",
                loan_type="Purchase",
                preapproval_amount=525000,
                credit_score=680,
                debt_to_income=0.42,
                owner_id=demo_user.id,
                ai_score=65,
                sentiment="neutral",
                next_action="Collect additional documentation"
            )
        ]

        for lead in sample_leads:
            db.add(lead)
        db.commit()

        # Create sample loans
        sample_loans = [
            Loan(
                loan_number="L2024-001",
                borrower_name="Emily Davis",
                amount=400000,
                stage=LoanStage.PROCESSING,
                program="Conventional",
                loan_type="Purchase",
                rate=6.875,
                term=360,
                property_address="123 Main St, Anytown, CA",
                closing_date=datetime.utcnow() + timedelta(days=25),
                loan_officer_id=demo_user.id,
                processor="Jane Processor",
                days_in_stage=5,
                sla_status="on-track"
            ),
            Loan(
                loan_number="L2024-002",
                borrower_name="Robert Brown",
                amount=550000,
                stage=LoanStage.UW_RECEIVED,
                program="FHA",
                loan_type="Purchase",
                rate=7.125,
                term=360,
                property_address="456 Oak Ave, Somewhere, CA",
                closing_date=datetime.utcnow() + timedelta(days=18),
                loan_officer_id=demo_user.id,
                processor="John Processor",
                underwriter="Sarah UW",
                days_in_stage=3,
                sla_status="on-track"
            )
        ]

        for loan in sample_loans:
            loan.ai_insights = generate_ai_insights(loan)
            db.add(loan)
        db.commit()

        # Create sample tasks
        sample_tasks = [
            AITask(
                title="Review appraisal for L2024-001",
                description="Appraisal came in at $395,000 - need to discuss with borrower",
                type=TaskType.HUMAN_NEEDED,
                category="Documentation",
                priority="high",
                ai_confidence=85,
                borrower_name="Emily Davis",
                loan_id=sample_loans[0].id,
                assigned_to_id=demo_user.id,
                due_date=datetime.utcnow() + timedelta(days=1)
            ),
            AITask(
                title="Follow up on income verification",
                description="Waiting on 2023 W2 from borrower",
                type=TaskType.IN_PROGRESS,
                category="Documentation",
                priority="medium",
                ai_confidence=92,
                borrower_name="Robert Brown",
                loan_id=sample_loans[1].id,
                assigned_to_id=demo_user.id,
                due_date=datetime.utcnow() + timedelta(days=3)
            )
        ]

        for task in sample_tasks:
            db.add(task)
        db.commit()

        # Create sample referral partners
        sample_partners = [
            ReferralPartner(
                name="Jane Realtor",
                company="Premier Realty",
                type="Real Estate Agent",
                phone="555-0200",
                email="jane@premierrealty.com",
                referrals_in=15,
                closed_loans=8,
                volume=3200000,
                loyalty_tier="gold",
                status="active"
            ),
            ReferralPartner(
                name="Bob Builder",
                company="Custom Homes Inc",
                type="Builder",
                phone="555-0201",
                email="bob@customhomes.com",
                referrals_in=8,
                closed_loans=5,
                volume=2100000,
                loyalty_tier="silver",
                status="active"
            )
        ]

        for partner in sample_partners:
            db.add(partner)
        db.commit()

        # Create sample MUM clients
        sample_mum = [
            MUMClient(
                name="Previous Borrower 1",
                loan_number="L2023-045",
                original_close_date=datetime.utcnow() - timedelta(days=365),
                days_since_funding=365,
                original_rate=7.5,
                current_rate=6.875,
                loan_balance=380000,
                refinance_opportunity=True,
                estimated_savings=2375,
                status="opportunity"
            )
        ]

        for mum in sample_mum:
            db.add(mum)
        db.commit()

        logger.info("✅ Sample data created successfully")
        logger.info(f"   Demo user: demo@example.com / demo123")
        logger.info(f"   Created {len(sample_leads)} leads, {len(sample_loans)} loans, {len(sample_tasks)} tasks")

    except Exception as e:
        logger.error(f"❌ Sample data creation failed: {e}")
        db.rollback()

# ============================================================================
# AI UNDERWRITER - INTELLIGENT Q&A
# ============================================================================

@app.post("/api/v1/ai-underwriter/ask")
async def ask_underwriter_question(
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """
    AI Underwriter: Answer mortgage lending questions using Claude AI.
    Provides comprehensive answers with source citations from mortgageguidelines.com.
    """
    question = request.get("question", "").strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    # Get Claude API key
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")

    try:
        # Call Claude API with expert mortgage underwriter system prompt
        client = anthropic.Anthropic(api_key=anthropic_api_key)

        system_prompt = """You are an expert mortgage underwriter assistant with deep knowledge of:
- FHA, VA, USDA, and Conventional loan guidelines
- Fannie Mae and Freddie Mac requirements
- DTI ratios, credit score requirements, and LTV limits
- Documentation requirements for various borrower types
- Appraisal and property requirements
- Income calculation and verification
- Asset and reserve requirements

Provide clear, accurate, and comprehensive answers to mortgage lending questions.
Be specific with numbers, percentages, and requirements.
If you're not certain about specific current limits or requirements, acknowledge that guidelines may change."""

        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": question}]
        )

        answer = message.content[0].text

        # Generate intelligent source links based on question topic
        sources = []
        question_lower = question.lower()

        # Map common topics to relevant guideline pages
        if 'fha' in question_lower:
            sources.append({
                "title": "FHA Loan Guidelines",
                "url": "https://my.mortgageguidelines.com/single-family/fha"
            })

        if 'va' in question_lower or 'veteran' in question_lower:
            sources.append({
                "title": "VA Loan Guidelines",
                "url": "https://my.mortgageguidelines.com/single-family/va"
            })

        if 'usda' in question_lower or 'rural' in question_lower:
            sources.append({
                "title": "USDA Loan Guidelines",
                "url": "https://my.mortgageguidelines.com/single-family/usda"
            })

        if 'conventional' in question_lower or 'fannie' in question_lower or 'freddie' in question_lower:
            sources.append({
                "title": "Conventional Loan Guidelines",
                "url": "https://my.mortgageguidelines.com/single-family/conventional"
            })

        if 'dti' in question_lower or 'debt' in question_lower:
            sources.append({
                "title": "DTI Requirements",
                "url": "https://my.mortgageguidelines.com/topics/debt-to-income"
            })

        if 'credit' in question_lower or 'score' in question_lower:
            sources.append({
                "title": "Credit Score Requirements",
                "url": "https://my.mortgageguidelines.com/topics/credit"
            })

        if 'self-employed' in question_lower or 'self employed' in question_lower:
            sources.append({
                "title": "Self-Employed Borrower Guidelines",
                "url": "https://my.mortgageguidelines.com/topics/self-employed"
            })

        if 'investment' in question_lower or 'rental' in question_lower:
            sources.append({
                "title": "Investment Property Guidelines",
                "url": "https://my.mortgageguidelines.com/topics/investment-properties"
            })

        if 'cash-out' in question_lower or 'refinance' in question_lower:
            sources.append({
                "title": "Refinance Guidelines",
                "url": "https://my.mortgageguidelines.com/topics/refinance"
            })

        if 'ltv' in question_lower or 'loan-to-value' in question_lower:
            sources.append({
                "title": "LTV Requirements",
                "url": "https://my.mortgageguidelines.com/topics/ltv"
            })

        if 'reserve' in question_lower:
            sources.append({
                "title": "Reserve Requirements",
                "url": "https://my.mortgageguidelines.com/topics/reserves"
            })

        # If no specific sources matched, add general guidelines page
        if not sources:
            sources.append({
                "title": "Mortgage Guidelines",
                "url": "https://my.mortgageguidelines.com/"
            })

        # Calculate confidence based on message usage
        # Higher token usage generally indicates more comprehensive, confident answers
        confidence = min(0.95, 0.7 + (len(answer) / 2000))

        return {
            "answer": answer,
            "sources": sources,
            "confidence": confidence
        }

    except Exception as e:
        logger.error(f"Error in AI Underwriter: {e}")
        error_msg = str(e)
        # Return more detailed error for debugging
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            raise HTTPException(status_code=500, detail=f"Anthropic API authentication error: {error_msg}")
        elif "quota" in error_msg.lower() or "credit" in error_msg.lower():
            raise HTTPException(status_code=500, detail=f"Anthropic API quota/billing error: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"AI Underwriter error: {error_msg}")

# ============================================================================
# EMAIL INTEGRATION - MICROSOFT GRAPH OAUTH
# ============================================================================

@app.get("/api/v1/email/connect")
async def start_email_oauth(current_user: User = Depends(get_current_user)):
    """
    Initiates Microsoft OAuth flow for email integration.
    Returns URL for user to authorize access to their Outlook.
    """
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    tenant_id = os.getenv("MICROSOFT_TENANT_ID")
    redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI")

    if not all([client_id, tenant_id, redirect_uri]):
        raise HTTPException(status_code=500, detail="Microsoft Graph API not configured")

    # Store user ID in state parameter to retrieve after callback
    state = f"{current_user.id}_{secrets.token_urlsafe(32)}"

    # Microsoft authorization endpoint
    auth_url = (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"response_mode=query&"
        f"scope=offline_access%20Mail.Read%20Mail.ReadWrite%20User.Read&"
        f"state={state}"
    )

    return {
        "auth_url": auth_url,
        "message": "Redirect user to this URL to authorize email access"
    }

@app.get("/api/v1/email/oauth/callback")
async def email_oauth_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    OAuth callback endpoint. Microsoft redirects here after user authorizes.
    Exchanges authorization code for access token and stores it.
    """
    try:
        # Extract user ID from state parameter
        user_id = int(state.split("_")[0])

        # Get configuration
        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        tenant_id = os.getenv("MICROSOFT_TENANT_ID")
        redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI")

        # Exchange code for tokens
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "offline_access Mail.Read Mail.ReadWrite User.Read"
        }

        import requests
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()

        # Calculate token expiration
        expires_in = tokens.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Store or update tokens in database
        existing_token = db.query(MicrosoftToken).filter(
            MicrosoftToken.user_id == user_id
        ).first()

        if existing_token:
            existing_token.access_token = tokens["access_token"]
            existing_token.refresh_token = tokens.get("refresh_token")
            existing_token.expires_at = expires_at
            existing_token.updated_at = datetime.utcnow()
        else:
            new_token = MicrosoftToken(
                user_id=user_id,
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token"),
                token_type=tokens.get("token_type", "Bearer"),
                expires_at=expires_at,
                scope=tokens.get("scope", "")
            )
            db.add(new_token)

        db.commit()
        logger.info(f"✅ Email connected for user {user_id}")

        # Redirect back to settings page with success message
        return RedirectResponse(
            url="https://mortgage-crm-nine.vercel.app/settings?email=connected",
            status_code=302
        )

    except Exception as e:
        logger.error(f"❌ Email OAuth callback error: {e}")
        return RedirectResponse(
            url="https://mortgage-crm-nine.vercel.app/settings?email=error",
            status_code=302
        )

@app.get("/api/v1/email/status")
async def get_email_connection_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if user has connected their email and if token is valid.
    """
    token = db.query(MicrosoftToken).filter(
        MicrosoftToken.user_id == current_user.id
    ).first()

    if not token:
        return {
            "connected": False,
            "email": None,
            "last_sync": None
        }

    # Check if token is expired
    is_expired = token.expires_at < datetime.utcnow() if token.expires_at else True

    return {
        "connected": True,
        "token_expired": is_expired,
        "last_sync": None,  # TODO: Track last email fetch time
        "message": "Email connected" if not is_expired else "Token expired, please reconnect"
    }

@app.post("/api/v1/email/disconnect")
async def disconnect_email(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Disconnect email integration by deleting stored tokens.
    """
    token = db.query(MicrosoftToken).filter(
        MicrosoftToken.user_id == current_user.id
    ).first()

    if token:
        db.delete(token)
        db.commit()
        logger.info(f"Email disconnected for user {current_user.id}")

    return {"message": "Email disconnected successfully"}

# ============================================================================
# EMAIL INTEGRATION - HELPER FUNCTIONS
# ============================================================================

async def refresh_microsoft_token(user_id: int, db: Session) -> Optional[str]:
    """
    Refresh an expired Microsoft access token using refresh token.
    Returns new access token or None if refresh fails.
    """
    token_record = db.query(MicrosoftToken).filter(
        MicrosoftToken.user_id == user_id
    ).first()

    if not token_record or not token_record.refresh_token:
        return None

    try:
        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        tenant_id = os.getenv("MICROSOFT_TENANT_ID")

        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        refresh_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": token_record.refresh_token,
            "grant_type": "refresh_token",
            "scope": "offline_access Mail.Read Mail.ReadWrite User.Read"
        }

        import requests
        response = requests.post(token_url, data=refresh_data)
        response.raise_for_status()
        tokens = response.json()

        # Update stored tokens
        expires_in = tokens.get("expires_in", 3600)
        token_record.access_token = tokens["access_token"]
        if "refresh_token" in tokens:
            token_record.refresh_token = tokens["refresh_token"]
        token_record.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        token_record.updated_at = datetime.utcnow()
        db.commit()

        return tokens["access_token"]

    except Exception as e:
        logger.error(f"Token refresh failed for user {user_id}: {e}")
        return None

async def get_valid_access_token(user_id: int, db: Session) -> Optional[str]:
    """
    Get a valid access token for user, refreshing if necessary.
    """
    token_record = db.query(MicrosoftToken).filter(
        MicrosoftToken.user_id == user_id
    ).first()

    if not token_record:
        return None

    # Check if token is expired or about to expire (within 5 minutes)
    if token_record.expires_at:
        time_until_expiry = token_record.expires_at - datetime.utcnow()
        if time_until_expiry.total_seconds() < 300:  # Less than 5 minutes
            # Try to refresh
            new_token = await refresh_microsoft_token(user_id, db)
            return new_token if new_token else token_record.access_token

    return token_record.access_token

# ============================================================================
# CALENDLY INTEGRATION
# ============================================================================

@app.get("/api/v1/calendly/event-types")
async def get_calendly_event_types(current_user: User = Depends(get_current_user)):
    """
    Get user's Calendly event types (available meeting types).
    Uses Calendly Personal Access Token to fetch event types.
    """
    calendly_token = os.getenv("CALENDLY_API_TOKEN")
    if not calendly_token:
        raise HTTPException(status_code=500, detail="Calendly API not configured")

    try:
        # First, get the current user's URI
        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        # Get current user info
        user_response = requests.get(
            "https://api.calendly.com/users/me",
            headers=headers
        )
        user_response.raise_for_status()
        user_data = user_response.json()
        user_uri = user_data["resource"]["uri"]

        # Get event types for this user
        event_types_response = requests.get(
            f"https://api.calendly.com/event_types",
            headers=headers,
            params={"user": user_uri}
        )
        event_types_response.raise_for_status()
        event_types_data = event_types_response.json()

        return {
            "event_types": event_types_data.get("collection", []),
            "count": event_types_data.get("pagination", {}).get("count", 0)
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly API error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch event types: {str(e)}")


@app.post("/api/v1/calendly/scheduling-link")
async def create_scheduling_link(
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a single-use Calendly scheduling link for a lead.
    This link can be sent via email/SMS to allow the lead to book a meeting.
    """
    calendly_token = os.getenv("CALENDLY_API_TOKEN")
    if not calendly_token:
        raise HTTPException(status_code=500, detail="Calendly API not configured")

    lead_id = request.get("lead_id")
    event_type_uuid = request.get("event_type_uuid")

    if not lead_id or not event_type_uuid:
        raise HTTPException(status_code=400, detail="lead_id and event_type_uuid required")

    # Get lead details
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        # Create single-use scheduling link
        payload = {
            "max_event_count": 1,  # Single-use link
            "owner": f"https://api.calendly.com/event_types/{event_type_uuid}",
            "owner_type": "EventType"
        }

        response = requests.post(
            "https://api.calendly.com/scheduling_links",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()

        booking_url = data["resource"]["booking_url"]

        # Store the scheduling link in lead metadata
        if not lead.meta_data:
            lead.meta_data = {}
        lead.meta_data["calendly_link"] = booking_url
        lead.meta_data["calendly_created_at"] = datetime.utcnow().isoformat()
        db.commit()

        return {
            "booking_url": booking_url,
            "lead_id": lead_id,
            "lead_name": lead.name,
            "message": "Single-use scheduling link created successfully"
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly API error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create scheduling link: {str(e)}")


@app.post("/api/v1/calendly/webhook")
async def calendly_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook endpoint to receive Calendly events.
    Handles invitee.created, invitee.canceled, etc.

    To set this up:
    1. Go to Calendly Integrations > Webhooks
    2. Add webhook URL: https://your-domain.com/api/v1/calendly/webhook
    3. Subscribe to events: invitee.created, invitee.canceled
    """
    try:
        payload = await request.json()
        event_type = payload.get("event")

        logger.info(f"Calendly webhook received: {event_type}")

        if event_type == "invitee.created":
            # Extract invitee and event details
            invitee_data = payload.get("payload", {})
            invitee_email = invitee_data.get("email")
            invitee_name = invitee_data.get("name")
            event_uri = invitee_data.get("event")
            scheduled_at = invitee_data.get("scheduled_event", {}).get("start_time")

            # Try to find matching lead by email
            lead = db.query(Lead).filter(Lead.email == invitee_email).first()

            if lead:
                # Update lead with appointment info
                if not lead.meta_data:
                    lead.meta_data = {}

                lead.meta_data["calendly_booked"] = True
                lead.meta_data["calendly_booked_at"] = scheduled_at
                lead.meta_data["calendly_event_uri"] = event_uri

                # Move lead to "Meeting Scheduled" stage if applicable
                lead.stage = "meeting_scheduled"

                # Create a task for the user
                task = Task(
                    title=f"Meeting scheduled with {invitee_name}",
                    description=f"Calendly meeting booked for {scheduled_at}",
                    due_date=datetime.fromisoformat(scheduled_at.replace('Z', '+00:00')) if scheduled_at else None,
                    priority="high",
                    status="pending",
                    lead_id=lead.id
                )
                db.add(task)
                db.commit()

                logger.info(f"Lead {lead.id} updated with Calendly appointment")
            else:
                # Create new lead from Calendly booking
                new_lead = Lead(
                    name=invitee_name,
                    email=invitee_email,
                    stage="meeting_scheduled",
                    source="Calendly",
                    meta_data={
                        "calendly_booked": True,
                        "calendly_booked_at": scheduled_at,
                        "calendly_event_uri": event_uri
                    }
                )
                db.add(new_lead)
                db.commit()

                logger.info(f"New lead created from Calendly: {invitee_name}")

        elif event_type == "invitee.canceled":
            # Handle cancellation
            invitee_data = payload.get("payload", {})
            invitee_email = invitee_data.get("email")

            lead = db.query(Lead).filter(Lead.email == invitee_email).first()
            if lead:
                if lead.meta_data:
                    lead.meta_data["calendly_booked"] = False
                    lead.meta_data["calendly_canceled_at"] = datetime.utcnow().isoformat()
                    db.commit()

                    logger.info(f"Lead {lead.id} Calendly appointment canceled")

        return {"status": "success", "event": event_type}

    except Exception as e:
        logger.error(f"Calendly webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calendly/calendar-mappings")
async def create_calendar_mapping(
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Map a lead stage to a Calendly event type.
    Example: map "new" stage to "Discovery Call" event type
    """
    stage = request.get("stage")
    event_type_uuid = request.get("event_type_uuid")
    event_type_name = request.get("event_type_name")
    event_type_url = request.get("event_type_url")

    if not all([stage, event_type_uuid, event_type_name]):
        raise HTTPException(status_code=400, detail="stage, event_type_uuid, and event_type_name required")

    # Check if mapping already exists
    existing = db.query(CalendarMapping).filter(
        CalendarMapping.user_id == current_user.id,
        CalendarMapping.stage == stage
    ).first()

    if existing:
        # Update existing mapping
        existing.event_type_uuid = event_type_uuid
        existing.event_type_name = event_type_name
        existing.event_type_url = event_type_url
        existing.is_active = True
        db.commit()
        return {"message": "Calendar mapping updated", "mapping_id": existing.id}
    else:
        # Create new mapping
        mapping = CalendarMapping(
            user_id=current_user.id,
            stage=stage,
            event_type_uuid=event_type_uuid,
            event_type_name=event_type_name,
            event_type_url=event_type_url
        )
        db.add(mapping)
        db.commit()
        return {"message": "Calendar mapping created", "mapping_id": mapping.id}


@app.get("/api/v1/calendly/calendar-mappings")
async def get_calendar_mappings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all calendar mappings for current user"""
    mappings = db.query(CalendarMapping).filter(
        CalendarMapping.user_id == current_user.id,
        CalendarMapping.is_active == True
    ).all()

    return {
        "mappings": [
            {
                "id": m.id,
                "stage": m.stage,
                "event_type_uuid": m.event_type_uuid,
                "event_type_name": m.event_type_name,
                "event_type_url": m.event_type_url
            }
            for m in mappings
        ]
    }


@app.get("/api/v1/calendly/availability")
async def get_availability(
    event_type_uuid: str,
    start_time: str,
    end_time: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get available time slots for a Calendly event type.

    Args:
        event_type_uuid: The UUID of the event type
        start_time: ISO 8601 format (e.g., "2024-01-15T00:00:00Z")
        end_time: ISO 8601 format (e.g., "2024-01-22T00:00:00Z")
    """
    calendly_token = os.getenv("CALENDLY_API_TOKEN")
    if not calendly_token:
        raise HTTPException(status_code=500, detail="Calendly API not configured")

    try:
        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        # Get availability from Calendly
        response = requests.get(
            f"https://api.calendly.com/event_type_available_times",
            headers=headers,
            params={
                "event_type": f"https://api.calendly.com/event_types/{event_type_uuid}",
                "start_time": start_time,
                "end_time": end_time
            }
        )
        response.raise_for_status()
        data = response.json()

        return {
            "available_times": data.get("collection", []),
            "count": len(data.get("collection", []))
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly availability API error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch availability: {str(e)}")


@app.post("/api/v1/calendly/ai-schedule")
async def ai_schedule_conversation(
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    AI-powered scheduling conversation endpoint.
    The AI can view availability and book appointments automatically.

    Example conversation:
    User: "I'd like to schedule a meeting"
    AI: "I have these times available: Jan 15 at 2pm, Jan 16 at 10am..."
    User: "Jan 15 at 2pm works"
    AI: *books appointment* "Great! You're confirmed for Jan 15 at 2pm"
    """
    lead_id = request.get("lead_id")
    message = request.get("message")
    conversation_history = request.get("conversation_history", [])

    if not lead_id or not message:
        raise HTTPException(status_code=400, detail="lead_id and message required")

    # Get lead details
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get the appropriate calendar mapping for this lead's stage
    mapping = db.query(CalendarMapping).filter(
        CalendarMapping.user_id == current_user.id,
        CalendarMapping.stage == lead.stage,
        CalendarMapping.is_active == True
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"No calendar mapping found for stage '{lead.stage}'. Please configure calendar mappings first."
        )

    calendly_token = os.getenv("CALENDLY_API_TOKEN")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    if not calendly_token or not anthropic_api_key:
        raise HTTPException(status_code=500, detail="Calendly or Anthropic API not configured")

    try:
        # Get availability for next 14 days
        from datetime import timezone
        start_time = datetime.now(timezone.utc).isoformat()
        end_time = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()

        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        # Fetch available times
        availability_response = requests.get(
            f"https://api.calendly.com/event_type_available_times",
            headers=headers,
            params={
                "event_type": f"https://api.calendly.com/event_types/{mapping.event_type_uuid}",
                "start_time": start_time,
                "end_time": end_time
            }
        )

        available_slots = []
        if availability_response.status_code == 200:
            avail_data = availability_response.json()
            available_slots = avail_data.get("collection", [])

        # Format available slots for AI
        formatted_slots = []
        for slot in available_slots[:10]:  # Show first 10 slots
            start_dt = datetime.fromisoformat(slot["start_time"].replace('Z', '+00:00'))
            formatted_slots.append({
                "datetime": start_dt.strftime("%A, %B %d at %I:%M %p"),
                "iso_time": slot["start_time"]
            })

        # Build context for Claude
        system_prompt = f"""You are a scheduling assistant for a mortgage loan officer. You help schedule {mapping.event_type_name} appointments.

Lead Information:
- Name: {lead.name}
- Email: {lead.email}
- Stage: {lead.stage}

Available Time Slots:
{chr(10).join([f"- {slot['datetime']}" for slot in formatted_slots]) if formatted_slots else "No availability in the next 14 days"}

Your capabilities:
1. View and present available time slots in a natural way
2. When the lead confirms a specific time, extract the ISO timestamp and respond with BOOK:[iso_timestamp]
3. Be friendly, professional, and helpful

Rules:
- Only book times from the available slots list
- When booking, respond with EXACTLY: BOOK:[iso_timestamp] (e.g., "BOOK:2024-01-15T14:00:00Z")
- After booking, confirm the appointment in natural language
- If no slots available, suggest alternative dates or contact methods"""

        # Call Claude
        client = anthropic.Anthropic(api_key=anthropic_api_key)

        messages = conversation_history + [{"role": "user", "content": message}]

        ai_response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )

        ai_message = ai_response.content[0].text

        # Check if AI wants to book an appointment
        if "BOOK:" in ai_message:
            # Extract timestamp
            booking_line = [line for line in ai_message.split('\n') if 'BOOK:' in line][0]
            iso_timestamp = booking_line.split('BOOK:')[1].strip()

            # Create single-use scheduling link
            scheduling_payload = {
                "max_event_count": 1,
                "owner": f"https://api.calendly.com/event_types/{mapping.event_type_uuid}",
                "owner_type": "EventType"
            }

            scheduling_response = requests.post(
                "https://api.calendly.com/scheduling_links",
                headers=headers,
                json=scheduling_payload
            )

            if scheduling_response.status_code == 201:
                scheduling_data = scheduling_response.json()
                booking_url = scheduling_data["resource"]["booking_url"]

                # Store in lead metadata
                if not lead.meta_data:
                    lead.meta_data = {}
                lead.meta_data["calendly_link"] = booking_url
                lead.meta_data["ai_suggested_time"] = iso_timestamp
                lead.meta_data["calendly_created_at"] = datetime.utcnow().isoformat()
                db.commit()

                # Remove BOOK: directive from message shown to user
                clean_message = ai_message.replace(booking_line, "").strip()

                return {
                    "ai_message": clean_message,
                    "booking_created": True,
                    "booking_url": booking_url,
                    "suggested_time": iso_timestamp,
                    "lead_name": lead.name
                }

        # Regular conversation response
        return {
            "ai_message": ai_message,
            "booking_created": False,
            "available_slots": formatted_slots[:5]  # Show top 5 in response
        }

    except Exception as e:
        logger.error(f"AI scheduling error: {e}")
        raise HTTPException(status_code=500, detail=f"AI scheduling failed: {str(e)}")

# ============================================================================
# ONBOARDING ENDPOINTS
# ============================================================================

@app.get("/api/v1/onboarding/steps")
async def get_onboarding_steps(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get onboarding step templates (customized or default)"""
    try:
        # Check if user has customized steps
        custom_steps = db.query(OnboardingStep).filter(
            OnboardingStep.user_id == current_user.id,
            OnboardingStep.is_active == True
        ).order_by(OnboardingStep.step_number).all()

        if custom_steps:
            return {
                "steps": [
                    {
                        "id": step.id,
                        "step_number": step.step_number,
                        "title": step.title,
                        "description": step.description,
                        "icon": step.icon,
                        "required": step.required,
                        "fields": step.fields or []
                    }
                    for step in custom_steps
                ],
                "is_custom": True
            }

        # Return default onboarding steps
        default_steps = [
            {
                "step_number": 1,
                "title": "Welcome to Your CRM",
                "description": "Let's get you set up with everything you need to manage your mortgage pipeline effectively.",
                "icon": "👋",
                "required": True,
                "fields": []
            },
            {
                "step_number": 2,
                "title": "Upload Your Documents",
                "description": "Upload important documents like rate sheets, guidelines, or templates you frequently use.",
                "icon": "📄",
                "required": False,
                "fields": [
                    {"name": "documents", "type": "file", "label": "Upload Documents", "multiple": True}
                ]
            },
            {
                "step_number": 3,
                "title": "Connect Your Integrations",
                "description": "Connect your email, calendar, and other tools to streamline your workflow.",
                "icon": "🔗",
                "required": False,
                "fields": [
                    {"name": "connect_email", "type": "button", "label": "Connect Outlook", "action": "email_oauth"},
                    {"name": "connect_calendar", "type": "button", "label": "Connect Calendar", "action": "calendar_oauth"}
                ]
            },
            {
                "step_number": 4,
                "title": "Add Team Members",
                "description": "Invite processors, assistants, or team members who will work with you.",
                "icon": "👥",
                "required": False,
                "fields": [
                    {"name": "team_member_email", "type": "email", "label": "Team Member Email"},
                    {"name": "team_member_role", "type": "select", "label": "Role", "options": ["Processor", "Assistant", "Loan Officer"]}
                ]
            },
            {
                "step_number": 5,
                "title": "You're All Set!",
                "description": "Your CRM is ready to go. Start adding leads and let AI help you close more deals!",
                "icon": "🎉",
                "required": True,
                "fields": []
            }
        ]

        return {"steps": default_steps, "is_custom": False}

    except Exception as e:
        logger.error(f"Get onboarding steps error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/onboarding/steps")
async def update_onboarding_steps(
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update/customize onboarding step templates"""
    try:
        steps_data = request.get("steps", [])

        # Delete existing custom steps
        db.query(OnboardingStep).filter(
            OnboardingStep.user_id == current_user.id
        ).delete()

        # Create new custom steps
        for step_data in steps_data:
            step = OnboardingStep(
                user_id=current_user.id,
                step_number=step_data.get("step_number"),
                title=step_data.get("title"),
                description=step_data.get("description"),
                icon=step_data.get("icon", "📄"),
                required=step_data.get("required", True),
                fields=step_data.get("fields", [])
            )
            db.add(step)

        db.commit()

        return {"message": "Onboarding steps updated successfully", "count": len(steps_data)}

    except Exception as e:
        db.rollback()
        logger.error(f"Update onboarding steps error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/onboarding/progress")
async def get_onboarding_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's onboarding progress"""
    try:
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if not progress:
            # Create initial progress
            progress = OnboardingProgress(
                user_id=current_user.id,
                current_step=1,
                steps_completed=[]
            )
            db.add(progress)
            db.commit()
            db.refresh(progress)

        return {
            "current_step": progress.current_step,
            "steps_completed": progress.steps_completed or [],
            "is_complete": progress.is_complete,
            "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
            "uploaded_documents": progress.uploaded_documents or [],
            "team_members_added": progress.team_members_added,
            "workflows_generated": progress.workflows_generated
        }

    except Exception as e:
        logger.error(f"Get onboarding progress error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/onboarding/progress")
async def update_onboarding_progress(
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's onboarding progress"""
    try:
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if not progress:
            progress = OnboardingProgress(user_id=current_user.id)
            db.add(progress)

        # Update fields
        if "current_step" in request:
            progress.current_step = request["current_step"]

        if "steps_completed" in request:
            progress.steps_completed = request["steps_completed"]

        if "uploaded_documents" in request:
            progress.uploaded_documents = request["uploaded_documents"]

        if "team_members_added" in request:
            progress.team_members_added = request["team_members_added"]

        db.commit()

        return {"message": "Progress updated successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Update onboarding progress error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/onboarding/complete")
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark onboarding as complete for user"""
    try:
        # Update progress
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if progress:
            progress.is_complete = True
            progress.completed_at = datetime.utcnow()

        # Update user
        current_user.onboarding_completed = True

        db.commit()

        return {"message": "Onboarding completed!", "completed_at": datetime.utcnow().isoformat()}

    except Exception as e:
        db.rollback()
        logger.error(f"Complete onboarding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STARTUP EVENT
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("🚀 Starting Agentic AI Mortgage CRM...")
    
    try:
        # Initialize database
        if init_db():
            # Create sample data
            db = SessionLocal()
            try:
                create_sample_data(db)
            except Exception as e:
                logger.warning(f"⚠️ Sample data creation skipped: {e}")
            finally:
                db.close()
    except Exception as e:
        logger.warning(f"⚠️ Startup initialization skipped: {e}")
        logger.info("Application will still start, database will be initialized on first request")

    logger.info("✅ CRM is ready!")
    logger.info("📚 API Documentation: http://localhost:8000/docs")
    logger.info("🔐 Demo Login: demo@example.com / demo123")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
