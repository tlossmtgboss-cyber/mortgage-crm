"""
Portfolio Agent

Specialized agent for post-close client management with 8 tools:
1. get_portfolio_summary - Get portfolio overview
2. get_client_details - Get funded client details
3. identify_refinance_candidates - Find clients eligible for refinance
4. get_anniversary_clients - Get loan anniversary clients
5. calculate_ltv_changes - Calculate current LTV based on market
6. get_retention_risks - Identify clients at risk of leaving
7. create_touchpoint - Log a client touchpoint
8. get_referral_opportunities - Identify referral potential
"""

import logging
from typing import Any, Dict, Optional, List
from ..utils.financial_calcs import calculate_ltv, calculate_rate_savings
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

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

class GetPortfolioSummaryInput(BaseModel):
    """Input schema for get_portfolio_summary tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    funded_after: Optional[str] = Field(None, description="Only include loans funded after date")


class GetClientDetailsInput(BaseModel):
    """Input schema for get_client_details tool"""
    loan_id: int = Field(..., description="Funded loan ID")
    include_history: bool = Field(default=True, description="Include interaction history")


class IdentifyRefinanceCandidatesInput(BaseModel):
    """Input schema for identify_refinance_candidates tool"""
    rate_drop_threshold: float = Field(default=0.5, description="Min rate drop % to qualify")
    min_equity_percent: float = Field(default=20, description="Min equity percentage")
    min_months_since_close: int = Field(default=6, description="Min months since closing")


class GetAnniversaryClientsInput(BaseModel):
    """Input schema for get_anniversary_clients tool"""
    days_ahead: int = Field(default=30, description="Days to look ahead for anniversaries")
    anniversary_type: str = Field(default="all", description="Type: funding, birthday, all")


class CalculateLtvChangesInput(BaseModel):
    """Input schema for calculate_ltv_changes tool"""
    loan_ids: Optional[List[int]] = Field(None, description="Specific loan IDs, or None for all")
    appreciation_rate: float = Field(default=5.0, description="Annual appreciation rate %")


class GetRetentionRisksInput(BaseModel):
    """Input schema for get_retention_risks tool"""
    risk_threshold: str = Field(default="medium", description="Min risk level: low, medium, high")
    limit: int = Field(default=50, description="Maximum clients to return")


class CreateTouchpointInput(BaseModel):
    """Input schema for create_touchpoint tool"""
    loan_id: int = Field(..., description="Funded loan ID")
    touchpoint_type: str = Field(..., description="Type: call, email, card, gift, review_request")
    notes: str = Field(..., description="Notes about the interaction")
    next_touchpoint_date: Optional[str] = Field(None, description="Schedule next touchpoint")


class GetReferralOpportunitiesInput(BaseModel):
    """Input schema for get_referral_opportunities tool"""
    min_satisfaction_score: int = Field(default=8, description="Min satisfaction score (1-10)")
    min_months_since_close: int = Field(default=3, description="Min months since closing")


# ============================================================================
# PORTFOLIO AGENT
# ============================================================================

@AgentRegistry.register
class PortfolioAgent(SpecializedAgent):
    """
    Specialized agent for post-close portfolio management.

    Manages funded client relationships, identifies refinance
    opportunities, tracks retention risks, and drives referrals.
    """

    @property
    def name(self) -> str:
        return "PortfolioAgent"

    @property
    def description(self) -> str:
        return "Manages post-close client portfolio including refinance opportunities, retention, and referrals"

    def _register_tools(self):
        """Register all portfolio management tools"""

        # Tool 1: Get Portfolio Summary
        self.register_tool(AgentTool(
            name="get_portfolio_summary",
            description="Get overview of funded loan portfolio including total clients, "
                       "volume, and key segments.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_portfolio_summary,
            input_schema=GetPortfolioSummaryInput
        ))

        # Tool 2: Get Client Details
        self.register_tool(AgentTool(
            name="get_client_details",
            description="Get comprehensive details for a funded client including loan terms, "
                       "payment history, and interaction timeline.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_client_details,
            input_schema=GetClientDetailsInput
        ))

        # Tool 3: Identify Refinance Candidates
        self.register_tool(AgentTool(
            name="identify_refinance_candidates",
            description="Find clients who may benefit from refinancing based on rate drops, "
                       "equity gains, or loan term changes.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_refinance_candidates,
            input_schema=IdentifyRefinanceCandidatesInput
        ))

        # Tool 4: Get Anniversary Clients
        self.register_tool(AgentTool(
            name="get_anniversary_clients",
            description="Get clients with upcoming loan anniversaries or birthdays "
                       "for outreach opportunities.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_anniversary_clients,
            input_schema=GetAnniversaryClientsInput
        ))

        # Tool 5: Calculate LTV Changes
        self.register_tool(AgentTool(
            name="calculate_ltv_changes",
            description="Calculate current LTV for loans based on original values and "
                       "estimated appreciation.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_ltv_changes,
            input_schema=CalculateLtvChangesInput
        ))

        # Tool 6: Get Retention Risks
        self.register_tool(AgentTool(
            name="get_retention_risks",
            description="Identify clients at risk of refinancing elsewhere or showing "
                       "disengagement signals.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_retention_risks,
            input_schema=GetRetentionRisksInput
        ))

        # Tool 7: Create Touchpoint
        self.register_tool(AgentTool(
            name="create_touchpoint",
            description="Log a client touchpoint interaction and optionally schedule "
                       "the next contact.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._create_touchpoint,
            input_schema=CreateTouchpointInput
        ))

        # Tool 8: Get Referral Opportunities
        self.register_tool(AgentTool(
            name="get_referral_opportunities",
            description="Identify satisfied clients who are good candidates for "
                       "referral requests.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_referral_opportunities,
            input_schema=GetReferralOpportunitiesInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _get_portfolio_summary(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get portfolio overview"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            lo_id = input_data.get("lo_id")
            funded_after = input_data.get("funded_after")

            org_id = self.context.get("organization_id")
            params = {}
            conditions = ["stage = 'Funded'"]

            if lo_id:
                conditions.append("assigned_lo = :lo_id")
                params["lo_id"] = lo_id

            if funded_after:
                conditions.append("funded_date >= :funded_after")
                params["funded_after"] = funded_after

            if org_id:
                conditions.append("organization_id = :org_id")
                params["org_id"] = org_id

            where_clause = " AND ".join(conditions)

            # Main summary
            summary_query = text(f"""
                SELECT
                    COUNT(*) as total_clients,
                    COALESCE(SUM(amount), 0) as total_volume,
                    COALESCE(AVG(amount), 0) as avg_loan_size,
                    COALESCE(AVG(rate), 0) as avg_rate,
                    COUNT(CASE WHEN funded_date >= CURRENT_DATE - 365 THEN 1 END) as funded_last_year,
                    COUNT(CASE WHEN funded_date >= CURRENT_DATE - 90 THEN 1 END) as funded_last_90
                FROM loans
                WHERE {where_clause}
            """)

            summary = db.execute(summary_query, params).fetchone()

            # By loan type
            type_query = text(f"""
                SELECT
                    program,
                    COUNT(*) as count,
                    COALESCE(SUM(amount), 0) as volume
                FROM loans
                WHERE {where_clause}
                GROUP BY program
                ORDER BY volume DESC
            """)

            types = db.execute(type_query, params).fetchall()

            loan_types = [
                {
                    "program": t.program,
                    "count": t.count,
                    "volume": float(t.volume)
                }
                for t in types
            ]

            # By year funded
            year_query = text(f"""
                SELECT
                    EXTRACT(YEAR FROM funded_date) as year,
                    COUNT(*) as count,
                    COALESCE(SUM(amount), 0) as volume
                FROM loans
                WHERE {where_clause}
                    AND funded_date IS NOT NULL
                GROUP BY EXTRACT(YEAR FROM funded_date)
                ORDER BY year DESC
                LIMIT 5
            """)

            years = db.execute(year_query, params).fetchall()

            by_year = [
                {
                    "year": int(y.year) if y.year else None,
                    "count": y.count,
                    "volume": float(y.volume)
                }
                for y in years
            ]

            return ToolResult(
                success=True,
                data={
                    "summary": {
                        "total_clients": summary.total_clients,
                        "total_volume": float(summary.total_volume),
                        "avg_loan_size": float(summary.avg_loan_size),
                        "avg_rate": round(float(summary.avg_rate), 3),
                        "funded_last_year": summary.funded_last_year,
                        "funded_last_90_days": summary.funded_last_90
                    },
                    "by_loan_type": loan_types,
                    "by_year": by_year
                },
                message=f"Portfolio: {summary.total_clients} clients, ${summary.total_volume:,.0f} total volume"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_client_details(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get funded client details"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()

        try:
            org_id = self.context.get("organization_id")
            org_clause = ""
            params = {"loan_id": loan_id}
            if org_id:
                org_clause = "AND l.organization_id = :org_id"
                params["org_id"] = org_id

            # Get loan details
            loan_query = text(f"""
                SELECT
                    l.*,
                    u.name as lo_name,
                    EXTRACT(MONTH FROM AGE(CURRENT_DATE, l.funded_date)) as months_since_close
                FROM loans l
                LEFT JOIN users u ON l.assigned_lo = u.id
                WHERE l.id = :loan_id AND l.stage = 'Funded'
                    {org_clause}
            """)

            loan = db.execute(loan_query, params).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Funded loan {loan_id} not found")

            client_data = {
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "borrower_email": loan.borrower_email,
                "borrower_phone": loan.borrower_phone,
                "property_address": loan.property_address,
                "loan_amount": float(loan.amount) if loan.amount else 0,
                "rate": float(loan.rate) if loan.rate else 0,
                "program": loan.program,
                "funded_date": loan.funded_date.isoformat() if loan.funded_date else None,
                "months_since_close": int(loan.months_since_close or 0),
                "lo_name": loan.lo_name
            }

            # Calculate current estimated LTV
            if loan.property_value and loan.amount:
                ltv = calculate_ltv(float(loan.amount), float(loan.property_value), int(loan.months_since_close or 0))
                client_data["equity_analysis"] = {
                    "original_ltv": ltv["original_ltv"],
                    "estimated_current_ltv": ltv["current_ltv"],
                    "original_property_value": float(loan.property_value),
                    "estimated_current_value": ltv["current_value"],
                    "estimated_equity": ltv["equity"]
                }

            # Get interaction history if requested
            if input_data.get("include_history", True):
                history_query = text("""
                    SELECT
                        touchpoint_type, notes, created_at, created_by
                    FROM client_touchpoints
                    WHERE loan_id = :loan_id
                    ORDER BY created_at DESC
                    LIMIT 10
                """)

                history = db.execute(history_query, {"loan_id": loan_id}).fetchall()

                client_data["touchpoint_history"] = [
                    {
                        "type": h.touchpoint_type,
                        "notes": h.notes,
                        "date": h.created_at.isoformat() if h.created_at else None
                    }
                    for h in history
                ]

                # Days since last contact
                if history:
                    last_contact = history[0].created_at
                    if last_contact:
                        client_data["days_since_last_contact"] = (datetime.now() - last_contact).days

            return ToolResult(
                success=True,
                data={"client": client_data},
                message=f"Client: {loan.borrower_name}, funded {loan.funded_date}"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_refinance_candidates(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Find refinance candidates"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            rate_threshold = input_data.get("rate_drop_threshold", 0.5)
            min_equity = input_data.get("min_equity_percent", 20)
            min_months = input_data.get("min_months_since_close", 6)

            # Current market rate (would come from rate service in production)
            current_market_rate = 6.5

            org_clause = ""
            extra_params = {}
            if org_id:
                org_clause = "AND l.organization_id = :org_id"
                extra_params["org_id"] = org_id

            query = text(f"""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.borrower_email,
                    l.amount, l.rate, l.property_value, l.program,
                    l.funded_date,
                    EXTRACT(MONTH FROM AGE(CURRENT_DATE, l.funded_date)) as months_since_close
                FROM loans l
                WHERE l.stage = 'Funded'
                    AND l.rate > :target_rate
                    AND l.funded_date <= CURRENT_DATE - INTERVAL ':min_months months'
                    {org_clause}
                ORDER BY l.rate DESC
            """)

            results = db.execute(query, {
                "target_rate": current_market_rate + rate_threshold,
                "min_months": min_months,
                **extra_params
            }).fetchall()

            candidates = []
            for r in results:
                if not r.amount or not r.property_value:
                    continue

                months = int(r.months_since_close or 0)
                ltv = calculate_ltv(float(r.amount), float(r.property_value), months)

                if ltv["current_ltv"] > (100 - min_equity):
                    continue  # Not enough equity

                savings = calculate_rate_savings(float(r.rate), current_market_rate, ltv["current_balance"])

                candidates.append({
                    "loan_id": r.id,
                    "loan_number": r.loan_number,
                    "borrower_name": r.borrower_name,
                    "borrower_email": r.borrower_email,
                    "current_rate": float(r.rate),
                    "market_rate": current_market_rate,
                    "rate_savings": savings["rate_savings"],
                    "estimated_monthly_savings": savings["monthly_savings"],
                    "estimated_annual_savings": savings["annual_savings"],
                    "current_ltv": ltv["current_ltv"],
                    "months_since_close": months,
                    "priority": "high" if savings["rate_savings"] >= 1.0 else "medium" if savings["rate_savings"] >= 0.5 else "low"
                })

            # Sort by savings potential
            candidates.sort(key=lambda x: x["estimated_annual_savings"], reverse=True)

            total_savings = sum(c["estimated_annual_savings"] for c in candidates)

            return ToolResult(
                success=True,
                data={
                    "candidates": candidates[:50],
                    "count": len(candidates),
                    "current_market_rate": current_market_rate,
                    "total_potential_annual_savings": round(total_savings, 2),
                    "criteria": {
                        "rate_drop_threshold": rate_threshold,
                        "min_equity_percent": min_equity,
                        "min_months_since_close": min_months
                    }
                },
                message=f"Found {len(candidates)} refinance candidates with ${total_savings:,.0f} potential annual savings"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_anniversary_clients(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get clients with upcoming anniversaries"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            days_ahead = input_data.get("days_ahead", 30)
            anniversary_type = input_data.get("anniversary_type", "all")

            org_clause = ""
            org_params = {}
            if org_id:
                org_clause = "AND organization_id = :org_id"
                org_params["org_id"] = org_id

            clients = []

            if anniversary_type in ["funding", "all"]:
                # Loan funding anniversaries
                funding_query = text(f"""
                    SELECT
                        id, loan_number, borrower_name, borrower_email,
                        funded_date,
                        EXTRACT(YEAR FROM AGE(CURRENT_DATE, funded_date)) as years,
                        DATE_PART('day',
                            (DATE_TRUNC('year', CURRENT_DATE) + (funded_date - DATE_TRUNC('year', funded_date)))
                            - CURRENT_DATE
                        ) as days_until
                    FROM loans
                    WHERE stage = 'Funded'
                        AND funded_date IS NOT NULL
                        {org_clause}
                        AND (
                            (EXTRACT(MONTH FROM funded_date) = EXTRACT(MONTH FROM CURRENT_DATE)
                             AND EXTRACT(DAY FROM funded_date) BETWEEN EXTRACT(DAY FROM CURRENT_DATE)
                                AND EXTRACT(DAY FROM CURRENT_DATE + :days))
                            OR
                            (EXTRACT(MONTH FROM funded_date) = EXTRACT(MONTH FROM CURRENT_DATE + :days)
                             AND EXTRACT(DAY FROM funded_date) <= EXTRACT(DAY FROM CURRENT_DATE + :days))
                        )
                    ORDER BY days_until
                """)

                funding_results = db.execute(funding_query, {"days": days_ahead, **org_params}).fetchall()

                for r in funding_results:
                    clients.append({
                        "type": "funding_anniversary",
                        "loan_id": r.id,
                        "loan_number": r.loan_number,
                        "borrower_name": r.borrower_name,
                        "borrower_email": r.borrower_email,
                        "anniversary_date": r.funded_date.isoformat() if r.funded_date else None,
                        "years": int(r.years or 0) + 1,
                        "days_until": int(r.days_until or 0) if r.days_until and r.days_until >= 0 else 365 + int(r.days_until or 0)
                    })

            if anniversary_type in ["birthday", "all"]:
                # Birthday lookup would require contact/lead table with DOB
                birthday_query = text("""
                    SELECT
                        l.id as loan_id, l.loan_number, l.borrower_name, l.borrower_email,
                        c.date_of_birth,
                        DATE_PART('day',
                            (DATE_TRUNC('year', CURRENT_DATE) + (c.date_of_birth - DATE_TRUNC('year', c.date_of_birth)))
                            - CURRENT_DATE
                        ) as days_until
                    FROM loans l
                    JOIN contacts c ON l.borrower_email = c.email
                    WHERE l.stage = 'Funded'
                        AND c.date_of_birth IS NOT NULL
                        AND (
                            (EXTRACT(MONTH FROM c.date_of_birth) = EXTRACT(MONTH FROM CURRENT_DATE)
                             AND EXTRACT(DAY FROM c.date_of_birth) BETWEEN EXTRACT(DAY FROM CURRENT_DATE)
                                AND EXTRACT(DAY FROM CURRENT_DATE + :days))
                            OR
                            (EXTRACT(MONTH FROM c.date_of_birth) = EXTRACT(MONTH FROM CURRENT_DATE + :days)
                             AND EXTRACT(DAY FROM c.date_of_birth) <= EXTRACT(DAY FROM CURRENT_DATE + :days))
                        )
                    ORDER BY days_until
                """)

                try:
                    birthday_results = db.execute(birthday_query, {"days": days_ahead}).fetchall()

                    for r in birthday_results:
                        clients.append({
                            "type": "birthday",
                            "loan_id": r.loan_id,
                            "loan_number": r.loan_number,
                            "borrower_name": r.borrower_name,
                            "borrower_email": r.borrower_email,
                            "date": r.date_of_birth.isoformat() if r.date_of_birth else None,
                            "days_until": int(r.days_until or 0) if r.days_until and r.days_until >= 0 else 365 + int(r.days_until or 0)
                        })
                except Exception as e:
                    logger.exception(f"Failed to query birthday contacts: {e}")

            # Sort by days until
            clients.sort(key=lambda x: x.get("days_until", 999))

            return ToolResult(
                success=True,
                data={
                    "clients": clients,
                    "count": len(clients),
                    "days_ahead": days_ahead,
                    "anniversary_type": anniversary_type
                },
                message=f"Found {len(clients)} upcoming anniversaries in next {days_ahead} days"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_ltv_changes(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Calculate LTV changes for portfolio"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            loan_ids = input_data.get("loan_ids")
            appreciation_rate = input_data.get("appreciation_rate", 5.0)

            params = {"appreciation": appreciation_rate / 100}

            if loan_ids:
                id_filter = "AND id = ANY(:loan_ids)"
                params["loan_ids"] = loan_ids
            else:
                id_filter = ""

            org_clause = ""
            if org_id:
                org_clause = "AND organization_id = :org_id"
                params["org_id"] = org_id

            query = text(f"""
                SELECT
                    id, loan_number, borrower_name,
                    amount, property_value, funded_date,
                    EXTRACT(MONTH FROM AGE(CURRENT_DATE, funded_date)) as months_since_close
                FROM loans
                WHERE stage = 'Funded'
                    AND property_value IS NOT NULL
                    AND amount IS NOT NULL
                    {id_filter}
                    {org_clause}
                ORDER BY funded_date
            """)

            results = db.execute(query, params).fetchall()

            ltv_analysis = []
            equity_gained = 0

            for r in results:
                months = int(r.months_since_close or 0)
                ltv = calculate_ltv(float(r.amount), float(r.property_value), months, appreciation_rate / 100)

                original_equity = float(r.property_value) - float(r.amount)
                current_equity = ltv["equity"]
                equity_change = current_equity - original_equity
                equity_gained += equity_change

                ltv_analysis.append({
                    "loan_id": r.id,
                    "loan_number": r.loan_number,
                    "borrower_name": r.borrower_name,
                    "original_ltv": ltv["original_ltv"],
                    "current_ltv": ltv["current_ltv"],
                    "ltv_change": round(ltv["original_ltv"] - ltv["current_ltv"], 1),
                    "original_value": float(r.property_value),
                    "estimated_value": ltv["current_value"],
                    "original_equity": round(original_equity, 0),
                    "current_equity": round(current_equity, 0),
                    "equity_gained": round(equity_change, 0),
                    "months_since_close": months
                })

            # Group by LTV bands
            ltv_bands = {
                "under_60": 0,
                "60_70": 0,
                "70_80": 0,
                "over_80": 0
            }

            for item in ltv_analysis:
                ltv = item["current_ltv"]
                if ltv < 60:
                    ltv_bands["under_60"] += 1
                elif ltv < 70:
                    ltv_bands["60_70"] += 1
                elif ltv < 80:
                    ltv_bands["70_80"] += 1
                else:
                    ltv_bands["over_80"] += 1

            return ToolResult(
                success=True,
                data={
                    "analysis": ltv_analysis,
                    "count": len(ltv_analysis),
                    "appreciation_rate_used": appreciation_rate,
                    "total_equity_gained": round(equity_gained, 0),
                    "ltv_distribution": ltv_bands
                },
                message=f"LTV analysis: {len(ltv_analysis)} loans, ${equity_gained:,.0f} total equity gained"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_retention_risks(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Identify retention risks"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            risk_threshold = input_data.get("risk_threshold", "medium")
            limit = input_data.get("limit", 50)

            org_clause = ""
            extra_params = {}
            if org_id:
                org_clause = "AND l.organization_id = :org_id"
                extra_params["org_id"] = org_id

            # Risk factors:
            # - High rate compared to market
            # - Long time since last contact
            # - High equity (refi target)
            # - Near rate adjustment date (for ARMs)

            query = text(f"""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.borrower_email,
                    l.amount, l.rate, l.property_value, l.program,
                    l.funded_date,
                    EXTRACT(MONTH FROM AGE(CURRENT_DATE, l.funded_date)) as months_since_close,
                    (
                        SELECT MAX(created_at)
                        FROM client_touchpoints
                        WHERE loan_id = l.id
                    ) as last_contact
                FROM loans l
                WHERE l.stage = 'Funded'
                    {org_clause}
                ORDER BY l.rate DESC
                LIMIT :limit
            """)

            results = db.execute(query, {"limit": limit * 2, **extra_params}).fetchall()

            # Current market rate
            market_rate = 6.5

            risks = []
            for r in results:
                risk_score = 0
                risk_factors = []

                # Rate comparison
                if r.rate:
                    rate_diff = float(r.rate) - market_rate
                    if rate_diff > 1.0:
                        risk_score += 30
                        risk_factors.append(f"Rate {rate_diff:.2f}% above market")
                    elif rate_diff > 0.5:
                        risk_score += 15
                        risk_factors.append(f"Rate {rate_diff:.2f}% above market")

                # Contact recency
                if r.last_contact:
                    days_since_contact = (datetime.now() - r.last_contact).days
                    if days_since_contact > 180:
                        risk_score += 25
                        risk_factors.append(f"No contact in {days_since_contact} days")
                    elif days_since_contact > 90:
                        risk_score += 10
                        risk_factors.append(f"No contact in {days_since_contact} days")
                else:
                    risk_score += 30
                    risk_factors.append("No recorded contact")

                # Equity (high equity = more likely to be targeted)
                if r.property_value and r.amount:
                    ltv = calculate_ltv(float(r.amount), float(r.property_value), int(r.months_since_close or 0))
                    equity_percent = ltv["equity_percent"]

                    if equity_percent > 40:
                        risk_score += 20
                        risk_factors.append(f"High equity ({equity_percent:.0f}%)")

                # Determine risk level
                if risk_score >= 50:
                    risk_level = "high"
                elif risk_score >= 25:
                    risk_level = "medium"
                else:
                    risk_level = "low"

                # Filter by threshold
                threshold_scores = {"low": 0, "medium": 25, "high": 50}
                if risk_score >= threshold_scores.get(risk_threshold, 0):
                    risks.append({
                        "loan_id": r.id,
                        "loan_number": r.loan_number,
                        "borrower_name": r.borrower_name,
                        "borrower_email": r.borrower_email,
                        "current_rate": float(r.rate) if r.rate else None,
                        "risk_score": risk_score,
                        "risk_level": risk_level,
                        "risk_factors": risk_factors,
                        "last_contact": r.last_contact.isoformat() if r.last_contact else None
                    })

            # Sort by risk score
            risks.sort(key=lambda x: x["risk_score"], reverse=True)
            risks = risks[:limit]

            high_risk = sum(1 for r in risks if r["risk_level"] == "high")
            medium_risk = sum(1 for r in risks if r["risk_level"] == "medium")

            return ToolResult(
                success=True,
                data={
                    "risks": risks,
                    "count": len(risks),
                    "high_risk_count": high_risk,
                    "medium_risk_count": medium_risk,
                    "threshold": risk_threshold
                },
                message=f"Found {len(risks)} retention risks: {high_risk} high, {medium_risk} medium"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_touchpoint(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Create client touchpoint"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")

            query = text("""
                INSERT INTO client_touchpoints (
                    loan_id, touchpoint_type, notes,
                    next_touchpoint_date, created_by, organization_id, created_at
                ) VALUES (
                    :loan_id, :touchpoint_type, :notes,
                    :next_date, :created_by, :org_id, CURRENT_TIMESTAMP
                )
                RETURNING id, touchpoint_type, created_at
            """)

            result = db.execute(query, {
                "loan_id": input_data["loan_id"],
                "touchpoint_type": input_data["touchpoint_type"],
                "notes": input_data["notes"],
                "next_date": input_data.get("next_touchpoint_date"),
                "created_by": context.get("user_id", 1),
                "org_id": org_id
            }).fetchone()

            db.commit()

            self.audit_log(
                "create_touchpoint",
                entity_type="client_touchpoint",
                entity_id=str(result.id),
                details={
                    "loan_id": input_data["loan_id"],
                    "touchpoint_type": input_data["touchpoint_type"]
                }
            )

            return ToolResult(
                success=True,
                data={
                    "touchpoint_id": result.id,
                    "type": result.touchpoint_type,
                    "created_at": result.created_at.isoformat() if result.created_at else None,
                    "next_touchpoint": input_data.get("next_touchpoint_date")
                },
                message=f"Touchpoint logged: {input_data['touchpoint_type']}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_referral_opportunities(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Identify referral opportunities"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            min_satisfaction = input_data.get("min_satisfaction_score", 8)
            min_months = input_data.get("min_months_since_close", 3)

            org_clause = ""
            extra_params = {}
            if org_id:
                org_clause = "AND l.organization_id = :org_id"
                extra_params["org_id"] = org_id

            # In production, this would check NPS scores, review history, etc.
            # For now, base on engagement and loan success

            query = text(f"""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.borrower_email,
                    l.funded_date, l.program,
                    EXTRACT(MONTH FROM AGE(CURRENT_DATE, l.funded_date)) as months_since_close,
                    (
                        SELECT COUNT(*)
                        FROM client_touchpoints
                        WHERE loan_id = l.id
                    ) as touchpoint_count,
                    (
                        SELECT COUNT(*)
                        FROM loans l2
                        WHERE l2.referral_source = l.borrower_email
                    ) as previous_referrals
                FROM loans l
                WHERE l.stage = 'Funded'
                    AND l.funded_date <= CURRENT_DATE - INTERVAL ':min_months months'
                    {org_clause}
                ORDER BY l.funded_date DESC
            """)

            results = db.execute(query, {"min_months": min_months, **extra_params}).fetchall()

            opportunities = []
            for r in results:
                # Calculate referral score
                score = 5  # Base score

                # Positive touchpoints indicate good relationship
                touchpoints = r.touchpoint_count or 0
                if touchpoints >= 3:
                    score += 2
                elif touchpoints >= 1:
                    score += 1

                # Previous referrals indicate willingness
                if r.previous_referrals and r.previous_referrals > 0:
                    score += 2

                # Recent closings more likely to refer
                months = int(r.months_since_close or 0)
                if months <= 6:
                    score += 1
                elif months <= 12:
                    score += 0.5

                if score >= min_satisfaction:
                    opportunities.append({
                        "loan_id": r.id,
                        "loan_number": r.loan_number,
                        "borrower_name": r.borrower_name,
                        "borrower_email": r.borrower_email,
                        "funded_date": r.funded_date.isoformat() if r.funded_date else None,
                        "months_since_close": months,
                        "referral_score": round(score, 1),
                        "touchpoint_count": touchpoints,
                        "previous_referrals": r.previous_referrals or 0,
                        "recommended_action": "Request referral" if score >= 8 else "Nurture first"
                    })

            # Sort by score
            opportunities.sort(key=lambda x: x["referral_score"], reverse=True)

            high_potential = sum(1 for o in opportunities if o["referral_score"] >= 8)

            return ToolResult(
                success=True,
                data={
                    "opportunities": opportunities[:50],
                    "count": len(opportunities),
                    "high_potential_count": high_potential,
                    "criteria": {
                        "min_satisfaction_score": min_satisfaction,
                        "min_months_since_close": min_months
                    }
                },
                message=f"Found {len(opportunities)} referral opportunities, {high_potential} high potential"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
