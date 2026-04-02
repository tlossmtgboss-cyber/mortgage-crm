"""
Phase 3: Financial Intelligence Service

Comprehensive financial analysis service that answers the 20 key executive questions:
1. Gain-on-sale margins
2. Hedge effectiveness
3. Product profitability
4. Cost per funded loan
5. Cash runway
6. Break-even volume
7. Warehouse optimization
8. Rate exposure
9. Branch/team profitability
10. MSR portfolio status
11. Pricing competitiveness
12. Cash flow forecasts
13. Liquidity planning
14. Capital requirements
15. Compliance risks
16. Tech ROI
17. Bottleneck costs
18. Lock extension losses
19. Concession impacts
20. Investment priorities
"""

import os
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import anthropic

from models.financial_intelligence import (
    LoanSale, HedgePosition, SecondaryMetrics, MSRPortfolio,
    WarehouseLine, WarehouseUsage, ProductProfitability,
    CashPosition, CashForecast, BurnRate, CompetitorRate,
    LostDeal, CapitalRequirement, ComplianceRisk
)
from services.profitability_service import ProfitabilityService


class FinancialIntelligenceService:
    """Executive-level financial intelligence for mortgage companies."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id
        self.profitability_service = ProfitabilityService(db, organization_id)
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

    # ============ Question 1: Gain-on-Sale ============

    def get_gain_on_sale_metrics(self, month: Optional[date] = None) -> Dict[str, Any]:
        """Get gain-on-sale margin analysis."""
        if not month:
            month = date.today().replace(day=1)

        # Current month
        current = self.db.query(SecondaryMetrics).filter(
            SecondaryMetrics.organization_id == self.organization_id,
            func.date_trunc('month', SecondaryMetrics.metric_date) == month,
            SecondaryMetrics.period_type == 'monthly'
        ).first()

        # Last month
        last_month = month - timedelta(days=month.day)
        prior = self.db.query(SecondaryMetrics).filter(
            SecondaryMetrics.organization_id == self.organization_id,
            func.date_trunc('month', SecondaryMetrics.metric_date) == last_month,
            SecondaryMetrics.period_type == 'monthly'
        ).first()

        # Last year
        last_year = month.replace(year=month.year - 1)
        yoy = self.db.query(SecondaryMetrics).filter(
            SecondaryMetrics.organization_id == self.organization_id,
            func.date_trunc('month', SecondaryMetrics.metric_date) == last_year,
            SecondaryMetrics.period_type == 'monthly'
        ).first()

        return {
            "current_month": {
                "avg_gain_bps": current.avg_gain_bps if current else 0,
                "total_volume": current.total_volume if current else 0,
                "total_gain": current.total_gain if current else 0
            },
            "vs_last_month": {
                "gain_bps_change": (current.avg_gain_bps - prior.avg_gain_bps) if current and prior else 0,
                "prior_gain_bps": prior.avg_gain_bps if prior else 0
            },
            "vs_last_year": {
                "gain_bps_change": (current.avg_gain_bps - yoy.avg_gain_bps) if current and yoy else 0,
                "prior_gain_bps": yoy.avg_gain_bps if yoy else 0
            },
            "by_product": {
                "conventional": current.conv_gain_bps if current else 0,
                "government": current.govt_gain_bps if current else 0,
                "jumbo": current.jumbo_gain_bps if current else 0
            }
        }

    # ============ Question 2: Hedge Effectiveness ============

    def get_hedge_analysis(self) -> Dict[str, Any]:
        """Get hedge effectiveness and position analysis."""
        today = date.today()

        # Latest hedge position
        latest = self.db.query(HedgePosition).filter(
            HedgePosition.organization_id == self.organization_id
        ).order_by(HedgePosition.position_date.desc()).first()

        # MTD hedge P&L
        mtd_start = today.replace(day=1)
        mtd_pnl = self.db.query(
            func.sum(HedgePosition.realized_gain_loss)
        ).filter(
            HedgePosition.organization_id == self.organization_id,
            HedgePosition.position_date >= mtd_start
        ).scalar() or 0

        return {
            "current_position": {
                "date": latest.position_date.isoformat() if latest else None,
                "notional": latest.notional_amount if latest else 0,
                "market_value": latest.market_value if latest else 0,
                "coverage_pct": latest.pipeline_coverage_pct if latest else 0,
                "effectiveness_ratio": latest.hedge_effectiveness if latest else 0
            },
            "unrealized_gain_loss": latest.unrealized_gain_loss if latest else 0,
            "mtd_realized_pnl": mtd_pnl,
            "is_properly_hedged": (latest.pipeline_coverage_pct or 0) >= 80 if latest else False
        }

    # ============ Question 3: Product Profitability ============

    def get_product_profitability(self, month: Optional[date] = None) -> Dict[str, Any]:
        """Get profitability breakdown by loan product."""
        if not month:
            month = date.today().replace(day=1)

        products = self.db.query(ProductProfitability).filter(
            ProductProfitability.organization_id == self.organization_id,
            ProductProfitability.month == month
        ).all()

        result = {
            "month": month.isoformat(),
            "products": [],
            "highest_margin": None,
            "lowest_margin": None
        }

        for p in products:
            product_data = {
                "product": p.product_type,
                "channel": p.channel,
                "volume": p.total_volume,
                "loan_count": p.loan_count,
                "avg_gain_bps": p.avg_gain_bps,
                "profit_margin": p.profit_margin,
                "profit_per_loan": p.profit_per_loan,
                "total_profit": p.net_profit
            }
            result["products"].append(product_data)

        if products:
            sorted_by_margin = sorted(products, key=lambda x: x.profit_margin or 0, reverse=True)
            result["highest_margin"] = {
                "product": sorted_by_margin[0].product_type,
                "margin": sorted_by_margin[0].profit_margin
            }
            result["lowest_margin"] = {
                "product": sorted_by_margin[-1].product_type,
                "margin": sorted_by_margin[-1].profit_margin
            }

        return result

    # ============ Question 4: Cost Per Funded Loan ============

    def get_true_cost_per_loan(self, month: Optional[date] = None) -> Dict[str, Any]:
        """Get fully loaded cost per funded loan."""
        if not month:
            month = date.today().replace(day=1)
        metrics = self.profitability_service.get_dashboard_metrics(month)

        return {
            "total_cost_per_loan": metrics.get("cost_per_loan", 0),
            "breakdown": {
                "labor": metrics.get("labor_cost_per_loan", 0),
                "tech_stack": metrics.get("tech_cost_per_loan", 0),
                "fulfillment": metrics.get("fulfillment_cost_per_loan", 0),
                "overhead": metrics.get("overhead_per_loan", 0)
            },
            "loans_closed": metrics.get("loans_closed", 0),
            "total_expenses": metrics.get("total_expenses", 0)
        }

    # ============ Question 5: Cash Runway ============

    def get_cash_runway(self) -> Dict[str, Any]:
        """Calculate months of operating cash runway."""
        # Latest cash position
        cash = self.db.query(CashPosition).filter(
            CashPosition.organization_id == self.organization_id
        ).order_by(CashPosition.position_date.desc()).first()

        # Latest burn rate
        burn = self.db.query(BurnRate).filter(
            BurnRate.organization_id == self.organization_id
        ).order_by(BurnRate.month.desc()).first()

        cash_on_hand = cash.total_cash if cash else 0
        monthly_burn = burn.net_burn if burn else 0

        # Calculate runway
        if monthly_burn > 0:
            runway_months = cash_on_hand / monthly_burn
        elif monthly_burn < 0:
            runway_months = float('inf')  # Profitable
        else:
            runway_months = 0

        return {
            "cash_on_hand": cash_on_hand,
            "monthly_burn_rate": monthly_burn,
            "months_runway": runway_months if runway_months != float('inf') else -1,
            "is_profitable": monthly_burn <= 0,
            "liquidity": {
                "operating_cash": cash.operating_cash if cash else 0,
                "available_credit": cash.available_credit_lines if cash else 0,
                "total_liquidity": cash.total_liquidity if cash else 0
            }
        }

    # ============ Question 6: Break-Even Volume ============

    def get_break_even_analysis(self, month: Optional[date] = None) -> Dict[str, Any]:
        """Calculate break-even production volume."""
        if not month:
            month = date.today().replace(day=1)
        # Use dashboard metrics which includes break-even analysis
        metrics = self.profitability_service.get_dashboard_metrics(month)
        return {
            "break_even_loans": metrics.get("break_even_loans", 0),
            "current_loans": metrics.get("loans_closed", 0),
            "margin_to_break_even": metrics.get("loans_closed", 0) - metrics.get("break_even_loans", 0),
            "revenue_per_loan": metrics.get("revenue_per_loan", 0),
            "cost_per_loan": metrics.get("cost_per_loan", 0),
            "is_profitable": metrics.get("net_profit", 0) > 0
        }

    # ============ Question 7: Warehouse Optimization ============

    def get_warehouse_efficiency(self) -> Dict[str, Any]:
        """Analyze warehouse line usage efficiency."""
        today = date.today()
        mtd_start = today.replace(day=1)

        # Latest usage by line
        lines = self.db.query(WarehouseLine).filter(
            WarehouseLine.organization_id == self.organization_id,
            WarehouseLine.is_active == True
        ).all()

        line_metrics = []
        total_interest = 0
        excess_interest = 0

        for line in lines:
            usage = self.db.query(WarehouseUsage).filter(
                WarehouseUsage.warehouse_line_id == line.id,
                WarehouseUsage.usage_date >= mtd_start
            ).order_by(WarehouseUsage.usage_date.desc()).first()

            if usage:
                # Calculate excess interest from slow turns
                optimal_turn = 15  # days
                actual_turn = usage.avg_turn_time or optimal_turn
                if actual_turn > optimal_turn:
                    excess_days = actual_turn - optimal_turn
                    daily_interest = (usage.outstanding_balance or 0) * (line.interest_rate or 0.05) / 365
                    line_excess = daily_interest * excess_days
                    excess_interest += line_excess

                total_interest += usage.interest_expense or 0

                line_metrics.append({
                    "lender": line.lender_name,
                    "limit": line.line_limit,
                    "outstanding": usage.outstanding_balance,
                    "utilization": usage.utilization_pct,
                    "avg_turn_time": usage.avg_turn_time,
                    "dwell_time": usage.avg_dwell_time,
                    "interest_expense": usage.interest_expense
                })

        return {
            "lines": line_metrics,
            "total_interest_mtd": total_interest,
            "excess_interest_from_slow_turns": excess_interest,
            "optimization_opportunity": excess_interest,
            "is_optimized": excess_interest < total_interest * 0.1
        }

    # ============ Question 8: Rate Exposure ============

    def get_rate_exposure(self) -> Dict[str, Any]:
        """Calculate exposure to rate movements."""
        hedge = self.get_hedge_analysis()

        # Estimate impact of rate changes
        pipeline_value = hedge["current_position"]["notional"]
        coverage = hedge["current_position"]["coverage_pct"] / 100 if hedge["current_position"]["coverage_pct"] else 0
        unhedged = pipeline_value * (1 - coverage)

        # Assume 25bps rate move = 0.5% price change
        rate_sensitivity = 0.5 / 25  # Price change per bps

        return {
            "unhedged_pipeline": unhedged,
            "rate_sensitivity": {
                "25bps_up": -unhedged * rate_sensitivity * 25,
                "25bps_down": unhedged * rate_sensitivity * 25,
                "50bps_up": -unhedged * rate_sensitivity * 50,
                "50bps_down": unhedged * rate_sensitivity * 50
            },
            "hedge_coverage": coverage * 100,
            "exposure_level": "High" if coverage < 0.7 else "Medium" if coverage < 0.9 else "Low"
        }

    # ============ Question 9: Branch/Team Profitability ============

    def get_branch_profitability(self, month: Optional[date] = None) -> Dict[str, Any]:
        """Get profitability by branch/team/region."""
        if not month:
            month = date.today().replace(day=1)
        return {
            "role_profitability": self.profitability_service.get_role_profitability(month),
            "employee_performance": self.profitability_service.get_employee_performance(month)
        }

    # ============ Question 10: MSR Portfolio ============

    def get_msr_status(self) -> Dict[str, Any]:
        """Get MSR portfolio status and value changes."""
        # Latest valuation
        latest = self.db.query(MSRPortfolio).filter(
            MSRPortfolio.organization_id == self.organization_id
        ).order_by(MSRPortfolio.valuation_date.desc()).first()

        # Prior month for comparison
        if latest:
            prior_date = (latest.valuation_date - timedelta(days=30)).replace(day=1)
            prior = self.db.query(MSRPortfolio).filter(
                MSRPortfolio.organization_id == self.organization_id,
                MSRPortfolio.valuation_date < latest.valuation_date
            ).order_by(MSRPortfolio.valuation_date.desc()).first()
        else:
            prior = None

        return {
            "current": {
                "date": latest.valuation_date.isoformat() if latest else None,
                "upb": latest.upb if latest else 0,
                "fair_value": latest.fair_value if latest else 0,
                "multiple": latest.multiple if latest else 0,
                "loan_count": latest.loan_count if latest else 0
            },
            "value_change": {
                "amount": latest.value_change if latest else 0,
                "percent": latest.value_change_pct if latest else 0,
                "is_gaining": (latest.value_change or 0) > 0 if latest else False
            },
            "assumptions": {
                "discount_rate": latest.discount_rate if latest else 0,
                "prepay_speed": latest.prepay_speed if latest else 0
            },
            "income": {
                "servicing_fee": latest.servicing_fee_income if latest else 0,
                "ancillary": latest.ancillary_income if latest else 0,
                "float": latest.float_income if latest else 0
            }
        }

    # ============ Question 11: Pricing Competitiveness ============

    def get_pricing_analysis(self) -> Dict[str, Any]:
        """Analyze pricing competitiveness."""
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)

        # Recent competitor rates
        rates = self.db.query(CompetitorRate).filter(
            CompetitorRate.organization_id == self.organization_id,
            CompetitorRate.rate_date >= thirty_days_ago
        ).all()

        # Lost deals
        lost = self.db.query(LostDeal).filter(
            LostDeal.organization_id == self.organization_id,
            LostDeal.lost_date >= thirty_days_ago
        ).all()

        lost_to_rate = [d for d in lost if d.loss_reason == 'Rate']
        lost_revenue = sum(d.estimated_revenue_lost or 0 for d in lost_to_rate)

        # Calculate average spread
        avg_spread = 0
        if rates:
            spreads = [r.rate_spread for r in rates if r.rate_spread]
            avg_spread = sum(spreads) / len(spreads) if spreads else 0

        return {
            "avg_rate_spread_bps": avg_spread * 100,  # Convert to bps
            "is_competitive": avg_spread <= 0.125,  # Within 12.5bps
            "lost_deals": {
                "total_count": len(lost),
                "lost_to_rate": len(lost_to_rate),
                "revenue_lost": lost_revenue
            },
            "top_competitors": self._get_top_competitors(lost)
        }

    def _get_top_competitors(self, lost_deals: List[LostDeal]) -> List[Dict]:
        """Get top competitors taking deals."""
        competitor_counts = {}
        for deal in lost_deals:
            comp = deal.lost_to_competitor or "Unknown"
            competitor_counts[comp] = competitor_counts.get(comp, 0) + 1

        sorted_comps = sorted(competitor_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"name": c[0], "deals_lost": c[1]} for c in sorted_comps[:5]]

    # ============ Question 12: Cash Flow Forecast ============

    def get_cash_forecast(self) -> Dict[str, Any]:
        """Get 30/60/90 day cash flow forecast."""
        today = date.today()

        forecasts = {}
        for days in [30, 60, 90]:
            target_date = today + timedelta(days=days)
            forecast = self.db.query(CashForecast).filter(
                CashForecast.organization_id == self.organization_id,
                CashForecast.period_end == target_date.replace(day=1)
            ).order_by(CashForecast.forecast_date.desc()).first()

            forecasts[f"{days}_day"] = {
                "ending_cash": forecast.ending_cash if forecast else 0,
                "net_flow": forecast.net_cash_flow if forecast else 0,
                "inflows": forecast.total_inflows if forecast else 0,
                "outflows": forecast.total_outflows if forecast else 0,
                "best_case": forecast.best_case if forecast else 0,
                "worst_case": forecast.worst_case if forecast else 0
            }

        return forecasts

    # ============ Question 13: Liquidity Planning ============

    def get_liquidity_analysis(self) -> Dict[str, Any]:
        """Analyze liquidity for volume increases."""
        cash = self.get_cash_runway()
        warehouse = self.get_warehouse_efficiency()

        total_warehouse_capacity = sum(
            line.get("limit", 0) - line.get("outstanding", 0)
            for line in warehouse["lines"]
        )

        return {
            "current_liquidity": cash["liquidity"]["total_liquidity"],
            "available_warehouse": total_warehouse_capacity,
            "can_handle_volume_increase": {
                "25_percent": total_warehouse_capacity > 5000000,
                "50_percent": total_warehouse_capacity > 10000000,
                "100_percent": total_warehouse_capacity > 20000000
            },
            "recommendations": self._get_liquidity_recommendations(cash, warehouse)
        }

    def _get_liquidity_recommendations(self, cash, warehouse) -> List[str]:
        recommendations = []
        if cash["months_runway"] < 6 and cash["months_runway"] > 0:
            recommendations.append("Consider building cash reserves - runway under 6 months")
        if warehouse["excess_interest_from_slow_turns"] > 10000:
            recommendations.append(f"Optimize turn times to save ${warehouse['excess_interest_from_slow_turns']:,.0f} in interest")
        return recommendations

    # ============ Question 14: Capital Requirements ============

    def get_capital_analysis(self) -> Dict[str, Any]:
        """Analyze capital adequacy for growth."""
        latest = self.db.query(CapitalRequirement).filter(
            CapitalRequirement.organization_id == self.organization_id
        ).order_by(CapitalRequirement.as_of_date.desc()).first()

        return {
            "current": {
                "tangible_net_worth": latest.tangible_net_worth if latest else 0,
                "adjusted_net_worth": latest.adjusted_net_worth if latest else 0
            },
            "requirements": {
                "fnma": latest.fnma_requirement if latest else 0,
                "fhlmc": latest.fhlmc_requirement if latest else 0,
                "gnma": latest.gnma_requirement if latest else 0,
                "state": latest.state_requirements if latest else 0
            },
            "excess_capital": latest.excess_capital if latest else 0,
            "cushion_pct": latest.cushion_pct if latest else 0,
            "meets_requirements": (latest.excess_capital or 0) > 0 if latest else False
        }

    # ============ Question 15: Compliance Risks ============

    def get_compliance_exposure(self) -> Dict[str, Any]:
        """Get compliance and regulatory risk exposure."""
        open_risks = self.db.query(ComplianceRisk).filter(
            ComplianceRisk.organization_id == self.organization_id,
            ComplianceRisk.status == "Open"
        ).all()

        total_exposure = sum(r.potential_exposure or 0 for r in open_risks)
        total_reserved = sum(r.reserved_amount or 0 for r in open_risks)

        by_type = {}
        for risk in open_risks:
            risk_type = risk.risk_type or "Other"
            if risk_type not in by_type:
                by_type[risk_type] = {"count": 0, "exposure": 0}
            by_type[risk_type]["count"] += 1
            by_type[risk_type]["exposure"] += risk.potential_exposure or 0

        return {
            "open_risks": len(open_risks),
            "total_potential_exposure": total_exposure,
            "reserved_amount": total_reserved,
            "unreserved_exposure": total_exposure - total_reserved,
            "by_type": by_type,
            "high_severity": [
                {
                    "type": r.risk_type,
                    "description": r.description,
                    "exposure": r.potential_exposure
                }
                for r in open_risks if r.severity == "High"
            ]
        }

    # ============ Question 16: Tech ROI ============

    def get_tech_roi(self, month: Optional[date] = None) -> Dict[str, Any]:
        """Calculate ROI on technology investments."""
        if not month:
            month = date.today().replace(day=1)
        metrics = self.profitability_service.get_dashboard_metrics(month)

        # This would need tech expense tracking
        # For now, estimate based on typical allocations
        # Convert to float for calculations
        total_expenses = float(metrics.get("total_expenses", 0) or 0)
        tech_expenses = total_expenses * 0.08  # Typical 8% of expenses

        # Estimate productivity gains
        loans_closed = int(metrics.get("loans_closed", 0) or 0)
        estimated_time_saved_hours = loans_closed * 2  # 2 hours per loan
        hourly_rate = 50
        productivity_value = estimated_time_saved_hours * hourly_rate

        return {
            "tech_investment": tech_expenses,
            "estimated_productivity_gain": productivity_value,
            "roi_pct": ((productivity_value - tech_expenses) / tech_expenses * 100) if tech_expenses else 0,
            "note": "Detailed ROI requires tech expense tracking by category"
        }

    # ============ Questions 17-19: Operational Costs ============

    def get_operational_losses(self) -> Dict[str, Any]:
        """Get losses from bottlenecks, extensions, and concessions."""
        today = date.today()
        month_start = today.replace(day=1)

        # Lock extensions from secondary metrics
        secondary = self.db.query(SecondaryMetrics).filter(
            SecondaryMetrics.organization_id == self.organization_id,
            SecondaryMetrics.metric_date >= month_start
        ).first()

        # Handle None secondary gracefully
        lock_ext_count = (secondary.lock_extensions or 0) if secondary else 0
        relock_count = (secondary.relocks or 0) if secondary else 0
        fallout_rate = (secondary.fallout_rate or 0) if secondary else 0

        return {
            "lock_extensions": {
                "count": lock_ext_count,
                "estimated_cost": lock_ext_count * 500  # $500 avg per extension
            },
            "relocks": {
                "count": relock_count,
                "estimated_cost": relock_count * 1000  # $1000 avg per relock
            },
            "fallout": {
                "rate": fallout_rate,
                "estimated_revenue_lost": 0  # Would need pipeline data
            },
            "bottleneck_costs": {
                "warehouse_interest": self.get_warehouse_efficiency()["excess_interest_from_slow_turns"]
            }
        }

    # ============ Question 20: Investment Priorities ============

    def get_investment_recommendations(self, month: Optional[date] = None) -> Dict[str, Any]:
        """AI-generated investment and cut recommendations."""
        # Gather all metrics
        context = {
            "gain_on_sale": self.get_gain_on_sale_metrics(month),
            "cash_runway": self.get_cash_runway(),
            "product_profitability": self.get_product_profitability(month),
            "warehouse": self.get_warehouse_efficiency(),
            "pricing": self.get_pricing_analysis(),
            "compliance": self.get_compliance_exposure()
        }

        system_prompt = """You are a mortgage industry CFO advisor. Based on the financial metrics provided,
