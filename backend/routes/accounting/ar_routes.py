"""
Accounts Receivable API Routes.

Provides endpoints for managing customers, invoices, payments,
and AR aging reports.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr
import uuid
import logging

logger = logging.getLogger(__name__)

from database import get_db
from models.accounting.core import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    AccountingPeriod, AccountingAuditLog, TaxRate
)
from models.accounting.accounts_receivable import (
    ARCustomer, ARInvoice, ARInvoiceLine, ARPayment, ARPaymentApplication
)

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/accounting/ar", tags=["Accounts Receivable"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# Pydantic Schemas
# =============================================================================

class CustomerCreate(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_type: str = Field(default="individual", pattern="^(individual|business)$")
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_zip: Optional[str] = None
    billing_country: str = "USA"
    payment_terms: str = Field(default="net_30")
    credit_limit: Optional[Decimal] = None
    tax_exempt: bool = False
    tax_id: Optional[str] = None
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_zip: Optional[str] = None
    payment_terms: Optional[str] = None
    credit_limit: Optional[Decimal] = None
    tax_exempt: Optional[bool] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class InvoiceLineCreate(BaseModel):
    description: str = Field(..., min_length=1)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal
    account_id: str  # Revenue account
    tax_rate_id: Optional[str] = None
    discount_percent: Optional[Decimal] = None


class InvoiceCreate(BaseModel):
    customer_id: str
    invoice_date: date
    due_date: date
    po_number: Optional[str] = None
    terms: Optional[str] = None
    notes: Optional[str] = None
    lines: List[InvoiceLineCreate]


class InvoiceUpdate(BaseModel):
    due_date: Optional[date] = None
    po_number: Optional[str] = None
    terms: Optional[str] = None
    notes: Optional[str] = None


class PaymentCreate(BaseModel):
    customer_id: str
    payment_date: date
    amount: Decimal
    payment_method: str = Field(default="check", pattern="^(cash|check|ach|wire|credit_card|other)$")
    reference_number: Optional[str] = None
    deposit_account_id: str  # Bank account to deposit into
    notes: Optional[str] = None
    # Invoice applications
    applications: List[dict] = []  # [{"invoice_id": "...", "amount": 100.00}]


class PaymentApplicationCreate(BaseModel):
    invoice_id: str
    amount: Decimal


# =============================================================================
# Helper Functions
# =============================================================================

def get_organization_id(request: Request) -> int:
    """Get organization ID from tenant context middleware."""
    org_id = getattr(request.state, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def generate_invoice_number(db: Session, org_id: int) -> str:
    """Generate next invoice number."""
    last = db.query(ARInvoice).filter(
        ARInvoice.organization_id == org_id
    ).order_by(ARInvoice.created_at.desc()).first()

    if last and last.invoice_number:
        try:
            num = int(last.invoice_number.replace("INV-", ""))
            return f"INV-{num + 1:06d}"
        except Exception as e:
            logger.warning(f"Error parsing invoice number: {e}")
    return "INV-000001"


def generate_payment_number(db: Session, org_id: int) -> str:
    """Generate next payment receipt number."""
    last = db.query(ARPayment).filter(
        ARPayment.organization_id == org_id
    ).order_by(ARPayment.created_at.desc()).first()

    if last and last.payment_number:
        try:
            num = int(last.payment_number.replace("PMT-", ""))
            return f"PMT-{num + 1:06d}"
        except Exception as e:
            logger.warning(f"Error parsing payment number: {e}")
    return "PMT-000001"


def log_audit(db: Session, org_id: int, user_id: int, action: str,
              entity_type: str, entity_id: uuid.UUID, entity_number: str = None,
              old_values: dict = None, new_values: dict = None, summary: str = None):
    """Log an audit entry."""
    audit = AccountingAuditLog(
        organization_id=org_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_number=entity_number,
        old_values=old_values,
        new_values=new_values,
        change_summary=summary,
    )
    db.add(audit)


def get_ar_account(db: Session, org_id: int) -> ChartOfAccounts:
    """Get the default AR account."""
    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.account_number == "1200",  # Standard AR account
        ChartOfAccounts.is_active == True
    ).first()

    if not account:
        # Try to find any AR account
        account = db.query(ChartOfAccounts).filter(
            ChartOfAccounts.organization_id == org_id,
            ChartOfAccounts.account_type == "asset",
            ChartOfAccounts.account_sub_type == "accounts_receivable",
            ChartOfAccounts.is_active == True
        ).first()

    return account


# =============================================================================
# Customer Routes
# =============================================================================

@router.get("/customers")
async def list_customers(
    request: Request,
    search: Optional[str] = Query(None, description="Search by name or email"),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List AR customers."""
    org_id = get_organization_id(request)

    query = db.query(ARCustomer).filter(
        ARCustomer.organization_id == org_id
    )

    if search:
        query = query.filter(
            (ARCustomer.customer_name.ilike(f"%{search}%")) |
            (ARCustomer.email.ilike(f"%{search}%"))
        )

    if is_active is not None:
        query = query.filter(ARCustomer.is_active == is_active)

    total = query.count()
    customers = query.order_by(ARCustomer.customer_name).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "customers": [c.to_dict() for c in customers],
    }


