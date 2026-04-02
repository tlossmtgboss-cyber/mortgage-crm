"""
SQLAlchemy models for Usage Intelligence & Cost Projection System.

Tracks per-user AI token usage, costs across all services, and provides
projections for pricing decisions. Owner-only access.
"""

import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


# =============================================================================
# AI TOKEN USAGE - Real-time tracking
# =============================================================================

class AITokenUsageLog(Base):
    """
    Real-time log of every AI API call with token counts and costs.
    Used for precise per-user billing and usage analysis.
    """
    __tablename__ = "ai_token_usage_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Request identification
    request_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Model information
    provider = Column(String(50), nullable=False)  # anthropic, openai
    model = Column(String(100), nullable=False)  # claude-opus-4-5-20251101, gpt-4o, etc.

    # Token counts
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)

    # Costs (8 decimal places for precision with small token costs)
    input_cost = Column(Numeric(14, 8), nullable=False)  # e.g., $0.00003 per token
    output_cost = Column(Numeric(14, 8), nullable=False)
    total_cost = Column(Numeric(14, 8), nullable=False)

    # Context for analysis
    feature = Column(String(100))  # chat, email_draft, document_analysis, ai_receptionist, etc.
    session_id = Column(String(100))  # For grouping related requests

    # Additional metadata
    metadata_json = Column(JSONB)  # temperature, max_tokens, any extra details

    # Performance tracking
    latency_ms = Column(Integer)  # Response time in milliseconds

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_token_log_user_date", "user_id", "timestamp"),
        Index("idx_token_log_org_date", "organization_id", "timestamp"),
        Index("idx_token_log_model", "provider", "model"),
        Index("idx_token_log_feature", "feature"),
        CheckConstraint("provider IN ('anthropic', 'openai', 'deepgram', 'eleven_labs', 'other')", name="ck_ai_provider"),
    )


# =============================================================================
# USAGE SNAPSHOTS - Daily aggregates
# =============================================================================

class UserUsageSnapshot(Base):
    """
    Daily aggregated usage costs per user.
    Rolled up from AITokenUsageLog and ServiceUsageRecord.
    """
    __tablename__ = "user_usage_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    # AI Token Costs (most significant cost usually)
    ai_tokens_cost = Column(Numeric(14, 6), default=0)  # Total AI cost for the day
    ai_tokens_input = Column(BigInteger, default=0)  # Total input tokens
    ai_tokens_output = Column(BigInteger, default=0)  # Total output tokens

    # Communication Costs
    sms_cost = Column(Numeric(14, 6), default=0)
    sms_segments = Column(Integer, default=0)
    voice_cost = Column(Numeric(14, 6), default=0)
    voice_minutes = Column(Numeric(10, 2), default=0)
    email_cost = Column(Numeric(14, 6), default=0)
    email_count = Column(Integer, default=0)

    # Storage Costs
    storage_cost = Column(Numeric(14, 6), default=0)
    storage_gb = Column(Numeric(10, 4), default=0)
    storage_requests = Column(Integer, default=0)

    # Infrastructure (allocated per user)
    infrastructure_cost = Column(Numeric(14, 6), default=0)

    # Total for the day
    total_cost = Column(Numeric(14, 6), nullable=False)

    # Detailed breakdown by AI model
    cost_by_model = Column(JSONB)  # {"claude-opus-4-5-20251101": 1.50, "gpt-4o": 0.80}

    # Detailed breakdown by feature
    cost_by_feature = Column(JSONB)  # {"chat": 1.20, "email_draft": 0.50, "receptionist": 0.60}

    # Request counts
    ai_request_count = Column(Integer, default=0)
    api_request_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "snapshot_date", name="uq_user_usage_date"),
        Index("idx_user_usage_org_date", "organization_id", "snapshot_date"),
        Index("idx_user_usage_user_date", "user_id", "snapshot_date"),
    )


class TeamUsageSnapshot(Base):
    """
    Daily aggregated usage costs per team.
    Sum of all UserUsageSnapshots for team members.
    """
    __tablename__ = "team_usage_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    team_id = Column(Integer, nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    # Aggregated totals
    total_cost = Column(Numeric(14, 6), nullable=False)
    user_count = Column(Integer, default=0)

    # Cost breakdown by category
    ai_tokens_cost = Column(Numeric(14, 6), default=0)
    communications_cost = Column(Numeric(14, 6), default=0)  # SMS + Voice + Email
    storage_cost = Column(Numeric(14, 6), default=0)
    infrastructure_cost = Column(Numeric(14, 6), default=0)

    # Full breakdown JSON
    cost_breakdown = Column(JSONB)
    # Example: {
    #   "by_category": {"ai": 10.50, "sms": 1.20, "voice": 3.40, "email": 0.50, "storage": 0.80},
    #   "by_user": {"user_1": 5.20, "user_2": 8.30, "user_3": 2.90},
    #   "by_model": {"claude-opus": 8.00, "gpt-4o": 2.50}
    # }

    # Top contributors for analysis
    top_users = Column(JSONB)  # [{"user_id": 1, "name": "John", "cost": 5.20}, ...]

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("organization_id", "team_id", "snapshot_date", name="uq_team_usage_date"),
        Index("idx_team_usage_org_date", "organization_id", "snapshot_date"),
    )


