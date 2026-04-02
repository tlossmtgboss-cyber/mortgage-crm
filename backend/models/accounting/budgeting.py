"""
Budgeting Models: Budget Templates and Line Items.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from database import Base


class BudgetTemplate(Base):
    """Budget templates for financial planning."""
    __tablename__ = "budget_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    fiscal_year = Column(Integer, nullable=False)
    budget_type = Column(String(30), default='annual')  # annual, quarterly, monthly, rolling
    status = Column(String(20), default='draft')  # draft, pending_approval, approved, active, closed
    approved_by = Column(Integer)
    approved_at = Column(DateTime)
    activated_at = Column(DateTime)
    total_revenue = Column(Numeric(15, 2), default=0)
    total_expenses = Column(Numeric(15, 2), default=0)
    notes = Column(Text)
    copied_from_budget_id = Column(UUID(as_uuid=True), ForeignKey("budget_templates.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    items = relationship("BudgetItem", back_populates="budget", cascade="all, delete-orphan")
    copied_from = relationship("BudgetTemplate", remote_side=[id])

    __table_args__ = (
        CheckConstraint("budget_type IN ('annual', 'quarterly', 'monthly', 'rolling')", name="ck_budget_type"),
        CheckConstraint("status IN ('draft', 'pending_approval', 'approved', 'active', 'closed')", name="ck_budget_status"),
        Index('idx_budget_year', 'organization_id', 'fiscal_year'),
    )

    @hybrid_property
    def net_budget(self):
        return (self.total_revenue or Decimal('0')) - (self.total_expenses or Decimal('0'))

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def is_approved(self):
        return self.status in ('approved', 'active')

    def calculate_totals(self):
        """Calculate budget totals from items."""
        revenue_accounts = ['revenue']
        expense_accounts = ['expense', 'cost_of_goods']

        self.total_revenue = Decimal('0')
        self.total_expenses = Decimal('0')

        for item in self.items:
            if item.account and item.account.account_type in revenue_accounts:
                self.total_revenue += item.annual_total or Decimal('0')
            elif item.account and item.account.account_type in expense_accounts:
                self.total_expenses += item.annual_total or Decimal('0')

    def to_dict(self, include_items=False):
        result = {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'fiscal_year': self.fiscal_year,
            'budget_type': self.budget_type,
            'status': self.status,
            'total_revenue': float(self.total_revenue or 0),
            'total_expenses': float(self.total_expenses or 0),
            'net_budget': float(self.net_budget),
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_items:
            result['items'] = [item.to_dict() for item in self.items]
        return result


class BudgetItem(Base):
    """Budget line items with monthly allocations."""
    __tablename__ = "budget_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_id = Column(UUID(as_uuid=True), ForeignKey("budget_templates.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"), nullable=False)
    department_id = Column(UUID(as_uuid=True))
    # Monthly periods (for annual budget)
    period_1 = Column(Numeric(15, 2), default=0)   # January or Q1
    period_2 = Column(Numeric(15, 2), default=0)
    period_3 = Column(Numeric(15, 2), default=0)
    period_4 = Column(Numeric(15, 2), default=0)
    period_5 = Column(Numeric(15, 2), default=0)
    period_6 = Column(Numeric(15, 2), default=0)
    period_7 = Column(Numeric(15, 2), default=0)
    period_8 = Column(Numeric(15, 2), default=0)
    period_9 = Column(Numeric(15, 2), default=0)
    period_10 = Column(Numeric(15, 2), default=0)
    period_11 = Column(Numeric(15, 2), default=0)
    period_12 = Column(Numeric(15, 2), default=0)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    budget = relationship("BudgetTemplate", back_populates="items")
    account = relationship("ChartOfAccounts")

    __table_args__ = (
        UniqueConstraint('budget_id', 'account_id', 'department_id', name='uq_budget_item'),
        Index('idx_budget_item_account', 'account_id'),
    )

    @hybrid_property
    def annual_total(self):
        """Calculate total across all periods."""
        return (
            (self.period_1 or Decimal('0')) +
            (self.period_2 or Decimal('0')) +
            (self.period_3 or Decimal('0')) +
            (self.period_4 or Decimal('0')) +
            (self.period_5 or Decimal('0')) +
            (self.period_6 or Decimal('0')) +
            (self.period_7 or Decimal('0')) +
            (self.period_8 or Decimal('0')) +
            (self.period_9 or Decimal('0')) +
            (self.period_10 or Decimal('0')) +
            (self.period_11 or Decimal('0')) +
            (self.period_12 or Decimal('0'))
        )

    def get_period_amount(self, period: int) -> Decimal:
        """Get amount for a specific period (1-12)."""
        period_map = {
            1: self.period_1,
            2: self.period_2,
            3: self.period_3,
            4: self.period_4,
            5: self.period_5,
            6: self.period_6,
            7: self.period_7,
            8: self.period_8,
            9: self.period_9,
            10: self.period_10,
            11: self.period_11,
            12: self.period_12,
        }
        return period_map.get(period, Decimal('0')) or Decimal('0')

    def set_period_amount(self, period: int, amount: Decimal):
        """Set amount for a specific period (1-12)."""
        if period == 1:
            self.period_1 = amount
        elif period == 2:
            self.period_2 = amount
        elif period == 3:
            self.period_3 = amount
        elif period == 4:
            self.period_4 = amount
        elif period == 5:
            self.period_5 = amount
        elif period == 6:
            self.period_6 = amount
        elif period == 7:
            self.period_7 = amount
        elif period == 8:
            self.period_8 = amount
        elif period == 9:
            self.period_9 = amount
        elif period == 10:
            self.period_10 = amount
        elif period == 11:
            self.period_11 = amount
        elif period == 12:
            self.period_12 = amount

    def distribute_evenly(self, annual_amount: Decimal):
        """Distribute an annual amount evenly across all periods."""
        monthly = annual_amount / Decimal('12')
        for i in range(1, 13):
            self.set_period_amount(i, monthly)

    def get_ytd_budget(self, through_period: int) -> Decimal:
        """Get year-to-date budget through a specific period."""
        total = Decimal('0')
        for i in range(1, through_period + 1):
            total += self.get_period_amount(i)
        return total

    def to_dict(self):
        return {
            'id': str(self.id),
            'budget_id': str(self.budget_id),
            'account_id': str(self.account_id),
            'account_number': self.account.account_number if self.account else None,
            'account_name': self.account.name if self.account else None,
            'account_type': self.account.account_type if self.account else None,
            'department_id': str(self.department_id) if self.department_id else None,
            'periods': {
                'period_1': float(self.period_1 or 0),
                'period_2': float(self.period_2 or 0),
                'period_3': float(self.period_3 or 0),
                'period_4': float(self.period_4 or 0),
                'period_5': float(self.period_5 or 0),
                'period_6': float(self.period_6 or 0),
                'period_7': float(self.period_7 or 0),
                'period_8': float(self.period_8 or 0),
                'period_9': float(self.period_9 or 0),
                'period_10': float(self.period_10 or 0),
                'period_11': float(self.period_11 or 0),
                'period_12': float(self.period_12 or 0),
            },
            'annual_total': float(self.annual_total),
            'notes': self.notes,
        }
