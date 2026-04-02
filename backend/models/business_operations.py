"""
SQLAlchemy models for the Business Operations Dashboard.

Tracks revenue, expenses, service costs, forecasting, and marketing metrics
for business decision-making.
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


# =============================================================================
# SERVICE COST TRACKING
# =============================================================================

class ServiceProvider(Base):
    """Registry of external paid services (OpenAI, Telnyx, AWS, etc.)."""
    __tablename__ = "service_providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)

    # Service Identity
    name = Column(String(100), nullable=False)
    display_name = Column(String(150))
    category = Column(String(50), nullable=False)  # ai, communications, storage, hosting, payments, crm, monitoring, other
    provider_type = Column(String(50), nullable=False)  # anthropic, openai, telnyx, stripe, aws_s3, etc.
    description = Column(Text)
    website_url = Column(String(500))

    # API Integration
    api_key_env_var = Column(String(100))  # Environment variable name for API key
    api_endpoint = Column(String(500))
    has_usage_api = Column(Boolean, default=False)
    auto_fetch_enabled = Column(Boolean, default=False)
    last_fetched_at = Column(DateTime)
    fetch_error = Column(Text)

    # Pricing Model
    pricing_model = Column(String(30), nullable=False)  # per_unit, tiered, subscription, usage_based, percentage, hybrid
    base_cost = Column(Numeric(12, 4), default=0)  # Fixed monthly cost
    unit_type = Column(String(50))  # token, message, minute, gb, request, transaction, etc.
    unit_cost = Column(Numeric(12, 8))  # Cost per unit (can be very small for tokens)
    percentage_rate = Column(Numeric(6, 4))  # For percentage-based pricing (e.g., Stripe 2.9%)
    billing_cycle = Column(String(20), default="monthly")  # monthly, annual, usage

    # Budget & Alerts
    monthly_budget = Column(Numeric(12, 2))
    alert_threshold_percent = Column(Integer, default=80)
    alert_email = Column(String(255))

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    usage_records = relationship("ServiceUsageRecord", back_populates="service_provider", cascade="all, delete-orphan")
    invoices = relationship("ServiceInvoice", back_populates="service_provider", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "provider_type", name="uq_service_org_provider"),
        CheckConstraint(
            "category IN ('ai', 'communications', 'storage', 'hosting', 'payments', 'crm', 'monitoring', 'email', 'other')",
            name="ck_service_category"
        ),
        CheckConstraint(
            "pricing_model IN ('per_unit', 'tiered', 'subscription', 'usage_based', 'percentage', 'hybrid')",
            name="ck_pricing_model"
        ),
    )


class ServiceUsageRecord(Base):
    """Daily/granular usage tracking for services."""
    __tablename__ = "service_usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    service_provider_id = Column(UUID(as_uuid=True), ForeignKey("service_providers.id", ondelete="CASCADE"), nullable=False)

    # User/Team Attribution (for per-user cost tracking)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    team_id = Column(Integer, index=True)
    request_id = Column(String(100), index=True)  # Correlation ID for AITokenUsageLog

    # Usage Details
    usage_date = Column(Date, nullable=False)
    usage_type = Column(String(50))  # api_call, tokens_input, tokens_output, messages, minutes, storage_gb, etc.
    quantity = Column(Numeric(18, 6), nullable=False)
    unit_type = Column(String(50))

    # Cost Calculation
    unit_cost = Column(Numeric(12, 8))
    total_cost = Column(Numeric(12, 4), nullable=False)

    # Metadata
    metadata_json = Column(JSONB)  # Model used, request type, additional details
    source = Column(String(20), default="manual")  # api, manual, csv_import
    external_id = Column(String(100))  # ID from external system

    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    service_provider = relationship("ServiceProvider", back_populates="usage_records")

    __table_args__ = (
        Index("idx_usage_org_date", "organization_id", "usage_date"),
        Index("idx_usage_provider_date", "service_provider_id", "usage_date"),
        Index("idx_usage_user", "user_id"),
        Index("idx_usage_team", "team_id"),
        CheckConstraint("source IN ('api', 'manual', 'csv_import')", name="ck_usage_source"),
    )


class ServiceInvoice(Base):
    """Monthly invoice tracking for services."""
    __tablename__ = "service_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    service_provider_id = Column(UUID(as_uuid=True), ForeignKey("service_providers.id", ondelete="CASCADE"), nullable=False)

    # Invoice Details
    invoice_date = Column(Date, nullable=False)
    invoice_period_start = Column(Date, nullable=False)
    invoice_period_end = Column(Date, nullable=False)

    # Amounts
    subtotal = Column(Numeric(12, 2), nullable=False)
    taxes = Column(Numeric(12, 2), default=0)
    credits = Column(Numeric(12, 2), default=0)
    total_amount = Column(Numeric(12, 2), nullable=False)

    # External Reference
    external_invoice_id = Column(String(100))
    external_invoice_url = Column(String(500))

    # Status
    status = Column(String(20), default="pending")  # pending, paid, overdue, cancelled
    paid_at = Column(DateTime)

    # Source
    source = Column(String(20), default="manual")  # api, manual, csv_import
    raw_data = Column(JSONB)

    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    service_provider = relationship("ServiceProvider", back_populates="invoices")

    __table_args__ = (
        Index("idx_invoice_org_date", "organization_id", "invoice_date"),
        CheckConstraint("status IN ('pending', 'paid', 'overdue', 'cancelled')", name="ck_invoice_status"),
    )


# =============================================================================
# REVENUE TRACKING
# =============================================================================

class SubscriptionRevenue(Base):
    """Customer subscription tracking for MRR/ARR calculations."""
    __tablename__ = "subscription_revenue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)

    # Customer Info
    customer_id = Column(Integer, index=True)  # Reference to customer organization
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255))
    customer_segment = Column(String(50))  # starter, professional, enterprise, custom

    # Subscription Details
    subscription_tier = Column(String(50), nullable=False)  # starter, professional, enterprise
    billing_cycle = Column(String(20), nullable=False)  # monthly, annual
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    renewal_date = Column(Date)

    # Revenue
    mrr = Column(Numeric(12, 2), nullable=False)  # Monthly Recurring Revenue
    arr = Column(Numeric(12, 2))  # Annual Recurring Revenue (calculated)
    discount_percent = Column(Numeric(5, 2), default=0)

    # Stripe Integration
    stripe_customer_id = Column(String(100))
    stripe_subscription_id = Column(String(100))

    # Status
    status = Column(String(20), default="active")  # trial, active, paused, churned, cancelled
    churn_date = Column(Date)
    churn_reason = Column(String(255))

    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_subscription_org_status", "organization_id", "status"),
        CheckConstraint(
            "status IN ('trial', 'active', 'paused', 'churned', 'cancelled')",
            name="ck_subscription_status"
        ),
        CheckConstraint(
            "billing_cycle IN ('monthly', 'annual', 'quarterly')",
            name="ck_billing_cycle"
        ),
    )

    @property
    def calculated_arr(self):
        """Calculate ARR from MRR."""
        if self.billing_cycle == "annual":
            return self.mrr
        return float(self.mrr or 0) * 12


class UsageRevenue(Base):
    """Usage-based revenue tracking (per-loan, API calls, overages)."""
    __tablename__ = "usage_revenue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    customer_id = Column(Integer, index=True)

    # Revenue Details
    revenue_date = Column(Date, nullable=False, index=True)
    revenue_type = Column(String(50), nullable=False)  # per_loan, api_calls, overage, addon, setup_fee, consulting

    # Amounts
    quantity = Column(Numeric(15, 4))
    unit_price = Column(Numeric(12, 4))
    amount = Column(Numeric(12, 2), nullable=False)

    description = Column(Text)

    # Reference
    reference_type = Column(String(50))  # loan, invoice, usage_period
    reference_id = Column(String(100))

    # Stripe
    stripe_invoice_id = Column(String(100))
    stripe_line_item_id = Column(String(100))

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_usage_revenue_org_date", "organization_id", "revenue_date"),
        CheckConstraint(
            "revenue_type IN ('per_loan', 'api_calls', 'overage', 'addon', 'setup_fee', 'consulting', 'other')",
            name="ck_usage_revenue_type"
        ),
    )


# =============================================================================
# MARKETING TRACKING
# =============================================================================

class MarketingCampaign(Base):
    """Marketing campaign tracking."""
    __tablename__ = "marketing_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)

    name = Column(String(255), nullable=False)
    channel = Column(String(50), nullable=False)  # google_ads, facebook, linkedin, email, referral, organic, content, events, other
    campaign_type = Column(String(50))  # awareness, acquisition, retention, reactivation

    # Budget & Spend
    budget = Column(Numeric(12, 2))
    spend_to_date = Column(Numeric(12, 2), default=0)

    # Timeline
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    status = Column(String(20), default="active")  # draft, active, paused, completed

    # Targeting
    target_audience = Column(JSONB)

    # External IDs
    external_campaign_id = Column(String(100))

    description = Column(Text)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    metrics = relationship("MarketingMetrics", back_populates="campaign", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "channel IN ('google_ads', 'facebook', 'linkedin', 'email', 'referral', 'organic', 'content', 'events', 'direct', 'other')",
            name="ck_marketing_channel"
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed')",
            name="ck_campaign_status"
        ),
    )


class MarketingMetrics(Base):
    """Daily marketing performance metrics."""
    __tablename__ = "marketing_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("marketing_campaigns.id", ondelete="SET NULL"))

    metric_date = Column(Date, nullable=False)
    channel = Column(String(50))

    # Performance Metrics
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    leads_generated = Column(Integer, default=0)
    trials_started = Column(Integer, default=0)
    conversions = Column(Integer, default=0)

    # Costs
    spend = Column(Numeric(12, 2), default=0)
    cpc = Column(Numeric(10, 4))  # Cost per click
    cpl = Column(Numeric(10, 2))  # Cost per lead
    cac = Column(Numeric(10, 2))  # Customer acquisition cost

    # Revenue Attribution
    attributed_revenue = Column(Numeric(12, 2), default=0)
    attributed_mrr = Column(Numeric(12, 2), default=0)
    roas = Column(Numeric(8, 4))  # Return on ad spend

    source = Column(String(20), default="manual")  # manual, api, csv_import
    raw_data = Column(JSONB)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign = relationship("MarketingCampaign", back_populates="metrics")

    __table_args__ = (
        Index("idx_marketing_org_date", "organization_id", "metric_date"),
        Index("idx_marketing_campaign_date", "campaign_id", "metric_date"),
    )


# =============================================================================
# FORECASTING & KPIs
# =============================================================================

class BusinessForecast(Base):
    """Financial projections and what-if scenarios."""
    __tablename__ = "business_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)

    forecast_name = Column(String(255), nullable=False)
    forecast_type = Column(String(50), nullable=False)  # revenue, expense, combined, scenario
    description = Column(Text)

    # Parameters
    base_month = Column(Date, nullable=False)
    projection_months = Column(Integer, default=12)

    # Assumptions
    parameters = Column(JSONB, nullable=False)
    # Example: {
    #   "revenue_growth_rate": 0.05,
    #   "churn_rate": 0.02,
    #   "new_customers_monthly": 5,
    #   "avg_mrr_per_customer": 199,
    #   "expense_growth_rate": 0.03,
    #   "hiring_plan": [{"month": 3, "role": "engineer", "cost": 8000}]
    # }

    # Results (calculated)
    monthly_projections = Column(JSONB)
    # Example: [
    #   {"month": "2025-01", "revenue": 50000, "expenses": 30000, "net": 20000, "mrr": 48000, "customers": 50},
    #   ...
    # ]

    summary = Column(JSONB)
    # Example: {
    #   "break_even_month": "2025-06",
    #   "cash_runway_months": 18,
    #   "year_end_mrr": 120000,
    #   "year_end_customers": 120
    # }

    # Metadata
    created_by = Column(Integer)
    is_primary = Column(Boolean, default=False)  # Primary/default forecast
    is_scenario = Column(Boolean, default=False)  # What-if scenario
    parent_forecast_id = Column(UUID(as_uuid=True), ForeignKey("business_forecasts.id"))

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "forecast_type IN ('revenue', 'expense', 'combined', 'scenario')",
            name="ck_forecast_type"
        ),
    )


class BusinessKPI(Base):
    """Daily KPI snapshots for historical tracking."""
    __tablename__ = "business_kpis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    # Revenue KPIs
    mrr = Column(Numeric(12, 2))  # Monthly Recurring Revenue
    arr = Column(Numeric(12, 2))  # Annual Recurring Revenue
    total_revenue_mtd = Column(Numeric(12, 2))  # Month-to-date revenue
    revenue_growth_rate = Column(Numeric(8, 4))  # MoM growth %

    # Customer KPIs
    total_customers = Column(Integer)
    new_customers_mtd = Column(Integer)
    churned_customers_mtd = Column(Integer)
    churn_rate = Column(Numeric(8, 4))  # Monthly churn %
    net_revenue_retention = Column(Numeric(8, 4))  # NRR %

    # Cost KPIs
    total_monthly_costs = Column(Numeric(12, 2))
    service_costs = Column(Numeric(12, 2))  # External services
    employee_costs = Column(Numeric(12, 2))
    marketing_costs = Column(Numeric(12, 2))
    other_costs = Column(Numeric(12, 2))

    # Profitability KPIs
    gross_profit = Column(Numeric(12, 2))
    gross_margin = Column(Numeric(8, 4))  # %
    net_profit = Column(Numeric(12, 2))
    net_margin = Column(Numeric(8, 4))  # %

    # Cash & Runway
    cash_balance = Column(Numeric(14, 2))
    burn_rate = Column(Numeric(12, 2))  # Monthly burn
    cash_runway_months = Column(Numeric(6, 2))

    # Unit Economics
    cac = Column(Numeric(10, 2))  # Customer Acquisition Cost
    ltv = Column(Numeric(12, 2))  # Lifetime Value
    ltv_cac_ratio = Column(Numeric(8, 4))
    arpu = Column(Numeric(10, 2))  # Average Revenue Per User

    # Service Cost Breakdown (JSONB for flexibility)
    service_cost_breakdown = Column(JSONB)
    # Example: {"ai": 500, "communications": 200, "storage": 50, "hosting": 100}

    # Full snapshot data
    data_json = Column(JSONB)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("organization_id", "snapshot_date", name="uq_kpi_org_date"),
        Index("idx_kpi_org_date", "organization_id", "snapshot_date"),
    )


# =============================================================================
# HELPER MODELS
# =============================================================================

class BudgetAlert(Base):
    """Budget threshold alerts for services and categories."""
    __tablename__ = "budget_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)

    alert_type = Column(String(50), nullable=False)  # service_budget, category_budget, total_budget
    service_provider_id = Column(UUID(as_uuid=True), ForeignKey("service_providers.id", ondelete="CASCADE"))
    category = Column(String(50))

    threshold_percent = Column(Integer, nullable=False)  # 80, 90, 100, etc.
    current_spend = Column(Numeric(12, 2), nullable=False)
    budget_amount = Column(Numeric(12, 2), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    status = Column(String(20), default="active")  # active, acknowledged, resolved
    acknowledged_by = Column(Integer)
    acknowledged_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('service_budget', 'category_budget', 'total_budget')",
            name="ck_alert_type"
        ),
        CheckConstraint(
            "status IN ('active', 'acknowledged', 'resolved')",
            name="ck_alert_status"
        ),
    )
