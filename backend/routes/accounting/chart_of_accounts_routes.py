"""
Chart of Accounts API Routes.

Provides CRUD operations for managing the chart of accounts,
account balances, and account hierarchies.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import Optional, List
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field
import uuid

from database import get_db
from models.accounting.core import ChartOfAccounts, JournalEntryLine, JournalEntry, AccountingSettings, AccountingAuditLog

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
    prefix="/api/v1/accounting/accounts", tags=["Chart of Accounts"],
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
        # Return a default that will use fallback values
        return None
    return _get_current_user


# =============================================================================
# Pydantic Schemas
# =============================================================================

class AccountCreate(BaseModel):
    account_number: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    account_type: str = Field(..., pattern="^(asset|liability|equity|revenue|expense)$")
    account_subtype: Optional[str] = None
    parent_account_id: Optional[str] = None
    normal_balance: str = Field(..., pattern="^(debit|credit)$")
    is_bank_account: bool = False
    currency: str = "USD"
    tax_code: Optional[str] = None
    display_order: Optional[int] = None
    opening_balance: Optional[float] = 0
    opening_balance_date: Optional[date] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    account_subtype: Optional[str] = None
    parent_account_id: Optional[str] = None
    is_bank_account: Optional[bool] = None
    tax_code: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class AccountResponse(BaseModel):
    id: str
    account_number: str
    name: str
    description: Optional[str]
    account_type: str
    account_subtype: Optional[str]
    parent_account_id: Optional[str]
    normal_balance: str
    is_bank_account: bool
    is_active: bool
    is_system_account: bool
    currency: str
    display_order: Optional[int]
    current_balance: Optional[float] = None

    class Config:
        from_attributes = True


class AccountTreeNode(BaseModel):
    id: str
    account_number: str
    name: str
    account_type: str
    normal_balance: str
    is_active: bool
    balance: float = 0
    children: List['AccountTreeNode'] = []


AccountTreeNode.model_rebuild()


# =============================================================================
# Helper Functions
# =============================================================================

def get_organization_id(current_user=None) -> int:
    """Get organization ID from current user. Raises if not authenticated."""
    if current_user and hasattr(current_user, 'organization_id') and current_user.organization_id:
        return current_user.organization_id
    raise HTTPException(status_code=401, detail="Authentication required - organization context missing")


def get_user_id(current_user=None) -> int:
    """Get user ID from current user. Raises if not authenticated."""
    if current_user and hasattr(current_user, 'id') and current_user.id:
        return current_user.id
    raise HTTPException(status_code=401, detail="Authentication required - user context missing")


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


def calculate_account_balance(db: Session, account_id: uuid.UUID, as_of_date: date = None) -> Decimal:
    """Calculate the current balance for an account."""
    query = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('total_debits'),
        func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('total_credits')
    ).join(
        JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id
    ).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.status == 'posted'
    )

    if as_of_date:
        query = query.filter(JournalEntry.entry_date <= as_of_date)

    result = query.first()

    # Get account to determine normal balance
    account = db.query(ChartOfAccounts).filter(ChartOfAccounts.id == account_id).first()
    if not account:
        return Decimal('0')

    debits = Decimal(str(result.total_debits or 0))
    credits = Decimal(str(result.total_credits or 0))

    # Add opening balance
    opening = Decimal(str(account.opening_balance or 0))

    # Calculate balance based on normal balance type
    if account.normal_balance == 'debit':
        balance = opening + debits - credits
    else:
        balance = opening + credits - debits

    return balance


# =============================================================================
# Routes
# =============================================================================

@router.get("")
async def list_accounts(
    account_type: Optional[str] = Query(None, description="Filter by account type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name or number"),
    include_balance: bool = Query(False, description="Include current balance"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """List all accounts with optional filters."""
    org_id = get_organization_id(current_user)

    query = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id
    )

    if account_type:
        query = query.filter(ChartOfAccounts.account_type == account_type)

    if is_active is not None:
        query = query.filter(ChartOfAccounts.is_active == is_active)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                ChartOfAccounts.name.ilike(search_pattern),
                ChartOfAccounts.account_number.ilike(search_pattern)
            )
        )

    total = query.count()
    accounts = query.order_by(
        ChartOfAccounts.display_order.nulls_last(),
        ChartOfAccounts.account_number
    ).offset(skip).limit(limit).all()

    result = []
    for account in accounts:
        account_dict = account.to_dict()
        if include_balance:
            account_dict['current_balance'] = float(calculate_account_balance(db, account.id))
        result.append(account_dict)

    return {
        "success": True,
        "total": total,
        "accounts": result,
    }


@router.get("/tree")
async def get_account_tree(
    account_type: Optional[str] = Query(None, description="Filter by account type"),
    include_balance: bool = Query(True, description="Include balances"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get hierarchical account tree structure."""
    org_id = get_organization_id(current_user)

    query = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.is_active == True
    )

    if account_type:
        query = query.filter(ChartOfAccounts.account_type == account_type)

    accounts = query.order_by(ChartOfAccounts.display_order.nulls_last(), ChartOfAccounts.account_number).all()

    # Build tree structure
    account_map = {}
    root_accounts = []

    for account in accounts:
        balance = float(calculate_account_balance(db, account.id)) if include_balance else 0
        node = {
            'id': str(account.id),
            'account_number': account.account_number,
            'name': account.name,
            'account_type': account.account_type,
            'normal_balance': account.normal_balance,
            'is_active': account.is_active,
            'balance': balance,
            'children': [],
        }
        account_map[str(account.id)] = node

    for account in accounts:
        node = account_map[str(account.id)]
        if account.parent_account_id and str(account.parent_account_id) in account_map:
            account_map[str(account.parent_account_id)]['children'].append(node)
        else:
            root_accounts.append(node)

    # Group by account type
    grouped = {
        'asset': [],
        'liability': [],
        'equity': [],
        'revenue': [],
        'expense': [],
    }

    for node in root_accounts:
        if node['account_type'] in grouped:
            grouped[node['account_type']].append(node)

    return {
        "success": True,
        "tree": grouped if not account_type else root_accounts,
    }


