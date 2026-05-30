"""
Email Intelligence & Reconciliation System Routes
Perennia AI - Advanced Email Processing Engine

This system provides enterprise-grade email intelligence:
1. Email scraping & import from Gmail/Outlook
2. Intelligent disposition engine with AI categorization
3. Document request tracking
4. Conversation intelligence & summaries
5. Data import & mapping to leads/loans
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Numeric, ForeignKey, JSON, text, desc, and_, or_, func
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timezone, timedelta
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

router = APIRouter(prefix="/api/v1/email-intelligence", tags=["email-intelligence"])


# ================================================================
# ENUMS
# ================================================================

class EmailDirection(str, Enum):
    INBOUND = "inbound"          # From borrower/client TO us
    OUTBOUND = "outbound"        # From us TO borrower/client
    INTERNAL = "internal"        # Internal team communication
    THIRD_PARTY = "third_party"  # Title, appraiser, etc.


class EmailDisposition(str, Enum):
    PENDING_REVIEW = "pending_review"
    DATA_IMPORT = "data_import"           # Contains data to import
    DOCUMENT_REQUEST = "document_request"  # We requested docs
    DOCUMENT_RECEIVED = "document_received"  # Borrower sent docs
    STATUS_UPDATE = "status_update"        # Contains status change info
    DATE_CHANGE = "date_change"            # Contains date/deadline info
    GENERAL_CORRESPONDENCE = "general_correspondence"  # Save to email history
    ACTION_REQUIRED = "action_required"    # Needs immediate attention
    INFORMATIONAL = "informational"        # FYI only
    COMPLIANCE_FLAG = "compliance_flag"    # Regulatory/compliance related
    SKIP = "skip"                          # Not relevant, skip
    ARCHIVED = "archived"                  # Processed and archived


class ImportTargetType(str, Enum):
    NEW_LEAD = "new_lead"
    EXISTING_LEAD = "existing_lead"
    NEW_LOAN = "new_loan"
    EXISTING_LOAN = "existing_loan"
    CONTACT = "contact"
    REFERRAL_PARTNER = "referral_partner"


class SentimentScore(str, Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"
    URGENT = "urgent"


class DocumentTrackingStatus(str, Enum):
    REQUESTED = "requested"
    REMINDED = "reminded"
    RECEIVED = "received"
    VERIFIED = "verified"
    EXPIRED = "expired"


# ================================================================
# DATABASE TABLE CREATION
# ================================================================

def ensure_email_intelligence_tables_exist():
    """Create email intelligence tables if they don't exist"""
    try:
        with engine.connect() as conn:
            # 1. Email Reconciliation Queue - Main inbox for email processing
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_reconciliation_queue (
                    id SERIAL PRIMARY KEY,

                    -- Source identification
                    email_provider VARCHAR(50),
                    provider_message_id VARCHAR(500),
                    thread_id VARCHAR(500),

                    -- Email headers
                    from_email VARCHAR(255),
                    from_name VARCHAR(255),
                    to_emails JSONB,
                    cc_emails JSONB,
                    reply_to VARCHAR(255),
                    subject TEXT,

                    -- Content
                    body_preview TEXT,
                    body_full TEXT,
                    body_html TEXT,

                    -- Attachments
                    has_attachments BOOLEAN DEFAULT FALSE,
                    attachment_count INTEGER DEFAULT 0,
                    attachment_names JSONB,

                    -- Timestamps
                    sent_date TIMESTAMP WITH TIME ZONE,
                    received_date TIMESTAMP WITH TIME ZONE,
                    imported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    -- Direction & Classification
                    direction VARCHAR(50),

                    -- AI Analysis (stored as JSON)
                    ai_analysis JSONB,
                    analysis_version VARCHAR(20),
                    analyzed_at TIMESTAMP WITH TIME ZONE,

                    -- Entity Matching
                    matched_contact_id INTEGER,
                    matched_loan_id INTEGER,
                    matched_lead_id INTEGER,
                    match_method VARCHAR(50),
                    match_confidence NUMERIC(3, 2),

                    -- Disposition
                    disposition VARCHAR(50) DEFAULT 'pending_review',
                    disposition_reason TEXT,

                    -- Processing
                    processed_by INTEGER,
                    processed_at TIMESTAMP WITH TIME ZONE,
                    processing_notes TEXT,

                    -- Flags
                    is_priority BOOLEAN DEFAULT FALSE,
                    requires_response BOOLEAN DEFAULT FALSE,
                    response_due_date TIMESTAMP WITH TIME ZONE,
                    compliance_flag BOOLEAN DEFAULT FALSE,

                    -- Status
                    status VARCHAR(50) DEFAULT 'pending',
                    error_message TEXT,

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_email_queue_status ON email_reconciliation_queue(status);
                CREATE INDEX IF NOT EXISTS idx_email_queue_disposition ON email_reconciliation_queue(disposition);
                CREATE INDEX IF NOT EXISTS idx_email_queue_from_email ON email_reconciliation_queue(from_email);
                CREATE INDEX IF NOT EXISTS idx_email_queue_thread_id ON email_reconciliation_queue(thread_id);
                CREATE INDEX IF NOT EXISTS idx_email_queue_user_id ON email_reconciliation_queue(user_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_email_queue_provider_msg ON email_reconciliation_queue(email_provider, provider_message_id);
            """))

            # 2. Email Conversation Log - AI summaries linked to borrower profiles
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_conversation_log (
                    id SERIAL PRIMARY KEY,

                    -- Entity links
                    contact_id INTEGER,
                    loan_id INTEGER,
                    lead_id INTEGER,

                    -- Source email reference
                    reconciliation_email_id INTEGER REFERENCES email_reconciliation_queue(id),
                    email_subject TEXT,
                    email_date TIMESTAMP WITH TIME ZONE,

                    -- Direction
                    direction VARCHAR(50),

                    -- AI Summary
                    summary TEXT NOT NULL,
                    key_points JSONB,
                    action_items JSONB,
                    next_steps JSONB,

                    -- Document tracking
                    documents_requested JSONB,
                    documents_received JSONB,
                    documents_mentioned JSONB,

                    -- Sentiment & Context
                    sentiment VARCHAR(50),
                    urgency_level INTEGER,
                    borrower_concerns JSONB,

                    -- Metadata
                    created_by VARCHAR(100),
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_conv_log_contact ON email_conversation_log(contact_id);
                CREATE INDEX IF NOT EXISTS idx_conv_log_loan ON email_conversation_log(loan_id);
                CREATE INDEX IF NOT EXISTS idx_conv_log_lead ON email_conversation_log(lead_id);
                CREATE INDEX IF NOT EXISTS idx_conv_log_email_date ON email_conversation_log(email_date);
            """))

            # 3. Email Document Tracking - Track document requests/receipts
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_document_tracking (
                    id SERIAL PRIMARY KEY,

                    -- Entity links
                    loan_id INTEGER,
                    lead_id INTEGER,
                    contact_id INTEGER,

                    -- Document info
                    document_name VARCHAR(255) NOT NULL,
                    document_type VARCHAR(100),

                    -- Status tracking
                    status VARCHAR(50) DEFAULT 'requested',

                    -- Request details
                    requested_date TIMESTAMP WITH TIME ZONE,
                    requested_via VARCHAR(50),
                    requested_email_id INTEGER REFERENCES email_reconciliation_queue(id),

                    -- Reminder tracking
                    reminder_count INTEGER DEFAULT 0,
                    last_reminder_date TIMESTAMP WITH TIME ZONE,
                    next_reminder_date TIMESTAMP WITH TIME ZONE,

                    -- Receipt details
                    received_date TIMESTAMP WITH TIME ZONE,
                    received_via VARCHAR(50),
                    received_email_id INTEGER REFERENCES email_reconciliation_queue(id),

                    -- Verification
                    verified_by INTEGER,
                    verified_at TIMESTAMP WITH TIME ZONE,
                    verification_notes TEXT,

                    -- Link to actual document
                    document_id INTEGER,

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_doc_track_loan ON email_document_tracking(loan_id);
                CREATE INDEX IF NOT EXISTS idx_doc_track_lead ON email_document_tracking(lead_id);
                CREATE INDEX IF NOT EXISTS idx_doc_track_status ON email_document_tracking(status);
            """))

            # 4. Email Data Imports - Log of data imported from emails
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_data_imports (
                    id SERIAL PRIMARY KEY,

                    -- Source
                    reconciliation_email_id INTEGER REFERENCES email_reconciliation_queue(id),

                    -- Target
                    target_type VARCHAR(50),
                    target_id INTEGER,

                    -- Import details
                    fields_imported JSONB,
                    import_status VARCHAR(50),

                    -- Audit
                    imported_by INTEGER,
                    imported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    -- Review
                    reviewed_by INTEGER,
                    reviewed_at TIMESTAMP WITH TIME ZONE,
                    review_notes TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_data_imports_email ON email_data_imports(reconciliation_email_id);
                CREATE INDEX IF NOT EXISTS idx_data_imports_target ON email_data_imports(target_type, target_id);
            """))

            # 5. Email Thread Tracking - Track email threads/conversations
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_thread_tracking (
                    id SERIAL PRIMARY KEY,

                    thread_id VARCHAR(500) UNIQUE,
                    subject TEXT,

                    -- Participants
                    participants JSONB,

                    -- Entity links
                    contact_id INTEGER,
                    loan_id INTEGER,
                    lead_id INTEGER,

                    -- Thread stats
                    email_count INTEGER DEFAULT 0,
                    first_email_date TIMESTAMP WITH TIME ZONE,
                    last_email_date TIMESTAMP WITH TIME ZONE,

                    -- Response tracking
                    awaiting_response_from VARCHAR(50),
                    last_response_by VARCHAR(50),
                    response_overdue BOOLEAN DEFAULT FALSE,

                    -- Status
                    status VARCHAR(50) DEFAULT 'active',

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_thread_track_thread_id ON email_thread_tracking(thread_id);
                CREATE INDEX IF NOT EXISTS idx_thread_track_status ON email_thread_tracking(status);
            """))

            # 6. Email SLA Tracking - Track response times
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_sla_tracking (
                    id SERIAL PRIMARY KEY,

                    -- Link to email
                    reconciliation_email_id INTEGER REFERENCES email_reconciliation_queue(id),
                    thread_id VARCHAR(500),

                    -- SLA details
                    sla_type VARCHAR(50),
                    sla_hours INTEGER,

                    -- Timing
                    email_received_at TIMESTAMP WITH TIME ZONE,
                    response_due_at TIMESTAMP WITH TIME ZONE,
                    responded_at TIMESTAMP WITH TIME ZONE,
                    response_email_id INTEGER,

                    -- Status
                    status VARCHAR(50),
                    breach_notified BOOLEAN DEFAULT FALSE,
                    breach_notified_at TIMESTAMP WITH TIME ZONE,

                    -- Metrics
                    response_time_hours NUMERIC(10, 2),

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sla_track_status ON email_sla_tracking(status);
                CREATE INDEX IF NOT EXISTS idx_sla_track_due ON email_sla_tracking(response_due_at);
            """))

            # Add missing columns to email_sla_tracking if they don't exist
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'email_sla_tracking' AND column_name = 'responded_at'
                    ) THEN
                        ALTER TABLE email_sla_tracking ADD COLUMN responded_at TIMESTAMP WITH TIME ZONE;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'email_sla_tracking' AND column_name = 'response_email_id'
                    ) THEN
                        ALTER TABLE email_sla_tracking ADD COLUMN response_email_id INTEGER;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'email_sla_tracking' AND column_name = 'breach_notified'
                    ) THEN
                        ALTER TABLE email_sla_tracking ADD COLUMN breach_notified BOOLEAN DEFAULT FALSE;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'email_sla_tracking' AND column_name = 'breach_notified_at'
                    ) THEN
                        ALTER TABLE email_sla_tracking ADD COLUMN breach_notified_at TIMESTAMP WITH TIME ZONE;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'email_sla_tracking' AND column_name = 'response_time_hours'
                    ) THEN
                        ALTER TABLE email_sla_tracking ADD COLUMN response_time_hours NUMERIC(10, 2);
                    END IF;
                END $$;
            """))

            # 7. Known Client Emails - Cache of all known client email addresses
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS known_client_emails (
                    id SERIAL PRIMARY KEY,

                    email_address VARCHAR(255) NOT NULL,

                    -- Entity links (one email can belong to multiple entities)
                    contact_id INTEGER,
                    loan_id INTEGER,
                    lead_id INTEGER,

                    -- Source of this email
                    source_type VARCHAR(50),
                    source_id INTEGER,

                    -- Metadata
                    client_name VARCHAR(255),
                    is_primary BOOLEAN DEFAULT FALSE,

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(email_address, user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_known_client_email ON known_client_emails(email_address);
                CREATE INDEX IF NOT EXISTS idx_known_client_user ON known_client_emails(user_id);
            """))

            conn.commit()
            logger.info("✅ Email intelligence tables created successfully")

    except SQLAlchemyError as e:
        logger.error(f"❌ Error creating email intelligence tables: {e}")
        raise


