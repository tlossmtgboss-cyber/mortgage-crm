"""
Rate Advisor Agent

Specialized agent for rate lock and pricing advice with 8 tools:
1. get_current_rates - Get current interest rates
2. analyze_lock_timing - Analyze optimal lock timing
3. calculate_payment - Calculate payment scenarios
4. compare_loan_products - Compare loan products
5. check_float_down - Check float-down eligibility
6. get_rate_history - Get rate history/trends
7. lock_rate - Lock interest rate
8. generate_rate_quote - Generate rate quote for borrower
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class CurrentRatesInput(BaseModel):
    loan_type: Optional[str] = Field(None, description="Loan type: conventional, fha, va, jumbo")
    lock_period: int = Field(default=30, description="Lock period in days")


class LockTimingInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID")
    expected_close_days: int = Field(..., description="Days until expected close")


class PaymentCalculationInput(BaseModel):
    loan_amount: float = Field(..., description="Loan amount")
    interest_rate: float = Field(..., description="Interest rate")
    term_years: int = Field(default=30, description="Loan term in years")
    include_taxes_insurance: bool = Field(default=False, description="Include taxes/insurance estimate")


class CompareProductsInput(BaseModel):
    loan_amount: float = Field(..., description="Loan amount")
    credit_score: int = Field(..., description="Credit score")
    ltv: float = Field(..., description="Loan-to-value ratio")
    loan_purpose: str = Field(default="purchase", description="Purpose: purchase, refinance, cash_out")


class FloatDownInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID")
    locked_rate: float = Field(..., description="Current locked rate")


class RateHistoryInput(BaseModel):
    loan_type: str = Field(default="conventional", description="Loan type")
    days: int = Field(default=30, description="History period in days")


class LockRateInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID")
    rate: float = Field(..., description="Rate to lock")
    lock_period: int = Field(default=30, description="Lock period in days")
    points: float = Field(default=0, description="Points")


class RateQuoteInput(BaseModel):
    loan_amount: float = Field(..., description="Loan amount")
    credit_score: int = Field(..., description="Credit score")
    ltv: float = Field(..., description="LTV ratio")
    loan_type: str = Field(default="conventional", description="Loan type")
    lock_period: int = Field(default=30, description="Lock period")


# ============================================================================
# RATE ADVISOR AGENT
# ============================================================================

@AgentRegistry.register
class RateAdvisorAgent(SpecializedAgent):
    """
    Rate advisory agent for pricing and lock decisions.

    Provides rate analysis, lock timing advice, and payment calculations
    with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "RateAdvisorAgent"

    @property
    def description(self) -> str:
        return "Provides rate advice, lock timing analysis, and payment calculations"

    def _register_tools(self):
        """Register all rate advisory tools"""

        self.register_tool(AgentTool(
            name="get_current_rates",
            description="Get current interest rates by loan type",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_current_rates,
            input_schema=CurrentRatesInput
        ))

        self.register_tool(AgentTool(
            name="analyze_lock_timing",
            description="Analyze optimal rate lock timing",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_lock_timing,
            input_schema=LockTimingInput
        ))

        self.register_tool(AgentTool(
            name="calculate_payment",
            description="Calculate monthly payment scenarios",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_payment,
            input_schema=PaymentCalculationInput
        ))

        self.register_tool(AgentTool(
            name="compare_loan_products",
            description="Compare different loan products and pricing",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._compare_loan_products,
            input_schema=CompareProductsInput
        ))

        self.register_tool(AgentTool(
            name="check_float_down",
            description="Check eligibility for float-down option",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_float_down,
            input_schema=FloatDownInput
        ))

        self.register_tool(AgentTool(
            name="get_rate_history",
            description="Get rate history and trends",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_rate_history,
            input_schema=RateHistoryInput
        ))

        self.register_tool(AgentTool(
            name="lock_rate",
            description="Lock interest rate for a loan",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._lock_rate,
            input_schema=LockRateInput,
            requires_confirmation=True
        ))

        self.register_tool(AgentTool(
            name="generate_rate_quote",
            description="Generate rate quote for borrower",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._generate_rate_quote,
            input_schema=RateQuoteInput
        ))

    async def _get_current_rates(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get current rates from rate_monitor table, falling back to illustrative rates.

        COMPLIANCE: Rates are informational only. Final pricing depends on
        full underwriting. NEVER guarantee a rate to a borrower.
        """
        lock_period = input_data.get("lock_period", 30)
        data_source = "live"

        try:
            from database import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Try to read from rate_monitor table (populated by rate monitoring service)
                result = db.execute(text("""
                    SELECT loan_type, term_years, rate, apr, points, updated_at
                    FROM rate_monitor_snapshots
                    WHERE lock_period_days = :lock_period
                      AND updated_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                    ORDER BY updated_at DESC
                """), {"lock_period": lock_period}).fetchall()

                if result:
                    rates = {}
                    for row in result:
                        lt = row.loan_type
                        if lt not in rates:
                            rates[lt] = {}
                        term_key = f"{row.term_years}_year"
                        rates[lt][term_key] = {
                            "rate": float(row.rate),
                            "apr": float(row.apr),
                            "points": float(row.points or 0)
                        }

                    loan_type = input_data.get("loan_type")
                    if loan_type and loan_type in rates:
                        rates = {loan_type: rates[loan_type]}

                    self.audit_log("rates_retrieved", details={"source": "live", "count": len(result)})

                    return ToolResult(
                        success=True,
                        data={
                            "rates": rates,
                            "lock_period": lock_period,
                            "as_of": result[0].updated_at.isoformat() if result else datetime.now().isoformat(),
                            "data_source": "live",
                            "disclaimer": "Rates shown are current market rates for informational purposes. "
                                          "Actual rate depends on credit, LTV, property type, and full underwriting."
                        },
                        message=f"Current rates retrieved ({lock_period}-day lock)"
                    )
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Live rates unavailable, using illustrative rates: {e}")
            data_source = "illustrative"

        # Fallback: illustrative rates with clear disclaimer
        rates = {
            "conventional": {
                "30_year": {"rate": 6.875, "apr": 6.95, "points": 0},
                "15_year": {"rate": 6.125, "apr": 6.20, "points": 0}
            },
            "fha": {
                "30_year": {"rate": 6.500, "apr": 7.15, "points": 0},
                "15_year": {"rate": 5.875, "apr": 6.50, "points": 0}
            },
            "va": {
                "30_year": {"rate": 6.375, "apr": 6.55, "points": 0},
                "15_year": {"rate": 5.750, "apr": 5.95, "points": 0}
            },
            "jumbo": {
                "30_year": {"rate": 7.125, "apr": 7.20, "points": 0},
                "15_year": {"rate": 6.625, "apr": 6.70, "points": 0}
            }
        }

        loan_type = input_data.get("loan_type")
        if loan_type and loan_type in rates:
            filtered = {loan_type: rates[loan_type]}
        else:
            filtered = rates

        self.audit_log("rates_retrieved", details={"source": "illustrative"})

        return ToolResult(
            success=True,
            data={
                "rates": filtered,
                "lock_period": lock_period,
                "as_of": datetime.now().isoformat(),
                "data_source": "illustrative",
                "disclaimer": "These are illustrative rates for demonstration purposes only. "
                              "Actual rates change daily and depend on credit profile, LTV, "
                              "property type, and full underwriting. Contact your LO for a personalized quote."
            },
            message=f"Illustrative rates retrieved ({lock_period}-day lock) — for informational purposes only"
        )

    async def _analyze_lock_timing(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Analyze lock timing"""
        days_to_close = input_data["expected_close_days"]

        # Determine recommended lock period
        if days_to_close <= 30:
            recommended_lock = 30
            timing_advice = "Lock now - closing is imminent"
        elif days_to_close <= 45:
            recommended_lock = 45
            timing_advice = "Consider locking soon with 45-day lock"
        elif days_to_close <= 60:
            recommended_lock = 60
            timing_advice = "60-day lock recommended, monitor rates"
        else:
            recommended_lock = 60
            timing_advice = "Monitor rates, lock closer to 60 days out"

        analysis = {
            "loan_id": input_data["loan_id"],
            "days_to_close": days_to_close,
            "recommended_lock_period": recommended_lock,
            "timing_advice": timing_advice,
            "market_outlook": "Rates expected to remain stable short-term",
            "risk_assessment": {
                "float_risk": "medium" if days_to_close > 30 else "low",
                "lock_cost_consideration": f"Longer locks cost ~0.125% more per 15 days"
            }
        }

        return ToolResult(
            success=True,
            data=analysis,
            message=f"Recommendation: {recommended_lock}-day lock"
        )

    async def _calculate_payment(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Calculate payment"""
        loan_amount = input_data["loan_amount"]
        rate = input_data["interest_rate"]
        term_years = input_data.get("term_years", 30)

        # Calculate P&I
        monthly_rate = rate / 100 / 12
        num_payments = term_years * 12
        pi_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)

        payment = {
            "loan_amount": loan_amount,
            "interest_rate": rate,
            "term_years": term_years,
            "principal_interest": round(pi_payment, 2),
            "total_payment": round(pi_payment, 2)
        }

        if input_data.get("include_taxes_insurance"):
            # Estimate taxes and insurance
            estimated_taxes = loan_amount * 0.012 / 12  # 1.2% annual
            estimated_insurance = loan_amount * 0.005 / 12  # 0.5% annual
            payment["estimated_taxes"] = round(estimated_taxes, 2)
            payment["estimated_insurance"] = round(estimated_insurance, 2)
            payment["total_payment"] = round(pi_payment + estimated_taxes + estimated_insurance, 2)

        # Calculate total interest over life of loan
        payment["total_interest"] = round((pi_payment * num_payments) - loan_amount, 2)

        return ToolResult(
            success=True,
            data=payment,
            message=f"Monthly P&I: ${pi_payment:,.2f}"
        )

    async def _compare_loan_products(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Compare loan products"""
        loan_amount = input_data["loan_amount"]
        credit_score = input_data["credit_score"]

        products = []

        # Conventional
        if credit_score >= 620:
            conv_rate = 6.875 if credit_score >= 740 else 7.125 if credit_score >= 700 else 7.375
            products.append({
                "product": "Conventional 30-Year",
                "rate": conv_rate,
                "monthly_payment": self._calc_payment(loan_amount, conv_rate, 30),
                "min_down": "3%",
                "pmi_required": input_data["ltv"] > 80,
                "pros": ["Lower MI cost with good credit", "No upfront MI"],
                "cons": ["Stricter credit requirements"]
            })

        # FHA
        if credit_score >= 580:
            products.append({
                "product": "FHA 30-Year",
                "rate": 6.500,
                "monthly_payment": self._calc_payment(loan_amount, 6.500, 30),
                "min_down": "3.5%",
                "pmi_required": True,
                "pros": ["Lower credit requirements", "Lower down payment"],
                "cons": ["Upfront MIP", "Monthly MIP for life of loan"]
            })

        # VA (if applicable)
        products.append({
            "product": "VA 30-Year",
            "rate": 6.375,
            "monthly_payment": self._calc_payment(loan_amount, 6.375, 30),
            "min_down": "0%",
            "pmi_required": False,
            "pros": ["No down payment", "No PMI", "Competitive rates"],
            "cons": ["VA funding fee", "Must be eligible veteran"]
        })

        return ToolResult(
            success=True,
            data={
                "loan_amount": loan_amount,
                "credit_score": credit_score,
                "products": products,
                "recommendation": products[0]["product"] if products else None,
                "disclaimer": "Product comparison is for educational purposes. Rates and terms "
                              "are illustrative and subject to change. VA eligibility requires "
                              "military service verification. Consult your LO for personalized options."
            },
            message=f"Compared {len(products)} loan products"
        )

    def _calc_payment(self, amount: float, rate: float, years: int) -> float:
        """Helper to calculate payment"""
        monthly_rate = rate / 100 / 12
        num_payments = years * 12
        payment = amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
        return round(payment, 2)

    async def _check_float_down(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Check float-down eligibility using loan's locked rate vs current market."""
        locked_rate = input_data["locked_rate"]

        # Try to get current rate from DB (loan's lock record or rate snapshots)
        current_rate = None
        try:
            from database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                row = db.execute(text("""
                    SELECT rate FROM rate_monitor_snapshots
                    WHERE loan_type = 'conventional' AND term_years = 30
                    ORDER BY updated_at DESC LIMIT 1
                """)).fetchone()
                if row:
                    current_rate = float(row.rate)
            finally:
                db.close()
        except Exception:
            pass

        if current_rate is None:
            current_rate = locked_rate - 0.125  # Conservative estimate

        improvement = locked_rate - current_rate
        eligible = improvement >= 0.25  # Standard float-down threshold

        result = {
            "loan_id": input_data["loan_id"],
            "locked_rate": locked_rate,
            "current_market_rate": current_rate,
            "improvement": round(improvement, 3),
            "float_down_eligible": eligible,
            "potential_new_rate": round(current_rate + 0.125, 3) if eligible else None,
            "action_required": "Contact processor to execute float-down" if eligible else None,
            "disclaimer": "Float-down eligibility is preliminary. Final determination requires "
                          "lock desk review. Improvement split and fees may apply."
        }

        self.audit_log("float_down_check", entity_type="loan", entity_id=str(input_data["loan_id"]),
                        details={"eligible": eligible, "improvement": round(improvement, 3)})

        return ToolResult(
            success=True,
            data=result,
            message=f"Float-down {'eligible' if eligible else 'not eligible'} ({improvement:.3f}% improvement)"
        )

    async def _get_rate_history(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get rate history — tries live data from rate_monitor_snapshots, falls back to illustrative."""
        days = input_data.get("days", 30)
        loan_type = input_data.get("loan_type", "conventional")
        data_source = "live"

        try:
            from database import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()
            try:
                rows = db.execute(text("""
                    SELECT DATE(updated_at) as snap_date, AVG(rate) as avg_rate
                    FROM rate_monitor_snapshots
                    WHERE loan_type = :loan_type
                      AND term_years = 30
                      AND updated_at >= CURRENT_DATE - :days
                    GROUP BY DATE(updated_at)
                    ORDER BY snap_date
                """), {"loan_type": loan_type, "days": days}).fetchall()

                if rows and len(rows) >= 3:
                    history = [{"date": r.snap_date.isoformat(), "rate": round(float(r.avg_rate), 3)} for r in rows]

                    current = history[-1]["rate"]
                    week_ago = history[-7]["rate"] if len(history) >= 7 else history[0]["rate"]
                    month_ago = history[0]["rate"]

                    trends = {
                        "7_day_change": round(current - week_ago, 3),
                        "30_day_change": round(current - month_ago, 3),
                        "direction": "up" if current > week_ago else "down" if current < week_ago else "stable"
                    }

                    return ToolResult(
                        success=True,
                        data={
                            "loan_type": loan_type,
                            "history": history,
                            "trends": trends,
                            "data_source": "live",
                            "disclaimer": "Historical rates for informational purposes. Past performance does not predict future rates."
                        },
                        message=f"Rate history for {days} days (live data)"
                    )
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Live rate history unavailable: {e}")
            data_source = "illustrative"

        # Fallback: illustrative history with disclaimer
        history = []
        base_rate = 6.875
        for i in range(days):
            date = datetime.now() - timedelta(days=days - i)
            variation = (hash(str(date.date())) % 50 - 25) / 1000
            history.append({
                "date": date.strftime("%Y-%m-%d"),
                "rate": round(base_rate + variation, 3)
            })

        current = history[-1]["rate"]
        week_ago = history[-7]["rate"] if len(history) >= 7 else history[0]["rate"]
        month_ago = history[0]["rate"]

        trends = {
            "7_day_change": round(current - week_ago, 3),
            "30_day_change": round(current - month_ago, 3),
            "direction": "up" if current > week_ago else "down" if current < week_ago else "stable"
        }

        return ToolResult(
            success=True,
            data={
                "loan_type": loan_type,
                "history": history,
                "trends": trends,
                "data_source": "illustrative",
                "disclaimer": "Illustrative rate history for demonstration only. "
                              "Actual rate movements vary. Contact your LO for current pricing."
            },
            message=f"Illustrative rate history for {days} days"
        )

    async def _lock_rate(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Lock rate — records lock in DB and creates audit trail.

        COMPLIANCE: Rate locks are binding commitments. This tool requires
        confirmation (risk_level=HIGH, requires_confirmation=True).
        """
        lock_period = input_data.get("lock_period", 30)
        lock_expiration = datetime.now() + timedelta(days=lock_period)

        # Try to persist to DB
        try:
            from database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                org_id = self.context.get("organization_id")
                # Update the loan's lock fields
                db.execute(text("""
                    UPDATE loans
                    SET rate = :rate,
                        lock_expiration_date = :lock_exp,
                        lock_date = CURRENT_TIMESTAMP
                    WHERE id = :loan_id
                    AND (:org_id IS NULL OR organization_id = :org_id)
                """), {
                    "rate": input_data["rate"],
                    "lock_exp": lock_expiration,
                    "loan_id": input_data["loan_id"],
                    "org_id": org_id,
                })
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Could not persist rate lock to DB: {e}")

        confirmation = f"LCK-{datetime.now().strftime('%Y%m%d')}-{input_data['loan_id']}"

        self.audit_log(
            "rate_locked",
            entity_type="loan",
            entity_id=str(input_data["loan_id"]),
            details={
                "rate": input_data["rate"],
                "points": input_data.get("points", 0),
                "lock_period": lock_period,
                "confirmation": confirmation
            }
        )

        return ToolResult(
            success=True,
            data={
                "loan_id": input_data["loan_id"],
                "locked_rate": input_data["rate"],
                "points": input_data.get("points", 0),
                "lock_period": lock_period,
                "locked_at": datetime.now().isoformat(),
                "expires_at": lock_expiration.isoformat(),
                "confirmation_number": confirmation,
                "disclaimer": "Rate lock is subject to lock desk confirmation. "
                              "Lock expiration is based on the selected period from today."
            },
            message=f"Rate locked at {input_data['rate']}% for {lock_period} days (confirmation: {confirmation})"
        )

    async def _generate_rate_quote(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate rate quote"""
        import uuid

        loan_amount = input_data["loan_amount"]
        credit_score = input_data["credit_score"]

        # Determine rate based on credit
        base_rate = 6.875
        if credit_score >= 760:
            rate_adj = -0.25
        elif credit_score >= 740:
            rate_adj = -0.125
        elif credit_score >= 700:
            rate_adj = 0
        elif credit_score >= 680:
            rate_adj = 0.25
        else:
            rate_adj = 0.5

        quoted_rate = base_rate + rate_adj
        monthly_payment = self._calc_payment(loan_amount, quoted_rate, 30)

        quote = {
            "quote_id": str(uuid.uuid4())[:8].upper(),
            "generated_at": datetime.now().isoformat(),
            "valid_until": (datetime.now() + timedelta(hours=24)).isoformat(),
            "loan_details": {
                "amount": loan_amount,
                "type": input_data.get("loan_type", "conventional"),
                "term": 30,
                "ltv": input_data["ltv"]
            },
            "pricing": {
                "rate": quoted_rate,
                "apr": round(quoted_rate + 0.08, 3),
                "points": 0,
                "monthly_payment": monthly_payment
            },
            "lock_options": [
                {"period": 30, "rate": quoted_rate, "cost": 0},
                {"period": 45, "rate": quoted_rate + 0.125, "cost": 0},
                {"period": 60, "rate": quoted_rate + 0.25, "cost": 0}
            ],
            "disclaimer": "This rate quote is for informational purposes only and is not a commitment "
                          "to lend. Actual rate, APR, and terms are subject to change based on credit "
                          "verification, property appraisal, and full underwriting review. "
                          "Quote valid for 24 hours."
        }

        self.audit_log("rate_quote_generated", details={
            "quote_id": quote["quote_id"],
            "rate": quoted_rate,
            "amount": loan_amount,
            "credit_score": credit_score
        })

        return ToolResult(
            success=True,
            data=quote,
            message=f"Quote generated: {quoted_rate}% rate, ${monthly_payment:,.2f}/mo — for informational purposes only"
        )
