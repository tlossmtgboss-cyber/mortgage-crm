"""
Call Screening Database Models
Tables for spam filtering, blocklist/whitelist management, and screening logs.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON,
    Index, ForeignKey
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class PhoneBlocklist(Base):
    """
    Blocked phone numbers for spam filtering.

    Numbers on this list are immediately hung up on with no message.
    Supports expiration for temporary blocks.
    """
    __tablename__ = "phone_blocklist"
    __table_args__ = (
        Index('idx_blocklist_phone', 'phone_number'),
        Index('idx_blocklist_active_expires', 'is_active', 'expires_at'),
    )

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, nullable=False)  # E.164 format
    reason = Column(String(100), nullable=False)  # spam, harassment, robocall, etc.
    source = Column(String(50), nullable=False)  # manual, telnyx_lookup, user_report, auto_detected
    spam_score = Column(Integer)  # 0-100 from phone lookup provider
    blocked_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    blocked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # NULL = permanent
    is_active = Column(Boolean, default=True)
    call_attempts_since_block = Column(Integer, default=0)
    extra_data = Column(JSON)  # carrier info, lookup details
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PhoneWhitelist(Base):
    """
    Whitelisted phone numbers for known callers.

    Categories:
    - client: Existing borrower with active/past loan
    - lead: Converted lead from previous call
    - referral_partner: Realtor, agent, etc.
    - vip: Important callers (manually added)
    - team: Internal team members
    """
    __tablename__ = "phone_whitelist"
    __table_args__ = (
        Index('idx_whitelist_phone', 'phone_number'),
        Index('idx_whitelist_category', 'category'),
    )

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, nullable=False)  # E.164 format
    name = Column(String(255))  # Caller name
    category = Column(String(50), nullable=False)  # client, lead, referral_partner, vip, team
    source = Column(String(50), nullable=False)  # auto_converted, manual, crm_sync, lead_creation
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # For team/partner entries
    added_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    added_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text)
    priority = Column(Integer, default=0)  # Higher = more important (affects routing)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CallScreeningLog(Base):
    """
    Log of all call screening decisions for analytics and debugging.

    Records every incoming call and the screening decision made.
    """
    __tablename__ = "call_screening_log"
    __table_args__ = (
        Index('idx_screening_call_sid', 'call_sid'),
        Index('idx_screening_phone', 'phone_number'),
        Index('idx_screening_decision_date', 'screening_decision', 'created_at'),
    )

    id = Column(Integer, primary_key=True, index=True)
    call_sid = Column(String(100), nullable=False)  # Telnyx call control ID
    phone_number = Column(String(20), nullable=False)  # Caller's number
    screening_decision = Column(String(20), nullable=False)  # ALLOW, BLOCK, SCREEN
    decision_reason = Column(String(255))  # whitelist_match, blocklist_match, spam_detected, unknown_screened
    lookup_performed = Column(Boolean, default=False)
    lookup_result = Column(JSON)  # Full phone lookup response
    lookup_cost_cents = Column(Integer)  # Cost tracking
    screening_duration_ms = Column(Integer)  # How long screening took
    caller_stated_name = Column(String(255))  # From screening flow
    caller_stated_reason = Column(Text)  # From screening flow
    connected_to_ai = Column(Boolean, default=False)  # Did call proceed to AI?
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)


class PhoneLookupCache(Base):
    """
    Cache for phone Lookup API results.

    Stores lookup results for 30 days to avoid repeated API calls.
    Cost optimization: ~$0.05 per lookup saved on repeat callers.
    """
    __tablename__ = "phone_lookup_cache"

    phone_number = Column(String(20), primary_key=True)  # E.164 format
    carrier_name = Column(String(255))
    carrier_type = Column(String(50))  # wireless, landline, voip
    line_type = Column(String(50))  # mobile, landline, fixedVoip, nonFixedVoip, etc.
    caller_name = Column(String(255))  # CNAM lookup result
    caller_type = Column(String(50))  # CONSUMER, BUSINESS
    country_code = Column(String(5))
    spam_score = Column(Integer)  # 0-100, calculated from indicators
    risk_level = Column(String(20))  # low, medium, high
    lookup_provider = Column(String(50), default="telnyx")
    lookup_data = Column(JSON)  # Full API response
    cached_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)  # Typically 30 days from cached_at
