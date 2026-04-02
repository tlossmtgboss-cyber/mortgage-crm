"""
Scoring Models for Acquisition Engine
LeadTemperature - Computed lead scoring based on behavioral events
CampaignAttribution - Revenue attribution tracking
"""

from sqlalchemy import Column, String, Integer, Numeric, DateTime, Boolean, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import Base


class Temperature(str, Enum):
    """Lead temperature levels"""
    COLD = "COLD"       # First touch, minimal engagement
    WARM = "WARM"       # Educational engagement, showing interest
    HOT = "HOT"         # Explicit intent, ready to convert
    REPEAT = "REPEAT"   # Multi-session visitor, returning interest


class AttributionType(str, Enum):
    """Attribution models for revenue tracking"""
    FIRST_TOUCH = "first_touch"   # 100% credit to first interaction
    LAST_TOUCH = "last_touch"     # 100% credit to last interaction before conversion
    LINEAR = "linear"             # Equal credit to all touchpoints
    TIME_DECAY = "time_decay"     # More credit to recent touchpoints
    POSITION_BASED = "position_based"  # 40% first, 40% last, 20% middle


class ConversionType(str, Enum):
    """Types of conversions to track"""
    LEAD = "lead"
    MEETING_BOOKED = "meeting_booked"
    MEETING_COMPLETED = "meeting_completed"
    APPLICATION_STARTED = "application_started"
    APPLICATION_COMPLETED = "application_completed"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    FUNDED = "funded"


class LeadTemperature(Base):
    """
    Lead Temperature - Real-time computed lead scoring

    Temperature is calculated deterministically based on event history:
    - HOT: Explicit intent signals (meeting booked, form submitted, 75%+ video)
    - WARM: Educational engagement (calculator, quiz, pricing page)
    - REPEAT: Multi-session visitor (3+ sessions, returning after 24h)
    - COLD: First touch, minimal engagement

    Score is 0-100 with breakdown by component.
    """
    __tablename__ = "lead_temperatures"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Lead Reference (unique - one temperature record per lead)
    lead_id = Column(Integer, unique=True, nullable=False, index=True)

    # Campaign Reference (which campaign sourced this lead)
    campaign_instance_id = Column(UUID(as_uuid=True), ForeignKey("campaign_instances.id"), index=True)
    campaign_instance = relationship("CampaignInstance", back_populates="temperatures")

    # ==================== TEMPERATURE ====================
    temperature = Column(String(20), nullable=False, default="COLD")  # Temperature enum
    score = Column(Integer, default=0)  # 0-100 overall score

    # Temperature history (for tracking changes)
    previous_temperature = Column(String(20))
    temperature_changed_at = Column(DateTime)

    # ==================== SCORE COMPONENTS ====================
    # Each component is 0-100, weighted to compute final score

    engagement_score = Column(Integer, default=0)
    # Based on: page views, time on site, content consumption
    # Weights: page_view=1, blog_read=3, video_25=5, video_50=10, video_75=15

    intent_score = Column(Integer, default=0)
    # Based on: explicit intent signals
    # Weights: pricing_view=10, calculator=15, form_start=20, form_submit=30, meeting=40

    recency_score = Column(Integer, default=0)
    # Based on: time since last engagement
    # 0-24h=100, 24-48h=80, 48-72h=60, 3-7d=40, 7-14d=20, 14d+=10

    frequency_score = Column(Integer, default=0)
    # Based on: number of sessions/interactions
    # 1 session=20, 2=40, 3=60, 4=80, 5+=100

    profile_score = Column(Integer, default=0)
    # Based on: lead profile completeness and quality
    # email=10, phone=10, loan_amount=10, credit_score=10, property_type=10, etc.

    # ==================== SIGNAL TRACKING ====================
    # Last signal that triggered each temperature level
    last_hot_signal = Column(String(100))  # Event type that made them hot
    last_hot_signal_at = Column(DateTime)
    last_warm_signal = Column(String(100))
    last_warm_signal_at = Column(DateTime)

    # Decay tracking (temperature decays over time without activity)
    last_decay_calculation = Column(DateTime)
    days_since_last_activity = Column(Integer, default=0)

    # ==================== SESSION TRACKING ====================
    total_sessions = Column(Integer, default=0)
    total_page_views = Column(Integer, default=0)
    total_events = Column(Integer, default=0)
    total_time_on_site_seconds = Column(Integer, default=0)

    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime)

    # ==================== CONVERSION TRACKING ====================
    is_converted = Column(Boolean, default=False)
    converted_at = Column(DateTime)
    conversion_type = Column(String(50))  # Which conversion event

    # ==================== TIMESTAMPS ====================
    last_calculated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<LeadTemperature lead={self.lead_id} temp={self.temperature} score={self.score}>"

    def calculate_weighted_score(self) -> int:
        """Calculate weighted score from components"""
        weights = {
            'engagement': 0.15,
            'intent': 0.35,
            'recency': 0.25,
            'frequency': 0.15,
            'profile': 0.10,
        }

        weighted = (
            (self.engagement_score or 0) * weights['engagement'] +
            (self.intent_score or 0) * weights['intent'] +
            (self.recency_score or 0) * weights['recency'] +
            (self.frequency_score or 0) * weights['frequency'] +
            (self.profile_score or 0) * weights['profile']
        )

        return min(100, max(0, int(weighted)))

    def determine_temperature(self) -> str:
        """Determine temperature level from score and signals"""
        # Hot signals override score
        if self.last_hot_signal and self.days_since_last_activity <= 3:
            return Temperature.HOT.value

        # Repeat visitor detection
        if self.total_sessions >= 3 and self.days_since_last_activity <= 7:
            return Temperature.REPEAT.value

        # Score-based determination
        score = self.score or 0
        if score >= 70:
            return Temperature.HOT.value
        elif score >= 40:
            return Temperature.WARM.value
        else:
            return Temperature.COLD.value


