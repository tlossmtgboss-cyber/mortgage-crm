"""
Journal Entry API Routes.

Provides CRUD operations for managing journal entries,
posting, voiding, and reversing entries.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
import uuid

from database import get_db
from models.accounting.core import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    AccountingPeriod, AccountingSettings, AccountingAuditLog
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
    prefix="/api/v1/accounting/journal-entries", tags=["Journal Entries"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# Dependency Injection
# =============================================================================

_get_current_user = None


def set_dependencies(get_current_user_func=None):
    """Set dependencies from main.py."""
    global _get_current_user
    _get_current_user = get_current_user_func


def get_current_user():
    """Get current user dependency."""
    if _get_current_user is None:
        return None
    return _get_current_user


# =============================================================================
# Pydantic Schemas
# =============================================================================

class JournalEntryLineCreate(BaseModel):
    account_id: str
    description: Optional[str] = None
    debit_amount: float = 0
    credit_amount: float = 0
    department_id: Optional[str] = None
    project_id: Optional[str] = None
    loan_id: Optional[str] = None
    customer_id: Optional[str] = None
    vendor_id: Optional[str] = None

    @field_validator('debit_amount', 'credit_amount')
    @classmethod
    def validate_amounts(cls, v):
        if v < 0:
            raise ValueError('Amount cannot be negative')
        return v


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: str = Field(..., min_length=1, max_length=500)
    entry_type: str = "standard"
    reference_number: Optional[str] = None
    memo: Optional[str] = None
    lines: List[JournalEntryLineCreate] = Field(..., min_length=2)

    @field_validator('lines')
    @classmethod
    def validate_lines(cls, v):
        if len(v) < 2:
            raise ValueError('Journal entry must have at least 2 lines')

        total_debits = sum(line.debit_amount for line in v)
        total_credits = sum(line.credit_amount for line in v)

        if abs(total_debits - total_credits) > 0.01:
            raise ValueError(f'Journal entry must balance. Debits: {total_debits}, Credits: {total_credits}')

        for line in v:
            if line.debit_amount == 0 and line.credit_amount == 0:
                raise ValueError('Each line must have either a debit or credit amount')
            if line.debit_amount > 0 and line.credit_amount > 0:
                raise ValueError('A line cannot have both debit and credit amounts')

        return v


class JournalEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    description: Optional[str] = None
    reference_number: Optional[str] = None
    memo: Optional[str] = None
    lines: Optional[List[JournalEntryLineCreate]] = None


class PostEntryRequest(BaseModel):
    confirm: bool = True


class VoidEntryRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ReverseEntryRequest(BaseModel):
    reversal_date: date
    description: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def get_organization_id(request: Request) -> int:
    """Get organization ID from tenant context middleware."""
    org_id = getattr(request.state, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def get_user_id(current_user=None) -> int:
    """Get user ID from current user or default."""
    if current_user and hasattr(current_user, 'id') and current_user.id:
        return current_user.id
    return 1


def get_next_entry_number(db: Session, org_id: int) -> str:
    """Generate the next journal entry number."""
    settings = db.query(AccountingSettings).filter(
        AccountingSettings.organization_id == org_id
    ).first()

    prefix = settings.journal_prefix if settings else "JE-"
    next_num = settings.journal_next_number if settings else 1001

    entry_number = f"{prefix}{next_num:06d}"

    # Update settings
    if settings:
        settings.journal_next_number = next_num + 1

    return entry_number


def get_period_for_date(db: Session, org_id: int, entry_date: date) -> Optional[AccountingPeriod]:
    """Get the accounting period for a given date."""
    return db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id,
        AccountingPeriod.start_date <= entry_date,
        AccountingPeriod.end_date >= entry_date
    ).first()


def check_period_open(db: Session, org_id: int, entry_date: date):
    """Check if the period for a date is open for posting."""
    period = get_period_for_date(db, org_id, entry_date)

    if period and period.status in ('closed', 'locked'):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot post to {period.status} period: {period.period_name}"
        )

    # Check lock date
    settings = db.query(AccountingSettings).filter(
        AccountingSettings.organization_id == org_id
    ).first()

    if settings and settings.lock_date and entry_date <= settings.lock_date:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot post entries on or before lock date: {settings.lock_date}"
        )


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


# =============================================================================
# Routes
# =============================================================================

@router.get("")
async def list_journal_entries(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    entry_type: Optional[str] = Query(None, description="Filter by entry type"),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    search: Optional[str] = Query(None, description="Search description or number"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List journal entries with filters."""
    org_id = get_organization_id(request)

    query = db.query(JournalEntry).filter(
        JournalEntry.organization_id == org_id
    )

    if status:
        query = query.filter(JournalEntry.status == status)

    if entry_type:
        query = query.filter(JournalEntry.entry_type == entry_type)

    if start_date:
        query = query.filter(JournalEntry.entry_date >= start_date)

    if end_date:
        query = query.filter(JournalEntry.entry_date <= end_date)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (JournalEntry.description.ilike(search_pattern)) |
            (JournalEntry.entry_number.ilike(search_pattern)) |
            (JournalEntry.reference_number.ilike(search_pattern))
        )

    total = query.count()
    entries = query.order_by(
        JournalEntry.entry_date.desc(),
        JournalEntry.entry_number.desc()
    ).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "entries": [entry.to_dict() for entry in entries],
    }


