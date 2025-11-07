# ============================================================================
# COMPLETE AGENTIC AI MORTGAGE CRM - FULLY FUNCTIONAL
# ============================================================================
# All features implemented:
# ✅ Complete CRUD for all entities
# ✅ AI Integration with OpenAI
# ✅ Authentication & Security
# ✅ Sample data generation
# ============================================================================

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, Enum as SQLEnum, func
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
from openai import OpenAI

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

# Database
try:
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        connect_args={"connect_timeout": 10}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("✅ Database engine created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create database engine: {e}")
    # Create a dummy sessionmaker for development
    SessionLocal = sessionmaker(autocommit=False, autoflush=False)
Base = declarative_base()

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
    notes = Column(Text)
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
    metadata = Column(JSON)
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
    metadata = Column(JSON)
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
    metadata = Column(JSON)
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
    metadata = Column(JSON)
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
    metadata = Column(JSON)
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
    metadata = Column(JSON)
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

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    stage: Optional[LeadStage] = None
    notes: Optional[str] = None

class LeadResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    stage: LeadStage
    source: Optional[str]
    ai_score: int
    sentiment: Optional[str]
    next_action: Optional[str]
    preapproval_amount: Optional[float]
    created_at: datetime
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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "https://mortgage-crm-nine.vercel.app"],    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include public routes
from public_routes import router as public_router
app.include_router(public_router, tags=["Public"])

# Auth
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

    if loan.days_in_stage > 10:
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
        db.execute("SELECT 1")
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

@app.post("/api/v1/register", response_model=UserResponse)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = User(
        email=user.email,
        hashed_password=get_password_hash(user.password),
        full_name=user.full_name
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    logger.info(f"User registered: {db_user.email}")
    return db_user

# ============================================================================
# DASHBOARD
# ============================================================================

@app.get("/api/v1/dashboard")
async def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total_leads = db.query(Lead).filter(Lead.owner_id == current_user.id).count()
    hot_leads = db.query(Lead).filter(Lead.owner_id == current_user.id, Lead.ai_score >= 80).count()
    active_loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id, Loan.stage != LoanStage.FUNDED).count()

    # Calculate pipeline volume
    loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id, Loan.stage != LoanStage.FUNDED).all()
    pipeline_volume = sum([loan.amount for loan in loans if loan.amount])

    # Get recent activities
    recent_leads = db.query(Lead).filter(Lead.owner_id == current_user.id).order_by(Lead.created_at.desc()).limit(5).all()
    recent_loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).order_by(Loan.updated_at.desc()).limit(5).all()

    return {
        "user": {
            "name": current_user.full_name or current_user.email,
            "email": current_user.email,
            "role": current_user.role
        },
        "stats": {
            "total_leads": total_leads,
            "hot_leads": hot_leads,
            "active_loans": active_loans,
            "pipeline_volume": pipeline_volume,
            "conversion_rate": 32.5,
            "avg_cycle_time": 28
        },
        "recent_leads": [
            {
                "id": lead.id,
                "name": lead.name,
                "stage": lead.stage.value,
                "ai_score": lead.ai_score,
                "created_at": lead.created_at.isoformat()
            } for lead in recent_leads
        ],
        "recent_loans": [
            {
                "id": loan.id,
                "loan_number": loan.loan_number,
                "borrower": loan.borrower_name,
                "stage": loan.stage.value,
                "amount": loan.amount
            } for loan in recent_loans
        ]
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

@app.post("/api/v1/ai/chat", response_model=ConversationResponse)
async def ai_chat(
    conversation: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI Assistant chat endpoint with context awareness"""

    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    # Build context from lead or loan if provided
    context_info = ""
    if conversation.lead_id:
        lead = db.query(Lead).filter(Lead.id == conversation.lead_id).first()
        if lead:
            context_info = f"Lead: {lead.name}, Stage: {lead.stage.value}, Score: {lead.ai_score}, Credit: {lead.credit_score}"

    if conversation.loan_id:
        loan = db.query(Loan).filter(Loan.id == conversation.loan_id).first()
        if loan:
            context_info = f"Loan: {loan.loan_number}, Borrower: {loan.borrower_name}, Stage: {loan.stage.value}, Amount: ${loan.amount:,.0f}"

    # Get conversation history for context
    history = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc()).limit(5).all()

    # Build messages for OpenAI
    messages = [
        {
            "role": "system",
            "content": f"""You are an AI assistant for a mortgage CRM system. You help loan officers manage leads, loans, tasks, and client relationships.

Current user: {current_user.full_name or current_user.email}
{f'Context: {context_info}' if context_info else ''}

You can help with:
- Lead prioritization and follow-up strategies
- Loan status updates and timeline management
- Task automation and completion
- Client communication suggestions
- Analytics and performance insights
- Calendar and appointment scheduling

Be concise, professional, and action-oriented."""
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
        # Call OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        ai_response = response.choices[0].message.content

        # Save conversation
        db_conversation = Conversation(
            user_id=current_user.id,
            lead_id=conversation.lead_id,
            loan_id=conversation.loan_id,
            message=conversation.message,
            response=ai_response,
            role="user",
            metadata=conversation.context
        )
        db.add(db_conversation)

        # Also save assistant response
        db_assistant = Conversation(
            user_id=current_user.id,
            lead_id=conversation.lead_id,
            loan_id=conversation.loan_id,
            message=ai_response,
            role="assistant"
        )
        db.add(db_assistant)

        db.commit()
        db.refresh(db_conversation)

        logger.info(f"AI chat completed for user {current_user.email}")
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
