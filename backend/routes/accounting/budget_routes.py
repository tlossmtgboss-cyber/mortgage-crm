"""
Budgeting API Routes.

Provides endpoints for:
- Budget template management
- Budget line items with monthly allocations
- Budget approval workflow
- Budget vs Actual comparison
- Budget copying and rollover
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import Optional, List
from datetime import date, datetime, timezone
from decimal import Decimal
from pydantic import BaseModel, Field
import uuid
import calendar

from database import get_db
from models.accounting.core import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    AccountingPeriod, AccountingAuditLog
)
from models.accounting.budgeting import BudgetTemplate, BudgetItem

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
    prefix="/api/v1/accounting/budgets", tags=["Budgeting"],
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

class BudgetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    fiscal_year: int
    budget_type: str = Field(default="annual", pattern="^(annual|quarterly|monthly|rolling)$")
    notes: Optional[str] = None


class BudgetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None


class BudgetItemCreate(BaseModel):
    account_id: str
    department_id: Optional[str] = None
    period_1: Decimal = Field(default=Decimal("0"))
    period_2: Decimal = Field(default=Decimal("0"))
    period_3: Decimal = Field(default=Decimal("0"))
    period_4: Decimal = Field(default=Decimal("0"))
    period_5: Decimal = Field(default=Decimal("0"))
    period_6: Decimal = Field(default=Decimal("0"))
    period_7: Decimal = Field(default=Decimal("0"))
    period_8: Decimal = Field(default=Decimal("0"))
    period_9: Decimal = Field(default=Decimal("0"))
    period_10: Decimal = Field(default=Decimal("0"))
    period_11: Decimal = Field(default=Decimal("0"))
    period_12: Decimal = Field(default=Decimal("0"))
    notes: Optional[str] = None


class BudgetItemUpdate(BaseModel):
    period_1: Optional[Decimal] = None
    period_2: Optional[Decimal] = None
    period_3: Optional[Decimal] = None
    period_4: Optional[Decimal] = None
    period_5: Optional[Decimal] = None
    period_6: Optional[Decimal] = None
    period_7: Optional[Decimal] = None
    period_8: Optional[Decimal] = None
    period_9: Optional[Decimal] = None
    period_10: Optional[Decimal] = None
    period_11: Optional[Decimal] = None
    period_12: Optional[Decimal] = None
    notes: Optional[str] = None


class BudgetItemBulkCreate(BaseModel):
    items: List[BudgetItemCreate]


class DistributeAmountRequest(BaseModel):
    annual_amount: Decimal
    distribution_method: str = Field(default="even", pattern="^(even|seasonal|custom)$")
    custom_weights: Optional[List[Decimal]] = None  # 12 weights for custom distribution


class CopyBudgetRequest(BaseModel):
    source_budget_id: str
    new_name: str
    new_fiscal_year: int
    adjustment_percent: Optional[Decimal] = None  # e.g., 5 for 5% increase


class ApprovalRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None


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


def calculate_budget_totals(db: Session, budget: BudgetTemplate):
    """Recalculate budget totals from items."""
    total_revenue = Decimal("0")
    total_expenses = Decimal("0")

    for item in budget.items:
        if item.account:
            annual = item.annual_total
            if item.account.account_type == 'revenue':
                total_revenue += annual
            elif item.account.account_type in ('expense', 'cost_of_goods'):
                total_expenses += annual

    budget.total_revenue = total_revenue
    budget.total_expenses = total_expenses


def get_actual_for_account(
    db: Session,
    org_id: int,
    account_id: str,
    start_date: date,
    end_date: date,
) -> Decimal:
    """Get actual amount for an account in a date range."""
    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id
    ).first()

    if not account:
        return Decimal("0")

    result = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('debits'),
        func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('credits'),
    ).join(JournalEntry).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date >= start_date,
        JournalEntry.entry_date <= end_date,
    ).first()

    debits = Decimal(str(result.debits or 0))
    credits = Decimal(str(result.credits or 0))

    if account.account_type == 'revenue':
        return credits - debits
    else:
        return debits - credits


# =============================================================================
# Budget Template Routes
# =============================================================================

@router.get("")
async def list_budgets(
    request: Request,
    fiscal_year: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List budget templates."""
    org_id = get_organization_id(request)

    query = db.query(BudgetTemplate).filter(
        BudgetTemplate.organization_id == org_id
    )

    if fiscal_year:
        query = query.filter(BudgetTemplate.fiscal_year == fiscal_year)

    if status:
        query = query.filter(BudgetTemplate.status == status)

    total = query.count()
    budgets = query.order_by(
        BudgetTemplate.fiscal_year.desc(),
        BudgetTemplate.created_at.desc()
    ).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "budgets": [b.to_dict() for b in budgets],
    }


