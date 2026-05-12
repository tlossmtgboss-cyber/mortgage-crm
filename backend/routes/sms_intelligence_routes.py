"""
SMS Intelligence System Routes
Perennia AI - Advanced SMS/Text Message Processing Engine

This system provides enterprise-grade SMS intelligence:
1. SMS import from telephony providers (Telnyx)
2. Intelligent disposition engine with AI categorization
3. Document mention tracking
4. Conversation intelligence & summaries
5. Opt-out compliance management
6. Fast SLA tracking (minutes, not hours)
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, desc, and_, or_, func
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timezone, timedelta, time as dt_time
from enum import Enum
import logging
import json
import re
import os

from database import get_db, Base, engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/sms-intelligence", tags=["sms-intelligence"],
    dependencies=[Depends(_get_current_user())],
)

# Separate router for unauthenticated webhook endpoints
webhook_router = APIRouter(
    prefix="/api/v1/sms-intelligence", tags=["sms-intelligence-webhooks"],
)


# ================================================================
# ENUMS
# ================================================================

class SMSDirection(str, Enum):
    INBOUND = "inbound"    # From borrower/client TO us
    OUTBOUND = "outbound"  # From us TO borrower/client


class SMSDisposition(str, Enum):
    PENDING_REVIEW = "pending_review"
    GENERAL_CORRESPONDENCE = "general_correspondence"
    DOCUMENT_MENTION = "document_mention"
    APPOINTMENT_RELATED = "appointment_related"
    STATUS_INQUIRY = "status_inquiry"
    ACTION_REQUIRED = "action_required"
    OPT_OUT = "opt_out"
    SKIP = "skip"
    PROCESSED = "processed"


class SMSIntent(str, Enum):
    QUESTION = "question"
    CONFIRMATION = "confirmation"
    DOCUMENT_MENTION = "document_mention"
    COMPLAINT = "complaint"
    THANK_YOU = "thank_you"
    STATUS_CHECK = "status_check"
    APPOINTMENT = "appointment"
    OPT_OUT = "opt_out"
    GENERAL = "general"


class SMSSLAType(str, Enum):
    IMMEDIATE = "immediate"    # 5 min - Urgent/opt-out
    STANDARD = "standard"      # 30 min - Normal business
    LOW_PRIORITY = "low_priority"  # 2 hours - FYI/confirmation


# ================================================================
# DATABASE TABLE CREATION
# ================================================================

def ensure_sms_intelligence_tables_exist():
    """Create SMS intelligence tables if they don't exist"""
    try:
        with engine.connect() as conn:
            # 1. SMS Intelligence Queue - Main inbox for SMS processing
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_intelligence_queue (
                    id SERIAL PRIMARY KEY,

                    -- Source
                    sms_provider VARCHAR(50),
                    provider_message_id VARCHAR(255),

                    -- Phone Numbers
                    from_phone VARCHAR(20),
                    to_phone VARCHAR(20),

                    -- Direction
                    direction VARCHAR(20),

                    -- Content
                    message_body TEXT,

                    -- MMS (attachments)
                    has_media BOOLEAN DEFAULT FALSE,
                    media_count INTEGER DEFAULT 0,
                    media_urls JSONB,
                    media_types JSONB,
                    media_s3_keys JSONB DEFAULT '[]'::jsonb,

                    -- Timestamps
                    sent_at TIMESTAMP WITH TIME ZONE,
                    received_at TIMESTAMP WITH TIME ZONE,
                    imported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    -- AI Analysis
                    ai_analysis JSONB,
                    analyzed_at TIMESTAMP WITH TIME ZONE,

                    -- Matching
                    matched_borrower_id INTEGER,
                    matched_loan_id INTEGER,
                    matched_lead_id INTEGER,
                    match_method VARCHAR(50),
                    match_confidence NUMERIC(3, 2),

                    -- Disposition
                    disposition VARCHAR(50) DEFAULT 'pending_review',

                    -- Processing
                    processed_by INTEGER,
                    processed_at TIMESTAMP WITH TIME ZONE,
                    processing_notes TEXT,

                    -- Flags
                    is_priority BOOLEAN DEFAULT FALSE,
                    requires_response BOOLEAN DEFAULT FALSE,
                    is_opt_out BOOLEAN DEFAULT FALSE,

                    -- Status
                    status VARCHAR(50) DEFAULT 'pending',
                    error_message TEXT,

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sms_queue_status ON sms_intelligence_queue(status);
                CREATE INDEX IF NOT EXISTS idx_sms_queue_disposition ON sms_intelligence_queue(disposition);
                CREATE INDEX IF NOT EXISTS idx_sms_queue_from_phone ON sms_intelligence_queue(from_phone);
                CREATE INDEX IF NOT EXISTS idx_sms_queue_to_phone ON sms_intelligence_queue(to_phone);
                CREATE INDEX IF NOT EXISTS idx_sms_queue_direction ON sms_intelligence_queue(direction);
                CREATE INDEX IF NOT EXISTS idx_sms_queue_user_id ON sms_intelligence_queue(user_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sms_queue_provider_msg ON sms_intelligence_queue(sms_provider, provider_message_id);
            """))

            # Add media_s3_keys column if table pre-exists without it
            conn.execute(text("""
                ALTER TABLE sms_intelligence_queue
                ADD COLUMN IF NOT EXISTS media_s3_keys JSONB DEFAULT '[]'::jsonb
            """))

            # 2. SMS Conversation Log - AI summaries linked to borrower profiles
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_conversation_log (
                    id SERIAL PRIMARY KEY,

                    -- Entity links
                    borrower_id INTEGER,
                    loan_id INTEGER,
                    lead_id INTEGER,

                    -- Source SMS
                    sms_queue_id INTEGER REFERENCES sms_intelligence_queue(id),

                    -- Phone info
                    phone_number VARCHAR(20),
                    direction VARCHAR(20),

                    -- Message content
                    message_body TEXT,
                    message_date TIMESTAMP WITH TIME ZONE,

                    -- AI Summary
                    summary TEXT,
                    intent VARCHAR(100),

                    -- Extracted info
                    key_info JSONB,
                    documents_mentioned JSONB,
                    dates_mentioned JSONB,

                    -- Sentiment
                    sentiment VARCHAR(50),
                    urgency_level INTEGER,

                    -- Action tracking
                    requires_response BOOLEAN DEFAULT FALSE,
                    response_sent BOOLEAN DEFAULT FALSE,
                    response_sent_at TIMESTAMP WITH TIME ZONE,

                    -- Metadata
                    created_by VARCHAR(100),
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sms_conv_log_borrower ON sms_conversation_log(borrower_id);
                CREATE INDEX IF NOT EXISTS idx_sms_conv_log_loan ON sms_conversation_log(loan_id);
                CREATE INDEX IF NOT EXISTS idx_sms_conv_log_lead ON sms_conversation_log(lead_id);
                CREATE INDEX IF NOT EXISTS idx_sms_conv_log_phone ON sms_conversation_log(phone_number);
                CREATE INDEX IF NOT EXISTS idx_sms_conv_log_date ON sms_conversation_log(message_date);
            """))

            # 3. SMS Document Mentions - Track document mentions in SMS
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_document_mentions (
                    id SERIAL PRIMARY KEY,

                    -- Entity links
                    loan_id INTEGER,
                    lead_id INTEGER,
                    borrower_id INTEGER,

                    -- Source
                    sms_queue_id INTEGER REFERENCES sms_intelligence_queue(id),

                    -- Document info
                    document_mentioned VARCHAR(255),
                    document_type VARCHAR(100),

                    -- Context
                    mention_context TEXT,
                    mentioned_at TIMESTAMP WITH TIME ZONE,

                    -- Status
                    status VARCHAR(50) DEFAULT 'mentioned',

                    -- Follow-up
                    follow_up_date TIMESTAMP WITH TIME ZONE,
                    followed_up BOOLEAN DEFAULT FALSE,

                    -- Receipt tracking
                    received_date TIMESTAMP WITH TIME ZONE,
                    received_via VARCHAR(50),
                    linked_document_id INTEGER,

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sms_doc_mention_loan ON sms_document_mentions(loan_id);
                CREATE INDEX IF NOT EXISTS idx_sms_doc_mention_lead ON sms_document_mentions(lead_id);
                CREATE INDEX IF NOT EXISTS idx_sms_doc_mention_status ON sms_document_mentions(status);
            """))

            # 4. SMS SLA Tracking - Track response times (in minutes for SMS)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_sla_tracking (
                    id SERIAL PRIMARY KEY,

                    -- Link to SMS
                    sms_queue_id INTEGER REFERENCES sms_intelligence_queue(id),

                    -- Phone conversation tracking
                    phone_number VARCHAR(20),

                    -- SLA details
                    sla_type VARCHAR(50),
                    sla_minutes INTEGER,

                    -- Timing
                    message_received_at TIMESTAMP WITH TIME ZONE,
                    response_due_at TIMESTAMP WITH TIME ZONE,
                    response_sent_at TIMESTAMP WITH TIME ZONE,

                    -- Status
                    status VARCHAR(50),
                    breach_notified BOOLEAN DEFAULT FALSE,

                    -- Metrics
                    response_time_minutes NUMERIC(10, 2),

                    -- Assignment
                    assigned_to INTEGER,

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sms_sla_status ON sms_sla_tracking(status);
                CREATE INDEX IF NOT EXISTS idx_sms_sla_due ON sms_sla_tracking(response_due_at);
                CREATE INDEX IF NOT EXISTS idx_sms_sla_phone ON sms_sla_tracking(phone_number);
            """))

            # 5. SMS Templates - Quick response templates
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_templates (
                    id SERIAL PRIMARY KEY,

                    name VARCHAR(255) NOT NULL,
                    category VARCHAR(100),

                    template_body TEXT NOT NULL,

                    -- Variables available: {borrower_name}, {loan_number}, {lo_name}, etc.
                    variables_used JSONB,

                    -- Usage tracking
                    times_used INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP WITH TIME ZONE,

                    -- Status
                    is_active BOOLEAN DEFAULT TRUE,

                    -- User ownership
                    created_by INTEGER,
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sms_template_category ON sms_templates(category);
                CREATE INDEX IF NOT EXISTS idx_sms_template_active ON sms_templates(is_active);
            """))

            # 6. SMS Opt-Outs - Track opt-out requests for compliance
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_opt_outs (
                    id SERIAL PRIMARY KEY,

                    phone_number VARCHAR(20) NOT NULL,

                    -- Source
                    opt_out_sms_id INTEGER REFERENCES sms_intelligence_queue(id),
                    opt_out_message TEXT,

                    -- Timing
                    opted_out_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    -- Linked entities (if known)
                    borrower_id INTEGER,
                    loan_id INTEGER,
                    lead_id INTEGER,

                    -- Compliance
                    confirmed BOOLEAN DEFAULT TRUE,
                    confirmation_sent BOOLEAN DEFAULT FALSE,
                    confirmation_sent_at TIMESTAMP WITH TIME ZONE,

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_sms_opt_out_phone_user ON sms_opt_outs(phone_number, user_id);
                CREATE INDEX IF NOT EXISTS idx_sms_opt_out_phone ON sms_opt_outs(phone_number);
            """))

            # 7. Known Client Phones - Cache of all known client phone numbers
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS known_client_phones (
                    id SERIAL PRIMARY KEY,

                    phone_number VARCHAR(20) NOT NULL,

                    -- Entity links
                    contact_id INTEGER,
                    loan_id INTEGER,
                    lead_id INTEGER,

                    -- Source of this phone
                    source_type VARCHAR(50),
                    source_id INTEGER,

                    -- Metadata
                    client_name VARCHAR(255),
                    is_primary BOOLEAN DEFAULT FALSE,
                    phone_type VARCHAR(20),  -- mobile, home, work

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(phone_number, user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_known_client_phone ON known_client_phones(phone_number);
                CREATE INDEX IF NOT EXISTS idx_known_client_phone_user ON known_client_phones(user_id);
            """))

            conn.commit()
            logger.info("SMS intelligence tables created successfully")

    except SQLAlchemyError as e:
        logger.error(f"Error creating SMS intelligence tables: {e}")
        raise


# Issue 6 FIX: DDL auto-create guarded by environment variable.
# In production, tables should be created via migration scripts.
if os.getenv("AUTO_CREATE_TABLES", "").lower() == "true":
    try:
        ensure_sms_intelligence_tables_exist()
    except SQLAlchemyError as e:
        logger.warning(f"Could not auto-create SMS intelligence tables: {e}")


# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class SMSAnalysisResult(BaseModel):
    """AI analysis of an SMS message"""
    direction: str
    disposition: str
    confidence: float = Field(ge=0, le=1)

    summary: str
    intent: str

    documents_mentioned: List[str] = []
    dates_mentioned: List[Dict[str, Any]] = []

    extracted_data: Dict[str, Any] = {}

    sentiment: str
    urgency_level: int = Field(ge=1, le=5)

    requires_response: bool = False
    is_opt_out: bool = False


class SMSQueueItem(BaseModel):
    """SMS message in the queue"""
    id: int
    sms_provider: Optional[str]
    provider_message_id: Optional[str]
    from_phone: str
    to_phone: str
    direction: str
    message_body: str
    has_media: bool = False
    media_count: int = 0
    sent_at: Optional[datetime]
    received_at: Optional[datetime]
    ai_analysis: Optional[Dict[str, Any]]
    matched_borrower_id: Optional[int]
    matched_loan_id: Optional[int]
    matched_lead_id: Optional[int]
    match_confidence: Optional[float]
    disposition: str
    status: str
    is_priority: bool = False
    requires_response: bool = False
    is_opt_out: bool = False
    created_at: datetime

    # Joined data
    borrower_name: Optional[str] = None
    loan_number: Optional[str] = None
    lead_name: Optional[str] = None


class SMSImportRequest(BaseModel):
    """Request to import SMS from provider"""
    provider: str = "telnyx"
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    direction: Optional[str] = None  # inbound, outbound, or both
    limit: int = Field(default=100, le=500)


class SMSDispositionUpdate(BaseModel):
    """Update SMS disposition"""
    sms_id: int
    disposition: str
    processing_notes: Optional[str] = None
    matched_loan_id: Optional[int] = None
    matched_lead_id: Optional[int] = None
    matched_borrower_id: Optional[int] = None


class SMSConversationEntry(BaseModel):
    """Conversation log entry"""
    id: int
    phone_number: str
    direction: str
    message_body: str
    message_date: datetime
    summary: Optional[str]
    intent: Optional[str]
    sentiment: Optional[str]
    requires_response: bool = False
    response_sent: bool = False


class SMSTemplateCreate(BaseModel):
    """Create SMS template"""
    name: str
    category: str
    template_body: str
    variables_used: Optional[List[str]] = None


class SMSTemplateResponse(BaseModel):
    """SMS template response"""
    id: int
    name: str
    category: str
    template_body: str
    variables_used: Optional[List[str]]
    times_used: int
    is_active: bool


class SMSSendRequest(BaseModel):
    """Request to send SMS"""
    to_phone: str
    message: str
    template_id: Optional[int] = None
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    contact_id: Optional[int] = None


class OptOutCheckResponse(BaseModel):
    """Response for opt-out check"""
    phone_number: str
    is_opted_out: bool
    opted_out_at: Optional[datetime] = None


# ================================================================
# HELPER FUNCTIONS
# ================================================================

def normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format"""
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # If 10 digits, assume US and add +1
    if len(digits) == 10:
        return f"+1{digits}"
    # If 11 digits starting with 1, add +
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    # Otherwise return with + prefix
    elif not digits.startswith('+'):
        return f"+{digits}"
    return phone


# ================================================================
# TCPA COMPLIANCE FOR SMS (CC-003)
# ================================================================

TCPA_SMS_START = dt_time(8, 0)   # 8:00 AM
TCPA_SMS_END = dt_time(21, 0)    # 9:00 PM


def _check_sms_tcpa_hours(phone: str) -> tuple:
    """
    Check if current time is within TCPA allowed hours (8AM-9PM)
    in the recipient's local timezone based on area code.
    Returns (is_allowed: bool, reason: str).
    """
    try:
        from routes.voicemail_drop_routes import _get_recipient_timezone
    except ImportError:
        # Fallback: inline area code lookup for the most common timezones
        _get_recipient_timezone = None

    try:
        import pytz
    except ImportError:
        # If pytz not available, allow the send (fail open for SMS)
        return True, ""

    # Extract area code from normalized phone (+1XXXXXXXXXX)
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]

    if _get_recipient_timezone:
        tz_name = _get_recipient_timezone(phone)
    else:
        # Minimal fallback mapping
        tz_name = "America/New_York"

    try:
        tz = pytz.timezone(tz_name)
        local_time = datetime.now(tz).time()
    except Exception as e:
        # Default to Eastern if timezone lookup fails
        logger.error(f"Error in TCPA timezone lookup: {e}")
        tz = pytz.timezone("America/New_York")
        local_time = datetime.now(tz).time()

    if local_time < TCPA_SMS_START or local_time >= TCPA_SMS_END:
        return False, (
            f"TCPA: Cannot send SMS outside 8:00 AM - 9:00 PM recipient local time. "
            f"Current time in {tz_name}: {local_time.strftime('%I:%M %p')}"
        )

    return True, ""


OPT_OUT_KEYWORDS = ['stop', 'unsubscribe', 'cancel', 'end', 'quit', 'optout', 'opt-out', 'opt out']

def is_opt_out_message(message: str) -> bool:
    """Check if message is an opt-out request"""
    message_lower = message.lower().strip()
    # Check if the message is ONLY an opt-out keyword (or starts with it)
    for keyword in OPT_OUT_KEYWORDS:
        if message_lower == keyword or message_lower.startswith(keyword + ' '):
            return True
    return False


# ================================================================
# TELNYX WEBHOOK SIGNATURE VALIDATION (Issue 3 FIX)
# ================================================================

async def _validate_telnyx_signature(request: Request) -> bool:
    """Validate Telnyx webhook signature using centralized verifier.

    Delegates to ``middleware.webhook_verification.WebhookVerifier.verify_telnyx``.
    Returns True ONLY on successful verification, False on any failure.

    SECURITY: This function is fail-closed. Any exception (missing module,
    unexpected error, invalid signature) returns False, which the caller MUST
    treat as "reject" by raising HTTPException(401).
    """
    try:
        from middleware.webhook_verification import WebhookVerifier
        await WebhookVerifier.verify_telnyx(request)
        return True  # Signature verified successfully
    except HTTPException:
        # WebhookVerifier raised 401/503 — signature invalid or verification unavailable
        return False
    except Exception as e:
        # Fail closed: any unexpected error means we cannot trust the request
        logger.error("Telnyx signature validation error: %s", e)
        return False


async def analyze_sms_with_ai(message_body: str, context: Dict[str, Any] = None) -> SMSAnalysisResult:
    """Analyze SMS message with AI"""
    # Check for opt-out first
    if is_opt_out_message(message_body):
        return SMSAnalysisResult(
            direction=context.get('direction', 'inbound') if context else 'inbound',
            disposition='opt_out',
            confidence=1.0,
            summary="Opt-out request",
            intent='opt_out',
            sentiment='neutral',
            urgency_level=5,
            requires_response=True,
            is_opt_out=True
        )

    # Try Claude AI for deeper analysis
    import os
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)

            prompt = f"""Analyze this SMS message in a mortgage/lending context and respond with JSON only:

Message: "{message_body}"

Respond with this exact JSON structure:
{{
    "intent": "one of: question, document_mention, appointment, status_update, thank_you, complaint, general",
    "disposition": "one of: status_inquiry, document_mention, appointment_related, action_required, general_correspondence",
    "sentiment": "one of: positive, neutral, negative",
    "urgency_level": 1-5,
    "requires_response": true/false,
    "summary": "brief 5-10 word summary",
    "documents_mentioned": ["list of document types if any"],
    "confidence": 0.0-1.0
}}"""

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )

            import json
            result_text = response.content[0].text.strip()
            # Extract JSON from response
            if '{' in result_text:
                json_start = result_text.index('{')
                json_end = result_text.rindex('}') + 1
                ai_result = json.loads(result_text[json_start:json_end])

                return SMSAnalysisResult(
                    direction=context.get('direction', 'inbound') if context else 'inbound',
                    disposition=ai_result.get('disposition', 'general_correspondence'),
                    confidence=ai_result.get('confidence', 0.9),
                    summary=ai_result.get('summary', 'AI analyzed message'),
                    intent=ai_result.get('intent', 'general'),
                    documents_mentioned=ai_result.get('documents_mentioned', []),
                    sentiment=ai_result.get('sentiment', 'neutral'),
                    urgency_level=ai_result.get('urgency_level', 2),
                    requires_response=ai_result.get('requires_response', False),
                    is_opt_out=False
                )

        except Exception as ai_err:
            logger.warning(f"Claude AI analysis failed, falling back to rules: {ai_err}")

    # Fallback: Rule-based analysis
    message_lower = message_body.lower()

    # Determine intent
    intent = 'general'
    disposition = 'general_correspondence'
    urgency = 2
    requires_response = False

    # Document mentions
    doc_keywords = ['w2', 'w-2', 'tax', 'paystub', 'pay stub', 'bank statement',
                    'driver license', 'id', 'insurance', 'appraisal', 'doc', 'document',
                    'send', 'sending', 'attached', 'upload']
    if any(kw in message_lower for kw in doc_keywords):
        intent = 'document_mention'
        disposition = 'document_mention'
        urgency = 3

    # Questions
    if '?' in message_body or any(q in message_lower for q in ['when', 'what', 'how', 'why', 'where', 'can you', 'could you']):
        intent = 'question'
        disposition = 'status_inquiry'
        urgency = 3
        requires_response = True

    # Appointments
    if any(kw in message_lower for kw in ['appointment', 'schedule', 'meeting', 'call', 'available', 'time']):
        intent = 'appointment'
        disposition = 'appointment_related'
        urgency = 3
        requires_response = True

    # Complaints/Urgency
    if any(kw in message_lower for kw in ['urgent', 'asap', 'immediately', 'problem', 'issue', 'help', 'frustrated']):
        urgency = 4
        disposition = 'action_required'
        requires_response = True

    # Thank you
    if any(kw in message_lower for kw in ['thank', 'thanks', 'appreciate']):
        intent = 'thank_you'
        urgency = 1

    # Sentiment
    sentiment = 'neutral'
    if any(kw in message_lower for kw in ['great', 'awesome', 'perfect', 'thanks', 'thank you', 'appreciate']):
        sentiment = 'positive'
    elif any(kw in message_lower for kw in ['frustrated', 'angry', 'upset', 'disappointed', 'problem', 'issue']):
        sentiment = 'negative'

    # Extract documents mentioned
    documents_mentioned = []
    doc_patterns = [
        (r'w-?2', 'W-2'),
        (r'tax return', 'Tax Return'),
        (r'pay ?stub', 'Pay Stub'),
        (r'bank statement', 'Bank Statement'),
        (r'driver.?s? ?license', 'Driver License'),
        (r'insurance', 'Insurance'),
        (r'appraisal', 'Appraisal'),
    ]
    for pattern, doc_name in doc_patterns:
        if re.search(pattern, message_lower):
            documents_mentioned.append(doc_name)

    return SMSAnalysisResult(
        direction=context.get('direction', 'inbound') if context else 'inbound',
        disposition=disposition,
        confidence=0.75,
        summary=f"{intent.replace('_', ' ').title()} message" + (f" mentioning {', '.join(documents_mentioned)}" if documents_mentioned else ""),
        intent=intent,
        documents_mentioned=documents_mentioned,
        sentiment=sentiment,
        urgency_level=urgency,
        requires_response=requires_response,
        is_opt_out=False
    )