@router.get("/customers/{customer_id}")
async def get_customer(
    request: Request,
    customer_id: str,
    db: Session = Depends(get_db),
):
    """Get a single customer with balance info."""
    org_id = get_organization_id(request)

    customer = db.query(ARCustomer).filter(
        ARCustomer.id == customer_id,
        ARCustomer.organization_id == org_id
    ).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Calculate open balance
    open_balance = db.query(func.sum(ARInvoice.balance_due)).filter(
        ARInvoice.customer_id == customer_id,
        ARInvoice.status.in_(['sent', 'partial', 'overdue'])
    ).scalar() or Decimal("0")

    result = customer.to_dict()
    result['open_balance'] = float(open_balance)

    return {
        "success": True,
        "customer": result,
    }


@router.post("/customers")
async def create_customer(
    request: Request,
    data: CustomerCreate,
    db: Session = Depends(get_db),
):
    """Create a new AR customer."""
    org_id = get_organization_id(request)

    # Check for duplicate email
    if data.email:
        existing = db.query(ARCustomer).filter(
            ARCustomer.organization_id == org_id,
            ARCustomer.email == data.email
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Customer with this email already exists")

    customer = ARCustomer(
        organization_id=org_id,
        **data.model_dump()
    )

    db.add(customer)
    db.flush()

    log_audit(
        db, org_id, 1, 'create', 'ar_customer', customer.id,
        entity_number=customer.customer_name,
        summary=f"Created customer {customer.customer_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Customer {customer.customer_name} created",
        "customer": customer.to_dict(),
    }


@router.put("/customers/{customer_id}")
async def update_customer(
    request: Request,
    customer_id: str,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
):
    """Update a customer."""
    org_id = get_organization_id(request)

    customer = db.query(ARCustomer).filter(
        ARCustomer.id == customer_id,
        ARCustomer.organization_id == org_id
    ).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    old_values = customer.to_dict()

    update_data = data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for key, value in update_data.items():
        if key not in _protected:
            setattr(customer, key, value)

    log_audit(
        db, org_id, 1, 'update', 'ar_customer', customer.id,
        entity_number=customer.customer_name,
        old_values=old_values,
        summary=f"Updated customer {customer.customer_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Customer {customer.customer_name} updated",
        "customer": customer.to_dict(),
    }


# =============================================================================
# Invoice Routes
# =============================================================================

@router.get("/invoices")
async def list_invoices(
    request: Request,
    customer_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List AR invoices."""
    org_id = get_organization_id(request)

    query = db.query(ARInvoice).filter(
        ARInvoice.organization_id == org_id
    )

    if customer_id:
        query = query.filter(ARInvoice.customer_id == customer_id)

    if status:
        query = query.filter(ARInvoice.status == status)

    if from_date:
        query = query.filter(ARInvoice.invoice_date >= from_date)

    if to_date:
        query = query.filter(ARInvoice.invoice_date <= to_date)

    total = query.count()
    invoices = query.order_by(ARInvoice.invoice_date.desc()).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "invoices": [inv.to_dict() for inv in invoices],
    }


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    request: Request,
    invoice_id: str,
    db: Session = Depends(get_db),
):
    """Get a single invoice with lines."""
    org_id = get_organization_id(request)

    invoice = db.query(ARInvoice).filter(
        ARInvoice.id == invoice_id,
        ARInvoice.organization_id == org_id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    result = invoice.to_dict(include_lines=True)

    # Get payment applications
    applications = db.query(ARPaymentApplication).filter(
        ARPaymentApplication.invoice_id == invoice_id
    ).all()

    result['payments'] = [
        {
            'payment_id': str(app.payment_id),
            'amount': float(app.amount_applied),
            'applied_at': app.applied_at.isoformat() if app.applied_at else None,
        }
        for app in applications
    ]

    return {
        "success": True,
        "invoice": result,
    }


@router.post("/invoices")
async def create_invoice(
    request: Request,
    data: InvoiceCreate,
    db: Session = Depends(get_db),
):
    """Create a new invoice."""
    org_id = get_organization_id(request)

    # Validate customer
    customer = db.query(ARCustomer).filter(
        ARCustomer.id == data.customer_id,
        ARCustomer.organization_id == org_id
    ).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not customer.is_active:
        raise HTTPException(status_code=400, detail="Customer is inactive")

    # Validate dates
    if data.due_date < data.invoice_date:
        raise HTTPException(status_code=400, detail="Due date must be on or after invoice date")

    # Validate lines
    if not data.lines:
        raise HTTPException(status_code=400, detail="Invoice must have at least one line")

    # Get AR account
    ar_account = get_ar_account(db, org_id)
    if not ar_account:
        raise HTTPException(status_code=400, detail="AR account not configured")

    # Create invoice
    invoice = ARInvoice(
        organization_id=org_id,
        customer_id=data.customer_id,
        invoice_number=generate_invoice_number(db, org_id),
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        po_number=data.po_number,
        terms=data.terms or customer.payment_terms,
        notes=data.notes,
        ar_account_id=ar_account.id,
        status='draft',
    )

    db.add(invoice)
    db.flush()

    # Create lines and calculate totals
    subtotal = Decimal("0")
    total_tax = Decimal("0")
    total_discount = Decimal("0")

    for i, line_data in enumerate(data.lines, 1):
        line_subtotal = line_data.quantity * line_data.unit_price
        line_discount = Decimal("0")
        line_tax = Decimal("0")

        if line_data.discount_percent:
            line_discount = line_subtotal * (line_data.discount_percent / 100)

        # Calculate tax if tax_rate_id provided (tax is on amount after discount)
        if line_data.tax_rate_id:
            tax_rate = db.query(TaxRate).filter(
                TaxRate.id == line_data.tax_rate_id,
                TaxRate.is_active == True
            ).first()
            if tax_rate:
                taxable_amount = line_subtotal - line_discount
                line_tax = taxable_amount * tax_rate.rate

        line_total = line_subtotal - line_discount + line_tax

        line = ARInvoiceLine(
            invoice_id=invoice.id,
            line_number=i,
            description=line_data.description,
            quantity=line_data.quantity,
            unit_price=line_data.unit_price,
            amount=line_subtotal,
            discount_amount=line_discount,
            tax_amount=line_tax,
            line_total=line_total,
            account_id=line_data.account_id,
            tax_rate_id=line_data.tax_rate_id,
        )
        db.add(line)

        subtotal += line_subtotal
        total_discount += line_discount
        total_tax += line_tax

    # Update invoice totals
    invoice.subtotal = subtotal
    invoice.discount_amount = total_discount
    invoice.tax_amount = total_tax
    invoice.total_amount = subtotal - total_discount + total_tax
    invoice.balance_due = invoice.total_amount

    log_audit(
        db, org_id, 1, 'create', 'ar_invoice', invoice.id,
        entity_number=invoice.invoice_number,
        summary=f"Created invoice {invoice.invoice_number} for {customer.customer_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Invoice {invoice.invoice_number} created",
        "invoice": invoice.to_dict(include_lines=True),
    }


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(
    request: Request,
    invoice_id: str,
    db: Session = Depends(get_db),
):
    """Mark invoice as sent."""
    org_id = get_organization_id(request)

    invoice = db.query(ARInvoice).filter(
        ARInvoice.id == invoice_id,
        ARInvoice.organization_id == org_id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != 'draft':
        raise HTTPException(status_code=400, detail=f"Cannot send invoice with status '{invoice.status}'")

    invoice.status = 'sent'
    invoice.sent_at = datetime.now(timezone.utc)

    # Create journal entry for AR
    # Debit AR, Credit Revenue
    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id,
        AccountingPeriod.start_date <= invoice.invoice_date,
        AccountingPeriod.end_date >= invoice.invoice_date,
        AccountingPeriod.status == 'open'
    ).first()

    if period:
        je = JournalEntry(
            organization_id=org_id,
            period_id=period.id,
            entry_number=f"AR-{invoice.invoice_number}",
            entry_date=invoice.invoice_date,
            description=f"Invoice {invoice.invoice_number} - {invoice.customer.customer_name}",
            source='ar_invoice',
            source_id=invoice.id,
            status='posted',
            posted_at=datetime.now(timezone.utc),
            posted_by=1,
        )
        db.add(je)
        db.flush()

        # Debit AR
        db.add(JournalEntryLine(
            entry_id=je.id,
            line_number=1,
            account_id=invoice.ar_account_id,
            description=f"AR - Invoice {invoice.invoice_number}",
            debit_amount=invoice.total_amount,
            credit_amount=Decimal("0"),
        ))

        # Credit revenue accounts from lines
        line_num = 2
        for line in invoice.lines:
            db.add(JournalEntryLine(
                entry_id=je.id,
                line_number=line_num,
                account_id=line.account_id,
                description=line.description,
                debit_amount=Decimal("0"),
                credit_amount=line.line_total,
            ))
            line_num += 1

        invoice.journal_entry_id = je.id

    # Update customer balance
    invoice.customer.current_balance = (invoice.customer.current_balance or Decimal("0")) + invoice.total_amount

    log_audit(
        db, org_id, 1, 'send', 'ar_invoice', invoice.id,
        entity_number=invoice.invoice_number,
        summary=f"Sent invoice {invoice.invoice_number}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Invoice {invoice.invoice_number} sent",
        "invoice": invoice.to_dict(),
    }


@router.post("/invoices/{invoice_id}/void")
async def void_invoice(
    request: Request,
    invoice_id: str,
    db: Session = Depends(get_db),
):
    """Void an invoice."""
    org_id = get_organization_id(request)

    invoice = db.query(ARInvoice).filter(
        ARInvoice.id == invoice_id,
        ARInvoice.organization_id == org_id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == 'void':
        raise HTTPException(status_code=400, detail="Invoice is already void")

    if invoice.status == 'paid':
        raise HTTPException(status_code=400, detail="Cannot void a paid invoice")

    # Check for payments
    if invoice.amount_paid > 0:
        raise HTTPException(status_code=400, detail="Cannot void invoice with payments applied")

    old_status = invoice.status
    invoice.status = 'void'
    invoice.voided_at = datetime.now(timezone.utc)
    invoice.voided_by = 1

    # Reverse journal entry if exists
    if invoice.journal_entry_id:
        je = db.query(JournalEntry).filter(JournalEntry.id == invoice.journal_entry_id).first()
        if je and je.status == 'posted':
            je.status = 'voided'
            je.voided_at = datetime.now(timezone.utc)
            je.voided_by = 1

    # Update customer balance
    if old_status in ['sent', 'partial', 'overdue']:
        invoice.customer.current_balance = (invoice.customer.current_balance or Decimal("0")) - invoice.balance_due

    log_audit(
        db, org_id, 1, 'void', 'ar_invoice', invoice.id,
        entity_number=invoice.invoice_number,
        summary=f"Voided invoice {invoice.invoice_number}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Invoice {invoice.invoice_number} voided",
        "invoice": invoice.to_dict(),
    }


# =============================================================================
# Payment Routes
# =============================================================================

@router.get("/payments")
async def list_payments(
    request: Request,
    customer_id: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List AR payments."""
    org_id = get_organization_id(request)

    query = db.query(ARPayment).filter(
        ARPayment.organization_id == org_id
    )

    if customer_id:
        query = query.filter(ARPayment.customer_id == customer_id)

    if from_date:
        query = query.filter(ARPayment.payment_date >= from_date)

    if to_date:
        query = query.filter(ARPayment.payment_date <= to_date)

    total = query.count()
    payments = query.order_by(ARPayment.payment_date.desc()).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "payments": [p.to_dict() for p in payments],
    }


@router.post("/payments")
async def create_payment(
    request: Request,
    data: PaymentCreate,
    db: Session = Depends(get_db),
):
    """Record a payment received."""
    org_id = get_organization_id(request)

    # Validate customer
    customer = db.query(ARCustomer).filter(
        ARCustomer.id == data.customer_id,
        ARCustomer.organization_id == org_id
    ).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Validate deposit account
    deposit_account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == data.deposit_account_id,
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.is_active == True
    ).first()

    if not deposit_account:
        raise HTTPException(status_code=404, detail="Deposit account not found")

    # Create payment
    payment = ARPayment(
        organization_id=org_id,
        customer_id=data.customer_id,
        payment_number=generate_payment_number(db, org_id),
        payment_date=data.payment_date,
        amount=data.amount,
        payment_method=data.payment_method,
        reference_number=data.reference_number,
        deposit_account_id=data.deposit_account_id,
        notes=data.notes,
        status='received',
    )

    db.add(payment)
    db.flush()

    # Apply to invoices if specified
    total_applied = Decimal("0")

    for app_data in data.applications:
        invoice = db.query(ARInvoice).filter(
            ARInvoice.id == app_data['invoice_id'],
            ARInvoice.customer_id == data.customer_id,
            ARInvoice.status.in_(['sent', 'partial', 'overdue'])
        ).first()

        if not invoice:
            continue

        apply_amount = min(Decimal(str(app_data['amount'])), invoice.balance_due)
        if apply_amount <= 0:
            continue

        # Create application
        application = ARPaymentApplication(
            payment_id=payment.id,
            invoice_id=invoice.id,
            amount_applied=apply_amount,
            applied_at=datetime.now(timezone.utc),
            applied_by=1,
        )
        db.add(application)

        # Update invoice
        invoice.amount_paid = (invoice.amount_paid or Decimal("0")) + apply_amount
        invoice.balance_due = invoice.total_amount - invoice.amount_paid

        if invoice.balance_due <= 0:
            invoice.status = 'paid'
            invoice.paid_at = datetime.now(timezone.utc)
        else:
            invoice.status = 'partial'

        total_applied += apply_amount

    payment.amount_applied = total_applied
    payment.amount_unapplied = payment.amount - total_applied

    # Update customer balance
    customer.current_balance = (customer.current_balance or Decimal("0")) - total_applied

    # Create journal entry
    # Debit Bank, Credit AR
    ar_account = get_ar_account(db, org_id)

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id,
        AccountingPeriod.start_date <= data.payment_date,
        AccountingPeriod.end_date >= data.payment_date,
        AccountingPeriod.status == 'open'
    ).first()

    if period and ar_account:
        je = JournalEntry(
            organization_id=org_id,
            period_id=period.id,
            entry_number=f"PMT-{payment.payment_number}",
            entry_date=data.payment_date,
            description=f"Payment {payment.payment_number} from {customer.customer_name}",
            source='ar_payment',
            source_id=payment.id,
            status='posted',
            posted_at=datetime.now(timezone.utc),
            posted_by=1,
        )
        db.add(je)
        db.flush()

        # Debit Bank
        db.add(JournalEntryLine(
            entry_id=je.id,
            line_number=1,
            account_id=deposit_account.id,
            description=f"Deposit - {payment.payment_number}",
            debit_amount=data.amount,
            credit_amount=Decimal("0"),
        ))

        # Credit AR
        db.add(JournalEntryLine(
            entry_id=je.id,
            line_number=2,
            account_id=ar_account.id,
            description=f"AR Payment - {customer.customer_name}",
            debit_amount=Decimal("0"),
            credit_amount=total_applied,
        ))

        # Handle unapplied amount (credit to unapplied payments if any)
        if payment.amount_unapplied > 0:
            db.add(JournalEntryLine(
                entry_id=je.id,
                line_number=3,
                account_id=ar_account.id,  # Or separate unapplied account
                description=f"Unapplied Payment - {customer.customer_name}",
                debit_amount=Decimal("0"),
                credit_amount=payment.amount_unapplied,
            ))

        payment.journal_entry_id = je.id

    log_audit(
        db, org_id, 1, 'create', 'ar_payment', payment.id,
        entity_number=payment.payment_number,
        summary=f"Received payment {payment.payment_number} from {customer.customer_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Payment {payment.payment_number} recorded",
        "payment": payment.to_dict(),
    }


