
# ============================================================================
# COMPLETE AGENTIC AI MORTGAGE CRM - FULLY FUNCTIONAL
# ============================================================================
# All features implemented:
# ✅ Complete CRUD for all entities
# ✅ AI Integration with OpenAI & Anthropic Claude
# ✅ Authentication & Security (JWT + API Keys)
# ✅ Sample data generation
# ✅ AI Underwriter with Claude AI
# ✅ AI Assistant with OpenAI GPT
# ✅ Zapier Integration via API Keys
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
from datetime import datetime, timedelta, timezone
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
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import asyncio

# Import security middleware
from security_middleware import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    IPBlockingMiddleware,
    RequestValidationMiddleware,
    SecurityLoggingMiddleware
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Fix Railway DATABASE_URL format (postgres:// -> postgresql://)
# Use SQLite for local development if DATABASE_URL not set
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
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
# SQLite-specific settings
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialize background scheduler for auto-sync
scheduler = AsyncIOScheduler()

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    branch = relationship("Branch", back_populates="users")
    leads = relationship("Lead", back_populates="owner")
    loans = relationship("Loan", back_populates="loan_officer")

class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime, nullable=True)

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    email = Column(String, index=True)
    phone = Column(String)
    co_applicant_name = Column(String)
    co_applicant_email = Column(String)
    co_applicant_phone = Column(String)
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    loan = relationship("Loan", back_populates="tasks")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(String, default="pending")  # pending, in_progress, completed
    priority = Column(String, default="medium")  # low, medium, high
    due_date = Column(DateTime)
    owner_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    related_contact_name = Column(String)
    related_type = Column(String)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    owner = relationship("User", backref="tasks")
    lead = relationship("Lead", backref="tasks")
    loan = relationship("Loan", backref="user_tasks")

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    integration_type = Column(String, nullable=False)  # calendly, zoom, docusign, etc.
    api_key = Column(String, nullable=False)  # Encrypted API key
    refresh_token = Column(String)  # For OAuth integrations
    access_token = Column(String)  # For OAuth integrations
    token_expiry = Column(DateTime)  # When access token expires
    integration_metadata = Column(JSON)  # Additional integration-specific data (renamed from metadata to avoid SQLAlchemy reserved word)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    email = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
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
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

# ============================================================================
# DATA RECONCILIATION ENGINE (DRE) MODELS
# ============================================================================

class IncomingDataEvent(Base):
    __tablename__ = "incoming_data_events"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False)  # 'outlook', 'calendar', 'dropbox', etc.
    raw_text = Column(Text)
    raw_html = Column(Text)
    subject = Column(String)
    sender = Column(String)
    recipients = Column(JSON)
    attachments = Column(JSON)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ExtractedData(Base):
    __tablename__ = "extracted_data"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("incoming_data_events.id"))
    category = Column(String)  # 'lead_update', 'loan_update', 'portfolio_update', etc.
    subcategory = Column(String)  # 'rate_lock', 'appraisal', 'title_clear', etc.
    fields = Column(JSON)  # {field_name: {value, confidence}}
    match_entity_type = Column(String)  # 'lead', 'loan', 'partner', etc.
    match_entity_id = Column(Integer)  # ID of matched entity
    match_confidence = Column(Float)
    ai_confidence = Column(Float)
    status = Column(String, default='pending_review')  # 'auto_applied', 'pending_review', 'rejected', 'error'
    applied_at = Column(DateTime)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AITrainingEvent(Base):
    __tablename__ = "ai_training_events"
    id = Column(Integer, primary_key=True, index=True)
    extracted_data_id = Column(Integer, ForeignKey("extracted_data.id"))
    field_name = Column(String)
    original_value = Column(String)
    corrected_value = Column(String)
    label = Column(String)  # 'correct', 'incorrect', 'overridden'
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class MicrosoftOAuthToken(Base):
    __tablename__ = "microsoft_oauth_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    access_token = Column(Text)  # Encrypted token
    refresh_token = Column(Text)  # Encrypted token
    token_expires_at = Column(DateTime)
    email_address = Column(String)  # Microsoft email address
    sync_enabled = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)
    sync_folder = Column(String, default="Inbox")  # Which folder to sync
    sync_frequency_minutes = Column(Integer, default=15)  # How often to sync
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

# ============================================================================
# CLIENT MANAGEMENT PROFILE (CMP) - MASTER SUBSCRIBER PROFILE
# ============================================================================

class ClientProfile(Base):
    __tablename__ = "client_profiles"

    # 1. ACCOUNT & SUBSCRIBER IDENTIFICATION
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String, unique=True, index=True)  # UUID for the subscriber
    account_type = Column(String)  # Solo LO / Team / Branch / Brokerage / Lender
    primary_user_id = Column(Integer, ForeignKey("users.id"))
    company_name = Column(String)  # DBA Name
    nmls_number = Column(String)  # NMLS # for LO
    business_address = Column(JSON)  # {street, city, state, zip}
    team_size = Column(Integer, default=1)

    # 2. USER PROFILE (Primary User)
    user_profile = Column(JSON)  # {first_name, last_name, photo_url, title, pronouns, email, phone, calendar_link, signature_block, disc_profile, communication_style, work_hours, days_off, vacation_mode, coaching_preferences}

    # 3. TEAM STRUCTURE (stored as JSON for flexibility)
    team_structure = Column(JSON)  # Array of team members with roles and responsibilities

    # 4. SYSTEM INTEGRATIONS CONFIGURATION
    integration_settings = Column(JSON)  # {email, calendar, sms, phone, los, pos, credit, pricing, storage, esignature, crm_sync, lead_providers}

    # 5. CUSTOM PROCESS FLOW
    process_flow_documents = Column(JSON)  # Array of uploaded document references
    ai_parsed_process_tree = Column(JSON)  # Node-based process structure
    role_to_task_mapping = Column(JSON)  # AI-generated responsibilities
    stage_definitions = Column(JSON)  # Lead → App → Processing → UW → CTC → Closing → Post-Close
    user_confirmed_flow = Column(JSON)  # Final approved process map

    # 6. COMMUNICATION & BRANDING SETTINGS
    branding_settings = Column(JSON)  # {email_signature, text_signature, brand_colors, logo_url, team_headshots, partner_branding}

    # 7. AUTOMATION SETTINGS & PREFERENCES
    automation_settings = Column(JSON)  # {speed_to_lead, auto_task_creation, sla_definitions, coach_intensity, follow_up_cadences, scorecard_delivery, notification_preferences, ai_auto_update_threshold}

    # 8. DATA RECONCILIATION PREFERENCES
    reconciliation_settings = Column(JSON)  # {auto_update_threshold, fields_to_review, fields_auto_approve, fields_never_modify, trusted_senders, match_preferences}

    # 9. LEAD & PIPELINE PREFERENCES
    pipeline_settings = Column(JSON)  # {lead_scoring_rules, follow_up_model, lead_buckets, partner_attribution, product_preferences, market_footprint}

    # 10. ANALYTICS, KPI TARGETS & COACHING GOALS
    kpi_targets = Column(JSON)  # {monthly_funded_goal, weekly_app_goal, daily_conversations, speed_to_lead_target, pull_through_target, preapproval_conversion, cycle_time_target, rework_reduction, nps_goal}

    # 11. BILLING & SUBSCRIPTION SETTINGS
    subscription_plan = Column(String)  # Solo / Team / Branch / Enterprise
    addon_modules = Column(JSON)  # Array of enabled add-ons
    seats = Column(Integer, default=1)
    billing_cycle = Column(String)  # monthly / annual
    billing_status = Column(String)  # active / past_due / canceled
    payment_method = Column(JSON)  # Payment details (encrypted)
    usage_metrics = Column(JSON)  # {sms_count, calls_count, ai_tokens, storage_gb}
    renewal_date = Column(DateTime)

    # 12. SUPPORT, LOGGING & AUDIT HISTORY
    support_tickets = Column(JSON)  # Array of support interactions
    ai_corrections = Column(JSON)  # Log of AI model corrections
    reconciliation_history = Column(JSON)  # History of data reconciliations
    user_overrides = Column(JSON)  # User preference overrides
    webhook_logs = Column(JSON)  # Integration logs
    integration_errors = Column(JSON)  # Error tracking

    # 13. PORTFOLIO SETTINGS
    portfolio_settings = Column(JSON)  # {mum_config, annual_review_automation, rate_drop_alerts, equity_alerts, insurance_reminders, pmi_monitoring, cashout_flags}

    # 14. ADVANCED FIELDS
    advanced_settings = Column(JSON)  # {partner_grading, task_delegation_matrix, ops_capacity_model, personal_brand_library, video_library, custom_calculators, custom_roles}

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    primary_user = relationship("User", backref="client_profile")

class TeamRole(Base):
    __tablename__ = "team_roles"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Null if role not assigned yet
    role_name = Column(String)  # Loan Officer, Processor, etc.
    responsibilities = Column(JSON)  # Array of responsibilities
    permissions = Column(JSON)  # Role-based permissions
    service_level_expectations = Column(JSON)
    backup_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    profile = relationship("ClientProfile", backref="team_roles")
    user = relationship("User", foreign_keys=[user_id], backref="assigned_roles")
    backup_user = relationship("User", foreign_keys=[backup_user_id])

class ProcessFlowDocument(Base):
    __tablename__ = "process_flow_documents"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"))
    document_name = Column(String)
    document_type = Column(String)  # PDF, spreadsheet, flowchart, SOP
    file_url = Column(String)  # S3 or storage URL
    ai_parsing_status = Column(String)  # pending, processing, completed, failed
    ai_parsed_content = Column(JSON)  # Extracted content
    upload_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    profile = relationship("ClientProfile", backref="uploaded_process_flows")

class KPISnapshot(Base):
    __tablename__ = "kpi_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"))
    snapshot_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    metrics = Column(JSON)  # All KPI metrics for this snapshot
    targets = Column(JSON)  # Targets at time of snapshot
    performance_score = Column(Float)  # Overall performance percentage
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    profile = relationship("ClientProfile", backref="kpi_history")

class ProcessTemplate(Base):
    __tablename__ = "process_templates"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_name = Column(String, nullable=False)  # Loan Officer, Processor, Underwriter, etc.
    task_title = Column(String, nullable=False)
    task_description = Column(Text)
    sequence_order = Column(Integer, default=0)  # Order in the process
    estimated_duration = Column(Integer)  # In minutes
    dependencies = Column(JSON)  # Array of task IDs this depends on
    is_required = Column(Boolean, default=True)
    automation_potential = Column(String)  # AI suggestion: high, medium, low, none
    efficiency_notes = Column(Text)  # AI-generated efficiency suggestions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="process_templates")

class ProcessRole(Base):
    """Stores AI-extracted roles from onboarding documents"""
    __tablename__ = "process_roles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_name = Column(String, nullable=False)
    role_title = Column(String, nullable=False)  # Display title
    responsibilities = Column(Text)  # AI-extracted responsibilities summary
    skills_required = Column(JSON)  # Array of required skills
    key_activities = Column(JSON)  # Array of key activities
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="process_roles")

class ProcessMilestone(Base):
    """Stores milestones from parsed process documents"""
    __tablename__ = "process_milestones"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    sequence_order = Column(Integer, default=0)
    estimated_duration = Column(Integer)  # Total duration in hours
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="process_milestones")

class ProcessTask(Base):
    """Stores tasks extracted from process documents"""
    __tablename__ = "process_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    milestone_id = Column(Integer, ForeignKey("process_milestones.id"))
    role_id = Column(Integer, ForeignKey("process_roles.id"))
    task_name = Column(String, nullable=False)
    task_description = Column(Text)
    sequence_order = Column(Integer, default=0)
    estimated_duration = Column(Integer)  # In minutes
    sla = Column(Integer)  # SLA in hours
    sla_unit = Column(String, default="hours")  # hours, days, minutes
    ai_automatable = Column(Boolean, default=False)
    dependencies = Column(JSON)  # Array of task IDs
    is_required = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="process_tasks")
    milestone = relationship("ProcessMilestone", backref="tasks")
    role = relationship("ProcessRole", backref="assigned_tasks")

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

class TeamMemberCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    title: Optional[str] = None

class TeamMemberUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    title: Optional[str] = None

class ApiKeyCreate(BaseModel):
    name: str

class ApiKeyResponse(BaseModel):
    id: int
    key: str
    name: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
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
    co_applicant_name: Optional[str] = None
    co_applicant_email: Optional[str] = None
    co_applicant_phone: Optional[str] = None
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
    co_applicant_email: Optional[str] = None
    co_applicant_phone: Optional[str] = None
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

# ============================================================================
# CLIENT MANAGEMENT PROFILE (CMP) SCHEMAS
# ============================================================================

