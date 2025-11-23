"""
Email Monitoring System - SQLAlchemy Models
12 tables for intelligent email filtering with AI
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, Enum, Numeric, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


# Enums
class EmailProviderEnum(str, enum.Enum):
    GMAIL = "gmail"
    OUTLOOK = "outlook"


class MonitorTypeEnum(str, enum.Enum):
    FROM = "from"
    TO = "to"
    CC = "cc"
    ANY = "any"


class MatchLogicEnum(str, enum.Enum):
    ADDRESS_ONLY = "address_only"
    KEYWORD_ONLY = "keyword_only"
    ADDRESS_AND_KEYWORD = "address_and_keyword"
    ADDRESS_OR_KEYWORD = "address_or_keyword"


class ProcessingStatusEnum(str, enum.Enum):
    CAPTURED = "captured"
    PROCESSING = "processing"
    ASSIGNED = "assigned"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class FilterStageEnum(str, enum.Enum):
    QUICK_SPAM = "quick_spam"
    CRM_MATCH = "crm_match"
    AI_ANALYSIS = "ai_analysis"


class EntityTypeEnum(str, enum.Enum):
    LOAN = "loan"
    LEAD = "lead"
    CONTACT = "contact"
    REFERRAL_PARTNER = "referral_partner"
    VENDOR = "vendor"


class LinkMethodEnum(str, enum.Enum):
    LOAN_NUMBER = "loan_number"
    EMAIL_MATCH = "email_match"
    MANUAL = "manual"
    AI_SUGGESTED = "ai_suggested"


# Models
class EmailMonitorAddress(Base):
    """Email addresses to monitor"""
    __tablename__ = "email_monitor_addresses"

    id = Column(Integer, primary_key=True, index=True)
    email_address = Column(String(255), nullable=False, index=True)
    description = Column(String(500))
    monitor_type = Column(Enum(MonitorTypeEnum), default=MonitorTypeEnum.FROM)
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EmailMonitorKeyword(Base):
    """Keywords and phrases to search for"""
    __tablename__ = "email_monitor_keywords"

    id = Column(Integer, primary_key=True, index=True)
    keyword_phrase = Column(String(255), nullable=False, index=True)
    search_location = Column(Enum("subject", "body", "both", name="search_location_enum"), default="both")
    match_type = Column(Enum("exact", "contains", "starts_with", "ends_with", name="match_type_enum"), default="contains")
    category = Column(String(100), index=True)
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EmailMonitorRule(Base):
    """Monitoring rules configuration"""
    __tablename__ = "email_monitor_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String(255), nullable=False)
    description = Column(Text)
    match_logic = Column(String(30), default="address_or_keyword")
    auto_assign_to_loan = Column(Boolean, default=False)
    loan_match_strategy = Column(Enum("loan_number", "borrower_email", "property_address", "manual", name="loan_match_enum"), default="loan_number")
    priority = Column(Integer, default=0, index=True)
    is_active = Column(Boolean, default=True, index=True)
    use_ai_filter = Column(Boolean, default=True)
    min_confidence_score = Column(Numeric(3, 2), default=0.70)
    allow_spam_check = Column(Boolean, default=True)
    require_crm_match = Column(Boolean, default=False)
    enabled_providers = Column(String(50), default="gmail,outlook")
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EmailMonitorCaptured(Base):
    """Captured emails"""
    __tablename__ = "email_monitor_captured"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("email_monitor_rules.id"), nullable=False)
    email_provider = Column(String(20), default="gmail")
    provider_message_id = Column(String(255), nullable=False)
    from_email = Column(String(255), index=True)
    to_email = Column(Text)
    cc_email = Column(Text)
    subject = Column(Text)
    body_preview = Column(Text)
    received_date = Column(DateTime(timezone=True), index=True)
    matched_addresses = Column(JSON)
    matched_keywords = Column(JSON)
    auto_assigned_loan_id = Column(Integer, ForeignKey("loans.id"))
    processing_status = Column(Enum(ProcessingStatusEnum), default=ProcessingStatusEnum.CAPTURED, index=True)
    processing_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))

    crm_links = relationship("EmailCRMLink", back_populates="email")

    __table_args__ = (
        UniqueConstraint('email_provider', 'provider_message_id', name='unique_provider_message'),
        Index('idx_provider_received', 'email_provider', 'received_date'),
    )


class EmailCRMLink(Base):
    """Links emails to CRM entities"""
    __tablename__ = "email_crm_links"

    id = Column(Integer, primary_key=True, index=True)
    captured_email_id = Column(Integer, ForeignKey("email_monitor_captured.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(Enum(EntityTypeEnum), nullable=False)
    entity_id = Column(Integer, nullable=False)
    link_confidence = Column(Numeric(3, 2), default=1.00)
    link_method = Column(Enum(LinkMethodEnum), default=LinkMethodEnum.EMAIL_MATCH)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("employees.id"))

    email = relationship("EmailMonitorCaptured", back_populates="crm_links")

    __table_args__ = (
        UniqueConstraint('captured_email_id', 'entity_type', 'entity_id', name='unique_email_entity_link'),
        Index('idx_entity_lookup', 'entity_type', 'entity_id'),
    )


class EmailRelevanceAnalysis(Base):
    """AI analysis results log"""
    __tablename__ = "email_relevance_analysis"

    id = Column(Integer, primary_key=True, index=True)
    email_provider = Column(String(20), default="gmail")
    provider_message_id = Column(String(255), nullable=False)
    from_email = Column(String(255))
    subject = Column(Text)
    is_relevant = Column(Boolean, index=True)
    relevance_category = Column(String(100), index=True)
    confidence_score = Column(Numeric(3, 2))
    analysis_reason = Column(Text)
    matched_entities = Column(JSON)
    filter_stage = Column(Enum(FilterStageEnum), nullable=False)
    processing_time_ms = Column(Integer)
    was_captured = Column(Boolean, default=False)
    user_feedback = Column(Enum("correct", "incorrect", "spam_missed", "relevant_missed", name="feedback_enum"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index('idx_provider_message_analysis', 'email_provider', 'provider_message_id'),
    )


class EmailFilterWhitelist(Base):
    """Trusted senders"""
    __tablename__ = "email_filter_whitelist"

    id = Column(Integer, primary_key=True, index=True)
    email_pattern = Column(String(255), nullable=False, index=True)
    description = Column(String(500))
    whitelist_type = Column(String(20), default="email")
    auto_assign_category = Column(String(100))
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmailFilterBlacklist(Base):
    """Blocked senders"""
    __tablename__ = "email_filter_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    email_pattern = Column(String(255), nullable=False, index=True)
    description = Column(String(500))
    blacklist_type = Column(String(20), default="email")
    reason = Column(String(255))
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmailProviderConfig(Base):
    """Email provider configuration"""
    __tablename__ = "email_provider_config"

    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String(20), unique=True, nullable=False)
    is_enabled = Column(Boolean, default=True, index=True)
    display_name = Column(String(100))
    config_json = Column(JSON)
    last_poll_time = Column(DateTime(timezone=True))
    total_emails_processed = Column(Integer, default=0)
    total_emails_captured = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GmailOAuthToken(Base):
    """Gmail OAuth tokens"""
    __tablename__ = "gmail_oauth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, default=1, unique=True)
    token_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True))


class OutlookOAuthToken(Base):
    """Outlook OAuth tokens"""
    __tablename__ = "outlook_oauth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, default=1, unique=True)
    token_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True))


class EmailMonitorLog(Base):
    """System activity log"""
    __tablename__ = "email_monitor_log"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(Enum("scan_started", "scan_completed", "email_captured", "rule_matched", "auto_assigned", "error", name="event_type_enum"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("email_monitor_rules.id"))
    captured_email_id = Column(Integer, ForeignKey("email_monitor_captured.id"))
    details = Column(JSON)
    emails_scanned = Column(Integer, default=0)
    emails_captured = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