class OrgUsageSnapshot(Base):
    """
    Daily aggregated usage costs for entire organization.
    Sum of all TeamUsageSnapshots.
    """
    __tablename__ = "org_usage_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    # Aggregated totals
    total_cost = Column(Numeric(14, 6), nullable=False)
    user_count = Column(Integer, default=0)
    team_count = Column(Integer, default=0)

    # Cost breakdown by category
    ai_tokens_cost = Column(Numeric(14, 6), default=0)
    communications_cost = Column(Numeric(14, 6), default=0)
    storage_cost = Column(Numeric(14, 6), default=0)
    infrastructure_cost = Column(Numeric(14, 6), default=0)

    # AI breakdown
    ai_tokens_input = Column(BigInteger, default=0)
    ai_tokens_output = Column(BigInteger, default=0)
    ai_request_count = Column(Integer, default=0)

    # Communication breakdown
    sms_segments = Column(Integer, default=0)
    voice_minutes = Column(Numeric(12, 2), default=0)
    email_count = Column(Integer, default=0)

    # Full breakdown JSON
    cost_breakdown = Column(JSONB)

    # Top contributors
    top_teams = Column(JSONB)
    top_users = Column(JSONB)
    top_features = Column(JSONB)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("organization_id", "snapshot_date", name="uq_org_usage_date"),
        Index("idx_org_usage_date", "organization_id", "snapshot_date"),
    )


# =============================================================================
# FORECASTING
# =============================================================================

class UsageForecast(Base):
    """
    30/60/90 day cost projections based on historical usage trends.
    """
    __tablename__ = "usage_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)

    # Scope of forecast
    scope_type = Column(String(20), nullable=False)  # user, team, organization
    scope_id = Column(Integer)  # user_id or team_id (null for organization)

    # Forecast parameters
    forecast_date = Column(Date, nullable=False)  # When forecast was generated
    period_days = Column(Integer, nullable=False)  # 30, 60, or 90
    lookback_days = Column(Integer, nullable=False)  # How many days of history used
    algorithm = Column(String(50), default="weighted_moving_average")

    # Projection results
    projected_cost = Column(Numeric(14, 6), nullable=False)
    confidence_interval_low = Column(Numeric(14, 6))  # 95% CI lower bound
    confidence_interval_high = Column(Numeric(14, 6))  # 95% CI upper bound
    confidence_score = Column(Numeric(5, 2))  # 0-100, based on data availability

    # Trend analysis
    trend_direction = Column(String(20))  # increasing, decreasing, stable
    trend_percentage = Column(Numeric(8, 2))  # e.g., +15.5% or -3.2%

    # Breakdown by category
    projected_by_category = Column(JSONB)
    # Example: {
    #   "ai_tokens": {"projected": 500.00, "trend": "increasing", "pct": 12.5},
    #   "sms": {"projected": 50.00, "trend": "stable", "pct": 0.5},
    #   "voice": {"projected": 120.00, "trend": "decreasing", "pct": -8.2},
    #   "email": {"projected": 15.00, "trend": "stable", "pct": 1.0},
    #   "storage": {"projected": 25.00, "trend": "increasing", "pct": 5.0}
    # }

    # Daily projection curve
    daily_projections = Column(JSONB)  # Array of daily projected costs

    # Alerts/warnings
    alerts = Column(JSONB)  # e.g., ["Projected to exceed $1000", "Unusual spike detected"]

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_forecast_scope", "organization_id", "scope_type", "scope_id"),
        Index("idx_forecast_date", "organization_id", "forecast_date"),
        CheckConstraint("scope_type IN ('user', 'team', 'organization')", name="ck_forecast_scope_type"),
        CheckConstraint("period_days IN (30, 60, 90)", name="ck_forecast_period"),
    )


# =============================================================================
# PRICING RECOMMENDATIONS
# =============================================================================

