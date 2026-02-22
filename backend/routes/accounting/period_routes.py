"""
Accounting Period API Routes.

Provides CRUD operations for managing accounting periods,
period closing, and lock functionality.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field
import uuid

from database import get_db
from models.accounting.core import AccountingPeriod, JournalEntry, AccountingSettings, AccountingAuditLog

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
    prefix="/api/v1/accounting/periods", tags=["Accounting Periods"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# Pydantic Schemas
# =============================================================================

class PeriodCreate(BaseModel):
    period_name: str = Field(..., min_length=1, max_length=50)
    period_type: str = Field(..., pattern="^(month|quarter|year)$")
    start_date: date
    end_date: date
    fiscal_year: int
    fiscal_period: int
    notes: Optional[str] = None


class PeriodUpdate(BaseModel):
    period_name: Optional[str] = None
    notes: Optional[str] = None


class ClosePeriodRequest(BaseModel):
    confirm: bool = True
    notes: Optional[str] = None


class LockDateRequest(BaseModel):
    lock_date: date


# =============================================================================
# Helper Functions
# =============================================================================

def get_organization_id(request: Request) -> int:
    """Get organization ID from tenant context middleware."""
    org_id = getattr(request.state, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


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
async def list_periods(
    request: Request,
    fiscal_year: Optional[int] = Query(None, description="Filter by fiscal year"),
    status: Optional[str] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List accounting periods."""
    org_id = get_organization_id(request)

    query = db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id
    )

    if fiscal_year:
        query = query.filter(AccountingPeriod.fiscal_year == fiscal_year)

    if status:
        query = query.filter(AccountingPeriod.status == status)

    total = query.count()
    periods = query.order_by(
        AccountingPeriod.fiscal_year.desc(),
        AccountingPeriod.fiscal_period.desc()
    ).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "periods": [period.to_dict() for period in periods],
    }


