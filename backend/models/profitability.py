"""
SQLAlchemy models for the Profitability Intelligence System.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class ExpenseCategory(Base):
    """Categories for organizing expenses."""
    __tablename__ = "expense_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    parent_category_id = Column(UUID(as_uuid=True), ForeignKey("expense_categories.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    expenses = relationship("Expense", back_populates="category")
    subcategories = relationship("ExpenseCategory", backref="parent", remote_side=[id])


class Expense(Base):
    """Business expenses (fixed, variable, one-time)."""
    __tablename__ = "expenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("expense_categories.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    amount = Column(Numeric(12, 2), nullable=False)
    expense_type = Column(String(20), nullable=False)  # fixed, variable, one_time
    recurrence = Column(String(20), default="monthly")  # daily, weekly, monthly, quarterly, annually, one_time
    effective_date = Column(Date, nullable=False)
    end_date = Column(Date)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    category = relationship("ExpenseCategory", back_populates="expenses")

    __table_args__ = (
        CheckConstraint("expense_type IN ('fixed', 'variable', 'one_time')", name="ck_expense_type"),
        CheckConstraint("recurrence IN ('daily', 'weekly', 'monthly', 'quarterly', 'annually', 'one_time')", name="ck_recurrence"),
    )


class ProfitabilityRole(Base):
    """Role definitions for profitability analysis."""
    __tablename__ = "profitability_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    department = Column(String(100))
    is_revenue_generating = Column(Boolean, default=False)
    base_salary_range_min = Column(Numeric(10, 2))
    base_salary_range_max = Column(Numeric(10, 2))
    typical_benefits_percentage = Column(Numeric(5, 2), default=25.00)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    employee_costs = relationship("EmployeeCost", back_populates="role")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_role_org_name"),
    )


class EmployeeCost(Base):
    """Fully-loaded employee costs."""
    __tablename__ = "employee_costs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_id = Column(UUID(as_uuid=True), ForeignKey("profitability_roles.id"))
    employee_name = Column(String(255), nullable=False)
    base_salary = Column(Numeric(10, 2), nullable=False)
    benefits_cost = Column(Numeric(10, 2), default=0)
    taxes_cost = Column(Numeric(10, 2), default=0)
    equipment_cost = Column(Numeric(10, 2), default=0)
    training_cost = Column(Numeric(10, 2), default=0)
    other_costs = Column(Numeric(10, 2), default=0)
    hire_date = Column(Date)
    termination_date = Column(Date)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    role = relationship("ProfitabilityRole", back_populates="employee_costs")
    loan_attributions = relationship("LoanAttribution", back_populates="employee_cost")

    @property
    def fully_loaded_cost(self):
        """Calculate total annual cost."""
        return float(
            self.base_salary + self.benefits_cost + self.taxes_cost +
            self.equipment_cost + self.training_cost + self.other_costs
        )

    @property
    def monthly_cost(self):
        """Calculate monthly cost."""
        return self.fully_loaded_cost / 12


class ProfitabilityLoan(Base):
    """Closed loans for profitability tracking."""
    __tablename__ = "profitability_loans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    loan_number = Column(String(100), nullable=False)
    borrower_name = Column(String(255))
    loan_amount = Column(Numeric(12, 2), nullable=False)
    loan_type = Column(String(50))
    close_date = Column(Date, nullable=False, index=True)
    total_revenue = Column(Numeric(12, 2), nullable=False)
    processing_days = Column(Integer)
    lead_source = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    attributions = relationship("LoanAttribution", back_populates="loan", cascade="all, delete-orphan")
    revenue_records = relationship("RevenueRecord", back_populates="loan")

    __table_args__ = (
        UniqueConstraint("organization_id", "loan_number", name="uq_loan_org_number"),
    )


class LoanAttribution(Base):
    """Employee contribution/attribution to loans."""
    __tablename__ = "loan_attributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("profitability_loans.id", ondelete="CASCADE"))
    employee_cost_id = Column(UUID(as_uuid=True), ForeignKey("employee_costs.id"))
    attribution_percentage = Column(Numeric(5, 2), nullable=False)
    role_at_time = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    loan = relationship("ProfitabilityLoan", back_populates="attributions")
    employee_cost = relationship("EmployeeCost", back_populates="loan_attributions")

    __table_args__ = (
        CheckConstraint("attribution_percentage > 0 AND attribution_percentage <= 100", name="ck_attribution_pct"),
    )


class RevenueRecord(Base):
    """Revenue records from loans and other sources."""
    __tablename__ = "revenue_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("profitability_loans.id", ondelete="SET NULL"))
    revenue_type = Column(String(50), nullable=False)  # origination_fee, processing_fee, admin_fee, commission, rebate, other
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(Text)
    record_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    loan = relationship("ProfitabilityLoan", back_populates="revenue_records")

    __table_args__ = (
        CheckConstraint(
            "revenue_type IN ('origination_fee', 'processing_fee', 'admin_fee', 'commission', 'rebate', 'other')",
            name="ck_revenue_type"
        ),
    )


class ProfitabilitySnapshot(Base):
    """Monthly snapshots for historical tracking."""
    __tablename__ = "profitability_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    snapshot_month = Column(Date, nullable=False)
    total_revenue = Column(Numeric(12, 2), nullable=False)
    total_expenses = Column(Numeric(12, 2), nullable=False)
    net_profit = Column(Numeric(12, 2), nullable=False)
    loans_closed = Column(Integer, nullable=False)
    cost_per_loan = Column(Numeric(10, 2))
    revenue_per_loan = Column(Numeric(10, 2))
    profit_per_loan = Column(Numeric(10, 2))
    employee_count = Column(Integer)
    break_even_loans = Column(Integer)
    data_json = Column(JSONB)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("organization_id", "snapshot_month", name="uq_snapshot_org_month"),
    )


class ProfitabilityScenario(Base):
    """What-if scenario analysis."""
    __tablename__ = "profitability_scenarios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    base_month = Column(Date, nullable=False)
    parameters = Column(JSONB, nullable=False)
    results = Column(JSONB)
    created_by = Column(Integer, ForeignKey("users.id"))
    is_saved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ProfitabilityInsight(Base):
    """AI-generated insights and recommendations."""
    __tablename__ = "profitability_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    insight_type = Column(String(50), nullable=False)  # gap, gain, trend, recommendation, alert
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(20), default="info")  # info, warning, critical, opportunity
    data_json = Column(JSONB)
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"))
    acknowledged_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint("insight_type IN ('gap', 'gain', 'trend', 'recommendation', 'alert')", name="ck_insight_type"),
        CheckConstraint("severity IN ('info', 'warning', 'critical', 'opportunity')", name="ck_severity"),
    )


class ProfitabilityAudit(Base):
    """Audit trail for profitability data changes."""
    __tablename__ = "profitability_audit"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True))
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
