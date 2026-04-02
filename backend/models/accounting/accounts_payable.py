"""
Accounts Payable Models: Vendors, Bills, Payments.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from database import Base


class APVendor(Base):
    """Vendor master for accounts payable."""
    __tablename__ = "ap_vendors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    vendor_number = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    company_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(JSONB, default=dict)
    payment_terms = Column(String(20), default='net30')
    default_expense_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    ap_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    tax_id = Column(String(50))
    requires_1099 = Column(Boolean, default=False)
    form_1099_type = Column(String(20))
    current_balance = Column(Numeric(12, 2), default=0)
    credit_limit = Column(Numeric(12, 2))
    payment_method_default = Column(String(30))
    bank_account_info = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    bills = relationship("APBill", back_populates="vendor")
    payments = relationship("APPayment", back_populates="vendor")
    default_expense_account = relationship("ChartOfAccounts", foreign_keys=[default_expense_account_id])
    ap_account = relationship("ChartOfAccounts", foreign_keys=[ap_account_id])

    __table_args__ = (
        UniqueConstraint('organization_id', 'vendor_number', name='uq_ap_vend_number'),
        CheckConstraint("payment_terms IN ('immediate', 'net15', 'net30', 'net45', 'net60', 'net90')", name="ck_ap_vend_terms"),
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'vendor_number': self.vendor_number,
            'name': self.name,
            'company_name': self.company_name,
            'email': self.email,
            'phone': self.phone,
            'address': self.address,
            'payment_terms': self.payment_terms,
            'current_balance': float(self.current_balance or 0),
            'requires_1099': self.requires_1099,
            'tax_id': self.tax_id,
            'is_active': self.is_active,
        }


class APBill(Base):
    """Vendor bills."""
    __tablename__ = "ap_bills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    bill_number = Column(String(30), nullable=False)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("ap_vendors.id"), nullable=False)
    vendor_invoice_number = Column(String(100))
    bill_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), default='draft')
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(12, 2), default=0)
    shipping_amount = Column(Numeric(12, 2), default=0)
    discount_amount = Column(Numeric(12, 2), default=0)
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(12, 2), default=0)
    currency = Column(String(3), default='USD')
    terms = Column(Text)
    notes = Column(Text)
    memo = Column(Text)
    approval_status = Column(String(20), default='pending')
    approved_by = Column(Integer)
    approved_at = Column(DateTime)
    rejection_reason = Column(Text)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"))
    recurring_bill_id = Column(UUID(as_uuid=True))
    document_url = Column(Text)
    voided_at = Column(DateTime)
    voided_by = Column(Integer)
    void_reason = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    vendor = relationship("APVendor", back_populates="bills")
    lines = relationship("APBillLine", back_populates="bill", cascade="all, delete-orphan")
    payment_applications = relationship("APPaymentApplication", back_populates="bill")
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])

    __table_args__ = (
        UniqueConstraint('organization_id', 'bill_number', name='uq_ap_bill_number'),
        CheckConstraint("status IN ('draft', 'pending_approval', 'approved', 'partial', 'paid', 'void')", name="ck_ap_bill_status"),
        CheckConstraint("approval_status IN ('pending', 'approved', 'rejected')", name="ck_ap_bill_approval"),
        Index('idx_ap_bill_vendor', 'vendor_id'),
        Index('idx_ap_bill_status', 'organization_id', 'status'),
        Index('idx_ap_bill_due', 'organization_id', 'due_date'),
    )

    @hybrid_property
    def amount_due(self):
        return (self.total_amount or Decimal('0')) - (self.amount_paid or Decimal('0'))

    @property
    def is_paid(self):
        return self.status == 'paid'

    @property
    def is_overdue(self):
        if self.status in ('paid', 'void'):
            return False
        return self.due_date < datetime.now().date() if self.due_date else False

    @property
    def is_approved(self):
        return self.approval_status == 'approved'

    def calculate_totals(self):
        """Calculate bill totals from lines."""
        self.subtotal = sum(line.amount or Decimal('0') for line in self.lines)
        self.tax_amount = sum(line.tax_amount or Decimal('0') for line in self.lines)
        self.total_amount = self.subtotal + self.tax_amount + (self.shipping_amount or Decimal('0')) - (self.discount_amount or Decimal('0'))

    def to_dict(self, include_lines=False):
        result = {
            'id': str(self.id),
            'bill_number': self.bill_number,
            'vendor_id': str(self.vendor_id),
            'vendor_name': self.vendor.name if self.vendor else None,
            'vendor_invoice_number': self.vendor_invoice_number,
            'bill_date': self.bill_date.isoformat() if self.bill_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'status': self.status,
            'approval_status': self.approval_status,
            'subtotal': float(self.subtotal or 0),
            'tax_amount': float(self.tax_amount or 0),
            'total_amount': float(self.total_amount or 0),
            'amount_paid': float(self.amount_paid or 0),
            'amount_due': float(self.amount_due),
            'currency': self.currency,
            'is_overdue': self.is_overdue,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_lines:
            result['lines'] = [line.to_dict() for line in self.lines]
        return result


class APBillLine(Base):
    """Bill line items."""
    __tablename__ = "ap_bill_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bill_id = Column(UUID(as_uuid=True), ForeignKey("ap_bills.id", ondelete="CASCADE"), nullable=False)
    line_order = Column(Integer, default=0)
    item_code = Column(String(50))
    description = Column(Text, nullable=False)
    quantity = Column(Numeric(10, 4), default=1)
    unit_price = Column(Numeric(12, 4), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    expense_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    tax_code = Column(String(20))
    tax_amount = Column(Numeric(12, 2), default=0)
    department_id = Column(UUID(as_uuid=True))
    project_id = Column(UUID(as_uuid=True))
    billable = Column(Boolean, default=False)
    billable_customer_id = Column(UUID(as_uuid=True), ForeignKey("ar_customers.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    bill = relationship("APBill", back_populates="lines")
    expense_account = relationship("ChartOfAccounts", foreign_keys=[expense_account_id])

    def calculate_amount(self):
        """Calculate line amount."""
        self.amount = (self.quantity or Decimal('1')) * (self.unit_price or Decimal('0'))

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
            'expense_account_id': str(self.expense_account_id) if self.expense_account_id else None,
            'billable': self.billable,
        }


class APPayment(Base):
    """Vendor bill payments."""
    __tablename__ = "ap_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    payment_number = Column(String(30), nullable=False)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("ap_vendors.id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    amount_applied = Column(Numeric(12, 2), default=0)
    payment_method = Column(String(30), nullable=False)
    check_number = Column(String(20))
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    status = Column(String(20), default='pending')
    memo = Column(Text)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"))
    bank_transaction_id = Column(UUID(as_uuid=True))
    reconciled_at = Column(DateTime)
    cleared_at = Column(DateTime)
    voided_at = Column(DateTime)
    voided_by = Column(Integer)
    void_reason = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    vendor = relationship("APVendor", back_populates="payments")
    applications = relationship("APPaymentApplication", back_populates="payment", cascade="all, delete-orphan")
    bank_account = relationship("ChartOfAccounts", foreign_keys=[bank_account_id])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])

    __table_args__ = (
        UniqueConstraint('organization_id', 'payment_number', name='uq_ap_pay_number'),
        CheckConstraint("payment_method IN ('check', 'ach', 'wire', 'credit_card', 'cash', 'other')", name="ck_ap_pay_method"),
        CheckConstraint("status IN ('pending', 'printed', 'sent', 'cleared', 'void')", name="ck_ap_pay_status"),
        Index('idx_ap_pay_vendor', 'vendor_id'),
        Index('idx_ap_pay_date', 'organization_id', 'payment_date'),
    )

    def to_dict(self, include_applications=False):
        result = {
            'id': str(self.id),
            'payment_number': self.payment_number,
            'vendor_id': str(self.vendor_id),
            'vendor_name': self.vendor.name if self.vendor else None,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'amount': float(self.amount or 0),
            'amount_applied': float(self.amount_applied or 0),
            'payment_method': self.payment_method,
            'check_number': self.check_number,
            'status': self.status,
            'memo': self.memo,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_applications:
            result['applications'] = [app.to_dict() for app in self.applications]
        return result


class APPaymentApplication(Base):
    """Application of payments to bills."""
    __tablename__ = "ap_payment_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("ap_payments.id", ondelete="CASCADE"), nullable=False)
    bill_id = Column(UUID(as_uuid=True), ForeignKey("ap_bills.id"), nullable=False)
    amount_applied = Column(Numeric(12, 2), nullable=False)
    applied_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    payment = relationship("APPayment", back_populates="applications")
    bill = relationship("APBill", back_populates="payment_applications")

    def to_dict(self):
        return {
            'id': str(self.id),
            'payment_id': str(self.payment_id),
            'bill_id': str(self.bill_id),
            'bill_number': self.bill.bill_number if self.bill else None,
            'amount_applied': float(self.amount_applied or 0),
            'applied_at': self.applied_at.isoformat() if self.applied_at else None,
        }