async def match_sms_to_entity(phone_number: str, db: Session, user_id: int, organization_id: Optional[int] = None) -> Dict[str, Any]:
    """Try to match a phone number to a borrower/loan/lead (tenant-isolated)."""
    normalized = normalize_phone(phone_number)

    # Check known_client_phones first
    result = db.execute(text("""
        SELECT contact_id, loan_id, lead_id, client_name
        FROM known_client_phones
        WHERE phone_number = :phone AND user_id = :user_id
        LIMIT 1
    """), {"phone": normalized, "user_id": user_id}).fetchone()

    if result:
        return {
            "matched_borrower_id": result[0],
            "matched_loan_id": result[1],
            "matched_lead_id": result[2],
            "match_method": "phone_exact",
            "match_confidence": 1.0,
            "client_name": result[3]
        }

    # SECURITY: org_filter is a code-defined constant, not user-derived input
    org_filter = "AND organization_id = :org_id" if organization_id else ""
    params = {"phone": normalized}
    if organization_id:
        params["org_id"] = organization_id

    # Check loans table by borrower phone
    try:
        result = db.execute(text(f"""
            SELECT id, borrower_name, loan_number
            FROM loans
            WHERE borrower_phone = :phone {org_filter}
            LIMIT 1
        """), params).fetchone()

        if result:
            return {
                "matched_borrower_id": None,
                "matched_loan_id": result[0],
                "matched_lead_id": None,
                "match_method": "loan_phone",
                "match_confidence": 0.95,
                "client_name": result[1]
            }
    except Exception as e:
        logger.error(f"Error matching phone to loan borrower: {e}")

    # Check leads table
    try:
        result = db.execute(text(f"""
            SELECT id, name
            FROM leads
            WHERE phone = :phone {org_filter}
            LIMIT 1
        """), params).fetchone()

        if result:
            return {
                "matched_borrower_id": None,
                "matched_loan_id": None,
                "matched_lead_id": result[0],
                "match_method": "lead_phone",
                "match_confidence": 0.9,
                "client_name": result[1]
            }
    except Exception as e:
        logger.error(f"Error matching phone to lead: {e}")

    return {
        "matched_borrower_id": None,
        "matched_loan_id": None,
        "matched_lead_id": None,
        "match_method": None,
        "match_confidence": 0,
        "client_name": None
    }