@router.get("/current")
async def get_current_period(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get the current open accounting period."""
    org_id = get_organization_id(request)
    today = date.today()

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id,
        AccountingPeriod.start_date <= today,
        AccountingPeriod.end_date >= today
    ).first()

    if not period:
        return {
            "success": True,
            "period": None,
            "message": "No period found for current date",
        }

    return {
        "success": True,
        "period": period.to_dict(),
    }


@router.get("/{period_id}")
async def get_period(
    request: Request,
    period_id: str,
    db: Session = Depends(get_db),
):
    """Get a single accounting period."""
    org_id = get_organization_id(request)

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.id == period_id,
        AccountingPeriod.organization_id == org_id
    ).first()

    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    # Get entry count for this period
    entry_count = db.query(JournalEntry).filter(
        JournalEntry.period_id == period.id,
        JournalEntry.status == 'posted'
    ).count()

    result = period.to_dict()
    result['entry_count'] = entry_count

    return {
        "success": True,
        "period": result,
    }


@router.post("")
async def create_period(
    request: Request,
    data: PeriodCreate,
    db: Session = Depends(get_db),
):
    """Create a new accounting period."""
    org_id = get_organization_id(request)

    # Validate dates
    if data.end_date <= data.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    # Check for overlapping periods
    overlapping = db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id,
        AccountingPeriod.start_date <= data.end_date,
        AccountingPeriod.end_date >= data.start_date
    ).first()

    if overlapping:
        raise HTTPException(
            status_code=400,
            detail=f"Period overlaps with existing period: {overlapping.period_name}"
        )

    period = AccountingPeriod(
        organization_id=org_id,
        period_name=data.period_name,
        period_type=data.period_type,
        start_date=data.start_date,
        end_date=data.end_date,
        fiscal_year=data.fiscal_year,
        fiscal_period=data.fiscal_period,
        notes=data.notes,
        status='open',
    )

    db.add(period)
    db.flush()

    log_audit(
        db, org_id, 1, 'create', 'accounting_period', period.id,
        entity_number=period.period_name,
        summary=f"Created accounting period {period.period_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Period {period.period_name} created",
        "period": period.to_dict(),
    }


@router.post("/generate-year")
async def generate_fiscal_year_periods(
    request: Request,
    fiscal_year: int = Query(..., description="Fiscal year to generate"),
    period_type: str = Query("month", description="Period type: month or quarter"),
    start_month: int = Query(1, ge=1, le=12, description="First month of fiscal year"),
    db: Session = Depends(get_db),
):
    """Generate all periods for a fiscal year."""
    org_id = get_organization_id(request)

    # Check if periods already exist
    existing = db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id,
        AccountingPeriod.fiscal_year == fiscal_year
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Periods already exist for fiscal year {fiscal_year}"
        )

    periods = []

    if period_type == 'month':
        # Generate 12 monthly periods
        for i in range(12):
            period_num = i + 1
            month = ((start_month - 1 + i) % 12) + 1
            year = fiscal_year if month >= start_month else fiscal_year + 1

            start = date(year, month, 1)
            end = start + relativedelta(months=1) - relativedelta(days=1)

            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

            period = AccountingPeriod(
                organization_id=org_id,
                period_name=f"{month_names[month-1]} {year}",
                period_type='month',
                start_date=start,
                end_date=end,
                fiscal_year=fiscal_year,
                fiscal_period=period_num,
                status='open',
            )
            db.add(period)
            periods.append(period)

    elif period_type == 'quarter':
        # Generate 4 quarterly periods
        for i in range(4):
            quarter_num = i + 1
            start_month_q = ((start_month - 1 + i * 3) % 12) + 1
            year = fiscal_year if start_month_q >= start_month else fiscal_year + 1

            start = date(year, start_month_q, 1)
            end = start + relativedelta(months=3) - relativedelta(days=1)

            period = AccountingPeriod(
                organization_id=org_id,
                period_name=f"Q{quarter_num} FY{fiscal_year}",
                period_type='quarter',
                start_date=start,
                end_date=end,
                fiscal_year=fiscal_year,
                fiscal_period=quarter_num,
                status='open',
            )
            db.add(period)
            periods.append(period)

    db.commit()

    return {
        "success": True,
        "message": f"Created {len(periods)} periods for fiscal year {fiscal_year}",
        "periods": [p.to_dict() for p in periods],
    }


@router.put("/{period_id}")
async def update_period(
    request: Request,
    period_id: str,
    data: PeriodUpdate,
    db: Session = Depends(get_db),
):
    """Update an accounting period."""
    org_id = get_organization_id(request)

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.id == period_id,
        AccountingPeriod.organization_id == org_id
    ).first()

    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    if period.status == 'locked':
        raise HTTPException(status_code=400, detail="Cannot modify locked period")

    old_values = period.to_dict()

    if data.period_name is not None:
        period.period_name = data.period_name

    if data.notes is not None:
        period.notes = data.notes

    log_audit(
        db, org_id, 1, 'update', 'accounting_period', period.id,
        entity_number=period.period_name,
        old_values=old_values,
        summary=f"Updated accounting period {period.period_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Period {period.period_name} updated",
        "period": period.to_dict(),
    }


@router.post("/{period_id}/close")
async def close_period(
    request: Request,
    period_id: str,
    data: ClosePeriodRequest,
    db: Session = Depends(get_db),
):
    """Close an accounting period."""
    org_id = get_organization_id(request)

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.id == period_id,
        AccountingPeriod.organization_id == org_id
    ).first()

    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    if period.status in ('closed', 'locked'):
        raise HTTPException(status_code=400, detail=f"Period is already {period.status}")

    # Check for draft entries in this period
    draft_entries = db.query(JournalEntry).filter(
        JournalEntry.period_id == period.id,
        JournalEntry.status == 'draft'
    ).count()

    if draft_entries > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot close period with {draft_entries} draft entries"
        )

    period.status = 'closed'
    period.closed_at = datetime.utcnow()
    period.closed_by = 1

    if data.notes:
        period.notes = (period.notes or '') + f"\nClosed: {data.notes}"

    log_audit(
        db, org_id, 1, 'close', 'accounting_period', period.id,
        entity_number=period.period_name,
        summary=f"Closed accounting period {period.period_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Period {period.period_name} closed",
        "period": period.to_dict(),
    }


@router.post("/{period_id}/lock")
async def lock_period(
    request: Request,
    period_id: str,
    db: Session = Depends(get_db),
):
    """Lock a closed accounting period (prevents all modifications)."""
    org_id = get_organization_id(request)

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.id == period_id,
        AccountingPeriod.organization_id == org_id
    ).first()

    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    if period.status == 'locked':
        raise HTTPException(status_code=400, detail="Period is already locked")

    if period.status != 'closed':
        raise HTTPException(status_code=400, detail="Must close period before locking")

    period.status = 'locked'

    log_audit(
        db, org_id, 1, 'update', 'accounting_period', period.id,
        entity_number=period.period_name,
        new_values={'status': 'locked'},
        summary=f"Locked accounting period {period.period_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Period {period.period_name} locked",
        "period": period.to_dict(),
    }


@router.post("/{period_id}/reopen")
async def reopen_period(
    request: Request,
    period_id: str,
    db: Session = Depends(get_db),
):
    """Reopen a closed (not locked) accounting period."""
    org_id = get_organization_id(request)

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.id == period_id,
        AccountingPeriod.organization_id == org_id
    ).first()

    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    if period.status == 'locked':
        raise HTTPException(status_code=400, detail="Cannot reopen locked period")

    if period.status == 'open':
        raise HTTPException(status_code=400, detail="Period is already open")

    period.status = 'open'
    period.closed_at = None
    period.closed_by = None

    log_audit(
        db, org_id, 1, 'reopen', 'accounting_period', period.id,
        entity_number=period.period_name,
        summary=f"Reopened accounting period {period.period_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Period {period.period_name} reopened",
        "period": period.to_dict(),
    }


@router.get("/settings/lock-date")
async def get_lock_date(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get the current lock date."""
    org_id = get_organization_id(request)

    settings = db.query(AccountingSettings).filter(
        AccountingSettings.organization_id == org_id
    ).first()

    return {
        "success": True,
        "lock_date": settings.lock_date.isoformat() if settings and settings.lock_date else None,
    }


@router.post("/settings/lock-date")
async def set_lock_date(
    request: Request,
    data: LockDateRequest,
    db: Session = Depends(get_db),
):
    """Set the global lock date (no entries can be posted on or before this date)."""
    org_id = get_organization_id(request)

    settings = db.query(AccountingSettings).filter(
        AccountingSettings.organization_id == org_id
    ).first()

    if not settings:
        settings = AccountingSettings(organization_id=org_id)
        db.add(settings)

    old_lock_date = settings.lock_date

    settings.lock_date = data.lock_date

    log_audit(
        db, org_id, 1, 'update', 'accounting_settings', settings.id,
        old_values={'lock_date': old_lock_date.isoformat() if old_lock_date else None},
        new_values={'lock_date': data.lock_date.isoformat()},
        summary=f"Set lock date to {data.lock_date}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Lock date set to {data.lock_date}",
        "lock_date": data.lock_date.isoformat(),
    }