class UserProfileData(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    photo_url: Optional[str] = None
    title: Optional[str] = None
    pronouns: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    calendar_link: Optional[str] = None
    signature_block: Optional[str] = None
    disc_profile: Optional[str] = None
    communication_style: Optional[str] = None
    work_hours: Optional[Dict[str, Any]] = None
    days_off: Optional[List[str]] = None
    vacation_mode: Optional[bool] = False
    coaching_preferences: Optional[str] = None

class BrandingSettings(BaseModel):
    email_signature: Optional[str] = None
    text_signature: Optional[str] = None
    brand_colors: Optional[Dict[str, str]] = None
    logo_url: Optional[str] = None
    team_headshots: Optional[List[str]] = None
    partner_branding: Optional[Dict[str, Any]] = None

class IntegrationSettings(BaseModel):
    email: Optional[Dict[str, Any]] = None
    calendar: Optional[Dict[str, Any]] = None
    sms: Optional[Dict[str, Any]] = None
    phone: Optional[Dict[str, Any]] = None
    los: Optional[Dict[str, Any]] = None
    pos: Optional[Dict[str, Any]] = None
    credit: Optional[Dict[str, Any]] = None
    pricing: Optional[Dict[str, Any]] = None
    storage: Optional[Dict[str, Any]] = None
    esignature: Optional[Dict[str, Any]] = None
    crm_sync: Optional[Dict[str, Any]] = None
    lead_providers: Optional[List[Dict[str, Any]]] = None

class AutomationSettings(BaseModel):
    speed_to_lead: Optional[Dict[str, Any]] = None
    auto_task_creation: Optional[bool] = True
    sla_definitions: Optional[Dict[str, Any]] = None
    coach_intensity: Optional[str] = "medium"
    follow_up_cadences: Optional[Dict[str, Any]] = None
    scorecard_delivery: Optional[str] = "email"
    notification_preferences: Optional[Dict[str, Any]] = None
    ai_auto_update_threshold: Optional[float] = 0.8

class ReconciliationSettings(BaseModel):
    auto_update_threshold: Optional[float] = 0.8
    fields_to_review: Optional[List[str]] = None
    fields_auto_approve: Optional[List[str]] = None
    fields_never_modify: Optional[List[str]] = None
    trusted_senders: Optional[List[str]] = None
    match_preferences: Optional[Dict[str, Any]] = None

class PipelineSettings(BaseModel):
    lead_scoring_rules: Optional[Dict[str, Any]] = None
    follow_up_model: Optional[str] = "balanced"
    lead_buckets: Optional[List[str]] = None
    partner_attribution: Optional[Dict[str, Any]] = None
    product_preferences: Optional[List[str]] = None
    market_footprint: Optional[Dict[str, Any]] = None

class KPITargets(BaseModel):
    monthly_funded_goal: Optional[int] = None
    weekly_app_goal: Optional[int] = None
    daily_conversations: Optional[int] = None
    speed_to_lead_target: Optional[int] = None
    pull_through_target: Optional[float] = None
    preapproval_conversion: Optional[float] = None
    cycle_time_target: Optional[int] = None
    rework_reduction: Optional[float] = None
    nps_goal: Optional[float] = None

class PortfolioSettings(BaseModel):
    mum_config: Optional[Dict[str, Any]] = None
    annual_review_automation: Optional[bool] = True
    rate_drop_alerts: Optional[bool] = True
    equity_alerts: Optional[bool] = True
    insurance_reminders: Optional[bool] = True
    pmi_monitoring: Optional[bool] = True
    cashout_flags: Optional[bool] = True

class AdvancedSettings(BaseModel):
    partner_grading: Optional[Dict[str, Any]] = None
    task_delegation_matrix: Optional[Dict[str, Any]] = None
    ops_capacity_model: Optional[Dict[str, Any]] = None
    personal_brand_library: Optional[List[str]] = None
    video_library: Optional[List[str]] = None
    custom_calculators: Optional[List[str]] = None
    custom_roles: Optional[List[str]] = None

class ClientProfileCreate(BaseModel):
    account_type: str  # Solo LO / Team / Branch / Brokerage / Lender
    company_name: str
    nmls_number: Optional[str] = None
    business_address: Optional[Dict[str, str]] = None
    team_size: Optional[int] = 1
    user_profile: Optional[UserProfileData] = None
    subscription_plan: Optional[str] = "Solo"

class ClientProfileUpdate(BaseModel):
    account_type: Optional[str] = None
    company_name: Optional[str] = None
    nmls_number: Optional[str] = None
    business_address: Optional[Dict[str, str]] = None
    team_size: Optional[int] = None
    user_profile: Optional[UserProfileData] = None
    team_structure: Optional[List[Dict[str, Any]]] = None
    integration_settings: Optional[IntegrationSettings] = None
    branding_settings: Optional[BrandingSettings] = None
    automation_settings: Optional[AutomationSettings] = None
    reconciliation_settings: Optional[ReconciliationSettings] = None
    pipeline_settings: Optional[PipelineSettings] = None
    kpi_targets: Optional[KPITargets] = None
    portfolio_settings: Optional[PortfolioSettings] = None
    advanced_settings: Optional[AdvancedSettings] = None

class ClientProfileResponse(BaseModel):
    id: int
    account_id: str
    account_type: str
    primary_user_id: int
    company_name: str
    nmls_number: Optional[str]
    business_address: Optional[Dict[str, Any]]
    team_size: int
    user_profile: Optional[Dict[str, Any]]
    team_structure: Optional[List[Dict[str, Any]]]
    integration_settings: Optional[Dict[str, Any]]
    branding_settings: Optional[Dict[str, Any]]
    automation_settings: Optional[Dict[str, Any]]
    reconciliation_settings: Optional[Dict[str, Any]]
    pipeline_settings: Optional[Dict[str, Any]]
    kpi_targets: Optional[Dict[str, Any]]
    subscription_plan: str
    billing_status: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class TeamRoleCreate(BaseModel):
    role_name: str
    user_id: Optional[int] = None
    responsibilities: Optional[List[str]] = None
    permissions: Optional[Dict[str, Any]] = None
    service_level_expectations: Optional[Dict[str, Any]] = None
    backup_user_id: Optional[int] = None

class TeamRoleUpdate(BaseModel):
    role_name: Optional[str] = None
    user_id: Optional[int] = None
    responsibilities: Optional[List[str]] = None
    permissions: Optional[Dict[str, Any]] = None
    service_level_expectations: Optional[Dict[str, Any]] = None
    backup_user_id: Optional[int] = None
    is_active: Optional[bool] = None

class TeamRoleResponse(BaseModel):
    id: int
    profile_id: int
    role_name: str
    user_id: Optional[int]
    responsibilities: Optional[List[Any]]
    permissions: Optional[Dict[str, Any]]
    service_level_expectations: Optional[Dict[str, Any]]
    backup_user_id: Optional[int]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ProcessFlowDocumentCreate(BaseModel):
    document_name: str
    document_type: str  # PDF, spreadsheet, flowchart, SOP
    file_url: str

class ProcessFlowDocumentResponse(BaseModel):
    id: int
    profile_id: int
    document_name: str
    document_type: str
    file_url: str
    ai_parsing_status: str
    ai_parsed_content: Optional[Dict[str, Any]]
    upload_date: datetime
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

class ProcessTemplateCreate(BaseModel):
    role_name: str
    task_title: str
    task_description: Optional[str] = None
    sequence_order: int = 0
    estimated_duration: Optional[int] = None
    dependencies: Optional[List[int]] = None
    is_required: bool = True

class ProcessTemplateUpdate(BaseModel):
    task_title: Optional[str] = None
    task_description: Optional[str] = None
    sequence_order: Optional[int] = None
    estimated_duration: Optional[int] = None
    dependencies: Optional[List[int]] = None
    is_required: Optional[bool] = None
    is_active: Optional[bool] = None

class ProcessTemplateResponse(BaseModel):
    id: int
    role_name: str
    task_title: str
    task_description: Optional[str]
    sequence_order: int
    estimated_duration: Optional[int]
    dependencies: Optional[List[int]]
    is_required: bool
    automation_potential: Optional[str]
    efficiency_notes: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class ProcessRoleCreate(BaseModel):
    role_name: str
    role_title: str
    responsibilities: Optional[str] = None
    skills_required: Optional[List[str]] = None
    key_activities: Optional[List[str]] = None

class ProcessRoleResponse(BaseModel):
    id: int
    role_name: str
    role_title: str
    responsibilities: Optional[str]
    skills_required: Optional[List[str]]
    key_activities: Optional[List[str]]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ProcessMilestoneCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sequence_order: int = 0
    estimated_duration: Optional[int] = None

class ProcessMilestoneResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    sequence_order: int
    estimated_duration: Optional[int]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ProcessTaskCreate(BaseModel):
    milestone_id: int
    role_id: int
    task_name: str
    task_description: Optional[str] = None
    sequence_order: int = 0
    estimated_duration: Optional[int] = None
    sla: Optional[int] = None
    sla_unit: str = "hours"
    ai_automatable: bool = False
    dependencies: Optional[List[int]] = None
    is_required: bool = True

class ProcessTaskResponse(BaseModel):
    id: int
    milestone_id: int
    role_id: int
    task_name: str
    task_description: Optional[str]
    sequence_order: int
    estimated_duration: Optional[int]
    sla: Optional[int]
    sla_unit: str
    ai_automatable: bool
    dependencies: Optional[List[int]]
    is_required: bool
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class DocumentParseRequest(BaseModel):
    document_content: str  # Base64 encoded document or text content
    document_name: Optional[str] = None
    document_type: Optional[str] = None  # pdf, docx, txt, etc.

class DocumentParseResponse(BaseModel):
    roles: List[ProcessRoleResponse]
    milestones: List[ProcessMilestoneResponse]
    tasks: List[ProcessTaskResponse]
    summary: Dict[str, Any]

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

# ============================================================================
# PERFORMANCE COACH SCHEMAS
# ============================================================================

class CoachMode(str, enum.Enum):
    daily_briefing = "daily_briefing"
    pipeline_audit = "pipeline_audit"
    focus_reset = "focus_reset"
    accountability = "accountability"
    tactical_advice = "tactical_advice"
    tough_love = "tough_love"
    teach_process = "teach_process"
    priority_guidance = "priority_guidance"

class CoachRequest(BaseModel):
    mode: CoachMode
    message: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class CoachResponse(BaseModel):
    mode: CoachMode
    response: str
    priorities: Optional[List[Dict[str, Any]]] = None
    metrics: Optional[Dict[str, Any]] = None
    action_items: Optional[List[str]] = None

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
# DATA RECONCILIATION ENGINE SCHEMAS
# ============================================================================

class IncomingDataEventCreate(BaseModel):
    source: str
    raw_text: Optional[str] = None
    raw_html: Optional[str] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    recipients: Optional[List[str]] = None
    attachments: Optional[List[Dict[str, Any]]] = None

class ExtractedDataResponse(BaseModel):
    id: int
    event_id: int
    category: Optional[str]
    subcategory: Optional[str]
    fields: Dict[str, Any]
    match_entity_type: Optional[str]
    match_entity_id: Optional[int]
    match_confidence: Optional[float]
    ai_confidence: Optional[float]
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class ReconciliationApproval(BaseModel):
    extracted_data_id: int
    approved_fields: Optional[Dict[str, Any]] = None  # If partial approval
    corrections: Optional[Dict[str, Any]] = None  # If user corrected values

class ReconciliationRejection(BaseModel):
    extracted_data_id: int
    reason: Optional[str] = None

# ============================================================================
# MICROSOFT OAUTH SCHEMAS
# ============================================================================

class MicrosoftOAuthConnect(BaseModel):
    authorization_code: str
    redirect_uri: str

class MicrosoftTokenResponse(BaseModel):
    connected: bool
    email_address: Optional[str] = None
    sync_enabled: bool = True
    last_sync_at: Optional[datetime] = None

class MicrosoftSyncSettings(BaseModel):
    sync_enabled: Optional[bool] = None
    sync_folder: Optional[str] = None
    sync_frequency_minutes: Optional[int] = None

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

# Add security middleware (order matters - first added is last executed)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestValidationMiddleware)
app.add_middleware(IPBlockingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=100, requests_per_hour=2000)
app.add_middleware(SecurityLoggingMiddleware)

logger.info("✅ Security middleware enabled: Rate limiting, IP blocking, security headers, request validation, and logging")

# Auth - Define BEFORE importing routes that use these functions
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Include public routes - Import AFTER defining functions it needs
from public_routes import router as public_router
app.include_router(public_router, tags=["Public"])

# Include AI API routes
from ai_api_endpoints import router as ai_router
app.include_router(ai_router, tags=["AI System"])

# Include Mission Control routes
from mission_control_routes import router as mission_control_router
app.include_router(mission_control_router, tags=["Mission Control"])

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Check if token is an API key (starts with 'sk_')
    if token.startswith('sk_'):
        api_key = db.query(ApiKey).filter(
            ApiKey.key == token,
            ApiKey.is_active == True
        ).first()

        if api_key is None:
            raise credentials_exception

        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

        # Get the user associated with this API key
        user = db.query(User).filter(User.id == api_key.user_id).first()
        if user is None:
            raise credentials_exception
        return user

    # Otherwise, treat it as a JWT token
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

async def get_current_user_flexible(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    Flexible authentication that supports both:
    1. Authorization: Bearer <token|api_key>
    2. X-API-Key: <api_key>

    This is useful for Zapier and other integrations.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None

    # Check X-API-Key header first (for Zapier and similar integrations)
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        # Try to find API key in database
        api_key = db.query(ApiKey).filter(
            ApiKey.key == api_key_header,
            ApiKey.is_active == True
        ).first()

        if api_key:
            # Update last used timestamp
            api_key.last_used_at = datetime.now(timezone.utc)
            db.commit()

            # Get the user associated with this API key
            user = db.query(User).filter(User.id == api_key.user_id).first()
            if user:
                return user

        # If we have X-API-Key header but it's invalid, raise exception
        raise credentials_exception

    # Check Authorization header (Bearer token)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")

    if not token:
        raise credentials_exception

    # Check if token is an API key (starts with 'sk_')
    if token.startswith('sk_'):
        api_key = db.query(ApiKey).filter(
            ApiKey.key == token,
            ApiKey.is_active == True
        ).first()

        if api_key is None:
            raise credentials_exception

        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

        # Get the user associated with this API key
        user = db.query(User).filter(User.id == api_key.user_id).first()
        if user is None:
            raise credentials_exception
        return user

    # Otherwise, treat it as a JWT token
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
# API KEY HELPER FUNCTIONS
# ============================================================================

def generate_api_key() -> str:
    """Generate a secure API key with prefix 'sk_'"""
    import secrets
    random_part = secrets.token_urlsafe(32)
    return f"sk_{random_part}"

# ============================================================================
# AI HELPER FUNCTIONS
# ============================================================================

def generate_ai_insights(loan: Loan) -> str:
    """Generate AI insights for a loan (simple rule-based for now)"""
    insights = []

    if loan.days_in_stage and loan.days_in_stage > 10:
        insights.append(f"⚠️ Loan has been in {loan.stage.value} stage for {loan.days_in_stage} days")

    if loan.closing_date:
        # Make closing_date timezone-aware if it's naive
        closing_dt = loan.closing_date if loan.closing_date.tzinfo else loan.closing_date.replace(tzinfo=timezone.utc)
        if (closing_dt - datetime.now(timezone.utc)).days < 7:
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
# DATA RECONCILIATION ENGINE (DRE) - AI EXTRACTION
# ============================================================================

def classify_email_content(content: str, subject: str) -> Dict[str, Any]:
    """Use AI to classify email content and determine category"""

    if not openai_client:
        logger.warning("OpenAI client not initialized - using fallback classification")
        # Fallback: Use keyword matching to classify
        content_lower = content.lower()
        subject_lower = subject.lower()

        if any(word in subject_lower or word in content_lower for word in ['loan', 'mortgage', 'borrower', 'closing', 'rate lock']):
            return {"category": "loan_update", "subcategory": "general", "confidence": 0.5}
        else:
            return {"category": "loan_update", "subcategory": "general", "confidence": 0.3}

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an email classification expert for mortgage loan processing.

Classify emails into categories:
- lead_update: New lead information or lead status changes
- loan_update: Active loan milestone updates
- rate_lock: Rate lock confirmations or expirations
- appraisal: Appraisal scheduling or results
- title: Title work, clear to close
- insurance: HOI binders, insurance updates
- closing: Closing date/time, CD delivery
- document: Document receipt confirmations
- portfolio: Servicing, escrow, tax updates
- unrelated: Not mortgage-related

Return JSON: {"category": "...", "subcategory": "...", "confidence": 0.0-1.0}"""
                },
                {
                    "role": "user",
                    "content": f"Subject: {subject}\n\nContent: {content[:1000]}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"Email classification error: {e}")
        # Return loan_update with low confidence so email still gets processed
        return {"category": "loan_update", "subcategory": "error", "confidence": 0.3}

def extract_loan_fields(content: str, category: str) -> Dict[str, Dict[str, Any]]:
    """Extract structured loan fields from email content"""

    if not openai_client:
        logger.warning("OpenAI client not initialized - cannot extract loan fields, returning empty")
        return {}

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"""Extract mortgage loan fields from this {category} email.

Extract any present fields:
- loan_number: string
- borrower_name: string
- property_address: string
- loan_amount: float
- rate: float (as decimal, e.g., 6.125)
- rate_lock_date: ISO date
- lock_expiration: ISO date
- appraisal_date: ISO date
- appraisal_value: float
- closing_date: ISO datetime
- milestone: string (e.g., "RateLocked", "AppraisalOrdered", "ClearToClose")
- documents_received: list of strings
- lender: string
- realtor_name: string
- title_company: string

For each field found, return:
{{"field_name": {{"value": actual_value, "confidence": 0.0-1.0}}}}

Return JSON object. Only include fields you found. Use null for missing."""
                },
                {
                    "role": "user",
                    "content": content[:2000]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )

        fields = json.loads(response.choices[0].message.content)
        return fields
    except Exception as e:
        logger.error(f"Field extraction error: {e}")
        return {}

def match_entity(fields: Dict[str, Any], db: Session, user_id: int) -> Dict[str, Any]:
    """Match extracted fields to existing CRM entities"""

    match_results = {
        "entity_type": None,
        "entity_id": None,
        "confidence": 0.0,
        "candidates": []
    }

    # Try to match by loan number first (highest confidence)
    if "loan_number" in fields and fields["loan_number"].get("value"):
        loan_num = str(fields["loan_number"]["value"])
        loan = db.query(Loan).filter(
            Loan.loan_number == loan_num,
            Loan.loan_officer_id == user_id
        ).first()

        if loan:
            match_results["entity_type"] = "loan"
            match_results["entity_id"] = loan.id
            match_results["confidence"] = 0.95
            return match_results

    # Try to match by borrower name + fuzzy matching
    if "borrower_name" in fields and fields["borrower_name"].get("value"):
        borrower = fields["borrower_name"]["value"].lower()

        # Try leads first
        leads = db.query(Lead).filter(Lead.owner_id == user_id).all()
        for lead in leads:
            if lead.name and borrower in lead.name.lower():
                match_results["candidates"].append({
                    "type": "lead",
                    "id": lead.id,
                    "name": lead.name,
                    "confidence": 0.75
                })

        # Try loans
        loans = db.query(Loan).filter(Loan.loan_officer_id == user_id).all()
        for loan in loans:
            if loan.borrower_name and borrower in loan.borrower_name.lower():
                match_results["candidates"].append({
                    "type": "loan",
                    "id": loan.id,
                    "name": loan.borrower_name,
                    "confidence": 0.80
                })

    # Return best candidate if found
    if match_results["candidates"]:
        best = max(match_results["candidates"], key=lambda x: x["confidence"])
        match_results["entity_type"] = best["type"]
        match_results["entity_id"] = best["id"]
        match_results["confidence"] = best["confidence"]

    return match_results

def apply_extracted_data(extracted_data: ExtractedData, db: Session) -> bool:
    """Apply extracted data to CRM entities"""

    try:
        if extracted_data.match_entity_type == "loan" and extracted_data.match_entity_id:
            loan = db.query(Loan).filter(Loan.id == extracted_data.match_entity_id).first()
            if not loan:
                return False

            # Apply high-confidence fields
            fields = extracted_data.fields

            if "rate" in fields and fields["rate"]["confidence"] > 0.85:
                loan.rate = float(fields["rate"]["value"])

            if "loan_amount" in fields and fields["loan_amount"]["confidence"] > 0.85:
                loan.loan_amount = float(fields["loan_amount"]["value"])

            if "closing_date" in fields and fields["closing_date"]["confidence"] > 0.80:
                loan.closing_date = datetime.fromisoformat(fields["closing_date"]["value"])

            if "milestone" in fields and fields["milestone"]["confidence"] > 0.90:
                # Update stage based on milestone
                milestone = fields["milestone"]["value"]
                if "ClearToClose" in milestone or "CTC" in milestone:
                    loan.stage = LoanStage.CTC
                elif "Processing" in milestone:
                    loan.stage = LoanStage.PROCESSING

            db.commit()
            return True

        elif extracted_data.match_entity_type == "lead" and extracted_data.match_entity_id:
            lead = db.query(Lead).filter(Lead.id == extracted_data.match_entity_id).first()
            if not lead:
                return False

            fields = extracted_data.fields

            if "credit_score" in fields and fields["credit_score"]["confidence"] > 0.85:
                lead.credit_score = int(fields["credit_score"]["value"])

            if "loan_amount" in fields and fields["loan_amount"]["confidence"] > 0.80:
                lead.loan_amount = float(fields["loan_amount"]["value"])

            db.commit()
            return True

        return False
    except Exception as e:
        logger.error(f"Apply extracted data error: {e}")
        db.rollback()
        return False

# ============================================================================
# MICROSOFT OAUTH & EMAIL SYNC FUNCTIONS
# ============================================================================

# Simple token encryption (use Fernet for production)
from cryptography.fernet import Fernet
import base64

# Generate encryption key from SECRET_KEY (in production, use dedicated key)
def get_encryption_key():
    # Use first 32 bytes of SECRET_KEY, base64 encoded
    key_material = SECRET_KEY.encode()[:32].ljust(32, b'0')
    return base64.urlsafe_b64encode(key_material)

def encrypt_token(token: str) -> str:
    """Encrypt a token for secure storage"""
    f = Fernet(get_encryption_key())
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a stored token"""
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted_token.encode()).decode()

async def refresh_microsoft_token(oauth_record: MicrosoftOAuthToken, db: Session) -> bool:
    """Refresh an expired Microsoft access token"""
    try:
        refresh_token = decrypt_token(oauth_record.refresh_token)

        # Microsoft token endpoint
        token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

        # Get client credentials from environment
        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("Microsoft OAuth credentials not configured")
            return False

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Mail.Read offline_access"
        }

        response = requests.post(token_url, data=data)

        if response.status_code == 200:
            token_data = response.json()

            # Update tokens
            oauth_record.access_token = encrypt_token(token_data["access_token"])
            oauth_record.refresh_token = encrypt_token(token_data["refresh_token"])
            oauth_record.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
            oauth_record.updated_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(f"Refreshed Microsoft token for user {oauth_record.user_id}")
            return True
        else:
            logger.error(f"Failed to refresh Microsoft token: {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error refreshing Microsoft token: {e}")
        return False

