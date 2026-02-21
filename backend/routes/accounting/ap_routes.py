"""
Accounts Payable API Routes.

Provides endpoints for managing vendors, bills, payments,
approval workflows, and AP aging reports.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import Optional, List
from datetime import date, datetime, timedelta
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr
import uuid

from database import get_db
from models.accounting.core import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    AccountingPeriod, AccountingAuditLog, TaxRate
)
from models.accounting.accounts_payable import (
    APVendor, APBill, APBillLine, APPayment, APPaymentApplication
)


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from main import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/accounting/ap", tags=["Accounts Payable"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# Pydantic Schemas
# =============================================================================

class VendorCreate(BaseModel):
    vendor_name: str = Field(..., min_length=1, max_length=255)
    vendor_type: str = Field(default="supplier", pattern="^(supplier|contractor|service|other)$")
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: str = "USA"
    payment_terms: str = Field(default="net_30")
    default_expense_account_id: Optional[str] = None
    tax_id: Optional[str] = None
    is_1099_vendor: bool = False
    w9_on_file: bool = False
    notes: Optional[str] = None


class VendorUpdate(BaseModel):
    vendor_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    payment_terms: Optional[str] = None
    default_expense_account_id: Optional[str] = None
    is_1099_vendor: Optional[bool] = None
    w9_on_file: Optional[bool] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class BillLineCreate(BaseModel):
    description: str = Field(..., min_length=1)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal
    account_id: str  # Expense account
    department_id: Optional[str] = None
    project_id: Optional[str] = None
    tax_rate_id: Optional[str] = None


class BillCreate(BaseModel):
    vendor_id: str
    bill_date: date
    due_date: date
    vendor_invoice_number: Optional[str] = None
    terms: Optional[str] = None
    notes: Optional[str] = None
    lines: List[BillLineCreate]


class BillUpdate(BaseModel):
    due_date: Optional[date] = None
    vendor_invoice_number: Optional[str] = None
    terms: Optional[str] = None
    notes: Optional[str] = None


class BillApprovalRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None


class PaymentCreate(BaseModel):
    payment_date: date
    payment_account_id: str  # Bank account paying from
    payment_method: str = Field(default="check", pattern="^(check|ach|wire|credit_card|cash|other)$")
    check_number: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    # Bills to pay
    bills: List[dict]  # [{"bill_id": "...", "amount": 100.00}]


class BatchPaymentCreate(BaseModel):
    payment_date: date
    payment_account_id: str
    payment_method: str = Field(default="ach")
    vendor_ids: Optional[List[str]] = None  # If None, pay all due bills
    include_overdue_only: bool = False


# =============================================================================
# Helper Functions
# =============================================================================

def get_organization_id(request: Request) -> int:
    """Get organization ID from tenant context middleware."""
    org_id = getattr(request.state, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def generate_bill_number(db: Session, org_id: int) -> str:
    """Generate next bill number."""
    last = db.query(APBill).filter(
        APBill.organization_id == org_id
    ).order_by(APBill.created_at.desc()).first()

    if last and last.bill_number:
        try:
            num = int(last.bill_number.replace("BILL-", ""))
            return f"BILL-{num + 1:06d}"
        except Exception:
            pass
    return "BILL-000001"


def generate_payment_number(db: Session, org_id: int) -> str:
    """Generate next payment number."""
    last = db.query(APPayment).filter(
        APPayment.organization_id == org_id
    ).order_by(APPayment.created_at.desc()).first()

    if last and last.payment_number:
        try:
            num = int(last.payment_number.replace("CHK-", ""))
            return f"CHK-{num + 1:06d}"
        except Exception:
            pass
    return "CHK-000001"


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


def get_ap_account(db: Session, org_id: int) -> ChartOfAccounts:
    """Get the default AP account."""
    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.account_number == "2000",  # Standard AP account
        ChartOfAccounts.is_active == True
    ).first()

    if not account:
        # Try to find any AP account
        account = db.query(ChartOfAccounts).filter(
            ChartOfAccounts.organization_id == org_id,
            ChartOfAccounts.account_type == "liability",
            ChartOfAccounts.account_sub_type == "accounts_payable",
            ChartOfAccounts.is_active == True
        ).first()

    return account


# =============================================================================
# Vendor Routes
# =============================================================================

@router.get("/vendors")
async def list_vendors(
    request: Request,
    search: Optional[str] = Query(None, description="Search by name or email"),
    is_active: Optional[bool] = Query(None),
    is_1099: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List AP vendors."""
    org_id = get_organization_id(request)

    query = db.query(APVendor).filter(
        APVendor.organization_id == org_id
    )

    if search:
        query = query.filter(
            (APVendor.vendor_name.ilike(f"%{search}%")) |
            (APVendor.email.ilike(f"%{search}%"))
        )

    if is_active is not None:
        query = query.filter(APVendor.is_active == is_active)

    if is_1099 is not None:
        query = query.filter(APVendor.is_1099_vendor == is_1099)

    total = query.count()
    vendors = query.order_by(APVendor.vendor_name).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "vendors": [v.to_dict() for v in vendors],
    }


