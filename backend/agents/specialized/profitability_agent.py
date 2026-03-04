"""
Profitability Analyst Agent

Specialized agent for loan and branch profitability analysis with 8 tools:
1. analyze_loan_profitability - Calculate profit metrics for a loan
2. get_branch_profitability - Branch-level profitability analysis
3. calculate_lo_compensation - Loan officer compensation breakdown
4. compare_profit_margins - Compare margins across loan types
5. analyze_pricing_trends - Analyze pricing and margin trends
6. calculate_cost_breakdown - Detailed cost analysis
7. project_revenue - Revenue projections
8. identify_profit_opportunities - Find profit improvement opportunities
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)

logger = logging.getLogger(__name__)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class LoanProfitabilityInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to analyze")
    include_breakdown: bool = Field(default=True, description="Include detailed cost breakdown")


class BranchProfitabilityInput(BaseModel):
    branch_id: Optional[int] = Field(None, description="Branch ID (null for all branches)")
    period_days: int = Field(default=30, description="Analysis period in days")


class LOCompensationInput(BaseModel):
    lo_id: int = Field(..., description="Loan officer ID")
    loan_id: Optional[int] = Field(None, description="Specific loan ID")
    period_days: int = Field(default=30, description="Period for compensation calculation")


class CompareMarginsInput(BaseModel):
    loan_types: Optional[List[str]] = Field(None, description="Loan types to compare")
    period_days: int = Field(default=90, description="Analysis period")


class PricingTrendsInput(BaseModel):
    loan_type: Optional[str] = Field(None, description="Filter by loan type")
    period_days: int = Field(default=180, description="Trend analysis period")


class CostBreakdownInput(BaseModel):
    loan_id: Optional[int] = Field(None, description="Specific loan ID")
    period_days: int = Field(default=30, description="Period for aggregate analysis")


class RevenueProjectionInput(BaseModel):
    period_months: int = Field(default=3, description="Projection period in months")
    include_pipeline: bool = Field(default=True, description="Include pipeline in projection")


class ProfitOpportunitiesInput(BaseModel):
    min_impact: float = Field(default=1000, description="Minimum profit impact to flag")
    limit: int = Field(default=10, description="Maximum opportunities to return")


# ============================================================================
# PROFITABILITY ANALYST AGENT
# ============================================================================

@AgentRegistry.register
class ProfitabilityAgent(SpecializedAgent):
    """
    Profitability analysis agent for loan and branch financial metrics.

    Provides comprehensive profitability analysis, cost breakdown, and
    revenue projections with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "ProfitabilityAgent"

    @property
    def description(self) -> str:
        return "Analyzes loan profitability, branch performance, compensation, and identifies profit opportunities"

    def _register_tools(self):
        """Register all profitability analysis tools"""

        self.register_tool(AgentTool(
            name="analyze_loan_profitability",
            description="Calculate profitability metrics for a specific loan including revenue, costs, and margins",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_loan_profitability,
            input_schema=LoanProfitabilityInput
        ))

        self.register_tool(AgentTool(
            name="get_branch_profitability",
            description="Analyze branch-level profitability including volume, revenue, and efficiency metrics",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_branch_profitability,
            input_schema=BranchProfitabilityInput
        ))

        self.register_tool(AgentTool(
            name="calculate_lo_compensation",
            description="Calculate loan officer compensation breakdown for loans or period",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            handler=self._calculate_lo_compensation,
            input_schema=LOCompensationInput
        ))

        self.register_tool(AgentTool(
            name="compare_profit_margins",
            description="Compare profit margins across different loan types and products",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._compare_profit_margins,
            input_schema=CompareMarginsInput
        ))

        self.register_tool(AgentTool(
            name="analyze_pricing_trends",
            description="Analyze pricing and margin trends over time",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_pricing_trends,
            input_schema=PricingTrendsInput
        ))

        self.register_tool(AgentTool(
            name="calculate_cost_breakdown",
            description="Get detailed cost breakdown for loan origination",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_cost_breakdown,
            input_schema=CostBreakdownInput
        ))

        self.register_tool(AgentTool(
            name="project_revenue",
            description="Project revenue based on current pipeline and historical trends",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._project_revenue,
            input_schema=RevenueProjectionInput
        ))

        self.register_tool(AgentTool(
            name="identify_profit_opportunities",
            description="Identify opportunities to improve profitability",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_profit_opportunities,
            input_schema=ProfitOpportunitiesInput
        ))

    async def _analyze_loan_profitability(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Analyze profitability for a specific loan"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            query = text("""
                SELECT
                    l.id, l.loan_number, l.loan_amount, l.interest_rate,
                    l.origination_fee, l.discount_points, l.loan_type,
                    l.status, l.funded_at
                FROM loans l
                WHERE l.id = :loan_id
                AND l.organization_id = :org_id
            """)

            result = db.execute(query, {"loan_id": input_data["loan_id"], "org_id": org_id}).fetchone()

            if not result:
                return ToolResult(success=False, error="Loan not found")

            loan_amount = float(result.loan_amount or 0)

            # Calculate revenue components
            origination_fee = float(result.origination_fee or 0) or loan_amount * 0.01
            srp_estimate = loan_amount * 0.02  # Service release premium estimate
            discount_points = float(result.discount_points or 0)

            total_revenue = origination_fee + srp_estimate + discount_points

            # Estimate costs
            lo_comp = loan_amount * 0.01  # LO compensation
            processing_cost = 500
            underwriting_cost = 400
            overhead = loan_amount * 0.003

            total_cost = lo_comp + processing_cost + underwriting_cost + overhead

            gross_profit = total_revenue - total_cost
            margin_bps = (gross_profit / loan_amount) * 10000 if loan_amount > 0 else 0

            data = {
                "loan_id": result.id,
                "loan_number": result.loan_number,
                "loan_amount": loan_amount,
                "revenue": {
                    "origination_fee": origination_fee,
                    "srp_estimate": srp_estimate,
                    "discount_points": discount_points,
                    "total": total_revenue
                },
                "costs": {
                    "lo_compensation": lo_comp,
                    "processing": processing_cost,
                    "underwriting": underwriting_cost,
                    "overhead": overhead,
                    "total": total_cost
                },
                "profit": {
                    "gross_profit": gross_profit,
                    "margin_bps": round(margin_bps, 0),
                    "margin_percent": round((gross_profit / total_revenue) * 100, 1) if total_revenue > 0 else 0
                }
            }

            return ToolResult(
                success=True,
                data=data,
                message=f"Loan {result.loan_number}: ${gross_profit:,.0f} profit ({margin_bps:.0f} bps)"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_branch_profitability(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Analyze branch profitability"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            params = {"days": input_data.get("period_days", 30), "org_id": org_id}
            branch_filter = ""

            if input_data.get("branch_id"):
                branch_filter = "AND l.branch_id = :branch_id"
                params["branch_id"] = input_data["branch_id"]

            query = text(f"""
                SELECT
                    COUNT(*) as loan_count,
                    SUM(loan_amount) as total_volume,
                    AVG(loan_amount) as avg_loan_size,
                    SUM(origination_fee) as total_origination,
                    COUNT(DISTINCT loan_officer_id) as lo_count
                FROM loans l
                WHERE l.funded_at >= CURRENT_DATE - :days
                AND l.organization_id = :org_id
                {branch_filter}
            """)

            result = db.execute(query, params).fetchone()

            volume = float(result.total_volume or 0)
            loan_count = result.loan_count or 0

            # Estimate profitability
            estimated_revenue = volume * 0.025  # 2.5% of volume
            estimated_costs = volume * 0.015   # 1.5% of volume
            estimated_profit = estimated_revenue - estimated_costs

            data = {
                "period_days": params["days"],
                "metrics": {
                    "loan_count": loan_count,
                    "total_volume": volume,
                    "avg_loan_size": float(result.avg_loan_size or 0),
                    "lo_count": result.lo_count or 0,
                    "loans_per_lo": round(loan_count / result.lo_count, 1) if result.lo_count else 0
                },
                "financials": {
                    "estimated_revenue": estimated_revenue,
                    "estimated_costs": estimated_costs,
                    "estimated_profit": estimated_profit,
                    "profit_per_loan": estimated_profit / loan_count if loan_count > 0 else 0
                }
            }

            return ToolResult(
                success=True,
                data=data,
                message=f"Branch profitability: ${estimated_profit:,.0f} on {loan_count} loans"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_lo_compensation(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Calculate LO compensation"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            query = text("""
                SELECT
                    l.id, l.loan_number, l.loan_amount, l.funded_at,
                    l.origination_fee
                FROM loans l
                WHERE l.loan_officer_id = :lo_id
                AND l.funded_at >= CURRENT_DATE - :days
                AND l.organization_id = :org_id
            """)

            results = db.execute(query, {
                "lo_id": input_data["lo_id"],
                "days": input_data.get("period_days", 30),
                "org_id": org_id
            }).fetchall()

            total_volume = 0
            total_comp = 0
            loans = []

            for r in results:
                loan_amount = float(r.loan_amount or 0)
                comp = loan_amount * 0.01  # 1% LO comp estimate

                total_volume += loan_amount
                total_comp += comp

                loans.append({
                    "loan_number": r.loan_number,
                    "amount": loan_amount,
                    "compensation": comp,
                    "funded_at": r.funded_at.isoformat() if r.funded_at else None
                })

            data = {
                "lo_id": input_data["lo_id"],
                "period_days": input_data.get("period_days", 30),
                "summary": {
                    "loan_count": len(loans),
                    "total_volume": total_volume,
                    "total_compensation": total_comp,
                    "avg_comp_per_loan": total_comp / len(loans) if loans else 0
                },
                "loans": loans
            }

            return ToolResult(
                success=True,
                data=data,
                message=f"LO compensation: ${total_comp:,.0f} on {len(loans)} loans"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _compare_profit_margins(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Compare profit margins across loan types"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            query = text("""
                SELECT
                    loan_type,
                    COUNT(*) as count,
                    AVG(loan_amount) as avg_amount,
                    SUM(loan_amount) as total_volume,
                    AVG(origination_fee) as avg_orig_fee
                FROM loans
                WHERE funded_at >= CURRENT_DATE - :days
                AND organization_id = :org_id
                GROUP BY loan_type
                ORDER BY total_volume DESC
            """)

            results = db.execute(query, {"days": input_data.get("period_days", 90), "org_id": org_id}).fetchall()

            comparisons = []
            for r in results:
                avg_amount = float(r.avg_amount or 0)
                avg_fee = float(r.avg_orig_fee or 0)
                margin_bps = (avg_fee / avg_amount) * 10000 if avg_amount > 0 else 0

                comparisons.append({
                    "loan_type": r.loan_type,
                    "count": r.count,
                    "avg_amount": avg_amount,
                    "total_volume": float(r.total_volume or 0),
                    "avg_origination_fee": avg_fee,
                    "margin_bps": round(margin_bps, 0)
                })

            return ToolResult(
                success=True,
                data={"comparisons": comparisons, "period_days": input_data.get("period_days", 90)},
                message=f"Compared margins for {len(comparisons)} loan types"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _analyze_pricing_trends(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Analyze pricing trends"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            query = text("""
                SELECT
                    DATE_TRUNC('week', funded_at) as week,
                    AVG(interest_rate) as avg_rate,
                    AVG(origination_fee / NULLIF(loan_amount, 0) * 10000) as avg_margin_bps,
                    COUNT(*) as loan_count
                FROM loans
                WHERE funded_at >= CURRENT_DATE - :days
                AND organization_id = :org_id
                GROUP BY DATE_TRUNC('week', funded_at)
                ORDER BY week DESC
            """)

            results = db.execute(query, {"days": input_data.get("period_days", 180), "org_id": org_id}).fetchall()

            trends = [
                {
                    "week": r.week.isoformat() if r.week else None,
                    "avg_rate": round(float(r.avg_rate or 0), 3),
                    "avg_margin_bps": round(float(r.avg_margin_bps or 0), 0),
                    "loan_count": r.loan_count
                }
                for r in results
            ]

            return ToolResult(
                success=True,
                data={"trends": trends, "period_days": input_data.get("period_days", 180)},
                message=f"Analyzed pricing trends for {len(trends)} weeks"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_cost_breakdown(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Calculate detailed cost breakdown"""
        # Standard cost structure for mortgage origination
        cost_structure = {
            "personnel": {
                "lo_compensation": {"percent": 1.0, "description": "Loan officer commission"},
                "processor": {"fixed": 350, "description": "Processor fee"},
                "underwriter": {"fixed": 400, "description": "Underwriting fee"},
                "closer": {"fixed": 200, "description": "Closing coordinator"}
            },
            "third_party": {
                "appraisal": {"fixed": 500, "description": "Appraisal fee"},
                "credit_report": {"fixed": 50, "description": "Credit report"},
                "title": {"fixed": 1200, "description": "Title services"},
                "flood_cert": {"fixed": 25, "description": "Flood certification"}
            },
            "overhead": {
                "technology": {"percent": 0.05, "description": "Tech & CRM costs"},
                "compliance": {"percent": 0.03, "description": "Compliance costs"},
                "facilities": {"percent": 0.02, "description": "Facilities allocation"}
            }
        }

        return ToolResult(
            success=True,
            data={"cost_structure": cost_structure},
            message="Cost breakdown structure retrieved"
        )

    async def _project_revenue(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Project future revenue"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            # Get historical average
            hist_query = text("""
                SELECT
                    AVG(monthly_volume) as avg_volume,
                    AVG(monthly_revenue) as avg_revenue
                FROM (
                    SELECT
                        DATE_TRUNC('month', funded_at) as month,
                        SUM(loan_amount) as monthly_volume,
                        SUM(origination_fee) as monthly_revenue
                    FROM loans
                    WHERE funded_at >= CURRENT_DATE - 180
                    AND organization_id = :org_id
                    GROUP BY DATE_TRUNC('month', funded_at)
                ) monthly
            """)

            hist = db.execute(hist_query, {"org_id": org_id}).fetchone()
            avg_monthly_revenue = float(hist.avg_revenue or 0)

            # Get pipeline value
            pipeline_query = text("""
                SELECT SUM(loan_amount) as pipeline_value
                FROM loans
                WHERE status NOT IN ('funded', 'cancelled', 'denied')
                AND organization_id = :org_id
            """)

            pipeline = db.execute(pipeline_query, {"org_id": org_id}).fetchone()
            pipeline_value = float(pipeline.pipeline_value or 0)

            months = input_data.get("period_months", 3)

            projection = {
                "period_months": months,
                "historical_avg_monthly": avg_monthly_revenue,
                "pipeline_value": pipeline_value,
                "pipeline_estimated_revenue": pipeline_value * 0.025,
                "projected_monthly_revenue": avg_monthly_revenue,
                "projected_total": avg_monthly_revenue * months + (pipeline_value * 0.025 * 0.7)
            }

            return ToolResult(
                success=True,
                data=projection,
                message=f"Projected revenue: ${projection['projected_total']:,.0f} over {months} months"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_profit_opportunities(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Identify profit improvement opportunities"""
        opportunities = [
            {
                "type": "pricing_optimization",
                "description": "Review loans with below-average margins for pricing adjustment opportunities",
                "estimated_impact": 5000,
                "difficulty": "medium"
            },
            {
                "type": "volume_increase",
                "description": "Top performing LOs have capacity for additional volume",
                "estimated_impact": 15000,
                "difficulty": "medium"
            },
            {
                "type": "cost_reduction",
                "description": "Negotiate better rates with title vendors based on volume",
                "estimated_impact": 3000,
                "difficulty": "low"
            },
            {
                "type": "process_efficiency",
                "description": "Reduce cycle time to improve pull-through rate",
                "estimated_impact": 8000,
                "difficulty": "high"
            }
        ]

        filtered = [o for o in opportunities if o["estimated_impact"] >= input_data.get("min_impact", 1000)]

        return ToolResult(
            success=True,
            data={
                "opportunities": filtered[:input_data.get("limit", 10)],
                "total_potential_impact": sum(o["estimated_impact"] for o in filtered)
            },
            message=f"Found {len(filtered)} profit opportunities"
        )
