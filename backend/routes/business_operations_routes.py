"""
FastAPI routes for the Business Operations Dashboard.

Provides endpoints for:
- Service cost tracking and monitoring
- Revenue tracking (subscription + usage)
- Marketing analytics (CAC, LTV, ROI)
- Forecasting and what-if scenarios
- P&L and business KPIs
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from database import get_db
from routes.auth_deps import require_auth

from models.business_operations import (
    ServiceProvider, ServiceUsageRecord, ServiceInvoice,
    SubscriptionRevenue, UsageRevenue,
    MarketingCampaign, MarketingMetrics,
    BusinessForecast, BusinessKPI, BudgetAlert
)
from sqlalchemy.exc import SQLAlchemyError
from schemas.business_operations import (
    ServiceProviderCreate, ServiceProviderUpdate, ServiceProviderResponse, ServiceProviderSummary,
    ServiceUsageCreate, ServiceUsageResponse, ServiceUsageImport,
    ServiceInvoiceCreate, ServiceInvoiceResponse,
    SubscriptionCreate, SubscriptionUpdate, SubscriptionResponse,
    UsageRevenueCreate, UsageRevenueResponse,
    CampaignCreate, CampaignUpdate, CampaignResponse,
    MarketingMetricsCreate, MarketingMetricsResponse,
    ForecastCreate, ForecastResponse, ForecastParameters, ScenarioRequest,
    BusinessKPIResponse, BusinessOpsDashboardResponse,
    RevenueSummary, CostSummary, ProfitLoss,
    RunwayAnalysis, BreakEvenAnalysis,
    CACAnalysis, LTVAnalysis, MarketingROI
)

router = APIRouter(prefix="/api/v1/business-ops", tags=["business-operations"], dependencies=[Depends(require_auth)])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_organization_id(request: Request = None) -> int:
    """Get organization ID from authenticated user's context."""
    if request:
        from jose import jwt, JWTError
        import os
        SECRET_KEY = os.getenv("SECRET_KEY")
        if SECRET_KEY:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                try:
                    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_aud": False})
                    if "org_id" in payload:
                        return payload["org_id"]
                    if "company_id" in payload:
                        return payload["company_id"]
                except JWTError:
                    raise HTTPException(status_code=401, detail="Invalid authentication token")
    raise HTTPException(status_code=401, detail="Authentication required")


def get_current_month_range():
    """Get start and end of current month."""
    today = date.today()
    start = today.replace(day=1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(today.year, today.month + 1, 1) - timedelta(days=1)
    return start, end


def get_previous_month_range():
    """Get start and end of previous month."""
    today = date.today()
    first_of_month = today.replace(day=1)
    last_of_prev = first_of_month - timedelta(days=1)
    start = last_of_prev.replace(day=1)
    return start, last_of_prev


# =============================================================================
# DASHBOARD ENDPOINTS
# =============================================================================

@router.get("/dashboard")
async def get_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get complete business operations dashboard data."""
    org_id = get_organization_id(request)
    month_start, month_end = get_current_month_range()

    # Get current KPIs
    kpi = db.query(BusinessKPI).filter(
        BusinessKPI.organization_id == org_id,
        BusinessKPI.snapshot_date == date.today()
    ).first()

    # Calculate revenue summary
    subscription_revenue = db.query(
        func.sum(SubscriptionRevenue.mrr)
    ).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or Decimal("0")

    active_subs = db.query(func.count(SubscriptionRevenue.id)).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or 0

    usage_rev = db.query(
        func.sum(UsageRevenue.amount)
    ).filter(
        UsageRevenue.organization_id == org_id,
        UsageRevenue.revenue_date >= month_start,
        UsageRevenue.revenue_date <= month_end
    ).scalar() or Decimal("0")

    # Calculate cost summary
    service_costs = db.query(
        func.sum(ServiceUsageRecord.total_cost)
    ).filter(
        ServiceUsageRecord.organization_id == org_id,
        ServiceUsageRecord.usage_date >= month_start,
        ServiceUsageRecord.usage_date <= month_end
    ).scalar() or Decimal("0")

    # Costs by category
    costs_by_cat = db.query(
        ServiceProvider.category,
        func.sum(ServiceUsageRecord.total_cost).label("total")
    ).join(
        ServiceUsageRecord, ServiceUsageRecord.service_provider_id == ServiceProvider.id
    ).filter(
        ServiceProvider.organization_id == org_id,
        ServiceUsageRecord.usage_date >= month_start,
        ServiceUsageRecord.usage_date <= month_end
    ).group_by(ServiceProvider.category).all()

    category_costs = {row.category: float(row.total or 0) for row in costs_by_cat}

    # Get active budget alerts
    alerts = db.query(BudgetAlert).filter(
        BudgetAlert.organization_id == org_id,
        BudgetAlert.status == "active"
    ).all()

    # Build response
    total_revenue = float(subscription_revenue) + float(usage_rev)
    total_costs = float(service_costs)
    gross_profit = total_revenue - total_costs
    gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

    return {
        "kpis": {
            "mrr": float(subscription_revenue),
            "arr": float(subscription_revenue) * 12,
            "total_revenue_mtd": total_revenue,
            "total_customers": active_subs,
            "service_costs": float(service_costs),
            "gross_margin": round(gross_margin, 2),
        },
        "revenue": {
            "mrr": float(subscription_revenue),
            "arr": float(subscription_revenue) * 12,
            "subscription_revenue_mtd": float(subscription_revenue),
            "usage_revenue_mtd": float(usage_rev),
            "total_revenue_mtd": total_revenue,
            "subscription_count": active_subs,
            "active_customers": active_subs,
        },
        "costs": {
            "total_costs_mtd": float(service_costs),
            "service_costs_mtd": float(service_costs),
            "by_category": category_costs,
            "budget_alerts": len(alerts),
        },
        "pnl": {
            "total_revenue": total_revenue,
            "total_expenses": total_costs,
            "gross_profit": gross_profit,
            "gross_margin": round(gross_margin, 2),
            "net_profit": gross_profit,  # Simplified - would include more expenses
            "net_margin": round(gross_margin, 2),
        },
        "alerts": [
            {
                "id": str(a.id),
                "type": a.alert_type,
                "threshold_percent": a.threshold_percent,
                "current_spend": float(a.current_spend),
                "budget_amount": float(a.budget_amount),
                "status": a.status,
            }
            for a in alerts
        ]
    }


@router.get("/kpis")
async def get_current_kpis(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current business KPIs."""
    org_id = get_organization_id(request)

    kpi = db.query(BusinessKPI).filter(
        BusinessKPI.organization_id == org_id
    ).order_by(BusinessKPI.snapshot_date.desc()).first()

    if not kpi:
        return {"message": "No KPI data available", "kpis": None}

    return {
        "snapshot_date": kpi.snapshot_date.isoformat(),
        "mrr": float(kpi.mrr or 0),
        "arr": float(kpi.arr or 0),
        "total_customers": kpi.total_customers,
        "churn_rate": float(kpi.churn_rate or 0),
        "gross_margin": float(kpi.gross_margin or 0),
        "net_margin": float(kpi.net_margin or 0),
        "cash_runway_months": float(kpi.cash_runway_months or 0),
        "ltv_cac_ratio": float(kpi.ltv_cac_ratio or 0),
    }


@router.get("/kpis/history")
async def get_kpi_history(
    request: Request,
    days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db)
):
    """Get historical KPI data."""
    org_id = get_organization_id(request)
    start_date = date.today() - timedelta(days=days)

    kpis = db.query(BusinessKPI).filter(
        BusinessKPI.organization_id == org_id,
        BusinessKPI.snapshot_date >= start_date
    ).order_by(BusinessKPI.snapshot_date).all()

    return {
        "period_days": days,
        "data": [
            {
                "date": k.snapshot_date.isoformat(),
                "mrr": float(k.mrr or 0),
                "arr": float(k.arr or 0),
                "customers": k.total_customers,
                "churn_rate": float(k.churn_rate or 0),
                "service_costs": float(k.service_costs or 0),
                "gross_margin": float(k.gross_margin or 0),
            }
            for k in kpis
        ]
    }


