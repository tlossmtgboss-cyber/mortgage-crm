"""
Campaign Models for Acquisition Engine
CampaignBlueprint - Immutable templates for campaign strategies
CampaignInstance - Runtime campaign state and metrics
"""

from sqlalchemy import Column, String, Integer, Numeric, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import Base


class GoalType(str, Enum):
    """Campaign goal types"""
    PURCHASE_BUYERS = "PURCHASE_BUYERS"
    REFI_PROSPECTS = "REFI_PROSPECTS"
    REALTOR_PARTNERS = "REALTOR_PARTNERS"
    PAST_CLIENT_REFI = "PAST_CLIENT_REFI"
    FIRST_TIME_BUYERS = "FIRST_TIME_BUYERS"


class CampaignStatus(str, Enum):
    """Campaign lifecycle status"""
    DRAFT = "DRAFT"
    LAUNCHING = "LAUNCHING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class BudgetType(str, Enum):
    """Budget period types"""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    TOTAL = "TOTAL"


class CampaignBlueprint(Base):
    """
    Campaign Blueprint - Immutable template for campaign strategies

    Blueprints are pre-configured campaign templates that define:
    - Goal type (purchase buyers, refi prospects, etc.)
    - Communication sequences (SMS, Email)
    - Dialer rules and priorities
    - Budget guardrails

    Blueprints are versioned and can be updated without affecting active campaigns.
    """
    __tablename__ = "campaign_blueprints"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Blueprint Identity
    name = Column(String(255), nullable=False)
    description = Column(Text)
    version = Column(String(50), nullable=False, default="1.0.0")
    goal_type = Column(String(50), nullable=False)  # GoalType enum value
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # Default blueprint for goal type

    # Template References - IDs of sequences to activate
    sms_sequence_ids = Column(JSON, default=list)  # List of SMS sequence IDs
    email_sequence_ids = Column(JSON, default=list)  # List of email sequence IDs

    # Dialer Configuration
    dialer_rules = Column(JSON, default=dict)
    # Example: {
    #   "priority": "URGENT",
    #   "max_attempts": 5,
    #   "call_window_start": "09:00",
    #   "call_window_end": "20:00",
    #   "retry_delay_hours": 4
    # }

    # Speed-to-Lead Configuration
    speed_to_lead_config = Column(JSON, default=dict)
    # Example: {
    #   "hot_lead_sla_seconds": 300,  # 5 minutes
    #   "warm_lead_sla_seconds": 3600,  # 1 hour
    #   "enable_sms": true,
    #   "enable_email": true,
    #   "enable_dialer": true,
    #   "enable_push_notification": true
    # }

    # Budget Guardrails
    min_budget = Column(Numeric(10, 2))
    max_budget = Column(Numeric(10, 2))
    recommended_budget = Column(Numeric(10, 2))

    # Targeting Defaults
    default_targeting = Column(JSON, default=dict)
    # Example: {
    #   "property_types": ["single_family", "condo"],
    #   "loan_types": ["conventional", "fha"],
    #   "credit_score_min": 620
    # }

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)  # User ID who created the blueprint

    # Relationships
    instances = relationship("CampaignInstance", back_populates="blueprint")

    def __repr__(self):
        return f"<CampaignBlueprint {self.name} v{self.version}>"


