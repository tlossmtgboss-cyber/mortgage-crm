"""
Refinance Intelligence Models

Models for tracking refinance opportunities, scenarios, and portfolio monitoring.
Addresses Module 9 gap: RefiOpportunity, RefiScenario, PortfolioMonitoring.

Usage:
    from database.models.refinance_intelligence import RefiOpportunity, RefiScenario, PortfolioMonitoringRun
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

class RefiOpportunityType(str, enum.Enum):
    """Types of refinance opportunities (Module 9.1 — 16 types)"""
    RATE_IMPROVEMENT = "rate_improvement"
    EQUITY_GROWTH = "equity_growth"
    MI_REMOVAL = "mi_removal"
    TERM_SHORTENING = "term_shortening"
    ARM_CONVERSION = "arm_conversion"
    CASH_OUT = "cash_out"
    DEBT_CONSOLIDATION = "debt_consolidation"
    DIVORCE_BUYOUT = "divorce_buyout"
    FHA_TO_CONVENTIONAL = "fha_to_conventional"
    STREAMLINE_REFI = "streamline_refi"
    VA_IRRRL = "va_irrrl"
    USDA_STREAMLINE = "usda_streamline"
    REVERSE_MORTGAGE = "reverse_mortgage"
    CONSTRUCTION_TO_PERM = "construction_to_perm"
    HELOC_CONSOLIDATION = "heloc_consolidation"
    RATE_TERM = "rate_term"


class RefiRecommendation(str, enum.Enum):
    """Recommendation action for a refi opportunity"""
    STRONG_REFI = "strong_refi"
    MODERATE_REFI = "moderate_refi"
    MONITOR = "monitor"
    NOT_RECOMMENDED = "not_recommended"


class RefiOpportunityStatus(str, enum.Enum):
    """Lifecycle status of a refi opportunity"""
    IDENTIFIED = "identified"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    APPLICATION = "application"
    PROCESSING = "processing"
    FUNDED = "funded"
    DECLINED = "declined"
    EXPIRED = "expired"


# ============================================================================
# REFI OPPORTUNITY MODEL
# ============================================================================

class RefiOpportunity(Base):
    """Individual refinance opportunity identified for a client.

    Tracks the full lifecycle from detection through outreach to conversion.
    Integrates with MUMClient for portfolio context and Rate tools for market data.
    """
    __tablename__ = "refi_opportunities"
    __table_args__ = (
        Index('ix_refi_opp_org_id', 'organization_id'),
        Index('ix_refi_opp_client_id', 'mum_client_id'),
        Index('ix_refi_opp_status', 'status'),
        Index('ix_refi_opp_score', 'refi_score'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    mum_client_id = Column(Integer, ForeignKey("mum_clients.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

    # Opportunity type and scoring
    opportunity_type = Column(SQLEnum(RefiOpportunityType), nullable=False)
    refi_score = Column(Integer)  # 0-100
    recommendation = Column(SQLEnum(RefiRecommendation), default=RefiRecommendation.MONITOR)

    # Current loan details
    original_rate = Column(Numeric(5, 3))
    original_term = Column(Integer)  # months
    original_amount = Column(Numeric(12, 2))
    current_balance = Column(Numeric(12, 2))
    current_payment = Column(Numeric(10, 2))
    months_remaining = Column(Integer)
    has_pmi = Column(Boolean, default=False)
    pmi_monthly = Column(Numeric(8, 2))

    # Market comparison
    current_market_rate = Column(Numeric(5, 3))
    rate_advantage = Column(Numeric(5, 3))  # original_rate - market_rate

    # Property / equity
    estimated_home_value = Column(Numeric(12, 2))
    estimated_equity = Column(Numeric(12, 2))
    estimated_ltv = Column(Numeric(6, 2))

    # Savings estimates
    projected_new_rate = Column(Numeric(5, 3))
    projected_new_payment = Column(Numeric(10, 2))
    estimated_monthly_savings = Column(Numeric(10, 2))
    estimated_total_savings = Column(Numeric(12, 2))  # Over remaining term
    estimated_closing_costs = Column(Numeric(10, 2))
    break_even_months = Column(Integer)

    # Lifecycle
    status = Column(SQLEnum(RefiOpportunityStatus), default=RefiOpportunityStatus.IDENTIFIED)
    identified_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    contacted_at = Column(DateTime)
    last_outreach_at = Column(DateTime)
    outreach_count = Column(Integer, default=0)
    declined_reason = Column(String)
    converted_loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

    # Analysis metadata
    analysis_run_id = Column(Integer, ForeignKey("portfolio_monitoring_runs.id"), nullable=True)
    analysis_notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# REFI SCENARIO MODEL
# ============================================================================

class RefiScenario(Base):
    """Rate/term/cashout scenarios for a refinance opportunity.

    Each opportunity can have multiple scenarios for borrower comparison.
    """
    __tablename__ = "refi_scenarios"
    __table_args__ = (
        Index('ix_refi_scenario_opp_id', 'opportunity_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("refi_opportunities.id"), nullable=False)

    scenario_type = Column(String, nullable=False)  # rate_reduction, term_reduction, cash_out, consolidation, mi_removal
    scenario_label = Column(String)  # Human-friendly label

    # Proposed terms
    new_rate = Column(Numeric(5, 3))
    new_term = Column(Integer)  # months
    new_loan_amount = Column(Numeric(12, 2))
    cash_out_amount = Column(Numeric(12, 2), default=0)
    points = Column(Numeric(5, 3), default=0)

    # Payment impact
    new_monthly_payment = Column(Numeric(10, 2))
    payment_change = Column(Numeric(10, 2))  # negative = savings

    # Savings analysis
    total_interest_savings = Column(Numeric(12, 2))
    closing_costs = Column(Numeric(10, 2))
    break_even_months = Column(Integer)
    net_benefit_5yr = Column(Numeric(12, 2))  # Net savings over 5 years
    net_benefit_life = Column(Numeric(12, 2))  # Net savings over life of loan

    is_recommended = Column(Boolean, default=False)
    recommendation_reason = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# PORTFOLIO MONITORING RUN MODEL
# ============================================================================

class PortfolioMonitoringRun(Base):
    """Batch portfolio analysis run tracking.

    Records each time the system scans the portfolio for refi opportunities.
    """
    __tablename__ = "portfolio_monitoring_runs"
    __table_args__ = (
        Index('ix_portfolio_run_org_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)

    # Run metadata
    run_type = Column(String, default="scheduled")  # scheduled, manual, rate_trigger
    trigger_reason = Column(String)  # "rate_drop_50bps", "quarterly_review", "manual"

    # Results
    clients_analyzed = Column(Integer, default=0)
    opportunities_created = Column(Integer, default=0)
    opportunities_updated = Column(Integer, default=0)
    highest_savings_monthly = Column(Numeric(10, 2))
    total_potential_volume = Column(Numeric(14, 2))  # Total refi volume identified

    # Market snapshot at time of run
    market_rate_30yr = Column(Numeric(5, 3))
    market_rate_15yr = Column(Numeric(5, 3))
    market_rate_arm = Column(Numeric(5, 3))

    # Timing
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)

    status = Column(String, default="running")  # running, completed, failed
    error_message = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "RefiOpportunityType",
    "RefiRecommendation",
    "RefiOpportunityStatus",
    "RefiOpportunity",
    "RefiScenario",
    "PortfolioMonitoringRun",
]
