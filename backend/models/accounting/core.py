"""
Core Accounting Models: Chart of Accounts, Journal Entries, Periods, Settings.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from database import Base


class ChartOfAccounts(Base):
    """Chart of Accounts - the foundation of double-entry accounting."""
    __tablename__ = "chart_of_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    account_number = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    account_type = Column(String(50), nullable=False)  # asset, liability, equity, revenue, expense
    account_subtype = Column(String(50))
    parent_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    normal_balance = Column(String(10), nullable=False)  # debit, credit
    is_bank_account = Column(Boolean, default=False)
    bank_account_id = Column(UUID(as_uuid=True))
    currency = Column(String(3), default='USD')
    is_active = Column(Boolean, default=True)
    is_system_account = Column(Boolean, default=False)
    tax_code = Column(String(20))
    display_order = Column(Integer)
    opening_balance = Column(Numeric(15, 2), default=0)
    opening_balance_date = Column(Date)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    parent = relationship("ChartOfAccounts", remote_side=[id], backref="children")
    journal_lines = relationship("JournalEntryLine", back_populates="account")

    __table_args__ = (
        UniqueConstraint('organization_id', 'account_number', name='uq_coa_org_number'),
        CheckConstraint("account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense')", name="ck_coa_type"),
        CheckConstraint("normal_balance IN ('debit', 'credit')", name="ck_coa_balance"),
        Index('idx_coa_org_type', 'organization_id', 'account_type'),
    )

    @hybrid_property
    def full_name(self):
        """Return account number and name combined."""
        return f"{self.account_number} - {self.name}"

    def to_dict(self):
        return {
            'id': str(self.id),
            'account_number': self.account_number,
            'name': self.name,
            'description': self.description,
            'account_type': self.account_type,
            'account_subtype': self.account_subtype,
            'parent_account_id': str(self.parent_account_id) if self.parent_account_id else None,
            'normal_balance': self.normal_balance,
            'is_bank_account': self.is_bank_account,
            'is_active': self.is_active,
            'is_system_account': self.is_system_account,
            'currency': self.currency,
            'display_order': self.display_order,
        }


class AccountingPeriod(Base):
    """Accounting periods for period-based financial reporting."""
    __tablename__ = "accounting_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    period_name = Column(String(50), nullable=False)
    period_type = Column(String(20), nullable=False)  # month, quarter, year
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), default='open')  # open, closing, closed, locked
    closed_at = Column(DateTime)
    closed_by = Column(Integer)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_period = Column(Integer, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    journal_entries = relationship("JournalEntry", back_populates="period")

    __table_args__ = (
        UniqueConstraint('organization_id', 'start_date', 'end_date', name='uq_period_dates'),
        CheckConstraint("period_type IN ('month', 'quarter', 'year')", name="ck_period_type"),
        CheckConstraint("status IN ('open', 'closing', 'closed', 'locked')", name="ck_period_status"),
    )

    @property
    def is_open(self):
        return self.status == 'open'

    def to_dict(self):
        return {
            'id': str(self.id),
            'period_name': self.period_name,
            'period_type': self.period_type,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'status': self.status,
            'fiscal_year': self.fiscal_year,
            'fiscal_period': self.fiscal_period,
        }


class JournalEntry(Base):
    """Journal entries - the core of double-entry bookkeeping."""
    __tablename__ = "journal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    entry_number = Column(String(20), nullable=False)
    entry_date = Column(Date, nullable=False)
    period_id = Column(UUID(as_uuid=True), ForeignKey("accounting_periods.id"))
    description = Column(Text, nullable=False)
    entry_type = Column(String(30), nullable=False, default='standard')
    source_type = Column(String(50))  # manual, invoice, bill, payment, bank_import
    source_id = Column(UUID(as_uuid=True))
    status = Column(String(20), default='draft')  # draft, posted, void
    posted_at = Column(DateTime)
    posted_by = Column(Integer)
    voided_at = Column(DateTime)
    voided_by = Column(Integer)
    void_reason = Column(Text)
    reversed_by_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"))
    reverses_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"))
    memo = Column(Text)
    reference_number = Column(String(100))
    total_debits = Column(Numeric(15, 2), default=0)
    total_credits = Column(Numeric(15, 2), default=0)
    attachments = Column(JSONB, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    period = relationship("AccountingPeriod", back_populates="journal_entries")
    lines = relationship("JournalEntryLine", back_populates="journal_entry", cascade="all, delete-orphan")
    reversed_by = relationship("JournalEntry", foreign_keys=[reversed_by_entry_id], remote_side=[id])
    reverses = relationship("JournalEntry", foreign_keys=[reverses_entry_id], remote_side=[id])

    __table_args__ = (
        UniqueConstraint('organization_id', 'entry_number', name='uq_je_number'),
        CheckConstraint("entry_type IN ('standard', 'adjusting', 'closing', 'reversing', 'opening')", name="ck_je_type"),
        CheckConstraint("status IN ('draft', 'posted', 'void')", name="ck_je_status"),
        Index('idx_je_org_date', 'organization_id', 'entry_date'),
        Index('idx_je_source', 'source_type', 'source_id'),
    )

    @hybrid_property
    def is_balanced(self):
        return self.total_debits == self.total_credits

    @property
    def is_posted(self):
        return self.status == 'posted'

    def calculate_totals(self):
        """Calculate total debits and credits from lines."""
        self.total_debits = sum(line.debit_amount or Decimal('0') for line in self.lines)
        self.total_credits = sum(line.credit_amount or Decimal('0') for line in self.lines)

    def to_dict(self, include_lines=False):
        result = {
            'id': str(self.id),
            'entry_number': self.entry_number,
            'entry_date': self.entry_date.isoformat() if self.entry_date else None,
            'description': self.description,
            'entry_type': self.entry_type,
            'source_type': self.source_type,
            'status': self.status,
            'total_debits': float(self.total_debits or 0),
            'total_credits': float(self.total_credits or 0),
            'is_balanced': self.total_debits == self.total_credits,
            'reference_number': self.reference_number,
            'memo': self.memo,
            'posted_at': self.posted_at.isoformat() if self.posted_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_lines:
            result['lines'] = [line.to_dict() for line in self.lines]
        return result


class JournalEntryLine(Base):
    """Individual debit/credit lines within a journal entry."""
    __tablename__ = "journal_entry_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"), nullable=False)
    description = Column(Text)
    debit_amount = Column(Numeric(15, 2), default=0)
    credit_amount = Column(Numeric(15, 2), default=0)
    currency = Column(String(3), default='USD')
    exchange_rate = Column(Numeric(10, 6), default=1.0)
    department_id = Column(UUID(as_uuid=True))
    project_id = Column(UUID(as_uuid=True))
    loan_id = Column(UUID(as_uuid=True))
    customer_id = Column(UUID(as_uuid=True))
    vendor_id = Column(UUID(as_uuid=True))
    line_order = Column(Integer, default=0)
    reconciled = Column(Boolean, default=False)
    reconciled_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("ChartOfAccounts", back_populates="journal_lines")

    __table_args__ = (
        CheckConstraint("debit_amount >= 0", name="ck_jel_debit_positive"),
        CheckConstraint("credit_amount >= 0", name="ck_jel_credit_positive"),
        Index('idx_jel_account', 'account_id'),
    )

    @hybrid_property
    def net_amount(self):
        """Return net amount (debit positive, credit negative)."""
        return (self.debit_amount or Decimal('0')) - (self.credit_amount or Decimal('0'))

    def to_dict(self):
        return {
            'id': str(self.id),
            'account_id': str(self.account_id),
            'account_number': self.account.account_number if self.account else None,
            'account_name': self.account.name if self.account else None,
            'description': self.description,
            'debit_amount': float(self.debit_amount or 0),
            'credit_amount': float(self.credit_amount or 0),
            'line_order': self.line_order,
        }


class JournalEntryTemplate(Base):
    """Templates for recurring journal entries."""
    __tablename__ = "journal_entry_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    entry_type = Column(String(30), default='standard')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    lines = relationship("JournalEntryTemplateLine", back_populates="template", cascade="all, delete-orphan")


class JournalEntryTemplateLine(Base):
    """Template lines for journal entry templates."""
    __tablename__ = "journal_entry_template_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("journal_entry_templates.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"), nullable=False)
    description = Column(Text)
    debit_amount = Column(Numeric(15, 2), default=0)
    credit_amount = Column(Numeric(15, 2), default=0)
    is_percentage = Column(Boolean, default=False)
    percentage = Column(Numeric(5, 2))
    line_order = Column(Integer, default=0)

    # Relationships
    template = relationship("JournalEntryTemplate", back_populates="lines")
    account = relationship("ChartOfAccounts")


class AccountingSettings(Base):
    """Organization-level accounting settings."""
    __tablename__ = "accounting_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, unique=True, nullable=False)
    fiscal_year_start_month = Column(Integer, default=1)
    default_ar_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    default_ap_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    default_revenue_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    default_expense_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    retained_earnings_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    default_bank_account_id = Column(UUID(as_uuid=True))
    invoice_prefix = Column(String(10), default='INV-')
    invoice_next_number = Column(Integer, default=1001)
    bill_prefix = Column(String(10), default='BILL-')
    bill_next_number = Column(Integer, default=1001)
    payment_prefix = Column(String(10), default='PMT-')
    payment_next_number = Column(Integer, default=1001)
    journal_prefix = Column(String(10), default='JE-')
    journal_next_number = Column(Integer, default=1001)
    default_payment_terms = Column(String(20), default='net30')
    require_bill_approval = Column(Boolean, default=True)
    bill_approval_threshold = Column(Numeric(12, 2))
    auto_create_journal_entries = Column(Boolean, default=True)
    lock_date = Column(Date)
    multi_currency_enabled = Column(Boolean, default=False)
    base_currency = Column(String(3), default='USD')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    default_ar_account = relationship("ChartOfAccounts", foreign_keys=[default_ar_account_id])
    default_ap_account = relationship("ChartOfAccounts", foreign_keys=[default_ap_account_id])
    default_revenue_account = relationship("ChartOfAccounts", foreign_keys=[default_revenue_account_id])
    default_expense_account = relationship("ChartOfAccounts", foreign_keys=[default_expense_account_id])
    retained_earnings_account = relationship("ChartOfAccounts", foreign_keys=[retained_earnings_account_id])


class TaxRate(Base):
    """Tax rates for invoices and bills."""
    __tablename__ = "tax_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    tax_code = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    rate = Column(Numeric(5, 4), nullable=False)
    is_compound = Column(Boolean, default=False)
    is_recoverable = Column(Boolean, default=True)
    tax_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('organization_id', 'tax_code', name='uq_tax_code'),
    )


class RecurringTransaction(Base):
    """Recurring invoices, bills, or journal entries."""
    __tablename__ = "recurring_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    transaction_type = Column(String(30), nullable=False)  # invoice, bill, journal_entry
    template_data = Column(JSONB, nullable=False)
    frequency = Column(String(20), nullable=False)  # daily, weekly, biweekly, monthly, quarterly, annually
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    next_date = Column(Date)
    last_generated_date = Column(Date)
    days_before_due = Column(Integer, default=0)
    auto_post = Column(Boolean, default=False)
    auto_send = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    occurrence_count = Column(Integer, default=0)
    max_occurrences = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    __table_args__ = (
        CheckConstraint("transaction_type IN ('invoice', 'bill', 'journal_entry')", name="ck_recurring_type"),
        CheckConstraint("frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'annually')", name="ck_recurring_freq"),
    )


class AccountingAuditLog(Base):
    """Audit trail for all accounting operations."""
    __tablename__ = "accounting_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    entity_number = Column(String(50))
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    change_summary = Column(Text)
    ip_address = Column(INET)
    user_agent = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_audit_entity', 'entity_type', 'entity_id'),
        Index('idx_audit_date', 'created_at'),
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'user_id': self.user_id,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': str(self.entity_id),
            'entity_number': self.entity_number,
            'change_summary': self.change_summary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
