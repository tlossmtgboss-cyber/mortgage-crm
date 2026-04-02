"""
Portal Home Value Service - Property valuation and equity intelligence.

Handles home price index tracking, property value estimation,
equity calculations, and value insights for the MUM portal.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc

from models.portal_models import (
    HomePriceIndex, PropertyValueBaseline, PropertyValuation,
    HomeValueInsight, PortalLoan
)

logger = logging.getLogger(__name__)


# HPI data sources and their weights for blended estimates
HPI_SOURCES = {
    "fhfa": {"name": "FHFA HPI", "weight": 0.5},
    "zillow": {"name": "Zillow ZHVI", "weight": 0.3},
    "corelogic": {"name": "CoreLogic HPI", "weight": 0.2},
}

# Default appreciation rate if no HPI data available
DEFAULT_ANNUAL_APPRECIATION = Decimal("0.035")  # 3.5%


class PortalHomeValueService:
    """Service for home value intelligence and equity tracking."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # HOME PRICE INDEX MANAGEMENT
    # =========================================================================

    def import_hpi_data(
        self,
        source: str,
        region_type: str,
        region_code: str,
        period_date: date,
        index_value: Decimal,
        year_over_year_change: Optional[Decimal] = None,
        month_over_month_change: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Import home price index data point."""
        # Check for existing
        existing = self.db.query(HomePriceIndex).filter(
            and_(
                HomePriceIndex.source == source,
                HomePriceIndex.region_type == region_type,
                HomePriceIndex.region_code == region_code,
                HomePriceIndex.period_date == period_date
            )
        ).first()

        if existing:
            existing.index_value = index_value
            existing.year_over_year_change = year_over_year_change
            existing.month_over_month_change = month_over_month_change
            hpi = existing
        else:
            hpi = HomePriceIndex(
                source=source,
                region_type=region_type,
                region_code=region_code,
                period_date=period_date,
                index_value=index_value,
                year_over_year_change=year_over_year_change,
                month_over_month_change=month_over_month_change,
            )
            self.db.add(hpi)

        self.db.commit()

        return {
            "success": True,
            "hpi_id": hpi.id,
            "source": source,
            "region": f"{region_type}:{region_code}",
            "period": period_date.isoformat(),
        }

    def get_latest_hpi(
        self,
        region_type: str,
        region_code: str,
        source: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get latest HPI data for a region."""
        query = self.db.query(HomePriceIndex).filter(
            and_(
                HomePriceIndex.region_type == region_type,
                HomePriceIndex.region_code == region_code
            )
        )

        if source:
            query = query.filter(HomePriceIndex.source == source)

        hpi = query.order_by(desc(HomePriceIndex.period_date)).first()

        if not hpi:
            return None

        return {
            "source": hpi.source,
            "region_type": hpi.region_type,
            "region_code": hpi.region_code,
            "period_date": hpi.period_date.isoformat(),
            "index_value": float(hpi.index_value),
            "yoy_change": float(hpi.year_over_year_change) if hpi.year_over_year_change else None,
            "mom_change": float(hpi.month_over_month_change) if hpi.month_over_month_change else None,
        }

    def get_hpi_history(
        self,
        region_type: str,
        region_code: str,
        source: Optional[str] = None,
        months: int = 24,
    ) -> List[Dict[str, Any]]:
        """Get HPI history for a region."""
        cutoff_date = date.today() - timedelta(days=months * 30)

        query = self.db.query(HomePriceIndex).filter(
            and_(
                HomePriceIndex.region_type == region_type,
                HomePriceIndex.region_code == region_code,
                HomePriceIndex.period_date >= cutoff_date
            )
        )

        if source:
            query = query.filter(HomePriceIndex.source == source)

        history = query.order_by(HomePriceIndex.period_date).all()

        return [
            {
                "source": h.source,
                "period_date": h.period_date.isoformat(),
                "index_value": float(h.index_value),
                "yoy_change": float(h.year_over_year_change) if h.year_over_year_change else None,
            }
            for h in history
        ]

    # =========================================================================
    # PROPERTY VALUE BASELINE
    # =========================================================================

    def set_property_baseline(
        self,
        loan_id: int,
        baseline_value: Decimal,
        baseline_date: date,
        baseline_source: str,
        property_state: str,
        property_county: Optional[str] = None,
        property_zip: Optional[str] = None,
        property_msa: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Set property value baseline (typically from appraisal at closing)."""
        # Check for existing baseline
        existing = self.db.query(PropertyValueBaseline).filter(
            PropertyValueBaseline.loan_id == loan_id
        ).first()

        if existing:
            existing.baseline_value = baseline_value
            existing.baseline_date = baseline_date
            existing.baseline_source = baseline_source
            existing.property_state = property_state
            existing.property_county = property_county
            existing.property_zip = property_zip
            existing.property_msa = property_msa
            baseline = existing
        else:
            baseline = PropertyValueBaseline(
                loan_id=loan_id,
                baseline_value=baseline_value,
                baseline_date=baseline_date,
                baseline_source=baseline_source,
                property_state=property_state,
                property_county=property_county,
                property_zip=property_zip,
                property_msa=property_msa,
            )
            self.db.add(baseline)

        self.db.commit()
        self.db.refresh(baseline)

        logger.info(f"Set property baseline for loan {loan_id}: ${baseline_value:,.0f}")

        return {
            "success": True,
            "baseline_id": baseline.id,
            "baseline_value": float(baseline_value),
            "baseline_date": baseline_date.isoformat(),
        }

    def get_property_baseline(self, loan_id: int) -> Optional[Dict[str, Any]]:
        """Get property value baseline for a loan."""
        baseline = self.db.query(PropertyValueBaseline).filter(
            PropertyValueBaseline.loan_id == loan_id
        ).first()

        if not baseline:
            return None

        return {
            "id": baseline.id,
            "baseline_value": float(baseline.baseline_value),
            "baseline_date": baseline.baseline_date.isoformat(),
            "baseline_source": baseline.baseline_source,
            "property_state": baseline.property_state,
            "property_county": baseline.property_county,
            "property_zip": baseline.property_zip,
            "property_msa": baseline.property_msa,
        }

    # =========================================================================
    # PROPERTY VALUATION
    # =========================================================================

    def calculate_current_value(
        self,
        loan_id: int,
        save_valuation: bool = True,
    ) -> Dict[str, Any]:
        """Calculate current property value based on HPI appreciation."""
        baseline = self.db.query(PropertyValueBaseline).filter(
            PropertyValueBaseline.loan_id == loan_id
        ).first()

        if not baseline:
            return {
                "success": False,
                "error": "No property baseline found for this loan",
            }

        # Get HPI data for region (try MSA, then county, then state)
        hpi_data = None
        region_used = None

        if baseline.property_msa:
            hpi_data = self.get_latest_hpi("msa", baseline.property_msa)
            region_used = f"MSA:{baseline.property_msa}"

        if not hpi_data and baseline.property_county:
            hpi_data = self.get_latest_hpi("county", f"{baseline.property_state}_{baseline.property_county}")
            region_used = f"County:{baseline.property_county}, {baseline.property_state}"

        if not hpi_data:
            hpi_data = self.get_latest_hpi("state", baseline.property_state)
            region_used = f"State:{baseline.property_state}"

        # Calculate appreciation
        months_since_baseline = self._months_between(baseline.baseline_date, date.today())

        if hpi_data and hpi_data.get("yoy_change"):
            # Use YoY change to calculate appreciation
            annual_rate = Decimal(str(hpi_data["yoy_change"])) / 100
            appreciation_method = "hpi_based"
        else:
            # Fallback to default rate
            annual_rate = DEFAULT_ANNUAL_APPRECIATION
            appreciation_method = "default_rate"

        # Compound monthly appreciation
        monthly_rate = (1 + float(annual_rate)) ** (1/12) - 1
        appreciation_factor = (1 + monthly_rate) ** months_since_baseline

        estimated_value = baseline.baseline_value * Decimal(str(appreciation_factor))
        appreciation_amount = estimated_value - baseline.baseline_value
        appreciation_percent = ((float(estimated_value) / float(baseline.baseline_value)) - 1) * 100

        valuation_result = {
            "baseline_value": float(baseline.baseline_value),
            "baseline_date": baseline.baseline_date.isoformat(),
            "estimated_value": float(estimated_value),
            "valuation_date": date.today().isoformat(),
            "appreciation_amount": float(appreciation_amount),
            "appreciation_percent": round(appreciation_percent, 2),
            "months_since_baseline": months_since_baseline,
            "annual_appreciation_rate": float(annual_rate) * 100,
            "appreciation_method": appreciation_method,
            "region_used": region_used,
            "confidence_level": "high" if appreciation_method == "hpi_based" else "medium",
        }

        if save_valuation:
            # Save valuation record
            valuation = PropertyValuation(
                loan_id=loan_id,
                baseline_id=baseline.id,
                valuation_date=date.today(),
                estimated_value=estimated_value,
                appreciation_since_baseline=appreciation_amount,
                appreciation_percent=Decimal(str(appreciation_percent)),
                hpi_region_used=region_used,
                hpi_value_used=Decimal(str(hpi_data["index_value"])) if hpi_data else None,
                confidence_level=valuation_result["confidence_level"],
                calculation_method=appreciation_method,
            )
            self.db.add(valuation)
            self.db.commit()
            self.db.refresh(valuation)
            valuation_result["valuation_id"] = valuation.id

        return {"success": True, **valuation_result}

    def get_valuation_history(
        self,
        loan_id: int,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        """Get historical valuations for a loan."""
        valuations = self.db.query(PropertyValuation).filter(
            PropertyValuation.loan_id == loan_id
        ).order_by(desc(PropertyValuation.valuation_date)).limit(limit).all()

        return [
            {
                "id": v.id,
                "valuation_date": v.valuation_date.isoformat(),
                "estimated_value": float(v.estimated_value),
                "appreciation_since_baseline": float(v.appreciation_since_baseline) if v.appreciation_since_baseline else 0,
                "appreciation_percent": float(v.appreciation_percent) if v.appreciation_percent else 0,
                "confidence_level": v.confidence_level,
            }
            for v in valuations
        ]

    # =========================================================================
    # EQUITY CALCULATIONS
    # =========================================================================

    def calculate_equity(
        self,
        loan_id: int,
        current_loan_balance: Decimal,
    ) -> Dict[str, Any]:
        """Calculate current equity position."""
        # Get current valuation
        valuation = self.calculate_current_value(loan_id, save_valuation=False)

        if not valuation.get("success"):
            return valuation

        estimated_value = Decimal(str(valuation["estimated_value"]))
        equity = estimated_value - current_loan_balance
        equity_percent = (float(equity) / float(estimated_value)) * 100 if estimated_value > 0 else 0
        ltv = (float(current_loan_balance) / float(estimated_value)) * 100 if estimated_value > 0 else 0

        return {
            "success": True,
            "estimated_value": float(estimated_value),
            "current_loan_balance": float(current_loan_balance),
            "equity": float(equity),
            "equity_percent": round(equity_percent, 2),
            "ltv": round(ltv, 2),
            "has_20_percent_equity": equity_percent >= 20,
            "can_remove_pmi": equity_percent >= 20,
            "valuation_date": valuation["valuation_date"],
        }

    def calculate_equity_unlock(
        self,
        loan_id: int,
        current_loan_balance: Decimal,
        max_ltv: Decimal = Decimal("0.80"),
    ) -> Dict[str, Any]:
        """Calculate potential equity available to unlock (cash-out refi)."""
        equity_data = self.calculate_equity(loan_id, current_loan_balance)

        if not equity_data.get("success"):
            return equity_data

        estimated_value = Decimal(str(equity_data["estimated_value"]))
        max_loan_amount = estimated_value * max_ltv
        available_equity = max_loan_amount - current_loan_balance

        if available_equity < 0:
            available_equity = Decimal("0")

        return {
            "success": True,
            "estimated_value": float(estimated_value),
            "current_loan_balance": float(current_loan_balance),
            "current_equity": float(equity_data["equity"]),
            "max_ltv": float(max_ltv) * 100,
            "max_loan_at_ltv": float(max_loan_amount),
            "available_cash_out": float(available_equity),
            "available_cash_out_formatted": f"${available_equity:,.0f}",
        }

    # =========================================================================
    # HOME VALUE INSIGHTS
    # =========================================================================

    def generate_insights(self, loan_id: int) -> List[Dict[str, Any]]:
        """Generate home value insights for a loan."""
        insights_to_create = []

        # Get valuation data
        valuation = self.calculate_current_value(loan_id, save_valuation=False)
        if not valuation.get("success"):
            return []

        baseline = self.get_property_baseline(loan_id)
        if not baseline:
            return []

        # Insight: Significant appreciation
        if valuation["appreciation_percent"] >= 10:
            insights_to_create.append({
                "insight_type": "appreciation_milestone",
                "title": "Strong Home Value Growth",
                "description": f"Your home has appreciated {valuation['appreciation_percent']:.1f}% since purchase, adding ${valuation['appreciation_amount']:,.0f} in value.",
                "priority": 1,
            })

        # Insight: PMI removal eligibility
        portal_loan = self.db.query(PortalLoan).filter(or_(PortalLoan.id == loan_id, PortalLoan.crm_deal_id == loan_id)).first()
        if portal_loan and portal_loan.current_loan_balance:
            equity = self.calculate_equity(loan_id, portal_loan.current_loan_balance)
            if equity.get("can_remove_pmi") and portal_loan.has_pmi:
                insights_to_create.append({
                    "insight_type": "pmi_removal",
                    "title": "You May Qualify to Remove PMI",
                    "description": f"With {equity['equity_percent']:.1f}% equity, you may be eligible to remove private mortgage insurance and save money.",
                    "priority": 1,
                })

        # Insight: Cash-out potential
        if portal_loan and portal_loan.current_loan_balance:
            cash_out = self.calculate_equity_unlock(loan_id, portal_loan.current_loan_balance)
            if cash_out.get("available_cash_out", 0) >= 25000:
                insights_to_create.append({
                    "insight_type": "cash_out_potential",
                    "title": "Equity Available to Tap",
                    "description": f"You have up to {cash_out['available_cash_out_formatted']} in tappable equity that could be used for home improvements, debt consolidation, or other needs.",
                    "priority": 2,
                })

        # Insight: Market conditions
        hpi_history = self.get_hpi_history(
            baseline["property_state"], baseline["property_state"][:2],
            months=6
        )
        if hpi_history and len(hpi_history) >= 3:
            recent_trend = hpi_history[-1].get("yoy_change", 0) if hpi_history else 0
            if recent_trend and recent_trend > 5:
                insights_to_create.append({
                    "insight_type": "market_trend",
                    "title": "Strong Local Market",
                    "description": f"Home values in your area have increased {recent_trend:.1f}% over the past year, outpacing the national average.",
                    "priority": 3,
                })

        # Save insights
        saved_insights = []
        for insight_data in insights_to_create:
            # Check if similar insight already exists
            existing = self.db.query(HomeValueInsight).filter(
                and_(
                    HomeValueInsight.loan_id == loan_id,
                    HomeValueInsight.insight_type == insight_data["insight_type"],
                    HomeValueInsight.is_active == True
                )
            ).first()

            if not existing:
                insight = HomeValueInsight(
                    loan_id=loan_id,
                    insight_type=insight_data["insight_type"],
                    title=insight_data["title"],
                    description=insight_data["description"],
                    priority=insight_data["priority"],
                    is_active=True,
                )
                self.db.add(insight)
                saved_insights.append(insight_data)

        self.db.commit()

        return saved_insights

    def get_active_insights(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get active home value insights for a loan."""
        insights = self.db.query(HomeValueInsight).filter(
            and_(
                HomeValueInsight.loan_id == loan_id,
                HomeValueInsight.is_active == True,
                HomeValueInsight.dismissed_at.is_(None)
            )
        ).order_by(HomeValueInsight.priority).all()

        return [
            {
                "id": i.id,
                "type": i.insight_type,
                "title": i.title,
                "description": i.description,
                "priority": i.priority,
                "created_at": i.created_at.isoformat(),
                "action_url": i.action_url,
            }
            for i in insights
        ]

    def dismiss_insight(self, insight_id: int) -> Dict[str, Any]:
        """Dismiss a home value insight."""
        insight = self.db.query(HomeValueInsight).filter(
            HomeValueInsight.id == insight_id
        ).first()

        if not insight:
            return {"success": False, "error": "Insight not found"}

        insight.dismissed_at = datetime.now(timezone.utc)
        self.db.commit()

        return {"success": True}

    # =========================================================================
    # DASHBOARD DATA
    # =========================================================================

    def get_home_value_dashboard(self, loan_id: int) -> Dict[str, Any]:
        """Get complete home value dashboard data."""
        baseline = self.get_property_baseline(loan_id)

        if not baseline:
            return {
                "has_baseline": False,
                "message": "Property value baseline not set",
            }

        valuation = self.calculate_current_value(loan_id, save_valuation=True)
        insights = self.get_active_insights(loan_id)
        history = self.get_valuation_history(loan_id, limit=6)

        # Get equity if loan balance available
        portal_loan = self.db.query(PortalLoan).filter(or_(PortalLoan.id == loan_id, PortalLoan.crm_deal_id == loan_id)).first()
        equity_data = None
        if portal_loan and portal_loan.current_loan_balance:
            equity_data = self.calculate_equity(loan_id, portal_loan.current_loan_balance)

        return {
            "has_baseline": True,
            "baseline": baseline,
            "current_valuation": valuation if valuation.get("success") else None,
            "equity": equity_data if equity_data and equity_data.get("success") else None,
            "insights": insights,
            "valuation_history": history,
            "chart_data": {
                "labels": [h["valuation_date"] for h in reversed(history)],
                "values": [h["estimated_value"] for h in reversed(history)],
            },
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _months_between(self, start_date: date, end_date: date) -> int:
        """Calculate months between two dates."""
        return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
