"""
Marketing Campaign Models

Models for audience segmentation, campaign definitions, and drip sequences.
Addresses Module 13 gap: AudienceSegment, CampaignDefinition, DripSequence.

Usage:
    from database.models.marketing import AudienceSegment, CampaignDefinition, DripSequence
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index, Numeric
)
from sqlalchemy.orm import relationship

from db import Base

import enum


# ============================================================================
# ENUMS
# ============================================================================

class CampaignType(str, enum.Enum):
    """Types of marketing campaigns"""
    WELCOME = "welcome"
    POST_CLOSE = "post_close"
    NURTURE = "nurture"
    STALE_REENGAGEMENT = "stale_reengagement"
    RATE_DROP = "rate_drop"
    SEASONAL = "seasonal"
    REFI = "refi"
    REFERRAL = "referral"
    EVENT = "event"
    CUSTOM = "custom"


class CampaignStatus(str, enum.Enum):
    """Campaign lifecycle status"""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class DripTrigger(str, enum.Enum):
    """What triggers a drip sequence"""
    LEAD_CREATED = "lead_created"
    STAGE_CHANGE = "stage_change"
    LOAN_FUNDED = "loan_funded"
    RATE_DROP = "rate_drop"
    INACTIVITY = "inactivity"
    DATE_BASED = "date_based"
    MANUAL = "manual"
    ANNIVERSARY = "anniversary"
    BIRTHDAY = "birthday"


# ============================================================================
# AUDIENCE SEGMENT MODEL
# ============================================================================

class AudienceSegment(Base):
    """Saved audience segment definitions for campaign targeting.

    Supports Module 13.2 segmentation: by lifecycle, source, product, engagement.
    """
    __tablename__ = "audience_segments"
    __table_args__ = (
        Index('ix_audience_seg_org_id', 'organization_id'),
        Index('ix_audience_seg_active', 'is_active'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"))

    name = Column(String, nullable=False)
    description = Column(Text)

    # Segment criteria (JSON filter definition)
    # Example: {"stage": ["pre_qualified", "pre_approved"], "ai_score_min": 60, "days_since_contact": ">30"}
    criteria = Column(JSON, nullable=False)

    # Segment type for quick filtering
    segment_type = Column(String)  # lifecycle, source, product, engagement, custom

    # Size tracking
    size_estimate = Column(Integer, default=0)
    last_evaluated_at = Column(DateTime)
    last_evaluated_size = Column(Integer)

    # Compliance
    exclude_opted_out = Column(Boolean, default=True)
    exclude_dnc = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# CAMPAIGN DEFINITION MODEL
# ============================================================================

class CampaignDefinition(Base):
    """Marketing campaign template and configuration.

    Supports Module 13.1 pre-built campaigns and custom campaigns.
    Tracks full lifecycle from draft through completion with performance metrics.
    """
    __tablename__ = "campaign_definitions"
    __table_args__ = (
        Index('ix_campaign_def_org_id', 'organization_id'),
        Index('ix_campaign_def_status', 'status'),
        Index('ix_campaign_def_type', 'campaign_type'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"))

    name = Column(String, nullable=False)
    description = Column(Text)
    campaign_type = Column(SQLEnum(CampaignType), nullable=False)
    status = Column(SQLEnum(CampaignStatus), default=CampaignStatus.DRAFT)

    # Targeting
    audience_segment_id = Column(Integer, ForeignKey("audience_segments.id"), nullable=True)
    channels = Column(JSON)  # ["email", "sms", "voicemail", "push"]

    # Schedule
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    timezone = Column(String, default="America/New_York")

    # Drip sequence (if campaign uses a drip)
    drip_sequence_id = Column(Integer, ForeignKey("drip_sequences.id"), nullable=True)

    # A/B testing
    is_ab_test = Column(Boolean, default=False)
    ab_variant_a = Column(JSON)  # {"subject": "...", "body_template": "..."}
    ab_variant_b = Column(JSON)
    ab_split_pct = Column(Integer, default=50)  # % going to variant A
    ab_winner = Column(String)  # "a", "b", or null

    # Performance metrics
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    opened_count = Column(Integer, default=0)
    clicked_count = Column(Integer, default=0)
    responded_count = Column(Integer, default=0)
    converted_count = Column(Integer, default=0)  # Led to application
    unsubscribed_count = Column(Integer, default=0)
    bounced_count = Column(Integer, default=0)

    # ROI tracking
    campaign_cost = Column(Numeric(10, 2), default=0)
    attributed_revenue = Column(Numeric(12, 2), default=0)

    # Compliance (Module 13.3)
    includes_unsubscribe = Column(Boolean, default=True)  # CAN-SPAM
    includes_physical_address = Column(Boolean, default=True)
    tcpa_consent_required = Column(Boolean, default=True)  # For SMS/phone
    equal_housing_included = Column(Boolean, default=True)  # Fair Housing

    # Approval
    requires_approval = Column(Boolean, default=False)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# DRIP SEQUENCE MODEL
# ============================================================================

class DripSequence(Base):
    """Multi-touch automated drip sequence.

    Defines the steps, timing, and channels for automated outreach.
    Supports Module 13.1 pre-built campaigns: welcome, post-close, stale re-engagement, rate drop.
    """
    __tablename__ = "drip_sequences"
    __table_args__ = (
        Index('ix_drip_seq_org_id', 'organization_id'),
        Index('ix_drip_seq_active', 'is_active'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"))

    name = Column(String, nullable=False)
    description = Column(Text)

    # Trigger
    trigger_event = Column(SQLEnum(DripTrigger), nullable=False)
    trigger_config = Column(JSON)  # {"stage_from": "new", "stage_to": "prospect"} or {"days_inactive": 30}

    # Steps definition (ordered list)
    # Each step: {"day": 0, "channel": "email", "template_id": 1, "subject": "...", "body": "...", "conditions": {...}}
    steps = Column(JSON, nullable=False)

    # Exit conditions
    exit_on_response = Column(Boolean, default=True)
    exit_on_stage_change = Column(Boolean, default=True)
    exit_on_conversion = Column(Boolean, default=True)
    exit_stages = Column(JSON)  # ["application", "withdrawn"] — stages that end the drip

    # Throttling
    max_contacts_per_day = Column(Integer, default=100)
    respect_quiet_hours = Column(Boolean, default=True)
    quiet_hours_start = Column(String, default="21:00")  # 9 PM
    quiet_hours_end = Column(String, default="08:00")  # 8 AM

    # TCPA compliance
    require_sms_consent = Column(Boolean, default=True)
    require_call_consent = Column(Boolean, default=True)

    # Metrics
    total_enrolled = Column(Integer, default=0)
    total_completed = Column(Integer, default=0)
    total_exited_early = Column(Integer, default=0)
    avg_completion_rate = Column(Numeric(8, 5))

    is_active = Column(Boolean, default=True)
    is_template = Column(Boolean, default=False)  # Pre-built template vs custom
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "CampaignType",
    "CampaignStatus",
    "DripTrigger",
    "AudienceSegment",
    "CampaignDefinition",
    "DripSequence",
]