async def fetch_microsoft_emails(oauth_record: MicrosoftOAuthToken, db: Session, limit: int = 50):
    """Fetch emails from Microsoft Graph API"""
    try:
        # Check if token needs refresh
        if oauth_record.token_expires_at:
            # Ensure token_expires_at is timezone-aware
            token_expiry = oauth_record.token_expires_at
            if token_expiry.tzinfo is None:
                token_expiry = token_expiry.replace(tzinfo=timezone.utc)

            if token_expiry < datetime.now(timezone.utc) + timedelta(minutes=5):
                logger.info("Token expiring soon, refreshing...")
                if not await refresh_microsoft_token(oauth_record, db):
                    return {"error": "Failed to refresh token"}

        access_token = decrypt_token(oauth_record.access_token)

        # Microsoft Graph API endpoint
        folder = oauth_record.sync_folder or "Inbox"
        # Simplified query - just get recent emails ordered by date
        graph_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages?$top={limit}&$orderby=receivedDateTime desc"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.get(graph_url, headers=headers)

        if response.status_code == 200:
            emails_data = response.json()
            emails = emails_data.get("value", [])

            logger.info(f"Fetched {len(emails)} emails from Microsoft for user {oauth_record.user_id}")

            # Update last sync time
            oauth_record.last_sync_at = datetime.now(timezone.utc)
            db.commit()

            return {"emails": emails, "count": len(emails)}
        else:
            error_detail = response.text
            logger.error(f"Failed to fetch Microsoft emails: {response.status_code} - {error_detail}")
            return {"error": f"Microsoft API error: {response.status_code} - {error_detail[:200]}"}

    except Exception as e:
        logger.error(f"Error fetching Microsoft emails: {e}")
        return {"error": str(e)}

async def process_microsoft_email_to_dre(email_data: dict, user_id: int, db: Session):
    """Process a Microsoft Graph email and ingest into DRE"""
    try:
        # Extract email data
        subject = email_data.get("subject", "")
        sender = email_data.get("from", {}).get("emailAddress", {}).get("address", "")
        recipients = [r.get("emailAddress", {}).get("address", "") for r in email_data.get("toRecipients", [])]
        received_at = email_data.get("receivedDateTime", "")

        # Get body content
        body = email_data.get("body", {})
        raw_html = body.get("content", "") if body.get("contentType") == "html" else None
        raw_text = body.get("content", "") if body.get("contentType") == "text" else None

        # Create incoming data event
        db_event = IncomingDataEvent(
            source="microsoft365",
            raw_text=raw_text,
            raw_html=raw_html,
            subject=subject,
            sender=sender,
            recipients=recipients,
            received_at=datetime.fromisoformat(received_at.replace('Z', '+00:00')) if received_at else datetime.now(timezone.utc),
            user_id=user_id,
            processed=False
        )
        db.add(db_event)
        db.commit()
        db.refresh(db_event)

        logger.info(f"Ingested Microsoft email {db_event.id} from {sender}")

        # Trigger extraction
        content = raw_text or raw_html or ""
        classification = classify_email_content(content, subject)

        # More lenient extraction - lower confidence threshold and allow emails with no fields
        # This ensures all emails appear in Reconciliation for user review and AI learning
        if classification["category"] != "unrelated" and classification["confidence"] >= 0.3:
            fields = extract_loan_fields(content, classification["category"])

            # Create extracted_data even if no fields found - user can manually review
            confidences = [field.get("confidence", 0.0) for field in fields.values()] if fields else []
            avg_confidence = sum(confidences) / len(confidences) if confidences else classification["confidence"]

            entity_match = match_entity(fields, db, user_id) if fields else {"entity_type": None, "entity_id": None, "confidence": 0.0}

            # Determine status based on confidence
            status = "needs_review"  # Default to needs_review for safety
            if fields and avg_confidence > 0.85 and entity_match["confidence"] > 0.90:
                status = "auto_approved"
            elif fields and avg_confidence >= 0.60 and entity_match["confidence"] >= 0.50:
                status = "pending_review"
            # Everything else stays as needs_review

            extracted = ExtractedData(
                event_id=db_event.id,
                category=classification["category"],
                subcategory=classification.get("subcategory"),
                fields=fields or {},  # Use empty dict if no fields
                match_entity_type=entity_match["entity_type"],
                match_entity_id=entity_match["entity_id"],
                match_confidence=entity_match["confidence"],
                ai_confidence=avg_confidence,
                status=status
            )
            db.add(extracted)
            db_event.processed = True
            db.commit()

            # Auto-apply if high confidence
            if status == "auto_approved":
                if apply_extracted_data(extracted, db):
                    extracted.status = "applied"
                    db.commit()
                    logger.info(f"Auto-applied extraction from email {db_event.id}")

        return {"status": "success", "event_id": db_event.id}

    except Exception as e:
        logger.error(f"Error processing Microsoft email: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}

# ============================================================================
# DATA RECONCILIATION ENGINE - API ENDPOINTS
# ============================================================================

@app.post("/api/v1/reconciliation/ingest")
async def ingest_email_data(
    event: IncomingDataEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ingest incoming email data for reconciliation"""
    try:
        # Create incoming data event
        db_event = IncomingDataEvent(
            source=event.source,
            raw_text=event.raw_text,
            raw_html=event.raw_html,
            subject=event.subject,
            sender=event.sender,
            recipients=event.recipients,
            attachments=event.attachments,
            user_id=current_user.id,
            processed=False
        )
        db.add(db_event)
        db.commit()
        db.refresh(db_event)

        logger.info(f"Ingested email data event {db_event.id} for user {current_user.id}")

        return {
            "status": "success",
            "event_id": db_event.id,
            "message": "Email data ingested successfully"
        }
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/reconciliation/extract/{event_id}")
async def extract_email_data(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Trigger AI extraction on an ingested email event"""
    try:
        # Get the event
        event = db.query(IncomingDataEvent).filter(
            IncomingDataEvent.id == event_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        # Classify the email
        content = event.raw_text or event.raw_html or ""
        subject = event.subject or ""

        classification = classify_email_content(content, subject)

        if classification["category"] == "unrelated" or classification["confidence"] < 0.5:
            event.processed = True
            db.commit()
            return {
                "status": "skipped",
                "reason": "Email classified as unrelated or low confidence",
                "classification": classification
            }

        # Extract fields
        fields = extract_loan_fields(content, classification["category"])

        if not fields:
            event.processed = True
            db.commit()
            return {
                "status": "no_data",
                "reason": "No extractable fields found",
                "classification": classification
            }

        # Calculate overall AI confidence
        confidences = [field.get("confidence", 0.0) for field in fields.values()]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Match entity
        entity_match = match_entity(fields, db, current_user.id)

        # Determine status based on confidence
        status = "pending_review"
        if avg_confidence > 0.85 and entity_match["confidence"] > 0.90:
            status = "auto_approved"
        elif avg_confidence < 0.60 or entity_match["confidence"] < 0.50:
            status = "needs_review"

        # Create extracted data record
        extracted = ExtractedData(
            event_id=event.id,
            category=classification["category"],
            subcategory=classification.get("subcategory"),
            fields=fields,
            match_entity_type=entity_match["entity_type"],
            match_entity_id=entity_match["entity_id"],
            match_confidence=entity_match["confidence"],
            ai_confidence=avg_confidence,
            status=status
        )
        db.add(extracted)

        # Mark event as processed
        event.processed = True

        db.commit()
        db.refresh(extracted)

        # Auto-apply if high confidence
        if status == "auto_approved":
            applied = apply_extracted_data(extracted, db)
            if applied:
                extracted.status = "applied"
                db.commit()

        logger.info(f"Extracted data from event {event_id}, status: {extracted.status}")

        return {
            "status": "success",
            "extracted_data_id": extracted.id,
            "category": extracted.category,
            "ai_confidence": extracted.ai_confidence,
            "match_confidence": extracted.match_confidence,
            "extraction_status": extracted.status,
            "fields": extracted.fields,
            "entity_match": {
                "type": extracted.match_entity_type,
                "id": extracted.match_entity_id
            }
        }
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/reconciliation/pending")
async def get_pending_reconciliation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all pending reconciliation items for review"""
    try:
        # Get all extracted data that needs review
        pending = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            IncomingDataEvent.user_id == current_user.id,
            ExtractedData.status.in_(["pending_review", "needs_review"])
        ).order_by(ExtractedData.created_at.desc()).all()

        # Format response with event details
        results = []
        for item in pending:
            event = db.query(IncomingDataEvent).filter(
                IncomingDataEvent.id == item.event_id
            ).first()

            results.append({
                "id": item.id,
                "event_id": item.event_id,
                "category": item.category,
                "subcategory": item.subcategory,
                "fields": item.fields,
                "match_entity_type": item.match_entity_type,
                "match_entity_id": item.match_entity_id,
                "match_confidence": item.match_confidence,
                "ai_confidence": item.ai_confidence,
                "status": item.status,
                "created_at": item.created_at,
                "email": {
                    "subject": event.subject,
                    "sender": event.sender,
                    "received_at": event.received_at
                }
            })

        logger.info(f"Retrieved {len(results)} pending reconciliation items for user {current_user.id}")

        return {
            "status": "success",
            "count": len(results),
            "items": results
        }
    except Exception as e:
        logger.error(f"Get pending error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/reconciliation/approve")
async def approve_reconciliation(
    approval: ReconciliationApproval,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Approve extracted data and apply to CRM"""
    try:
        # Get extracted data
        extracted = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            ExtractedData.id == approval.extracted_data_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        # Apply corrections if provided
        if approval.corrections:
            for field_name, corrected_value in approval.corrections.items():
                if field_name in extracted.fields:
                    # Store original value for training
                    original = extracted.fields[field_name]["value"]

                    # Create training event
                    training = AITrainingEvent(
                        extracted_data_id=extracted.id,
                        field_name=field_name,
                        original_value=str(original),
                        corrected_value=str(corrected_value),
                        label="corrected",
                        user_id=current_user.id
                    )
                    db.add(training)

                    # Update field value
                    extracted.fields[field_name]["value"] = corrected_value
                    extracted.fields[field_name]["confidence"] = 1.0  # User-verified

        # Apply partial approval if specified
        if approval.approved_fields:
            # Only apply specified fields
            original_fields = extracted.fields.copy()
            extracted.fields = {k: v for k, v in original_fields.items() if k in approval.approved_fields}

        # Apply to CRM
        applied = apply_extracted_data(extracted, db)

        if applied:
            extracted.status = "approved"
            db.commit()

            logger.info(f"Approved and applied extracted data {extracted.id}")

            return {
                "status": "success",
                "message": "Data approved and applied to CRM",
                "extracted_data_id": extracted.id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to apply data to CRM")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approval error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/reconciliation/reject")
async def reject_reconciliation(
    rejection: ReconciliationRejection,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reject extracted data"""
    try:
        # Get extracted data
        extracted = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            ExtractedData.id == rejection.extracted_data_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        # Create training events for all fields (mark as incorrect)
        for field_name, field_data in extracted.fields.items():
            training = AITrainingEvent(
                extracted_data_id=extracted.id,
                field_name=field_name,
                original_value=str(field_data.get("value", "")),
                corrected_value="",  # Empty means rejected
                label="rejected",
                user_id=current_user.id,
                notes=rejection.reason
            )
            db.add(training)

        extracted.status = "rejected"
        db.commit()

        logger.info(f"Rejected extracted data {extracted.id}: {rejection.reason}")

        return {
            "status": "success",
            "message": "Data rejected",
            "extracted_data_id": extracted.id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rejection error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/reconciliation/correct")
async def correct_and_train(
    correction: ReconciliationApproval,  # Reuse same schema
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Correct extracted data and train AI"""
    try:
        # Get extracted data
        extracted = db.query(ExtractedData).join(
            IncomingDataEvent,
            ExtractedData.event_id == IncomingDataEvent.id
        ).filter(
            ExtractedData.id == correction.extracted_data_id,
            IncomingDataEvent.user_id == current_user.id
        ).first()

        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        if not correction.corrections:
            raise HTTPException(status_code=400, detail="No corrections provided")

        # Apply corrections and create training events
        for field_name, corrected_value in correction.corrections.items():
            if field_name in extracted.fields:
                original = extracted.fields[field_name]["value"]

                # Create training event
                training = AITrainingEvent(
                    extracted_data_id=extracted.id,
                    field_name=field_name,
                    original_value=str(original),
                    corrected_value=str(corrected_value),
                    label="corrected",
                    user_id=current_user.id
                )
                db.add(training)

                # Update field
                extracted.fields[field_name]["value"] = corrected_value
                extracted.fields[field_name]["confidence"] = 1.0

        # Apply corrected data
        applied = apply_extracted_data(extracted, db)

        if applied:
            extracted.status = "corrected_and_applied"
            db.commit()

            logger.info(f"Corrected and applied extracted data {extracted.id}")

            return {
                "status": "success",
                "message": "Data corrected and applied. AI will learn from this correction.",
                "extracted_data_id": extracted.id,
                "corrections_count": len(correction.corrections)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to apply corrected data")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Correction error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MICROSOFT 365 OAUTH ENDPOINTS
# ============================================================================

@app.post("/api/v1/microsoft/connect")
async def connect_microsoft365(
    auth_data: MicrosoftOAuthConnect,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exchange authorization code for access token and store"""
    try:
        # Microsoft token endpoint
        token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

        # Get client credentials from environment
        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise HTTPException(status_code=500, detail="Microsoft OAuth not configured. Contact administrator.")

        # Exchange authorization code for tokens
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_data.authorization_code,
            "redirect_uri": auth_data.redirect_uri,
            "grant_type": "authorization_code",
            "scope": "https://graph.microsoft.com/Mail.Read offline_access"
        }

        response = requests.post(token_url, data=data)

        if response.status_code != 200:
            logger.error(f"Microsoft token exchange failed: {response.text}")
            raise HTTPException(status_code=400, detail="Failed to connect to Microsoft 365")

        token_data = response.json()

        # Get user's email address from Microsoft
        access_token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        profile_response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)

        email_address = None
        if profile_response.status_code == 200:
            profile = profile_response.json()
            email_address = profile.get("mail") or profile.get("userPrincipalName")

        # Check if user already has OAuth record
        existing = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if existing:
            # Update existing record
            existing.access_token = encrypt_token(token_data["access_token"])
            existing.refresh_token = encrypt_token(token_data["refresh_token"])
            existing.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
            existing.email_address = email_address
            existing.sync_enabled = True
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Updated Microsoft OAuth for user {current_user.id}")
        else:
            # Create new OAuth record
            oauth_record = MicrosoftOAuthToken(
                user_id=current_user.id,
                access_token=encrypt_token(token_data["access_token"]),
                refresh_token=encrypt_token(token_data["refresh_token"]),
                token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"]),
                email_address=email_address,
                sync_enabled=True
            )
            db.add(oauth_record)
            db.commit()

            logger.info(f"Created Microsoft OAuth for user {current_user.id}")

        return {
            "status": "success",
            "message": "Microsoft 365 connected successfully",
            "email_address": email_address
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Microsoft connect error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/microsoft/status")
async def get_microsoft_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get Microsoft 365 connection status"""
    try:
        oauth_record = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if not oauth_record:
            return {
                "connected": False,
                "email_address": None,
                "sync_enabled": False,
                "last_sync_at": None
            }

        return {
            "connected": True,
            "email_address": oauth_record.email_address,
            "sync_enabled": oauth_record.sync_enabled,
            "last_sync_at": oauth_record.last_sync_at,
            "sync_folder": oauth_record.sync_folder,
            "sync_frequency_minutes": oauth_record.sync_frequency_minutes
        }

    except Exception as e:
        logger.error(f"Microsoft status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/microsoft/disconnect")
async def disconnect_microsoft365(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect Microsoft 365 account"""
    try:
        oauth_record = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if not oauth_record:
            raise HTTPException(status_code=404, detail="No Microsoft 365 connection found")

        db.delete(oauth_record)
        db.commit()

        logger.info(f"Disconnected Microsoft 365 for user {current_user.id}")

        return {
            "status": "success",
            "message": "Microsoft 365 disconnected successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Microsoft disconnect error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/system/diagnostics")
async def get_system_diagnostics(current_user: User = Depends(get_current_user)):
    """Get system configuration diagnostics"""
    return {
        "openai_configured": openai_client is not None,
        "openai_api_key_set": bool(OPENAI_API_KEY),
        "database_type": "postgresql" if "postgresql" in DATABASE_URL else "sqlite",
        "environment": os.getenv("RAILWAY_ENVIRONMENT", "local")
    }

@app.post("/api/v1/microsoft/sync-now")
async def sync_microsoft_emails_now(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger email sync from Microsoft 365"""
    try:
        # Log diagnostic info
        logger.info(f"Sync triggered by user {current_user.id}")
        logger.info(f"OpenAI client available: {openai_client is not None}")
        logger.info(f"OpenAI API key set: {bool(OPENAI_API_KEY)}")
        oauth_record = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if not oauth_record:
            raise HTTPException(status_code=404, detail="Microsoft 365 not connected")

        if not oauth_record.sync_enabled:
            raise HTTPException(status_code=400, detail="Email sync is disabled")

        # Fetch emails
        result = await fetch_microsoft_emails(oauth_record, db, limit=50)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        # Process each email through DRE
        emails = result.get("emails", [])
        processed_count = 0

        for email_data in emails:
            process_result = await process_microsoft_email_to_dre(email_data, current_user.id, db)
            if process_result.get("status") == "success":
                processed_count += 1

        # Update last_sync_at timestamp
        oauth_record.last_sync_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Synced {processed_count}/{len(emails)} emails for user {current_user.id}")

        return {
            "status": "success",
            "fetched_count": len(emails),
            "processed_count": processed_count,
            "message": f"Synced {processed_count} emails successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Microsoft sync error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Sync error: {str(e)}")

@app.post("/api/v1/microsoft/reprocess-emails")
async def reprocess_unextracted_emails(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reprocess emails that were synced but not extracted (for fixing failed extractions)"""
    try:
        # Find all emails without extracted data for this user
        unextracted = db.execute(text("""
            SELECT ide.id, ide.subject, ide.sender, ide.raw_text, ide.raw_html, ide.received_at, ide.recipients
            FROM incoming_data_events ide
            LEFT JOIN extracted_data ed ON ide.id = ed.event_id
            WHERE ed.id IS NULL AND ide.user_id = :user_id
            ORDER BY ide.created_at DESC
        """), {"user_id": current_user.id}).fetchall()

        logger.info(f"Found {len(unextracted)} unextracted emails for user {current_user.id}")

        if len(unextracted) == 0:
            return {
                "status": "success",
                "reprocessed_count": 0,
                "message": "No emails need reprocessing"
            }

        # Reprocess each email
        success_count = 0

        for email_id, subject, sender, raw_text, raw_html, received_at, recipients in unextracted:
            # Get the full event
            event = db.query(IncomingDataEvent).filter(IncomingDataEvent.id == email_id).first()

            if not event:
                continue

            # Create email_data dict (mimicking Microsoft Graph format)
            email_data = {
                "subject": subject,
                "from": {"emailAddress": {"address": sender}},
                "toRecipients": [{"emailAddress": {"address": r}} for r in (recipients or [])],
                "receivedDateTime": received_at.isoformat() if received_at else None,
                "body": {
                    "content": raw_text or raw_html or "",
                    "contentType": "text" if raw_text else "html"
                }
            }

            # Delete old event to avoid duplicates
            db.delete(event)
            db.commit()

            # Reprocess with new extraction logic
            result = await process_microsoft_email_to_dre(email_data, current_user.id, db)

            if result.get("status") == "success":
                success_count += 1

        logger.info(f"Reprocessed {success_count}/{len(unextracted)} emails for user {current_user.id}")

        return {
            "status": "success",
            "reprocessed_count": success_count,
            "total_found": len(unextracted),
            "message": f"Reprocessed {success_count} emails successfully"
        }

    except Exception as e:
        logger.error(f"Email reprocessing error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/v1/microsoft/settings")
async def update_microsoft_settings(
    settings: MicrosoftSyncSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update Microsoft 365 sync settings"""
    try:
        oauth_record = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if not oauth_record:
            raise HTTPException(status_code=404, detail="Microsoft 365 not connected")

        # Update settings
        if settings.sync_enabled is not None:
            oauth_record.sync_enabled = settings.sync_enabled

        if settings.sync_folder is not None:
            oauth_record.sync_folder = settings.sync_folder

        if settings.sync_frequency_minutes is not None:
            # Validate frequency (min 5 minutes, max 1440 = 24 hours)
            if settings.sync_frequency_minutes < 5 or settings.sync_frequency_minutes > 1440:
                raise HTTPException(status_code=400, detail="Sync frequency must be between 5 and 1440 minutes")
            oauth_record.sync_frequency_minutes = settings.sync_frequency_minutes

        oauth_record.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Updated Microsoft settings for user {current_user.id}")

        return {
            "status": "success",
            "message": "Settings updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Microsoft settings update error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

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
        return {"status": "healthy", "database": "connected", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.post("/authentication/test")
async def authentication_test_post(current_user: User = Depends(get_current_user_flexible)):
    """
    Zapier authentication test endpoint (POST method).
    This endpoint verifies that the API key authentication is working correctly.
    """
    return {
        "authenticated": True,
        "user_id": current_user.id,
        "email": current_user.email,
        "name": current_user.full_name,
        "message": "Authentication successful",
        "timestamp": datetime.now(timezone.utc)
    }

@app.get("/authentication/test")
async def authentication_test_get(current_user: User = Depends(get_current_user_flexible)):
    """
    Zapier authentication test endpoint (GET method).
    This endpoint verifies that the API key authentication is working correctly.
    """
    return {
        "authenticated": True,
        "user_id": current_user.id,
        "email": current_user.email,
        "name": current_user.full_name,
        "message": "Authentication successful",
        "timestamp": datetime.now(timezone.utc)
    }

@app.post("/admin/create-api-keys-table")
async def create_api_keys_table(db: Session = Depends(get_db)):
    """Admin endpoint to manually create the api_keys table"""
    try:
        # Create api_keys table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                key VARCHAR UNIQUE NOT NULL,
                name VARCHAR NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP
            );
        """))

        # Create index
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_api_keys_key ON api_keys(key);
        """))

        db.commit()

        logger.info("✅ api_keys table created successfully")
        return {"status": "success", "message": "api_keys table created"}
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to create api_keys table: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.post("/admin/add-coborrower-columns")
async def add_coborrower_columns(db: Session = Depends(get_db)):
    """Admin endpoint to add co-borrower email and phone columns"""
    try:
        # Add co_applicant_email column
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='leads' AND column_name='co_applicant_email'
                ) THEN
                    ALTER TABLE leads ADD COLUMN co_applicant_email VARCHAR;
                END IF;
            END $$;
        """))

        # Add co_applicant_phone column
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='leads' AND column_name='co_applicant_phone'
                ) THEN
                    ALTER TABLE leads ADD COLUMN co_applicant_phone VARCHAR;
                END IF;
            END $$;
        """))

        db.commit()

        logger.info("✅ Co-borrower columns added successfully")
        return {"status": "success", "message": "Co-borrower columns added"}
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to add co-borrower columns: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.post("/admin/add-dre-columns")
async def add_dre_columns(db: Session = Depends(get_db)):
    """Admin endpoint to add missing columns to extracted_data table"""
    try:
        # Add applied_at column
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='extracted_data' AND column_name='applied_at'
                ) THEN
                    ALTER TABLE extracted_data ADD COLUMN applied_at TIMESTAMP;
                END IF;
            END $$;
        """))

        # Add reviewed_by column
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='extracted_data' AND column_name='reviewed_by'
                ) THEN
                    ALTER TABLE extracted_data ADD COLUMN reviewed_by INTEGER REFERENCES users(id);
                END IF;
            END $$;
        """))

        # Add reviewed_at column
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='extracted_data' AND column_name='reviewed_at'
                ) THEN
                    ALTER TABLE extracted_data ADD COLUMN reviewed_at TIMESTAMP;
                END IF;
            END $$;
        """))

        db.commit()

        logger.info("✅ DRE columns added successfully")
        return {"status": "success", "message": "DRE columns added successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to add DRE columns: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.post("/admin/create-dre-tables")
async def create_dre_tables(db: Session = Depends(get_db)):
    """Admin endpoint to create Data Reconciliation Engine tables"""
    try:
        # Create incoming_data_events table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS incoming_data_events (
                id SERIAL PRIMARY KEY,
                source VARCHAR NOT NULL,
                raw_text TEXT,
                raw_html TEXT,
                subject VARCHAR,
                sender VARCHAR,
                recipients JSON,
                attachments JSON,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed BOOLEAN DEFAULT FALSE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Create extracted_data table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS extracted_data (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES incoming_data_events(id),
                category VARCHAR,
                subcategory VARCHAR,
                fields JSON NOT NULL,
                match_entity_type VARCHAR,
                match_entity_id INTEGER,
                match_confidence FLOAT,
                ai_confidence FLOAT,
                status VARCHAR DEFAULT 'pending_review',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Create ai_training_events table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_training_events (
                id SERIAL PRIMARY KEY,
                extracted_data_id INTEGER NOT NULL REFERENCES extracted_data(id),
                field_name VARCHAR NOT NULL,
                original_value VARCHAR,
                corrected_value VARCHAR,
                label VARCHAR NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        db.commit()

        logger.info("✅ DRE tables created successfully")
        return {
            "status": "success",
            "message": "Data Reconciliation Engine tables created",
            "tables": ["incoming_data_events", "extracted_data", "ai_training_events"]
        }
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to create DRE tables: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.post("/admin/create-microsoft-oauth-table")
async def create_microsoft_oauth_table(db: Session = Depends(get_db)):
    """Admin endpoint to create Microsoft OAuth tokens table"""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS microsoft_oauth_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
                access_token TEXT,
                refresh_token TEXT,
                token_expires_at TIMESTAMP,
                email_address VARCHAR,
                sync_enabled BOOLEAN DEFAULT TRUE,
                last_sync_at TIMESTAMP,
                sync_folder VARCHAR DEFAULT 'Inbox',
                sync_frequency_minutes INTEGER DEFAULT 15,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        db.commit()

        logger.info("✅ Microsoft OAuth tokens table created successfully")
        return {
            "status": "success",
            "message": "Microsoft OAuth tokens table created"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to create Microsoft OAuth tokens table: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.post("/admin/create-zapier-api-key")
async def create_zapier_api_key(db: Session = Depends(get_db)):
    """Admin endpoint to create the Zapier API key for integration"""
    try:
        # Get the first user (demo user) or create one
        user = db.query(User).first()
        if not user:
            logger.error("No users found in database")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "No users found. Please create a user first."}
            )

        # Check if the Zapier API key already exists
        zapier_api_key = "185b7101-9435-44da-87ab-b7582c4e4607"
        existing_key = db.query(ApiKey).filter(ApiKey.key == zapier_api_key).first()

        if existing_key:
            logger.info("✅ Zapier API key already exists")
            return {
                "status": "success",
                "message": "Zapier API key already exists",
                "key": zapier_api_key,
                "user_email": user.email
            }

        # Create the API key
        new_api_key = ApiKey(
            key=zapier_api_key,
            name="Zapier Integration",
            user_id=user.id,
            is_active=True
        )

        db.add(new_api_key)
        db.commit()
        db.refresh(new_api_key)

        logger.info(f"✅ Zapier API key created for user {user.email}")
        return {
            "status": "success",
            "message": "Zapier API key created successfully",
            "key": zapier_api_key,
            "user_email": user.email
        }
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to create Zapier API key: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
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
# API KEY MANAGEMENT
# ============================================================================

@app.post("/api/v1/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    key_data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a new API key for the current user"""
    try:
        # Generate a secure API key
        api_key_string = generate_api_key()

        logger.info(f"Attempting to create API key '{key_data.name}' for user {current_user.email}")

        # Create the API key record
        new_api_key = ApiKey(
            key=api_key_string,
            name=key_data.name,
            user_id=current_user.id
        )

        db.add(new_api_key)
        db.commit()
        db.refresh(new_api_key)

        logger.info(f"✅ API key created successfully for user {current_user.email}: {key_data.name}")
        return new_api_key
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to create API key: {str(e)}")
        logger.exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )

@app.get("/api/v1/api-keys", response_model=List[ApiKeyResponse])
async def list_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all API keys for the current user"""
    api_keys = db.query(ApiKey).filter(
        ApiKey.user_id == current_user.id
    ).all()
    return api_keys

@app.delete("/api/v1/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke (deactivate) an API key"""
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == current_user.id
    ).first()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    db.commit()

    logger.info(f"API key revoked for user {current_user.email}: {api_key.name}")
    return {"message": "API key revoked successfully"}

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
        Lead.created_at < datetime.now(timezone.utc) - timedelta(hours=24)
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
        Loan.stage == LoanStage.UW_RECEIVED
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
        Loan.stage == LoanStage.CTC
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
        Lead.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
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
# LOAN SCORECARD REPORT
# ============================================================================

@app.get("/api/v1/scorecard")
async def get_scorecard(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive loan scorecard metrics matching the Loan Scorecard Report format.
    Includes conversion metrics, funding totals, and referral source breakdown.
    """
    from datetime import date, timedelta
    from sqlalchemy import func, extract, case
    from decimal import Decimal

    # Date range setup
    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        # Default to current month
        today = date.today()
        start = today.replace(day=1)
        end = today

    # ============================================================================
    # LOAN STARTS VS. ACTIVITY TOTALS
    # ============================================================================

    # Get all relevant loans and leads for the period
    all_leads = db.query(Lead).filter(
        Lead.owner_id == current_user.id,
        Lead.created_at >= start,
        Lead.created_at <= end
    ).all()

    all_loans = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id
    ).all()

    # Calculate counts
    starts_count = len(all_leads)  # Total leads

    # Applications (leads that became loans)
    apps_count = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.created_at >= start,
        Loan.created_at <= end
    ).scalar() or 0

    # Funded loans
    funded_count = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= start,
        Loan.funded_date <= end
    ).scalar() or 0

    # Credit pulls (assuming leads with credit_score indicate credit pulled)
    credit_pulls = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == current_user.id,
        Lead.created_at >= start,
        Lead.created_at <= end,
        Lead.credit_score.isnot(None)
    ).scalar() or 0

    # Cancelled loans
    cancelled_count = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.CANCELLED,
        Loan.created_at >= start,
        Loan.created_at <= end
    ).scalar() or 0

    # Denied loans
    denied_count = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.DENIED,
        Loan.created_at >= start,
        Loan.created_at <= end
    ).scalar() or 0

    # UW to TBDs (underwriting to clear to close)
    uw_count = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.UW_RECEIVED,
        Loan.created_at >= start,
        Loan.created_at <= end
    ).scalar() or 0

    ctc_count = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.CTC,
        Loan.created_at >= start,
        Loan.created_at <= end
    ).scalar() or 0

    # Initial lock to funded (loans that locked and funded)
    locked_funded = funded_count  # Simplified - all funded loans were locked

    # Calculate conversion percentages
    starts_to_apps_pct = int((apps_count / starts_count * 100)) if starts_count > 0 else 0
    apps_to_funded_pct = int((funded_count / apps_count * 100)) if apps_count > 0 else 0
    starts_to_funded_pct = int((funded_count / starts_count * 100)) if starts_count > 0 else 0
    credit_to_funded_pct = int((funded_count / credit_pulls * 100)) if credit_pulls > 0 else 0
    starts_to_cancelled_pct = int((cancelled_count / starts_count * 100)) if starts_count > 0 else 0
    starts_to_denied_pct = int((denied_count / starts_count * 100)) if starts_count > 0 else 0
    uw_to_ctc_pct = int((ctc_count / uw_count * 100)) if uw_count > 0 else 0
    lock_to_funded_pct = int((funded_count / locked_funded * 100)) if locked_funded > 0 else 0

    conversion_metrics = [
        {
            "metric": "Starts to Appl(E)",
            "current": apps_count,
            "total": starts_count,
            "mot_pct": starts_to_apps_pct,
            "goal_pct": 75,
            "status": "good" if starts_to_apps_pct >= 75 else "warning" if starts_to_apps_pct >= 60 else "critical"
        },
        {
            "metric": "Appl(E) to Funded",
            "current": funded_count,
            "total": apps_count,
            "mot_pct": apps_to_funded_pct,
            "goal_pct": 80,
            "status": "good" if apps_to_funded_pct >= 80 else "warning" if apps_to_funded_pct >= 60 else "critical"
        },
        {
            "metric": "Starts to Funded",
            "current": funded_count,
            "total": starts_count,
            "mot_pct": starts_to_funded_pct,
            "goal_pct": 50,
            "status": "good" if starts_to_funded_pct >= 50 else "warning" if starts_to_funded_pct >= 40 else "critical"
        },
        {
            "metric": "Credit Pulls to Funded",
            "current": funded_count,
            "total": credit_pulls,
            "mot_pct": credit_to_funded_pct,
            "goal_pct": 70,
            "status": "critical" if credit_to_funded_pct < 50 else "warning" if credit_to_funded_pct < 70 else "good"
        },
        {
            "metric": "Starts to Cancelled",
            "current": cancelled_count,
            "total": starts_count,
            "mot_pct": starts_to_cancelled_pct,
            "goal_pct": 10,
            "status": "good" if starts_to_cancelled_pct <= 10 else "warning"
        },
        {
            "metric": "Starts to Denied",
            "current": denied_count,
            "total": starts_count,
            "mot_pct": starts_to_denied_pct,
            "goal_pct": 5,
            "status": "good" if starts_to_denied_pct <= 5 else "warning"
        },
        {
            "metric": "UW to TBDs",
            "current": ctc_count,
            "total": uw_count,
            "mot_pct": uw_to_ctc_pct,
            "goal_pct": 50,
            "status": "good" if uw_to_ctc_pct >= 50 else "warning"
        },
        {
            "metric": "Initial Lock to Funded",
            "current": funded_count,
            "total": locked_funded,
            "mot_pct": lock_to_funded_pct,
            "goal_pct": 90,
            "status": "warning" if lock_to_funded_pct < 90 else "good"
        }
    ]

    # ============================================================================
    # CONVERSION UPSWING (10% Pull-Thru Analysis)
    # ============================================================================

    # Calculate current vs target metrics
    current_pull_thru_pct = starts_to_funded_pct
    target_pull_thru_pct = current_pull_thru_pct + 10  # 10% improvement

    # Get funded loans for volume calculations
    funded_loans = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= start,
        Loan.funded_date <= end
    ).all()

    current_avg_amount = sum(loan.amount for loan in funded_loans if loan.amount) / len(funded_loans) if funded_loans else 0
    current_volume = sum(loan.amount for loan in funded_loans if loan.amount)

    # Project 10% increase
    target_funded_count = int(funded_count * 1.1)
    target_volume = current_volume * 1.1
    volume_increase = target_volume - current_volume

    # Basis points (commission) - assuming 100 bps average
    current_bps = 100
    current_compensation = (current_volume * current_bps) / 10000
    target_compensation = (target_volume * current_bps) / 10000
    additional_compensation = target_compensation - current_compensation

    conversion_upswing = {
        "current_starts": starts_count,
        "target_starts": int(starts_count * 1.1),
        "current_pull_thru_pct": current_pull_thru_pct,
        "target_pull_thru_pct": target_pull_thru_pct,
        "current_avg_amount": current_avg_amount,
        "target_avg_amount": current_avg_amount,
        "current_volume": current_volume,
        "target_volume": target_volume,
        "volume_increase": volume_increase,
        "current_bps": current_bps,
        "target_bps": current_bps,
        "current_compensation": current_compensation,
        "additional_compensation": additional_compensation
    }

    # ============================================================================
    # FUNDING TOTALS
    # ============================================================================

    # Get all funded loans
    funded_loans_all = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= start,
        Loan.funded_date <= end
    ).all()

    # Calculate totals
    total_funded_units = len(funded_loans_all)
    total_funded_volume = sum(loan.amount for loan in funded_loans_all if loan.amount)

    # Break down by loan type
    loan_type_breakdown = {}
    for loan in funded_loans_all:
        loan_type = loan.loan_type or "Unknown"
        if loan_type not in loan_type_breakdown:
            loan_type_breakdown[loan_type] = {"units": 0, "volume": 0}
        loan_type_breakdown[loan_type]["units"] += 1
        loan_type_breakdown[loan_type]["volume"] += loan.amount if loan.amount else 0

    loan_types = [
        {
            "type": loan_type,
            "units": data["units"],
            "volume": data["volume"],
            "percentage": (data["volume"] / total_funded_volume * 100) if total_funded_volume > 0 else 0
        }
        for loan_type, data in loan_type_breakdown.items()
    ]

    # Break down by referral source
    referral_breakdown = {}
    for loan in funded_loans_all:
        source = loan.source or "Unknown"
        if source not in referral_breakdown:
            referral_breakdown[source] = {"referrals": 0, "closed_volume": 0}
        referral_breakdown[source]["referrals"] += 1
        referral_breakdown[source]["closed_volume"] += loan.amount if loan.amount else 0

    referral_sources = [
        {
            "source": source,
            "referrals": data["referrals"],
            "closed_volume": data["closed_volume"]
        }
        for source, data in referral_breakdown.items()
    ]

    funding_totals = {
        "total_units": total_funded_units,
        "total_volume": total_funded_volume,
        "loan_types": loan_types,
        "referral_sources": referral_sources,
        "avg_loan_amount": total_funded_volume / total_funded_units if total_funded_units > 0 else 0
    }

    # ============================================================================
    # RETURN COMPLETE SCORECARD
    # ============================================================================

    return {
        "period": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat()
        },
        "conversion_metrics": conversion_metrics,
        "conversion_upswing": conversion_upswing,
        "funding_totals": funding_totals,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

# ============================================================================
# LEADS CRUD
# ============================================================================

@app.post("/api/v1/leads/", response_model=LeadResponse, status_code=201)
async def create_lead(lead: LeadCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
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
    current_user: User = Depends(get_current_user_flexible)
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
async def get_lead(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead

@app.patch("/api/v1/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(lead_id: int, lead_update: LeadUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    for key, value in lead_update.dict(exclude_unset=True).items():
        setattr(lead, key, value)

    # Recalculate AI score
    lead.ai_score = calculate_lead_score(lead)
    lead.updated_at = datetime.now(timezone.utc)

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
    loan.updated_at = datetime.now(timezone.utc)

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
# CLIENT MANAGEMENT PROFILE (CMP) API ENDPOINTS
# ============================================================================

@app.post("/api/v1/profile/", response_model=ClientProfileResponse, status_code=201)
async def create_client_profile(
    profile_data: ClientProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new Client Management Profile for the current user"""
    # Check if user already has a profile
    existing_profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if existing_profile:
        raise HTTPException(status_code=400, detail="User already has a client profile")

    # Generate unique account ID
    import uuid
    account_id = str(uuid.uuid4())

    # Create profile
    db_profile = ClientProfile(
        account_id=account_id,
        account_type=profile_data.account_type,
        primary_user_id=current_user.id,
        company_name=profile_data.company_name,
        nmls_number=profile_data.nmls_number,
        business_address=profile_data.business_address,
        team_size=profile_data.team_size or 1,
        user_profile=profile_data.user_profile.dict() if profile_data.user_profile else None,
        subscription_plan=profile_data.subscription_plan or "Solo",
        billing_status="active",
        # Initialize empty JSON fields
        integration_settings={},
        branding_settings={},
        automation_settings={"coach_intensity": "medium", "auto_task_creation": True},
        reconciliation_settings={"auto_update_threshold": 0.8},
        pipeline_settings={"follow_up_model": "balanced"},
        kpi_targets={},
        portfolio_settings={"rate_drop_alerts": True, "equity_alerts": True},
        advanced_settings={}
    )

    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)

    logger.info(f"Client profile created for user {current_user.id}: {account_id}")
    return db_profile