@router.get("/{entry_id}")
async def get_journal_entry(
    request: Request,
    entry_id: str,
    db: Session = Depends(get_db),
):
    """Get a single journal entry with lines."""
    org_id = get_organization_id(request)

    entry = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.organization_id == org_id
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    return {
        "success": True,
        "entry": entry.to_dict(include_lines=True),
    }


@router.post("")
async def create_journal_entry(
    request: Request,
    data: JournalEntryCreate,
    auto_post: bool = Query(False, description="Automatically post the entry"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new journal entry."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    # Generate entry number
    entry_number = get_next_entry_number(db, org_id)

    # Get period
    period = get_period_for_date(db, org_id, data.entry_date)

    # Create entry
    entry = JournalEntry(
        organization_id=org_id,
        entry_number=entry_number,
        entry_date=data.entry_date,
        period_id=period.id if period else None,
        description=data.description,
        entry_type=data.entry_type,
        reference_number=data.reference_number,
        memo=data.memo,
        status='draft',
        created_by=user_id,
    )

    db.add(entry)
    db.flush()

    # Create lines
    total_debits = Decimal('0')
    total_credits = Decimal('0')

    for i, line_data in enumerate(data.lines):
        # Validate account exists
        account = db.query(ChartOfAccounts).filter(
            ChartOfAccounts.id == line_data.account_id,
            ChartOfAccounts.organization_id == org_id
        ).first()

        if not account:
            raise HTTPException(status_code=400, detail=f"Account {line_data.account_id} not found")

        if not account.is_active:
            raise HTTPException(status_code=400, detail=f"Account {account.account_number} is inactive")

        line = JournalEntryLine(
            journal_entry_id=entry.id,
            account_id=uuid.UUID(line_data.account_id),
            description=line_data.description,
            debit_amount=Decimal(str(line_data.debit_amount)),
            credit_amount=Decimal(str(line_data.credit_amount)),
            department_id=uuid.UUID(line_data.department_id) if line_data.department_id else None,
            project_id=uuid.UUID(line_data.project_id) if line_data.project_id else None,
            loan_id=uuid.UUID(line_data.loan_id) if line_data.loan_id else None,
            customer_id=uuid.UUID(line_data.customer_id) if line_data.customer_id else None,
            vendor_id=uuid.UUID(line_data.vendor_id) if line_data.vendor_id else None,
            line_order=i,
        )
        db.add(line)

        total_debits += Decimal(str(line_data.debit_amount))
        total_credits += Decimal(str(line_data.credit_amount))

    entry.total_debits = total_debits
    entry.total_credits = total_credits

    # Log audit
    log_audit(
        db, org_id, user_id, 'create', 'journal_entry', entry.id,
        entity_number=entry.entry_number,
        summary=f"Created journal entry {entry.entry_number}"
    )

    # Auto-post if requested
    if auto_post:
        check_period_open(db, org_id, data.entry_date)
        entry.status = 'posted'
        entry.posted_at = datetime.utcnow()
        entry.posted_by = user_id

        log_audit(
            db, org_id, user_id, 'post', 'journal_entry', entry.id,
            entity_number=entry.entry_number,
            summary=f"Posted journal entry {entry.entry_number}"
        )

    db.commit()

    return {
        "success": True,
        "message": f"Journal entry {entry.entry_number} created" + (" and posted" if auto_post else ""),
        "entry": entry.to_dict(include_lines=True),
    }


@router.put("/{entry_id}")
async def update_journal_entry(
    request: Request,
    entry_id: str,
    data: JournalEntryUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a draft journal entry."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    entry = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.organization_id == org_id
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    if entry.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only update draft entries")

    old_values = entry.to_dict()

    # Update fields
    if data.entry_date is not None:
        entry.entry_date = data.entry_date
        period = get_period_for_date(db, org_id, data.entry_date)
        entry.period_id = period.id if period else None

    if data.description is not None:
        entry.description = data.description

    if data.reference_number is not None:
        entry.reference_number = data.reference_number

    if data.memo is not None:
        entry.memo = data.memo

    # Update lines if provided
    if data.lines is not None:
        # Delete existing lines
        db.query(JournalEntryLine).filter(
            JournalEntryLine.journal_entry_id == entry.id
        ).delete()

        # Create new lines
        total_debits = Decimal('0')
        total_credits = Decimal('0')

        for i, line_data in enumerate(data.lines):
            line = JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=uuid.UUID(line_data.account_id),
                description=line_data.description,
                debit_amount=Decimal(str(line_data.debit_amount)),
                credit_amount=Decimal(str(line_data.credit_amount)),
                line_order=i,
            )
            db.add(line)

            total_debits += Decimal(str(line_data.debit_amount))
            total_credits += Decimal(str(line_data.credit_amount))

        entry.total_debits = total_debits
        entry.total_credits = total_credits

    log_audit(
        db, org_id, user_id, 'update', 'journal_entry', entry.id,
        entity_number=entry.entry_number,
        old_values=old_values,
        summary=f"Updated journal entry {entry.entry_number}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Journal entry {entry.entry_number} updated",
        "entry": entry.to_dict(include_lines=True),
    }


@router.post("/{entry_id}/post")
async def post_journal_entry(
    request: Request,
    entry_id: str,
    data: PostEntryRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Post a draft journal entry."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    entry = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.organization_id == org_id
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    if entry.status != 'draft':
        raise HTTPException(status_code=400, detail=f"Entry is already {entry.status}")

    # Validate entry is balanced
    if entry.total_debits != entry.total_credits:
        raise HTTPException(status_code=400, detail="Entry is not balanced")

    # Check period is open
    check_period_open(db, org_id, entry.entry_date)

    # Post the entry
    entry.status = 'posted'
    entry.posted_at = datetime.utcnow()
    entry.posted_by = user_id

    log_audit(
        db, org_id, user_id, 'post', 'journal_entry', entry.id,
        entity_number=entry.entry_number,
        summary=f"Posted journal entry {entry.entry_number}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Journal entry {entry.entry_number} posted",
        "entry": entry.to_dict(),
    }


@router.post("/{entry_id}/void")
async def void_journal_entry(
    request: Request,
    entry_id: str,
    data: VoidEntryRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Void a posted journal entry."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    entry = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.organization_id == org_id
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    if entry.status == 'void':
        raise HTTPException(status_code=400, detail="Entry is already void")

    if entry.status == 'draft':
        # Just delete draft entries
        db.delete(entry)
        db.commit()
        return {"success": True, "message": "Draft entry deleted"}

    # Check period is open
    check_period_open(db, org_id, entry.entry_date)

    # Void the entry
    entry.status = 'void'
    entry.voided_at = datetime.utcnow()
    entry.voided_by = user_id
    entry.void_reason = data.reason

    log_audit(
        db, org_id, user_id, 'void', 'journal_entry', entry.id,
        entity_number=entry.entry_number,
        new_values={'void_reason': data.reason},
        summary=f"Voided journal entry {entry.entry_number}: {data.reason}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Journal entry {entry.entry_number} voided",
        "entry": entry.to_dict(),
    }


@router.post("/{entry_id}/reverse")
async def reverse_journal_entry(
    request: Request,
    entry_id: str,
    data: ReverseEntryRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a reversing entry for a posted journal entry."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    original = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.organization_id == org_id
    ).first()

    if not original:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    if original.status != 'posted':
        raise HTTPException(status_code=400, detail="Can only reverse posted entries")

    if original.reversed_by_entry_id:
        raise HTTPException(status_code=400, detail="Entry has already been reversed")

    # Check period is open
    check_period_open(db, org_id, data.reversal_date)

    # Generate new entry number
    entry_number = get_next_entry_number(db, org_id)
    period = get_period_for_date(db, org_id, data.reversal_date)

    # Create reversing entry
    description = data.description or f"Reversal of {original.entry_number}: {original.description}"

    reversing = JournalEntry(
        organization_id=org_id,
        entry_number=entry_number,
        entry_date=data.reversal_date,
        period_id=period.id if period else None,
        description=description,
        entry_type='reversing',
        reverses_entry_id=original.id,
        status='posted',
        posted_at=datetime.utcnow(),
        posted_by=user_id,
        total_debits=original.total_credits,  # Swap
        total_credits=original.total_debits,
        created_by=user_id,
    )

    db.add(reversing)
    db.flush()

    # Create reversed lines
    for i, orig_line in enumerate(original.lines):
        line = JournalEntryLine(
            journal_entry_id=reversing.id,
            account_id=orig_line.account_id,
            description=f"Reversal: {orig_line.description or ''}",
            debit_amount=orig_line.credit_amount,  # Swap
            credit_amount=orig_line.debit_amount,
            department_id=orig_line.department_id,
            project_id=orig_line.project_id,
            loan_id=orig_line.loan_id,
            customer_id=orig_line.customer_id,
            vendor_id=orig_line.vendor_id,
            line_order=i,
        )
        db.add(line)

    # Link original to reversing
    original.reversed_by_entry_id = reversing.id

    log_audit(
        db, org_id, user_id, 'reverse', 'journal_entry', original.id,
        entity_number=original.entry_number,
        new_values={'reversed_by': entry_number},
        summary=f"Reversed {original.entry_number} with {entry_number}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Created reversing entry {entry_number}",
        "original_entry": original.to_dict(),
        "reversing_entry": reversing.to_dict(include_lines=True),
    }


@router.get("/summary/trial-balance")
async def get_trial_balance(
    request: Request,
    as_of_date: Optional[date] = Query(None, description="Trial balance as of date"),
    db: Session = Depends(get_db),
):
    """Generate trial balance report."""
    org_id = get_organization_id(request)
    as_of = as_of_date or date.today()

    # Get all active accounts with their balances
    accounts = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.is_active == True
    ).order_by(ChartOfAccounts.account_number).all()

    trial_balance = []
    total_debits = Decimal('0')
    total_credits = Decimal('0')

    for account in accounts:
        # Get sum of debits and credits for this account
        result = db.query(
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('debits'),
            func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('credits')
        ).join(
            JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id
        ).filter(
            JournalEntryLine.account_id == account.id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date <= as_of
        ).first()

        debits = Decimal(str(result.debits or 0)) + Decimal(str(account.opening_balance or 0) if account.normal_balance == 'debit' else 0)
        credits = Decimal(str(result.credits or 0)) + Decimal(str(account.opening_balance or 0) if account.normal_balance == 'credit' else 0)

        if debits != 0 or credits != 0:
            # Calculate ending balance
            if account.normal_balance == 'debit':
                balance = debits - credits
                debit_balance = balance if balance > 0 else Decimal('0')
                credit_balance = abs(balance) if balance < 0 else Decimal('0')
            else:
                balance = credits - debits
                credit_balance = balance if balance > 0 else Decimal('0')
                debit_balance = abs(balance) if balance < 0 else Decimal('0')

            total_debits += debit_balance
            total_credits += credit_balance

            trial_balance.append({
                'account_number': account.account_number,
                'account_name': account.name,
                'account_type': account.account_type,
                'debit_balance': float(debit_balance),
                'credit_balance': float(credit_balance),
            })

    return {
        "success": True,
        "as_of_date": as_of.isoformat(),
        "accounts": trial_balance,
        "total_debits": float(total_debits),
        "total_credits": float(total_credits),
        "is_balanced": abs(total_debits - total_credits) < Decimal('0.01'),
    }
