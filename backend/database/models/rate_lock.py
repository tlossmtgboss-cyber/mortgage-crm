"""
Rate Lock & Market Data Models

Models for tracking individual rate locks and historical market data.
Addresses Module 6 gap: RateLock ledger, RateMarketData.

Usage:
    from database.models.rate_lock import RateLock, RateMarketData
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index, Numeric
)
from sqlalchemy.orm import relationship

from db import Base
from database.enums import RateLockStatus, RateLockRecommendation


# ============================================================================
# RATE LOCK LEDGER
# ============================================================================

class RateLock(Base):
    """Individual rate lock record for a loan.

    Tracks the full lifecycle of a rate lock including extensions,
    float-down exercises, and expiration handling.
    """
    __tablename__ = "rate_locks"
    __table_args__ = (
        Index('ix_rate_locks_loan_id', 'loan_id'),
        Index('ix_rate_locks_org_id', 'organization_id'),
        Index('ix_rate_locks_status', 'status'),
        Index('ix_rate_locks_expiration', 'lock_expiration_date'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    # Lock details
    status = Column(SQLEnum(RateLockStatus), default=RateLockStatus.ELIGIBLE_NO_LOCK)
    lock_type = Column(String)  # standard, float_down, rate_hold, extended
    lock_period_days = Column(Integer)  # 15, 30, 45, 60, 90

    # Rate info
    rate_locked = Column(Numeric(5, 3))
    apr_locked = Column(Numeric(5, 3))
    points = Column(Numeric(5, 3), default=0)
    lock_cost = Column(Numeric(10, 2))  # Cost of the lock if applicable

    # Dates
    lock_date = Column(DateTime)
    lock_expiration_date = Column(DateTime)
    original_expiration_date = Column(DateTime)  # Before any extensions

    # Extensions
    extension_count = Column(Integer, default=0)
    extension_days_total = Column(Integer, default=0)
    extension_cost_total = Column(Numeric(10, 2), default=0)
    last_extension_date = Column(DateTime)

    # Float-down
    float_down_available = Column(Boolean, default=False)
    float_down_exercised = Column(Boolean, default=False)
    float_down_date = Column(DateTime)
    float_down_original_rate = Column(Numeric(5, 3))
    float_down_new_rate = Column(Numeric(5, 3))

    # AI recommendation at time of lock
    ai_recommendation = Column(SQLEnum(RateLockRecommendation), nullable=True)
    ai_lock_score = Column(Integer)  # 0-100
    ai_reasoning = Column(Text)

    # Market conditions at time of lock
    market_rate_at_lock = Column(Numeric(5, 3))
    market_trend_at_lock = Column(String)  # up, down, stable

    # Resolution
    resolved_at = Column(DateTime)
    resolution = Column(String)  # funded, expired, cancelled, relocked

    # Audit
    locked_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# RATE MARKET DATA
# ============================================================================

class RateMarketData(Base):
    """Historical market rate data for trend analysis.

    Stores daily market rate snapshots for trending, comparison, and
    rate drop trigger detection.
    """
    __tablename__ = "rate_market_data"
    __table_args__ = (
        Index('ix_rate_market_date', 'snapshot_date'),
        Index('ix_rate_market_org', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    snapshot_date = Column(Date, nullable=False)
    source = Column(String, default="fred")  # fred, mbs_live, internal, manual

    # Conforming rates
    rate_30yr_fixed = Column(Numeric(5, 3))
    rate_15yr_fixed = Column(Numeric(5, 3))
    rate_arm_5_1 = Column(Numeric(5, 3))
    rate_arm_7_1 = Column(Numeric(5, 3))

    # Non-conforming / specialty
    rate_jumbo_30yr = Column(Numeric(5, 3))
    rate_fha_30yr = Column(Numeric(5, 3))
    rate_va_30yr = Column(Numeric(5, 3))

    # Indices
    treasury_10yr = Column(Numeric(5, 3))
    sofr_rate = Column(Numeric(5, 3))
    prime_rate = Column(Numeric(5, 3))

    # Spread analysis
    spread_to_treasury = Column(Numeric(5, 3))  # 30yr fixed - 10yr treasury

    # Trend indicators
    trend_7day = Column(String)  # up, down, stable
    trend_30day = Column(String)
    trend_90day = Column(String)
    volatility_score = Column(Integer)  # 0-100

    # Change from previous day
    change_30yr = Column(Numeric(5, 3))  # bps change from yesterday
    change_15yr = Column(Numeric(5, 3))

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "RateLock",
    "RateMarketData",
]