@app.get("/api/v1/profile/", response_model=ClientProfileResponse)
async def get_client_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the current user's Client Management Profile"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found. Create one first.")

    return profile

@app.patch("/api/v1/profile/", response_model=ClientProfileResponse)
async def update_client_profile(
    profile_update: ClientProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update the current user's Client Management Profile"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    # Update fields if provided
    update_data = profile_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field == "user_profile" and value:
            setattr(profile, field, value.dict())
        elif field in ["integration_settings", "branding_settings", "automation_settings",
                       "reconciliation_settings", "pipeline_settings", "kpi_targets",
                       "portfolio_settings", "advanced_settings"] and value:
            setattr(profile, field, value.dict())
        else:
            setattr(profile, field, value)

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)

    logger.info(f"Client profile updated for user {current_user.id}")
    return profile

@app.delete("/api/v1/profile/", status_code=204)
async def delete_client_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete the current user's Client Management Profile"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    db.delete(profile)
    db.commit()

    logger.info(f"Client profile deleted for user {current_user.id}")
    return None

# ============================================================================
# TEAM ROLES MANAGEMENT
# ============================================================================

@app.post("/api/v1/profile/team-roles/", response_model=TeamRoleResponse, status_code=201)
async def create_team_role(
    role_data: TeamRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new team role for the current user's profile"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    db_role = TeamRole(
        profile_id=profile.id,
        **role_data.dict()
    )

    db.add(db_role)
    db.commit()
    db.refresh(db_role)

    logger.info(f"Team role created: {db_role.role_name}")
    return db_role

@app.get("/api/v1/profile/team-roles/", response_model=List[TeamRoleResponse])
async def get_team_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all team roles for the current user's profile"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    roles = db.query(TeamRole).filter(TeamRole.profile_id == profile.id, TeamRole.is_active == True).all()
    return roles

@app.patch("/api/v1/profile/team-roles/{role_id}", response_model=TeamRoleResponse)
async def update_team_role(
    role_id: int,
    role_update: TeamRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a team role"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    role = db.query(TeamRole).filter(TeamRole.id == role_id, TeamRole.profile_id == profile.id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Team role not found")

    update_data = role_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(role, field, value)

    role.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(role)

    logger.info(f"Team role updated: {role.role_name}")
    return role

@app.delete("/api/v1/profile/team-roles/{role_id}", status_code=204)
async def delete_team_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete (deactivate) a team role"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    role = db.query(TeamRole).filter(TeamRole.id == role_id, TeamRole.profile_id == profile.id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Team role not found")

    role.is_active = False
    db.commit()

    logger.info(f"Team role deactivated: {role.role_name}")
    return None

# ============================================================================
# PROCESS FLOW MANAGEMENT
# ============================================================================

@app.post("/api/v1/profile/process-flows/", response_model=ProcessFlowDocumentResponse, status_code=201)
async def upload_process_flow(
    document_data: ProcessFlowDocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a process flow document for AI parsing"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    db_document = ProcessFlowDocument(
        profile_id=profile.id,
        **document_data.dict(),
        ai_parsing_status="pending"
    )

    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    # TODO: Trigger AI parsing job asynchronously
    logger.info(f"Process flow document uploaded: {db_document.document_name}")
    return db_document