# =============================================================================
# Aging Report
# =============================================================================

@router.get("/aging-report")
async def get_aging_report(
    request: Request,
    as_of_date: Optional[date] = Query(None, description="Report as of date"),
    customer_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get AR aging report."""
    org_id = get_organization_id(request)
    report_date = as_of_date or date.today()

    # Get open invoices
    query = db.query(ARInvoice).filter(
        ARInvoice.organization_id == org_id,
        ARInvoice.status.in_(['sent', 'partial', 'overdue']),
        ARInvoice.invoice_date <= report_date
    )

    if customer_id:
        query = query.filter(ARInvoice.customer_id == customer_id)

    invoices = query.all()

    # Categorize by age
    aging_buckets = {
        'current': Decimal("0"),
        '1_30': Decimal("0"),
        '31_60': Decimal("0"),
        '61_90': Decimal("0"),
        'over_90': Decimal("0"),
    }

    customer_aging = {}

    for invoice in invoices:
        days_old = (report_date - invoice.due_date).days
        balance = invoice.balance_due

        if days_old <= 0:
            bucket = 'current'
        elif days_old <= 30:
            bucket = '1_30'
        elif days_old <= 60:
            bucket = '31_60'
        elif days_old <= 90:
            bucket = '61_90'
        else:
            bucket = 'over_90'

        aging_buckets[bucket] += balance

        # Track by customer
        cust_id = str(invoice.customer_id)
        if cust_id not in customer_aging:
            customer_aging[cust_id] = {
                'customer_id': cust_id,
                'customer_name': invoice.customer.customer_name,
                'current': Decimal("0"),
                '1_30': Decimal("0"),
                '31_60': Decimal("0"),
                '61_90': Decimal("0"),
                'over_90': Decimal("0"),
                'total': Decimal("0"),
            }

        customer_aging[cust_id][bucket] += balance
        customer_aging[cust_id]['total'] += balance

    total = sum(aging_buckets.values())

    return {
        "success": True,
        "report_date": report_date.isoformat(),
        "summary": {
            "current": float(aging_buckets['current']),
            "1_30_days": float(aging_buckets['1_30']),
            "31_60_days": float(aging_buckets['31_60']),
            "61_90_days": float(aging_buckets['61_90']),
            "over_90_days": float(aging_buckets['over_90']),
            "total": float(total),
        },
        "by_customer": [
            {
                'customer_id': v['customer_id'],
                'customer_name': v['customer_name'],
                'current': float(v['current']),
                '1_30_days': float(v['1_30']),
                '31_60_days': float(v['31_60']),
                '61_90_days': float(v['61_90']),
                'over_90_days': float(v['over_90']),
                'total': float(v['total']),
            }
            for v in sorted(customer_aging.values(), key=lambda x: x['total'], reverse=True)
        ],
    }


# =============================================================================
# Dashboard / Summary
# =============================================================================

@router.get("/summary")
async def get_ar_summary(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get AR summary for dashboard."""
    org_id = get_organization_id(request)
    today = date.today()

    # Open balance
    open_balance = db.query(func.sum(ARInvoice.balance_due)).filter(
        ARInvoice.organization_id == org_id,
        ARInvoice.status.in_(['sent', 'partial', 'overdue'])
    ).scalar() or Decimal("0")

    # Overdue balance
    overdue_balance = db.query(func.sum(ARInvoice.balance_due)).filter(
        ARInvoice.organization_id == org_id,
        ARInvoice.status.in_(['sent', 'partial', 'overdue']),
        ARInvoice.due_date < today
    ).scalar() or Decimal("0")

    # Invoice counts
    invoice_counts = db.query(
        ARInvoice.status,
        func.count(ARInvoice.id)
    ).filter(
        ARInvoice.organization_id == org_id
    ).group_by(ARInvoice.status).all()

    counts = {status: count for status, count in invoice_counts}

    # Payments this month
    first_of_month = today.replace(day=1)
    payments_this_month = db.query(func.sum(ARPayment.amount)).filter(
        ARPayment.organization_id == org_id,
        ARPayment.payment_date >= first_of_month
    ).scalar() or Decimal("0")

    # Customer count
    customer_count = db.query(func.count(ARCustomer.id)).filter(
        ARCustomer.organization_id == org_id,
        ARCustomer.is_active == True
    ).scalar() or 0

    return {
        "success": True,
        "summary": {
            "open_balance": float(open_balance),
            "overdue_balance": float(overdue_balance),
            "overdue_percent": round((float(overdue_balance) / float(open_balance) * 100), 1) if open_balance > 0 else 0,
            "draft_invoices": counts.get('draft', 0),
            "sent_invoices": counts.get('sent', 0),
            "partial_invoices": counts.get('partial', 0),
            "overdue_invoices": counts.get('overdue', 0),
            "payments_this_month": float(payments_this_month),
            "active_customers": customer_count,
        },
    }