class CampaignAttribution(Base):
    """
    Campaign Attribution - Track revenue attribution from campaigns

    Connects campaign spend to actual revenue (funded loans).
    Supports multiple attribution models:
    - First touch: 100% credit to first campaign
    - Last touch: 100% credit to last campaign
    - Linear: Equal credit across all touchpoints
    """
    __tablename__ = "campaign_attributions"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Campaign Reference
    campaign_instance_id = Column(UUID(as_uuid=True), ForeignKey("campaign_instances.id"), index=True)
    campaign_instance = relationship("CampaignInstance", back_populates="attributions")

    # Lead/Loan Reference
    lead_id = Column(Integer, index=True)
    loan_id = Column(Integer, index=True)  # Once lead converts to loan

    # ==================== ATTRIBUTION ====================
    attribution_type = Column(String(50), default="first_touch")  # AttributionType enum
    attribution_credit = Column(Numeric(5, 2), default=1.00)  # 0.00-1.00 (percentage of credit)

    # Position in attribution chain
    touchpoint_position = Column(Integer)  # 1=first, n=last
    total_touchpoints = Column(Integer)

    # ==================== CONVERSION TRACKING ====================
    conversion_type = Column(String(50), nullable=False)  # ConversionType enum
    conversion_date = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Conversion value at each stage
    is_lead = Column(Boolean, default=False)
    is_meeting = Column(Boolean, default=False)
    is_application = Column(Boolean, default=False)
    is_funded = Column(Boolean, default=False)

    # ==================== REVENUE TRACKING ====================
    # For funded loans
    loan_amount = Column(Numeric(12, 2))
    loan_type = Column(String(50))  # conventional, fha, va, etc.

    # Estimated revenue (based on average revenue per funded loan)
    estimated_revenue = Column(Numeric(10, 2))

    # Actual revenue (if tracked)
    actual_revenue = Column(Numeric(10, 2))
    revenue_recorded_at = Column(DateTime)

    # Revenue attribution (credit * revenue)
    attributed_revenue = Column(Numeric(10, 2))

    # ==================== COST TRACKING ====================
    # Spend attributed to this conversion
    attributed_spend = Column(Numeric(10, 2))

    # Cost metrics
    cost_per_this_conversion = Column(Numeric(10, 2))

    # ==================== TIMESTAMPS ====================
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<CampaignAttribution campaign={self.campaign_instance_id} type={self.conversion_type}>"

    def calculate_attributed_revenue(self):
        """Calculate attributed revenue based on credit"""
        if self.actual_revenue:
            self.attributed_revenue = float(self.actual_revenue) * float(self.attribution_credit or 1)
        elif self.estimated_revenue:
            self.attributed_revenue = float(self.estimated_revenue) * float(self.attribution_credit or 1)


# Indexes for common queries
Index('idx_temperature_campaign', LeadTemperature.campaign_instance_id, LeadTemperature.temperature)
Index('idx_temperature_score', LeadTemperature.temperature, LeadTemperature.score.desc())
Index('idx_attribution_campaign_type', CampaignAttribution.campaign_instance_id, CampaignAttribution.conversion_type)
Index('idx_attribution_lead', CampaignAttribution.lead_id, CampaignAttribution.conversion_date)