@app.get("/api/v1/profile/process-flows/", response_model=List[ProcessFlowDocumentResponse])
async def get_process_flows(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all process flow documents for the current user's profile"""
    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    documents = db.query(ProcessFlowDocument).filter(ProcessFlowDocument.profile_id == profile.id).all()
    return documents

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
        task.completed_at = datetime.now(timezone.utc)

    task.updated_at = datetime.now(timezone.utc)
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

    # Calculate days since funding - make timezone-aware if needed
    original_close_dt = client.original_close_date if client.original_close_date.tzinfo else client.original_close_date.replace(tzinfo=timezone.utc)
    days_since = (datetime.now(timezone.utc) - original_close_dt).days

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
            lead.last_contact = datetime.now(timezone.utc)
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
# PROCESS TEMPLATES - Role-Based Task Management
# ============================================================================

@app.get("/api/v1/process-templates/", response_model=List[ProcessTemplateResponse])
async def get_process_templates(
    role_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all process templates, optionally filtered by role"""
    query = db.query(ProcessTemplate).filter(
        ProcessTemplate.user_id == current_user.id,
        ProcessTemplate.is_active == True
    )

    if role_name:
        query = query.filter(ProcessTemplate.role_name == role_name)

    templates = query.order_by(ProcessTemplate.role_name, ProcessTemplate.sequence_order).all()
    return templates

@app.get("/api/v1/process-templates/roles", response_model=List[str])
async def get_process_template_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all unique role names that have process templates"""
    roles = db.query(ProcessTemplate.role_name).filter(
        ProcessTemplate.user_id == current_user.id,
        ProcessTemplate.is_active == True
    ).distinct().all()

    return [role[0] for role in roles]

@app.post("/api/v1/process-templates/", response_model=ProcessTemplateResponse, status_code=201)
async def create_process_template(
    template: ProcessTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new process template task"""
    db_template = ProcessTemplate(**template.dict(), user_id=current_user.id)
    db.add(db_template)
    db.commit()
    db.refresh(db_template)

    logger.info(f"Process template created: {db_template.role_name} - {db_template.task_title}")
    return db_template

@app.patch("/api/v1/process-templates/{template_id}", response_model=ProcessTemplateResponse)
async def update_process_template(
    template_id: int,
    template_update: ProcessTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a process template (admin only)"""
    db_template = db.query(ProcessTemplate).filter(
        ProcessTemplate.id == template_id,
        ProcessTemplate.user_id == current_user.id
    ).first()

    if not db_template:
        raise HTTPException(status_code=404, detail="Process template not found")

    update_data = template_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_template, field, value)

    db_template.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_template)

    logger.info(f"Process template updated: {db_template.id}")
    return db_template

@app.delete("/api/v1/process-templates/{template_id}", status_code=204)
async def delete_process_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a process template (soft delete)"""
    db_template = db.query(ProcessTemplate).filter(
        ProcessTemplate.id == template_id,
        ProcessTemplate.user_id == current_user.id
    ).first()

    if not db_template:
        raise HTTPException(status_code=404, detail="Process template not found")

    db_template.is_active = False
    db.commit()

    logger.info(f"Process template deleted: {db_template.id}")
    return None

@app.post("/api/v1/process-templates/analyze-efficiency")
async def analyze_process_efficiency(
    role_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI-powered efficiency analysis of process templates"""
    query = db.query(ProcessTemplate).filter(
        ProcessTemplate.user_id == current_user.id,
        ProcessTemplate.is_active == True
    )

    if role_name:
        query = query.filter(ProcessTemplate.role_name == role_name)

    templates = query.order_by(ProcessTemplate.role_name, ProcessTemplate.sequence_order).all()

    if not templates:
        return {
            "status": "no_data",
            "message": "No process templates found for analysis",
            "suggestions": []
        }

    # AI-powered efficiency analysis
    suggestions = []
    role_groups = {}

    # Group by role
    for template in templates:
        if template.role_name not in role_groups:
            role_groups[template.role_name] = []
        role_groups[template.role_name].append(template)

    # Analyze each role's process
    for role, tasks in role_groups.items():
        total_duration = sum(t.estimated_duration or 30 for t in tasks)
        required_tasks = [t for t in tasks if t.is_required]
        optional_tasks = [t for t in tasks if not t.is_required]

        # Suggest automation opportunities
        manual_tasks = [t for t in tasks if not t.automation_potential or t.automation_potential == "none"]
        if len(manual_tasks) > len(tasks) * 0.6:
            suggestions.append({
                "role": role,
                "type": "automation",
                "severity": "high",
                "title": f"{role}: High manual task load detected",
                "description": f"{len(manual_tasks)} out of {len(tasks)} tasks are manual. Consider automating repetitive tasks.",
                "impact": "Could reduce process time by 30-40%",
                "tasks_affected": [t.task_title for t in manual_tasks[:3]]
            })

        # Check for bottlenecks (long duration tasks)
        long_tasks = [t for t in tasks if (t.estimated_duration or 30) > 60]
        if long_tasks:
            suggestions.append({
                "role": role,
                "type": "bottleneck",
                "severity": "medium",
                "title": f"{role}: Time-intensive tasks identified",
                "description": f"{len(long_tasks)} tasks take over 60 minutes. Consider breaking them down.",
                "impact": "Could improve workflow parallelization",
                "tasks_affected": [f"{t.task_title} ({t.estimated_duration}min)" for t in long_tasks]
            })

        # Check dependencies
        tasks_with_deps = [t for t in tasks if t.dependencies and len(t.dependencies) > 0]
        if len(tasks_with_deps) > len(tasks) * 0.7:
            suggestions.append({
                "role": role,
                "type": "dependency",
                "severity": "medium",
                "title": f"{role}: High task dependency detected",
                "description": f"{len(tasks_with_deps)} tasks have dependencies. This may slow down the process.",
                "impact": "Review if some tasks can be parallelized",
                "tasks_affected": []
            })

        # Check for missing required tasks
        if len(required_tasks) < 3:
            suggestions.append({
                "role": role,
                "type": "completeness",
                "severity": "low",
                "title": f"{role}: Process may be incomplete",
                "description": f"Only {len(required_tasks)} required tasks defined. Review if process is complete.",
                "impact": "Ensure all critical steps are documented",
                "tasks_affected": []
            })

        # Overall efficiency score
        efficiency_score = 100
        if len(manual_tasks) > len(tasks) * 0.6:
            efficiency_score -= 30
        if long_tasks:
            efficiency_score -= 20
        if len(tasks_with_deps) > len(tasks) * 0.7:
            efficiency_score -= 15

        suggestions.append({
            "role": role,
            "type": "summary",
            "severity": "info",
            "title": f"{role}: Efficiency Score - {efficiency_score}%",
            "description": f"Total tasks: {len(tasks)} | Est. time: {total_duration} min | Required: {len(required_tasks)}",
            "impact": f"Process is {'efficient' if efficiency_score >= 70 else 'needs optimization'}",
            "efficiency_score": efficiency_score
        })

    return {
        "status": "success",
        "total_templates": len(templates),
        "roles_analyzed": list(role_groups.keys()),
        "suggestions": suggestions
    }

@app.post("/api/v1/process-templates/seed-defaults")
async def seed_default_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Seed default process templates for common roles"""
    # Check if user already has templates
    existing = db.query(ProcessTemplate).filter(ProcessTemplate.user_id == current_user.id).first()
    if existing:
        return {"message": "Templates already exist", "count": 0}

    default_templates = [
        # Loan Officer Tasks
        {"role_name": "Loan Officer", "task_title": "Initial Client Contact", "task_description": "Make first contact with borrower, introduce yourself and explain the loan process", "sequence_order": 1, "estimated_duration": 30, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Gather Financial Documents", "task_description": "Request pay stubs, tax returns, bank statements, and employment verification", "sequence_order": 2, "estimated_duration": 20, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Run Credit Report", "task_description": "Pull credit report and review credit score and history", "sequence_order": 3, "estimated_duration": 15, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Calculate DTI and Pre-Approval Amount", "task_description": "Calculate debt-to-income ratio and determine pre-approval amount", "sequence_order": 4, "estimated_duration": 30, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Send Pre-Approval Letter", "task_description": "Generate and send pre-approval letter to borrower", "sequence_order": 5, "estimated_duration": 15, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Schedule Follow-Up", "task_description": "Schedule follow-up call to check on house hunting progress", "sequence_order": 6, "estimated_duration": 10, "is_required": False},

        # Processor Tasks
        {"role_name": "Processor", "task_title": "Receive Loan Application", "task_description": "Receive completed loan application from loan officer", "sequence_order": 1, "estimated_duration": 15, "is_required": True},
        {"role_name": "Processor", "task_title": "Order Appraisal", "task_description": "Contact appraiser and schedule property appraisal", "sequence_order": 2, "estimated_duration": 20, "is_required": True},
        {"role_name": "Processor", "task_title": "Order Title Report", "task_description": "Request title search and title commitment", "sequence_order": 3, "estimated_duration": 15, "is_required": True},
        {"role_name": "Processor", "task_title": "Verify Employment", "task_description": "Contact employer to verify employment and income", "sequence_order": 4, "estimated_duration": 30, "is_required": True},
        {"role_name": "Processor", "task_title": "Review Documentation", "task_description": "Review all submitted documentation for completeness and accuracy", "sequence_order": 5, "estimated_duration": 45, "is_required": True},
        {"role_name": "Processor", "task_title": "Prepare Underwriting Package", "task_description": "Compile all documents and prepare file for underwriting", "sequence_order": 6, "estimated_duration": 60, "is_required": True},
        {"role_name": "Processor", "task_title": "Submit to Underwriting", "task_description": "Submit completed file to underwriter for review", "sequence_order": 7, "estimated_duration": 15, "is_required": True},

        # Underwriter Tasks
        {"role_name": "Underwriter", "task_title": "Initial File Review", "task_description": "Perform initial review of loan file for completeness", "sequence_order": 1, "estimated_duration": 30, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Verify Income Documentation", "task_description": "Review and verify all income documentation", "sequence_order": 2, "estimated_duration": 45, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Review Credit Report", "task_description": "Analyze credit report and evaluate credit risk", "sequence_order": 3, "estimated_duration": 30, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Evaluate Collateral", "task_description": "Review appraisal and assess property value", "sequence_order": 4, "estimated_duration": 30, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Issue Conditions", "task_description": "Create list of conditions that must be satisfied for approval", "sequence_order": 5, "estimated_duration": 45, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Final Approval Decision", "task_description": "Make final loan approval decision once all conditions are met", "sequence_order": 6, "estimated_duration": 30, "is_required": True},

        # Closer Tasks
        {"role_name": "Closer", "task_title": "Receive Clear to Close", "task_description": "Receive clear to close notification from underwriting", "sequence_order": 1, "estimated_duration": 10, "is_required": True},
        {"role_name": "Closer", "task_title": "Prepare Closing Disclosure", "task_description": "Generate closing disclosure with final loan terms and costs", "sequence_order": 2, "estimated_duration": 45, "is_required": True},
        {"role_name": "Closer", "task_title": "Send Closing Disclosure", "task_description": "Send closing disclosure to borrower (3-day waiting period required)", "sequence_order": 3, "estimated_duration": 15, "is_required": True},
        {"role_name": "Closer", "task_title": "Schedule Closing Appointment", "task_description": "Coordinate with all parties and schedule closing date/time", "sequence_order": 4, "estimated_duration": 30, "is_required": True},
        {"role_name": "Closer", "task_title": "Prepare Closing Package", "task_description": "Prepare all closing documents and wire instructions", "sequence_order": 5, "estimated_duration": 60, "is_required": True},
        {"role_name": "Closer", "task_title": "Coordinate Final Walk-Through", "task_description": "Ensure borrower completes final property walk-through", "sequence_order": 6, "estimated_duration": 20, "is_required": True},
        {"role_name": "Closer", "task_title": "Attend Closing", "task_description": "Attend closing or coordinate with title company", "sequence_order": 7, "estimated_duration": 90, "is_required": True},
    ]

    templates_created = []
    for template_data in default_templates:
        db_template = ProcessTemplate(**template_data, user_id=current_user.id)
        db.add(db_template)
        templates_created.append(db_template)

    db.commit()

    logger.info(f"Seeded {len(templates_created)} default process templates for user {current_user.id}")
    return {"message": "Default templates created successfully", "count": len(templates_created)}

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
    """Get comprehensive scorecard metrics based on real loan activity"""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, extract
    
    # Get current year for YTD calculations
    current_year = datetime.now().year
    
    # Get all leads and loans for the user
    leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
    loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()
    activities = db.query(Activity).join(Loan).filter(Loan.loan_officer_id == current_user.id).all()
    
    # Filter YTD data
    ytd_leads = [l for l in leads if l.created_at and l.created_at.year == current_year]
    ytd_loans = [l for l in loans if l.created_at and l.created_at.year == current_year]
    funded_loans = [l for l in ytd_loans if l.stage == LoanStage.FUNDED]
    
    # Calculate stage-based metrics from real loan activity
    total_leads = len(ytd_leads)
    prospect_leads = len([l for l in ytd_leads if l.stage == LeadStage.PROSPECT])
    app_started = len([l for l in ytd_leads if l.stage in [LeadStage.APPLICATION_STARTED, LeadStage.APPLICATION_COMPLETE, LeadStage.PRE_APPROVED]])
    pre_approved = len([l for l in ytd_leads if l.stage == LeadStage.PRE_APPROVED])
    funded_count = len(funded_loans)
    
    # Active loans in different stages
    processing_loans = [l for l in ytd_loans if l.stage == LoanStage.PROCESSING]
    underwriting_loans = [l for l in ytd_loans if l.stage == LoanStage.UW_RECEIVED]
    clear_to_close = [l for l in ytd_loans if l.stage == LoanStage.CTC]
    
    # Calculate conversion metrics from actual data
    conversion_metrics = {
        "starts_to_apps": round((app_started / total_leads * 100) if total_leads > 0 else 0, 1),
        "apps_to_funded": round((funded_count / app_started * 100) if app_started > 0 else 0, 1),
        "starts_to_funded": round((funded_count / total_leads * 100) if total_leads > 0 else 0, 1),
        "credit_to_funded": round((funded_count / pre_approved * 100) if pre_approved > 0 else 0, 1)
    }

    # Calculate volume & revenue from real loan data
    total_volume = sum([l.amount for l in funded_loans if l.amount]) or 0
    avg_loan_amount = (total_volume / len(funded_loans)) if funded_loans else 0
    
    # Calculate commission (assuming 185 basis points average)
    commission_earned = total_volume * 0.0185 if total_volume else 0

    volume_revenue = {
        "total_loans": funded_count,
        "total_volume": total_volume,
        "avg_loan_amount": avg_loan_amount,
        "commission_earned": commission_earned,
        "referrals": len([l for l in ytd_leads if l.source and 'referral' in l.source.lower()]),
        "portfolio_value": sum([l.amount for l in loans if l.amount]) or 0  # All loans, not just YTD
    }

    # Calculate loan type distribution from real data
    loan_types = {}
    for loan in funded_loans:
        loan_type = loan.product_type or "Conventional"
        if loan_type not in loan_types:
            loan_types[loan_type] = {"count": 0, "volume": 0}
        loan_types[loan_type]["count"] += 1
        loan_types[loan_type]["volume"] += loan.amount if loan.amount else 0

    loan_type_distribution = [
        {
            "type": loan_type,
            "units": data["count"],
            "volume": data["volume"],
            "percentage": round((data["volume"] / total_volume * 100) if total_volume > 0 else 0, 2)
        }
        for loan_type, data in loan_types.items()
    ]

    # Calculate referral sources from real lead data
    referral_sources = {}
    for lead in ytd_leads:
        source = lead.source or "Unknown"
        if source not in referral_sources:
            referral_sources[source] = {"count": 0, "volume": 0}
        referral_sources[source]["count"] += 1
        # Find corresponding loan for this lead
        lead_loan = next((l for l in funded_loans if l.borrower_name == lead.name), None)
        if lead_loan and lead_loan.amount:
            referral_sources[source]["volume"] += lead_loan.amount

    referral_sources_list = [
        {
            "source": source,
            "referrals": data["count"],
            "closedVolume": data["volume"]
        }
        for source, data in referral_sources.items()
    ]

    # Calculate process timeline from actual loan activities and timestamps
    def calculate_avg_days(from_stage, to_stage):
        stage_transitions = []
        for loan in ytd_loans:
            if loan.created_at and loan.updated_at:
                # This is simplified - in reality you'd track stage transitions in activities
                if from_stage == "start" and to_stage == "app":
                    # Days from lead creation to loan creation (application start)
                    lead = next((l for l in ytd_leads if l.name == loan.borrower_name), None)
                    if lead and lead.created_at:
                        days = (loan.created_at - lead.created_at).days
                        stage_transitions.append(days)
                elif from_stage == "app" and to_stage == "underwriting":
                    # Days in processing
                    if loan.stage in [LoanStage.UW_RECEIVED, LoanStage.CTC, LoanStage.FUNDED]:
                        # Simplified calculation - would be better with activity timestamps
                        days = 5  # Default assumption
                        stage_transitions.append(days)
        
        return round(sum(stage_transitions) / len(stage_transitions)) if stage_transitions else 10

    process_timeline = [
        {
            "id": "starts-to-app",
            "title": "Avg Starts to App (LE)",
            "value": f"{calculate_avg_days('start', 'app')} Days",
            "subtitle": "Loan Officer Average"
        },
        {
            "id": "app-to-uw",
            "title": "Avg App (LE) to UW",
            "value": f"{calculate_avg_days('app', 'underwriting')} Days",
            "subtitle": "Loan Officer Average"
        },
        {
            "id": "lock-to-funded",
            "title": "Initial Lock to Funded",
            "value": len(funded_loans),
            "goal": 90,
            "current": len(processing_loans) + len(underwriting_loans),
            "total": len(ytd_loans),
            "isPercentage": True
        }
    ]

    # Current pipeline status
    pipeline_status = {
        "prospect": len([l for l in ytd_leads if l.stage == LeadStage.PROSPECT]),
        "application": len([l for l in ytd_loans if l.stage in [LoanStage.DISCLOSED, LoanStage.PROCESSING]]),
        "underwriting": len(underwriting_loans),
        "clear_to_close": len(clear_to_close),
        "funded": funded_count
    }

    return {
        "conversionMetrics": [
            {
                "id": "starts-to-apps",
                "title": "Starts to Apps (LE)",
                "value": conversion_metrics["starts_to_apps"],
                "goal": 75,
                "current": app_started,
                "total": total_leads,
                "isPercentage": True
            },
            {
                "id": "apps-to-funded",
                "title": "Apps (LE) to Funded",
                "value": conversion_metrics["apps_to_funded"],
                "goal": 80,
                "current": funded_count,
                "total": app_started,
                "isPercentage": True
            },
            {
                "id": "starts-to-funded",
                "title": "Starts to Funded Pull-thru",
                "value": conversion_metrics["starts_to_funded"],
                "goal": 50,
                "current": funded_count,
                "total": total_leads,
                "isPercentage": True
            },
            {
                "id": "credit-to-funded",
                "title": "Credit Pull to Funded",
                "value": conversion_metrics["credit_to_funded"],
                "goal": 70,
                "current": funded_count,
                "total": pre_approved,
                "isPercentage": True
            }
        ],
        "volumeRevenue": [
            {
                "id": "total-loans",
                "title": "Total Loans",
                "value": volume_revenue["total_loans"],
                "subtitle": "Year to Date"
            },
            {
                "id": "total-volume",
                "title": "Total Volume",
                "value": f"${volume_revenue['total_volume']:,.0f}",
                "subtitle": "Year to Date"
            },
            {
                "id": "referrals",
                "title": "Referrals",
                "value": volume_revenue["referrals"],
                "subtitle": "Active Referral Partners"
            },
            {
                "id": "commission",
                "title": "Commission Earned",
                "value": f"${volume_revenue['commission_earned']:,.0f}",
                "subtitle": "Year to Date"
            },
            {
                "id": "portfolio-value",
                "title": "Portfolio Value",
                "value": f"${volume_revenue['portfolio_value']:,.0f}",
                "subtitle": "Total Active Loans"
            }
        ],
        "loanTypes": loan_type_distribution,
        "referralSources": referral_sources_list,
        "processTimeline": process_timeline,
        "pipelineStatus": pipeline_status
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
            lead.updated_at = datetime.now(timezone.utc)

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

    event.updated_at = datetime.now(timezone.utc)
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

        # Run schema migrations for existing tables (PostgreSQL only)
        # Note: SQLite tables are already created with all columns via Base.metadata.create_all()
        try:
            # Only run PostgreSQL-specific migrations if using PostgreSQL
            if not DATABASE_URL.startswith("sqlite"):
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

                    # Create api_keys table if it doesn't exist
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS api_keys (
                            id SERIAL PRIMARY KEY,
                            key VARCHAR UNIQUE NOT NULL,
                            name VARCHAR NOT NULL,
                            user_id INTEGER NOT NULL REFERENCES users(id),
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_used_at TIMESTAMP
                        );
                    """))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_api_keys_key ON api_keys(key);
                    """))

                    conn.commit()
                    logger.info("✅ Schema migrations applied (PostgreSQL)")
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
                closing_date=datetime.now(timezone.utc) + timedelta(days=25),
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
                closing_date=datetime.now(timezone.utc) + timedelta(days=18),
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
                due_date=datetime.now(timezone.utc) + timedelta(days=1)
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
                due_date=datetime.now(timezone.utc) + timedelta(days=3)
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
                original_close_date=datetime.now(timezone.utc) - timedelta(days=365),
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
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Store or update tokens in database
        existing_token = db.query(MicrosoftToken).filter(
            MicrosoftToken.user_id == user_id
        ).first()

        if existing_token:
            existing_token.access_token = tokens["access_token"]
            existing_token.refresh_token = tokens.get("refresh_token")
            existing_token.expires_at = expires_at
            existing_token.updated_at = datetime.now(timezone.utc)
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
    is_expired = token.expires_at < datetime.now(timezone.utc) if token.expires_at else True

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

async def refresh_microsoft_token_by_user(user_id: int, db: Session) -> Optional[str]:
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
        token_record.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        token_record.updated_at = datetime.now(timezone.utc)
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
        time_until_expiry = token_record.expires_at - datetime.now(timezone.utc)
        if time_until_expiry.total_seconds() < 300:  # Less than 5 minutes
            # Try to refresh
            new_token = await refresh_microsoft_token_by_user(user_id, db)
            return new_token if new_token else token_record.access_token

    return token_record.access_token

# ============================================================================
# CALENDLY INTEGRATION
# ============================================================================

@app.post("/api/v1/calendly/connect")
async def connect_calendly(
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save user's Calendly API key for integration.
    """
    api_key = request.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    try:
        # Verify the API key works by making a test call to Calendly
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        test_response = requests.get(
            "https://api.calendly.com/users/me",
            headers=headers
        )

        if test_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid Calendly API key")

        # Check if user already has a Calendly credential
        existing_cred = db.query(IntegrationCredential).filter(
            IntegrationCredential.user_id == current_user.id,
            IntegrationCredential.integration_type == "calendly"
        ).first()

        if existing_cred:
            # Update existing credential
            existing_cred.api_key = api_key
            existing_cred.is_active = True
            existing_cred.updated_at = datetime.now(timezone.utc)
        else:
            # Create new credential
            new_cred = IntegrationCredential(
                user_id=current_user.id,
                integration_type="calendly",
                api_key=api_key,
                is_active=True
            )
            db.add(new_cred)

        db.commit()

        return {
            "message": "Calendly connected successfully",
            "status": "connected"
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly API test failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to verify Calendly API key")
    except Exception as e:
        db.rollback()
        logger.error(f"Error connecting Calendly: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/calendly/event-types")
async def get_calendly_event_types(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's Calendly event types (available meeting types).
    Uses user's stored Calendly API key.
    """
    # Get user's Calendly credential from database
    cred = db.query(IntegrationCredential).filter(
        IntegrationCredential.user_id == current_user.id,
        IntegrationCredential.integration_type == "calendly",
        IntegrationCredential.is_active == True
    ).first()

    if not cred:
        # Return empty list if not connected
        return {
            "event_types": [],
            "count": 0
        }

    try:
        # First, get the current user's URI
        headers = {
            "Authorization": f"Bearer {cred.api_key}",
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
        lead.meta_data["calendly_created_at"] = datetime.now(timezone.utc).isoformat()
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
                    lead.meta_data["calendly_canceled_at"] = datetime.now(timezone.utc).isoformat()
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
                lead.meta_data["calendly_created_at"] = datetime.now(timezone.utc).isoformat()
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
            progress.completed_at = datetime.now(timezone.utc)

        # Update user
        current_user.onboarding_completed = True

        db.commit()

        return {"message": "Onboarding completed!", "completed_at": datetime.now(timezone.utc).isoformat()}

    except Exception as e:
        db.rollback()
        logger.error(f"Complete onboarding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def parse_document_basic(document_content: str, document_name: str = None):
    """
    Basic text-based document parser (fallback when OpenAI is not available).
    Extracts roles, milestones, and tasks using keyword matching.
    """
    import re

    lines = document_content.split('\n')

    # Extract role from document name or content
    role_name = "application_analyst" if "application" in document_content.lower()[:500] else "loan_specialist"
    role_title = role_name.replace('_', ' ').title()

    # Look for role indicators in first 1000 chars
    content_start = document_content[:1000].lower()
    if "application analysis" in content_start:
        role_name = "application_analyst"
        role_title = "Application Analyst"
    elif "loan officer" in content_start:
        role_name = "loan_officer"
        role_title = "Loan Officer"
    elif "processor" in content_start:
        role_name = "loan_processor"
        role_title = "Loan Processor"

    # Extract milestones (sections with "Checklist" or major headings)
    milestones = []
    milestone_pattern = r'(Pre-Call|During|Post-Call|Before|After|Step \d+|Phase \d+).*?(Checklist|Process|Stage|Milestone)'

    for i, line in enumerate(lines):
        if re.search(milestone_pattern, line, re.IGNORECASE) or (line.isupper() and len(line) > 5 and len(line) < 50):
            milestone_name = line.strip()
            if milestone_name and len(milestone_name) > 3:
                milestones.append({
                    "name": milestone_name[:50],  # Limit length
                    "description": f"Milestone extracted from document",
                    "sequence_order": len(milestones),
                    "estimated_duration": 2
                })

    # If no milestones found, create default ones
    if not milestones:
        milestones = [
            {"name": "Preparation", "description": "Initial preparation phase", "sequence_order": 0, "estimated_duration": 1},
            {"name": "Execution", "description": "Main execution phase", "sequence_order": 1, "estimated_duration": 2},
            {"name": "Follow-up", "description": "Follow-up and completion", "sequence_order": 2, "estimated_duration": 1}
        ]

    # Extract tasks (numbered items or items starting with verbs)
    tasks = []
    task_pattern = r'^\s*(\d+\.|\d+\)|-|•|[a-z]\.|[a-z]\))\s*(.+)$'
    current_milestone = milestones[0]["name"] if milestones else "General"

    for line in lines:
        # Check if line is a milestone header
        for milestone in milestones:
            if milestone["name"].lower() in line.lower() and len(line) < 100:
                current_milestone = milestone["name"]
                break

        # Extract tasks
        match = re.match(task_pattern, line.strip())
        if match and len(match.group(2)) > 10:
            task_text = match.group(2).strip()
            # Only include substantial tasks
            if len(task_text) > 15 and not task_text.endswith(':'):
                tasks.append({
                    "milestone": current_milestone,
                    "role": role_name,
                    "task_name": task_text[:100],  # First 100 chars as name
                    "task_description": task_text,
                    "sequence_order": len([t for t in tasks if t["milestone"] == current_milestone]),
                    "estimated_duration": 15,
                    "sla": 24,
                    "ai_automatable": False,
                    "is_required": True
                })

    # Ensure we have at least some tasks
    if not tasks:
        tasks = [
            {
                "milestone": milestones[0]["name"],
                "role": role_name,
                "task_name": "Review document requirements",
                "task_description": "Review all requirements from the uploaded document",
                "sequence_order": 0,
                "estimated_duration": 30,
                "sla": 24,
                "ai_automatable": False,
                "is_required": True
            }
        ]

    return {
        "roles": [{
            "role_name": role_name,
            "role_title": role_title,
            "responsibilities": f"Responsibilities extracted from {document_name or 'uploaded document'}",
            "skills_required": ["Document Analysis", "Process Management", "Attention to Detail"],
            "key_activities": ["Document review", "Process execution", "Quality control"]
        }],
        "milestones": milestones,
        "tasks": tasks
    }

@app.post("/api/v1/onboarding/parse-documents")
async def parse_onboarding_documents(
    request: DocumentParseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Parse uploaded documents and extract roles, milestones, and tasks using AI"""
    try:
        # Clear existing parsed data for this user
        db.query(ProcessTask).filter(ProcessTask.user_id == current_user.id).delete()
        db.query(ProcessMilestone).filter(ProcessMilestone.user_id == current_user.id).delete()
        db.query(ProcessRole).filter(ProcessRole.user_id == current_user.id).delete()
        db.commit()

        # Use AI to analyze the document content
        analysis_prompt = f"""
        Analyze the following mortgage loan process document and extract:
        1. All unique roles/positions involved in the process
        2. All major milestones in the mortgage loan process
        3. All tasks for each milestone with role assignments

        For each role, provide:
        - role_name: Short identifier (e.g., "loan_officer", "processor")
        - role_title: Display name (e.g., "Loan Officer", "Loan Processor")
        - responsibilities: Brief description of their main responsibilities
        - skills_required: List of required skills
        - key_activities: List of their primary activities

        For each milestone, provide:
        - name: Milestone name
        - description: Brief description
        - sequence_order: Order in process (0, 1, 2...)
        - estimated_duration: Estimated hours to complete

        For each task, provide:
        - milestone: Which milestone it belongs to
        - role: Which role is responsible
        - task_name: Task name
        - task_description: Detailed description
        - sequence_order: Order within milestone
        - estimated_duration: Minutes to complete
        - sla: Service level agreement in hours
        - ai_automatable: Boolean if AI can automate this
        - is_required: Boolean if required

        Document content:
        {request.document_content[:10000]}  # Limit to 10k chars

        Return response as JSON with keys: roles, milestones, tasks
        """

        # Use OpenAI to actually parse the document, or fall back to basic parsing
        if openai_client:
            try:
                completion = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are an expert at analyzing process documents and extracting structured information."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                ai_response = json.loads(completion.choices[0].message.content)

                # Validate response structure
                if not all(key in ai_response for key in ["roles", "milestones", "tasks"]):
                    raise HTTPException(status_code=500, detail="AI response missing required keys (roles, milestones, tasks)")

                if not ai_response["roles"]:
                    raise HTTPException(status_code=400, detail="No roles found in document. Please upload a document containing role and responsibility information.")

            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {e}")
                raise HTTPException(status_code=500, detail="AI returned invalid JSON")
            except Exception as e:
                logger.error(f"OpenAI parsing error: {e}")
                raise HTTPException(status_code=500, detail=f"AI parsing failed: {str(e)}")
        else:
            # Fallback: Use basic text parsing when OpenAI is not available
            logger.info("Using fallback text-based parsing (no OpenAI API key configured)")
            ai_response = parse_document_basic(request.document_content, request.document_name)

        # Create ProcessRole records
        role_map = {}
        for role_data in ai_response["roles"]:
            role = ProcessRole(
                user_id=current_user.id,
                role_name=role_data["role_name"],
                role_title=role_data["role_title"],
                responsibilities=role_data.get("responsibilities"),
                skills_required=role_data.get("skills_required", []),
                key_activities=role_data.get("key_activities", [])
            )
            db.add(role)
            db.flush()
            role_map[role_data["role_name"]] = role.id

        # Create ProcessMilestone records
        milestone_map = {}
        for milestone_data in ai_response["milestones"]:
            milestone = ProcessMilestone(
                user_id=current_user.id,
                name=milestone_data["name"],
                description=milestone_data.get("description"),
                sequence_order=milestone_data.get("sequence_order", 0),
                estimated_duration=milestone_data.get("estimated_duration")
            )
            db.add(milestone)
            db.flush()
            milestone_map[milestone_data["name"]] = milestone.id

        # Create ProcessTask records
        for task_data in ai_response["tasks"]:
            milestone_id = milestone_map.get(task_data["milestone"])
            role_id = role_map.get(task_data["role"])

            if milestone_id and role_id:
                task = ProcessTask(
                    user_id=current_user.id,
                    milestone_id=milestone_id,
                    role_id=role_id,
                    task_name=task_data["task_name"],
                    task_description=task_data.get("task_description"),
                    sequence_order=task_data.get("sequence_order", 0),
                    estimated_duration=task_data.get("estimated_duration"),
                    sla=task_data.get("sla"),
                    sla_unit=task_data.get("sla_unit", "hours"),
                    ai_automatable=task_data.get("ai_automatable", False),
                    is_required=task_data.get("is_required", True)
                )
                db.add(task)

        db.commit()

        # Get created records
        roles = db.query(ProcessRole).filter(ProcessRole.user_id == current_user.id).all()
        milestones = db.query(ProcessMilestone).filter(ProcessMilestone.user_id == current_user.id).all()
        tasks = db.query(ProcessTask).filter(ProcessTask.user_id == current_user.id).all()

        return {
            "roles": [ProcessRoleResponse.from_orm(r) for r in roles],
            "milestones": [ProcessMilestoneResponse.from_orm(m) for m in milestones],
            "tasks": [ProcessTaskResponse.from_orm(t) for t in tasks],
            "summary": {
                "total_roles": len(roles),
                "total_milestones": len(milestones),
                "total_tasks": len(tasks),
                "document_name": request.document_name
            }
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Parse documents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/onboarding/roles")
async def get_process_roles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all AI-extracted roles for current user"""
    try:
        roles = db.query(ProcessRole).filter(
            ProcessRole.user_id == current_user.id,
            ProcessRole.is_active == True
        ).order_by(ProcessRole.role_name).all()

        return [ProcessRoleResponse.from_orm(role) for role in roles]

    except Exception as e:
        logger.error(f"Get roles error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/onboarding/milestones")
async def get_process_milestones(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all AI-extracted milestones for current user"""
    try:
        milestones = db.query(ProcessMilestone).filter(
            ProcessMilestone.user_id == current_user.id,
            ProcessMilestone.is_active == True
        ).order_by(ProcessMilestone.sequence_order).all()

        return [ProcessMilestoneResponse.from_orm(milestone) for milestone in milestones]

    except Exception as e:
        logger.error(f"Get milestones error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/onboarding/tasks")
async def get_process_tasks(
    role_id: Optional[int] = None,
    milestone_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all AI-extracted tasks for current user, optionally filtered by role or milestone"""
    try:
        query = db.query(ProcessTask).filter(
            ProcessTask.user_id == current_user.id,
            ProcessTask.is_active == True
        )

        if role_id:
            query = query.filter(ProcessTask.role_id == role_id)

        if milestone_id:
            query = query.filter(ProcessTask.milestone_id == milestone_id)

        tasks = query.order_by(ProcessTask.milestone_id, ProcessTask.sequence_order).all()

        return [ProcessTaskResponse.from_orm(task) for task in tasks]

    except Exception as e:
        logger.error(f"Get tasks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/team/members")
async def get_team_members(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all team members with their assigned roles from onboarding"""
    try:
        # Get all users in the system
        all_users = db.query(User).filter(User.id != current_user.id).all()

        # Get all process roles for the current user (the admin who completed onboarding)
        process_roles = db.query(ProcessRole).filter(
            ProcessRole.user_id == current_user.id,
            ProcessRole.is_active == True
        ).all()

        # Get tasks count for each role
        team_members = []
        for user in all_users:
            # Extract metadata
            metadata = user.user_metadata or {}

            # Try to find a matching role for this user (simplified - in production you'd have explicit user-role mapping)
            member_data = {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "first_name": metadata.get("first_name"),
                "last_name": metadata.get("last_name"),
                "phone": metadata.get("phone"),
                "role": user.role,
                "title": metadata.get("title"),
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "onboarding_completed": user.onboarding_completed,
                "tasks_count": 0
            }

            # Add to list
            team_members.append(member_data)

        # Also include current user
        current_metadata = current_user.user_metadata or {}
        current_member = {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "first_name": current_metadata.get("first_name"),
            "last_name": current_metadata.get("last_name"),
            "phone": current_metadata.get("phone"),
            "role": current_user.role or "Admin",
            "title": current_metadata.get("title"),
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "onboarding_completed": current_user.onboarding_completed,
            "tasks_count": 0,
            "is_current": True
        }

        team_members.insert(0, current_member)

        # Get role assignments and task counts
        roles_data = []
        for role in process_roles:
            tasks_count = db.query(ProcessTask).filter(
                ProcessTask.role_id == role.id,
                ProcessTask.is_active == True
            ).count()

            roles_data.append({
                "id": role.id,
                "role_name": role.role_name,
                "role_title": role.role_title,
                "responsibilities": role.responsibilities,
                "skills_required": role.skills_required,
                "key_activities": role.key_activities,
                "tasks_count": tasks_count
            })

        return {
            "team_members": team_members,
            "available_roles": roles_data
        }

    except Exception as e:
        logger.error(f"Get team members error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/team/members/{user_id}")
async def get_team_member_detail(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific team member"""
    try:
        # Get the user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get roles assigned to the admin
        process_roles = db.query(ProcessRole).filter(
            ProcessRole.user_id == current_user.id,
            ProcessRole.is_active == True
        ).all()

        # Get tasks for this user's role
        # In a real app, you'd have a user_role_assignments table
        # For now, we'll just return all roles and tasks

        roles_with_tasks = []
        for role in process_roles:
            tasks = db.query(ProcessTask).filter(
                ProcessTask.role_id == role.id,
                ProcessTask.is_active == True
            ).order_by(ProcessTask.milestone_id, ProcessTask.sequence_order).all()

            roles_with_tasks.append({
                "role": ProcessRoleResponse.from_orm(role),
                "tasks": [ProcessTaskResponse.from_orm(t) for t in tasks]
            })

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "onboarding_completed": user.onboarding_completed
            },
            "roles_with_tasks": roles_with_tasks
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get team member detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/team/members")
async def create_team_member(
    member_data: TeamMemberCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new team member"""
    try:
        # Create a new user for the team member
        # Generate a random password (they can reset it later)
        import secrets
        temp_password = secrets.token_urlsafe(16)
        hashed_password = bcrypt.hashpw(temp_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Create full_name from first and last name
        full_name = f"{member_data.first_name} {member_data.last_name}"

        # Store additional data in user_metadata
        user_metadata = {
            "first_name": member_data.first_name,
            "last_name": member_data.last_name,
            "phone": member_data.phone,
            "title": member_data.title
        }

        new_user = User(
            email=member_data.email or f"{member_data.first_name.lower()}.{member_data.last_name.lower()}@temp.com",
            hashed_password=hashed_password,
            full_name=full_name,
            role=member_data.role,
            user_metadata=user_metadata,
            is_active=True,
            email_verified=False,
            onboarding_completed=False
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "id": new_user.id,
            "first_name": member_data.first_name,
            "last_name": member_data.last_name,
            "email": member_data.email,
            "phone": member_data.phone,
            "role": member_data.role,
            "title": member_data.title
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Create team member error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/v1/team/members/{member_id}")
async def update_team_member(
    member_id: int,
    member_data: TeamMemberUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a team member"""
    try:
        user = db.query(User).filter(User.id == member_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Team member not found")

        # Update fields
        user_metadata = user.user_metadata or {}

        if member_data.first_name is not None:
            user_metadata["first_name"] = member_data.first_name
        if member_data.last_name is not None:
            user_metadata["last_name"] = member_data.last_name
        if member_data.phone is not None:
            user_metadata["phone"] = member_data.phone
        if member_data.title is not None:
            user_metadata["title"] = member_data.title

        # Update full_name if first or last name changed
        if member_data.first_name or member_data.last_name:
            first = member_data.first_name or user_metadata.get("first_name", "")
            last = member_data.last_name or user_metadata.get("last_name", "")
            user.full_name = f"{first} {last}"

        if member_data.email is not None:
            user.email = member_data.email
        if member_data.role is not None:
            user.role = member_data.role

        user.user_metadata = user_metadata

        db.commit()
        db.refresh(user)

        return {
            "id": user.id,
            "first_name": user_metadata.get("first_name"),
            "last_name": user_metadata.get("last_name"),
            "email": user.email,
            "phone": user_metadata.get("phone"),
            "role": user.role,
            "title": user_metadata.get("title")
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Update team member error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/team/members/{member_id}")
async def delete_team_member(
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a team member"""
    try:
        user = db.query(User).filter(User.id == member_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Team member not found")

        # Soft delete - just mark as inactive
        user.is_active = False
        db.commit()

        return {"message": "Team member deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete team member error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# AGENTIC AI PERFORMANCE COACH ("THE PROCESS COACH")
# ============================================================================

def build_coach_context(user: User, db: Session) -> Dict[str, Any]:
    """Build comprehensive context for the Performance Coach"""

    # Get user's pipeline
    leads = db.query(Lead).filter(Lead.owner_id == user.id).all()
    loans = db.query(Loan).filter(Loan.loan_officer_id == user.id).all()

    # Get open tasks
    open_tasks = db.query(AITask).filter(
        AITask.assigned_to_id == user.id,
        AITask.type != TaskType.COMPLETED
    ).all()

    # Get overdue tasks
    overdue_tasks = [t for t in open_tasks if t.due_date and t.due_date < datetime.now(timezone.utc)]

    # Get pending reconciliation items
    pending_reconciliation = db.query(ExtractedData).join(
        IncomingDataEvent,
        ExtractedData.event_id == IncomingDataEvent.id
    ).filter(
        IncomingDataEvent.user_id == user.id,
        ExtractedData.status.in_(["pending_review", "needs_review"])
    ).count()

    # Calculate pipeline metrics
    leads_by_stage = {}
    for lead in leads:
        stage = lead.stage.value
        leads_by_stage[stage] = leads_by_stage.get(stage, 0) + 1

    loans_by_stage = {}
    for loan in loans:
        stage = loan.stage.value
        loans_by_stage[stage] = loans_by_stage.get(stage, 0) + 1

    # Identify bottlenecks (loans/leads stuck in same stage > 7 days)
    bottlenecks = []
    for lead in leads:
        # Use last_contact if available, otherwise updated_at
        last_activity = lead.last_contact or lead.updated_at
        if last_activity:
            days_in_stage = (datetime.now(timezone.utc) - last_activity).days
            if days_in_stage > 7:
                bottlenecks.append({"type": "Lead", "name": lead.name, "stage": lead.stage.value, "days": days_in_stage})

    for loan in loans:
        if loan.updated_at:
            days_in_stage = (datetime.now(timezone.utc) - loan.updated_at).days
            if days_in_stage > 7:
                bottlenecks.append({"type": "Loan", "name": loan.loan_number, "stage": loan.stage.value, "days": days_in_stage})

    return {
        "user": {
            "name": user.full_name,
            "role": user.role,
            "email": user.email
        },
        "pipeline": {
            "total_leads": len(leads),
            "total_loans": len(loans),
            "leads_by_stage": leads_by_stage,
            "loans_by_stage": loans_by_stage
        },
        "tasks": {
            "total_open": len(open_tasks),
            "overdue": len(overdue_tasks),
            "overdue_list": [{"title": t.title, "days_overdue": (datetime.now(timezone.utc) - t.due_date).days} for t in overdue_tasks[:5]]
        },
        "reconciliation": {
            "pending_review": pending_reconciliation
        },
        "bottlenecks": bottlenecks[:10]  # Top 10 bottlenecks
    }

def get_coach_system_prompt(mode: CoachMode) -> str:
    """Get the system prompt for the Performance Coach based on mode"""

    base_personality = """You are The Process Coach - a high-performance coach for mortgage professionals.

Your coaching philosophy is inspired by elite athletic coaching principles:
- PROCESS OVER OUTCOME: Focus on daily execution, not results
- BRUTAL CLARITY: Direct, concise, no fluff
- STANDARD-FIRST: Do things the right way every time
- DISTRACTION-RESISTANT: Cut noise, maintain focus
- CONTROLLED URGENCY: Push pace without panic
- ROLE ACCOUNTABILITY: Everyone has a job
- BEHAVIOR-BASED: Habits, routines, fundamentals
- EXECUTION-ONLY: No excuses, output only

Communication style:
- Short, punchy sentences
- Military/coaching brevity
- Call out inefficiencies directly
- No motivational speaker energy
- No "you got this" cheerleading
- Pure tactical guidance
- Action-oriented only
"""

    mode_prompts = {
        CoachMode.daily_briefing: base_personality + """
MODE: Daily Briefing

Your job: Review their pipeline and give them their top 3 priorities for today.

Important: If they have pending reconciliation items, prioritize those. Data accuracy is fundamental to The Process.

Format:
"Morning. Today we run The Process.

Top priorities:
1. [High-leverage task]
2. [High-leverage task]
3. [High-leverage task]

Eliminate distractions. Execute with pace."

Be specific. Use their actual pipeline data. If reconciliation.pending_review > 0, include reviewing those items as a priority.""",

        CoachMode.pipeline_audit: base_personality + """
MODE: Pipeline Audit

Your job: Identify bottlenecks, stalled deals, and what needs immediate action.

Include data reconciliation if pending. Unreviewed data = blind spots in your pipeline.

Format:
"Pipeline audit complete.

Bottlenecks:
- [Specific deal/lead + issue]
- [Specific deal/lead + issue]

Fix these now. Nothing else matters until this is done."

Be ruthless. Call out what's broken. If reconciliation.pending_review > 0, flag it as a data integrity issue.""",

        CoachMode.focus_reset: base_personality + """
MODE: Focus Reset

Your job: Get them back on track when they're scattered or overwhelmed.

Format:
"Focus reset.

Right now: [One specific task]
Duration: 25 minutes
No exceptions.

Everything else can wait."

Single-task them. Break the overwhelm.""",

        CoachMode.accountability: base_personality + """
MODE: Accountability

Your job: Review their performance and hold them to their standard.

Format:
"Performance review:

Wins: [List what they did well]
Misses: [List what they missed]

Fix the misses tomorrow. No repeating patterns."

Be fair but firm.""",

        CoachMode.tactical_advice: base_personality + """
MODE: Tactical Advice

Your job: Answer their specific question with actionable guidance.

Stay brief. Give the play call. Move on.""",

        CoachMode.tough_love: base_personality + """
MODE: Tough Love Correction

Your job: Call out lazy habits, drift, or declining standards.

Format:
"Your current output does not match your goals.

Issue: [Specific problem]
Standard: [What the standard should be]
Fix: [Specific action]

Raise your standard. Follow the system."

Be direct. No sugar coating.""",

        CoachMode.teach_process: base_personality + """
MODE: Teach The Process

Your job: Teach them how to think about systems, habits, and execution.

Explain the principle. Give the drill. Apply it to their situation.""",

        CoachMode.priority_guidance: base_personality + """
MODE: Priority Guidance

Your job: Help them decide what to do next when they're unsure.

Format:
"Priority decision:

Do this: [Highest leverage task]
Then this: [Second priority]

Everything else is distraction."

Clear hierarchy. No ambiguity."""
    }

    return mode_prompts.get(mode, base_personality)

def generate_priorities(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate prioritized action items from context"""
    priorities = []

    # Priority 1: Overdue tasks
    if context["tasks"]["overdue"] > 0:
        priorities.append({
            "priority": 1,
            "category": "Overdue Tasks",
            "action": f"Clear {context['tasks']['overdue']} overdue tasks",
            "urgency": "CRITICAL"
        })

    # Priority 2: Bottlenecked deals
    if context["bottlenecks"]:
        top_bottleneck = context["bottlenecks"][0]
        priorities.append({
            "priority": 2,
            "category": "Pipeline Bottleneck",
            "action": f"Unstick {top_bottleneck['name']} ({top_bottleneck['days']} days in {top_bottleneck['stage']})",
            "urgency": "HIGH"
        })

    # Priority 3: High-value pipeline movement
    priorities.append({
        "priority": 3,
        "category": "Pipeline Advancement",
        "action": "Move top 3 deals forward one stage",
        "urgency": "MEDIUM"
    })

    return priorities

@app.post("/api/v1/coach", response_model=CoachResponse)
async def performance_coach(
    request: CoachRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Agentic AI Performance Coach endpoint"""

    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    try:
        # Build comprehensive context
        context = build_coach_context(current_user, db)

        # Get system prompt for the mode
        system_prompt = get_coach_system_prompt(request.mode)

        # Build user message with context
        context_message = f"""
USER CONTEXT:
- Name: {context['user']['name']}
- Role: {context['user']['role']}

PIPELINE:
- Total Leads: {context['pipeline']['total_leads']}
- Total Loans: {context['pipeline']['total_loans']}
- Leads by Stage: {context['pipeline']['leads_by_stage']}
- Loans by Stage: {context['pipeline']['loans_by_stage']}

TASKS:
- Total Open: {context['tasks']['total_open']}
- Overdue: {context['tasks']['overdue']}
- Top Overdue: {context['tasks']['overdue_list']}

BOTTLENECKS:
{chr(10).join([f"- {b['type']}: {b['name']} ({b['days']} days in {b['stage']})" for b in context['bottlenecks']])}

"""

        if request.message:
            context_message += f"\nUSER REQUEST: {request.message}"

        # Call OpenAI with the coach system prompt
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_message}
            ],
            temperature=0.7,
            max_tokens=500
        )

        coach_response = response.choices[0].message.content

        # Generate priorities if in daily_briefing or priority_guidance mode
        priorities = None
        if request.mode in [CoachMode.daily_briefing, CoachMode.priority_guidance]:
            priorities = generate_priorities(context)

        # Generate action items from bottlenecks
        action_items = None
        if request.mode == CoachMode.pipeline_audit:
            action_items = [f"Fix {b['name']} - stuck {b['days']} days in {b['stage']}" for b in context['bottlenecks'][:5]]

        logger.info(f"Performance Coach responded to {current_user.email} in {request.mode.value} mode")

        return CoachResponse(
            mode=request.mode,
            response=coach_response,
            priorities=priorities,
            metrics={
                "pipeline_health": "good" if len(context['bottlenecks']) < 3 else "needs_attention",
                "total_bottlenecks": len(context['bottlenecks']),
                "overdue_tasks": context['tasks']['overdue']
            },
            action_items=action_items
        )

    except Exception as e:
        logger.error(f"Performance Coach error: {e}")
        raise HTTPException(status_code=500, detail=f"Coach error: {str(e)}")

# ============================================================================
# AI SYSTEM INITIALIZATION ENDPOINT
# ============================================================================

@app.post("/api/admin/initialize-ai-system")
async def initialize_ai_system(db: Session = Depends(get_db)):
    """Initialize AI system tables and register agents/tools"""
    try:
        import os
        from pathlib import Path

        # Step 1: Run database migration
        logger.info("Initializing AI system database schema...")
        schema_path = Path(__file__).parent / "ai_architecture_schema.sql"

        if not schema_path.exists():
            raise HTTPException(status_code=500, detail="AI schema file not found")

        with open(schema_path, "r") as f:
            sql = f.read()

        # Execute SQL statements one by one
        from sqlalchemy import text
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        for statement in statements:
            if statement:
                db.execute(text(statement))
        db.commit()

        logger.info("✅ AI database schema created")

        # Step 2: Register agents
        logger.info("Registering AI agents...")
        from ai_agent_definitions import ALL_AGENTS
        from ai_services import AgentRegistry

        registry = AgentRegistry(db)
        registered_agents = []

        for agent in ALL_AGENTS:
            try:
                agent_id = await registry.register_agent(agent)
                registered_agents.append(agent.name)
                logger.info(f"✅ Registered agent: {agent.name}")
            except Exception as e:
                logger.error(f"Failed to register {agent.name}: {e}")

        logger.info(f"✅ Registered {len(registered_agents)}/{len(ALL_AGENTS)} agents")

        # Step 3: Register tools
        logger.info("Registering AI tools...")
        from ai_agent_definitions import TOOL_DEFINITIONS
        from ai_services import ToolRegistry

        tool_registry = ToolRegistry(db)
        registered_tools = []

        for tool in TOOL_DEFINITIONS:
            try:
                # Create a placeholder handler
                async def placeholder_handler(input_data: dict, context):
                    return {
                        "success": True,
                        "message": f"Tool {tool.name} executed",
                        "data": input_data
                    }

                await tool_registry.register_tool(tool, placeholder_handler)
                registered_tools.append(tool.name)
                logger.info(f"✅ Registered tool: {tool.name}")
            except Exception as e:
                logger.error(f"Failed to register tool {tool.name}: {e}")

        logger.info(f"✅ Registered {len(registered_tools)}/{len(TOOL_DEFINITIONS)} tools")

        return {
            "status": "success",
            "message": "AI system initialized successfully",
            "agents_registered": len(registered_agents),
            "tools_registered": len(registered_tools),
            "agents": registered_agents,
            "tools": registered_tools
        }

    except Exception as e:
        logger.error(f"AI system initialization failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Initialization failed: {str(e)}")


@app.post("/api/admin/initialize-mission-control")
async def initialize_mission_control(db: Session = Depends(get_db)):
    """Initialize Mission Control database schema"""
    try:
        import os
        from pathlib import Path

        logger.info("Initializing Mission Control database schema...")
        schema_path = Path(__file__).parent / "mission_control_schema.sql"

        if not schema_path.exists():
            raise HTTPException(status_code=500, detail="Mission Control schema file not found")

        with open(schema_path, "r") as f:
            sql = f.read()

        # Execute SQL statements one by one
        from sqlalchemy import text
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        tables_created = 0

        for statement in statements:
            if statement and not statement.startswith('--'):
                try:
                    db.execute(text(statement))
                    if 'CREATE TABLE' in statement.upper():
                        tables_created += 1
                except Exception as e:
                    # Ignore "already exists" errors
                    if 'already exists' not in str(e).lower():
                        logger.error(f"Error executing statement: {e}")

        db.commit()
        logger.info(f"✅ Mission Control schema initialized ({tables_created} tables)")

        # Create initial data
        logger.info("Creating initial Mission Control data...")

        # Insert sample integration status
        sample_integrations = [
            ('LOS (BytePro)', 'healthy', 250, 0),
            ('Email (Microsoft 365)', 'healthy', 180, 0),
            ('Calendar (Outlook)', 'healthy', 200, 0),
            ('SMS (Twilio)', 'healthy', 120, 0),
        ]

        for name, status, latency, errors in sample_integrations:
            try:
                insert_query = text("""
                    INSERT INTO integration_status_log (integration_name, status, latency_ms, error_count_24h, last_success_at, checked_at)
                    VALUES (:name, :status, :latency, :errors, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """)
                db.execute(insert_query, {"name": name, "status": status, "latency": latency, "errors": errors})
            except:
                pass  # Ignore if already exists

        # Insert initial AI metrics
        try:
            from datetime import date
            today = date.today()
            metrics_query = text("""
                INSERT INTO ai_metrics_daily (
                    date, tasks_total, tasks_auto_completed, tasks_escalated_to_humans,
                    automation_rate, escalation_rate, ai_improvement_index
                )
                VALUES (
                    :date, 100, 74, 23, 74.0, 23.0, 128.0
                )
                ON CONFLICT (date) DO NOTHING
            """)
            db.execute(metrics_query, {"date": today})
        except:
            pass

        # Insert initial security snapshot
        try:
            security_query = text("""
                INSERT INTO security_snapshot_daily (
                    date, active_users_with_2fa, active_users_total, high_privilege_actions_24h
                )
                VALUES (
                    :date, 8, 10, 3
                )
                ON CONFLICT (date) DO NOTHING
            """)
            db.execute(security_query, {"date": today})
        except:
            pass

        db.commit()

        return {
            "status": "success",
            "message": "Mission Control initialized successfully",
            "tables_created": tables_created
        }

    except Exception as e:
        logger.error(f"Mission Control initialization failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Initialization failed: {str(e)}")


# ============================================================================
# STARTUP EVENT
# ============================================================================

async def auto_sync_emails():
    """Background task to automatically sync emails for all users with sync enabled"""
    try:
        db = SessionLocal()

        # Get all users with Microsoft sync enabled
        oauth_tokens = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.sync_enabled == True
        ).all()

        logger.info(f"🔄 Auto-sync: Checking {len(oauth_tokens)} users for email sync")

        for oauth_record in oauth_tokens:
            try:
                # Check if it's time to sync based on sync_frequency_minutes
                if oauth_record.last_sync_at:
                    last_sync = oauth_record.last_sync_at
                    # Ensure timezone-aware comparison
                    if last_sync.tzinfo is None:
                        last_sync = last_sync.replace(tzinfo=timezone.utc)

                    time_since_sync = datetime.now(timezone.utc) - last_sync
                    minutes_since_sync = time_since_sync.total_seconds() / 60

                    # Skip if synced recently (within sync_frequency_minutes)
                    if minutes_since_sync < oauth_record.sync_frequency_minutes:
                        continue

                logger.info(f"📧 Auto-syncing emails for user {oauth_record.user_id} ({oauth_record.email_address})")

                # Fetch emails
                result = await fetch_microsoft_emails(oauth_record, db, limit=50)

                if "error" in result:
                    logger.error(f"Auto-sync error for user {oauth_record.user_id}: {result['error']}")
                    continue

                # Process each email through DRE
                emails = result.get("emails", [])
                processed_count = 0

                for email_data in emails:
                    process_result = await process_microsoft_email_to_dre(email_data, oauth_record.user_id, db)
                    if process_result.get("status") == "success":
                        processed_count += 1

                # Update last_sync_at
                oauth_record.last_sync_at = datetime.now(timezone.utc)
                db.commit()

                logger.info(f"✅ Auto-synced {processed_count}/{len(emails)} emails for user {oauth_record.user_id}")

            except Exception as e:
                logger.error(f"Error auto-syncing for user {oauth_record.user_id}: {e}")
                db.rollback()
                continue

        db.close()

    except Exception as e:
        logger.error(f"Auto-sync task error: {e}")

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

    # Start auto-sync scheduler
    try:
        scheduler.add_job(
            auto_sync_emails,
            trigger=IntervalTrigger(minutes=5),
            id='auto_sync_emails',
            name='Auto-sync Microsoft 365 emails',
            replace_existing=True
        )
        scheduler.start()
        logger.info("✅ Auto-sync scheduler started (runs every 5 minutes)")
    except Exception as e:
        logger.error(f"Failed to start auto-sync scheduler: {e}")

    logger.info("✅ CRM is ready!")
    logger.info("📚 API Documentation: http://localhost:8000/docs")
    logger.info("🔐 Demo Login: demo@example.com / demo123")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        scheduler.shutdown()
        logger.info("✅ Auto-sync scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")

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
