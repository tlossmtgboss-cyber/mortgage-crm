"""
Vendor Management Routes — CRUD, ordering, and performance analytics.

Manages third-party service vendors (appraisal, title, HOI, survey),
vendor orders tied to loans, and performance metrics (turnaround, quality).

Prefix: /api/v1/vendors
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import current_user_dep
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vendors", tags=["Vendor Management"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class VendorCreate(BaseModel):
    name: str = Field(..., max_length=255)
    vendor_type: str = Field(..., description="appraisal, title, hoi, or survey")
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    company_name: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None
    license_number: Optional[str] = Field(None, max_length=100)
    is_preferred: bool = False


class VendorUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    vendor_type: Optional[str] = None
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    company_name: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None
    license_number: Optional[str] = Field(None, max_length=100)
    is_preferred: Optional[bool] = None
    is_active: Optional[bool] = None


class OrderCreate(BaseModel):
    loan_id: int
    order_type: str = Field(..., description="appraisal, title, hoi, or survey")
    amount: Optional[float] = None
    due_at: Optional[datetime] = None
    notes: Optional[str] = None


# =============================================================================
# Helpers — lazy model imports
# =============================================================================

_models_loaded = False
_Vendor = None
_VendorOrder = None

VALID_VENDOR_TYPES = {"appraisal", "title", "hoi", "survey"}
VALID_ORDER_STATUSES = {"ordered", "in_progress", "completed", "cancelled", "revision_needed"}


def _ensure_models():
    """Lazy-import models on first use."""
    global _models_loaded, _Vendor, _VendorOrder
    if _models_loaded:
        return
    from database.models.vendor import Vendor, VendorOrder
    _Vendor = Vendor
    _VendorOrder = VendorOrder
    _models_loaded = True


def _ensure_tables(db: Session):
    """Create tables if they don't exist (production-safe)."""
    try:
        from database.models.vendor import Vendor, VendorOrder
        from db import engine
        Vendor.__table__.create(engine, checkfirst=True)
        VendorOrder.__table__.create(engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Vendor table creation check failed (non-fatal): {e}")


def _vendor_to_dict(v) -> dict:
    """Serialize a Vendor ORM object to a dict."""
    return {
        "id": v.id,
        "organization_id": v.organization_id,
        "name": v.name,
        "vendor_type": v.vendor_type,
        "contact_email": v.contact_email,
        "contact_phone": v.contact_phone,
        "company_name": v.company_name,
        "address": v.address,
        "license_number": v.license_number,
        "avg_turnaround_days": float(v.avg_turnaround_days) if v.avg_turnaround_days else None,
        "quality_score": float(v.quality_score) if v.quality_score else None,
        "total_orders": v.total_orders or 0,
        "completed_orders": v.completed_orders or 0,
        "issue_count": v.issue_count or 0,
        "is_preferred": v.is_preferred,
        "is_active": v.is_active,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


def _order_to_dict(o) -> dict:
    """Serialize a VendorOrder ORM object to a dict."""
    return {
        "id": o.id,
        "organization_id": o.organization_id,
        "vendor_id": o.vendor_id,
        "loan_id": o.loan_id,
        "order_type": o.order_type,
        "status": o.status,
        "amount": float(o.amount) if o.amount else None,
        "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
        "due_at": o.due_at.isoformat() if o.due_at else None,
        "completed_at": o.completed_at.isoformat() if o.completed_at else None,
        "turnaround_days": float(o.turnaround_days) if o.turnaround_days else None,
        "has_issues": o.has_issues,
        "issue_description": o.issue_description,
        "revision_count": o.revision_count or 0,
        "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


# =============================================================================
# Routes — Vendor CRUD
# =============================================================================

@router.post("")
async def create_vendor(
    body: VendorCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Create a new vendor for the organization."""
    _ensure_models()
    _ensure_tables(db)

    if body.vendor_type not in VALID_VENDOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vendor_type. Must be one of: {', '.join(sorted(VALID_VENDOR_TYPES))}",
        )

    vendor = _Vendor(
        organization_id=current_user.organization_id,
        name=body.name,
        vendor_type=body.vendor_type,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        company_name=body.company_name,
        address=body.address,
        license_number=body.license_number,
        is_preferred=body.is_preferred,
    )
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)

    logger.info(
        "Vendor created: id=%s name=%r type=%s org=%s",
        vendor.id, vendor.name, vendor.vendor_type, current_user.organization_id,
    )

    return {"status": "ok", "vendor": _vendor_to_dict(vendor)}


@router.get("")
async def list_vendors(
    vendor_type: Optional[str] = Query(None, description="Filter by type: appraisal, title, hoi, survey"),
    is_active: Optional[bool] = Query(None),
    is_preferred: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """List vendors for the organization, optionally filtered by type."""
    _ensure_models()
    _ensure_tables(db)

    q = db.query(_Vendor).filter(
        _Vendor.organization_id == current_user.organization_id,
    )

    if vendor_type:
        if vendor_type not in VALID_VENDOR_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid vendor_type: {vendor_type}")
        q = q.filter(_Vendor.vendor_type == vendor_type)

    if is_active is not None:
        q = q.filter(_Vendor.is_active == is_active)

    if is_preferred is not None:
        q = q.filter(_Vendor.is_preferred == is_preferred)

    total = q.count()
    vendors = q.order_by(_Vendor.name).offset(offset).limit(limit).all()

    return {
        "vendors": [_vendor_to_dict(v) for v in vendors],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# Static path '/slow' MUST come before '/{vendor_id}' path parameter
@router.get("/slow")
async def list_slow_vendors(
    threshold_multiplier: float = Query(2.0, ge=1.0, description="Multiplier of avg turnaround to flag as slow"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """
    List slow vendors: those whose average turnaround exceeds the
    overall average by a given multiplier (default 2x).

    Returns vendors with avg_turnaround_days > (org avg * threshold_multiplier).
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = current_user.organization_id

    # Compute the org-wide average turnaround across all vendors with data
    avg_result = db.query(
        func.avg(_Vendor.avg_turnaround_days)
    ).filter(
        _Vendor.organization_id == org_id,
        _Vendor.avg_turnaround_days.isnot(None),
        _Vendor.is_active == True,  # noqa: E712
    ).scalar()

    if avg_result is None:
        return {"slow_vendors": [], "org_avg_turnaround_days": None, "threshold_multiplier": threshold_multiplier}

    org_avg = float(avg_result)
    threshold = org_avg * threshold_multiplier

    slow = db.query(_Vendor).filter(
        _Vendor.organization_id == org_id,
        _Vendor.avg_turnaround_days > threshold,
        _Vendor.is_active == True,  # noqa: E712
    ).order_by(_Vendor.avg_turnaround_days.desc()).all()

    return {
        "slow_vendors": [_vendor_to_dict(v) for v in slow],
        "org_avg_turnaround_days": round(org_avg, 2),
        "threshold_days": round(threshold, 2),
        "threshold_multiplier": threshold_multiplier,
        "count": len(slow),
    }


@router.get("/{vendor_id}")
async def get_vendor(
    vendor_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Get vendor details by ID."""
    _ensure_models()
    _ensure_tables(db)

    vendor = (await db.execute(select(_Vendor).where(
        _Vendor.id == vendor_id,
        _Vendor.organization_id == current_user.organization_id,
    ))).scalars().first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return {"vendor": _vendor_to_dict(vendor)}


@router.patch("/{vendor_id}")
async def update_vendor(
    vendor_id: int,
    body: VendorUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Update a vendor's details."""
    _ensure_models()
    _ensure_tables(db)

    vendor = (await db.execute(select(_Vendor).where(
        _Vendor.id == vendor_id,
        _Vendor.organization_id == current_user.organization_id,
    ))).scalars().first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    update_data = body.model_dump(exclude_unset=True)

    if "vendor_type" in update_data and update_data["vendor_type"] not in VALID_VENDOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vendor_type. Must be one of: {', '.join(sorted(VALID_VENDOR_TYPES))}",
        )

    for field, value in update_data.items():
        setattr(vendor, field, value)

    vendor.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(vendor)

    logger.info("Vendor updated: id=%s fields=%s", vendor_id, list(update_data.keys()))

    return {"status": "ok", "vendor": _vendor_to_dict(vendor)}


# =============================================================================
# Routes — Vendor Orders
# =============================================================================

@router.post("/{vendor_id}/orders")
async def create_order(
    vendor_id: int,
    body: OrderCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Create a new order (appraisal, title, HOI, survey) for a vendor."""
    _ensure_models()
    _ensure_tables(db)

    org_id = current_user.organization_id

    vendor = (await db.execute(select(_Vendor).where(
        _Vendor.id == vendor_id,
        _Vendor.organization_id == org_id,
    ))).scalars().first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    if not vendor.is_active:
        raise HTTPException(status_code=400, detail="Vendor is inactive")

    if body.order_type not in VALID_VENDOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid order_type. Must be one of: {', '.join(sorted(VALID_VENDOR_TYPES))}",
        )

    order = _VendorOrder(
        organization_id=org_id,
        vendor_id=vendor_id,
        loan_id=body.loan_id,
        order_type=body.order_type,
        status="ordered",
        amount=body.amount,
        due_at=body.due_at,
        notes=body.notes,
    )
    db.add(order)

    # Increment total_orders on the vendor
    vendor.total_orders = (vendor.total_orders or 0) + 1
    vendor.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(order)

    logger.info(
        "Vendor order created: id=%s vendor_id=%s loan_id=%s type=%s",
        order.id, vendor_id, body.loan_id, body.order_type,
    )

    return {"status": "ok", "order": _order_to_dict(order)}


@router.get("/{vendor_id}/orders")
async def list_orders(
    vendor_id: int,
    status: Optional[str] = Query(None, description="Filter by order status"),
    order_type: Optional[str] = Query(None, description="Filter by order type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """List orders for a specific vendor."""
    _ensure_models()
    _ensure_tables(db)

    org_id = current_user.organization_id

    # Verify vendor exists in this org
    vendor = (await db.execute(select(_Vendor).where(
        _Vendor.id == vendor_id,
        _Vendor.organization_id == org_id,
    ))).scalars().first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    q = db.query(_VendorOrder).filter(
        _VendorOrder.vendor_id == vendor_id,
        _VendorOrder.organization_id == org_id,
    )

    if status:
        if status not in VALID_ORDER_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        q = q.filter(_VendorOrder.status == status)

    if order_type:
        if order_type not in VALID_VENDOR_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid order_type: {order_type}")
        q = q.filter(_VendorOrder.order_type == order_type)

    total = q.count()
    orders = q.order_by(_VendorOrder.ordered_at.desc()).offset(offset).limit(limit).all()

    return {
        "orders": [_order_to_dict(o) for o in orders],
        "total": total,
        "vendor_id": vendor_id,
        "limit": limit,
        "offset": offset,
    }


# =============================================================================
# Routes — Vendor Performance
# =============================================================================

@router.get("/{vendor_id}/performance")
async def get_vendor_performance(
    vendor_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """
    Get performance metrics for a vendor: turnaround, quality, completion rate,
    issue rate, and recent order breakdown.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = current_user.organization_id

    vendor = (await db.execute(select(_Vendor).where(
        _Vendor.id == vendor_id,
        _Vendor.organization_id == org_id,
    ))).scalars().first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Compute live metrics from orders
    order_stats = db.query(
        func.count(_VendorOrder.id).label("total"),
        func.count(_VendorOrder.id).filter(
            _VendorOrder.status == "completed"
        ).label("completed"),
        func.count(_VendorOrder.id).filter(
            _VendorOrder.has_issues == True  # noqa: E712
        ).label("with_issues"),
        func.avg(_VendorOrder.turnaround_days).label("avg_turnaround"),
        func.sum(_VendorOrder.revision_count).label("total_revisions"),
    ).filter(
        _VendorOrder.vendor_id == vendor_id,
        _VendorOrder.organization_id == org_id,
    ).first()

    total = order_stats.total or 0
    completed = order_stats.completed or 0
    with_issues = order_stats.with_issues or 0

    # Status breakdown
    status_breakdown = db.query(
        _VendorOrder.status,
        func.count(_VendorOrder.id),
    ).filter(
        _VendorOrder.vendor_id == vendor_id,
        _VendorOrder.organization_id == org_id,
    ).group_by(_VendorOrder.status).all()

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "vendor_type": vendor.vendor_type,
        "metrics": {
            "total_orders": total,
            "completed_orders": completed,
            "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
            "avg_turnaround_days": round(float(order_stats.avg_turnaround), 2) if order_stats.avg_turnaround else None,
            "quality_score": float(vendor.quality_score) if vendor.quality_score else None,
            "issue_count": with_issues,
            "issue_rate": round(with_issues / total * 100, 1) if total > 0 else 0,
            "total_revisions": int(order_stats.total_revisions) if order_stats.total_revisions else 0,
        },
        "status_breakdown": {row[0]: row[1] for row in status_breakdown},
        "is_preferred": vendor.is_preferred,
    }


# =============================================================================
# Registration
# =============================================================================

def register_vendor_management_routes(app):
    """Register vendor management routes with the FastAPI app."""
    app.include_router(router)
    logger.info("Vendor management routes registered")