give specific recommendations on where to invest and where to cut over the next 6-12 months.

Format your response as:
INVEST:
1. [Area] - [Reason] - [Expected ROI]
2. ...

CUT/REDUCE:
1. [Area] - [Reason] - [Expected Savings]
2. ...

Be specific with dollar amounts where possible. Focus on actionable recommendations."""

        user_prompt = f"""Based on these financial metrics, provide investment and cost-cutting recommendations:

{context}

Provide 3-5 specific investment areas and 3-5 cost-cutting opportunities."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return {
            "analysis": response.content[0].text,
            "data_context": context,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    # ============ Executive Dashboard ============

    def get_executive_dashboard(self, month: Optional[date] = None, include_ai_recommendations: bool = False) -> Dict[str, Any]:
        """
        Get complete executive dashboard with all 20 answers.
        Optimized with parallel execution for 10x faster response.

        Args:
            month: Optional month for time-based metrics
            include_ai_recommendations: If True, includes AI-generated recommendations (adds ~3-5s)
        """
        from performance_cache import run_parallel_sync, get_cached, set_cached, cache_key, DASHBOARD_TTL

        # Check cache first
        cache_k = cache_key("exec_dashboard", month, include_ai_recommendations)
        cached_result = get_cached(cache_k)
        if cached_result:
            return cached_result

        # Execute all independent queries in parallel (huge speedup)
        parallel_results = run_parallel_sync(
            (self.get_gain_on_sale_metrics, (month,)),
            (self.get_hedge_analysis, ()),
            (self.get_product_profitability, (month,)),
            (self.get_true_cost_per_loan, (month,)),
            (self.get_cash_runway, ()),
            (self.get_break_even_analysis, (month,)),
            (self.get_warehouse_efficiency, ()),
            (self.get_msr_status, ()),
            (self.get_pricing_analysis, ()),
            (self.get_cash_forecast, ()),
            (self.get_capital_analysis, ()),
            (self.get_compliance_exposure, ()),
            (self.get_tech_roi, (month,)),
            (self.get_operational_losses, ()),
            (self.get_branch_profitability, (month,)),
        )

        # Rate exposure depends on hedge analysis, calculate after
        rate_exposure = self.get_rate_exposure()

        # Liquidity depends on cash runway and warehouse, calculate after
        liquidity = self.get_liquidity_analysis()

        result = {
            "1_gain_on_sale": parallel_results[0],
            "2_hedge_effectiveness": parallel_results[1],
            "3_product_profitability": parallel_results[2],
            "4_cost_per_loan": parallel_results[3],
            "5_cash_runway": parallel_results[4],
            "6_break_even": parallel_results[5],
            "7_warehouse_optimization": parallel_results[6],
            "8_rate_exposure": rate_exposure,
            "9_branch_profitability": parallel_results[14],
            "10_msr_status": parallel_results[7],
            "11_pricing_competitiveness": parallel_results[8],
            "12_cash_forecast": parallel_results[9],
            "13_liquidity": liquidity,
            "14_capital": parallel_results[10],
            "15_compliance": parallel_results[11],
            "16_tech_roi": parallel_results[12],
            "17_18_19_operational_losses": parallel_results[13],
            "20_recommendations": None,  # Lazy load - call /investment-recommendations endpoint separately
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "_meta": {
                "cached": False,
                "ai_recommendations_included": include_ai_recommendations,
                "recommendation_endpoint": "/api/v1/financial-intelligence/investment-recommendations"
            }
        }

        # Only include AI recommendations if explicitly requested (adds 3-5s)
        if include_ai_recommendations:
            result["20_recommendations"] = self.get_investment_recommendations(month)
            result["_meta"]["ai_recommendations_included"] = True

        # Cache the result
        set_cached(cache_k, result, DASHBOARD_TTL)

        return result