class CampaignInstance(Base):
    """
    Campaign Instance - Active campaign with runtime state and metrics

    Created when an LO launches a campaign. Tracks:
    - LO inputs (budget, targeting, capacity)
    - Runtime state (active, paused, etc.)
    - Performance metrics (leads, meetings, applications, funded loans)
    - Revenue attribution
    """
    __tablename__ = "campaign_instances"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Ownership
    organization_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)  # LO who launched

    # Blueprint Reference
    blueprint_id = Column(UUID(as_uuid=True), ForeignKey("campaign_blueprints.id"), index=True)
    blueprint = relationship("CampaignBlueprint", back_populates="instances")

    # Campaign Identity
    name = Column(String(255))  # Auto-generated or user-provided
    goal_type = Column(String(50), nullable=False)

    # LO Inputs
    budget_type = Column(String(20), nullable=False, default="DAILY")  # BudgetType enum
    budget_amount = Column(Numeric(10, 2), nullable=False)
    market_geo = Column(JSON, nullable=False)
    # Example: {
    #   "state": "CA",
    #   "metro": "San Francisco",
    #   "zip_codes": ["94102", "94103"],
    #   "radius_miles": 25
    # }

    product_focus = Column(String(50))  # "PURCHASE", "REFINANCE", "BOTH"
    capacity_leads_per_week = Column(Integer)

    # Runtime Configuration (copied from blueprint, can be customized)
    sms_sequences_active = Column(JSON, default=list)
    email_sequences_active = Column(JSON, default=list)
    dialer_config = Column(JSON, default=dict)
    speed_to_lead_config = Column(JSON, default=dict)

    # Runtime State
    status = Column(String(20), nullable=False, default="DRAFT")  # CampaignStatus enum
    funnel_url = Column(String(500))  # Generated landing page URL
    tracking_pixel_id = Column(String(100))  # For retargeting

    # Lifecycle Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    launched_at = Column(DateTime)  # When LAUNCHING started
    activated_at = Column(DateTime)  # When ACTIVE started
    paused_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Error Tracking
    last_error = Column(Text)
    error_count = Column(Integer, default=0)

    # ==================== METRICS ====================
    # Spend Tracking
    total_spend = Column(Numeric(10, 2), default=0)
    spend_today = Column(Numeric(10, 2), default=0)
    spend_this_week = Column(Numeric(10, 2), default=0)
    spend_this_month = Column(Numeric(10, 2), default=0)

    # Funnel Metrics
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    visitors = Column(Integer, default=0)

    # Lead Metrics
    leads_generated = Column(Integer, default=0)
    leads_hot = Column(Integer, default=0)
    leads_warm = Column(Integer, default=0)
    leads_cold = Column(Integer, default=0)

    # Conversion Metrics
    meetings_booked = Column(Integer, default=0)
    meetings_completed = Column(Integer, default=0)
    applications_started = Column(Integer, default=0)
    applications_completed = Column(Integer, default=0)
    loans_submitted = Column(Integer, default=0)
    loans_approved = Column(Integer, default=0)
    loans_closed = Column(Integer, default=0)

    # Revenue Attribution
    revenue_attributed = Column(Numeric(12, 2), default=0)
    total_loan_volume = Column(Numeric(14, 2), default=0)  # Sum of funded loan amounts

    # Speed-to-Lead Metrics
    avg_speed_to_first_contact_seconds = Column(Integer)
    hot_leads_within_sla = Column(Integer, default=0)
    hot_leads_missed_sla = Column(Integer, default=0)

    # Calculated Metrics (updated periodically)
    cost_per_lead = Column(Numeric(10, 2))
    cost_per_meeting = Column(Numeric(10, 2))
    cost_per_application = Column(Numeric(10, 2))
    cost_per_funded_loan = Column(Numeric(10, 2))
    roi_percentage = Column(Numeric(8, 2))  # (revenue - spend) / spend * 100

    # Relationships
    events = relationship("AcquisitionEvent", back_populates="campaign_instance")
    temperatures = relationship("LeadTemperature", back_populates="campaign_instance")
    attributions = relationship("CampaignAttribution", back_populates="campaign_instance")

    def __repr__(self):
        return f"<CampaignInstance {self.id} [{self.status}]>"

    def calculate_cost_metrics(self):
        """Calculate cost-per-X metrics based on current spend and conversions"""
        if self.total_spend and self.total_spend > 0:
            spend = float(self.total_spend)

            if self.leads_generated > 0:
                self.cost_per_lead = spend / self.leads_generated

            if self.meetings_booked > 0:
                self.cost_per_meeting = spend / self.meetings_booked

            if self.applications_started > 0:
                self.cost_per_application = spend / self.applications_started

            if self.loans_closed > 0:
                self.cost_per_funded_loan = spend / self.loans_closed

            if self.revenue_attributed and float(self.revenue_attributed) > 0:
                self.roi_percentage = ((float(self.revenue_attributed) - spend) / spend) * 100