# Lazy table creation - only run once on first request
_tables_ensured = False

def _ensure_tables_once():
    global _tables_ensured
    if _tables_ensured:
        return
    try:
        ensure_email_intelligence_tables_exist()
    except SQLAlchemyError as e:
        logger.warning(f"Could not auto-create email intelligence tables: {e}")
    _tables_ensured = True


# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class EmailAnalysisResult(BaseModel):
    """Complete AI analysis of an email"""
    direction: str
    disposition: str
    confidence: float = Field(ge=0, le=1)

    summary: str
    key_points: List[str] = []
    action_items: List[str] = []
    next_steps: List[str] = []

    documents_requested: List[str] = []
    documents_mentioned: List[str] = []
    documents_attached: List[str] = []

    dates_mentioned: List[Dict[str, Any]] = []
    status_changes: List[Dict[str, Any]] = []

    extracted_data: Dict[str, Any] = {}

    sentiment: str
    urgency_level: int = Field(ge=1, le=5)

    compliance_flags: List[str] = []
    regulatory_mentions: List[str] = []

    is_reply: bool = False
    thread_id: Optional[str] = None
    references_previous: bool = False

    suggested_assignee: Optional[str] = None
    suggested_tasks: List[Dict[str, Any]] = []


class DataImportMapping(BaseModel):
    """Field mapping for data import"""
    source_field: str
    target_entity: str
    target_field: str
    value: Any
    confidence: float = 0.9
    override_existing: bool = False


class ReconciliationActionRequest(BaseModel):
    """Request to disposition an email"""
    action: str  # EmailDisposition value

    # For data import
    import_target: Optional[str] = None
    target_id: Optional[int] = None
    field_mappings: List[DataImportMapping] = []
    new_status: Optional[str] = None

    # For conversation log
    save_to_conversation: bool = True
    conversation_note: Optional[str] = None

    # For document tracking
    documents_to_track: List[str] = []
    create_followup_task: bool = False
    followup_days: int = 3

    # Processing
    assign_to: Optional[int] = None
    notes: Optional[str] = None


class EmailQueueItem(BaseModel):
    """Email in the reconciliation queue"""
    id: int
    email_provider: Optional[str]
    provider_message_id: Optional[str]
    thread_id: Optional[str]

    from_email: Optional[str]
    from_name: Optional[str]
    to_emails: Optional[List[str]]
    cc_emails: Optional[List[str]]
    subject: Optional[str]

    body_preview: Optional[str]
    has_attachments: bool = False
    attachment_count: int = 0
    attachment_names: Optional[List[str]]

    sent_date: Optional[datetime]
    received_date: Optional[datetime]
    imported_at: Optional[datetime]

    direction: Optional[str]
    ai_analysis: Optional[Dict[str, Any]]

    matched_contact_id: Optional[int]
    matched_loan_id: Optional[int]
    matched_lead_id: Optional[int]
    match_confidence: Optional[float]

    disposition: Optional[str]
    status: Optional[str]
    is_priority: bool = False

    class Config:
        from_attributes = True


class ConversationLogEntry(BaseModel):
    """Entry in conversation log"""
    id: int
    contact_id: Optional[int]
    loan_id: Optional[int]
    lead_id: Optional[int]

    email_subject: Optional[str]
    email_date: Optional[datetime]
    direction: Optional[str]

    summary: str
    key_points: Optional[List[str]]
    action_items: Optional[List[str]]
    next_steps: Optional[List[str]]

    documents_requested: Optional[List[str]]
    documents_received: Optional[List[str]]

    sentiment: Optional[str]
    urgency_level: Optional[int]

    created_by: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class DocumentTrackingItem(BaseModel):
    """Document tracking item"""
    id: int
    document_name: str
    document_type: Optional[str]
    status: str

    loan_id: Optional[int]
    lead_id: Optional[int]

    requested_date: Optional[datetime]
    received_date: Optional[datetime]

    reminder_count: int = 0
    next_reminder_date: Optional[datetime]

    class Config:
        from_attributes = True


# ================================================================
# AI ANALYSIS ENGINE
# ================================================================

class EmailIntelligenceEngine:
    """AI engine for email analysis using Claude"""

    def __init__(self, db: Session):
        self.db = db
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

    async def analyze_email(
        self,
        email_data: Dict[str, Any],
        borrower_context: Optional[Dict[str, Any]] = None,
        loan_context: Optional[Dict[str, Any]] = None
    ) -> EmailAnalysisResult:
        """Comprehensive AI analysis of email for reconciliation"""

        if not self.anthropic_api_key:
            # Return basic analysis without AI
            return self._basic_analysis(email_data)

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.anthropic_api_key)

            context_info = ""
            if borrower_context:
                context_info += f"""
KNOWN BORROWER CONTEXT:
- Name: {borrower_context.get('name')}
- Email: {borrower_context.get('email')}
- Phone: {borrower_context.get('phone')}
- Status: {borrower_context.get('status')}
"""

            if loan_context:
                context_info += f"""
KNOWN LOAN CONTEXT:
- Loan Number: {loan_context.get('loan_number')}
- Stage: {loan_context.get('stage')}
- Loan Amount: {loan_context.get('loan_amount')}
- Property: {loan_context.get('property_address')}
- Closing Date: {loan_context.get('closing_date')}
"""

            prompt = f"""You are an expert mortgage loan processor analyzing emails for a CRM system.

Analyze this email comprehensively and provide structured data for reconciliation.

EMAIL DETAILS:
From: {email_data.get('from_email')} ({email_data.get('from_name', 'Unknown')})
To: {email_data.get('to_emails')}
CC: {email_data.get('cc_emails', [])}
Subject: {email_data.get('subject')}
Date: {email_data.get('sent_date')}
Has Attachments: {email_data.get('has_attachments')} ({email_data.get('attachment_names', [])})

BODY:
{email_data.get('body_preview', email_data.get('body_full', ''))}

{context_info}

ANALYZE AND RESPOND WITH ONLY VALID JSON:
{{
    "direction": "inbound|outbound|internal|third_party",
    "disposition": "pending_review|data_import|document_request|document_received|status_update|date_change|general_correspondence|action_required|informational|compliance_flag|skip",
    "confidence": 0.0-1.0,

    "summary": "2-3 sentence summary for conversation log",
    "key_points": ["point 1", "point 2"],
    "action_items": ["action 1", "action 2"],
    "next_steps": ["step 1", "step 2"],

    "documents_requested": ["doc name if we requested documents"],
    "documents_mentioned": ["docs discussed in email"],
    "documents_attached": ["docs attached to email"],

    "dates_mentioned": [
        {{"date": "2025-01-15", "context": "closing date", "is_deadline": true}}
    ],
    "status_changes": [
        {{"field": "loan_status", "old_value": null, "new_value": "Clear to Close"}}
    ],

    "extracted_data": {{
        "borrower_first_name": "extracted value or null",
        "borrower_last_name": "extracted value or null",
        "borrower_email": "extracted value or null",
        "borrower_phone": "extracted value or null",
        "property_address": "extracted value or null",
        "loan_amount": "extracted value or null",
        "loan_number": "extracted value or null"
    }},

    "sentiment": "very_positive|positive|neutral|negative|very_negative|urgent",
    "urgency_level": 1-5,

    "compliance_flags": ["any regulatory concerns"],
    "regulatory_mentions": ["TRID", "RESPA", etc if mentioned],

    "is_reply": true/false,
    "thread_id": "extracted thread ID if present",
    "references_previous": true/false,

    "suggested_assignee": "role or null",
    "suggested_tasks": []
}}

DO NOT OUTPUT ANYTHING OTHER THAN VALID JSON."""

            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text
            response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()

            analysis_data = json.loads(response_text)
            return EmailAnalysisResult(**analysis_data)

        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return self._basic_analysis(email_data)

    def _basic_analysis(self, email_data: Dict[str, Any]) -> EmailAnalysisResult:
        """Fallback basic analysis without AI"""
        return EmailAnalysisResult(
            direction="inbound",
            disposition="pending_review",
            confidence=0.5,
            summary=f"Email from {email_data.get('from_email', 'unknown')}: {email_data.get('subject', 'No subject')}",
            key_points=[],
            action_items=[],
            next_steps=[],
            sentiment="neutral",
            urgency_level=3,
            is_reply=False
        )

    def classify_document(self, doc_name: str) -> str:
        """Classify document type from name"""
        doc_lower = doc_name.lower()

        if 'w2' in doc_lower or 'w-2' in doc_lower:
            return 'w2'
        elif 'paystub' in doc_lower or 'pay stub' in doc_lower:
            return 'paystub'
        elif 'bank' in doc_lower and 'statement' in doc_lower:
            return 'bank_statement'
        elif 'tax' in doc_lower and 'return' in doc_lower:
            return 'tax_return'
        elif 'id' in doc_lower or 'license' in doc_lower or 'passport' in doc_lower:
            return 'identification'
        elif 'insurance' in doc_lower:
            return 'insurance'
        elif 'appraisal' in doc_lower:
            return 'appraisal'
        elif 'title' in doc_lower:
            return 'title'
        else:
            return 'other'


# ================================================================
# HELPER FUNCTIONS
# ================================================================

async def get_current_user_id(
    request: Request,
    db: Session = Depends(get_db),
) -> int:
    """Extract authenticated user ID from JWT token."""
    from auth.dependencies import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    user = await get_current_user_flexible(token=token, request=request, db=db)
    return user.id


