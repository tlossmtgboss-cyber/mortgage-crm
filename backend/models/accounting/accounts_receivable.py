"""
Accounts Receivable Models: Customers, Invoices, Payments.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from database import Base


class ARCustomer(Base):
    """Customer master for accounts receivable."""
    __tablename__ = "ar_customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    customer_number = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    company_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    billing_address = Column(JSONB, default=dict)
    shipping_address = Column(JSONB, default=dict)
    payment_terms = Column(String(20), default='net30')
    credit_limit = Column(Numeric(12, 2))
    current_balance = Column(Numeric(12, 2), default=0)
    ar_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    tax_exempt = Column(Boolean, default=False)
    tax_id = Column(String(50))
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    contact_id = Column(Integer)
    borrower_id = Column(Integer)
    tenant_account_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    invoices = relationship("ARInvoice", back_populates="customer")
    payments = relationship("ARPayment", back_populates="customer")
    ar_account = relationship("ChartOfAccounts", foreign_keys=[ar_account_id])

    __table_args__ = (
        UniqueConstraint('organization_id', 'customer_number', name='uq_ar_cust_number'),
        CheckConstraint("payment_terms IN ('immediate', 'net15', 'net30', 'net45', 'net60', 'net90')", name="ck_ar_cust_terms"),
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'customer_number': self.customer_number,
            'name': self.name,
            'company_name': self.company_name,
            'email': self.email,
            'phone': self.phone,
            'billing_address': self.billing_address,
            'payment_terms': self.payment_terms,
            'credit_limit': float(self.credit_limit) if self.credit_limit else None,
            'current_balance': float(self.current_balance or 0),
            'tax_exempt': self.tax_exempt,
            'is_active': self.is_active,
        }


class ARInvoice(Base):
    """Customer invoices."""
    __tablename__ = "ar_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    invoice_number = Column(String(30), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("ar_customers.id"), nullable=False)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), default='draft')
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(12, 2), default=0)
    discount_amount = Column(Numeric(12, 2), default=0)
    discount_percent = Column(Numeric(5, 2))
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(12, 2), default=0)
    currency = Column(String(3), default='USD')
    terms = Column(Text)
    notes = Column(Text)
    memo = Column(Text)
    footer = Column(Text)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"))
    source_type = Column(String(50))  # subscription, service, loan_fee, other
    source_id = Column(UUID(as_uuid=True))
    sent_at = Column(DateTime)
    sent_to = Column(String(255))
    viewed_at = Column(DateTime)
    last_reminder_at = Column(DateTime)
    reminder_count = Column(Integer, default=0)
    paid_at = Column(DateTime)
    voided_at = Column(DateTime)
    voided_by = Column(Integer)
    void_reason = Column(Text)
    template_id = Column(UUID(as_uuid=True))
    pdf_url = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    customer = relationship("ARCustomer", back_populates="invoices")
    lines = relationship("ARInvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payment_applications = relationship("ARPaymentApplication", back_populates="invoice")
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])

    __table_args__ = (
        UniqueConstraint('organization_id', 'invoice_number', name='uq_ar_inv_number'),
        CheckConstraint("status IN ('draft', 'sent', 'viewed', 'partial', 'paid', 'overdue', 'void', 'written_off')", name="ck_ar_inv_status"),
        Index('idx_ar_inv_customer', 'customer_id'),
        Index('idx_ar_inv_status', 'organization_id', 'status'),
        Index('idx_ar_inv_due', 'organization_id', 'due_date'),
    )

    @hybrid_property
    def amount_due(self):
        return (self.total_amount or Decimal('0')) - (self.amount_paid or Decimal('0'))

    @property
    def is_paid(self):
        return self.status == 'paid'

    @property
    def is_overdue(self):
        if self.status in ('paid', 'void', 'written_off'):
            return False
        return self.due_date < datetime.now().date() if self.due_date else False

    def calculate_totals(self):
        """Calculate invoice totals from lines."""
        self.subtotal = sum(line.amount or Decimal('0') for line in self.lines)
        self.tax_amount = sum(line.tax_amount or Decimal('0') for line in self.lines)
        if self.discount_percent:
            self.discount_amount = self.subtotal * (self.discount_percent / Decimal('100'))
        self.total_amount = self.subtotal + self.tax_amount - (self.discount_amount or Decimal('0'))

    def to_dict(self, include_lines=False):
        result = {
            'id': str(self.id),
            'invoice_number': self.invoice_number,
            'customer_id': str(self.customer_id),
            'customer_name': self.customer.name if self.customer else None,
            'invoice_date': self.invoice_date.isoformat() if self.invoice_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'status': self.status,
            'subtotal': float(self.subtotal or 0),
            'tax_amount': float(self.tax_amount or 0),
            'discount_amount': float(self.discount_amount or 0),
            'total_amount': float(self.total_amount or 0),
            'amount_paid': float(self.amount_paid or 0),
            'amount_due': float(self.amount_due),
            'currency': self.currency,
            'is_overdue': self.is_overdue,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_lines:
            result['lines'] = [line.to_dict() for line in self.lines]
        return result


class ARInvoiceLine(Base):
    """Invoice line items."""
    __tablename__ = "ar_invoice_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("ar_invoices.id", ondelete="CASCADE"), nullable=False)
    line_order = Column(Integer, default=0)
    item_code = Column(String(50))
    description = Column(Text, nullable=False)
    quantity = Column(Numeric(10, 4), default=1)
    unit_price = Column(Numeric(12, 4), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    discount_percent = Column(Numeric(5, 2))
    discount_amount = Column(Numeric(12, 2), default=0)
    revenue_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    tax_code = Column(String(20))
    tax_rate = Column(Numeric(5, 4))
    tax_amount = Column(Numeric(12, 2), default=0)
    product_id = Column(UUID(as_uuid=True))
    service_id = Column(UUID(as_uuid=True))
    loan_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    invoice = relationship("ARInvoice", back_populates="lines")
    revenue_account = relationship("ChartOfAccounts", foreign_keys=[revenue_account_id])

    def calculate_amount(self):
        """Calculate line amount."""
        base_amount = (self.quantity or Decimal('1')) * (self.unit_price or Decimal('0'))
        if self.discount_percent:
            self.discount_amount = base_amount * (self.discount_percent / Decimal('100'))
        self.amount = base_amount - (self.discount_amount or Decimal('0'))
        if self.tax_rate:
            self.tax_amount = self.amount * self.tax_rate

    def to_dict(self):
        return {
            'id': str(self.id),
            'line_order': self.line_order,
            'item_code': self.item_code,
            'description': self.description,
            'quantity': float(self.quantity or 1),
            'unit_price': float(self.unit_price or 0),
            'amount': float(self.amount or 0),
            'tax_amount': float(self.tax_amount or 0),
            'revenue_account_id': str(self.revenue_account_id) if self.revenue_account_id else None,
        }


class ARPayment(Base):
    """Customer payment receipts."""
    __tablename__ = "ar_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    payment_number = Column(String(30), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("ar_customers.id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    amount_applied = Column(Numeric(12, 2), default=0)
    amount_unapplied = Column(Numeric(12, 2), default=0)
    payment_method = Column(String(30), nullable=False)
    reference_number = Column(String(100))
    deposit_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    status = Column(String(20), default='pending')
    memo = Column(Text)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"))
    stripe_payment_id = Column(String(100))
    stripe_charge_id = Column(String(100))
    bank_transaction_id = Column(UUID(as_uuid=True))
    reconciled_at = Column(DateTime)
    voided_at = Column(DateTime)
    voided_by = Column(Integer)
    void_reason = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    customer = relationship("ARCustomer", back_populates="payments")
    applications = relationship("ARPaymentApplication", back_populates="payment", cascade="all, delete-orphan")
    deposit_account = relationship("ChartOfAccounts", foreign_keys=[deposit_account_id])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])

    __table_args__ = (
        UniqueConstraint('organization_id', 'payment_number', name='uq_ar_pay_number'),
        CheckConstraint("payment_method IN ('check', 'ach', 'wire', 'credit_card', 'cash', 'stripe', 'other')", name="ck_ar_pay_method"),
        CheckConstraint("status IN ('pending', 'cleared', 'returned', 'void')", name="ck_ar_pay_status"),
        Index('idx_ar_pay_customer', 'customer_id'),
        Index('idx_ar_pay_date', 'organization_id', 'payment_date'),
    )

    def calculate_unapplied(self):
        """Calculate unapplied amount."""
        self.amount_applied = sum(app.amount_applied or Decimal('0') for app in self.applications)
        self.amount_unapplied = (self.amount or Decimal('0')) - self.amount_applied

    def to_dict(self, include_applications=False):
        result = {
            'id': str(self.id),
            'payment_number': self.payment_number,
            'customer_id': str(self.customer_id),
            'customer_name': self.customer.name if self.customer else None,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'amount': float(self.amount or 0),
            'amount_applied': float(self.amount_applied or 0),
            'amount_unapplied': float(self.amount_unapplied or 0),
            'payment_method': self.payment_method,
            'reference_number': self.reference_number,
            'status': self.status,
            'memo': self.memo,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_applications:
            result['applications'] = [app.to_dict() for app in self.applications]
        return result


class ARPaymentApplication(Base):
    """Application of payments to invoices."""
    __tablename__ = "ar_payment_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("ar_payments.id", ondelete="CASCADE"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("ar_invoices.id"), nullable=False)
    amount_applied = Column(Numeric(12, 2), nullable=False)
    applied_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    payment = relationship("ARPayment", back_populates="applications")
    invoice = relationship("ARInvoice", back_populates="payment_applications")

    def to_dict(self):
        return {
            'id': str(self.id),
            'payment_id': str(self.payment_id),
            'invoice_id': str(self.invoice_id),
            'invoice_number': self.invoice.invoice_number if self.invoice else None,
            'amount_applied': float(self.amount_applied or 0),
            'applied_at': self.applied_at.isoformat() if self.applied_at else None,
        }
