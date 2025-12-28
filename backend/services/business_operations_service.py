"""
Business Operations Service

Provides business logic for:
- Service cost tracking and monitoring
- Revenue analysis (subscription + usage)
- Forecasting and scenarios
- Marketing analytics (CAC, LTV, ROI)
- KPI snapshots
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from models.business_operations import (
    ServiceProvider, ServiceUsageRecord, ServiceInvoice,
    SubscriptionRevenue, UsageRevenue,
    MarketingCampaign, MarketingMetrics,
    BusinessForecast, BusinessKPI, BudgetAlert
)


class BusinessOperationsService:
    """Main orchestrator for business operations."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.org_id = organization_id
        self.cost_tracker = ServiceCostTracker(db, organization_id)
        self.revenue_analyzer = RevenueAnalyzer(db, organization_id)
        self.forecast_engine = ForecastEngine(db, organization_id)
        self.marketing_analytics = MarketingAnalytics(db, organization_id)

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get complete dashboard data."""
        return {
            "kpis": self.get_current_kpis(),
            "revenue": self.revenue_analyzer.get_summary(),
            "costs": self.cost_tracker.get_summary(),
            "alerts": self.cost_tracker.get_active_alerts(),
        }

    def get_current_kpis(self) -> Dict[str, Any]:
        """Get current KPIs."""
        kpi = self.db.query(BusinessKPI).filter(
            BusinessKPI.organization_id == self.org_id
        ).order_by(BusinessKPI.snapshot_date.desc()).first()

        if not kpi:
            return self._calculate_kpis()

        return {
            "snapshot_date": kpi.snapshot_date.isoformat(),
            "mrr": float(kpi.mrr or 0),
            "arr": float(kpi.arr or 0),
            "total_customers": kpi.total_customers,
            "churn_rate": float(kpi.churn_rate or 0),
            "service_costs": float(kpi.service_costs or 0),
            "gross_margin": float(kpi.gross_margin or 0),
            "cash_runway_months": float(kpi.cash_runway_months or 0),
            "ltv_cac_ratio": float(kpi.ltv_cac_ratio or 0),
        }

    def _calculate_kpis(self) -> Dict[str, Any]:
        """Calculate KPIs from current data."""
        revenue_summary = self.revenue_analyzer.get_summary()
        cost_summary = self.cost_tracker.get_summary()

        mrr = revenue_summary.get("mrr", 0)
        total_costs = cost_summary.get("total_costs_mtd", 0)

        gross_margin = 0
        if mrr > 0:
            gross_margin = ((mrr - total_costs) / mrr) * 100

        return {
            "snapshot_date": date.today().isoformat(),
            "mrr": mrr,
            "arr": mrr * 12,
            "total_customers": revenue_summary.get("subscription_count", 0),
            "churn_rate": 0,
            "service_costs": total_costs,
            "gross_margin": round(gross_margin, 2),
            "cash_runway_months": 0,
            "ltv_cac_ratio": 0,
        }

    def create_kpi_snapshot(self) -> BusinessKPI:
        """Create a KPI snapshot for today."""
        today = date.today()

        # Check if snapshot exists
        existing = self.db.query(BusinessKPI).filter(
            BusinessKPI.organization_id == self.org_id,
            BusinessKPI.snapshot_date == today
        ).first()

        if existing:
            return existing

        # Calculate all KPIs
        revenue = self.revenue_analyzer.get_summary()
        costs = self.cost_tracker.get_summary()
        marketing = self.marketing_analytics.get_cac_ltv()

        mrr = Decimal(str(revenue.get("mrr", 0)))
        total_costs = Decimal(str(costs.get("total_costs_mtd", 0)))
        gross_profit = mrr - total_costs
        gross_margin = (gross_profit / mrr) if mrr > 0 else Decimal("0")

        kpi = BusinessKPI(
            organization_id=self.org_id,
            snapshot_date=today,
            mrr=mrr,
            arr=mrr * 12,
            total_revenue_mtd=mrr + Decimal(str(revenue.get("usage_revenue_mtd", 0))),
            total_customers=revenue.get("subscription_count", 0),
            service_costs=total_costs,
            gross_profit=gross_profit,
            gross_margin=gross_margin,
            net_profit=gross_profit,
            net_margin=gross_margin,
            cac=Decimal(str(marketing.get("cac", 0))),
            ltv=Decimal(str(marketing.get("ltv", 0))),
            ltv_cac_ratio=Decimal(str(marketing.get("ltv_cac_ratio", 0))),
            service_cost_breakdown=costs.get("by_category", {}),
        )

        self.db.add(kpi)
        self.db.commit()
        self.db.refresh(kpi)
        return kpi


class ServiceCostTracker:
    """Tracks and analyzes service costs."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.org_id = organization_id

    def get_summary(self) -> Dict[str, Any]:
        """Get cost summary for current month."""
        month_start = date.today().replace(day=1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)

        # Total costs
        total = self.db.query(
            func.sum(ServiceUsageRecord.total_cost)
        ).join(ServiceProvider).filter(
            ServiceProvider.organization_id == self.org_id,
            ServiceUsageRecord.usage_date >= month_start,
            ServiceUsageRecord.usage_date <= month_end
        ).scalar() or Decimal("0")

        # By category
        by_category = self.db.query(
            ServiceProvider.category,
            func.sum(ServiceUsageRecord.total_cost).label("total")
        ).join(ServiceUsageRecord).filter(
            ServiceProvider.organization_id == self.org_id,
            ServiceUsageRecord.usage_date >= month_start,
            ServiceUsageRecord.usage_date <= month_end
        ).group_by(ServiceProvider.category).all()

        return {
            "total_costs_mtd": float(total),
            "service_costs_mtd": float(total),
            "by_category": {row.category: float(row.total or 0) for row in by_category},
        }

    def get_service_costs(self, service_id: str, days: int = 30) -> Dict[str, Any]:
        """Get costs for a specific service."""
        start_date = date.today() - timedelta(days=days)

        records = self.db.query(ServiceUsageRecord).filter(
            ServiceUsageRecord.service_provider_id == service_id,
            ServiceUsageRecord.usage_date >= start_date
        ).all()

        total = sum(float(r.total_cost) for r in records)
        total_quantity = sum(float(r.quantity) for r in records)

        return {
            "total_cost": total,
            "total_quantity": total_quantity,
            "record_count": len(records),
            "daily_average": total / days if days > 0 else 0,
        }

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active budget alerts."""
        alerts = self.db.query(BudgetAlert).filter(
            BudgetAlert.organization_id == self.org_id,
            BudgetAlert.status == "active"
        ).all()

        return [
            {
                "id": str(a.id),
                "type": a.alert_type,
                "threshold": a.threshold_percent,
                "current_spend": float(a.current_spend),
                "budget": float(a.budget_amount),
                "percent_used": round(float(a.current_spend / a.budget_amount * 100), 1),
            }
            for a in alerts
        ]

    def check_budgets(self):
        """Check all service budgets and create alerts."""
        month_start = date.today().replace(day=1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)

        services = self.db.query(ServiceProvider).filter(
            ServiceProvider.organization_id == self.org_id,
            ServiceProvider.is_active == True,
            ServiceProvider.monthly_budget.isnot(None)
        ).all()

        for service in services:
            current_spend = self.db.query(
                func.sum(ServiceUsageRecord.total_cost)
            ).filter(
                ServiceUsageRecord.service_provider_id == service.id,
                ServiceUsageRecord.usage_date >= month_start,
                ServiceUsageRecord.usage_date <= month_end
            ).scalar() or Decimal("0")

            percent_used = float(current_spend / service.monthly_budget * 100)

            if percent_used >= service.alert_threshold_percent:
                # Check if alert exists
                existing = self.db.query(BudgetAlert).filter(
                    BudgetAlert.service_provider_id == service.id,
                    BudgetAlert.period_start == month_start,
                    BudgetAlert.status == "active"
                ).first()

                if not existing:
                    alert = BudgetAlert(
                        organization_id=self.org_id,
                        alert_type="service_budget",
                        service_provider_id=service.id,
                        threshold_percent=service.alert_threshold_percent,
                        current_spend=current_spend,
                        budget_amount=service.monthly_budget,
                        period_start=month_start,
                        period_end=month_end,
                    )
                    self.db.add(alert)

        self.db.commit()


class RevenueAnalyzer:
    """Analyzes revenue metrics."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.org_id = organization_id

    def get_summary(self) -> Dict[str, Any]:
        """Get revenue summary."""
        month_start = date.today().replace(day=1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)

        # Subscription MRR
        mrr = self.db.query(
            func.sum(SubscriptionRevenue.mrr)
        ).filter(
            SubscriptionRevenue.organization_id == self.org_id,
            SubscriptionRevenue.status == "active"
        ).scalar() or Decimal("0")

        # Subscription count
        sub_count = self.db.query(func.count(SubscriptionRevenue.id)).filter(
            SubscriptionRevenue.organization_id == self.org_id,
            SubscriptionRevenue.status == "active"
        ).scalar() or 0

        # Usage revenue
        usage_rev = self.db.query(
            func.sum(UsageRevenue.amount)
        ).filter(
            UsageRevenue.organization_id == self.org_id,
            UsageRevenue.revenue_date >= month_start,
            UsageRevenue.revenue_date <= month_end
        ).scalar() or Decimal("0")

        return {
            "mrr": float(mrr),
            "arr": float(mrr) * 12,
            "subscription_revenue_mtd": float(mrr),
            "usage_revenue_mtd": float(usage_rev),
            "total_revenue_mtd": float(mrr) + float(usage_rev),
            "subscription_count": sub_count,
            "active_customers": sub_count,
        }

    def get_by_segment(self) -> List[Dict[str, Any]]:
        """Get revenue by customer segment."""
        segments = self.db.query(
            SubscriptionRevenue.subscription_tier,
            func.count(SubscriptionRevenue.id).label("count"),
            func.sum(SubscriptionRevenue.mrr).label("mrr")
        ).filter(
            SubscriptionRevenue.organization_id == self.org_id,
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

    def calculate_churn_rate(self, months: int = 3) -> float:
        """Calculate monthly churn rate."""
        start_date = date.today() - timedelta(days=30 * months)

        churned = self.db.query(func.count(SubscriptionRevenue.id)).filter(
            SubscriptionRevenue.organization_id == self.org_id,
            SubscriptionRevenue.status == "churned",
            SubscriptionRevenue.churn_date >= start_date
        ).scalar() or 0

        # Average active customers
        active = self.db.query(func.count(SubscriptionRevenue.id)).filter(
            SubscriptionRevenue.organization_id == self.org_id,
            SubscriptionRevenue.status == "active"
        ).scalar() or 1

        monthly_churn = (churned / months) / active if active > 0 else 0
        return round(monthly_churn * 100, 2)


class ForecastEngine:
    """Handles financial forecasting and scenarios."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.org_id = organization_id

    def calculate_projection(
        self,
        starting_mrr: float,
        starting_customers: int,
        months: int = 12,
        growth_rate: float = 0.05,
        churn_rate: float = 0.02,
        new_customers_monthly: int = 5,
        avg_mrr_per_customer: float = 199,
        expense_ratio: float = 0.6,
        starting_cash: float = 0,
    ) -> Dict[str, Any]:
        """Calculate financial projection."""
        projections = []

        mrr = starting_mrr
        customers = starting_customers
        cash = starting_cash

        for i in range(months):
            month_date = date.today().replace(day=1) + timedelta(days=32 * i)

            # Customer changes
            new = new_customers_monthly
            churned = int(customers * churn_rate)
            customers = customers + new - churned

            # Revenue changes
            new_mrr = avg_mrr_per_customer * new
            lost_mrr = mrr * churn_rate
            mrr = mrr + new_mrr - lost_mrr

            # Expenses
            expenses = mrr * expense_ratio

            # Cash
            net = mrr - expenses
            cash = cash + net

            projections.append({
                "month": month_date.strftime("%Y-%m"),
                "revenue": round(mrr, 2),
                "expenses": round(expenses, 2),
                "net": round(net, 2),
                "mrr": round(mrr, 2),
                "customers": customers,
                "new_customers": new,
                "churned": churned,
                "cash": round(cash, 2),
            })

        # Summary
        break_even_month = None
        for p in projections:
            if p["net"] > 0:
                break_even_month = p["month"]
                break

        return {
            "projections": projections,
            "summary": {
                "break_even_month": break_even_month,
                "year_end_mrr": projections[-1]["mrr"],
                "year_end_arr": projections[-1]["mrr"] * 12,
                "year_end_customers": projections[-1]["customers"],
                "total_revenue": sum(p["revenue"] for p in projections),
                "total_expenses": sum(p["expenses"] for p in projections),
                "ending_cash": projections[-1]["cash"],
            }
        }


class MarketingAnalytics:
    """Handles marketing analytics."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.org_id = organization_id

    def get_cac_ltv(self) -> Dict[str, Any]:
        """Calculate CAC and LTV."""
        # Last 90 days of marketing
        start_date = date.today() - timedelta(days=90)

        # Total spend and conversions
        metrics = self.db.query(
            func.sum(MarketingMetrics.spend).label("total_spend"),
            func.sum(MarketingMetrics.conversions).label("total_conversions")
        ).filter(
            MarketingMetrics.organization_id == self.org_id,
            MarketingMetrics.metric_date >= start_date
        ).first()

        total_spend = float(metrics.total_spend or 0)
        total_conversions = metrics.total_conversions or 0
        cac = total_spend / total_conversions if total_conversions > 0 else 0

        # LTV calculation
        avg_mrr = self.db.query(
            func.avg(SubscriptionRevenue.mrr)
        ).filter(
            SubscriptionRevenue.organization_id == self.org_id,
            SubscriptionRevenue.status == "active"
        ).scalar() or Decimal("199")

        # Estimate churn to calculate lifespan
        churn_rate = 0.03  # 3% monthly default
        avg_lifespan = 1 / churn_rate if churn_rate > 0 else 33
        ltv = float(avg_mrr) * avg_lifespan

        ltv_cac_ratio = ltv / cac if cac > 0 else 0

        return {
            "cac": round(cac, 2),
            "ltv": round(ltv, 2),
            "ltv_cac_ratio": round(ltv_cac_ratio, 2),
            "avg_customer_lifespan_months": round(avg_lifespan, 1),
        }

    def get_roi_by_channel(self) -> Dict[str, Any]:
        """Get ROI by marketing channel."""
        start_date = date.today() - timedelta(days=90)

        by_channel = self.db.query(
            MarketingMetrics.channel,
            func.sum(MarketingMetrics.spend).label("spend"),
            func.sum(MarketingMetrics.attributed_revenue).label("revenue"),
            func.sum(MarketingMetrics.conversions).label("conversions")
        ).filter(
            MarketingMetrics.organization_id == self.org_id,
            MarketingMetrics.metric_date >= start_date
        ).group_by(MarketingMetrics.channel).all()

        results = {}
        for c in by_channel:
            spend = float(c.spend or 0)
            revenue = float(c.revenue or 0)
            roas = revenue / spend if spend > 0 else 0

            results[c.channel] = {
                "spend": spend,
                "revenue": revenue,
                "roas": round(roas, 2),
                "conversions": c.conversions or 0,
            }

        return results