@router.get("/{account_id}")
async def get_account(
    account_id: str,
    include_balance: bool = Query(True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a single account by ID."""
    org_id = get_organization_id(current_user)

    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id,
        ChartOfAccounts.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    result = account.to_dict()
    if include_balance:
        result['current_balance'] = float(calculate_account_balance(db, account.id))

    return {
        "success": True,
        "account": result,
    }


@router.post("")
async def create_account(
    data: AccountCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new account."""
    org_id = get_organization_id(current_user)
    user_id = get_user_id(current_user)

    # Check for duplicate account number
    existing = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.account_number == data.account_number
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail=f"Account number {data.account_number} already exists")

    # Validate parent account if provided
    if data.parent_account_id:
        parent = db.query(ChartOfAccounts).filter(
            ChartOfAccounts.id == data.parent_account_id,
            ChartOfAccounts.organization_id == org_id
        ).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent account not found")
        if parent.account_type != data.account_type:
            raise HTTPException(status_code=400, detail="Parent account must be of the same type")

    account = ChartOfAccounts(
        organization_id=org_id,
        account_number=data.account_number,
        name=data.name,
        description=data.description,
        account_type=data.account_type,
        account_subtype=data.account_subtype,
        parent_account_id=uuid.UUID(data.parent_account_id) if data.parent_account_id else None,
        normal_balance=data.normal_balance,
        is_bank_account=data.is_bank_account,
        currency=data.currency,
        tax_code=data.tax_code,
        display_order=data.display_order,
        opening_balance=Decimal(str(data.opening_balance or 0)),
        opening_balance_date=data.opening_balance_date,
        created_by=user_id,
    )

    db.add(account)
    db.flush()

    # Log audit
    log_audit(
        db, org_id, user_id, 'create', 'chart_of_accounts', account.id,
        entity_number=account.account_number,
        new_values=data.model_dump(),
        summary=f"Created account {account.account_number} - {account.name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Account {account.account_number} created successfully",
        "account": account.to_dict(),
    }


@router.put("/{account_id}")
async def update_account(
    account_id: str,
    data: AccountUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update an existing account."""
    org_id = get_organization_id(current_user)

    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id,
        ChartOfAccounts.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.is_system_account:
        raise HTTPException(status_code=400, detail="Cannot modify system accounts")

    old_values = account.to_dict()

    # Update fields
    update_fields = data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for field, value in update_fields.items():
        if field in _protected:
            continue
        if field == 'parent_account_id' and value:
            value = uuid.UUID(value)
        setattr(account, field, value)

    # Log audit
    user_id = get_user_id(current_user)
    log_audit(
        db, org_id, user_id, 'update', 'chart_of_accounts', account.id,
        entity_number=account.account_number,
        old_values=old_values,
        new_values=update_fields,
        summary=f"Updated account {account.account_number}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Account {account.account_number} updated successfully",
        "account": account.to_dict(),
    }


@router.delete("/{account_id}")
async def deactivate_account(
    account_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Deactivate an account (soft delete)."""
    org_id = get_organization_id(current_user)

    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id,
        ChartOfAccounts.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.is_system_account:
        raise HTTPException(status_code=400, detail="Cannot deactivate system accounts")

    # Check if account has any posted transactions
    has_transactions = db.query(JournalEntryLine).join(JournalEntry).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.status == 'posted'
    ).first()

    user_id = get_user_id(current_user)

    if has_transactions:
        # Just deactivate, don't delete
        account.is_active = False
        log_audit(
            db, org_id, user_id, 'update', 'chart_of_accounts', account.id,
            entity_number=account.account_number,
            new_values={'is_active': False},
            summary=f"Deactivated account {account.account_number}"
        )
    else:
        # Can delete if no transactions
        db.delete(account)
        log_audit(
            db, org_id, user_id, 'delete', 'chart_of_accounts', account.id,
            entity_number=account.account_number,
            summary=f"Deleted account {account.account_number}"
        )

    db.commit()

    return {
        "success": True,
        "message": f"Account {account.account_number} {'deactivated' if has_transactions else 'deleted'} successfully",
    }


@router.get("/{account_id}/balance")
async def get_account_balance(
    account_id: str,
    as_of_date: Optional[date] = Query(None, description="Balance as of date"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get account balance, optionally as of a specific date."""
    org_id = get_organization_id(current_user)

    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id,
        ChartOfAccounts.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    balance = calculate_account_balance(db, account.id, as_of_date)

    return {
        "success": True,
        "account_id": str(account.id),
        "account_number": account.account_number,
        "account_name": account.name,
        "balance": float(balance),
        "as_of_date": as_of_date.isoformat() if as_of_date else date.today().isoformat(),
        "normal_balance": account.normal_balance,
    }


@router.get("/{account_id}/transactions")
async def get_account_transactions(
    account_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get transactions for an account."""
    org_id = get_organization_id(current_user)

    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id,
        ChartOfAccounts.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    query = db.query(JournalEntryLine, JournalEntry).join(
        JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id
    ).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.status == 'posted'
    )

    if start_date:
        query = query.filter(JournalEntry.entry_date >= start_date)
    if end_date:
        query = query.filter(JournalEntry.entry_date <= end_date)

    total = query.count()
    results = query.order_by(
        JournalEntry.entry_date.desc(),
        JournalEntry.entry_number.desc()
    ).offset(skip).limit(limit).all()

    # Calculate running balance
    transactions = []
    running_balance = float(account.opening_balance or 0)

    for line, entry in results:
        if account.normal_balance == 'debit':
            change = float(line.debit_amount or 0) - float(line.credit_amount or 0)
        else:
            change = float(line.credit_amount or 0) - float(line.debit_amount or 0)

        running_balance += change

        transactions.append({
            'id': str(line.id),
            'entry_id': str(entry.id),
            'entry_number': entry.entry_number,
            'entry_date': entry.entry_date.isoformat() if entry.entry_date else None,
            'description': line.description or entry.description,
            'debit': float(line.debit_amount or 0),
            'credit': float(line.credit_amount or 0),
            'balance': running_balance,
            'reference': entry.reference_number,
            'source_type': entry.source_type,
        })

    return {
        "success": True,
        "account_id": str(account.id),
        "account_number": account.account_number,
        "total": total,
        "transactions": transactions,
    }


@router.post("/initialize-defaults")
async def initialize_default_accounts(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Initialize default chart of accounts for an organization."""
    org_id = get_organization_id(current_user)

    # Check if accounts already exist
    existing = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Chart of accounts already initialized")

    # Call the database function to create default accounts
    db.execute(
        "SELECT create_default_chart_of_accounts(:org_id, :user_id)",
        {"org_id": org_id, "user_id": 1}
    )

    db.commit()

    return {
        "success": True,
        "message": "Default chart of accounts created successfully",
    }
