"""
Email Intelligence & Reconciliation System Routes
Pipeline 360 - Advanced Email Processing Engine

This system provides enterprise-grade email intelligence:
1. Email scraping & import from Gmail/Outlook
2. Intelligent disposition engine with AI categorization
3. Document request tracking
4. Conversation intelligence & summaries
5. Data import & mapping to leads/loans
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
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

logger = logging.getLogger(__name__)
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
                    response_sent_at TIMESTAMP WITH TIME ZONE,

                    -- Status
                    status VARCHAR(50),
                    breach_notified BOOLEAN DEFAULT FALSE,

                    -- Metrics
                    response_time_hours NUMERIC(10, 2),

                    -- User ownership
                    user_id INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sla_track_status ON email_sla_tracking(status);
                CREATE INDEX IF NOT EXISTS idx_sla_track_due ON email_sla_tracking(response_due_at);
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

    except Exception as e:
        logger.error(f"❌ Error creating email intelligence tables: {e}")
        raise


# Auto-create tables on module load
try:
    ensure_email_intelligence_tables_exist()
except Exception as e:
    logger.warning(f"Could not auto-create email intelligence tables: {e}")


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
                model="claude-sonnet-4-20250514",
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

def get_current_user_id(db: Session) -> int:
    """Get current user ID - placeholder for auth integration"""
    # In production, this would come from JWT token
    # For now, return demo user
    result = db.execute(text("SELECT id FROM users WHERE email = 'demo@example.com' LIMIT 1")).fetchone()
    return result[0] if result else 1


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
    db: Session = Depends(get_db)
):
    """
    Get emails in reconciliation queue
    """
    user_id = get_current_user_id(db)

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
    db: Session = Depends(get_db)
):
    """Get single email with full details"""
    user_id = get_current_user_id(db)

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


@router.post("/queue/{email_id}/analyze")
async def analyze_email(
    email_id: int,
    db: Session = Depends(get_db)
):
    """Run AI analysis on email"""
    user_id = get_current_user_id(db)

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
    db: Session = Depends(get_db)
):
    """
    Process email disposition - save to conversation log, import data, etc.
    """
    user_id = get_current_user_id(db)

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
    db: Session = Depends(get_db)
):
    """Get conversation log for an entity"""
    user_id = get_current_user_id(db)

    if entity_type == "contact":
        filter_col = "contact_id"
    elif entity_type == "loan":
        filter_col = "loan_id"
    else:
        filter_col = "lead_id"

    result = db.execute(text(f"""
        SELECT id, contact_id, loan_id, lead_id,
               email_subject, email_date, direction,
               summary, key_points, action_items, next_steps,
               documents_requested, documents_received,
               sentiment, urgency_level, created_by, created_at
        FROM email_conversation_log
        WHERE {filter_col} = :entity_id AND user_id = :user_id
        ORDER BY email_date DESC
        LIMIT :limit
    """), {"entity_id": entity_id, "user_id": user_id, "limit": limit}).fetchall()

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
    db: Session = Depends(get_db)
):
    """Get document tracking for an entity"""
    user_id = get_current_user_id(db)

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


@router.post("/document-tracking/{doc_id}/received")
async def mark_document_received(
    doc_id: int,
    received_email_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Mark a tracked document as received"""
    user_id = get_current_user_id(db)

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
    db: Session = Depends(get_db)
):
    """Get email intelligence statistics"""
    user_id = get_current_user_id(db)
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

    return {
        "period_days": days,
        "queue_by_disposition": {row[0]: row[1] for row in disposition_stats if row[0]},
        "queue_by_direction": {row[0]: row[1] for row in direction_stats if row[0]},
        "processed_count": processed or 0,
        "pending_count": pending or 0,
        "conversation_logs_created": logs_created or 0,
        "documents_requested": docs_requested or 0,
        "documents_received": docs_received or 0
    }