@router.get("/active")
async def get_active_budget(
    request: Request,
    fiscal_year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Get the active budget for a fiscal year."""
    org_id = get_organization_id(request)
    year = fiscal_year or date.today().year

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.organization_id == org_id,
        BudgetTemplate.fiscal_year == year,
        BudgetTemplate.status == 'active'
    ).first()

    if not budget:
        return {
            "success": True,
            "budget": None,
            "message": f"No active budget for fiscal year {year}",
        }

    return {
        "success": True,
        "budget": budget.to_dict(include_items=True),
    }


@router.get("/{budget_id}")
async def get_budget(
    request: Request,
    budget_id: str,
    include_items: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Get a budget template with optional items."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    return {
        "success": True,
        "budget": budget.to_dict(include_items=include_items),
    }


@router.post("")
async def create_budget(
    request: Request,
    data: BudgetCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new budget template."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    # Check for duplicate
    existing = db.query(BudgetTemplate).filter(
        BudgetTemplate.organization_id == org_id,
        BudgetTemplate.name == data.name,
        BudgetTemplate.fiscal_year == data.fiscal_year
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Budget '{data.name}' already exists for fiscal year {data.fiscal_year}"
        )

    budget = BudgetTemplate(
        organization_id=org_id,
        name=data.name,
        description=data.description,
        fiscal_year=data.fiscal_year,
        budget_type=data.budget_type,
        notes=data.notes,
        status='draft',
        created_by=user_id,
    )

    db.add(budget)
    db.flush()

    log_audit(
        db, org_id, user_id, 'create', 'budget_template', budget.id,
        entity_number=budget.name,
        summary=f"Created budget {budget.name} for FY{budget.fiscal_year}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Budget '{budget.name}' created",
        "budget": budget.to_dict(),
    }


@router.put("/{budget_id}")
async def update_budget(
    request: Request,
    budget_id: str,
    data: BudgetUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a budget template."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status in ('approved', 'active', 'closed'):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot modify budget with status '{budget.status}'"
        )

    old_values = budget.to_dict()

    update_data = data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for key, value in update_data.items():
        if key not in _protected:
            setattr(budget, key, value)

    log_audit(
        db, org_id, user_id, 'update', 'budget_template', budget.id,
        entity_number=budget.name,
        old_values=old_values,
        summary=f"Updated budget {budget.name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Budget '{budget.name}' updated",
        "budget": budget.to_dict(),
    }


@router.post("/{budget_id}/submit")
async def submit_budget_for_approval(
    request: Request,
    budget_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Submit a budget for approval."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status != 'draft':
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit budget with status '{budget.status}'"
        )

    # Validate budget has items
    if not budget.items:
        raise HTTPException(status_code=400, detail="Budget must have at least one line item")

    # Recalculate totals
    calculate_budget_totals(db, budget)

    budget.status = 'pending_approval'

    log_audit(
        db, org_id, user_id, 'submit', 'budget_template', budget.id,
        entity_number=budget.name,
        summary=f"Submitted budget {budget.name} for approval"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Budget '{budget.name}' submitted for approval",
        "budget": budget.to_dict(),
    }


@router.post("/{budget_id}/approve")
async def approve_budget(
    request: Request,
    budget_id: str,
    data: ApprovalRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Approve or reject a budget."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status != 'pending_approval':
        raise HTTPException(
            status_code=400,
            detail=f"Budget is not pending approval"
        )

    if data.approved:
        budget.status = 'approved'
        budget.approved_at = datetime.now(timezone.utc)
        budget.approved_by = user_id

        if data.notes:
            budget.notes = (budget.notes or '') + f"\nApproval: {data.notes}"

        action = 'approve'
        message = f"Budget '{budget.name}' approved"
    else:
        budget.status = 'draft'  # Return to draft for revisions

        if data.notes:
            budget.notes = (budget.notes or '') + f"\nRejected: {data.notes}"

        action = 'reject'
        message = f"Budget '{budget.name}' rejected - returned to draft"

    log_audit(
        db, org_id, user_id, action, 'budget_template', budget.id,
        entity_number=budget.name,
        summary=message
    )

    db.commit()

    return {
        "success": True,
        "message": message,
        "budget": budget.to_dict(),
    }


@router.post("/{budget_id}/activate")
async def activate_budget(
    request: Request,
    budget_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Activate an approved budget (makes it the active budget for the year)."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status != 'approved':
        raise HTTPException(
            status_code=400,
            detail="Only approved budgets can be activated"
        )

    # Deactivate any existing active budget for this year
    db.query(BudgetTemplate).filter(
        BudgetTemplate.organization_id == org_id,
        BudgetTemplate.fiscal_year == budget.fiscal_year,
        BudgetTemplate.status == 'active'
    ).update({'status': 'closed'})

    budget.status = 'active'
    budget.activated_at = datetime.now(timezone.utc)

    log_audit(
        db, org_id, user_id, 'activate', 'budget_template', budget.id,
        entity_number=budget.name,
        summary=f"Activated budget {budget.name} for FY{budget.fiscal_year}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Budget '{budget.name}' is now active for FY{budget.fiscal_year}",
        "budget": budget.to_dict(),
    }


@router.post("/{budget_id}/close")
async def close_budget(
    request: Request,
    budget_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Close a budget (end of year or replaced by new budget)."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status == 'closed':
        raise HTTPException(status_code=400, detail="Budget is already closed")

    budget.status = 'closed'

    log_audit(
        db, org_id, user_id, 'close', 'budget_template', budget.id,
        entity_number=budget.name,
        summary=f"Closed budget {budget.name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Budget '{budget.name}' closed",
        "budget": budget.to_dict(),
    }


@router.delete("/{budget_id}")
async def delete_budget(
    request: Request,
    budget_id: str,
    db: Session = Depends(get_db),
):
    """Delete a draft budget."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status != 'draft':
        raise HTTPException(
            status_code=400,
            detail="Only draft budgets can be deleted"
        )

    db.delete(budget)
    db.commit()

    return {
        "success": True,
        "message": f"Budget '{budget.name}' deleted",
    }


# =============================================================================
# Budget Item Routes
# =============================================================================

@router.get("/{budget_id}/items")
async def list_budget_items(
    request: Request,
    budget_id: str,
    account_type: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List budget items for a budget."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    query = db.query(BudgetItem).filter(
        BudgetItem.budget_id == budget_id
    )

    if department_id:
        query = query.filter(BudgetItem.department_id == department_id)

    items = query.all()

    # Filter by account type if requested
    if account_type:
        items = [i for i in items if i.account and i.account.account_type == account_type]

    # Group by account type
    revenue_items = [i.to_dict() for i in items if i.account and i.account.account_type == 'revenue']
    expense_items = [i.to_dict() for i in items if i.account and i.account.account_type in ('expense', 'cost_of_goods')]

    return {
        "success": True,
        "budget_id": budget_id,
        "revenue_items": revenue_items,
        "expense_items": expense_items,
        "total_revenue": sum(i['annual_total'] for i in revenue_items),
        "total_expenses": sum(i['annual_total'] for i in expense_items),
    }


@router.post("/{budget_id}/items")
async def create_budget_item(
    request: Request,
    budget_id: str,
    data: BudgetItemCreate,
    db: Session = Depends(get_db),
):
    """Create a budget line item."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status not in ('draft', 'pending_approval'):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add items to budget with status '{budget.status}'"
        )

    # Validate account
    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == data.account_id,
        ChartOfAccounts.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Check for duplicate
    existing = db.query(BudgetItem).filter(
        BudgetItem.budget_id == budget_id,
        BudgetItem.account_id == data.account_id,
        BudgetItem.department_id == data.department_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Budget item already exists for this account/department"
        )

    item = BudgetItem(
        budget_id=budget_id,
        account_id=data.account_id,
        department_id=data.department_id,
        period_1=data.period_1,
        period_2=data.period_2,
        period_3=data.period_3,
        period_4=data.period_4,
        period_5=data.period_5,
        period_6=data.period_6,
        period_7=data.period_7,
        period_8=data.period_8,
        period_9=data.period_9,
        period_10=data.period_10,
        period_11=data.period_11,
        period_12=data.period_12,
        notes=data.notes,
    )

    db.add(item)

    # Recalculate budget totals
    calculate_budget_totals(db, budget)

    db.commit()

    return {
        "success": True,
        "message": f"Budget item created for {account.name}",
        "item": item.to_dict(),
    }


@router.post("/{budget_id}/items/bulk")
async def create_budget_items_bulk(
    request: Request,
    budget_id: str,
    data: BudgetItemBulkCreate,
    db: Session = Depends(get_db),
):
    """Create multiple budget items at once."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status not in ('draft', 'pending_approval'):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add items to budget with status '{budget.status}'"
        )

    created = []
    errors = []

    for item_data in data.items:
        # Validate account
        account = db.query(ChartOfAccounts).filter(
            ChartOfAccounts.id == item_data.account_id,
            ChartOfAccounts.organization_id == org_id
        ).first()

        if not account:
            errors.append(f"Account {item_data.account_id} not found")
            continue

        # Check for duplicate
        existing = db.query(BudgetItem).filter(
            BudgetItem.budget_id == budget_id,
            BudgetItem.account_id == item_data.account_id,
            BudgetItem.department_id == item_data.department_id
        ).first()

        if existing:
            # Update existing instead
            existing.period_1 = item_data.period_1
            existing.period_2 = item_data.period_2
            existing.period_3 = item_data.period_3
            existing.period_4 = item_data.period_4
            existing.period_5 = item_data.period_5
            existing.period_6 = item_data.period_6
            existing.period_7 = item_data.period_7
            existing.period_8 = item_data.period_8
            existing.period_9 = item_data.period_9
            existing.period_10 = item_data.period_10
            existing.period_11 = item_data.period_11
            existing.period_12 = item_data.period_12
            existing.notes = item_data.notes
            created.append(existing)
        else:
            item = BudgetItem(
                budget_id=budget_id,
                **item_data.model_dump()
            )
            db.add(item)
            created.append(item)

    # Recalculate budget totals
    calculate_budget_totals(db, budget)

    db.commit()

    return {
        "success": True,
        "message": f"Created/updated {len(created)} budget items",
        "created_count": len(created),
        "errors": errors,
    }