# =============================================================================
# SERVICE PROVIDER ENDPOINTS
# =============================================================================

@router.get("/services", response_model=List[ServiceProviderSummary])
async def list_services(
    request: Request,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all service providers with current month costs."""
    org_id = get_organization_id(request)
    month_start, month_end = get_current_month_range()
    prev_start, prev_end = get_previous_month_range()

    query = db.query(ServiceProvider).filter(
        ServiceProvider.organization_id == org_id,
        ServiceProvider.is_active == True
    )

    if category:
        query = query.filter(ServiceProvider.category == category)

    services = query.all()

    result = []
    for s in services:
        # Current month cost
        current_cost = db.query(
            func.sum(ServiceUsageRecord.total_cost)
        ).filter(
            ServiceUsageRecord.service_provider_id == s.id,
            ServiceUsageRecord.usage_date >= month_start,
            ServiceUsageRecord.usage_date <= month_end
        ).scalar() or Decimal("0")

        # Previous month cost
        prev_cost = db.query(
            func.sum(ServiceUsageRecord.total_cost)
        ).filter(
            ServiceUsageRecord.service_provider_id == s.id,
            ServiceUsageRecord.usage_date >= prev_start,
            ServiceUsageRecord.usage_date <= prev_end
        ).scalar() or Decimal("0")

        budget_pct = None
        if s.monthly_budget and s.monthly_budget > 0:
            budget_pct = float(current_cost / s.monthly_budget * 100)

        result.append({
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "provider_type": s.provider_type,
            "current_month_cost": float(current_cost),
            "last_month_cost": float(prev_cost),
            "monthly_budget": float(s.monthly_budget) if s.monthly_budget else None,
            "budget_used_percent": budget_pct,
            "has_usage_api": s.has_usage_api,
        })

    return result


@router.post("/services", response_model=ServiceProviderResponse)
async def create_service(
    data: ServiceProviderCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Add a new service provider."""
    org_id = get_organization_id(request)

    # Check for duplicate
    existing = db.query(ServiceProvider).filter(
        ServiceProvider.organization_id == org_id,
        ServiceProvider.provider_type == data.provider_type
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail=f"Service provider '{data.provider_type}' already exists")

    service = ServiceProvider(
        organization_id=org_id,
        **data.model_dump()
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.put("/services/{service_id}", response_model=ServiceProviderResponse)
async def update_service(
    service_id: UUID,
    data: ServiceProviderUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update a service provider."""
    org_id = get_organization_id(request)

    service = db.query(ServiceProvider).filter(
        ServiceProvider.id == service_id,
        ServiceProvider.organization_id == org_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for key, value in data.model_dump(exclude_unset=True).items():
        if key not in _protected:
            setattr(service, key, value)

    service.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(service)
    return service


@router.get("/services/{service_id}/usage")
async def get_service_usage(
    service_id: UUID,
    request: Request,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Get usage history for a service."""
    org_id = get_organization_id(request)
    start_date = date.today() - timedelta(days=days)

    usage = db.query(ServiceUsageRecord).filter(
        ServiceUsageRecord.service_provider_id == service_id,
        ServiceUsageRecord.organization_id == org_id,
        ServiceUsageRecord.usage_date >= start_date
    ).order_by(ServiceUsageRecord.usage_date.desc()).all()

    total_cost = sum(float(u.total_cost) for u in usage)
    total_quantity = sum(float(u.quantity) for u in usage)

    return {
        "service_id": str(service_id),
        "period_days": days,
        "total_cost": total_cost,
        "total_quantity": total_quantity,
        "records": [
            {
                "id": str(u.id),
                "date": u.usage_date.isoformat(),
                "usage_type": u.usage_type,
                "quantity": float(u.quantity),
                "unit_type": u.unit_type,
                "total_cost": float(u.total_cost),
                "source": u.source,
            }
            for u in usage
        ]
    }


@router.post("/services/{service_id}/usage", response_model=ServiceUsageResponse)
async def record_usage(
    service_id: UUID,
    data: ServiceUsageCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Manually record usage for a service."""
    org_id = get_organization_id(request)

    # Verify service exists
    service = db.query(ServiceProvider).filter(
        ServiceProvider.id == service_id,
        ServiceProvider.organization_id == org_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    record = ServiceUsageRecord(
        organization_id=org_id,
        service_provider_id=service_id,
        source="manual",
        **data.model_dump(exclude={"service_provider_id"})
    )
    db.add(record)

    # Check budget alert
    await check_budget_alert(db, service, org_id)

    db.commit()
    db.refresh(record)
    return record


@router.post("/services/{service_id}/fetch-usage")
async def fetch_usage_from_api(
    service_id: UUID,
    request: Request,
    db: Session = Depends(get_db)
):
    """Trigger API fetch for service usage (where available)."""
    org_id = get_organization_id(request)

    service = db.query(ServiceProvider).filter(
        ServiceProvider.id == service_id,
        ServiceProvider.organization_id == org_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if not service.has_usage_api:
        raise HTTPException(status_code=400, detail="Service does not support API fetching")

    # This would call the appropriate fetcher based on provider_type
    # For now, return a placeholder response
    return {
        "message": f"Usage fetch triggered for {service.name}",
        "provider_type": service.provider_type,
        "status": "pending"
    }


@router.post("/services/import-csv")
async def import_usage_csv(
    file: UploadFile = File(...),
    service_id: UUID = Query(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Import usage records from CSV file."""
    org_id = get_organization_id(request)

    # Verify service exists
    service = db.query(ServiceProvider).filter(
        ServiceProvider.id == service_id,
        ServiceProvider.organization_id == org_id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Read CSV
    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    records_created = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            record = ServiceUsageRecord(
                organization_id=org_id,
                service_provider_id=service_id,
                usage_date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                usage_type=row.get("usage_type"),
                quantity=Decimal(row["quantity"]),
                unit_type=row.get("unit_type", service.unit_type),
                total_cost=Decimal(row["total_cost"]),
                source="csv_import",
                notes=row.get("notes")
            )
            db.add(record)
            records_created += 1
        except SQLAlchemyError as e:
            errors.append(f"Row {row_num}: {str(e)}")

    if records_created > 0:
        db.commit()

    return {
        "records_created": records_created,
        "errors": errors if errors else None
    }


@router.get("/services/costs/summary")
async def get_costs_summary(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get summary of all service costs."""
    org_id = get_organization_id(request)
    month_start, month_end = get_current_month_range()
    prev_start, prev_end = get_previous_month_range()

    # Current month total
    current_total = db.query(
        func.sum(ServiceUsageRecord.total_cost)
    ).join(ServiceProvider).filter(
        ServiceProvider.organization_id == org_id,
        ServiceUsageRecord.usage_date >= month_start,
        ServiceUsageRecord.usage_date <= month_end
    ).scalar() or Decimal("0")

    # Previous month total
    prev_total = db.query(
        func.sum(ServiceUsageRecord.total_cost)
    ).join(ServiceProvider).filter(
        ServiceProvider.organization_id == org_id,
        ServiceUsageRecord.usage_date >= prev_start,
        ServiceUsageRecord.usage_date <= prev_end
    ).scalar() or Decimal("0")

    # By category
    by_category = db.query(
        ServiceProvider.category,
        func.sum(ServiceUsageRecord.total_cost).label("total")
    ).join(ServiceUsageRecord).filter(
        ServiceProvider.organization_id == org_id,
        ServiceUsageRecord.usage_date >= month_start,
        ServiceUsageRecord.usage_date <= month_end
    ).group_by(ServiceProvider.category).all()

    # Month over month change
    mom_change = 0
    if prev_total > 0:
        mom_change = ((float(current_total) - float(prev_total)) / float(prev_total)) * 100

    return {
        "current_month_total": float(current_total),
        "previous_month_total": float(prev_total),
        "month_over_month_change_percent": round(mom_change, 2),
        "by_category": {row.category: float(row.total) for row in by_category}
    }


@router.get("/services/costs/by-category")
async def get_costs_by_category(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get costs broken down by category."""
    org_id = get_organization_id(request)
    month_start, month_end = get_current_month_range()

    results = db.query(
        ServiceProvider.category,
        func.count(ServiceProvider.id).label("service_count"),
        func.sum(ServiceUsageRecord.total_cost).label("total_cost")
    ).outerjoin(
        ServiceUsageRecord,
        and_(
            ServiceUsageRecord.service_provider_id == ServiceProvider.id,
            ServiceUsageRecord.usage_date >= month_start,
            ServiceUsageRecord.usage_date <= month_end
        )
    ).filter(
        ServiceProvider.organization_id == org_id,
        ServiceProvider.is_active == True
    ).group_by(ServiceProvider.category).all()

    return [
        {
            "category": r.category,
            "service_count": r.service_count,
            "total_cost": float(r.total_cost or 0)
        }
        for r in results
    ]


@router.get("/services/alerts")
async def get_budget_alerts(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get active budget alerts."""
    org_id = get_organization_id(request)

    alerts = db.query(BudgetAlert).filter(
        BudgetAlert.organization_id == org_id,
        BudgetAlert.status == "active"
    ).order_by(BudgetAlert.threshold_percent.desc()).all()

    return [
        {
            "id": str(a.id),
            "alert_type": a.alert_type,
            "service_provider_id": str(a.service_provider_id) if a.service_provider_id else None,
            "category": a.category,
            "threshold_percent": a.threshold_percent,
            "current_spend": float(a.current_spend),
            "budget_amount": float(a.budget_amount),
            "percent_used": round(float(a.current_spend / a.budget_amount * 100), 1) if a.budget_amount > 0 else 0,
            "period_start": a.period_start.isoformat(),
            "period_end": a.period_end.isoformat(),
        }
        for a in alerts
    ]


async def check_budget_alert(db: Session, service: ServiceProvider, org_id: int):
    """Check if budget alert should be triggered."""
    if not service.monthly_budget:
        return

    month_start, month_end = get_current_month_range()

    current_spend = db.query(
        func.sum(ServiceUsageRecord.total_cost)
    ).filter(
        ServiceUsageRecord.service_provider_id == service.id,
        ServiceUsageRecord.usage_date >= month_start,
        ServiceUsageRecord.usage_date <= month_end
    ).scalar() or Decimal("0")

    percent_used = float(current_spend / service.monthly_budget * 100)

    if percent_used >= service.alert_threshold_percent:
        # Check if alert already exists
        existing = db.query(BudgetAlert).filter(
            BudgetAlert.service_provider_id == service.id,
            BudgetAlert.period_start == month_start,
            BudgetAlert.status == "active"
        ).first()

        if not existing:
            alert = BudgetAlert(
                organization_id=org_id,
                alert_type="service_budget",
                service_provider_id=service.id,
                threshold_percent=service.alert_threshold_percent,
                current_spend=current_spend,
                budget_amount=service.monthly_budget,
                period_start=month_start,
                period_end=month_end,
                status="active"
            )
            db.add(alert)


# =============================================================================
# REVENUE ENDPOINTS
# =============================================================================

@router.get("/revenue/summary")
async def get_revenue_summary(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get revenue summary."""
    org_id = get_organization_id(request)
    month_start, month_end = get_current_month_range()
    prev_start, prev_end = get_previous_month_range()

    # Subscription revenue
    current_mrr = db.query(
        func.sum(SubscriptionRevenue.mrr)
    ).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or Decimal("0")

    sub_count = db.query(func.count(SubscriptionRevenue.id)).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or 0

    # Usage revenue this month
    usage_rev = db.query(
        func.sum(UsageRevenue.amount)
    ).filter(
        UsageRevenue.organization_id == org_id,
        UsageRevenue.revenue_date >= month_start,
        UsageRevenue.revenue_date <= month_end
    ).scalar() or Decimal("0")

    # Previous month MRR for growth calc
    # (Would need historical tracking for accurate calc)

    return {
        "mrr": float(current_mrr),
        "arr": float(current_mrr) * 12,
        "subscription_revenue_mtd": float(current_mrr),
        "usage_revenue_mtd": float(usage_rev),
        "total_revenue_mtd": float(current_mrr) + float(usage_rev),
        "subscription_count": sub_count,
        "active_customers": sub_count,
    }


@router.get("/revenue/subscriptions", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all subscriptions."""
    org_id = get_organization_id(request)

    query = db.query(SubscriptionRevenue).filter(
        SubscriptionRevenue.organization_id == org_id
    )

    if status:
        query = query.filter(SubscriptionRevenue.status == status)

    return query.order_by(SubscriptionRevenue.start_date.desc()).all()


@router.post("/revenue/subscriptions", response_model=SubscriptionResponse)
async def create_subscription(
    data: SubscriptionCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Add a new subscription."""
    org_id = get_organization_id(request)

    # Calculate ARR
    arr = data.mrr * 12 if data.billing_cycle == "monthly" else data.mrr

    sub = SubscriptionRevenue(
        organization_id=org_id,
        arr=arr,
        status="active",
        **data.model_dump()
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("/revenue/usage")
async def get_usage_revenue(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Get usage-based revenue."""
    org_id = get_organization_id(request)
    start_date = date.today() - timedelta(days=days)

    revenue = db.query(UsageRevenue).filter(
        UsageRevenue.organization_id == org_id,
        UsageRevenue.revenue_date >= start_date
    ).order_by(UsageRevenue.revenue_date.desc()).all()

    total = sum(float(r.amount) for r in revenue)

    # Group by type
    by_type = {}
    for r in revenue:
        by_type[r.revenue_type] = by_type.get(r.revenue_type, 0) + float(r.amount)

    return {
        "period_days": days,
        "total": total,
        "by_type": by_type,
        "records": [
            {
                "id": str(r.id),
                "date": r.revenue_date.isoformat(),
                "type": r.revenue_type,
                "amount": float(r.amount),
                "description": r.description,
            }
            for r in revenue
        ]
    }


@router.post("/revenue/usage", response_model=UsageRevenueResponse)
async def record_usage_revenue(
    data: UsageRevenueCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Record usage-based revenue."""
    org_id = get_organization_id(request)

    record = UsageRevenue(
        organization_id=org_id,
        **data.model_dump()
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/revenue/by-segment")
async def get_revenue_by_segment(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get revenue breakdown by customer segment."""
    org_id = get_organization_id(request)

    segments = db.query(
        SubscriptionRevenue.subscription_tier,
        func.count(SubscriptionRevenue.id).label("count"),
        func.sum(SubscriptionRevenue.mrr).label("mrr")
    ).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).group_by(SubscriptionRevenue.subscription_tier).all()

    return [
        {
            "segment": s.subscription_tier,
            "customer_count": s.count,
            "mrr": float(s.mrr or 0),
            "arr": float(s.mrr or 0) * 12
        }
        for s in segments
    ]


# =============================================================================
# FORECASTING ENDPOINTS
# =============================================================================

@router.get("/forecasts", response_model=List[ForecastResponse])
async def list_forecasts(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all saved forecasts."""
    org_id = get_organization_id(request)

    return db.query(BusinessForecast).filter(
        BusinessForecast.organization_id == org_id
    ).order_by(BusinessForecast.created_at.desc()).all()


@router.post("/forecasts", response_model=ForecastResponse)
async def create_forecast(
    data: ForecastCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create and save a new forecast."""
    org_id = get_organization_id(request)

    # Calculate projections
    projections = calculate_forecast_projections(data.parameters, data.projection_months)
    summary = calculate_forecast_summary(projections)

    forecast = BusinessForecast(
        organization_id=org_id,
        forecast_name=data.forecast_name,
        forecast_type=data.forecast_type,
        description=data.description,
        base_month=data.base_month,
        projection_months=data.projection_months,
        parameters=data.parameters.model_dump(),
        monthly_projections=projections,
        summary=summary,
        is_primary=data.is_primary,
    )
    db.add(forecast)
    db.commit()
    db.refresh(forecast)
    return forecast


@router.post("/forecasts/calculate")
async def calculate_forecast(
    data: ForecastCreate,
    request: Request
):
    """Calculate forecast without saving."""
    projections = calculate_forecast_projections(data.parameters, data.projection_months)
    summary = calculate_forecast_summary(projections)

    return {
        "parameters": data.parameters.model_dump(),
        "monthly_projections": projections,
        "summary": summary
    }


@router.post("/forecasts/scenario")
async def calculate_scenario(
    data: ScenarioRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Calculate what-if scenario."""
    org_id = get_organization_id(request)

    # Get base forecast if provided
    base_params = {}
    if data.base_forecast_id:
        base = db.query(BusinessForecast).filter(
            BusinessForecast.id == data.base_forecast_id,
            BusinessForecast.organization_id == org_id
        ).first()
        if base:
            base_params = base.parameters.copy()

    # Apply changes
    scenario_params = {**base_params, **data.changes}
    params = ForecastParameters(**scenario_params)

    projections = calculate_forecast_projections(params, 12)
    summary = calculate_forecast_summary(projections)

    return {
        "scenario_name": data.scenario_name,
        "changes_applied": data.changes,
        "parameters": params.model_dump(),
        "monthly_projections": projections,
        "summary": summary
    }


def calculate_forecast_projections(params: ForecastParameters, months: int) -> List[Dict]:
    """Calculate monthly forecast projections."""
    projections = []

    mrr = float(params.starting_mrr or 0)
    customers = params.starting_customers or 0
    cash = float(params.starting_cash or 0)

    for i in range(months):
        month_date = date.today().replace(day=1) + timedelta(days=32 * i)
        month_str = month_date.strftime("%Y-%m")

        # New customers
        new_customers = params.new_customers_monthly
        churned = int(customers * params.churn_rate)
        customers = customers + new_customers - churned

        # Revenue
        new_mrr = float(params.avg_mrr_per_customer) * new_customers
        churned_mrr = mrr * params.churn_rate
        mrr = mrr + new_mrr - churned_mrr

        # Expenses (simplified)
        expenses = mrr * 0.6  # 60% expense ratio assumption

        # Cash
        net = mrr - expenses
        cash = cash + net

        projections.append({
            "month": month_str,
            "revenue": round(mrr, 2),
            "expenses": round(expenses, 2),
            "net": round(net, 2),
            "mrr": round(mrr, 2),
            "customers": customers,
            "new_customers": new_customers,
            "churned": churned,
            "cash": round(cash, 2)
        })

    return projections


def calculate_forecast_summary(projections: List[Dict]) -> Dict:
    """Calculate summary from projections."""
    if not projections:
        return {}

    # Find break-even month (first month with positive net)
    break_even_month = None
    for p in projections:
        if p["net"] > 0:
            break_even_month = p["month"]
            break

    # Cash runway
    last_projection = projections[-1]
    avg_burn = sum(p["expenses"] - p["revenue"] for p in projections[:3]) / 3
    runway = int(last_projection["cash"] / abs(avg_burn)) if avg_burn < 0 else 999

    return {
        "break_even_month": break_even_month,
        "cash_runway_months": runway,
        "year_end_mrr": projections[-1]["mrr"],
        "year_end_arr": projections[-1]["mrr"] * 12,
        "year_end_customers": projections[-1]["customers"],
        "total_revenue": sum(p["revenue"] for p in projections),
        "total_expenses": sum(p["expenses"] for p in projections),
    }


# =============================================================================
# MARKETING ENDPOINTS
# =============================================================================

@router.get("/marketing/campaigns", response_model=List[CampaignResponse])
async def list_campaigns(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List marketing campaigns."""
    org_id = get_organization_id(request)

    query = db.query(MarketingCampaign).filter(
        MarketingCampaign.organization_id == org_id
    )

    if status:
        query = query.filter(MarketingCampaign.status == status)

    return query.order_by(MarketingCampaign.start_date.desc()).all()


@router.post("/marketing/campaigns", response_model=CampaignResponse)
async def create_campaign(
    data: CampaignCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a marketing campaign."""
    org_id = get_organization_id(request)

    campaign = MarketingCampaign(
        organization_id=org_id,
        status="draft",
        **data.model_dump()
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/marketing/metrics")
async def get_marketing_metrics(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Get marketing performance metrics."""
    org_id = get_organization_id(request)
    start_date = date.today() - timedelta(days=days)

    metrics = db.query(MarketingMetrics).filter(
        MarketingMetrics.organization_id == org_id,
        MarketingMetrics.metric_date >= start_date
    ).all()

    # Aggregate
    total_spend = sum(float(m.spend or 0) for m in metrics)
    total_leads = sum(m.leads_generated or 0 for m in metrics)
    total_conversions = sum(m.conversions or 0 for m in metrics)
    total_revenue = sum(float(m.attributed_revenue or 0) for m in metrics)

    return {
        "period_days": days,
        "totals": {
            "spend": total_spend,
            "leads": total_leads,
            "conversions": total_conversions,
            "attributed_revenue": total_revenue,
            "cpl": round(total_spend / total_leads, 2) if total_leads > 0 else 0,
            "cac": round(total_spend / total_conversions, 2) if total_conversions > 0 else 0,
            "roas": round(total_revenue / total_spend, 2) if total_spend > 0 else 0,
        },
        "daily": [
            {
                "date": m.metric_date.isoformat(),
                "spend": float(m.spend or 0),
                "leads": m.leads_generated,
                "conversions": m.conversions,
            }
            for m in sorted(metrics, key=lambda x: x.metric_date)
        ]
    }


@router.get("/marketing/cac")
async def get_cac_analysis(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get CAC (Customer Acquisition Cost) analysis."""
    org_id = get_organization_id(request)
    month_start, month_end = get_current_month_range()

    # By channel
    by_channel = db.query(
        MarketingMetrics.channel,
        func.sum(MarketingMetrics.spend).label("spend"),
        func.sum(MarketingMetrics.conversions).label("conversions")
    ).filter(
        MarketingMetrics.organization_id == org_id,
        MarketingMetrics.metric_date >= month_start,
        MarketingMetrics.metric_date <= month_end
    ).group_by(MarketingMetrics.channel).all()

    channel_cac = {}
    total_spend = 0
    total_conversions = 0

    for c in by_channel:
        spend = float(c.spend or 0)
        convs = c.conversions or 0
        total_spend += spend
        total_conversions += convs
        cac = round(spend / convs, 2) if convs > 0 else 0
        channel_cac[c.channel] = cac

    overall_cac = round(total_spend / total_conversions, 2) if total_conversions > 0 else 0

    return {
        "overall_cac": overall_cac,
        "by_channel": channel_cac,
        "total_spend": total_spend,
        "total_conversions": total_conversions
    }


@router.get("/marketing/ltv")
async def get_ltv_analysis(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get LTV (Lifetime Value) analysis."""
    org_id = get_organization_id(request)

    # Get average MRR
    avg_mrr = db.query(
        func.avg(SubscriptionRevenue.mrr)
    ).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or Decimal("0")

    # Estimate churn rate (simplified)
    total_active = db.query(func.count(SubscriptionRevenue.id)).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or 1

    churned_last_90d = db.query(func.count(SubscriptionRevenue.id)).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "churned",
        SubscriptionRevenue.churn_date >= date.today() - timedelta(days=90)
    ).scalar() or 0

    monthly_churn = (churned_last_90d / 3) / total_active if total_active > 0 else 0.05
    avg_lifespan = 1 / monthly_churn if monthly_churn > 0 else 20  # months

    ltv = float(avg_mrr) * avg_lifespan

    # By segment
    by_segment = db.query(
        SubscriptionRevenue.subscription_tier,
        func.avg(SubscriptionRevenue.mrr).label("avg_mrr")
    ).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).group_by(SubscriptionRevenue.subscription_tier).all()

    segment_ltv = {s.subscription_tier: round(float(s.avg_mrr or 0) * avg_lifespan, 2) for s in by_segment}

    return {
        "overall_ltv": round(ltv, 2),
        "by_segment": segment_ltv,
        "avg_customer_lifespan_months": round(avg_lifespan, 1),
        "arpu": float(avg_mrr),
        "monthly_churn_rate": round(monthly_churn * 100, 2)
    }


@router.get("/marketing/roi")
async def get_marketing_roi(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get marketing ROI by channel."""
    org_id = get_organization_id(request)
    start_date = date.today() - timedelta(days=90)

    by_channel = db.query(
        MarketingMetrics.channel,
        func.sum(MarketingMetrics.spend).label("spend"),
        func.sum(MarketingMetrics.attributed_revenue).label("revenue"),
        func.sum(MarketingMetrics.conversions).label("conversions"),
        func.sum(MarketingMetrics.leads_generated).label("leads")
    ).filter(
        MarketingMetrics.organization_id == org_id,
        MarketingMetrics.metric_date >= start_date
    ).group_by(MarketingMetrics.channel).all()

    channel_data = {}
    best_channel = None
    best_roas = 0

    for c in by_channel:
        spend = float(c.spend or 0)
        revenue = float(c.revenue or 0)
        roas = round(revenue / spend, 2) if spend > 0 else 0

        channel_data[c.channel] = {
            "spend": spend,
            "revenue": revenue,
            "roas": roas,
            "conversions": c.conversions or 0,
            "leads": c.leads or 0,
        }

        if roas > best_roas:
            best_roas = roas
            best_channel = c.channel

    return {
        "overall_roas": round(sum(float(c.revenue or 0) for c in by_channel) / sum(float(c.spend or 1) for c in by_channel), 2),
        "by_channel": channel_data,
        "best_performing": best_channel,
    }


# =============================================================================
# P&L ENDPOINTS
# =============================================================================

@router.get("/pnl")
async def get_pnl(
    request: Request,
    month: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get Profit & Loss statement."""
    org_id = get_organization_id(request)

    if month:
        period_start = datetime.strptime(month, "%Y-%m").date()
    else:
        period_start = date.today().replace(day=1)

    if period_start.month == 12:
        period_end = date(period_start.year + 1, 1, 1) - timedelta(days=1)
    else:
        period_end = date(period_start.year, period_start.month + 1, 1) - timedelta(days=1)

    # Revenue
    subscription_rev = db.query(
        func.sum(SubscriptionRevenue.mrr)
    ).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or Decimal("0")

    usage_rev = db.query(
        func.sum(UsageRevenue.amount)
    ).filter(
        UsageRevenue.organization_id == org_id,
        UsageRevenue.revenue_date >= period_start,
        UsageRevenue.revenue_date <= period_end
    ).scalar() or Decimal("0")

    total_revenue = float(subscription_rev) + float(usage_rev)

    # Expenses by category
    expenses = db.query(
        ServiceProvider.category,
        func.sum(ServiceUsageRecord.total_cost).label("total")
    ).join(ServiceUsageRecord).filter(
        ServiceProvider.organization_id == org_id,
        ServiceUsageRecord.usage_date >= period_start,
        ServiceUsageRecord.usage_date <= period_end
    ).group_by(ServiceProvider.category).all()

    expense_breakdown = {e.category: float(e.total or 0) for e in expenses}
    total_expenses = sum(expense_breakdown.values())

    gross_profit = total_revenue - total_expenses
    gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "revenue": {
            "subscription": float(subscription_rev),
            "usage": float(usage_rev),
        },
        "total_revenue": total_revenue,
        "expenses": expense_breakdown,
        "total_expenses": total_expenses,
        "gross_profit": gross_profit,
        "gross_margin": round(gross_margin, 2),
        "net_profit": gross_profit,  # Simplified
        "net_margin": round(gross_margin, 2),
    }


@router.get("/pnl/monthly")
async def get_monthly_pnl_trend(
    request: Request,
    months: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db)
):
    """Get monthly P&L trend."""
    org_id = get_organization_id(request)

    trend = []
    for i in range(months - 1, -1, -1):
        month_date = date.today().replace(day=1) - timedelta(days=32 * i)
        month_start = month_date.replace(day=1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)

        # Get revenue for this month
        revenue = float(db.query(
            func.sum(UsageRevenue.amount)
        ).filter(
            UsageRevenue.organization_id == org_id,
            UsageRevenue.revenue_date >= month_start,
            UsageRevenue.revenue_date <= month_end
        ).scalar() or 0)

        # Get expenses for this month
        expenses = float(db.query(
            func.sum(ServiceUsageRecord.total_cost)
        ).join(ServiceProvider).filter(
            ServiceProvider.organization_id == org_id,
            ServiceUsageRecord.usage_date >= month_start,
            ServiceUsageRecord.usage_date <= month_end
        ).scalar() or 0)

        trend.append({
            "month": month_start.strftime("%Y-%m"),
            "revenue": revenue,
            "expenses": expenses,
            "net": revenue - expenses,
            "margin": round((revenue - expenses) / revenue * 100, 2) if revenue > 0 else 0
        })

    return {"months": months, "trend": trend}


@router.get("/runway")
async def get_runway_analysis(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get cash runway analysis."""
    org_id = get_organization_id(request)

    # Get latest KPI for cash balance
    kpi = db.query(BusinessKPI).filter(
        BusinessKPI.organization_id == org_id
    ).order_by(BusinessKPI.snapshot_date.desc()).first()

    cash_balance = float(kpi.cash_balance or 0) if kpi else 100000  # Default assumption

    # Calculate average monthly burn (last 3 months)
    three_months_ago = date.today() - timedelta(days=90)

    total_revenue = float(db.query(
        func.sum(UsageRevenue.amount)
    ).filter(
        UsageRevenue.organization_id == org_id,
        UsageRevenue.revenue_date >= three_months_ago
    ).scalar() or 0) / 3

    total_expenses = float(db.query(
        func.sum(ServiceUsageRecord.total_cost)
    ).join(ServiceProvider).filter(
        ServiceProvider.organization_id == org_id,
        ServiceUsageRecord.usage_date >= three_months_ago
    ).scalar() or 0) / 3

    monthly_burn = total_expenses - total_revenue
    runway_months = cash_balance / abs(monthly_burn) if monthly_burn < 0 else 999

    # Project forward
    projections = []
    current_cash = cash_balance
    for i in range(12):
        month_date = date.today().replace(day=1) + timedelta(days=32 * i)
        current_cash = current_cash - monthly_burn
        projections.append({
            "month": month_date.strftime("%Y-%m"),
            "cash_balance": max(0, round(current_cash, 2)),
            "burn": round(monthly_burn, 2)
        })

    return {
        "cash_balance": cash_balance,
        "monthly_burn_rate": round(monthly_burn, 2),
        "runway_months": round(runway_months, 1),
        "monthly_projections": projections
    }


@router.get("/break-even")
async def get_break_even_analysis(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get break-even analysis."""
    org_id = get_organization_id(request)

    # Current MRR
    current_mrr = float(db.query(
        func.sum(SubscriptionRevenue.mrr)
    ).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or 0)

    # Current monthly costs
    month_start, month_end = get_current_month_range()
    current_costs = float(db.query(
        func.sum(ServiceUsageRecord.total_cost)
    ).join(ServiceProvider).filter(
        ServiceProvider.organization_id == org_id,
        ServiceUsageRecord.usage_date >= month_start,
        ServiceUsageRecord.usage_date <= month_end
    ).scalar() or 0)

    # Average MRR per customer
    avg_mrr = float(db.query(
        func.avg(SubscriptionRevenue.mrr)
    ).filter(
        SubscriptionRevenue.organization_id == org_id,
        SubscriptionRevenue.status == "active"
    ).scalar() or 199)

    # Break-even calculation
    break_even_mrr = current_costs
    mrr_gap = break_even_mrr - current_mrr
    customers_needed = int(mrr_gap / avg_mrr) if avg_mrr > 0 and mrr_gap > 0 else 0

    return {
        "current_mrr": current_mrr,
        "current_costs": current_costs,
        "break_even_mrr": break_even_mrr,
        "mrr_gap": max(0, mrr_gap),
        "customers_needed": max(0, customers_needed),
        "avg_mrr_per_customer": avg_mrr,
        "is_profitable": current_mrr >= current_costs
    }


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@router.get("/admin/run-migration")
async def run_business_ops_migration(
    admin_key: str = Query(..., description="Admin API key for authorization"),
    db: Session = Depends(get_db)
):
    """
    Run the business operations migration to create tables and seed data.
    This endpoint is for initial deployment setup.
    """
    import os
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from sqlalchemy import text, inspect

        # Check if tables already exist
        inspector = inspect(db.get_bind())
        existing_tables = inspector.get_table_names()

        if 'service_providers' in existing_tables:
            # Tables exist, check if seeded
            count = db.execute(text("SELECT COUNT(*) FROM service_providers")).scalar()
            if count > 0:
                return {
                    "status": "already_exists",
                    "message": f"Business operations tables already exist with {count} service providers",
                    "tables": [t for t in existing_tables if t in [
                        'service_providers', 'service_usage_records', 'service_invoices',
                        'subscription_revenue', 'usage_revenue', 'marketing_campaigns',
                        'marketing_metrics', 'business_forecasts', 'business_kpis', 'budget_alerts'
                    ]]
                }

        # Run migration
        from migrations.add_business_operations_tables import run_migration
        run_migration()

        # Verify
        inspector = inspect(db.get_bind())
        new_tables = inspector.get_table_names()
        created = [t for t in new_tables if t in [
            'service_providers', 'service_usage_records', 'service_invoices',
            'subscription_revenue', 'usage_revenue', 'marketing_campaigns',
            'marketing_metrics', 'business_forecasts', 'business_kpis', 'budget_alerts'
        ]]

        return {
            "status": "success",
            "message": f"Migration completed successfully. Created {len(created)} tables.",
            "tables_created": created
        }

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Migration failed")