@router.post("/import-email")
async def import_email_to_queue(
    email_data: Dict[str, Any],
    auto_analyze: bool = Query(True),
    db: Session = Depends(get_db)
):
    """
    Import an email into the reconciliation queue

    Used by email sync services to add emails for processing
    """
    user_id = get_current_user_id(db)

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

    # Insert email
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
        "user_id": user_id
    })

    email_id = result.fetchone()[0]
    db.commit()

    # Auto-match to known clients
    if email_data.get("from_email"):
        match_result = db.execute(text("""
            SELECT contact_id, loan_id, lead_id
            FROM known_client_emails
            WHERE email_address = :email AND user_id = :user_id
            LIMIT 1
        """), {"email": email_data.get("from_email").lower(), "user_id": user_id}).fetchone()

        if match_result:
            db.execute(text("""
                UPDATE email_reconciliation_queue
                SET matched_contact_id = :contact_id,
                    matched_loan_id = :loan_id,
                    matched_lead_id = :lead_id,
                    match_method = 'known_client_email',
                    match_confidence = 1.0
                WHERE id = :email_id
            """), {
                "contact_id": match_result[0],
                "loan_id": match_result[1],
                "lead_id": match_result[2],
                "email_id": email_id
            })
            db.commit()

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
        except Exception as e:
            logger.error(f"Auto-analysis failed: {e}")

    return {
        "status": "imported",
        "email_id": email_id,
        "analysis": analysis.dict() if analysis else None
    }


