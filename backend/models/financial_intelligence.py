"""
Phase 3: Enhanced Financial Intelligence Models

Models for comprehensive mortgage company financial analysis including:
- Secondary marketing & gain-on-sale
- Hedge positions & effectiveness
- MSR portfolio tracking
- Warehouse line management
- Product-level P&L
- Cash management & forecasting
- Competitive intelligence
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


# ============ Secondary Marketing ============

class LoanSale(Base):
    """Individual loan sale to secondary market."""
    __tablename__ = "loan_sales"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)
    loan_id = Column(Integer, ForeignKey("profitability_loans.id"), nullable=True)

    # Loan details
    loan_number = Column(String(50), index=True)
    loan_amount = Column(Float, nullable=False)
    loan_type = Column(String(50))  # Conventional, FHA, VA, USDA, Jumbo
    note_rate = Column(Float)

    # Sale details
    sale_date = Column(Date, nullable=False)
    investor = Column(String(100))
    sale_price = Column(Float, nullable=False)  # As percentage (e.g., 101.5)
    srp = Column(Float, default=0)  # Service release premium
    llpa = Column(Float, default=0)  # Loan-level price adjustments

    # Gain calculation
    base_price = Column(Float)
    gain_on_sale = Column(Float)  # Dollar amount
    gain_on_sale_bps = Column(Float)  # Basis points

    # Costs
    origination_cost = Column(Float, default=0)
    direct_costs = Column(Float, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HedgePosition(Base):
    """Hedge positions for rate risk management."""
    __tablename__ = "hedge_positions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    # Position details
    position_date = Column(Date, nullable=False)
    position_type = Column(String(50))  # TBA, Pair-off, Best Efforts
    security_type = Column(String(50))  # FNMA, FHLMC, GNMA
    coupon = Column(Float)

    # Amounts
    notional_amount = Column(Float, nullable=False)
    market_value = Column(Float)

    # Pipeline coverage
    pipeline_coverage_pct = Column(Float)  # Percentage of pipeline hedged

    # P&L
    unrealized_gain_loss = Column(Float)
    realized_gain_loss = Column(Float)

    # Effectiveness
    hedge_effectiveness = Column(Float)  # Ratio

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SecondaryMetrics(Base):
    """Daily/monthly secondary marketing metrics."""
    __tablename__ = "secondary_metrics"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    metric_date = Column(Date, nullable=False)
    period_type = Column(String(20), default="daily")  # daily, weekly, monthly

    # Gain on sale
    total_volume = Column(Float)
    total_gain = Column(Float)
    avg_gain_bps = Column(Float)

    # By product
    conv_volume = Column(Float, default=0)
    conv_gain_bps = Column(Float, default=0)
    govt_volume = Column(Float, default=0)
    govt_gain_bps = Column(Float, default=0)
    jumbo_volume = Column(Float, default=0)
    jumbo_gain_bps = Column(Float, default=0)

    # Hedging
    hedge_gain_loss = Column(Float)
    pair_off_gain_loss = Column(Float)

    # Fallout
    fallout_rate = Column(Float)
    lock_extensions = Column(Integer)
    relocks = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============ MSR Portfolio ============

class MSRPortfolio(Base):
    """MSR portfolio valuation and tracking."""
    __tablename__ = "msr_portfolio"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    valuation_date = Column(Date, nullable=False)

    # Portfolio size
    upb = Column(Float, nullable=False)  # Unpaid principal balance
    loan_count = Column(Integer)
    weighted_avg_rate = Column(Float)
    weighted_avg_age = Column(Float)  # Months

    # Valuation
    fair_value = Column(Float)
    multiple = Column(Float)  # Value as multiple of servicing fee

    # Changes
    value_change = Column(Float)  # From prior period
    value_change_pct = Column(Float)

    # Assumptions
    discount_rate = Column(Float)
    prepay_speed = Column(Float)  # CPR
    cost_to_service = Column(Float)  # Per loan per year

    # Income
    servicing_fee_income = Column(Float)
    ancillary_income = Column(Float)
    float_income = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============ Warehouse Lines ============

class WarehouseLine(Base):
    """Warehouse line of credit configuration."""
    __tablename__ = "warehouse_lines"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    lender_name = Column(String(100), nullable=False)
    line_limit = Column(Float, nullable=False)
    interest_rate = Column(Float)  # Spread over index
    index_type = Column(String(50))  # SOFR, Prime

    # Terms
    advance_rate = Column(Float, default=98)  # Percentage
    wet_funding = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)
    expiration_date = Column(Date)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WarehouseUsage(Base):
    """Daily warehouse line usage and efficiency metrics."""
    __tablename__ = "warehouse_usage"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)
    warehouse_line_id = Column(Integer, ForeignKey("warehouse_lines.id"))

    usage_date = Column(Date, nullable=False)

    # Usage
    outstanding_balance = Column(Float)
    available_capacity = Column(Float)
    utilization_pct = Column(Float)

    # Efficiency
    loans_on_line = Column(Integer)
    avg_dwell_time = Column(Float)  # Days

    # Costs
    interest_expense = Column(Float)
    fees = Column(Float)

    # Turn time analysis
    loans_funded = Column(Integer)
    loans_sold = Column(Integer)
    avg_turn_time = Column(Float)  # Days from fund to sale

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============ Product P&L ============

class ProductProfitability(Base):
    """Profitability by loan product type."""
    __tablename__ = "product_profitability"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    month = Column(Date, nullable=False)
    product_type = Column(String(50), nullable=False)  # Conv, FHA, VA, USDA, Jumbo
    channel = Column(String(50))  # Retail, Wholesale, Correspondent

    # Volume
    loan_count = Column(Integer)
    total_volume = Column(Float)
    avg_loan_size = Column(Float)

    # Revenue
    total_revenue = Column(Float)
    avg_gain_bps = Column(Float)
    srp_revenue = Column(Float)
    other_revenue = Column(Float)

    # Costs
    direct_costs = Column(Float)
    allocated_overhead = Column(Float)
    total_costs = Column(Float)

    # Profitability
    gross_profit = Column(Float)
    net_profit = Column(Float)
    profit_margin = Column(Float)
    profit_per_loan = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============ Cash Management ============

class CashPosition(Base):
    """Daily cash position tracking."""
    __tablename__ = "cash_positions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    position_date = Column(Date, nullable=False)

    # Balances
    operating_cash = Column(Float, nullable=False)
    restricted_cash = Column(Float, default=0)
    total_cash = Column(Float)

    # Liquidity
    available_warehouse_capacity = Column(Float)
    available_credit_lines = Column(Float)
    total_liquidity = Column(Float)

    # Receivables
    accounts_receivable = Column(Float)
    investor_receivables = Column(Float)

    # Payables
    accounts_payable = Column(Float)
    warehouse_payable = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CashForecast(Base):
    """Cash flow forecasting."""
    __tablename__ = "cash_forecasts"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    forecast_date = Column(Date, nullable=False)  # Date forecast was made
    period_end = Column(Date, nullable=False)  # 30, 60, 90 days out

    # Inflows
    expected_closings = Column(Float)
    expected_sales = Column(Float)
    servicing_income = Column(Float)
    other_inflows = Column(Float)
    total_inflows = Column(Float)

    # Outflows
    payroll = Column(Float)
    operating_expenses = Column(Float)
    warehouse_interest = Column(Float)
    loan_purchases = Column(Float)
    other_outflows = Column(Float)
    total_outflows = Column(Float)

    # Net
    net_cash_flow = Column(Float)
    ending_cash = Column(Float)

    # Risk scenarios
    best_case = Column(Float)
    worst_case = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BurnRate(Base):
    """Monthly burn rate tracking."""
    __tablename__ = "burn_rates"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    month = Column(Date, nullable=False)

    # Expenses
    fixed_costs = Column(Float)
    variable_costs = Column(Float)
    total_burn = Column(Float)

    # Revenue
    total_revenue = Column(Float)
    net_burn = Column(Float)  # Burn - Revenue (negative = profitable)

    # Runway
    cash_on_hand = Column(Float)
    months_runway = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============ Competitive Intelligence ============

class CompetitorRate(Base):
    """Competitor rate tracking."""
    __tablename__ = "competitor_rates"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    rate_date = Column(Date, nullable=False)
    competitor_name = Column(String(100), nullable=False)

    # Rates
    product_type = Column(String(50))
    rate_30yr = Column(Float)
    rate_15yr = Column(Float)
    points = Column(Float)
    apr = Column(Float)

    # Our rates for comparison
    our_rate_30yr = Column(Float)
    our_rate_15yr = Column(Float)
    our_points = Column(Float)

    # Spread
    rate_spread = Column(Float)  # Competitor - Ours (negative = we're higher)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LostDeal(Base):
    """Track deals lost to competitors."""
    __tablename__ = "lost_deals"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    lost_date = Column(Date, nullable=False)
    lead_id = Column(Integer, nullable=True)

    # Deal details
    loan_amount = Column(Float)
    loan_type = Column(String(50))

    # Loss reason
    lost_to_competitor = Column(String(100))
    loss_reason = Column(String(50))  # Rate, Fees, Service, Speed
    rate_difference = Column(Float)  # BPS we were higher

    # Impact
    estimated_revenue_lost = Column(Float)

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============ Capital & Compliance ============

class CapitalRequirement(Base):
    """Capital adequacy tracking."""
    __tablename__ = "capital_requirements"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    as_of_date = Column(Date, nullable=False)

    # Net worth
    tangible_net_worth = Column(Float)
    adjusted_net_worth = Column(Float)

    # Requirements
    fnma_requirement = Column(Float)
    fhlmc_requirement = Column(Float)
    gnma_requirement = Column(Float)
    state_requirements = Column(Float)

    # Cushion
    excess_capital = Column(Float)
    cushion_pct = Column(Float)

    # Liquidity
    liquidity_requirement = Column(Float)
    current_liquidity = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ComplianceRisk(Base):
    """Track compliance and regulatory risks."""
    __tablename__ = "compliance_risks"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False)

    identified_date = Column(Date, nullable=False)
    risk_type = Column(String(50))  # Audit, Regulatory, QC, Legal

    description = Column(Text)
    severity = Column(String(20))  # High, Medium, Low

    # Financial exposure
    potential_exposure = Column(Float)
    reserved_amount = Column(Float)

    # Status
    status = Column(String(20), default="Open")  # Open, Mitigated, Closed
    resolution_date = Column(Date)
    resolution_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
