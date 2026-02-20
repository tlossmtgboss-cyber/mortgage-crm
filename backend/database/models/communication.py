"""
Communication Models

Models for tracking communications, activities, and messaging.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.communication import Activity, SMSMessage, EmailMessage

    # Query activities
    activities = db.query(Activity).filter(Activity.lead_id == lead_id).all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index, Numeric
)
from sqlalchemy.orm import relationship

# Import Base from the db module
from db import Base

# Import enums from the database package
from database.enums import ActivityType


# ============================================================================
# ACTIVITY & STAGE HISTORY
# ============================================================================

class Activity(Base):
    """Activity/touchpoint log for leads and loans"""
    __tablename__ = "activities"
    __table_args__ = (
        Index('ix_activities_lead_id', 'lead_id'),
        Index('ix_activities_loan_id', 'loan_id'),
        Index('ix_activities_user_id', 'user_id'),
        Index('ix_activities_created_at', 'created_at'),
        Index('ix_activities_lead_created', 'lead_id', 'created_at'),
        Index('ix_activities_organization_id', 'organization_id'),
        Index('ix_activities_org_created', 'organization_id', 'created_at'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    type = Column(SQLEnum(ActivityType), nullable=False)
    content = Column(Text)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    mum_client_id = Column(Integer, ForeignKey("mum_clients.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    duration = Column(String)
    sentiment = Column(String)
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    lead = relationship("Lead", back_populates="activities")
    loan = relationship("Loan", back_populates="activities")


class StageHistory(Base):
    """Tracks all stage/status changes for leads and loans with timestamps"""
    __tablename__ = "stage_history"
    __table_args__ = (
        Index('ix_stage_history_lead_id', 'lead_id'),
        Index('ix_stage_history_loan_id', 'loan_id'),
        Index('ix_stage_history_changed_at', 'changed_at'),
        Index('ix_stage_history_entity', 'entity_type', 'entity_id'),
        Index('ix_stage_history_organization_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    entity_type = Column(String, nullable=False)  # 'lead' or 'loan'
    entity_id = Column(Integer, nullable=False)  # The lead_id or loan_id
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    from_stage = Column(String)  # Previous stage (null for initial)
    to_stage = Column(String, nullable=False)  # New stage
    changed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id"))  # User who made the change
    notes = Column(Text)  # Optional notes about the change
    duration_in_previous_stage = Column(Integer)  # Days spent in previous stage

    # Relationships
    lead = relationship("Lead", back_populates="stage_history", foreign_keys=[lead_id])
    loan = relationship("Loan", back_populates="stage_history", foreign_keys=[loan_id])
    changed_by = relationship("User")


# ============================================================================
# CONVERSATION & AI CHAT
# ============================================================================

class Conversation(Base):
    """AI chat conversation history"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    message = Column(Text, nullable=False)
    response = Column(Text)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ConversationMemory(Base):
    """Stores conversation summaries with vector embeddings for AI context retrieval"""
    __tablename__ = "conversation_memory"
    __table_args__ = (
        Index('ix_conversation_memory_organization_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), index=True)
    conversation_summary = Column(Text, nullable=False)  # Summary of the conversation
    key_points = Column(JSON)  # Extracted entities, preferences, issues
    sentiment = Column(String)  # positive, neutral, negative
    intent = Column(String)  # The user's intent in the conversation
    pinecone_id = Column(String, unique=True, index=True)  # Reference to vector in Pinecone
    relevance_score = Column(Float)  # How relevant this memory is (updated over time)
    access_count = Column(Integer, default=0)  # How many times this memory was retrieved
    last_accessed_at = Column(DateTime)  # When this memory was last used
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# SMS MESSAGING
# ============================================================================

class SMSMessage(Base):
    """SMS message log"""
    __tablename__ = "sms_messages"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    conversation_id = Column(Integer, ForeignKey("sms_conversations.id"))
    to_number = Column(String, nullable=False)
    from_number = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    direction = Column(String)  # inbound, outbound
    status = Column(String)  # queued, sent, delivered, failed, received
    twilio_sid = Column(String)
    template_used = Column(String)
    error_message = Column(Text)
    ai_generated = Column(Boolean, default=False)
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    conversation = relationship("SMSConversation", back_populates="messages")


class SMSConversation(Base):
    """Tracks SMS conversation threads for two-way AI messaging"""
    __tablename__ = "sms_conversations"
    __table_args__ = (
        Index('ix_sms_conv_phone', 'phone_number'),
        Index('ix_sms_conv_user', 'user_id'),
        Index('ix_sms_conv_active', 'is_active'),
        Index('ix_sms_conversations_organization_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    phone_number = Column(String, nullable=False, index=True)  # The external party's phone
    user_id = Column(Integer, ForeignKey("users.id"))  # The LO managing this conversation
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    contact_id = Column(Integer)  # No FK - contacts table may not exist in all deployments
    contact_name = Column(String)  # Cached name for quick display
    is_active = Column(Boolean, default=True)
    ai_enabled = Column(Boolean, default=True)  # Whether AI auto-responds
    last_message_at = Column(DateTime)
    last_ai_response_at = Column(DateTime)
    message_count = Column(Integer, default=0)
    context = Column(JSON)  # Conversation context for AI (loan details, etc.)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    messages = relationship("SMSMessage", back_populates="conversation", order_by="SMSMessage.created_at")


# ============================================================================
# EMAIL MESSAGING
# ============================================================================

class EmailMessage(Base):
    """Email message log"""
    __tablename__ = "email_messages"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
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


class Email(Base):
    """Stores emails fetched from Microsoft Graph API"""
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
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


class EmailDraft(Base):
    """Stores email drafts including AI-generated call summaries"""
    __tablename__ = "email_drafts"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), index=True)

    # Email content
    recipient_email = Column(String, index=True)
    recipient_name = Column(String)
    cc_emails = Column(JSON)  # Array of CC recipients
    subject = Column(String)
    body_html = Column(Text)
    body_text = Column(Text)

    # Source reference
    source_type = Column(String)  # "call_recording", "ai_generated", "manual"
    source_id = Column(String)  # Recording ID or other reference
    recording_url = Column(String)  # URL to the recording if applicable

    # AI-generated content
    call_summary = Column(Text)
    action_items = Column(JSON)  # List of action items from the call

    # Status
    status = Column(String, default="draft", index=True)  # "draft", "sent", "deleted"
    sent_at = Column(DateTime)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class EmailVerificationToken(Base):
    """Email verification tokens for registration"""
    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    email = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# TEAMS MESSAGING
# ============================================================================

class TeamsMessage(Base):
    """Microsoft Teams message log"""
    __tablename__ = "teams_messages"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
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


# ============================================================================
# VOICEMAIL
# ============================================================================

class VoicemailDrop(Base):
    """Tracks voicemail drops via Vapi AI"""
    __tablename__ = "voicemail_drops"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    lead_id = Column(Integer, ForeignKey("leads.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("voicemail_campaigns.id"), index=True)
    template_id = Column(Integer, ForeignKey("voicemail_templates.id"), index=True)

    # Contact info
    contact_name = Column(String(255))
    phone_number = Column(String(20), nullable=False)
    contact_email = Column(String(255))

    # Message
    message_text = Column(Text, nullable=False)
    message_variables = Column(JSON)
    audio_url = Column(String(500))

    # Delivery
    delivery_method = Column(String(50), default='vapi_ai')  # vapi_ai, ringless
    vapi_call_id = Column(String(255), index=True)
    vapi_assistant_id = Column(String(255))

    # Ringless voicemail (RVM) provider fields
    rvm_session_id = Column(String(255), index=True)  # Slybroadcast session_id / Drop Cowboy message_id
    rvm_provider = Column(String(50))                  # slybroadcast, dropcowboy
    rvm_dispo_code = Column(String(50))                # Provider disposition code

    # Status
    status = Column(String(50), default='pending')  # pending, queued, calling, delivered, failed, no_voicemail, human_answered
    delivery_attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime)
    delivered_at = Column(DateTime)

    # Call metadata
    call_duration = Column(Integer)
    call_cost = Column(Numeric(10, 4))
    carrier = Column(String(50))

    # Analytics
    voicemail_listened = Column(Boolean, default=False)
    listened_at = Column(DateTime)
    callback_received = Column(Boolean, default=False)
    callback_at = Column(DateTime)
    callback_notes = Column(Text)

    # Errors
    error_code = Column(String(50))
    error_message = Column(Text)
    retry_scheduled_at = Column(DateTime)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class VoicemailTemplate(Base):
    """Voicemail message templates"""
    __tablename__ = "voicemail_templates"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    name = Column(String(255), nullable=False)
    category = Column(String(100), index=True)  # closing, follow_up, urgent, scheduling, status_update

    message_text = Column(Text, nullable=False)
    variables = Column(JSON)  # ["contact_name", "loan_officer"]
    audio_url = Column(String(500))  # Pre-recorded audio file URL

    # Voice configuration
    voice_provider = Column(String(50), default='deepgram')  # deepgram, 11labs, openai
    voice_id = Column(String(100), default='asteria')  # Provider-specific voice ID
    voice_speed = Column(Numeric(3, 2), default=1.0)  # 0.5 - 2.0

    # Delivery method
    delivery_method = Column(String(50), default='vapi_ai')  # vapi_ai, ringless

    # Usage tracking
    times_used = Column(Integer, default=0)
    last_used_at = Column(DateTime)

    # Settings
    is_active = Column(Boolean, default=True, index=True)
    is_default = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class VoicemailCampaign(Base):
    """Bulk voicemail campaigns"""
    __tablename__ = "voicemail_campaigns"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    template_id = Column(Integer, ForeignKey("voicemail_templates.id"))

    # Target contacts
    contact_filter = Column(JSON)  # {"stage": "closing", "tags": ["hot_lead"]}
    total_contacts = Column(Integer)

    # Status
    status = Column(String(50), default='draft', index=True)  # draft, scheduled, running, paused, completed, cancelled
    scheduled_at = Column(DateTime, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    paused_at = Column(DateTime)

    # Throttling
    throttle_rate = Column(Integer, default=100)  # calls per hour

    # Results
    sent_count = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    callback_count = Column(Integer, default=0)

    # Cost
    total_cost = Column(Numeric(10, 4), default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class VoicemailEvent(Base):
    """Voicemail analytics events"""
    __tablename__ = "voicemail_events"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    voicemail_drop_id = Column(Integer, ForeignKey("voicemail_drops.id"), nullable=False, index=True)

    event_type = Column(String(50), nullable=False, index=True)  # queued, calling, delivered, failed, listened, callback, deleted
    event_data = Column(JSON)
    event_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# CALENDAR
# ============================================================================

class CalendarEvent(Base):
    """Calendar events for scheduling"""
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
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


# ============================================================================
# INTEGRATION LOGS
# ============================================================================

class IntegrationLog(Base):
    """Log of integration actions"""
    __tablename__ = "integration_logs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
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
    """Integration credentials for third-party services"""
    __tablename__ = "integration_credentials"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    integration_type = Column(String, nullable=False)  # calendly, zoom, docusign, etc.
    api_key = Column(String, nullable=False)  # Encrypted API key
    refresh_token = Column(String)  # For OAuth integrations
    access_token = Column(String)  # For OAuth integrations
    token_expiry = Column(DateTime)  # When access token expires
    integration_metadata = Column(JSON)  # Additional integration-specific data
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# CONVERSATION SESSION & ENTITY EXTRACTION (Module 2 Gap Fix)
# ============================================================================

class ConversationSession(Base):
    """Multi-turn conversation session tracking.

    Enables context preservation across turns and agent handoffs.
    Addresses Module 2 gap: session abstraction for conversation memory.
    """
    __tablename__ = "conversation_sessions"
    __table_args__ = (
        Index('ix_conv_session_user_id', 'user_id'),
        Index('ix_conv_session_org_id', 'organization_id'),
        Index('ix_conv_session_active', 'is_active'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    session_uuid = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

    # Session state
    is_active = Column(Boolean, default=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime)
    message_count = Column(Integer, default=0)
    turn_count = Column(Integer, default=0)

    # Agent tracking
    current_agent = Column(String)  # pipeline_analyst, compliance_checker, etc.
    agents_used = Column(JSON)  # ["lead_nurturer", "rate_advisor"]
    handoff_count = Column(Integer, default=0)

    # Context summary (compressed for handoffs — Module 2.5)
    summary = Column(Text)
    active_entities = Column(JSON)  # [{"type": "loan", "id": 123}, {"type": "lead", "id": 456}]
    key_decisions = Column(JSON)  # ["Decided to lock rate", "Requested W2"]
    open_items = Column(JSON)  # ["Waiting for bank statements"]
    user_sentiment = Column(String)  # neutral, positive, frustrated, urgent

    # Last interaction
    last_message_at = Column(DateTime)
    last_agent = Column(String)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class EntityExtraction(Base):
    """Extracted entities from conversations with confidence scores.

    Enables co-reference resolution ("it", "that loan", "the borrower")
    by tracking all entities mentioned in a conversation session.
    Addresses Module 2.2 entity extraction gap.
    """
    __tablename__ = "entity_extractions"
    __table_args__ = (
        Index('ix_entity_ext_session_id', 'session_id'),
        Index('ix_entity_ext_type', 'entity_type'),
        Index('ix_entity_ext_org_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    session_id = Column(Integer, ForeignKey("conversation_sessions.id"), nullable=False)
    conversation_memory_id = Column(Integer, ForeignKey("conversation_memory.id"), nullable=True)

    # Entity details
    entity_type = Column(String, nullable=False)  # lead, loan, borrower, partner, document, rate, date, amount
    entity_value = Column(String, nullable=False)  # "John Smith", "LOAN-123456", "$350,000"
    entity_id = Column(Integer)  # FK to actual record if resolved
    entity_table = Column(String)  # "leads", "loans", "users"

    # Extraction quality
    confidence = Column(Float, default=1.0)  # 0.0-1.0
    extraction_method = Column(String)  # explicit, implicit, coreference
    source_text = Column(Text)  # The text that contained the entity

    # Usage tracking
    mention_count = Column(Integer, default=1)
    first_mentioned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_mentioned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)  # Still relevant in conversation

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# CHANNEL PREFERENCE & MESSAGE TEMPLATE (Module 5 Gap Fix)
# ============================================================================

class ChannelPreference(Base):
    """User/lead communication channel preferences.

    Unified cross-channel preference layer per Module 5 spec.
    Enforces quiet hours, preferred channels, and DNC by channel.
    """
    __tablename__ = "channel_preferences"
    __table_args__ = (
        Index('ix_channel_pref_user_id', 'user_id'),
        Index('ix_channel_pref_lead_id', 'lead_id'),
        Index('ix_channel_pref_org_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    # Preferred channels (ordered by preference)
    preferred_channels = Column(JSON, default=["email", "sms", "call"])  # ["email", "sms", "call", "teams"]

    # Channel-specific DNC
    do_not_email = Column(Boolean, default=False)
    do_not_sms = Column(Boolean, default=False)
    do_not_call = Column(Boolean, default=False)
    do_not_mail = Column(Boolean, default=False)

    # Quiet hours
    quiet_hours_start = Column(String, default="21:00")  # HH:MM
    quiet_hours_end = Column(String, default="08:00")
    quiet_days = Column(JSON)  # ["Saturday", "Sunday"]
    timezone = Column(String, default="America/New_York")

    # Language
    language = Column(String, default="en")

    # Consent tracking
    sms_consent = Column(Boolean, default=False)
    sms_consent_date = Column(DateTime)
    call_consent = Column(Boolean, default=False)
    call_consent_date = Column(DateTime)
    email_opt_in = Column(Boolean, default=True)
    email_opt_in_date = Column(DateTime)

    # Fatigue prevention (Module 5 Notification spec)
    max_contacts_per_day = Column(Integer, default=5)
    max_contacts_per_week = Column(Integer, default=15)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MessageTemplate(Base):
    """Reusable message templates across all channels.

    Standardized template management per Module 5.1 channel format rules.
    """
    __tablename__ = "message_templates"
    __table_args__ = (
        Index('ix_msg_template_org_id', 'organization_id'),
        Index('ix_msg_template_channel', 'channel'),
        Index('ix_msg_template_category', 'category'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"))

    name = Column(String, nullable=False)
    channel = Column(String, nullable=False)  # email, sms, voicemail, push, in_app
    category = Column(String)  # welcome, follow_up, document_request, rate_update, closing, post_close

    # Content
    subject = Column(String)  # For email
    body_text = Column(Text, nullable=False)  # Plain text version
    body_html = Column(Text)  # HTML version (email only)

    # Variables (for personalization)
    variables = Column(JSON)  # ["first_name", "loan_number", "lo_name", "next_step"]
    sample_preview = Column(Text)  # Rendered preview with sample data

    # Channel constraints
    character_count = Column(Integer)  # Computed from body_text
    is_sms_compatible = Column(Boolean, default=False)  # Under 320 chars

    # Compliance
    includes_unsubscribe = Column(Boolean, default=False)
    includes_equal_housing = Column(Boolean, default=False)
    includes_nmls = Column(Boolean, default=False)
    compliance_reviewed = Column(Boolean, default=False)
    compliance_reviewed_at = Column(DateTime)

    # Usage
    times_used = Column(Integer, default=0)
    last_used_at = Column(DateTime)

    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # System-provided vs user-created
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Activity & History
    "Activity",
    "StageHistory",
    # Conversations
    "Conversation",
    "ConversationMemory",
    # Conversation Sessions & Entity Extraction (Module 2)
    "ConversationSession",
    "EntityExtraction",
    # Channel Preferences & Templates (Module 5)
    "ChannelPreference",
    "MessageTemplate",
    # SMS
    "SMSMessage",
    "SMSConversation",
    # Email
    "EmailMessage",
    "Email",
    "EmailDraft",
    "EmailVerificationToken",
    # Teams
    "TeamsMessage",
    # Voicemail
    "VoicemailDrop",
    "VoicemailTemplate",
    "VoicemailCampaign",
    "VoicemailEvent",
    # Calendar
    "CalendarEvent",
    # Integration
    "IntegrationLog",
    "IntegrationCredential",
]