@router.post("/sync-known-clients")
async def sync_known_client_emails(
    db: Session = Depends(get_db)
):
    """
    Sync all known client emails from leads, loans, and contacts

    This builds the known_client_emails lookup table for email matching
    """
    user_id = get_current_user_id(db)

    synced = 0

    # Get emails from leads
    leads = db.execute(text("""
        SELECT id, email, name FROM leads WHERE email IS NOT NULL
    """)).fetchall()

    for lead in leads:
        if lead[1]:
            db.execute(text("""
                INSERT INTO known_client_emails (email_address, lead_id, client_name, source_type, source_id, user_id)
                VALUES (:email, :lead_id, :name, 'lead', :lead_id, :user_id)
                ON CONFLICT (email_address, user_id) DO UPDATE SET
                    lead_id = COALESCE(known_client_emails.lead_id, :lead_id),
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "email": lead[1].lower(),
                "lead_id": lead[0],
                "name": lead[2],
                "user_id": user_id
            })
            synced += 1

    # Get emails from loans
    loans = db.execute(text("""
        SELECT id, borrower_email, borrower_name FROM loans WHERE borrower_email IS NOT NULL
    """)).fetchall()

    for loan in loans:
        if loan[1]:
            db.execute(text("""
                INSERT INTO known_client_emails (email_address, loan_id, client_name, source_type, source_id, user_id)
                VALUES (:email, :loan_id, :name, 'loan', :loan_id, :user_id)
                ON CONFLICT (email_address, user_id) DO UPDATE SET
                    loan_id = COALESCE(known_client_emails.loan_id, :loan_id),
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "email": loan[1].lower(),
                "loan_id": loan[0],
                "name": loan[2],
                "user_id": user_id
            })
            synced += 1

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
        raise HTTPException(status_code=500, detail=str(e))


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

        # Auto-match to known clients
        match_info = None
        if from_email:
            match_result = db.execute(text("""
                SELECT contact_id, loan_id, lead_id, client_name
                FROM known_client_emails
                WHERE email_address = :email AND user_id = :user_id
                LIMIT 1
            """), {"email": from_email.lower(), "user_id": user_id}).fetchone()

            if match_result:
                db.execute(text("""
                    UPDATE email_reconciliation_queue
                    SET matched_contact_id = :contact_id,
                        matched_loan_id = :loan_id,
                        matched_lead_id = :lead_id,
                        match_method = 'known_client_email',
                        match_confidence = 1.0,
                        is_priority = TRUE
                    WHERE id = :email_id
                """), {
                    "contact_id": match_result[0],
                    "loan_id": match_result[1],
                    "lead_id": match_result[2],
                    "email_id": email_id
                })
                db.commit()

                match_info = {
                    "contact_id": match_result[0],
                    "loan_id": match_result[1],
                    "lead_id": match_result[2],
                    "client_name": match_result[3],
                    "method": "known_client_email"
                }

        # Run AI analysis if requested
        analysis = None
        if auto_analyze:
            try:
                engine = EmailIntelligenceEngine(db)
                analysis = await engine.analyze_email({
                    "from_email": from_email,
                    "from_name": from_name,
                    "subject": email_data.get("subject", ""),
                    "body_preview": body_preview
                })

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
            except Exception as e:
                logger.warning(f"Auto-analysis failed for email {email_id}: {e}")

        return {
            "status": "queued",
            "email_id": email_id,
            "match": match_info,
            "analysis": analysis.dict() if analysis else None
        }

    except Exception as e:
        logger.error(f"Error queuing email for intelligence: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}


@router.post("/batch-import")
async def batch_import_emails(
    emails: List[Dict[str, Any]],
    auto_analyze: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Import multiple emails to the queue in batch.

    This is the primary endpoint for email sync services.
    """
    user_id = get_current_user_id(db)

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
    db: Session = Depends(get_db)
):
    """
    Cron endpoint to sync ALL emails from connected providers to the intelligence queue.

    Unlike the regular cron sync which only processes matching emails through DRE,
    this queues ALL emails for intelligent disposition.
    """
    import os

    expected_key = os.getenv("CRON_API_KEY")
    if not expected_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # First, refresh known client emails
    try:
        from sqlalchemy import text

        # Get all users
        users = db.execute(text("SELECT id FROM users")).fetchall()

        total_synced = 0
        for user_row in users:
            user_id = user_row[0]

            # Sync leads
            leads = db.execute(text("""
                SELECT id, email, name FROM leads
                WHERE email IS NOT NULL AND loan_officer_id = :user_id
            """), {"user_id": user_id}).fetchall()

            for lead in leads:
                if lead[1]:
                    db.execute(text("""
                        INSERT INTO known_client_emails (email_address, lead_id, client_name, source_type, source_id, user_id)
                        VALUES (:email, :lead_id, :name, 'lead', :lead_id, :user_id)
                        ON CONFLICT (email_address, user_id) DO UPDATE SET
                            lead_id = COALESCE(known_client_emails.lead_id, :lead_id),
                            updated_at = CURRENT_TIMESTAMP
                    """), {
                        "email": lead[1].lower(),
                        "lead_id": lead[0],
                        "name": lead[2],
                        "user_id": user_id
                    })

            # Sync loans
            loans = db.execute(text("""
                SELECT id, borrower_email, borrower_name FROM loans
                WHERE borrower_email IS NOT NULL AND loan_officer_id = :user_id
            """), {"user_id": user_id}).fetchall()

            for loan in loans:
                if loan[1]:
                    db.execute(text("""
                        INSERT INTO known_client_emails (email_address, loan_id, client_name, source_type, source_id, user_id)
                        VALUES (:email, :loan_id, :name, 'loan', :loan_id, :user_id)
                        ON CONFLICT (email_address, user_id) DO UPDATE SET
                            loan_id = COALESCE(known_client_emails.loan_id, :loan_id),
                            updated_at = CURRENT_TIMESTAMP
                    """), {
                        "email": loan[1].lower(),
                        "loan_id": loan[0],
                        "name": loan[2],
                        "user_id": user_id
                    })

            total_synced += len(leads) + len(loans)

        db.commit()

        return {
            "status": "success",
            "known_clients_synced": total_synced,
            "message": "Run the provider-specific sync endpoints to queue emails"
        }

    except Exception as e:
        logger.error(f"Error in cron sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))