# ================================================================
# API ENDPOINTS
# ================================================================

# Issue 1 FIX: All GET endpoints now inject current_user and filter by user_id

@router.get("/queue")
async def get_sms_queue(
    status: Optional[str] = Query(None),
    disposition: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    phone: Optional[str] = Query(None),
    is_priority: Optional[bool] = Query(None),
    requires_response: Optional[bool] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Get SMS messages in the queue with filters"""
    try:
        # Build query - simplified without complex joins
        query = """
            SELECT
                s.*,
                l.borrower_name as loan_borrower_name,
                l.loan_number,
                ld.name as lead_name
            FROM sms_intelligence_queue s
            LEFT JOIN loans l ON s.matched_loan_id = l.id
            LEFT JOIN leads ld ON s.matched_lead_id = ld.id
            WHERE s.user_id = :user_id
        """
        params = {"user_id": current_user.id}

        if status:
            query += " AND s.status = :status"
            params["status"] = status

        if disposition:
            query += " AND s.disposition = :disposition"
            params["disposition"] = disposition

        if direction:
            query += " AND s.direction = :direction"
            params["direction"] = direction

        if phone:
            normalized = normalize_phone(phone)
            query += " AND (s.from_phone = :phone OR s.to_phone = :phone)"
            params["phone"] = normalized

        if is_priority is not None:
            query += " AND s.is_priority = :is_priority"
            params["is_priority"] = is_priority

        if requires_response is not None:
            query += " AND s.requires_response = :requires_response"
            params["requires_response"] = requires_response

        # Count total
        count_query = f"SELECT COUNT(*) FROM ({query}) sq"
        total = db.execute(text(count_query), params).scalar()

        # Add ordering and pagination
        query += " ORDER BY s.is_priority DESC, s.sent_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        results = db.execute(text(query), params).fetchall()

        items = []
        for row in results:
            items.append({
                "id": row[0],
                "sms_provider": row[1],
                "provider_message_id": row[2],
                "from_phone": row[3],
                "to_phone": row[4],
                "direction": row[5],
                "message_body": row[6],
                "has_media": row[7],
                "media_count": row[8],
                "media_urls": row[9],
                "media_types": row[10],
                "sent_at": row[11].isoformat() if row[11] else None,
                "received_at": row[12].isoformat() if row[12] else None,
                "imported_at": row[13].isoformat() if row[13] else None,
                "ai_analysis": row[14],
                "analyzed_at": row[15].isoformat() if row[15] else None,
                "matched_borrower_id": row[16],
                "matched_loan_id": row[17],
                "matched_lead_id": row[18],
                "match_method": row[19],
                "match_confidence": float(row[20]) if row[20] else None,
                "disposition": row[21],
                "processed_by": row[22],
                "processed_at": row[23].isoformat() if row[23] else None,
                "processing_notes": row[24],
                "is_priority": row[25],
                "requires_response": row[26],
                "is_opt_out": row[27],
                "status": row[28],
                "error_message": row[29],
                "user_id": row[30],
                "created_at": row[31].isoformat() if row[31] else None,
                "borrower_name": row[33] if len(row) > 33 else None,
                "loan_number": row[34] if len(row) > 34 else None,
                "lead_name": row[35] if len(row) > 35 else None,
            })

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error getting SMS queue: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/queue/{sms_id}")
async def get_sms_detail(
    sms_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Get detailed view of a single SMS"""
    try:
        result = db.execute(text("""
            SELECT
                s.*,
                l.borrower_name as loan_borrower_name,
                l.loan_number,
                ld.name as lead_name
            FROM sms_intelligence_queue s
            LEFT JOIN loans l ON s.matched_loan_id = l.id
            LEFT JOIN leads ld ON s.matched_lead_id = ld.id
            WHERE s.id = :sms_id AND s.user_id = :user_id
        """), {"sms_id": sms_id, "user_id": current_user.id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="SMS not found")

        return {
            "id": result[0],
            "sms_provider": result[1],
            "provider_message_id": result[2],
            "from_phone": result[3],
            "to_phone": result[4],
            "direction": result[5],
            "message_body": result[6],
            "has_media": result[7],
            "media_count": result[8],
            "media_urls": result[9],
            "media_types": result[10],
            "sent_at": result[11].isoformat() if result[11] else None,
            "received_at": result[12].isoformat() if result[12] else None,
            "ai_analysis": result[14],
            "matched_borrower_id": result[16],
            "matched_loan_id": result[17],
            "matched_lead_id": result[18],
            "match_confidence": float(result[20]) if result[20] else None,
            "disposition": result[21],
            "status": result[28],
            "is_priority": result[25],
            "requires_response": result[26],
            "is_opt_out": result[27],
            "borrower_name": result[33] if len(result) > 33 else None,
            "loan_number": result[34] if len(result) > 34 else None,
            "lead_name": result[35] if len(result) > 35 else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SMS detail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Issue 2 FIX: Write/delete endpoints now verify ownership via user_id

@router.delete("/queue/{sms_id}")
async def delete_sms_from_queue(
    sms_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Delete an SMS from the queue"""
    try:
        # Check if SMS exists AND belongs to current user
        result = db.execute(text("""
            SELECT id FROM sms_intelligence_queue WHERE id = :sms_id AND user_id = :user_id
        """), {"sms_id": sms_id, "user_id": current_user.id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="SMS not found")

        # Delete the SMS (ownership already verified above)
        db.execute(text("""
            DELETE FROM sms_intelligence_queue WHERE id = :sms_id AND user_id = :user_id
        """), {"sms_id": sms_id, "user_id": current_user.id})
        db.commit()

        return {"status": "success", "message": f"SMS {sms_id} deleted"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error deleting SMS: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/queue/{sms_id}/analyze")
async def analyze_sms(
    sms_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Run AI analysis on an SMS message"""
    try:
        # Get the SMS - verify ownership
        result = db.execute(text("""
            SELECT message_body, direction, from_phone
            FROM sms_intelligence_queue
            WHERE id = :sms_id AND user_id = :user_id
        """), {"sms_id": sms_id, "user_id": current_user.id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="SMS not found")

        message_body = result[0]
        direction = result[1]

        # Analyze
        analysis = await analyze_sms_with_ai(message_body, {"direction": direction})

        # Update the record - verify ownership
        db.execute(text("""
            UPDATE sms_intelligence_queue
            SET ai_analysis = :analysis,
                analyzed_at = CURRENT_TIMESTAMP,
                disposition = :disposition,
                requires_response = :requires_response,
                is_opt_out = :is_opt_out,
                is_priority = :is_priority,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :sms_id AND user_id = :user_id
        """), {
            "sms_id": sms_id,
            "user_id": current_user.id,
            "analysis": json.dumps(analysis.dict()),
            "disposition": analysis.disposition,
            "requires_response": analysis.requires_response,
            "is_opt_out": analysis.is_opt_out,
            "is_priority": analysis.urgency_level >= 4
        })
        db.commit()

        return {"success": True, "analysis": analysis.dict()}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error analyzing SMS: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/queue/{sms_id}/disposition")
async def update_sms_disposition(
    sms_id: int,
    update: SMSDispositionUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Update SMS disposition and matching"""
    try:
        # Issue 2 FIX: verify ownership via user_id
        db.execute(text("""
            UPDATE sms_intelligence_queue
            SET disposition = :disposition,
                processing_notes = COALESCE(:notes, processing_notes),
                matched_loan_id = COALESCE(:loan_id, matched_loan_id),
                matched_lead_id = COALESCE(:lead_id, matched_lead_id),
                matched_borrower_id = COALESCE(:borrower_id, matched_borrower_id),
                processed_at = CURRENT_TIMESTAMP,
                processed_by = :processed_by,
                status = CASE WHEN :disposition IN ('processed', 'skip', 'opt_out') THEN 'completed' ELSE status END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :sms_id AND user_id = :user_id
        """), {
            "sms_id": sms_id,
            "user_id": current_user.id,
            "processed_by": current_user.id,
            "disposition": update.disposition,
            "notes": update.processing_notes,
            "loan_id": update.matched_loan_id,
            "lead_id": update.matched_lead_id,
            "borrower_id": update.matched_borrower_id
        })
        db.commit()

        return {"success": True, "sms_id": sms_id, "disposition": update.disposition}

    except SQLAlchemyError as e:
        logger.error(f"Error updating SMS disposition: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/conversation/{phone_number}")
async def get_sms_conversation(
    phone_number: str,
    loan_id: Optional[int] = Query(None),
    lead_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Get conversation history for a phone number"""
    try:
        normalized = normalize_phone(phone_number)

        # Issue 1 FIX: filter by user_id
        query = """
            SELECT
                id, phone_number, direction, message_body, message_date,
                summary, intent, sentiment, requires_response, response_sent
            FROM sms_conversation_log
            WHERE phone_number = :phone AND user_id = :user_id
        """
        params = {"phone": normalized, "user_id": current_user.id}

        if loan_id:
            query += " AND loan_id = :loan_id"
            params["loan_id"] = loan_id

        if lead_id:
            query += " AND lead_id = :lead_id"
            params["lead_id"] = lead_id

        query += " ORDER BY message_date DESC LIMIT :limit"
        params["limit"] = limit

        results = db.execute(text(query), params).fetchall()

        conversations = []
        for row in results:
            conversations.append({
                "id": row[0],
                "phone_number": row[1],
                "direction": row[2],
                "message_body": row[3],
                "message_date": row[4].isoformat() if row[4] else None,
                "summary": row[5],
                "intent": row[6],
                "sentiment": row[7],
                "requires_response": row[8],
                "response_sent": row[9]
            })

        return {"phone_number": normalized, "conversations": conversations}

    except Exception as e:
        logger.error(f"Error getting SMS conversation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/templates")
async def get_sms_templates(
    category: Optional[str] = Query(None),
    is_active: bool = Query(True),
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Get SMS templates"""
    try:
        # Issue 1 FIX: filter by user_id
        query = "SELECT * FROM sms_templates WHERE is_active = :is_active AND user_id = :user_id"
        params = {"is_active": is_active, "user_id": current_user.id}

        if category:
            query += " AND category = :category"
            params["category"] = category

        query += " ORDER BY times_used DESC, name"

        results = db.execute(text(query), params).fetchall()

        templates = []
        for row in results:
            templates.append({
                "id": row[0],
                "name": row[1],
                "category": row[2],
                "template_body": row[3],
                "variables_used": row[4],
                "times_used": row[5],
                "last_used_at": row[6].isoformat() if row[6] else None,
                "is_active": row[7]
            })

        return {"templates": templates}

    except Exception as e:
        logger.error(f"Error getting SMS templates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/templates")
async def create_sms_template(
    template: SMSTemplateCreate,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Create a new SMS template"""
    try:
        result = db.execute(text("""
            INSERT INTO sms_templates (name, category, template_body, variables_used, user_id, created_by)
            VALUES (:name, :category, :body, :variables, :user_id, :user_id)
            RETURNING id
        """), {
            "name": template.name,
            "category": template.category,
            "body": template.template_body,
            "variables": json.dumps(template.variables_used) if template.variables_used else None,
            "user_id": current_user.id,
        })
        template_id = result.fetchone()[0]
        db.commit()

        return {"success": True, "template_id": template_id}

    except SQLAlchemyError as e:
        logger.error(f"Error creating SMS template: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/opt-out/check/{phone_number}")
async def check_opt_out(
    phone_number: str,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Check if a phone number has opted out"""
    try:
        normalized = normalize_phone(phone_number)

        # Issue 1 FIX: filter by user_id
        result = db.execute(text("""
            SELECT phone_number, opted_out_at
            FROM sms_opt_outs
            WHERE phone_number = :phone AND user_id = :user_id
            LIMIT 1
        """), {"phone": normalized, "user_id": current_user.id}).fetchone()

        if result:
            return {
                "phone_number": normalized,
                "is_opted_out": True,
                "opted_out_at": result[1].isoformat() if result[1] else None
            }

        return {
            "phone_number": normalized,
            "is_opted_out": False,
            "opted_out_at": None
        }

    except Exception as e:
        logger.error(f"Error checking opt-out: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/opt-outs")
async def get_opt_outs(
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Get list of opted-out phone numbers"""
    try:
        # Issue 1 FIX: filter by user_id
        results = db.execute(text("""
            SELECT phone_number, opted_out_at, opt_out_message, borrower_id, loan_id, lead_id
            FROM sms_opt_outs
            WHERE user_id = :user_id
            ORDER BY opted_out_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset, "user_id": current_user.id}).fetchall()

        opt_outs = []
        for row in results:
            opt_outs.append({
                "phone_number": row[0],
                "opted_out_at": row[1].isoformat() if row[1] else None,
                "opt_out_message": row[2],
                "borrower_id": row[3],
                "loan_id": row[4],
                "lead_id": row[5]
            })

        total = db.execute(text(
            "SELECT COUNT(*) FROM sms_opt_outs WHERE user_id = :user_id"
        ), {"user_id": current_user.id}).scalar()

        return {
            "opt_outs": opt_outs,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except SQLAlchemyError as e:
        logger.error(f"Error getting opt-outs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/opt-out/{phone_number}")
async def add_opt_out(
    phone_number: str,
    message: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Manually add a phone number to opt-out list"""
    try:
        normalized = normalize_phone(phone_number)

        # Issue 4 FIX: Include user_id in INSERT so ON CONFLICT (phone_number, user_id) can match.
        # Previously user_id was NULL, causing ON CONFLICT to never match (NULL != NULL in PG).
        db.execute(text("""
            INSERT INTO sms_opt_outs (phone_number, opt_out_message, user_id)
            VALUES (:phone, :message, :user_id)
            ON CONFLICT (phone_number, user_id) DO UPDATE SET opted_out_at = CURRENT_TIMESTAMP
        """), {"phone": normalized, "message": message, "user_id": current_user.id})
        db.commit()

        return {"success": True, "phone_number": normalized, "is_opted_out": True}

    except SQLAlchemyError as e:
        logger.error(f"Error adding opt-out: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/opt-out/{phone_number}")
async def remove_opt_out(
    phone_number: str,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Remove a phone number from opt-out list (re-subscribe)"""
    try:
        normalized = normalize_phone(phone_number)

        # Issue 2 FIX: verify ownership via user_id
        db.execute(text("""
            DELETE FROM sms_opt_outs WHERE phone_number = :phone AND user_id = :user_id
        """), {"phone": normalized, "user_id": current_user.id})
        db.commit()

        return {"success": True, "phone_number": normalized, "is_opted_out": False}

    except SQLAlchemyError as e:
        logger.error(f"Error removing opt-out: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/document-mentions")
async def get_document_mentions(
    loan_id: Optional[int] = Query(None),
    lead_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Get document mentions from SMS messages"""
    try:
        # Issue 1 FIX: filter by user_id
        query = """
            SELECT
                dm.*,
                s.message_body as sms_message,
                s.from_phone
            FROM sms_document_mentions dm
            LEFT JOIN sms_intelligence_queue s ON dm.sms_queue_id = s.id
            WHERE dm.user_id = :user_id
        """
        params = {"user_id": current_user.id}

        if loan_id:
            query += " AND dm.loan_id = :loan_id"
            params["loan_id"] = loan_id

        if lead_id:
            query += " AND dm.lead_id = :lead_id"
            params["lead_id"] = lead_id

        if status:
            query += " AND dm.status = :status"
            params["status"] = status

        query += " ORDER BY dm.mentioned_at DESC LIMIT :limit"
        params["limit"] = limit

        results = db.execute(text(query), params).fetchall()

        mentions = []
        for row in results:
            mentions.append({
                "id": row[0],
                "loan_id": row[1],
                "lead_id": row[2],
                "borrower_id": row[3],
                "sms_queue_id": row[4],
                "document_mentioned": row[5],
                "document_type": row[6],
                "mention_context": row[7],
                "mentioned_at": row[8].isoformat() if row[8] else None,
                "status": row[9],
                "follow_up_date": row[10].isoformat() if row[10] else None,
                "followed_up": row[11],
                "received_date": row[12].isoformat() if row[12] else None,
                "received_via": row[13]
            })

        return {"document_mentions": mentions}

    except Exception as e:
        logger.error(f"Error getting document mentions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sla/pending")
async def get_pending_sla(
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Get SMS messages with pending SLA (awaiting response)"""
    try:
        # Issue 1 FIX: filter by user_id
        results = db.execute(text("""
            SELECT
                st.*,
                sq.message_body,
                sq.from_phone,
                sq.to_phone,
                sq.direction
            FROM sms_sla_tracking st
            JOIN sms_intelligence_queue sq ON st.sms_queue_id = sq.id
            WHERE st.status = 'pending' AND st.user_id = :user_id
            ORDER BY st.response_due_at ASC
        """), {"user_id": current_user.id}).fetchall()

        pending = []
        for row in results:
            pending.append({
                "id": row[0],
                "sms_queue_id": row[1],
                "phone_number": row[2],
                "sla_type": row[3],
                "sla_minutes": row[4],
                "message_received_at": row[5].isoformat() if row[5] else None,
                "response_due_at": row[6].isoformat() if row[6] else None,
                "status": row[8],
                "message_body": row[12] if len(row) > 12 else None,
                "from_phone": row[13] if len(row) > 13 else None,
                "direction": row[15] if len(row) > 15 else None
            })

        return {"pending_sla": pending, "count": len(pending)}

    except Exception as e:
        logger.error(f"Error getting pending SLA: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_sms_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Get SMS intelligence statistics"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Issue 1 FIX: filter by user_id on all stats queries
        # Total counts
        total_result = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE direction = 'inbound') as inbound,
                COUNT(*) FILTER (WHERE direction = 'outbound') as outbound,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE requires_response = true AND status = 'pending') as needs_response,
                COUNT(*) FILTER (WHERE is_opt_out = true) as opt_outs,
                COUNT(*) FILTER (WHERE is_priority = true AND status = 'pending') as priority_pending
            FROM sms_intelligence_queue
            WHERE created_at >= :cutoff AND user_id = :user_id
        """), {"cutoff": cutoff, "user_id": current_user.id}).fetchone()

        # Disposition breakdown
        disposition_result = db.execute(text("""
            SELECT disposition, COUNT(*) as count
            FROM sms_intelligence_queue
            WHERE created_at >= :cutoff AND user_id = :user_id
            GROUP BY disposition
            ORDER BY count DESC
        """), {"cutoff": cutoff, "user_id": current_user.id}).fetchall()

        # SLA stats
        sla_result = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'met') as met,
                COUNT(*) FILTER (WHERE status = 'breached') as breached,
                AVG(response_time_minutes) as avg_response_minutes
            FROM sms_sla_tracking
            WHERE created_at >= :cutoff AND user_id = :user_id
        """), {"cutoff": cutoff, "user_id": current_user.id}).fetchone()

        return {
            "period_days": days,
            "totals": {
                "total": total_result[0],
                "inbound": total_result[1],
                "outbound": total_result[2],
                "pending": total_result[3],
                "completed": total_result[4],
                "needs_response": total_result[5],
                "opt_outs": total_result[6],
                "priority_pending": total_result[7]
            },
            "disposition_breakdown": [
                {"disposition": row[0], "count": row[1]}
                for row in disposition_result
            ],
            "sla": {
                "total_tracked": sla_result[0],
                "met": sla_result[1],
                "breached": sla_result[2],
                "avg_response_minutes": float(sla_result[3]) if sla_result[3] else None
            }
        }

    except Exception as e:
        logger.error(f"Error getting SMS stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Issue 3 FIX: Webhook uses separate unauthenticated router with Telnyx signature validation
@webhook_router.post("/webhook/telnyx")
async def telephony_sms_webhook(
    request: Request,
    request_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Webhook endpoint for incoming SMS with Telnyx signature validation"""
    # SECURITY: Fail-closed webhook validation — reject unless signature is positively verified
    if not await _validate_telnyx_signature(request):
        logger.warning("Rejected SMS webhook: invalid Telnyx signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        # Extract webhook data (form-encoded)
        message_sid = request_data.get("MessageSid")
        from_phone = request_data.get("From")
        to_phone = request_data.get("To")
        body = request_data.get("Body", "")
        num_media = int(request_data.get("NumMedia", 0))

        # Collect media URLs if present
        media_urls = []
        media_types = []
        for i in range(num_media):
            media_url = request_data.get(f"MediaUrl{i}")
            media_type = request_data.get(f"MediaContentType{i}")
            if media_url:
                media_urls.append(media_url)
            if media_type:
                media_types.append(media_type)

        # Persist MMS media to S3 (Telnyx URLs are temporary)
        media_s3_keys = []
        if media_urls:
            try:
                from utils.media_storage import get_media_storage
                import mimetypes as _mt
                storage = get_media_storage()
                for idx, murl in enumerate(media_urls):
                    ct = media_types[idx] if idx < len(media_types) else ""
                    ext = _mt.guess_extension(ct) or ".bin"
                    fname = f"intel_inbound_{idx}{ext}"
                    s3_key = storage.store_from_url(murl, fname)
                    if s3_key:
                        media_s3_keys.append(s3_key)
            except Exception as media_err:
                logger.warning(f"MMS media S3 persistence failed: {media_err}")

        # Insert into queue (with S3 keys for persisted media)
        result = db.execute(text("""
            INSERT INTO sms_intelligence_queue (
                sms_provider, provider_message_id, from_phone, to_phone,
                direction, message_body, has_media, media_count,
                media_urls, media_types, media_s3_keys,
                received_at, status
            ) VALUES (
                'telnyx', :message_sid, :from_phone, :to_phone,
                'inbound', :body, :has_media, :media_count,
                :media_urls, :media_types, :media_s3_keys,
                CURRENT_TIMESTAMP, 'pending'
            )
            ON CONFLICT (sms_provider, provider_message_id) DO NOTHING
            RETURNING id
        """), {
            "message_sid": message_sid,
            "from_phone": normalize_phone(from_phone),
            "to_phone": normalize_phone(to_phone),
            "body": body,
            "has_media": num_media > 0,
            "media_count": num_media,
            "media_urls": json.dumps(media_urls) if media_urls else None,
            "media_types": json.dumps(media_types) if media_types else None,
            "media_s3_keys": json.dumps(media_s3_keys) if media_s3_keys else "[]",
        })

        new_id = result.fetchone()
        db.commit()

        if new_id:
            # Schedule background analysis - don't pass db, task creates its own
            background_tasks.add_task(process_incoming_sms, new_id[0])

        return {"success": True, "message_id": new_id[0] if new_id else None}

    except SQLAlchemyError as e:
        logger.error(f"Error processing SMS webhook: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_incoming_sms(sms_id: int):
    """Background task to process an incoming SMS - creates its own db session"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        # Get the SMS
        result = db.execute(text("""
            SELECT message_body, direction, from_phone, user_id
            FROM sms_intelligence_queue
            WHERE id = :sms_id
        """), {"sms_id": sms_id}).fetchone()

        if not result:
            return

        message_body = result[0]
        direction = result[1]
        from_phone = result[2]
        user_id = result[3]

        # Analyze the message
        analysis = await analyze_sms_with_ai(message_body, {"direction": direction})

        # Match to entity
        match = await match_sms_to_entity(from_phone, db, user_id) if user_id else {}

        # Update the record
        db.execute(text("""
            UPDATE sms_intelligence_queue
            SET ai_analysis = :analysis,
                analyzed_at = CURRENT_TIMESTAMP,
                disposition = :disposition,
                requires_response = :requires_response,
                is_opt_out = :is_opt_out,
                is_priority = :is_priority,
                matched_borrower_id = :borrower_id,
                matched_loan_id = :loan_id,
                matched_lead_id = :lead_id,
                match_method = :match_method,
                match_confidence = :match_confidence,
                status = CASE WHEN :is_opt_out THEN 'completed' ELSE 'analyzed' END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :sms_id
        """), {
            "sms_id": sms_id,
            "analysis": json.dumps(analysis.dict()),
            "disposition": analysis.disposition,
            "requires_response": analysis.requires_response,
            "is_opt_out": analysis.is_opt_out,
            "is_priority": analysis.urgency_level >= 4,
            "borrower_id": match.get("matched_borrower_id"),
            "loan_id": match.get("matched_loan_id"),
            "lead_id": match.get("matched_lead_id"),
            "match_method": match.get("match_method"),
            "match_confidence": match.get("match_confidence")
        })

        # If opt-out, add to opt-out list
        if analysis.is_opt_out:
            db.execute(text("""
                INSERT INTO sms_opt_outs (phone_number, opt_out_sms_id, opt_out_message, borrower_id, loan_id, lead_id, user_id)
                VALUES (:phone, :sms_id, :message, :borrower_id, :loan_id, :lead_id, :user_id)
                ON CONFLICT (phone_number, user_id) DO UPDATE SET opted_out_at = CURRENT_TIMESTAMP
            """), {
                "phone": from_phone,
                "sms_id": sms_id,
                "message": message_body,
                "borrower_id": match.get("matched_borrower_id"),
                "loan_id": match.get("matched_loan_id"),
                "lead_id": match.get("matched_lead_id"),
                "user_id": user_id
            })

        # Create SLA tracking if response required
        if analysis.requires_response:
            sla_minutes = 5 if analysis.is_opt_out else (30 if analysis.urgency_level >= 3 else 120)
            sla_type = "immediate" if analysis.is_opt_out else ("standard" if analysis.urgency_level >= 3 else "low_priority")

            db.execute(text("""
                INSERT INTO sms_sla_tracking (
                    sms_queue_id, phone_number, sla_type, sla_minutes,
                    message_received_at, response_due_at, status, user_id
                ) VALUES (
                    :sms_id, :phone, :sla_type, :sla_minutes,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '1 minute' * :sla_minutes,
                    'pending', :user_id
                )
            """), {
                "sms_id": sms_id,
                "phone": from_phone,
                "sla_type": sla_type,
                "sla_minutes": sla_minutes,
                "user_id": user_id
            })

        # Log to conversation
        db.execute(text("""
            INSERT INTO sms_conversation_log (
                borrower_id, loan_id, lead_id, sms_queue_id,
                phone_number, direction, message_body, message_date,
                summary, intent, sentiment, urgency_level, requires_response,
                created_by, user_id
            ) VALUES (
                :borrower_id, :loan_id, :lead_id, :sms_id,
                :phone, :direction, :message, CURRENT_TIMESTAMP,
                :summary, :intent, :sentiment, :urgency, :requires_response,
                'AI', :user_id
            )
        """), {
            "borrower_id": match.get("matched_borrower_id"),
            "loan_id": match.get("matched_loan_id"),
            "lead_id": match.get("matched_lead_id"),
            "sms_id": sms_id,
            "phone": from_phone,
            "direction": direction,
            "message": message_body,
            "summary": analysis.summary,
            "intent": analysis.intent,
            "sentiment": analysis.sentiment,
            "urgency": analysis.urgency_level,
            "requires_response": analysis.requires_response,
            "user_id": user_id
        })

        # Track document mentions
        if analysis.documents_mentioned:
            for doc in analysis.documents_mentioned:
                db.execute(text("""
                    INSERT INTO sms_document_mentions (
                        loan_id, lead_id, borrower_id, sms_queue_id,
                        document_mentioned, mention_context, mentioned_at, user_id
                    ) VALUES (
                        :loan_id, :lead_id, :borrower_id, :sms_id,
                        :doc, :context, CURRENT_TIMESTAMP, :user_id
                    )
                """), {
                    "loan_id": match.get("matched_loan_id"),
                    "lead_id": match.get("matched_lead_id"),
                    "borrower_id": match.get("matched_borrower_id"),
                    "sms_id": sms_id,
                    "doc": doc,
                    "context": message_body[:500],
                    "user_id": user_id
                })

        db.commit()
        logger.info(f"Processed incoming SMS {sms_id}: disposition={analysis.disposition}")

    except SQLAlchemyError as e:
        logger.error(f"Error processing incoming SMS {sms_id}: {e}")
        db.rollback()
    except Exception as e:
        logger.error(f"Unexpected error processing incoming SMS {sms_id}: {e}")
        db.rollback()
    finally:
        db.close()


# ================================================================
# SMS SENDING ENDPOINTS
# ================================================================

@router.post("/send")
async def send_sms(
    request: SMSSendRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """
    Send an SMS message to a phone number.

    Checks opt-out status before sending.
    Logs the message to conversation history.
    Supports template-based sending.
    """
    try:
        from integrations.sms_service import SMSClient

        sms_client = SMSClient(db, user_id=current_user.id)
        if not sms_client.enabled:
            raise HTTPException(
                status_code=503,
                detail="SMS service not configured. Set TELNYX_API_KEY and TELNYX_PHONE_NUMBER."
            )

        normalized_phone = normalize_phone(request.to_phone)

        # Check opt-out status (scoped to current user)
        opt_out_check = db.execute(text("""
            SELECT phone_number FROM sms_opt_outs
            WHERE phone_number = :phone AND organization_id = :org_id AND active = true
            LIMIT 1
        """), {"phone": normalized_phone, "org_id": current_user.organization_id}).fetchone()

        if opt_out_check:
            return {
                "success": False,
                "error": "recipient_opted_out",
                "message": f"Cannot send SMS to {normalized_phone} - recipient has opted out"
            }

        # TCPA 8AM-9PM compliance check (CC-003)
        tcpa_ok, tcpa_reason = _check_sms_tcpa_hours(normalized_phone)
        if not tcpa_ok:
            return {
                "success": False,
                "error": "tcpa_restricted",
                "message": tcpa_reason
            }

        # Get message from template if template_id provided
        message = request.message
        template_name = None

        if request.template_id:
            template = db.execute(text("""
                SELECT name, template_body, variables_used
                FROM sms_templates
                WHERE id = :template_id AND is_active = true AND user_id = :user_id
            """), {"template_id": request.template_id, "user_id": current_user.id}).fetchone()

            if template:
                template_name = template[0]
                message = template[1]

                # Update template usage
                db.execute(text("""
                    UPDATE sms_templates
                    SET times_used = times_used + 1, last_used_at = CURRENT_TIMESTAMP
                    WHERE id = :template_id AND user_id = :user_id
                """), {"template_id": request.template_id, "user_id": current_user.id})

        # Get recipient info for personalization
        recipient_name = None
        if request.loan_id:
            # Issue 5 FIX: Add organization_id filter for tenant isolation
            loan = db.execute(text("""
                SELECT borrower_name, loan_number FROM loans
                WHERE id = :loan_id AND organization_id = :org_id
            """), {"loan_id": request.loan_id, "org_id": current_user.organization_id}).fetchone()
            if loan:
                recipient_name = loan[0]
                message = message.replace("{borrower_name}", loan[0] or "")
                message = message.replace("{loan_number}", loan[1] or "")

        if request.lead_id:
            # Issue 5 FIX: Add organization_id filter for tenant isolation
            lead = db.execute(text("""
                SELECT name FROM leads
                WHERE id = :lead_id AND organization_id = :org_id
            """), {"lead_id": request.lead_id, "org_id": current_user.organization_id}).fetchone()
            if lead:
                recipient_name = lead[0]
                message = message.replace("{name}", lead[0] or "")
                message = message.replace("{borrower_name}", lead[0] or "")

        # Send the SMS
        send_result = sms_client.send_sms(normalized_phone, message)

        if not send_result["success"]:
            raise HTTPException(
                status_code=500,
                detail=send_result.get("error", "Failed to send SMS. Check telephony configuration.")
            )

        message_sid = send_result.get("message_id")

        # Write to sms_panel_messages so the SMS Archive tab can find it
        import uuid as _uuid
        from datetime import datetime as _dt
        panel_msg_id = message_sid or str(_uuid.uuid4())
        sender_name = f"{getattr(current_user, 'first_name', '') or ''} {getattr(current_user, 'last_name', '') or ''}".strip() or "System"
        try:
            db.execute(text("""
                INSERT INTO sms_panel_messages
                    (id, phone, contact_id, organization_id, direction, body,
                     sender_name, sender_user_id, status,
                     media_urls, telnyx_message_id, created_at)
                VALUES
                    (:id, :phone, :contact_id, :org_id, 'outbound', :body,
                     :sender_name, :sender_user_id, 'sent',
                     '[]'::jsonb, :telnyx_id, NOW())
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": panel_msg_id,
                "phone": normalized_phone,
                "contact_id": str(request.contact_id or request.lead_id or ""),
                "org_id": current_user.organization_id,
                "body": message,
                "sender_name": sender_name,
                "sender_user_id": current_user.id,
                "telnyx_id": message_sid,
            })
            db.commit()
        except Exception as panel_err:
            logger.warning(f"Failed to write sms_panel_messages (non-blocking): {panel_err}")
            db.rollback()

        # Log to intelligence queue (best-effort — don't lose the send record)
        sms_queue_id = None
        try:
            result = db.execute(text("""
                INSERT INTO sms_intelligence_queue (
                    sms_provider, provider_message_id, from_phone, to_phone,
                    direction, message_body, sent_at, status,
                    matched_loan_id, matched_lead_id, matched_borrower_id,
                    disposition, user_id
                ) VALUES (
                    'telnyx', :message_sid, :from_phone, :to_phone,
                    'outbound', :message, CURRENT_TIMESTAMP, 'sent',
                    :loan_id, :lead_id, :contact_id,
                    'processed', :user_id
                )
                RETURNING id
            """), {
                "message_sid": message_sid,
                "from_phone": sms_client.from_number,
                "to_phone": normalized_phone,
                "message": message,
                "loan_id": request.loan_id,
                "lead_id": request.lead_id,
                "contact_id": request.contact_id,
                "user_id": current_user.id,
            })
            sms_queue_id = result.fetchone()[0]
        except Exception as q_err:
            logger.warning(f"Failed to write sms_intelligence_queue (non-blocking): {q_err}")
            db.rollback()

        # Log to conversation (best-effort)
        try:
            db.execute(text("""
                INSERT INTO sms_conversation_log (
                    borrower_id, loan_id, lead_id, sms_queue_id,
                    phone_number, direction, message_body, message_date,
                    summary, intent, created_by, user_id
                ) VALUES (
                    :contact_id, :loan_id, :lead_id, :sms_queue_id,
                    :phone, 'outbound', :message, CURRENT_TIMESTAMP,
                    :summary, 'outreach', 'user', :user_id
                )
            """), {
                "contact_id": request.contact_id,
                "loan_id": request.loan_id,
                "lead_id": request.lead_id,
                "sms_queue_id": sms_queue_id,
                "phone": normalized_phone,
                "message": message,
                "summary": f"Outbound SMS" + (f" using template '{template_name}'" if template_name else ""),
                "user_id": current_user.id,
            })
            db.commit()
        except Exception as conv_err:
            logger.warning(f"Failed to write sms_conversation_log (non-blocking): {conv_err}")
            db.rollback()

        return {
            "success": True,
            "message_sid": message_sid,
            "sms_queue_id": sms_queue_id,
            "to_phone": normalized_phone,
            "message_length": len(message),
            "template_used": template_name
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error sending SMS: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# Issue 5 FIX: send_sms_to_loan_borrower and send_sms_to_lead now enforce tenant isolation

@router.post("/send/loan/{loan_id}")
async def send_sms_to_loan_borrower(
    loan_id: int,
    message: str,
    template_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Send SMS to a loan's borrower using their phone number"""
    try:
        # Issue 5 FIX: Add organization_id filter to prevent cross-tenant access
        loan = db.execute(text("""
            SELECT borrower_name, borrower_phone, loan_number
            FROM loans
            WHERE id = :loan_id AND organization_id = :org_id
        """), {"loan_id": loan_id, "org_id": current_user.organization_id}).fetchone()

        if not loan:
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

        if not loan[1]:
            raise HTTPException(
                status_code=400,
                detail=f"Loan {loan_id} does not have a borrower phone number"
            )

        # Use the main send endpoint
        sms_request = SMSSendRequest(
            to_phone=loan[1],
            message=message,
            template_id=template_id,
            loan_id=loan_id
        )

        from fastapi import BackgroundTasks
        return await send_sms(sms_request, BackgroundTasks(), db, current_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending SMS to loan borrower: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/send/lead/{lead_id}")
async def send_sms_to_lead(
    lead_id: int,
    message: str,
    template_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """Send SMS to a lead using their phone number"""
    try:
        # Issue 5 FIX: Add organization_id filter to prevent cross-tenant access
        lead = db.execute(text("""
            SELECT name, phone
            FROM leads
            WHERE id = :lead_id AND organization_id = :org_id
        """), {"lead_id": lead_id, "org_id": current_user.organization_id}).fetchone()

        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")

        if not lead[1]:
            raise HTTPException(
                status_code=400,
                detail=f"Lead {lead_id} does not have a phone number"
            )

        # Use the main send endpoint
        sms_request = SMSSendRequest(
            to_phone=lead[1],
            message=message,
            template_id=template_id,
            lead_id=lead_id
        )

        from fastapi import BackgroundTasks
        return await send_sms(sms_request, BackgroundTasks(), db, current_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending SMS to lead: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/send/bulk")
async def send_bulk_sms(
    recipients: List[Dict[str, Any]],
    message: str,
    template_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(_get_current_user()),
):
    """
    Send SMS to multiple recipients.

    Recipients should be a list of dicts with 'phone' and optionally 'name', 'loan_id', 'lead_id'.
    Respects opt-out status for each recipient.
    """
    try:
        from integrations.sms_service import SMSClient

        sms_client = SMSClient(db, user_id=current_user.id)
        if not sms_client.enabled:
            raise HTTPException(
                status_code=503,
                detail="SMS service not configured"
            )

        # Get template if provided
        template_body = message
        template_name = None
        if template_id:
            template = db.execute(text("""
                SELECT name, template_body FROM sms_templates
                WHERE id = :template_id AND is_active = true AND user_id = :user_id
            """), {"template_id": template_id, "user_id": current_user.id}).fetchone()
            if template:
                template_name = template[0]
                template_body = template[1]

        # Get all opted-out phones (scoped to current user)
        opt_outs = db.execute(text("""
            SELECT phone_number FROM sms_opt_outs WHERE user_id = :user_id
        """), {"user_id": current_user.id}).fetchall()
        opted_out_phones = {normalize_phone(row[0]) for row in opt_outs}

        results = {
            "sent": 0,
            "skipped_opt_out": 0,
            "failed": 0,
            "details": []
        }

        for recipient in recipients:
            phone = recipient.get("phone")
            if not phone:
                continue

            normalized = normalize_phone(phone)

            # Check opt-out
            if normalized in opted_out_phones:
                results["skipped_opt_out"] += 1
                results["details"].append({
                    "phone": normalized,
                    "status": "skipped",
                    "reason": "opted_out"
                })
                continue

            # TCPA 8AM-9PM compliance check (CC-003)
            tcpa_ok, tcpa_reason = _check_sms_tcpa_hours(normalized)
            if not tcpa_ok:
                results["failed"] += 1
                results["details"].append({
                    "phone": normalized,
                    "status": "skipped",
                    "reason": "tcpa_restricted"
                })
                continue

            # Personalize message
            personalized = template_body
            if recipient.get("name"):
                personalized = personalized.replace("{name}", recipient["name"])
                personalized = personalized.replace("{borrower_name}", recipient["name"])

            # Send
            try:
                send_result = sms_client.send_sms(normalized, personalized)
                if send_result["success"]:
                    sid = send_result.get("message_id")
                    results["sent"] += 1
                    results["details"].append({
                        "phone": normalized,
                        "status": "sent",
                        "message_sid": sid
                    })

                    # Log to queue
                    db.execute(text("""
                        INSERT INTO sms_intelligence_queue (
                            sms_provider, provider_message_id, from_phone, to_phone,
                            direction, message_body, sent_at, status, disposition, user_id
                        ) VALUES (
                            'telnyx', :sid, :from_phone, :to_phone,
                            'outbound', :message, CURRENT_TIMESTAMP, 'sent', 'processed', :user_id
                        )
                    """), {
                        "sid": sid,
                        "from_phone": sms_client.from_number,
                        "to_phone": normalized,
                        "message": personalized,
                        "user_id": current_user.id,
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "phone": normalized,
                        "status": "failed",
                        "reason": send_result.get("error", "send_failed")
                    })
            except Exception as send_error:
                results["failed"] += 1
                results["details"].append({
                    "phone": normalized,
                    "status": "failed",
                    "reason": str(send_error)
                })

        db.commit()

        return {
            "success": True,
            "template_used": template_name,
            "results": results
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error sending bulk SMS: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