@router.get("/vendors/{vendor_id}")
async def get_vendor(
    request: Request,
    vendor_id: str,
    db: Session = Depends(get_db),
):
    """Get a single vendor with balance info."""
    org_id = get_organization_id(request)

    vendor = db.query(APVendor).filter(
        APVendor.id == vendor_id,
        APVendor.organization_id == org_id
    ).first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Calculate open balance
    open_balance = db.query(func.sum(APBill.balance_due)).filter(
        APBill.vendor_id == vendor_id,
        APBill.status.in_(['approved', 'partial', 'overdue'])
    ).scalar() or Decimal("0")

    # YTD payments
    first_of_year = date.today().replace(month=1, day=1)
    ytd_payments = db.query(func.sum(APPaymentApplication.amount_applied)).join(
        APBill, APPaymentApplication.bill_id == APBill.id
    ).filter(
        APBill.vendor_id == vendor_id,
        APPaymentApplication.applied_at >= first_of_year
    ).scalar() or Decimal("0")

    result = vendor.to_dict()
    result['open_balance'] = float(open_balance)
    result['ytd_payments'] = float(ytd_payments)

    return {
        "success": True,
        "vendor": result,
    }


@router.post("/vendors")
async def create_vendor(
    request: Request,
    data: VendorCreate,
    db: Session = Depends(get_db),
):
    """Create a new AP vendor."""
    org_id = get_organization_id(request)

    # Check for duplicate
    existing = db.query(APVendor).filter(
        APVendor.organization_id == org_id,
        APVendor.vendor_name == data.vendor_name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Vendor with this name already exists")

    vendor = APVendor(
        organization_id=org_id,
        **data.model_dump()
    )

    db.add(vendor)
    db.flush()

    log_audit(
        db, org_id, 1, 'create', 'ap_vendor', vendor.id,
        entity_number=vendor.vendor_name,
        summary=f"Created vendor {vendor.vendor_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Vendor {vendor.vendor_name} created",
        "vendor": vendor.to_dict(),
    }


@router.put("/vendors/{vendor_id}")
async def update_vendor(
    request: Request,
    vendor_id: str,
    data: VendorUpdate,
    db: Session = Depends(get_db),
):
    """Update a vendor."""
    org_id = get_organization_id(request)

    vendor = db.query(APVendor).filter(
        APVendor.id == vendor_id,
        APVendor.organization_id == org_id
    ).first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    old_values = vendor.to_dict()

    update_data = data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for key, value in update_data.items():
        if key not in _protected:
            setattr(vendor, key, value)

    log_audit(
        db, org_id, 1, 'update', 'ap_vendor', vendor.id,
        entity_number=vendor.vendor_name,
        old_values=old_values,
        summary=f"Updated vendor {vendor.vendor_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Vendor {vendor.vendor_name} updated",
        "vendor": vendor.to_dict(),
    }


# =============================================================================
# Bill Routes
# =============================================================================

@router.get("/bills")
async def list_bills(
    request: Request,
    vendor_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    needs_approval: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List AP bills."""
    org_id = get_organization_id(request)

    query = db.query(APBill).filter(
        APBill.organization_id == org_id
    )

    if vendor_id:
        query = query.filter(APBill.vendor_id == vendor_id)

    if status:
        query = query.filter(APBill.status == status)

    if needs_approval:
        query = query.filter(APBill.status == 'pending_approval')

    if from_date:
        query = query.filter(APBill.bill_date >= from_date)

    if to_date:
        query = query.filter(APBill.bill_date <= to_date)

    total = query.count()
    bills = query.order_by(APBill.due_date.asc()).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "bills": [bill.to_dict() for bill in bills],
    }


@router.get("/bills/due")
async def get_bills_due(
    request: Request,
    days_ahead: int = Query(7, ge=0, le=90),
    vendor_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get bills due within specified days."""
    org_id = get_organization_id(request)
    today = date.today()
    due_by = today + timedelta(days=days_ahead)

    query = db.query(APBill).filter(
        APBill.organization_id == org_id,
        APBill.status.in_(['approved', 'partial', 'overdue']),
        APBill.due_date <= due_by
    )

    if vendor_id:
        query = query.filter(APBill.vendor_id == vendor_id)

    bills = query.order_by(APBill.due_date.asc()).all()

    total_due = sum(bill.balance_due for bill in bills)

    return {
        "success": True,
        "days_ahead": days_ahead,
        "due_by": due_by.isoformat(),
        "total_due": float(total_due),
        "bill_count": len(bills),
        "bills": [
            {
                **bill.to_dict(),
                "days_until_due": (bill.due_date - today).days,
            }
            for bill in bills
        ],
    }


@router.get("/bills/{bill_id}")
async def get_bill(
    request: Request,
    bill_id: str,
    db: Session = Depends(get_db),
):
    """Get a single bill with lines."""
    org_id = get_organization_id(request)

    bill = db.query(APBill).filter(
        APBill.id == bill_id,
        APBill.organization_id == org_id
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    result = bill.to_dict(include_lines=True)

    # Get payment applications
    applications = db.query(APPaymentApplication).filter(
        APPaymentApplication.bill_id == bill_id
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
        "bill": result,
    }


@router.post("/bills")
async def create_bill(
    request: Request,
    data: BillCreate,
    db: Session = Depends(get_db),
):
    """Create a new bill."""
    org_id = get_organization_id(request)

    # Validate vendor
    vendor = db.query(APVendor).filter(
        APVendor.id == data.vendor_id,
        APVendor.organization_id == org_id
    ).first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    if not vendor.is_active:
        raise HTTPException(status_code=400, detail="Vendor is inactive")

    # Validate dates
    if data.due_date < data.bill_date:
        raise HTTPException(status_code=400, detail="Due date must be on or after bill date")

    # Validate lines
    if not data.lines:
        raise HTTPException(status_code=400, detail="Bill must have at least one line")

    # Get AP account
    ap_account = get_ap_account(db, org_id)
    if not ap_account:
        raise HTTPException(status_code=400, detail="AP account not configured")

    # Check for duplicate vendor invoice
    if data.vendor_invoice_number:
        existing = db.query(APBill).filter(
            APBill.vendor_id == data.vendor_id,
            APBill.vendor_invoice_number == data.vendor_invoice_number,
            APBill.status != 'void'
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bill with this vendor invoice number already exists")

    # Create bill
    bill = APBill(
        organization_id=org_id,
        vendor_id=data.vendor_id,
        bill_number=generate_bill_number(db, org_id),
        vendor_invoice_number=data.vendor_invoice_number,
        bill_date=data.bill_date,
        due_date=data.due_date,
        terms=data.terms or vendor.payment_terms,
        notes=data.notes,
        ap_account_id=ap_account.id,
        status='draft',
    )

    db.add(bill)
    db.flush()

    # Create lines and calculate totals
    subtotal = Decimal("0")
    total_tax = Decimal("0")

    for i, line_data in enumerate(data.lines, 1):
        line_subtotal = line_data.quantity * line_data.unit_price
        line_tax = Decimal("0")

        # Calculate tax if tax_rate_id provided
        if line_data.tax_rate_id:
            tax_rate = db.query(TaxRate).filter(
                TaxRate.id == line_data.tax_rate_id,
                TaxRate.is_active == True
            ).first()
            if tax_rate:
                line_tax = line_subtotal * tax_rate.rate

        line_total = line_subtotal + line_tax

        line = APBillLine(
            bill_id=bill.id,
            line_number=i,
            description=line_data.description,
            quantity=line_data.quantity,
            unit_price=line_data.unit_price,
            amount=line_subtotal,
            tax_amount=line_tax,
            line_total=line_total,
            account_id=line_data.account_id,
            department_id=line_data.department_id,
            project_id=line_data.project_id,
            tax_rate_id=line_data.tax_rate_id,
        )
        db.add(line)

        subtotal += line_subtotal
        total_tax += line_tax

    # Update bill totals
    bill.subtotal = subtotal
    bill.tax_amount = total_tax
    bill.total_amount = subtotal + total_tax
    bill.balance_due = bill.total_amount

    log_audit(
        db, org_id, 1, 'create', 'ap_bill', bill.id,
        entity_number=bill.bill_number,
        summary=f"Created bill {bill.bill_number} from {vendor.vendor_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Bill {bill.bill_number} created",
        "bill": bill.to_dict(include_lines=True),
    }


@router.post("/bills/{bill_id}/submit")
async def submit_bill_for_approval(
    request: Request,
    bill_id: str,
    db: Session = Depends(get_db),
):
    """Submit a bill for approval."""
    org_id = get_organization_id(request)

    bill = db.query(APBill).filter(
        APBill.id == bill_id,
        APBill.organization_id == org_id
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    if bill.status != 'draft':
        raise HTTPException(status_code=400, detail=f"Cannot submit bill with status '{bill.status}'")

    bill.status = 'pending_approval'
    bill.submitted_at = datetime.utcnow()
    bill.submitted_by = 1

    log_audit(
        db, org_id, 1, 'submit', 'ap_bill', bill.id,
        entity_number=bill.bill_number,
        summary=f"Submitted bill {bill.bill_number} for approval"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Bill {bill.bill_number} submitted for approval",
        "bill": bill.to_dict(),
    }


@router.post("/bills/{bill_id}/approve")
async def approve_bill(
    request: Request,
    bill_id: str,
    data: BillApprovalRequest,
    db: Session = Depends(get_db),
):
    """Approve or reject a bill."""
    org_id = get_organization_id(request)

    bill = db.query(APBill).filter(
        APBill.id == bill_id,
        APBill.organization_id == org_id
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    if bill.status != 'pending_approval':
        raise HTTPException(status_code=400, detail=f"Bill is not pending approval")

    if data.approved:
        bill.status = 'approved'
        bill.approved_at = datetime.utcnow()
        bill.approved_by = 1

        if data.notes:
            bill.notes = (bill.notes or '') + f"\nApproval: {data.notes}"

        # Create journal entry
        # Debit Expense accounts, Credit AP
        period = db.query(AccountingPeriod).filter(
            AccountingPeriod.organization_id == org_id,
            AccountingPeriod.start_date <= bill.bill_date,
            AccountingPeriod.end_date >= bill.bill_date,
            AccountingPeriod.status == 'open'
        ).first()

        if period:
            je = JournalEntry(
                organization_id=org_id,
                period_id=period.id,
                entry_number=f"AP-{bill.bill_number}",
                entry_date=bill.bill_date,
                description=f"Bill {bill.bill_number} - {bill.vendor.vendor_name}",
                source='ap_bill',
                source_id=bill.id,
                status='posted',
                posted_at=datetime.utcnow(),
                posted_by=1,
            )
            db.add(je)
            db.flush()

            # Debit expense accounts from lines
            line_num = 1
            for line in bill.lines:
                db.add(JournalEntryLine(
                    entry_id=je.id,
                    line_number=line_num,
                    account_id=line.account_id,
                    description=line.description,
                    debit_amount=line.line_total,
                    credit_amount=Decimal("0"),
                    department_id=line.department_id,
                ))
                line_num += 1

            # Credit AP
            db.add(JournalEntryLine(
                entry_id=je.id,
                line_number=line_num,
                account_id=bill.ap_account_id,
                description=f"AP - Bill {bill.bill_number}",
                debit_amount=Decimal("0"),
                credit_amount=bill.total_amount,
            ))

            bill.journal_entry_id = je.id

        # Update vendor balance
        bill.vendor.current_balance = (bill.vendor.current_balance or Decimal("0")) + bill.total_amount

        action = 'approve'
        message = f"Bill {bill.bill_number} approved"
    else:
        bill.status = 'rejected'
        bill.rejected_at = datetime.utcnow()
        bill.rejected_by = 1
        bill.rejection_reason = data.notes

        action = 'reject'
        message = f"Bill {bill.bill_number} rejected"

    log_audit(
        db, org_id, 1, action, 'ap_bill', bill.id,
        entity_number=bill.bill_number,
        summary=message
    )

    db.commit()

    return {
        "success": True,
        "message": message,
        "bill": bill.to_dict(),
    }


@router.post("/bills/{bill_id}/void")
async def void_bill(
    request: Request,
    bill_id: str,
    db: Session = Depends(get_db),
):
    """Void a bill."""
    org_id = get_organization_id(request)

    bill = db.query(APBill).filter(
        APBill.id == bill_id,
        APBill.organization_id == org_id
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    if bill.status == 'void':
        raise HTTPException(status_code=400, detail="Bill is already void")

    if bill.status == 'paid':
        raise HTTPException(status_code=400, detail="Cannot void a paid bill")

    if bill.amount_paid > 0:
        raise HTTPException(status_code=400, detail="Cannot void bill with payments applied")

    old_status = bill.status
    bill.status = 'void'
    bill.voided_at = datetime.utcnow()
    bill.voided_by = 1

    # Reverse journal entry if exists
    if bill.journal_entry_id:
        je = db.query(JournalEntry).filter(JournalEntry.id == bill.journal_entry_id).first()
        if je and je.status == 'posted':
            je.status = 'voided'
            je.voided_at = datetime.utcnow()
            je.voided_by = 1

    # Update vendor balance
    if old_status == 'approved':
        bill.vendor.current_balance = (bill.vendor.current_balance or Decimal("0")) - bill.balance_due

    log_audit(
        db, org_id, 1, 'void', 'ap_bill', bill.id,
        entity_number=bill.bill_number,
        summary=f"Voided bill {bill.bill_number}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Bill {bill.bill_number} voided",
        "bill": bill.to_dict(),
    }


# =============================================================================
# Payment Routes
# =============================================================================

@router.get("/payments")
async def list_payments(
    request: Request,
    vendor_id: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List AP payments."""
    org_id = get_organization_id(request)

    query = db.query(APPayment).filter(
        APPayment.organization_id == org_id
    )

    if vendor_id:
        query = query.filter(APPayment.vendor_id == vendor_id)

    if from_date:
        query = query.filter(APPayment.payment_date >= from_date)

    if to_date:
        query = query.filter(APPayment.payment_date <= to_date)

    total = query.count()
    payments = query.order_by(APPayment.payment_date.desc()).offset(skip).limit(limit).all()

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
    """Create a payment to one or more bills."""
    org_id = get_organization_id(request)

    if not data.bills:
        raise HTTPException(status_code=400, detail="Must specify at least one bill to pay")

    # Validate payment account
    payment_account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == data.payment_account_id,
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.is_active == True
    ).first()

    if not payment_account:
        raise HTTPException(status_code=404, detail="Payment account not found")

    # Get AP account
    ap_account = get_ap_account(db, org_id)
    if not ap_account:
        raise HTTPException(status_code=400, detail="AP account not configured")

    # Group bills by vendor
    vendor_bills = {}
    total_amount = Decimal("0")

    for bill_data in data.bills:
        bill = db.query(APBill).filter(
            APBill.id == bill_data['bill_id'],
            APBill.organization_id == org_id,
            APBill.status.in_(['approved', 'partial', 'overdue'])
        ).first()

        if not bill:
            raise HTTPException(status_code=404, detail=f"Bill {bill_data['bill_id']} not found or not payable")

        pay_amount = min(Decimal(str(bill_data['amount'])), bill.balance_due)
        if pay_amount <= 0:
            continue

        vendor_id = str(bill.vendor_id)
        if vendor_id not in vendor_bills:
            vendor_bills[vendor_id] = {
                'vendor': bill.vendor,
                'bills': [],
                'total': Decimal("0"),
            }

        vendor_bills[vendor_id]['bills'].append({
            'bill': bill,
            'amount': pay_amount,
        })
        vendor_bills[vendor_id]['total'] += pay_amount
        total_amount += pay_amount

    if not vendor_bills:
        raise HTTPException(status_code=400, detail="No valid bills to pay")

    # Create payments (one per vendor)
    payments = []
    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id,
        AccountingPeriod.start_date <= data.payment_date,
        AccountingPeriod.end_date >= data.payment_date,
        AccountingPeriod.status == 'open'
    ).first()

    for vendor_id, vendor_data in vendor_bills.items():
        vendor = vendor_data['vendor']

        payment = APPayment(
            organization_id=org_id,
            vendor_id=vendor_id,
            payment_number=generate_payment_number(db, org_id),
            payment_date=data.payment_date,
            amount=vendor_data['total'],
            payment_method=data.payment_method,
            check_number=data.check_number,
            reference_number=data.reference_number,
            payment_account_id=data.payment_account_id,
            notes=data.notes,
            status='completed',
        )

        db.add(payment)
        db.flush()

        # Apply to bills
        for bill_info in vendor_data['bills']:
            bill = bill_info['bill']
            pay_amount = bill_info['amount']

            application = APPaymentApplication(
                payment_id=payment.id,
                bill_id=bill.id,
                amount_applied=pay_amount,
                applied_at=datetime.utcnow(),
                applied_by=1,
            )
            db.add(application)

            # Update bill
            bill.amount_paid = (bill.amount_paid or Decimal("0")) + pay_amount
            bill.balance_due = bill.total_amount - bill.amount_paid

            if bill.balance_due <= 0:
                bill.status = 'paid'
                bill.paid_at = datetime.utcnow()
            else:
                bill.status = 'partial'

        # Update vendor balance
        vendor.current_balance = (vendor.current_balance or Decimal("0")) - vendor_data['total']
        vendor.last_payment_date = data.payment_date

        # Track 1099 payments
        if vendor.is_1099_vendor:
            vendor.ytd_1099_payments = (vendor.ytd_1099_payments or Decimal("0")) + vendor_data['total']

        # Create journal entry
        # Debit AP, Credit Bank
        if period:
            je = JournalEntry(
                organization_id=org_id,
                period_id=period.id,
                entry_number=f"PAY-{payment.payment_number}",
                entry_date=data.payment_date,
                description=f"Payment {payment.payment_number} to {vendor.vendor_name}",
                source='ap_payment',
                source_id=payment.id,
                status='posted',
                posted_at=datetime.utcnow(),
                posted_by=1,
            )
            db.add(je)
            db.flush()

            # Debit AP
            db.add(JournalEntryLine(
                entry_id=je.id,
                line_number=1,
                account_id=ap_account.id,
                description=f"AP Payment - {vendor.vendor_name}",
                debit_amount=vendor_data['total'],
                credit_amount=Decimal("0"),
            ))

            # Credit Bank
            db.add(JournalEntryLine(
                entry_id=je.id,
                line_number=2,
                account_id=payment_account.id,
                description=f"Payment - {payment.payment_number}",
                debit_amount=Decimal("0"),
                credit_amount=vendor_data['total'],
            ))

            payment.journal_entry_id = je.id

        log_audit(
            db, org_id, 1, 'create', 'ap_payment', payment.id,
            entity_number=payment.payment_number,
            summary=f"Paid {vendor.vendor_name} ${float(vendor_data['total']):,.2f}"
        )

        payments.append(payment)

    db.commit()

    return {
        "success": True,
        "message": f"Created {len(payments)} payment(s) totaling ${float(total_amount):,.2f}",
        "payments": [p.to_dict() for p in payments],
    }


@router.post("/payments/batch")
async def create_batch_payment(
    request: Request,
    data: BatchPaymentCreate,
    db: Session = Depends(get_db),
):
    """Create batch payment for all due bills."""
    org_id = get_organization_id(request)
    today = date.today()

    # Get bills to pay
    query = db.query(APBill).filter(
        APBill.organization_id == org_id,
        APBill.status.in_(['approved', 'partial', 'overdue'])
    )

    if data.vendor_ids:
        query = query.filter(APBill.vendor_id.in_(data.vendor_ids))

    if data.include_overdue_only:
        query = query.filter(APBill.due_date < today)
    else:
        query = query.filter(APBill.due_date <= data.payment_date)

    bills = query.all()

    if not bills:
        return {
            "success": True,
            "message": "No bills due for payment",
            "payments": [],
        }

    # Convert to payment format
    bill_data = [
        {"bill_id": str(bill.id), "amount": float(bill.balance_due)}
        for bill in bills
    ]

    # Use regular payment endpoint
    payment_request = PaymentCreate(
        payment_date=data.payment_date,
        payment_account_id=data.payment_account_id,
        payment_method=data.payment_method,
        bills=bill_data,
    )

    return await create_payment(request, payment_request, db)


# =============================================================================
# Aging Report
# =============================================================================

@router.get("/aging-report")
async def get_aging_report(
    request: Request,
    as_of_date: Optional[date] = Query(None, description="Report as of date"),
    vendor_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get AP aging report."""
    org_id = get_organization_id(request)
    report_date = as_of_date or date.today()

    # Get open bills
    query = db.query(APBill).filter(
        APBill.organization_id == org_id,
        APBill.status.in_(['approved', 'partial', 'overdue']),
        APBill.bill_date <= report_date
    )

    if vendor_id:
        query = query.filter(APBill.vendor_id == vendor_id)

    bills = query.all()

    # Categorize by age
    aging_buckets = {
        'current': Decimal("0"),
        '1_30': Decimal("0"),
        '31_60': Decimal("0"),
        '61_90': Decimal("0"),
        'over_90': Decimal("0"),
    }

    vendor_aging = {}

    for bill in bills:
        days_old = (report_date - bill.due_date).days
        balance = bill.balance_due

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

        # Track by vendor
        v_id = str(bill.vendor_id)
        if v_id not in vendor_aging:
            vendor_aging[v_id] = {
                'vendor_id': v_id,
                'vendor_name': bill.vendor.vendor_name,
                'current': Decimal("0"),
                '1_30': Decimal("0"),
                '31_60': Decimal("0"),
                '61_90': Decimal("0"),
                'over_90': Decimal("0"),
                'total': Decimal("0"),
            }

        vendor_aging[v_id][bucket] += balance
        vendor_aging[v_id]['total'] += balance

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
        "by_vendor": [
            {
                'vendor_id': v['vendor_id'],
                'vendor_name': v['vendor_name'],
                'current': float(v['current']),
                '1_30_days': float(v['1_30']),
                '31_60_days': float(v['31_60']),
                '61_90_days': float(v['61_90']),
                'over_90_days': float(v['over_90']),
                'total': float(v['total']),
            }
            for v in sorted(vendor_aging.values(), key=lambda x: x['total'], reverse=True)
        ],
    }


# =============================================================================
# 1099 Report
# =============================================================================

@router.get("/1099-report")
async def get_1099_report(
    request: Request,
    year: int = Query(..., description="Tax year"),
    db: Session = Depends(get_db),
):
    """Get 1099 vendor payment report for tax year."""
    org_id = get_organization_id(request)

    # Get 1099 vendors with payments in the year
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    vendors = db.query(APVendor).filter(
        APVendor.organization_id == org_id,
        APVendor.is_1099_vendor == True
    ).all()

    report = []
    threshold = Decimal("600")  # $600 1099 threshold

    for vendor in vendors:
        # Sum payments for the year
        total_payments = db.query(func.sum(APPayment.amount)).filter(
            APPayment.vendor_id == vendor.id,
            APPayment.payment_date >= start_date,
            APPayment.payment_date <= end_date,
            APPayment.status == 'completed'
        ).scalar() or Decimal("0")

        if total_payments >= threshold:
            report.append({
                'vendor_id': str(vendor.id),
                'vendor_name': vendor.vendor_name,
                'tax_id': vendor.tax_id,
                'address': {
                    'line1': vendor.address_line1,
                    'line2': vendor.address_line2,
                    'city': vendor.city,
                    'state': vendor.state,
                    'zip': vendor.zip_code,
                },
                'total_payments': float(total_payments),
                'w9_on_file': vendor.w9_on_file,
                'needs_attention': not vendor.w9_on_file or not vendor.tax_id,
            })

    return {
        "success": True,
        "tax_year": year,
        "threshold": float(threshold),
        "vendor_count": len(report),
        "total_reportable": sum(v['total_payments'] for v in report),
        "vendors": sorted(report, key=lambda x: x['total_payments'], reverse=True),
    }


# =============================================================================
# Dashboard / Summary
# =============================================================================

@router.get("/summary")
async def get_ap_summary(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get AP summary for dashboard."""
    org_id = get_organization_id(request)
    today = date.today()

    # Open balance
    open_balance = db.query(func.sum(APBill.balance_due)).filter(
        APBill.organization_id == org_id,
        APBill.status.in_(['approved', 'partial', 'overdue'])
    ).scalar() or Decimal("0")

    # Overdue balance
    overdue_balance = db.query(func.sum(APBill.balance_due)).filter(
        APBill.organization_id == org_id,
        APBill.status.in_(['approved', 'partial', 'overdue']),
        APBill.due_date < today
    ).scalar() or Decimal("0")

    # Due this week
    week_end = today + timedelta(days=7)
    due_this_week = db.query(func.sum(APBill.balance_due)).filter(
        APBill.organization_id == org_id,
        APBill.status.in_(['approved', 'partial']),
        APBill.due_date >= today,
        APBill.due_date <= week_end
    ).scalar() or Decimal("0")

    # Pending approval count
    pending_approval = db.query(func.count(APBill.id)).filter(
        APBill.organization_id == org_id,
        APBill.status == 'pending_approval'
    ).scalar() or 0

    # Payments this month
    first_of_month = today.replace(day=1)
    payments_this_month = db.query(func.sum(APPayment.amount)).filter(
        APPayment.organization_id == org_id,
        APPayment.payment_date >= first_of_month
    ).scalar() or Decimal("0")

    # Vendor count
    vendor_count = db.query(func.count(APVendor.id)).filter(
        APVendor.organization_id == org_id,
        APVendor.is_active == True
    ).scalar() or 0

    return {
        "success": True,
        "summary": {
            "open_balance": float(open_balance),
            "overdue_balance": float(overdue_balance),
            "overdue_percent": round((float(overdue_balance) / float(open_balance) * 100), 1) if open_balance > 0 else 0,
            "due_this_week": float(due_this_week),
            "pending_approval_count": pending_approval,
            "payments_this_month": float(payments_this_month),
            "active_vendors": vendor_count,
        },
    }