@router.put("/{budget_id}/items/{item_id}")
async def update_budget_item(
    request: Request,
    budget_id: str,
    item_id: str,
    data: BudgetItemUpdate,
    db: Session = Depends(get_db),
):
    """Update a budget item."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status not in ('draft', 'pending_approval'):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot modify items in budget with status '{budget.status}'"
        )

    item = db.query(BudgetItem).filter(
        BudgetItem.id == item_id,
        BudgetItem.budget_id == budget_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Budget item not found")

    update_data = data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for key, value in update_data.items():
        if key not in _protected:
            setattr(item, key, value)

    # Recalculate budget totals
    calculate_budget_totals(db, budget)

    db.commit()

    return {
        "success": True,
        "message": "Budget item updated",
        "item": item.to_dict(),
    }


@router.post("/{budget_id}/items/{item_id}/distribute")
async def distribute_amount(
    request: Request,
    budget_id: str,
    item_id: str,
    data: DistributeAmountRequest,
    db: Session = Depends(get_db),
):
    """Distribute an annual amount across periods."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status not in ('draft', 'pending_approval'):
        raise HTTPException(status_code=400, detail="Cannot modify this budget")

    item = db.query(BudgetItem).filter(
        BudgetItem.id == item_id,
        BudgetItem.budget_id == budget_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Budget item not found")

    if data.distribution_method == "even":
        item.distribute_evenly(data.annual_amount)

    elif data.distribution_method == "seasonal":
        # Default seasonal weights (higher in spring/summer for mortgage business)
        weights = [
            Decimal("0.07"),  # Jan
            Decimal("0.07"),  # Feb
            Decimal("0.08"),  # Mar
            Decimal("0.09"),  # Apr
            Decimal("0.10"),  # May
            Decimal("0.10"),  # Jun
            Decimal("0.10"),  # Jul
            Decimal("0.09"),  # Aug
            Decimal("0.08"),  # Sep
            Decimal("0.08"),  # Oct
            Decimal("0.07"),  # Nov
            Decimal("0.07"),  # Dec
        ]
        for i, weight in enumerate(weights, 1):
            item.set_period_amount(i, data.annual_amount * weight)

    elif data.distribution_method == "custom":
        if not data.custom_weights or len(data.custom_weights) != 12:
            raise HTTPException(
                status_code=400,
                detail="Custom distribution requires 12 weights"
            )
        # Normalize weights
        total_weight = sum(data.custom_weights)
        for i, weight in enumerate(data.custom_weights, 1):
            item.set_period_amount(i, data.annual_amount * (weight / total_weight))

    # Recalculate totals
    calculate_budget_totals(db, budget)

    db.commit()

    return {
        "success": True,
        "message": f"Distributed ${float(data.annual_amount):,.2f} across periods",
        "item": item.to_dict(),
    }


@router.delete("/{budget_id}/items/{item_id}")
async def delete_budget_item(
    request: Request,
    budget_id: str,
    item_id: str,
    db: Session = Depends(get_db),
):
    """Delete a budget item."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status not in ('draft', 'pending_approval'):
        raise HTTPException(status_code=400, detail="Cannot modify this budget")

    item = db.query(BudgetItem).filter(
        BudgetItem.id == item_id,
        BudgetItem.budget_id == budget_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Budget item not found")

    db.delete(item)

    # Recalculate totals
    calculate_budget_totals(db, budget)

    db.commit()

    return {
        "success": True,
        "message": "Budget item deleted",
    }


# =============================================================================
# Budget Copy / Rollover
# =============================================================================

@router.post("/copy")
async def copy_budget(
    request: Request,
    data: CopyBudgetRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Copy a budget to create a new one (useful for year-over-year planning)."""
    org_id = get_organization_id(request)
    user_id = get_user_id(current_user)

    source = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == data.source_budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not source:
        raise HTTPException(status_code=404, detail="Source budget not found")

    # Check for duplicate
    existing = db.query(BudgetTemplate).filter(
        BudgetTemplate.organization_id == org_id,
        BudgetTemplate.name == data.new_name,
        BudgetTemplate.fiscal_year == data.new_fiscal_year
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Budget '{data.new_name}' already exists for FY{data.new_fiscal_year}"
        )

    # Create new budget
    new_budget = BudgetTemplate(
        organization_id=org_id,
        name=data.new_name,
        description=source.description,
        fiscal_year=data.new_fiscal_year,
        budget_type=source.budget_type,
        status='draft',
        copied_from_budget_id=source.id,
        created_by=user_id,
        notes=f"Copied from {source.name} (FY{source.fiscal_year})",
    )

    db.add(new_budget)
    db.flush()

    # Copy items with optional adjustment
    adjustment_factor = Decimal("1")
    if data.adjustment_percent:
        adjustment_factor = Decimal("1") + (data.adjustment_percent / Decimal("100"))

    for source_item in source.items:
        new_item = BudgetItem(
            budget_id=new_budget.id,
            account_id=source_item.account_id,
            department_id=source_item.department_id,
            period_1=source_item.period_1 * adjustment_factor,
            period_2=source_item.period_2 * adjustment_factor,
            period_3=source_item.period_3 * adjustment_factor,
            period_4=source_item.period_4 * adjustment_factor,
            period_5=source_item.period_5 * adjustment_factor,
            period_6=source_item.period_6 * adjustment_factor,
            period_7=source_item.period_7 * adjustment_factor,
            period_8=source_item.period_8 * adjustment_factor,
            period_9=source_item.period_9 * adjustment_factor,
            period_10=source_item.period_10 * adjustment_factor,
            period_11=source_item.period_11 * adjustment_factor,
            period_12=source_item.period_12 * adjustment_factor,
            notes=source_item.notes,
        )
        db.add(new_item)

    # Calculate totals
    calculate_budget_totals(db, new_budget)

    log_audit(
        db, org_id, user_id, 'create', 'budget_template', new_budget.id,
        entity_number=new_budget.name,
        summary=f"Copied budget from {source.name} to {new_budget.name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Budget copied to '{new_budget.name}'",
        "budget": new_budget.to_dict(),
        "items_copied": len(source.items),
        "adjustment_applied": f"{float(data.adjustment_percent or 0)}%" if data.adjustment_percent else None,
    }


# =============================================================================
# Budget vs Actual Analysis
# =============================================================================

@router.get("/{budget_id}/variance")
async def get_budget_variance(
    request: Request,
    budget_id: str,
    through_period: Optional[int] = Query(None, ge=1, le=12),
    department_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get detailed budget vs actual variance for a budget."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    # Determine period
    if through_period is None:
        today = date.today()
        if today.year == budget.fiscal_year:
            through_period = today.month
        else:
            through_period = 12

    # Date range for actuals
    year = budget.fiscal_year
    start_date = date(year, 1, 1)
    end_date = date(year, through_period, calendar.monthrange(year, through_period)[1])

    # Get items
    query = db.query(BudgetItem).filter(BudgetItem.budget_id == budget_id)
    if department_id:
        query = query.filter(BudgetItem.department_id == department_id)

    items = query.all()

    variance_data = []
    total_budget_revenue = Decimal("0")
    total_actual_revenue = Decimal("0")
    total_budget_expense = Decimal("0")
    total_actual_expense = Decimal("0")

    for item in items:
        if not item.account:
            continue

        ytd_budget = item.get_ytd_budget(through_period)
        actual = get_actual_for_account(db, org_id, str(item.account_id), start_date, end_date)
        variance = actual - ytd_budget
        variance_pct = (variance / ytd_budget * 100) if ytd_budget != 0 else Decimal("0")

        # Determine if favorable
        if item.account.account_type == 'revenue':
            is_favorable = variance >= 0
            total_budget_revenue += ytd_budget
            total_actual_revenue += actual
        else:
            is_favorable = variance <= 0
            total_budget_expense += ytd_budget
            total_actual_expense += actual

        # Monthly breakdown
        monthly = []
        for period in range(1, through_period + 1):
            period_budget = item.get_period_amount(period)
            period_start = date(year, period, 1)
            _, last_day = calendar.monthrange(year, period)
            period_end = date(year, period, last_day)
            period_actual = get_actual_for_account(db, org_id, str(item.account_id), period_start, period_end)

            monthly.append({
                "period": period,
                "budget": float(period_budget),
                "actual": float(period_actual),
                "variance": float(period_actual - period_budget),
            })

        variance_data.append({
            "account_id": str(item.account_id),
            "account_number": item.account.account_number,
            "account_name": item.account.name,
            "account_type": item.account.account_type,
            "department_id": str(item.department_id) if item.department_id else None,
            "ytd_budget": float(ytd_budget),
            "ytd_actual": float(actual),
            "variance": float(variance),
            "variance_percent": round(float(variance_pct), 2),
            "is_favorable": is_favorable,
            "annual_budget": float(item.annual_total),
            "remaining_budget": float(item.annual_total - ytd_budget),
            "monthly": monthly,
        })

    # Sort by account number
    variance_data.sort(key=lambda x: x['account_number'])

    # Summary
    budget_net = total_budget_revenue - total_budget_expense
    actual_net = total_actual_revenue - total_actual_expense

    return {
        "success": True,
        "budget": {
            "id": str(budget.id),
            "name": budget.name,
            "fiscal_year": budget.fiscal_year,
        },
        "period": {
            "through_period": through_period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "summary": {
            "revenue": {
                "budget": float(total_budget_revenue),
                "actual": float(total_actual_revenue),
                "variance": float(total_actual_revenue - total_budget_revenue),
            },
            "expenses": {
                "budget": float(total_budget_expense),
                "actual": float(total_actual_expense),
                "variance": float(total_actual_expense - total_budget_expense),
            },
            "net_income": {
                "budget": float(budget_net),
                "actual": float(actual_net),
                "variance": float(actual_net - budget_net),
            },
        },
        "line_items": variance_data,
    }


@router.get("/{budget_id}/forecast")
async def get_budget_forecast(
    request: Request,
    budget_id: str,
    db: Session = Depends(get_db),
):
    """Forecast year-end results based on YTD actuals and trends."""
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    today = date.today()
    current_period = today.month if today.year == budget.fiscal_year else 12
    year = budget.fiscal_year

    forecasts = []

    for item in budget.items:
        if not item.account:
            continue

        # Get YTD actual
        start_date = date(year, 1, 1)
        end_date = date(year, current_period, calendar.monthrange(year, current_period)[1])
        ytd_actual = get_actual_for_account(db, org_id, str(item.account_id), start_date, end_date)

        ytd_budget = item.get_ytd_budget(current_period)
        remaining_budget = item.annual_total - ytd_budget

        # Forecast methods
        # 1. Run rate: (YTD Actual / months elapsed) * 12
        run_rate_forecast = (ytd_actual / current_period) * 12 if current_period > 0 else Decimal("0")

        # 2. Budget remaining: YTD Actual + Remaining Budget
        budget_remaining_forecast = ytd_actual + remaining_budget

        # 3. Trend-based: Use YTD variance rate for remaining periods
        variance_rate = (ytd_actual / ytd_budget) if ytd_budget != 0 else Decimal("1")
        trend_forecast = ytd_actual + (remaining_budget * variance_rate)

        forecasts.append({
            "account_id": str(item.account_id),
            "account_number": item.account.account_number,
            "account_name": item.account.name,
            "account_type": item.account.account_type,
            "annual_budget": float(item.annual_total),
            "ytd_actual": float(ytd_actual),
            "forecasts": {
                "run_rate": float(run_rate_forecast),
                "budget_remaining": float(budget_remaining_forecast),
                "trend_based": float(trend_forecast),
            },
            "variance_to_budget": {
                "run_rate": float(run_rate_forecast - item.annual_total),
                "budget_remaining": float(budget_remaining_forecast - item.annual_total),
                "trend_based": float(trend_forecast - item.annual_total),
            },
        })

    # Aggregate forecasts
    revenue_items = [f for f in forecasts if f['account_type'] == 'revenue']
    expense_items = [f for f in forecasts if f['account_type'] in ('expense', 'cost_of_goods')]

    def sum_forecast(items, method):
        return sum(f['forecasts'][method] for f in items)

    return {
        "success": True,
        "budget": {
            "id": str(budget.id),
            "name": budget.name,
            "fiscal_year": budget.fiscal_year,
        },
        "as_of_period": current_period,
        "summary": {
            "revenue": {
                "budget": float(budget.total_revenue),
                "run_rate_forecast": sum_forecast(revenue_items, 'run_rate'),
                "trend_forecast": sum_forecast(revenue_items, 'trend_based'),
            },
            "expenses": {
                "budget": float(budget.total_expenses),
                "run_rate_forecast": sum_forecast(expense_items, 'run_rate'),
                "trend_forecast": sum_forecast(expense_items, 'trend_based'),
            },
            "net_income": {
                "budget": float(budget.total_revenue - budget.total_expenses),
                "run_rate_forecast": sum_forecast(revenue_items, 'run_rate') - sum_forecast(expense_items, 'run_rate'),
                "trend_forecast": sum_forecast(revenue_items, 'trend_based') - sum_forecast(expense_items, 'trend_based'),
            },
        },
        "line_items": forecasts,
    }


# =============================================================================
# Summary / Dashboard
# =============================================================================

@router.get("/summary")
async def get_budgeting_summary(
    request: Request,
    fiscal_year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Get budgeting summary for dashboard."""
    org_id = get_organization_id(request)
    year = fiscal_year or date.today().year

    # Get active budget
    active_budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.organization_id == org_id,
        BudgetTemplate.fiscal_year == year,
        BudgetTemplate.status == 'active'
    ).first()

    # Get all budgets for the year
    budgets = db.query(BudgetTemplate).filter(
        BudgetTemplate.organization_id == org_id,
        BudgetTemplate.fiscal_year == year
    ).all()

    # Budget counts by status
    status_counts = {}
    for b in budgets:
        status_counts[b.status] = status_counts.get(b.status, 0) + 1

    summary = {
        "fiscal_year": year,
        "has_active_budget": active_budget is not None,
        "budget_count": len(budgets),
        "by_status": status_counts,
    }

    if active_budget:
        # Calculate YTD variance
        current_period = date.today().month if date.today().year == year else 12
        start_date = date(year, 1, 1)
        end_date = date(year, current_period, calendar.monthrange(year, current_period)[1])

        ytd_budget_revenue = Decimal("0")
        ytd_budget_expense = Decimal("0")
        ytd_actual_revenue = Decimal("0")
        ytd_actual_expense = Decimal("0")

        for item in active_budget.items:
            if not item.account:
                continue

            ytd_budget = item.get_ytd_budget(current_period)
            actual = get_actual_for_account(db, org_id, str(item.account_id), start_date, end_date)

            if item.account.account_type == 'revenue':
                ytd_budget_revenue += ytd_budget
                ytd_actual_revenue += actual
            else:
                ytd_budget_expense += ytd_budget
                ytd_actual_expense += actual

        summary["active_budget"] = {
            "id": str(active_budget.id),
            "name": active_budget.name,
            "annual_revenue": float(active_budget.total_revenue),
            "annual_expenses": float(active_budget.total_expenses),
            "annual_net": float(active_budget.total_revenue - active_budget.total_expenses),
            "ytd": {
                "through_period": current_period,
                "budget_revenue": float(ytd_budget_revenue),
                "actual_revenue": float(ytd_actual_revenue),
                "budget_expense": float(ytd_budget_expense),
                "actual_expense": float(ytd_actual_expense),
                "budget_net": float(ytd_budget_revenue - ytd_budget_expense),
                "actual_net": float(ytd_actual_revenue - ytd_actual_expense),
            },
        }

    return {
        "success": True,
        "summary": summary,
    }