class PricingRecommendation(Base):
    """
    Pricing recommendations based on actual costs and target margin.
    Used by owner to set appropriate subscription/usage pricing.
    """
    __tablename__ = "pricing_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)

    # Calculation period
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Actual costs observed
    total_actual_cost = Column(Numeric(14, 6), nullable=False)
    avg_cost_per_user = Column(Numeric(14, 6))
    avg_cost_per_active_user = Column(Numeric(14, 6))  # Users with activity

    # Cost breakdown
    cost_breakdown = Column(JSONB, nullable=False)
    # Example: {
    #   "ai_tokens": {"total": 500.00, "per_user": 25.00, "pct_of_total": 62.5},
    #   "sms": {"total": 80.00, "per_user": 4.00, "pct_of_total": 10.0},
    #   "voice": {"total": 120.00, "per_user": 6.00, "pct_of_total": 15.0},
    #   "email": {"total": 20.00, "per_user": 1.00, "pct_of_total": 2.5},
    #   "storage": {"total": 40.00, "per_user": 2.00, "pct_of_total": 5.0},
    #   "infrastructure": {"total": 40.00, "per_user": 2.00, "pct_of_total": 5.0}
    # }

    # User statistics
    total_users = Column(Integer)
    active_users = Column(Integer)  # Users with any activity
    power_users = Column(Integer)  # Users above average usage

    # Target margin settings
    target_margin_pct = Column(Numeric(5, 2), default=200)  # 200% = 3x cost

    # Recommended pricing (at target margin)
    recommended_base_price = Column(Numeric(12, 2))  # Monthly base subscription
    recommended_per_user_price = Column(Numeric(12, 2))  # Per seat price

    # Recommended usage fees for overages
    recommended_usage_fees = Column(JSONB)
    # Example: {
    #   "ai_tokens_per_1k": 0.05,
    #   "sms_per_message": 0.02,
    #   "voice_per_minute": 0.05,
    #   "email_per_message": 0.005,
    #   "storage_per_gb": 0.10
    # }

    # Included allowances (what's covered by base price)
    recommended_allowances = Column(JSONB)
    # Example: {
    #   "ai_tokens": 100000,
    #   "sms_messages": 500,
    #   "voice_minutes": 100,
    #   "emails": 1000,
    #   "storage_gb": 5
    # }

    # Comparison with current pricing (if set)
    current_base_price = Column(Numeric(12, 2))
    current_per_user_price = Column(Numeric(12, 2))
    margin_at_current = Column(Numeric(8, 2))  # Actual margin %

    # Revenue projections
    projected_revenue_at_recommended = Column(Numeric(14, 2))
    projected_profit_at_recommended = Column(Numeric(14, 2))

    # Notes and recommendations
    notes = Column(Text)
    recommendations = Column(JSONB)  # Array of actionable recommendations

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_pricing_org_date", "organization_id", "calculated_at"),
    )


# =============================================================================
# USAGE ALERTS
# =============================================================================

class UsageAlert(Base):
    """
    Alerts for unusual usage patterns or threshold breaches.
    """
    __tablename__ = "usage_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)

    # Alert scope
    scope_type = Column(String(20), nullable=False)  # user, team, organization, category
    scope_id = Column(Integer)
    category = Column(String(50))  # ai_tokens, sms, voice, email, storage, total

    # Alert details
    alert_type = Column(String(50), nullable=False)
    # Types: budget_threshold, unusual_spike, sustained_increase, projected_overage

    severity = Column(String(20), default="warning")  # info, warning, critical

    # Trigger details
    threshold_value = Column(Numeric(14, 6))  # Budget threshold that was crossed
    actual_value = Column(Numeric(14, 6), nullable=False)  # Actual usage/cost
    period_start = Column(Date)
    period_end = Column(Date)

    # Message
    title = Column(String(255), nullable=False)
    message = Column(Text)

    # Status
    status = Column(String(20), default="active")  # active, acknowledged, resolved
    acknowledged_by = Column(Integer, ForeignKey("users.id"))
    acknowledged_at = Column(DateTime)
    resolved_at = Column(DateTime)

    # Metadata
    metadata_json = Column(JSONB)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_usage_alert_org", "organization_id", "status"),
        CheckConstraint("alert_type IN ('budget_threshold', 'unusual_spike', 'sustained_increase', 'projected_overage')", name="ck_usage_alert_type"),
        CheckConstraint("severity IN ('info', 'warning', 'critical')", name="ck_usage_alert_severity"),
        CheckConstraint("status IN ('active', 'acknowledged', 'resolved')", name="ck_usage_alert_status"),
    )


# =============================================================================
# AI MODEL PRICING CONFIG
# =============================================================================

class AIModelPricing(Base):
    """
    Configurable pricing for AI models.
    Updated when providers change pricing.
    """
    __tablename__ = "ai_model_pricing"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Model identification
    provider = Column(String(50), nullable=False)  # anthropic, openai
    model_id = Column(String(100), nullable=False)  # claude-opus-4-5-20251101
    model_name = Column(String(150))  # Claude Opus 4.5 (display name)

    # Pricing per 1M tokens (standard industry format)
    input_price_per_1m = Column(Numeric(12, 6), nullable=False)
    output_price_per_1m = Column(Numeric(12, 6), nullable=False)

    # Calculated per-token prices
    input_price_per_token = Column(Numeric(18, 14))  # For convenience
    output_price_per_token = Column(Numeric(18, 14))

    # Context limits
    max_context_tokens = Column(Integer)
    max_output_tokens = Column(Integer)

    # Status
    is_active = Column(Boolean, default=True)
    effective_date = Column(Date, nullable=False)  # When this pricing takes effect
    deprecated_date = Column(Date)  # When model was deprecated

    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("provider", "model_id", "effective_date", name="uq_ai_model_pricing"),
        Index("idx_ai_model_active", "provider", "is_active"),
    )