async def get_current_admin_user_id(
    request: Request,
    db: Session = Depends(get_db),
) -> int:
    """Extract authenticated admin user ID. Raises 403 if not platform admin."""
    from auth.dependencies import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    user = await get_current_user_flexible(token=token, request=request, db=db)
    if not getattr(user, "is_platform_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user.id


# ================================================================
# API ENDPOINTS
# ================================================================

@router.get("/queue")
async def get_email_queue(
    status: Optional[str] = Query("pending", description="Filter by status"),
    disposition: Optional[str] = Query(None, description="Filter by disposition"),
    direction: Optional[str] = Query(None, description="Filter by direction"),
    has_match: Optional[bool] = Query(None, description="Filter by match status"),
    priority_only: bool = Query(False, description="Only priority emails"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Get emails in reconciliation queue
    """
    _ensure_tables_once()

    # Build query
    query = """
        SELECT
            id, email_provider, provider_message_id, thread_id,
            from_email, from_name, to_emails, cc_emails, subject,
            body_preview, has_attachments, attachment_count, attachment_names,
            sent_date, received_date, imported_at,
            direction, ai_analysis,
            matched_contact_id, matched_loan_id, matched_lead_id, match_confidence,
            disposition, status, is_priority
        FROM email_reconciliation_queue
        WHERE user_id = :user_id
    """
    params = {"user_id": user_id}

    if status:
        query += " AND status = :status"
        params["status"] = status

    if disposition:
        query += " AND disposition = :disposition"
        params["disposition"] = disposition

    if direction:
        query += " AND direction = :direction"
        params["direction"] = direction

    if has_match is not None:
        if has_match:
            query += """ AND (matched_contact_id IS NOT NULL
                        OR matched_loan_id IS NOT NULL
                        OR matched_lead_id IS NOT NULL)"""
        else:
            query += """ AND matched_contact_id IS NULL
                        AND matched_loan_id IS NULL
                        AND matched_lead_id IS NULL"""

    if priority_only:
        query += " AND is_priority = TRUE"

    # Get total count
    count_query = f"SELECT COUNT(*) FROM ({query}) sq"
    total = db.execute(text(count_query), params).scalar()

    # Add ordering and pagination
    query += " ORDER BY is_priority DESC, received_date DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    result = db.execute(text(query), params).fetchall()

    emails = []
    for row in result:
        emails.append({
            "id": row[0],
            "email_provider": row[1],
            "provider_message_id": row[2],
            "thread_id": row[3],
            "from_email": row[4],
            "from_name": row[5],
            "to_emails": row[6],
            "cc_emails": row[7],
            "subject": row[8],
            "body_preview": row[9],
            "has_attachments": row[10],
            "attachment_count": row[11],
            "attachment_names": row[12],
            "sent_date": str(row[13]) if row[13] else None,
            "received_date": str(row[14]) if row[14] else None,
            "imported_at": str(row[15]) if row[15] else None,
            "direction": row[16],
            "ai_analysis": row[17],
            "matched_contact_id": row[18],
            "matched_loan_id": row[19],
            "matched_lead_id": row[20],
            "match_confidence": float(row[21]) if row[21] else None,
            "disposition": row[22],
            "status": row[23],
            "is_priority": row[24]
        })

    return {
        "total": total,
        "emails": emails,
        "limit": limit,
        "offset": offset
    }


@router.get("/queue/{email_id}")
async def get_email_detail(
    email_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get single email with full details"""

    result = db.execute(text("""
        SELECT
            id, email_provider, provider_message_id, thread_id,
            from_email, from_name, to_emails, cc_emails, subject,
            body_preview, body_full, body_html,
            has_attachments, attachment_count, attachment_names,
            sent_date, received_date, imported_at,
            direction, ai_analysis, analyzed_at,
            matched_contact_id, matched_loan_id, matched_lead_id,
            match_method, match_confidence,
            disposition, disposition_reason,
            processed_by, processed_at, processing_notes,
            is_priority, requires_response, response_due_date,
            compliance_flag, status, error_message
        FROM email_reconciliation_queue
        WHERE id = :email_id AND user_id = :user_id
    """), {"email_id": email_id, "user_id": user_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Email not found")

    return {
        "id": result[0],
        "email_provider": result[1],
        "provider_message_id": result[2],
        "thread_id": result[3],
        "from_email": result[4],
        "from_name": result[5],
        "to_emails": result[6],
        "cc_emails": result[7],
        "subject": result[8],
        "body_preview": result[9],
        "body_full": result[10],
        "body_html": result[11],
        "has_attachments": result[12],
        "attachment_count": result[13],
        "attachment_names": result[14],
        "sent_date": str(result[15]) if result[15] else None,
        "received_date": str(result[16]) if result[16] else None,
        "imported_at": str(result[17]) if result[17] else None,
        "direction": result[18],
        "ai_analysis": result[19],
        "analyzed_at": str(result[20]) if result[20] else None,
        "matched_contact_id": result[21],
        "matched_loan_id": result[22],
        "matched_lead_id": result[23],
        "match_method": result[24],
        "match_confidence": float(result[25]) if result[25] else None,
        "disposition": result[26],
        "disposition_reason": result[27],
        "processed_by": result[28],
        "processed_at": str(result[29]) if result[29] else None,
        "processing_notes": result[30],
        "is_priority": result[31],
        "requires_response": result[32],
        "response_due_date": str(result[33]) if result[33] else None,
        "compliance_flag": result[34],
        "status": result[35],
        "error_message": result[36]
    }


@router.delete("/queue/{email_id}")
async def delete_email_from_queue(
    email_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Delete an email from the queue"""

    # Check if email exists and belongs to user
    result = db.execute(text("""
        SELECT id FROM email_reconciliation_queue
        WHERE id = :email_id AND user_id = :user_id
    """), {"email_id": email_id, "user_id": user_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Email not found")

    # Delete the email
    db.execute(text("""
        DELETE FROM email_reconciliation_queue
        WHERE id = :email_id AND user_id = :user_id
    """), {"email_id": email_id, "user_id": user_id})
    db.commit()

    return {"status": "success", "message": f"Email {email_id} deleted"}


@router.post("/queue/{email_id}/analyze")
async def analyze_email(
    email_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Run AI analysis on email"""

    # Get email
    result = db.execute(text("""
        SELECT id, from_email, from_name, to_emails, cc_emails, subject,
               body_preview, body_full, sent_date, has_attachments, attachment_names,
               matched_contact_id, matched_loan_id, matched_lead_id
        FROM email_reconciliation_queue
        WHERE id = :email_id AND user_id = :user_id
    """), {"email_id": email_id, "user_id": user_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Email not found")

    email_data = {
        "from_email": result[1],
        "from_name": result[2],
        "to_emails": result[3],
        "cc_emails": result[4],
        "subject": result[5],
        "body_preview": result[6],
        "body_full": result[7],
        "sent_date": str(result[8]) if result[8] else None,
        "has_attachments": result[9],
        "attachment_names": result[10]
    }

    # Get context if we have matches
    borrower_context = None
    loan_context = None

    # Run AI analysis
    engine = EmailIntelligenceEngine(db)
    analysis = await engine.analyze_email(email_data, borrower_context, loan_context)

    # Save analysis
    db.execute(text("""
        UPDATE email_reconciliation_queue
        SET ai_analysis = :analysis,
            analyzed_at = :analyzed_at,
            disposition = :disposition,
            direction = :direction,
            updated_at = :updated_at
        WHERE id = :email_id
    """), {
        "analysis": json.dumps(analysis.dict()),
        "analyzed_at": datetime.now(timezone.utc),
        "disposition": analysis.disposition,
        "direction": analysis.direction,
        "updated_at": datetime.now(timezone.utc),
        "email_id": email_id
    })
    db.commit()

    return {
        "email_id": email_id,
        "analysis": analysis.dict()
    }


@router.post("/queue/{email_id}/disposition")
async def disposition_email(
    email_id: int,
    action: ReconciliationActionRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Process email disposition - save to conversation log, import data, etc.
    """

    # Get email
    result = db.execute(text("""
        SELECT id, from_email, subject, body_preview, sent_date, direction,
               ai_analysis, matched_contact_id, matched_loan_id, matched_lead_id
        FROM email_reconciliation_queue
        WHERE id = :email_id AND user_id = :user_id
    """), {"email_id": email_id, "user_id": user_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Email not found")

    email_data = {
        "id": result[0],
        "from_email": result[1],
        "subject": result[2],
        "body_preview": result[3],
        "sent_date": result[4],
        "direction": result[5],
        "ai_analysis": result[6],
        "matched_contact_id": result[7],
        "matched_loan_id": result[8],
        "matched_lead_id": result[9]
    }

    results = {
        "email_id": email_id,
        "action": action.action,
        "conversation_logged": False,
        "data_imported": False,
        "documents_tracked": 0,
        "tasks_created": 0
    }

    analysis = email_data.get("ai_analysis") or {}

    # 1. Save to conversation log if requested
    if action.save_to_conversation:
        target_contact = action.target_id or email_data.get("matched_contact_id")
        target_loan = email_data.get("matched_loan_id")
        target_lead = email_data.get("matched_lead_id")

        if target_contact or target_loan or target_lead:
            db.execute(text("""
                INSERT INTO email_conversation_log (
                    contact_id, loan_id, lead_id,
                    reconciliation_email_id, email_subject, email_date,
                    direction, summary, key_points, action_items, next_steps,
                    documents_requested, documents_received, documents_mentioned,
                    sentiment, urgency_level, created_by, user_id
                ) VALUES (
                    :contact_id, :loan_id, :lead_id,
                    :email_id, :subject, :email_date,
                    :direction, :summary, :key_points, :action_items, :next_steps,
                    :docs_requested, :docs_received, :docs_mentioned,
                    :sentiment, :urgency, :created_by, :user_id
                )
            """), {
                "contact_id": target_contact,
                "loan_id": target_loan,
                "lead_id": target_lead,
                "email_id": email_id,
                "subject": email_data.get("subject"),
                "email_date": email_data.get("sent_date"),
                "direction": email_data.get("direction"),
                "summary": action.conversation_note or analysis.get("summary", f"Email: {email_data.get('subject')}"),
                "key_points": json.dumps(analysis.get("key_points", [])),
                "action_items": json.dumps(analysis.get("action_items", [])),
                "next_steps": json.dumps(analysis.get("next_steps", [])),
                "docs_requested": json.dumps(analysis.get("documents_requested", [])),
                "docs_received": json.dumps(analysis.get("documents_attached", [])),
                "docs_mentioned": json.dumps(analysis.get("documents_mentioned", [])),
                "sentiment": analysis.get("sentiment"),
                "urgency": analysis.get("urgency_level"),
                "created_by": "AI",
                "user_id": user_id
            })
            results["conversation_logged"] = True

    # 2. Track document requests
    if action.action == "document_request" or action.documents_to_track:
        docs_to_track = action.documents_to_track or analysis.get("documents_requested", [])
        engine = EmailIntelligenceEngine(db)

        for doc_name in docs_to_track:
            db.execute(text("""
                INSERT INTO email_document_tracking (
                    loan_id, lead_id, contact_id,
                    document_name, document_type, status,
                    requested_date, requested_via, requested_email_id,
                    user_id
                ) VALUES (
                    :loan_id, :lead_id, :contact_id,
                    :doc_name, :doc_type, 'requested',
                    :requested_date, 'email', :email_id,
                    :user_id
                )
            """), {
                "loan_id": email_data.get("matched_loan_id"),
                "lead_id": email_data.get("matched_lead_id"),
                "contact_id": email_data.get("matched_contact_id"),
                "doc_name": doc_name,
                "doc_type": engine.classify_document(doc_name),
                "requested_date": datetime.now(timezone.utc),
                "email_id": email_id,
                "user_id": user_id
            })
            results["documents_tracked"] += 1

    # 3. Update email status
    db.execute(text("""
        UPDATE email_reconciliation_queue
        SET disposition = :disposition,
            status = 'processed',
            processed_at = :processed_at,
            processing_notes = :notes,
            updated_at = :updated_at
        WHERE id = :email_id
    """), {
        "disposition": action.action,
        "processed_at": datetime.now(timezone.utc),
        "notes": action.notes,
        "updated_at": datetime.now(timezone.utc),
        "email_id": email_id
    })

    db.commit()

    return results


@router.get("/conversation-log/{entity_type}/{entity_id}")
async def get_conversation_log(
    entity_type: Literal["contact", "loan", "lead"],
    entity_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get conversation log for an entity"""

    if entity_type == "contact":
        filter_col = "contact_id"
    elif entity_type == "loan":
        filter_col = "loan_id"
    else:
        filter_col = "lead_id"

    query = (
        "SELECT id, contact_id, loan_id, lead_id,"
        " email_subject, email_date, direction,"
        " summary, key_points, action_items, next_steps,"
        " documents_requested, documents_received,"
        " sentiment, urgency_level, created_by, created_at"
        " FROM email_conversation_log"
        " WHERE " + filter_col + " = :entity_id AND user_id = :user_id"
        " ORDER BY email_date DESC"
        " LIMIT :limit"
    )
    result = db.execute(text(query), {"entity_id": entity_id, "user_id": user_id, "limit": limit}).fetchall()

    entries = []
    for row in result:
        entries.append({
            "id": row[0],
            "contact_id": row[1],
            "loan_id": row[2],
            "lead_id": row[3],
            "email_subject": row[4],
            "email_date": str(row[5]) if row[5] else None,
            "direction": row[6],
            "summary": row[7],
            "key_points": row[8],
            "action_items": row[9],
            "next_steps": row[10],
            "documents_requested": row[11],
            "documents_received": row[12],
            "sentiment": row[13],
            "urgency_level": row[14],
            "created_by": row[15],
            "created_at": str(row[16]) if row[16] else None
        })

    return {"entries": entries, "total": len(entries)}


@router.get("/document-tracking/{entity_type}/{entity_id}")
async def get_document_tracking(
    entity_type: Literal["loan", "lead"],
    entity_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get document tracking for an entity"""

    filter_col = "loan_id" if entity_type == "loan" else "lead_id"

    query = f"""
        SELECT id, document_name, document_type, status,
               loan_id, lead_id, requested_date, received_date,
               reminder_count, next_reminder_date
        FROM email_document_tracking
        WHERE {filter_col} = :entity_id AND user_id = :user_id
    """
    params = {"entity_id": entity_id, "user_id": user_id}

    if status:
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY requested_date DESC"

    result = db.execute(text(query), params).fetchall()

    documents = []
    for row in result:
        documents.append({
            "id": row[0],
            "document_name": row[1],
            "document_type": row[2],
            "status": row[3],
            "loan_id": row[4],
            "lead_id": row[5],
            "requested_date": str(row[6]) if row[6] else None,
            "received_date": str(row[7]) if row[7] else None,
            "reminder_count": row[8],
            "next_reminder_date": str(row[9]) if row[9] else None
        })

    return {"documents": documents, "total": len(documents)}


@router.get("/document-tracking/all")
async def get_all_document_tracking(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get all document tracking records for the current user"""

    # First get total count
    count_query = "SELECT COUNT(*) FROM email_document_tracking WHERE user_id = :user_id"
    count_params = {"user_id": user_id}
    if status:
        count_query += " AND status = :status"
        count_params["status"] = status

    total = db.execute(text(count_query), count_params).scalar() or 0

    # Then get documents with source email info
    query = """
        SELECT edt.id, edt.document_name, edt.document_type, edt.status,
               edt.loan_id, edt.lead_id, edt.requested_date, edt.received_date,
               edt.reminder_count, edt.next_reminder_date, edt.created_at,
               eq.from_email, eq.from_name
        FROM email_document_tracking edt
        LEFT JOIN email_queue eq ON edt.received_email_id = eq.id
        WHERE edt.user_id = :user_id
    """
    params = {"user_id": user_id, "limit": limit, "offset": offset}

    if status:
        query += " AND edt.status = :status"
        params["status"] = status

    query += " ORDER BY COALESCE(edt.received_date, edt.created_at) DESC LIMIT :limit OFFSET :offset"

    result = db.execute(text(query), params).fetchall()

    documents = []
    for row in result:
        documents.append({
            "id": row[0],
            "document_name": row[1],
            "document_type": row[2],
            "status": row[3],
            "loan_id": row[4],
            "lead_id": row[5],
            "requested_date": str(row[6]) if row[6] else None,
            "received_date": str(row[7]) if row[7] else None,
            "reminder_count": row[8],
            "next_reminder_date": str(row[9]) if row[9] else None,
            "created_at": str(row[10]) if row[10] else None,
            "from_email": row[11],
            "from_name": row[12]
        })

    return {"documents": documents, "total": total}


@router.post("/document-tracking/{doc_id}/received")
async def mark_document_received(
    doc_id: int,
    received_email_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Mark a tracked document as received"""

    db.execute(text("""
        UPDATE email_document_tracking
        SET status = 'received',
            received_date = :received_date,
            received_via = 'email',
            received_email_id = :email_id,
            updated_at = :updated_at
        WHERE id = :doc_id AND user_id = :user_id
    """), {
        "received_date": datetime.now(timezone.utc),
        "email_id": received_email_id,
        "updated_at": datetime.now(timezone.utc),
        "doc_id": doc_id,
        "user_id": user_id
    })
    db.commit()

    return {"status": "success", "document_id": doc_id}


@router.get("/stats")
async def get_email_intelligence_stats(
    days: int = Query(7, le=90),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get email intelligence statistics"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Queue stats by disposition
    disposition_stats = db.execute(text("""
        SELECT disposition, COUNT(*) as count
        FROM email_reconciliation_queue
        WHERE user_id = :user_id AND imported_at >= :since
        GROUP BY disposition
    """), {"user_id": user_id, "since": since}).fetchall()

    # Queue stats by direction
    direction_stats = db.execute(text("""
        SELECT direction, COUNT(*) as count
        FROM email_reconciliation_queue
        WHERE user_id = :user_id AND imported_at >= :since
        GROUP BY direction
    """), {"user_id": user_id, "since": since}).fetchall()

    # Processing stats
    processed = db.execute(text("""
        SELECT COUNT(*) FROM email_reconciliation_queue
        WHERE user_id = :user_id AND processed_at >= :since AND status = 'processed'
    """), {"user_id": user_id, "since": since}).scalar()

    pending = db.execute(text("""
        SELECT COUNT(*) FROM email_reconciliation_queue
        WHERE user_id = :user_id AND status = 'pending'
    """), {"user_id": user_id}).scalar()

    # Conversation logs created
    logs_created = db.execute(text("""
        SELECT COUNT(*) FROM email_conversation_log
        WHERE user_id = :user_id AND created_at >= :since
    """), {"user_id": user_id, "since": since}).scalar()

    # Documents tracked
    docs_requested = db.execute(text("""
        SELECT COUNT(*) FROM email_document_tracking
        WHERE user_id = :user_id AND requested_date >= :since
    """), {"user_id": user_id, "since": since}).scalar()

    docs_received = db.execute(text("""
        SELECT COUNT(*) FROM email_document_tracking
        WHERE user_id = :user_id AND received_date >= :since
    """), {"user_id": user_id, "since": since}).scalar()

    # Identity resolution stats
    match_method_stats = db.execute(text("""
        SELECT match_method, COUNT(*) as count
        FROM email_reconciliation_queue
        WHERE user_id = :user_id AND match_method IS NOT NULL AND imported_at >= :since
        GROUP BY match_method
        ORDER BY count DESC
    """), {"user_id": user_id, "since": since}).fetchall()

    total_matched = db.execute(text("""
        SELECT COUNT(*) FROM email_reconciliation_queue
        WHERE user_id = :user_id AND imported_at >= :since
        AND (matched_contact_id IS NOT NULL OR matched_loan_id IS NOT NULL OR matched_lead_id IS NOT NULL)
    """), {"user_id": user_id, "since": since}).scalar() or 0

    total_in_period = db.execute(text("""
        SELECT COUNT(*) FROM email_reconciliation_queue
        WHERE user_id = :user_id AND imported_at >= :since
    """), {"user_id": user_id, "since": since}).scalar() or 0

    priority_count = db.execute(text("""
        SELECT COUNT(*) FROM email_reconciliation_queue
        WHERE user_id = :user_id AND is_priority = TRUE AND imported_at >= :since
    """), {"user_id": user_id, "since": since}).scalar() or 0

    known_clients = db.execute(text("""
        SELECT COUNT(*) FROM known_client_emails
        WHERE user_id = :user_id
    """), {"user_id": user_id}).scalar() or 0

    return {
        "period_days": days,
        "queue_by_disposition": {row[0]: row[1] for row in disposition_stats if row[0]},
        "queue_by_direction": {row[0]: row[1] for row in direction_stats if row[0]},
        "processed_count": processed or 0,
        "pending_count": pending or 0,
        "conversation_logs_created": logs_created or 0,
        "documents_requested": docs_requested or 0,
        "documents_received": docs_received or 0,
        "identity_resolution": {
            "total_emails": total_in_period,
            "matched": total_matched,
            "unmatched": total_in_period - total_matched,
            "match_rate": round(total_matched / total_in_period * 100, 1) if total_in_period > 0 else 0,
            "priority_count": priority_count,
            "by_method": {row[0]: row[1] for row in match_method_stats},
            "known_clients_count": known_clients
        }
    }


@router.post("/import-email")
async def import_email_to_queue(
    email_data: Dict[str, Any],
    auto_analyze: bool = Query(True),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Import an email into the reconciliation queue

    Used by email sync services to add emails for processing
    """

    # Check for duplicate
    if email_data.get("provider_message_id"):
        existing = db.execute(text("""
            SELECT id FROM email_reconciliation_queue
            WHERE email_provider = :provider AND provider_message_id = :msg_id
        """), {
            "provider": email_data.get("email_provider"),
            "msg_id": email_data.get("provider_message_id")
        }).fetchone()

        if existing:
            return {"status": "duplicate", "existing_id": existing[0]}

    # Insert email (include entity IDs if provided)
    result = db.execute(text("""
        INSERT INTO email_reconciliation_queue (
            email_provider, provider_message_id, thread_id,
            from_email, from_name, to_emails, cc_emails, subject,
            body_preview, body_full, body_html,
            has_attachments, attachment_count, attachment_names,
            sent_date, received_date, direction,
            matched_loan_id, matched_lead_id, matched_contact_id,
            match_method, match_confidence,
            status, user_id
        ) VALUES (
            :provider, :msg_id, :thread_id,
            :from_email, :from_name, :to_emails, :cc_emails, :subject,
            :body_preview, :body_full, :body_html,
            :has_attachments, :attachment_count, :attachment_names,
            :sent_date, :received_date, :direction,
            :matched_loan_id, :matched_lead_id, :matched_contact_id,
            :match_method, :match_confidence,
            'pending', :user_id
        ) RETURNING id
    """), {
        "provider": email_data.get("email_provider"),
        "msg_id": email_data.get("provider_message_id"),
        "thread_id": email_data.get("thread_id"),
        "from_email": email_data.get("from_email"),
        "from_name": email_data.get("from_name"),
        "to_emails": json.dumps(email_data.get("to_emails", [])),
        "cc_emails": json.dumps(email_data.get("cc_emails", [])),
        "subject": email_data.get("subject"),
        "body_preview": email_data.get("body_preview", "")[:500],
        "body_full": email_data.get("body_full"),
        "body_html": email_data.get("body_html"),
        "has_attachments": email_data.get("has_attachments", False),
        "attachment_count": email_data.get("attachment_count", 0),
        "attachment_names": json.dumps(email_data.get("attachment_names", [])),
        "sent_date": email_data.get("sent_date"),
        "received_date": email_data.get("received_date"),
        "direction": email_data.get("direction", "inbound"),
        "matched_loan_id": email_data.get("matched_loan_id"),
        "matched_lead_id": email_data.get("matched_lead_id"),
        "matched_contact_id": email_data.get("matched_contact_id"),
        "match_method": "manual" if email_data.get("matched_loan_id") or email_data.get("matched_lead_id") else None,
        "match_confidence": 1.0 if email_data.get("matched_loan_id") or email_data.get("matched_lead_id") else None,
        "user_id": user_id
    })

    email_id = result.fetchone()[0]
    db.commit()

    # Auto-match using full EmailIdentityResolver (only if entity IDs weren't provided)
    identity_resolution_result = None
    has_entity_match = email_data.get("matched_loan_id") or email_data.get("matched_lead_id") or email_data.get("matched_contact_id")
    if not has_entity_match and email_data.get("from_email"):
        try:
            from services.email_identity_resolver import get_email_identity_resolver

            resolver = get_email_identity_resolver(db)
            match_result = resolver.resolve(email_data, user_id)
            identity_resolution_result = {"attempted": True, "match_result": match_result}

            if match_result.get("match_method"):
                db.execute(text("""
                    UPDATE email_reconciliation_queue
                    SET matched_contact_id = :contact_id,
                        matched_loan_id = :loan_id,
                        matched_lead_id = :lead_id,
                        match_method = :method,
                        match_confidence = :confidence,
                        match_evidence = :evidence,
                        match_client_name = :client_name,
                        match_loan_number = :loan_number,
                        is_priority = :is_priority
                    WHERE id = :email_id
                """), {
                    "contact_id": match_result.get("matched_contact_id"),
                    "loan_id": match_result.get("matched_loan_id"),
                    "lead_id": match_result.get("matched_lead_id"),
                    "method": match_result.get("match_method"),
                    "confidence": match_result.get("match_confidence"),
                    "evidence": match_result.get("match_evidence"),
                    "client_name": match_result.get("match_client_name"),
                    "loan_number": match_result.get("match_loan_number"),
                    "is_priority": match_result.get("is_priority", False),
                    "email_id": email_id
                })
                db.commit()
                identity_resolution_result["update_executed"] = True
        except SQLAlchemyError as e:
            logger.error(f"Email identity resolution failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            identity_resolution_result = {"attempted": True, "error": "Internal server error"}

    # Run AI analysis if requested
    analysis = None
    if auto_analyze:
        try:
            engine = EmailIntelligenceEngine(db)
            analysis = await engine.analyze_email(email_data)

            db.execute(text("""
                UPDATE email_reconciliation_queue
                SET ai_analysis = :analysis,
                    analyzed_at = :analyzed_at,
                    disposition = :disposition,
                    direction = :direction
                WHERE id = :email_id
            """), {
                "analysis": json.dumps(analysis.dict()),
                "analyzed_at": datetime.now(timezone.utc),
                "disposition": analysis.disposition,
                "direction": analysis.direction,
                "email_id": email_id
            })
            db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Auto-analysis failed: {e}")

    return {
        "status": "imported",
        "email_id": email_id,
        "analysis": analysis.dict() if analysis else None,
        "identity_resolution": identity_resolution_result
    }


@router.post("/sync-known-clients")
async def sync_known_client_emails(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Sync all known client emails from leads, loans, and contacts

    This builds the known_client_emails lookup table for email matching
    """

    synced = 0

    # Get emails from leads — scope to this user's leads for proper user_id
    leads = db.execute(text("""
        SELECT id, email, name FROM leads
        WHERE email IS NOT NULL AND owner_id = :user_id
    """), {"user_id": user_id}).fetchall()

    lead_params = [
        {"email": lead[1].lower(), "lead_id": lead[0], "name": lead[2], "user_id": user_id}
        for lead in leads if lead[1]
    ]
    if lead_params:
        db.execute(text("""
            INSERT INTO known_client_emails (email_address, lead_id, client_name, source_type, source_id, user_id)
            VALUES (:email, :lead_id, :name, 'lead', :lead_id, :user_id)
            ON CONFLICT (email_address, user_id) DO UPDATE SET
                lead_id = COALESCE(known_client_emails.lead_id, EXCLUDED.lead_id),
                updated_at = CURRENT_TIMESTAMP
        """), lead_params)
    synced += len(lead_params)

    # Get emails from loans — scope to this user's loans
    loans = db.execute(text("""
        SELECT id, borrower_email, borrower_name FROM loans
        WHERE borrower_email IS NOT NULL AND loan_officer_id = :user_id
    """), {"user_id": user_id}).fetchall()

    loan_params = [
        {"email": loan[1].lower(), "loan_id": loan[0], "name": loan[2], "user_id": user_id}
        for loan in loans if loan[1]
    ]
    if loan_params:
        db.execute(text("""
            INSERT INTO known_client_emails (email_address, loan_id, client_name, source_type, source_id, user_id)
            VALUES (:email, :loan_id, :name, 'loan', :loan_id, :user_id)
            ON CONFLICT (email_address, user_id) DO UPDATE SET
                loan_id = COALESCE(known_client_emails.loan_id, EXCLUDED.loan_id),
                updated_at = CURRENT_TIMESTAMP
        """), loan_params)
    synced += len(loan_params)

    db.commit()

    return {
        "status": "success",
        "emails_synced": synced
    }


@router.post("/migrate-tables")
async def migrate_email_intelligence_tables(
    db: Session = Depends(get_db)
):
    """
    Create/update email intelligence tables

    Call this endpoint to ensure all tables exist
    """
    try:
        ensure_email_intelligence_tables_exist()
        return {"status": "success", "message": "Email intelligence tables created/updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# ================================================================
# HELPER FUNCTIONS FOR EXTERNAL INTEGRATION
# ================================================================

async def queue_email_for_intelligence(
    db: Session,
    user_id: int,
    email_data: Dict[str, Any],
    auto_analyze: bool = False,
    source: str = "sync"
) -> Dict[str, Any]:
    """
    Queue an email for the Email Intelligence system.

    Called by Gmail and Microsoft sync services to add ALL emails
    to the reconciliation queue for intelligent processing.

    Args:
        db: Database session
        user_id: User ID who owns the email
        email_data: Dict with email fields (from_email, subject, body, etc.)
        auto_analyze: Whether to run AI analysis immediately
        source: Source identifier (gmail_sync, microsoft_sync, manual)

    Returns:
        Dict with status, email_id, match info, and analysis (if requested)
    """
    try:
        # Check for duplicate by provider message ID
        provider = email_data.get("email_provider", source)
        msg_id = email_data.get("provider_message_id") or email_data.get("id", "")

        if msg_id:
            existing = db.execute(text("""
                SELECT id FROM email_reconciliation_queue
                WHERE email_provider = :provider AND provider_message_id = :msg_id AND user_id = :user_id
            """), {
                "provider": provider,
                "msg_id": msg_id,
                "user_id": user_id
            }).fetchone()

            if existing:
                return {"status": "duplicate", "existing_id": existing[0]}

        # Extract email fields with fallbacks
        from_email = email_data.get("from_email") or ""
        if not from_email and email_data.get("from"):
            # Handle Microsoft format: {"emailAddress": {"address": "..."}}
            if isinstance(email_data["from"], dict):
                from_email = email_data["from"].get("emailAddress", {}).get("address", "")
            else:
                from_email = email_data["from"]

        from_name = email_data.get("from_name", "")
        if not from_name and email_data.get("from") and isinstance(email_data["from"], dict):
            from_name = email_data["from"].get("emailAddress", {}).get("name", "")

        # Extract to_emails
        to_emails = email_data.get("to_emails", [])
        if not to_emails and email_data.get("toRecipients"):
            to_emails = [r.get("emailAddress", {}).get("address", "") for r in email_data["toRecipients"] if r]

        # Extract cc_emails
        cc_emails = email_data.get("cc_emails", [])
        if not cc_emails and email_data.get("ccRecipients"):
            cc_emails = [r.get("emailAddress", {}).get("address", "") for r in email_data["ccRecipients"] if r]

        # Extract body content
        body_preview = email_data.get("body_preview", "")
        body_full = email_data.get("body_full")
        body_html = email_data.get("body_html")

        if not body_preview and email_data.get("body"):
            if isinstance(email_data["body"], dict):
                content = email_data["body"].get("content", "")
                content_type = email_data["body"].get("contentType", "text")
                if content_type == "html":
                    body_html = content
                    # Strip HTML for preview
                    import re
                    body_preview = re.sub(r'<[^>]+>', ' ', content)[:500]
                else:
                    body_preview = content[:500]
                    body_full = content
            else:
                body_preview = str(email_data["body"])[:500]

        # Get dates
        sent_date = email_data.get("sent_date") or email_data.get("sentDateTime")
        received_date = email_data.get("received_date") or email_data.get("receivedDateTime")

        # Determine direction based on our email being in from/to
        direction = email_data.get("direction", "inbound")

        # Handle attachments
        has_attachments = email_data.get("has_attachments", False) or email_data.get("hasAttachments", False)
        attachment_count = email_data.get("attachment_count", 0)
        attachment_names = email_data.get("attachment_names", [])

        # Insert into queue
        result = db.execute(text("""
            INSERT INTO email_reconciliation_queue (
                email_provider, provider_message_id, thread_id,
                from_email, from_name, to_emails, cc_emails, subject,
                body_preview, body_full, body_html,
                has_attachments, attachment_count, attachment_names,
                sent_date, received_date, direction,
                status, user_id
            ) VALUES (
                :provider, :msg_id, :thread_id,
                :from_email, :from_name, :to_emails, :cc_emails, :subject,
                :body_preview, :body_full, :body_html,
                :has_attachments, :attachment_count, :attachment_names,
                :sent_date, :received_date, :direction,
                'pending', :user_id
            ) RETURNING id
        """), {
            "provider": provider,
            "msg_id": msg_id,
            "thread_id": email_data.get("thread_id") or email_data.get("conversationId"),
            "from_email": from_email,
            "from_name": from_name,
            "to_emails": json.dumps(to_emails) if isinstance(to_emails, list) else to_emails,
            "cc_emails": json.dumps(cc_emails) if isinstance(cc_emails, list) else cc_emails,
            "subject": email_data.get("subject", ""),
            "body_preview": body_preview[:500] if body_preview else "",
            "body_full": body_full,
            "body_html": body_html,
            "has_attachments": has_attachments,
            "attachment_count": attachment_count,
            "attachment_names": json.dumps(attachment_names) if isinstance(attachment_names, list) else attachment_names,
            "sent_date": sent_date,
            "received_date": received_date,
            "direction": direction,
            "user_id": user_id
        })

        email_id = result.fetchone()[0]
        db.commit()

        # Use EmailIdentityResolver for comprehensive matching
        match_info = None
        try:
            from services.email_identity_resolver import get_email_identity_resolver

            resolver = get_email_identity_resolver(db)
            match_result = resolver.resolve(email_data, user_id)

            if match_result.get("match_method"):
                # Update the queue record with match info
                db.execute(text("""
                    UPDATE email_reconciliation_queue
                    SET matched_contact_id = :contact_id,
                        matched_loan_id = :loan_id,
                        matched_lead_id = :lead_id,
                        match_method = :method,
                        match_confidence = :confidence,
                        match_evidence = :evidence,
                        match_client_name = :client_name,
                        match_loan_number = :loan_number,
                        is_priority = :is_priority
                    WHERE id = :email_id
                """), {
                    "contact_id": match_result.get("matched_contact_id"),
                    "loan_id": match_result.get("matched_loan_id"),
                    "lead_id": match_result.get("matched_lead_id"),
                    "method": match_result.get("match_method"),
                    "confidence": match_result.get("match_confidence"),
                    "evidence": match_result.get("match_evidence"),
                    "client_name": match_result.get("match_client_name"),
                    "loan_number": match_result.get("match_loan_number"),
                    "is_priority": match_result.get("is_priority", False),
                    "email_id": email_id
                })
                db.commit()

                match_info = {
                    "contact_id": match_result.get("matched_contact_id"),
                    "loan_id": match_result.get("matched_loan_id"),
                    "lead_id": match_result.get("matched_lead_id"),
                    "client_name": match_result.get("match_client_name"),
                    "loan_number": match_result.get("match_loan_number"),
                    "method": match_result.get("match_method"),
                    "confidence": match_result.get("match_confidence"),
                    "evidence": match_result.get("match_evidence"),
                    "is_priority": match_result.get("is_priority", False),
                    "vendor_type": match_result.get("vendor_type")
                }
        except SQLAlchemyError as e:
            logger.warning(f"Email identity resolution failed for email {email_id}: {e}")

        # Run AI analysis if requested
        analysis = None
        task_id = None
        if auto_analyze:
            try:
                engine = EmailIntelligenceEngine(db)
                analysis = await engine.analyze_email({
                    "from_email": from_email,
                    "from_name": from_name,
                    "subject": email_data.get("subject", ""),
                    "body_preview": body_preview,
                    "body_full": body_full
                })

                analysis_dict = analysis.dict()

                db.execute(text("""
                    UPDATE email_reconciliation_queue
                    SET ai_analysis = :analysis,
                        analyzed_at = :analyzed_at,
                        disposition = :disposition,
                        direction = :direction
                    WHERE id = :email_id
                """), {
                    "analysis": json.dumps(analysis_dict),
                    "analyzed_at": datetime.now(timezone.utc),
                    "disposition": analysis.disposition,
                    "direction": analysis.direction,
                    "email_id": email_id
                })
                db.commit()

                # RE-RUN IDENTITY RESOLUTION with extracted data if no match found initially
                if not match_info or not (match_info.get("loan_id") or match_info.get("lead_id")):
                    extracted_data = analysis_dict.get("extracted_data", {})
                    if extracted_data:
                        try:
                            from services.email_identity_resolver import get_email_identity_resolver
                            resolver = get_email_identity_resolver(db)

                            # Add extracted data to email_data for re-resolution
                            enhanced_email_data = {
                                **email_data,
                                "extracted_data": extracted_data,
                                "ai_analysis": analysis_dict
                            }

                            re_match_result = resolver.resolve(enhanced_email_data, user_id)

                            if re_match_result.get("match_method"):
                                # Update with new match info
                                db.execute(text("""
                                    UPDATE email_reconciliation_queue
                                    SET matched_contact_id = :contact_id,
                                        matched_loan_id = :loan_id,
                                        matched_lead_id = :lead_id,
                                        match_method = :method,
                                        match_confidence = :confidence,
                                        match_evidence = :evidence,
                                        match_client_name = :client_name,
                                        match_loan_number = :loan_number,
                                        is_priority = :is_priority
                                    WHERE id = :email_id
                                """), {
                                    "contact_id": re_match_result.get("matched_contact_id"),
                                    "loan_id": re_match_result.get("matched_loan_id"),
                                    "lead_id": re_match_result.get("matched_lead_id"),
                                    "method": re_match_result.get("match_method"),
                                    "confidence": re_match_result.get("match_confidence"),
                                    "evidence": re_match_result.get("match_evidence"),
                                    "client_name": re_match_result.get("match_client_name"),
                                    "loan_number": re_match_result.get("match_loan_number"),
                                    "is_priority": re_match_result.get("is_priority", False),
                                    "email_id": email_id
                                })
                                db.commit()

                                # Update match_info for downstream use
                                match_info = {
                                    "contact_id": re_match_result.get("matched_contact_id"),
                                    "loan_id": re_match_result.get("matched_loan_id"),
                                    "lead_id": re_match_result.get("matched_lead_id"),
                                    "client_name": re_match_result.get("match_client_name"),
                                    "loan_number": re_match_result.get("match_loan_number"),
                                    "method": re_match_result.get("match_method"),
                                    "confidence": re_match_result.get("match_confidence"),
                                    "evidence": re_match_result.get("match_evidence"),
                                    "is_priority": re_match_result.get("is_priority", False),
                                }
                                logger.info(f"🔍 Re-matched email {email_id} using AI-extracted data: {match_info.get('method')}")
                        except Exception as rematch_error:
                            logger.warning(f"Re-matching with AI data failed: {rematch_error}")

                # AUTO-CREATE TASK for document requests
                documents_requested = analysis_dict.get("documents_requested", [])
                action_items = analysis_dict.get("action_items", [])
                urgency = analysis_dict.get("urgency_level", 3)

                # Create task if there are document requests OR action items with high urgency
                if documents_requested or (action_items and urgency >= 4):
                    try:
                        # Build task title
                        if documents_requested:
                            task_title = f"📄 Documents Requested: {email_data.get('subject', 'Email')[:50]}"
                            task_description = f"Documents requested from {from_email}:\n\n"
                            task_description += "\n".join([f"• {doc}" for doc in documents_requested])
                        else:
                            task_title = f"⚠️ Action Required: {email_data.get('subject', 'Email')[:50]}"
                            task_description = f"Action items from email by {from_email}:\n\n"
                            task_description += "\n".join([f"• {item}" for item in action_items])

                        task_description += f"\n\nEmail Subject: {email_data.get('subject')}"
                        task_description += f"\nFrom: {from_email}"

                        # Get matched entity IDs
                        loan_id = match_info.get("loan_id") if match_info else None
                        lead_id = match_info.get("lead_id") if match_info else None

                        # Due date based on urgency
                        due_days = 1 if urgency >= 4 else 3
                        due_date = datetime.now(timezone.utc) + timedelta(days=due_days)

                        result = db.execute(text("""
                            INSERT INTO tasks (
                                title, description, due_date, priority,
                                loan_id, lead_id, assigned_to, created_by,
                                source, source_id, status, created_at
                            ) VALUES (
                                :title, :description, :due_date, :priority,
                                :loan_id, :lead_id, :assigned_to, :created_by,
                                'email_intelligence', :source_id, 'pending', :created_at
                            ) RETURNING id
                        """), {
                            "title": task_title[:255],
                            "description": task_description,
                            "due_date": due_date,
                            "priority": "high" if urgency >= 4 else "medium",
                            "loan_id": loan_id,
                            "lead_id": lead_id,
                            "assigned_to": user_id,
                            "created_by": user_id,
                            "source_id": email_id,
                            "created_at": datetime.now(timezone.utc)
                        })
                        task_id = result.fetchone()[0]
                        db.commit()
                        logger.info(f"📋 Auto-created task {task_id} for document request email {email_id}")
                    except Exception as task_error:
                        logger.warning(f"Could not auto-create task: {task_error}")

                # AUTO-CREATE CONVERSATION LOG ENTRY
                try:
                    loan_id = match_info.get("loan_id") if match_info else None
                    lead_id = match_info.get("lead_id") if match_info else None
                    client_name = match_info.get("client_name") if match_info else from_name or from_email

                    if loan_id or lead_id:
                        db.execute(text("""
                            INSERT INTO email_conversation_log (
                                email_queue_id, loan_id, lead_id, client_name,
                                direction, summary, key_points, action_items,
                                next_steps, documents_requested, documents_received,
                                sentiment, urgency_level, created_by, created_at
                            ) VALUES (
                                :email_queue_id, :loan_id, :lead_id, :client_name,
                                :direction, :summary, :key_points, :action_items,
                                :next_steps, :documents_requested, :documents_received,
                                :sentiment, :urgency_level, :created_by, :created_at
                            )
                        """), {
                            "email_queue_id": email_id,
                            "loan_id": loan_id,
                            "lead_id": lead_id,
                            "client_name": client_name,
                            "direction": analysis.direction,
                            "summary": analysis_dict.get("summary", ""),
                            "key_points": json.dumps(analysis_dict.get("key_points", [])),
                            "action_items": json.dumps(analysis_dict.get("action_items", [])),
                            "next_steps": json.dumps(analysis_dict.get("next_steps", [])),
                            "documents_requested": json.dumps(documents_requested),
                            "documents_received": json.dumps(analysis_dict.get("documents_attached", [])),
                            "sentiment": analysis_dict.get("sentiment", "neutral"),
                            "urgency_level": urgency,
                            "created_by": user_id,
                            "created_at": datetime.now(timezone.utc)
                        })
                        db.commit()
                        logger.info(f"📝 Auto-created conversation log for email {email_id} (loan={loan_id}, lead={lead_id})")
                except Exception as log_error:
                    logger.warning(f"Could not auto-create conversation log: {log_error}")

            except SQLAlchemyError as e:
                logger.warning(f"Auto-analysis failed for email {email_id}: {e}")

        return {
            "status": "queued",
            "email_id": email_id,
            "match": match_info,
            "analysis": analysis.dict() if analysis else None,
            "task_id": task_id
        }

    except Exception as e:
        logger.error(f"Error queuing email for intelligence: {e}")
        db.rollback()
        return {"status": "error", "error": "Internal server error"}


@router.post("/batch-import")
async def batch_import_emails(
    emails: List[Dict[str, Any]],
    auto_analyze: bool = Query(False),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Import multiple emails to the queue in batch.

    This is the primary endpoint for email sync services.
    """

    results = {
        "queued": 0,
        "duplicates": 0,
        "errors": 0,
        "matched": 0,
        "details": []
    }

    for email in emails:
        result = await queue_email_for_intelligence(
            db=db,
            user_id=user_id,
            email_data=email,
            auto_analyze=auto_analyze,
            source=email.get("email_provider", "batch")
        )

        if result["status"] == "queued":
            results["queued"] += 1
            if result.get("match"):
                results["matched"] += 1
        elif result["status"] == "duplicate":
            results["duplicates"] += 1
        else:
            results["errors"] += 1

        results["details"].append(result)

    return results


@router.post("/cron-sync-to-queue")
async def cron_sync_emails_to_queue(
    api_key: str = Query(..., description="API key for cron authentication"),
    days_back: int = Query(1, le=7),
    db: Session = Depends(get_db),
):
    """
    Cron endpoint to sync ALL emails from connected providers to the intelligence queue.

    Unlike the regular cron sync which only processes matching emails through DRE,
    this queues ALL emails for intelligent disposition.
    """
    import os
    import hmac

    expected_key = os.getenv("CRON_API_KEY")
    if not expected_key or not hmac.compare_digest(api_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # First, refresh known client emails
    try:
        from sqlalchemy import text

        # Bulk sync all leads and loans in 2 SELECT + 2 batch INSERT (instead of 2*N queries)
        leads = db.execute(text("""
            SELECT id, email, name, owner_id FROM leads
            WHERE email IS NOT NULL AND owner_id IS NOT NULL
        """)).fetchall()

        lead_params = [
            {"email": lead[1].lower(), "lead_id": lead[0], "name": lead[2], "user_id": lead[3]}
            for lead in leads if lead[1]
        ]
        if lead_params:
            db.execute(text("""
                INSERT INTO known_client_emails (email_address, lead_id, client_name, source_type, source_id, user_id)
                VALUES (:email, :lead_id, :name, 'lead', :lead_id, :user_id)
                ON CONFLICT (email_address, user_id) DO UPDATE SET
                    lead_id = COALESCE(known_client_emails.lead_id, EXCLUDED.lead_id),
                    updated_at = CURRENT_TIMESTAMP
            """), lead_params)

        loans = db.execute(text("""
            SELECT id, borrower_email, borrower_name, loan_officer_id FROM loans
            WHERE borrower_email IS NOT NULL AND loan_officer_id IS NOT NULL
        """)).fetchall()

        loan_params = [
            {"email": loan[1].lower(), "loan_id": loan[0], "name": loan[2], "user_id": loan[3]}
            for loan in loans if loan[1]
        ]
        if loan_params:
            db.execute(text("""
                INSERT INTO known_client_emails (email_address, loan_id, client_name, source_type, source_id, user_id)
                VALUES (:email, :loan_id, :name, 'loan', :loan_id, :user_id)
                ON CONFLICT (email_address, user_id) DO UPDATE SET
                    loan_id = COALESCE(known_client_emails.loan_id, EXCLUDED.loan_id),
                    updated_at = CURRENT_TIMESTAMP
            """), loan_params)

        total_synced = len(lead_params) + len(loan_params)

        db.commit()

        return {
            "status": "success",
            "known_clients_synced": total_synced,
            "message": "Run the provider-specific sync endpoints to queue emails"
        }

    except SQLAlchemyError as e:
        logger.error(f"Error in cron sync: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ================================================================
# PHASE 3: CONVERSATION INTELLIGENCE SERVICE
# ================================================================

class ConversationIntelligenceService:
    """
    AI-powered conversation logging and document tracking.

    Called when:
    1. Email is dispositioned in the queue
    2. Email is auto-processed by rules
    3. Manual "save to conversation log" action
    """

    def __init__(self, db: Session):
        self.db = db
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

    async def process_email_disposition(
        self,
        email_id: int,
        disposition: str,
        user_id: int,
        override_summary: Optional[str] = None,
        additional_notes: Optional[str] = None,
        create_task: bool = False,
        task_title: Optional[str] = None,
        task_due_days: int = 3
    ) -> Dict[str, Any]:
        """
        Main entry point when an email is dispositioned.

        Returns dict with:
        - conversation_log_created: bool
        - documents_tracked: int
        - sla_created: bool
        - task_created: bool
        """

        result = {
            "email_id": email_id,
            "disposition": disposition,
            "conversation_log_created": False,
            "conversation_log_id": None,
            "documents_tracked": 0,
            "document_ids": [],
            "sla_created": False,
            "sla_id": None,
            "task_created": False,
            "task_id": None,
            "errors": []
        }

        # Get the email
        email_row = self.db.execute(text("""
            SELECT id, from_email, from_name, to_emails, cc_emails, subject,
                   body_preview, body_full, sent_date, received_date,
                   has_attachments, attachment_names, direction,
                   ai_analysis, matched_contact_id, matched_loan_id, matched_lead_id,
                   thread_id
            FROM email_reconciliation_queue
            WHERE id = :email_id AND user_id = :user_id
        """), {"email_id": email_id, "user_id": user_id}).fetchone()

        if not email_row:
            result["errors"].append(f"Email {email_id} not found")
            return result

        email_data = {
            "id": email_row[0],
            "from_email": email_row[1],
            "from_name": email_row[2],
            "to_emails": email_row[3],
            "cc_emails": email_row[4],
            "subject": email_row[5],
            "body_preview": email_row[6],
            "body_full": email_row[7],
            "sent_date": email_row[8],
            "received_date": email_row[9],
            "has_attachments": email_row[10],
            "attachment_names": email_row[11],
            "direction": email_row[12],
            "ai_analysis": email_row[13],
            "matched_contact_id": email_row[14],
            "matched_loan_id": email_row[15],
            "matched_lead_id": email_row[16],
            "thread_id": email_row[17]
        }

        # Get or run AI analysis
        analysis = email_data.get("ai_analysis") or {}
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except Exception as e:
                logger.error(f"Error in process_email (parse ai_analysis JSON): {e}")
                analysis = {}

        if not analysis and self.anthropic_api_key:
            try:
                analysis = await self._run_ai_analysis(email_data)
                self.db.execute(text("""
                    UPDATE email_reconciliation_queue
                    SET ai_analysis = :analysis, analyzed_at = :analyzed_at
                    WHERE id = :email_id
                """), {
                    "analysis": json.dumps(analysis),
                    "analyzed_at": datetime.now(timezone.utc),
                    "email_id": email_id
                })
                self.db.commit()
            except SQLAlchemyError as e:
                logger.error(f"AI analysis failed for email {email_id}: {e}")
                analysis = self._basic_analysis_dict(email_data)

        # 1. Create conversation log entry (for most dispositions)
        if disposition not in ['skip', 'archived']:
            try:
                log_id = await self._create_conversation_log(
                    email_data=email_data,
                    analysis=analysis,
                    override_summary=override_summary,
                    additional_notes=additional_notes,
                    user_id=user_id
                )
                if log_id:
                    result["conversation_log_created"] = True
                    result["conversation_log_id"] = log_id
            except Exception as e:
                logger.error(f"Failed to create conversation log: {e}")
                result["errors"].append(f"Conversation log failed: {str(e)}")

        # 2. Track documents if applicable
        if disposition in ['document_request', 'document_received'] or \
           analysis.get('documents_requested') or analysis.get('documents_attached'):
            try:
                doc_ids = await self._track_documents(
                    email_data=email_data,
                    analysis=analysis,
                    disposition=disposition,
                    user_id=user_id
                )
                result["documents_tracked"] = len(doc_ids)
                result["document_ids"] = doc_ids
            except Exception as e:
                logger.error(f"Failed to track documents: {e}")
                result["errors"].append(f"Document tracking failed: {str(e)}")

        # 3. Create SLA tracking for inbound emails needing response
        if email_data.get("direction") == 'inbound' and disposition in ['action_required', 'general_correspondence']:
            try:
                sla_id = await self._create_sla_tracking(
                    email_data=email_data,
                    analysis=analysis,
                    user_id=user_id
                )
                if sla_id:
                    result["sla_created"] = True
                    result["sla_id"] = sla_id
            except Exception as e:
                logger.error(f"Failed to create SLA: {e}")
                result["errors"].append(f"SLA tracking failed: {str(e)}")

        # 4. Create follow-up task if requested
        if create_task:
            try:
                task_id = await self._create_followup_task(
                    email_data=email_data,
                    analysis=analysis,
                    user_id=user_id,
                    task_title=task_title,
                    due_days=task_due_days
                )
                if task_id:
                    result["task_created"] = True
                    result["task_id"] = task_id
            except Exception as e:
                logger.error(f"Failed to create task: {e}")
                result["errors"].append(f"Task creation failed: {str(e)}")

        # Update email status - handle potential transaction failures
        try:
            self.db.rollback()  # Clear any failed transaction state
        except Exception as e:
            logger.error(f"Error in process_email (pre-update rollback): {e}")

        try:
            self.db.execute(text("""
                UPDATE email_reconciliation_queue
                SET disposition = :disposition,
                    status = 'processed',
                    processed_by = :user_id,
                    processed_at = :processed_at,
                    processing_notes = :notes,
                    updated_at = :updated_at
                WHERE id = :email_id
            """), {
                "disposition": disposition,
                "user_id": user_id,
                "processed_at": datetime.now(timezone.utc),
                "notes": additional_notes,
                "updated_at": datetime.now(timezone.utc),
                "email_id": email_id
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to update email status: {e}")
            result["errors"].append(f"Status update failed: {str(e)}")
            try:
                self.db.rollback()
            except Exception as e2:
                logger.error(f"Error in process_email (post-update rollback): {e2}")

        return result

    async def _create_conversation_log(
        self,
        email_data: Dict[str, Any],
        analysis: Dict[str, Any],
        override_summary: Optional[str],
        additional_notes: Optional[str],
        user_id: int
    ) -> Optional[int]:
        """Create conversation log entry from email"""

        loan_id = email_data.get("matched_loan_id")
        lead_id = email_data.get("matched_lead_id")
        contact_id = email_data.get("matched_contact_id")

        # Must have at least one entity link
        if not any([loan_id, lead_id, contact_id]):
            logger.warning(f"Email {email_data['id']} has no entity match, skipping conversation log")
            return None

        # Build summary
        summary = override_summary or analysis.get('summary', '')
        if not summary:
            summary = f"Email from {email_data.get('from_email', 'unknown')}: {email_data.get('subject', 'No subject')}"

        if additional_notes:
            summary = f"{summary}\n\nNotes: {additional_notes}"

        # Insert conversation log
        result = self.db.execute(text("""
            INSERT INTO email_conversation_log (
                contact_id, loan_id, lead_id,
                reconciliation_email_id, email_subject, email_date, direction,
                summary, key_points, action_items, next_steps,
                documents_requested, documents_received, documents_mentioned,
                sentiment, urgency_level, borrower_concerns,
                user_id, created_at
            ) VALUES (
                :contact_id, :loan_id, :lead_id,
                :email_id, :subject, :email_date, :direction,
                :summary, :key_points, :action_items, :next_steps,
                :docs_requested, :docs_received, :docs_mentioned,
                :sentiment, :urgency, :concerns,
                :user_id, :created_at
            ) RETURNING id
        """), {
            "contact_id": contact_id,
            "loan_id": loan_id,
            "lead_id": lead_id,
            "email_id": email_data["id"],
            "subject": email_data.get("subject"),
            "email_date": email_data.get("sent_date") or email_data.get("received_date"),
            "direction": email_data.get("direction", "inbound"),
            "summary": summary,
            "key_points": json.dumps(analysis.get("key_points", [])),
            "action_items": json.dumps(analysis.get("action_items", [])),
            "next_steps": json.dumps(analysis.get("next_steps", [])),
            "docs_requested": json.dumps(analysis.get("documents_requested", [])),
            "docs_received": json.dumps(analysis.get("documents_attached", [])),
            "docs_mentioned": json.dumps(analysis.get("documents_mentioned", [])),
            "sentiment": analysis.get("sentiment", "neutral"),
            "urgency": analysis.get("urgency_level", 3),
            "concerns": json.dumps(analysis.get("borrower_concerns", [])),
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc)
        })

        log_id = result.fetchone()[0]
        self.db.commit()

        logger.info(f"Created conversation log {log_id} for email {email_data['id']}")
        return log_id

    async def _track_documents(
        self,
        email_data: Dict[str, Any],
        analysis: Dict[str, Any],
        disposition: str,
        user_id: int
    ) -> List[int]:
        """Track document requests and receipts from email"""

        doc_ids = []
        loan_id = email_data.get("matched_loan_id")
        lead_id = email_data.get("matched_lead_id")

        # Track documents we requested (outbound)
        if disposition == 'document_request' or \
           (email_data.get("direction") == 'outbound' and analysis.get('documents_requested')):
            docs = analysis.get('documents_requested', [])
            for doc_name in docs:
                doc_type = self._classify_document_type(doc_name)

                # Check if already tracking
                existing = self.db.execute(text("""
                    SELECT id FROM email_document_tracking
                    WHERE (loan_id = :loan_id OR lead_id = :lead_id)
                      AND document_name = :doc_name
                      AND status IN ('requested', 'reminded')
                """), {"loan_id": loan_id, "lead_id": lead_id, "doc_name": doc_name}).fetchone()

                if existing:
                    # Update existing - increment reminder
                    self.db.execute(text("""
                        UPDATE email_document_tracking
                        SET reminder_count = reminder_count + 1,
                            next_reminder_date = :next_date,
                            updated_at = :updated_at
                        WHERE id = :id
                    """), {
                        "next_date": datetime.now(timezone.utc) + timedelta(days=3),
                        "updated_at": datetime.now(timezone.utc),
                        "id": existing[0]
                    })
                    doc_ids.append(existing[0])
                else:
                    # Create new tracking
                    result = self.db.execute(text("""
                        INSERT INTO email_document_tracking (
                            loan_id, lead_id, document_name, document_type,
                            status, requested_date, requested_via, requested_email_id,
                            next_reminder_date, user_id, created_at
                        ) VALUES (
                            :loan_id, :lead_id, :doc_name, :doc_type,
                            'requested', :req_date, 'email', :email_id,
                            :next_date, :user_id, :created_at
                        ) RETURNING id
                    """), {
                        "loan_id": loan_id,
                        "lead_id": lead_id,
                        "doc_name": doc_name,
                        "doc_type": doc_type,
                        "req_date": datetime.now(timezone.utc),
                        "email_id": email_data["id"],
                        "next_date": datetime.now(timezone.utc) + timedelta(days=3),
                        "user_id": user_id,
                        "created_at": datetime.now(timezone.utc)
                    })
                    doc_ids.append(result.fetchone()[0])

        # Track documents received (inbound with attachments)
        if disposition == 'document_received' or \
           (email_data.get("direction") == 'inbound' and email_data.get("has_attachments")):
            attachments = email_data.get("attachment_names") or []
            if isinstance(attachments, str):
                try:
                    attachments = json.loads(attachments)
                except Exception as e:
                    logger.error(f"Error in _apply_disposition (parse attachments JSON): {e}")
                    attachments = []

            docs_mentioned = analysis.get('documents_attached', []) or analysis.get('documents_mentioned', [])
            all_docs = list(set(attachments + docs_mentioned))

            for doc_name in all_docs:
                if not doc_name:
                    continue
                doc_type = self._classify_document_type(doc_name)

                # Find matching open request
                existing = self.db.execute(text("""
                    SELECT id FROM email_document_tracking
                    WHERE (loan_id = :loan_id OR lead_id = :lead_id)
                      AND document_type = :doc_type
                      AND status IN ('requested', 'reminded')
                    LIMIT 1
                """), {"loan_id": loan_id, "lead_id": lead_id, "doc_type": doc_type}).fetchone()

                if existing:
                    # Mark as received
                    self.db.execute(text("""
                        UPDATE email_document_tracking
                        SET status = 'received',
                            received_date = :recv_date,
                            received_via = 'email',
                            received_email_id = :email_id,
                            updated_at = :updated_at
                        WHERE id = :id
                    """), {
                        "recv_date": datetime.now(timezone.utc),
                        "email_id": email_data["id"],
                        "updated_at": datetime.now(timezone.utc),
                        "id": existing[0]
                    })
                    doc_ids.append(existing[0])
                else:
                    # Create new record as received (unsolicited)
                    result = self.db.execute(text("""
                        INSERT INTO email_document_tracking (
                            loan_id, lead_id, document_name, document_type,
                            status, received_date, received_via, received_email_id,
                            user_id, created_at
                        ) VALUES (
                            :loan_id, :lead_id, :doc_name, :doc_type,
                            'received', :recv_date, 'email', :email_id,
                            :user_id, :created_at
                        ) RETURNING id
                    """), {
                        "loan_id": loan_id,
                        "lead_id": lead_id,
                        "doc_name": doc_name,
                        "doc_type": doc_type,
                        "recv_date": datetime.now(timezone.utc),
                        "email_id": email_data["id"],
                        "user_id": user_id,
                        "created_at": datetime.now(timezone.utc)
                    })
                    doc_ids.append(result.fetchone()[0])

        self.db.commit()
        return doc_ids

    def _classify_document_type(self, doc_name: str) -> str:
        """Classify document type from filename"""
        doc_lower = doc_name.lower()

        classifications = [
            (['w2', 'w-2'], 'w2'),
            (['paystub', 'pay stub', 'paycheck'], 'paystub'),
            (['bank statement', 'bank stmt', 'checking', 'savings'], 'bank_statement'),
            (['tax return', '1040', 'tax transcript'], 'tax_return'),
            (['driver', 'license', 'passport', 'id card', 'identification'], 'identification'),
            (['insurance', 'hoi', 'homeowner'], 'insurance'),
            (['appraisal'], 'appraisal'),
            (['title', 'deed'], 'title'),
            (['1099'], '1099'),
            (['lease', 'rental'], 'lease'),
            (['award letter', 'benefit', 'social security'], 'benefits'),
            (['profit', 'loss', 'p&l'], 'profit_loss'),
            (['voided check', 'void check'], 'voided_check'),
            (['gift letter'], 'gift_letter'),
            (['explanation', 'loe', 'loc'], 'letter_of_explanation'),
            (['purchase', 'contract', 'agreement'], 'purchase_contract'),
        ]

        for keywords, doc_type in classifications:
            if any(kw in doc_lower for kw in keywords):
                return doc_type

        return 'other'

    async def _create_sla_tracking(
        self,
        email_data: Dict[str, Any],
        analysis: Dict[str, Any],
        user_id: int
    ) -> Optional[int]:
        """Create SLA tracking for email needing response"""

        urgency = analysis.get('urgency_level', 3)

        if urgency >= 5:
            sla_hours = 2
            sla_type = 'critical_response'
        elif urgency >= 4:
            sla_hours = 4
            sla_type = 'urgent_response'
        elif urgency >= 3:
            sla_hours = 24
            sla_type = 'standard_response'
        else:
            sla_hours = 48
            sla_type = 'low_priority_response'

        # Check if SLA exists
        existing = self.db.execute(text("""
            SELECT id FROM email_sla_tracking
            WHERE reconciliation_email_id = :email_id
        """), {"email_id": email_data["id"]}).fetchone()

        if existing:
            return existing[0]

        received_at = email_data.get("received_date") or email_data.get("sent_date") or datetime.now(timezone.utc)
        if isinstance(received_at, str):
            try:
                received_at = datetime.fromisoformat(received_at.replace('Z', '+00:00'))
            except Exception as e:
                logger.error(f"Error in _create_sla_tracker (parse received_at): {e}")
                received_at = datetime.now(timezone.utc)

        due_at = received_at + timedelta(hours=sla_hours)

        result = self.db.execute(text("""
            INSERT INTO email_sla_tracking (
                reconciliation_email_id, thread_id, sla_type, sla_hours,
                email_received_at, response_due_at, status, user_id, created_at
            ) VALUES (
                :email_id, :thread_id, :sla_type, :sla_hours,
                :received_at, :due_at, 'pending', :user_id, :created_at
            ) RETURNING id
        """), {
            "email_id": email_data["id"],
            "thread_id": email_data.get("thread_id"),
            "sla_type": sla_type,
            "sla_hours": sla_hours,
            "received_at": received_at,
            "due_at": due_at,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc)
        })

        sla_id = result.fetchone()[0]
        self.db.commit()

        logger.info(f"Created SLA tracking {sla_id}: {sla_type} ({sla_hours}h)")
        return sla_id

    async def _create_followup_task(
        self,
        email_data: Dict[str, Any],
        analysis: Dict[str, Any],
        user_id: int,
        task_title: Optional[str],
        due_days: int
    ) -> Optional[int]:
        """Create a follow-up task"""

        loan_id = email_data.get("matched_loan_id")
        lead_id = email_data.get("matched_lead_id")

        title = task_title or f"Follow up: {email_data.get('subject', 'Email')}"
        description = f"Generated from email\nFrom: {email_data.get('from_email')}\nSubject: {email_data.get('subject')}"

        if analysis.get("action_items"):
            description += f"\n\nAction items:\n" + "\n".join([f"- {item}" for item in analysis.get("action_items", [])])

        due_date = datetime.now(timezone.utc) + timedelta(days=due_days)

        # Check if tasks table exists and create task
        try:
            result = self.db.execute(text("""
                INSERT INTO tasks (
                    title, description, due_date, priority,
                    loan_id, lead_id, assigned_to, created_by,
                    source, source_id, status, created_at
                ) VALUES (
                    :title, :description, :due_date, :priority,
                    :loan_id, :lead_id, :assigned_to, :created_by,
                    'email_intelligence', :source_id, 'pending', :created_at
                ) RETURNING id
            """), {
                "title": title[:255],
                "description": description,
                "due_date": due_date,
                "priority": "high" if analysis.get("urgency_level", 3) >= 4 else "medium",
                "loan_id": loan_id,
                "lead_id": lead_id,
                "assigned_to": user_id,
                "created_by": user_id,
                "source_id": email_data["id"],
                "created_at": datetime.now(timezone.utc)
            })

            task_id = result.fetchone()[0]
            self.db.commit()
            logger.info(f"Created task {task_id} from email {email_data['id']}")
            return task_id
        except SQLAlchemyError as e:
            logger.warning(f"Could not create task (table may not exist): {e}")
            return None

    async def _run_ai_analysis(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run AI analysis on email"""

        if not self.anthropic_api_key:
            return self._basic_analysis_dict(email_data)

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.anthropic_api_key)

            prompt = f"""Analyze this mortgage-related email and extract key information.

EMAIL:
From: {email_data.get('from_email')} ({email_data.get('from_name', 'Unknown')})
Subject: {email_data.get('subject')}
Date: {email_data.get('sent_date')}
Has Attachments: {email_data.get('has_attachments')}
Attachments: {email_data.get('attachment_names', [])}

Body:
{email_data.get('body_preview') or email_data.get('body_full', 'No body')}

Return ONLY valid JSON with this structure:
{{
    "summary": "2-3 sentence summary for conversation log",
    "key_points": ["key point 1", "key point 2"],
    "action_items": ["action if any"],
    "next_steps": ["suggested next step"],
    "documents_requested": ["docs WE requested if outbound"],
    "documents_attached": ["docs attached/sent by client"],
    "documents_mentioned": ["other docs discussed"],
    "sentiment": "positive|neutral|negative|urgent",
    "urgency_level": 1-5,
    "borrower_concerns": ["any concerns raised"]
}}"""

            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text
            response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()

            return json.loads(response_text)

        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return self._basic_analysis_dict(email_data)

    def _basic_analysis_dict(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback basic analysis"""
        return {
            "summary": f"Email from {email_data.get('from_email', 'unknown')}: {email_data.get('subject', 'No subject')}",
            "key_points": [],
            "action_items": [],
            "next_steps": [],
            "documents_requested": [],
            "documents_attached": [],
            "documents_mentioned": [],
            "sentiment": "neutral",
            "urgency_level": 3,
            "borrower_concerns": []
        }


# ================================================================
# PHASE 3 API ENDPOINTS
# ================================================================

@router.post("/queue/{email_id}/process-with-intelligence")
async def process_email_with_intelligence(
    email_id: int,
    disposition: str = Query(..., description="Disposition for the email"),
    override_summary: Optional[str] = Query(None, description="Override AI summary"),
    additional_notes: Optional[str] = Query(None, description="Additional notes"),
    create_task: bool = Query(False, description="Create follow-up task"),
    task_title: Optional[str] = Query(None, description="Task title if creating"),
    task_due_days: int = Query(3, description="Days until task due"),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Process email with full conversation intelligence.

    Creates:
    - Conversation log entry (AI-generated summary)
    - Document tracking records
    - SLA tracking (if needed)
    - Follow-up task (optional)
    """
    try:

        service = ConversationIntelligenceService(db)

        result = await service.process_email_disposition(
            email_id=email_id,
            disposition=disposition,
            user_id=user_id,
            override_summary=override_summary,
            additional_notes=additional_notes,
            create_task=create_task,
            task_title=task_title,
            task_due_days=task_due_days
        )

        return result
    except Exception as e:
        logger.error(f"Error processing email {email_id} with intelligence: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/batch-process-with-intelligence")
async def batch_process_emails_with_intelligence(
    limit: int = Query(50, le=200),
    auto_disposition: bool = Query(True, description="Auto-determine disposition"),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Batch process pending emails with conversation intelligence.

    Processes emails that have entity matches (loan/lead).
    """

    # Get pending emails with matches
    pending = db.execute(text("""
        SELECT id, direction, has_attachments, ai_analysis
        FROM email_reconciliation_queue
        WHERE user_id = :user_id
          AND status = 'pending'
          AND (matched_loan_id IS NOT NULL OR matched_lead_id IS NOT NULL)
        ORDER BY is_priority DESC, received_date DESC
        LIMIT :limit
    """), {"user_id": user_id, "limit": limit}).fetchall()

    results = {
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }

    service = ConversationIntelligenceService(db)

    for row in pending:
        email_id = row[0]
        direction = row[1]
        has_attachments = row[2]
        analysis = row[3] or {}

        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except Exception as e:
                logger.error(f"Error in batch_process_emails_with_intelligence (parse analysis JSON): {e}")
                analysis = {}

        try:
            # Determine disposition
            if auto_disposition:
                disposition = _auto_determine_disposition(direction, has_attachments, analysis)
            else:
                disposition = "general_correspondence"

            result = await service.process_email_disposition(
                email_id=email_id,
                disposition=disposition,
                user_id=user_id
            )

            results["processed"] += 1
            results["details"].append({
                "email_id": email_id,
                "disposition": disposition,
                "conversation_log_created": result.get("conversation_log_created"),
                "documents_tracked": result.get("documents_tracked")
            })

        except Exception as e:
            logger.error(f"Failed to process email {email_id}: {e}")
            results["errors"] += 1
            results["details"].append({
                "email_id": email_id,
                "error": "Internal server error"
            })

    return results


def _auto_determine_disposition(direction: str, has_attachments: bool, analysis: Dict[str, Any]) -> str:
    """Auto-determine disposition based on email characteristics"""

    # Document request (outbound)
    if direction == 'outbound' and analysis.get('documents_requested'):
        return 'document_request'

    # Document received (inbound with attachments)
    if direction == 'inbound' and (has_attachments or analysis.get('documents_attached')):
        return 'document_received'

    # High urgency
    if analysis.get('urgency_level', 3) >= 4:
        return 'action_required'

    # Urgent sentiment
    if analysis.get('sentiment') == 'urgent':
        return 'action_required'

    return 'general_correspondence'


@router.get("/conversation-log/loan/{loan_id}")
async def get_loan_conversation_log(
    loan_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get conversation log entries for a loan"""

    result = db.execute(text("""
        SELECT id, email_subject, email_date, direction, summary,
               key_points, action_items, sentiment, urgency_level,
               documents_requested, documents_received, created_at
        FROM email_conversation_log
        WHERE loan_id = :loan_id AND user_id = :user_id
        ORDER BY email_date DESC
        LIMIT :limit
    """), {"loan_id": loan_id, "user_id": user_id, "limit": limit}).fetchall()

    entries = []
    for row in result:
        entries.append({
            "id": row[0],
            "email_subject": row[1],
            "email_date": str(row[2]) if row[2] else None,
            "direction": row[3],
            "summary": row[4],
            "key_points": row[5],
            "action_items": row[6],
            "sentiment": row[7],
            "urgency_level": row[8],
            "documents_requested": row[9],
            "documents_received": row[10],
            "created_at": str(row[11]) if row[11] else None
        })

    return {"entries": entries, "total": len(entries), "loan_id": loan_id}


@router.get("/sla-tracking")
async def get_sla_tracking(
    status: Optional[str] = Query(None, description="Filter by status"),
    include_breached: bool = Query(True),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get SLA tracking records"""

    try:
        # Check if table exists first
        table_check = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'email_sla_tracking'
            )
        """)).scalar()

        if not table_check:
            # Table doesn't exist - return empty result
            return {"slas": [], "total": 0, "message": "SLA tracking table not initialized"}

        query = """
            SELECT s.id, s.reconciliation_email_id, s.sla_type, s.sla_hours,
                   s.email_received_at, s.response_due_at, s.responded_at, s.status,
                   e.from_email, e.subject
            FROM email_sla_tracking s
            JOIN email_reconciliation_queue e ON s.reconciliation_email_id = e.id
            WHERE s.user_id = :user_id
        """
        params = {"user_id": user_id}

        if status:
            query += " AND s.status = :status"
            params["status"] = status

        if not include_breached:
            query += " AND s.status != 'breached'"

        query += " ORDER BY s.response_due_at ASC"

        result = db.execute(text(query), params).fetchall()
    except SQLAlchemyError as e:
        logger.error(f"Error fetching SLA tracking: {e}")
        # Return empty result instead of crashing
        return {"slas": [], "total": 0, "error": "Internal server error"}

    slas = []
    for row in result:
        due_at = row[5]
        is_overdue = False
        if due_at and row[7] == 'pending':
            if isinstance(due_at, str):
                try:
                    due_at = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
                except Exception as e:
                    logger.error(f"Error in get_sla_tracking (parse due_at): {e}")
            if isinstance(due_at, datetime):
                is_overdue = due_at < datetime.now(timezone.utc)

        slas.append({
            "id": row[0],
            "email_id": row[1],
            "sla_type": row[2],
            "sla_hours": row[3],
            "received_at": str(row[4]) if row[4] else None,
            "due_at": str(row[5]) if row[5] else None,
            "responded_at": str(row[6]) if row[6] else None,
            "status": row[7],
            "from_email": row[8],
            "subject": row[9],
            "is_overdue": is_overdue
        })

    return {"slas": slas, "total": len(slas)}


@router.post("/sla-tracking/{sla_id}/respond")
async def mark_sla_responded(
    sla_id: int,
    response_email_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Mark SLA as responded"""

    db.execute(text("""
        UPDATE email_sla_tracking
        SET status = 'responded',
            responded_at = :responded_at,
            response_email_id = :response_email_id,
            updated_at = :updated_at
        WHERE id = :sla_id AND user_id = :user_id
    """), {
        "responded_at": datetime.now(timezone.utc),
        "response_email_id": response_email_id,
        "updated_at": datetime.now(timezone.utc),
        "sla_id": sla_id,
        "user_id": user_id
    })
    db.commit()

    return {"status": "success", "sla_id": sla_id}


# ================================================================
# DEBUG & TESTING ENDPOINTS
# ================================================================

@router.get("/debug/schema")
async def debug_email_queue_schema(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_admin_user_id),
):
    """
    Debug endpoint to check the email_reconciliation_queue table schema.
    Shows all columns and their types.
    """
    try:
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'email_reconciliation_queue'
            ORDER BY ordinal_position
        """)).fetchall()

        columns = [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2],
                "default": row[3]
            }
            for row in result
        ]

        # Check which identity-related columns exist
        column_names = [c["name"] for c in columns]
        identity_columns = {
            "match_method": "match_method" in column_names,
            "match_confidence": "match_confidence" in column_names,
            "match_evidence": "match_evidence" in column_names,
            "match_client_name": "match_client_name" in column_names,
            "match_loan_number": "match_loan_number" in column_names,
            "is_priority": "is_priority" in column_names,
        }

        return {
            "table": "email_reconciliation_queue",
            "column_count": len(columns),
            "columns": columns,
            "identity_columns_status": identity_columns,
            "all_identity_columns_exist": all(identity_columns.values())
        }
    except Exception as e:
        return {"error": "Internal server error"}


@router.post("/debug/test-identity-resolution")
async def debug_test_identity_resolution(
    email_data: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_admin_user_id),
):
    """
    Debug endpoint to test the EmailIdentityResolver without creating a queue record.
    Pass email data and see what match result would be returned.
    """

    try:
        from services.email_identity_resolver import get_email_identity_resolver

        resolver = get_email_identity_resolver(db)
        match_result = resolver.resolve(email_data, user_id)

        return {
            "status": "success",
            "user_id": user_id,
            "email_data_received": {
                "from_email": email_data.get("from_email"),
                "subject": email_data.get("subject"),
                "thread_id": email_data.get("thread_id")
            },
            "match_result": match_result
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.post("/debug/add-missing-columns")
async def debug_add_missing_columns(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_admin_user_id),
):
    """
    Add missing identity resolution columns to email_reconciliation_queue.
    """
    try:
        # Add missing columns if they don't exist
        columns_to_add = [
            ("match_method", "VARCHAR(100)"),
            ("match_evidence", "TEXT"),
            ("match_client_name", "VARCHAR(255)"),
            ("match_loan_number", "VARCHAR(100)"),
        ]

        added = []
        for col_name, col_type in columns_to_add:
            try:
                alter_sql = "ALTER TABLE email_reconciliation_queue ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                db.execute(text(alter_sql))
                added.append(col_name)
            except SQLAlchemyError as e:
                logger.warning(f"Could not add column {col_name}: {e}")

        db.commit()

        return {
            "status": "success",
            "columns_added": added
        }
    except SQLAlchemyError as e:
        db.rollback()
        return {"status": "error", "error": "Internal server error"}
