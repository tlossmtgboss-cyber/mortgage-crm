"""
Pydantic schemas for the Business Operations Dashboard.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, validator
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class ServiceCategory(str, Enum):
    AI = "ai"
    COMMUNICATIONS = "communications"
    STORAGE = "storage"
    HOSTING = "hosting"
    PAYMENTS = "payments"
    CRM = "crm"
    MONITORING = "monitoring"
    EMAIL = "email"
    OTHER = "other"


class PricingModel(str, Enum):
    PER_UNIT = "per_unit"
    TIERED = "tiered"
    SUBSCRIPTION = "subscription"
    USAGE_BASED = "usage_based"
    PERCENTAGE = "percentage"
    HYBRID = "hybrid"


class UsageSource(str, Enum):
    API = "api"
    MANUAL = "manual"
    CSV_IMPORT = "csv_import"


class SubscriptionStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAUSED = "paused"
    CHURNED = "churned"
    CANCELLED = "cancelled"


class BillingCycle(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class MarketingChannel(str, Enum):
    GOOGLE_ADS = "google_ads"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    EMAIL = "email"
    REFERRAL = "referral"
    ORGANIC = "organic"
    CONTENT = "content"
    EVENTS = "events"
    DIRECT = "direct"
    OTHER = "other"


class ForecastType(str, Enum):
    REVENUE = "revenue"
    EXPENSE = "expense"
    COMBINED = "combined"
    SCENARIO = "scenario"


# =============================================================================
# SERVICE PROVIDER SCHEMAS
# =============================================================================

class ServiceProviderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=150)
    category: ServiceCategory
    provider_type: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    website_url: Optional[str] = None

    # Pricing
    pricing_model: PricingModel
    base_cost: Decimal = Field(default=Decimal("0"))
    unit_type: Optional[str] = None
    unit_cost: Optional[Decimal] = None
    percentage_rate: Optional[Decimal] = None
    billing_cycle: str = "monthly"

    # Budget
    monthly_budget: Optional[Decimal] = None
    alert_threshold_percent: int = Field(default=80, ge=0, le=100)


class ServiceProviderCreate(ServiceProviderBase):
    api_key_env_var: Optional[str] = None
    has_usage_api: bool = False
    auto_fetch_enabled: bool = False


class ServiceProviderUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    base_cost: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = None
    monthly_budget: Optional[Decimal] = None
    alert_threshold_percent: Optional[int] = None
    auto_fetch_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class ServiceProviderResponse(ServiceProviderBase):
    id: UUID
    organization_id: int
    api_key_env_var: Optional[str] = None
    has_usage_api: bool
    auto_fetch_enabled: bool
    last_fetched_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ServiceProviderSummary(BaseModel):
    id: UUID
    name: str
    category: str
    provider_type: str
    current_month_cost: Decimal = Decimal("0")
    last_month_cost: Decimal = Decimal("0")
    monthly_budget: Optional[Decimal] = None
    budget_used_percent: Optional[float] = None
    has_usage_api: bool


# =============================================================================
# SERVICE USAGE SCHEMAS
# =============================================================================

class ServiceUsageBase(BaseModel):
    usage_date: date
    usage_type: Optional[str] = None
    quantity: Decimal = Field(..., ge=0)
    unit_type: Optional[str] = None
    unit_cost: Optional[Decimal] = None
    total_cost: Decimal = Field(..., ge=0)
    notes: Optional[str] = None


class ServiceUsageCreate(ServiceUsageBase):
    service_provider_id: UUID
    metadata_json: Optional[Dict[str, Any]] = None


class ServiceUsageResponse(ServiceUsageBase):
    id: UUID
    organization_id: int
    service_provider_id: UUID
    source: UsageSource
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ServiceUsageImport(BaseModel):
    """Schema for CSV import of usage records."""
    service_provider_id: UUID
    records: List[ServiceUsageBase]


# =============================================================================
# SERVICE INVOICE SCHEMAS
# =============================================================================

class ServiceInvoiceBase(BaseModel):
    invoice_date: date
    invoice_period_start: date
    invoice_period_end: date
    subtotal: Decimal
    taxes: Decimal = Decimal("0")
    credits: Decimal = Decimal("0")
    total_amount: Decimal
    external_invoice_id: Optional[str] = None
    external_invoice_url: Optional[str] = None
    notes: Optional[str] = None


class ServiceInvoiceCreate(ServiceInvoiceBase):
    service_provider_id: UUID


class ServiceInvoiceResponse(ServiceInvoiceBase):
    id: UUID
    organization_id: int
    service_provider_id: UUID
    status: str
    paid_at: Optional[datetime] = None
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# SUBSCRIPTION REVENUE SCHEMAS
# =============================================================================

class SubscriptionBase(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_email: Optional[str] = None
    customer_segment: Optional[str] = None
    subscription_tier: str = Field(..., min_length=1, max_length=50)
    billing_cycle: BillingCycle
    start_date: date
    end_date: Optional[date] = None
    renewal_date: Optional[date] = None
    mrr: Decimal = Field(..., gt=0)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class SubscriptionCreate(SubscriptionBase):
    customer_id: Optional[int] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


class SubscriptionUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_segment: Optional[str] = None
    subscription_tier: Optional[str] = None
    mrr: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None
    renewal_date: Optional[date] = None
    status: Optional[SubscriptionStatus] = None
    churn_date: Optional[date] = None
    churn_reason: Optional[str] = None


class SubscriptionResponse(SubscriptionBase):
    id: UUID
    organization_id: int
    customer_id: Optional[int] = None
    arr: Optional[Decimal] = None
    status: SubscriptionStatus
    churn_date: Optional[date] = None
    churn_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# USAGE REVENUE SCHEMAS
# =============================================================================

class UsageRevenueBase(BaseModel):
    revenue_date: date
    revenue_type: str  # per_loan, api_calls, overage, addon, setup_fee, consulting, other
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Decimal = Field(..., gt=0)
    description: Optional[str] = None


class UsageRevenueCreate(UsageRevenueBase):
    customer_id: Optional[int] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None


class UsageRevenueResponse(UsageRevenueBase):
    id: UUID
    organization_id: int
    customer_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# MARKETING SCHEMAS
# =============================================================================

class CampaignBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    channel: MarketingChannel
    campaign_type: Optional[str] = None
    budget: Optional[Decimal] = None
    start_date: date
    end_date: Optional[date] = None
    description: Optional[str] = None
    target_audience: Optional[Dict[str, Any]] = None


class CampaignCreate(CampaignBase):
    external_campaign_id: Optional[str] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    budget: Optional[Decimal] = None
    spend_to_date: Optional[Decimal] = None
    end_date: Optional[date] = None
    status: Optional[CampaignStatus] = None
    description: Optional[str] = None


class CampaignResponse(CampaignBase):
    id: UUID
    organization_id: int
    spend_to_date: Decimal
    status: CampaignStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MarketingMetricsBase(BaseModel):
    metric_date: date
    channel: Optional[str] = None
    impressions: int = 0
    clicks: int = 0
    leads_generated: int = 0
    trials_started: int = 0
    conversions: int = 0
    spend: Decimal = Decimal("0")
    attributed_revenue: Decimal = Decimal("0")


class MarketingMetricsCreate(MarketingMetricsBase):
    campaign_id: Optional[UUID] = None


class MarketingMetricsResponse(MarketingMetricsBase):
    id: UUID
    organization_id: int
    campaign_id: Optional[UUID] = None
    cpc: Optional[Decimal] = None
    cpl: Optional[Decimal] = None
    cac: Optional[Decimal] = None
    roas: Optional[Decimal] = None
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# FORECAST SCHEMAS
# =============================================================================

class ForecastParameters(BaseModel):
    """Parameters for forecast calculation."""
    revenue_growth_rate: float = Field(default=0.05, description="Monthly growth rate")
    churn_rate: float = Field(default=0.02, description="Monthly churn rate")
    new_customers_monthly: int = Field(default=5, description="Expected new customers/month")
    avg_mrr_per_customer: Decimal = Field(default=Decimal("199"))
    expense_growth_rate: float = Field(default=0.03)
    starting_mrr: Optional[Decimal] = None
    starting_customers: Optional[int] = None
    starting_cash: Optional[Decimal] = None
    hiring_plan: Optional[List[Dict[str, Any]]] = None


class ForecastCreate(BaseModel):
    forecast_name: str = Field(..., min_length=1, max_length=255)
    forecast_type: ForecastType
    description: Optional[str] = None
    base_month: date
    projection_months: int = Field(default=12, ge=1, le=60)
    parameters: ForecastParameters
    is_primary: bool = False


class ForecastResponse(BaseModel):
    id: UUID
    organization_id: int
    forecast_name: str
    forecast_type: ForecastType
    description: Optional[str] = None
    base_month: date
    projection_months: int
    parameters: Dict[str, Any]
    monthly_projections: Optional[List[Dict[str, Any]]] = None
    summary: Optional[Dict[str, Any]] = None
    is_primary: bool
    is_scenario: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScenarioRequest(BaseModel):
    """Request to calculate a what-if scenario."""
    base_forecast_id: Optional[UUID] = None
    scenario_name: str
    changes: Dict[str, Any]  # Parameter overrides


# =============================================================================
# KPI SCHEMAS
# =============================================================================

class BusinessKPIResponse(BaseModel):
    id: UUID
    organization_id: int
    snapshot_date: date

    # Revenue
    mrr: Optional[Decimal] = None
    arr: Optional[Decimal] = None
    total_revenue_mtd: Optional[Decimal] = None
    revenue_growth_rate: Optional[Decimal] = None

    # Customers
    total_customers: Optional[int] = None
    new_customers_mtd: Optional[int] = None
    churned_customers_mtd: Optional[int] = None
    churn_rate: Optional[Decimal] = None

    # Costs
    total_monthly_costs: Optional[Decimal] = None
    service_costs: Optional[Decimal] = None
    employee_costs: Optional[Decimal] = None
    marketing_costs: Optional[Decimal] = None

    # Profitability
    gross_profit: Optional[Decimal] = None
    gross_margin: Optional[Decimal] = None
    net_profit: Optional[Decimal] = None
    net_margin: Optional[Decimal] = None

    # Cash
    cash_balance: Optional[Decimal] = None
    burn_rate: Optional[Decimal] = None
    cash_runway_months: Optional[Decimal] = None

    # Unit Economics
    cac: Optional[Decimal] = None
    ltv: Optional[Decimal] = None
    ltv_cac_ratio: Optional[Decimal] = None

    service_cost_breakdown: Optional[Dict[str, Decimal]] = None
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# DASHBOARD SCHEMAS
# =============================================================================

class RevenueSummary(BaseModel):
    mrr: Decimal
    arr: Decimal
    subscription_revenue_mtd: Decimal
    usage_revenue_mtd: Decimal
    total_revenue_mtd: Decimal
    revenue_growth_rate: Optional[float] = None
    subscription_count: int
    active_customers: int


class CostSummary(BaseModel):
    total_costs_mtd: Decimal
    service_costs_mtd: Decimal
    by_category: Dict[str, Decimal]
    top_services: List[ServiceProviderSummary]
    budget_alerts: int


class ProfitLoss(BaseModel):
    period_start: date
    period_end: date
    revenue: Dict[str, Decimal]  # subscription, usage, other
    total_revenue: Decimal
    expenses: Dict[str, Decimal]  # by category
    total_expenses: Decimal
    gross_profit: Decimal
    gross_margin: float
    net_profit: Decimal
    net_margin: float


class BusinessOpsDashboardResponse(BaseModel):
    """Full dashboard response."""
    # Current KPIs
    kpis: BusinessKPIResponse

    # Revenue breakdown
    revenue: RevenueSummary

    # Cost breakdown
    costs: CostSummary

    # P&L
    pnl: ProfitLoss

    # Trends (monthly for last 12 months)
    trends: Dict[str, List[Dict[str, Any]]]

    # Active alerts
    alerts: List[Dict[str, Any]]


class RunwayAnalysis(BaseModel):
    cash_balance: Decimal
    monthly_burn_rate: Decimal
    runway_months: float
    break_even_date: Optional[date] = None
    monthly_projections: List[Dict[str, Any]]


class BreakEvenAnalysis(BaseModel):
    current_mrr: Decimal
    current_costs: Decimal
    break_even_mrr: Decimal
    mrr_gap: Decimal
    customers_needed: int
    at_current_growth: Optional[int] = None  # Months to break-even


# =============================================================================
# MARKETING ANALYTICS SCHEMAS
# =============================================================================

class CACAnalysis(BaseModel):
    overall_cac: Decimal
    by_channel: Dict[str, Decimal]
    trend: List[Dict[str, Any]]  # Monthly CAC trend


class LTVAnalysis(BaseModel):
    overall_ltv: Decimal
    by_segment: Dict[str, Decimal]
    avg_customer_lifespan_months: float
    arpu: Decimal


class MarketingROI(BaseModel):
    overall_roas: float
    by_channel: Dict[str, Dict[str, Any]]
    best_performing: str
    recommendations: List[str]
