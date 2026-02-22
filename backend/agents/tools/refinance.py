"""
Perennia AI - Refinance Advisor Agent Tools
Tools for scoring refinance opportunities, calculating savings,
identifying candidates, and comparing scenarios.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
    is_sqlite, sql_now,
)

from ..utils.financial_calcs import (
    get_appreciation_rate,
    calculate_monthly_payment,
    calculate_remaining_balance,
    estimate_current_property_value,
    calculate_rate_savings,
)


# Default market rate for comparisons
DEFAULT_MARKET_RATE = 6.5  # Current market rate assumption (pct)
DEFAULT_CLOSING_COST_PCT = 0.02  # 2% of loan amount


def _get_market_rate() -> float:
    """Get current market rate from settings or default."""
    try:
        row = execute_single("""
            SELECT value FROM settings WHERE key = 'current_market_rate' LIMIT 1
        """)
        if row and row["value"]:
            return float(row["value"])
    except Exception as e:
        logger.warning(f"Error fetching market rate from settings: {e}")
    return DEFAULT_MARKET_RATE


# =============================================================================
# Tool 1: Score Refi Opportunity
# =============================================================================

@mortgage_tool(
    name="score_refi_opportunity",
    description="Calculate a 0-100 refinance opportunity score for a MUM client based on rate differential, equity, loan size, timing, and breakeven",
    agent_roles=["refinance_advisor", "customer_intelligence", "lead_nurturer"],
    risk_level="low",
    examples=[
        "What's the refi score for this client?",
        "Score the refinance opportunity",
        "Is this a good refi candidate?",
    ],
)
def score_refi_opportunity(
    mum_client_id: int,
    market_rate: Optional[float] = None,
) -> ToolResult:
    """Calculate refi opportunity score (0-100)."""
    try:
        client = execute_single("""
            SELECT id, client_name, interest_rate, original_rate,
                   original_loan_amount, current_loan_amount,
                   appraisal_value_at_closing, term, first_payment_date,
                   original_close_date, property_state, property_zip
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        if market_rate is None:
            market_rate = _get_market_rate()

        current_rate = float(client["interest_rate"] or client["original_rate"] or 0)
        original_amount = float(client["original_loan_amount"] or 0)
        original_value = float(client["appraisal_value_at_closing"] or 0)
        term = client["term"] or 360
        state = client["property_state"]

        if current_rate <= 0 or original_amount <= 0:
            return ToolResult.error("Insufficient loan data for scoring")

        # Calculate months since first payment
        first_pmt = client["first_payment_date"] or client["original_close_date"]
        if first_pmt:
            if isinstance(first_pmt, str):
                first_pmt = datetime.fromisoformat(first_pmt)
            months_passed = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
        else:
            months_passed = 0

        # Remaining balance
        remaining_balance = calculate_remaining_balance(
            original_amount, current_rate / 100, term, months_passed
        )

        # Current property value
        appreciation_rate = get_appreciation_rate(state)
        current_value = estimate_current_property_value(original_value, months_passed, appreciation_rate)
        current_ltv = (remaining_balance / current_value * 100) if current_value > 0 else 100

        # --- Score Components ---
        score_breakdown = {}

        # 1. Rate differential (0-35 points)
        rate_diff = current_rate - market_rate
        if rate_diff >= 2.0:
            score_breakdown["rate_differential"] = 35
        elif rate_diff >= 1.5:
            score_breakdown["rate_differential"] = 30
        elif rate_diff >= 1.0:
            score_breakdown["rate_differential"] = 25
        elif rate_diff >= 0.75:
            score_breakdown["rate_differential"] = 20
        elif rate_diff >= 0.5:
            score_breakdown["rate_differential"] = 15
        elif rate_diff >= 0.25:
            score_breakdown["rate_differential"] = 8
        elif rate_diff > 0:
            score_breakdown["rate_differential"] = 3
        else:
            score_breakdown["rate_differential"] = 0

        # 2. Equity position (0-20 points)
        equity_pct = 100 - current_ltv
        if equity_pct >= 40:
            score_breakdown["equity_position"] = 20
        elif equity_pct >= 30:
            score_breakdown["equity_position"] = 17
        elif equity_pct >= 20:
            score_breakdown["equity_position"] = 14
        elif equity_pct >= 10:
            score_breakdown["equity_position"] = 8
        elif equity_pct >= 5:
            score_breakdown["equity_position"] = 4
        else:
            score_breakdown["equity_position"] = 0

        # 3. Loan size (0-15 points) — larger = more absolute savings
        if remaining_balance >= 500000:
            score_breakdown["loan_size"] = 15
        elif remaining_balance >= 400000:
            score_breakdown["loan_size"] = 13
        elif remaining_balance >= 300000:
            score_breakdown["loan_size"] = 10
        elif remaining_balance >= 200000:
            score_breakdown["loan_size"] = 7
        elif remaining_balance >= 100000:
            score_breakdown["loan_size"] = 4
        else:
            score_breakdown["loan_size"] = 1

        # 4. Time in loan (0-10 points) — penalty < 12mo, bonus > 24mo
        if months_passed >= 36:
            score_breakdown["time_in_loan"] = 10
        elif months_passed >= 24:
            score_breakdown["time_in_loan"] = 8
        elif months_passed >= 18:
            score_breakdown["time_in_loan"] = 6
        elif months_passed >= 12:
            score_breakdown["time_in_loan"] = 4
        elif months_passed >= 6:
            score_breakdown["time_in_loan"] = 2
        else:
            score_breakdown["time_in_loan"] = 0

        # 5. Rate trend (0-10 points) — static for now (rates assumed declining)
        score_breakdown["rate_trend"] = 5 if rate_diff > 0 else 0

        # 6. Breakeven (0-10 points)
        closing_costs = remaining_balance * DEFAULT_CLOSING_COST_PCT
        savings = calculate_rate_savings(current_rate, market_rate, remaining_balance, 360)
        monthly_savings = savings["monthly_savings"]
        if monthly_savings > 0:
            breakeven_months = closing_costs / monthly_savings
            if breakeven_months <= 12:
                score_breakdown["breakeven"] = 10
            elif breakeven_months <= 24:
                score_breakdown["breakeven"] = 7
            elif breakeven_months <= 36:
                score_breakdown["breakeven"] = 4
            elif breakeven_months <= 48:
                score_breakdown["breakeven"] = 2
            else:
                score_breakdown["breakeven"] = 0
        else:
            breakeven_months = float('inf')
            score_breakdown["breakeven"] = 0

        total_score = sum(score_breakdown.values())
        total_score = min(100, max(0, total_score))

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "refi_score": total_score,
            "score_breakdown": score_breakdown,
            "inputs": {
                "current_rate": current_rate,
                "market_rate": market_rate,
                "rate_differential": round(rate_diff, 3),
                "remaining_balance": round(remaining_balance, 2),
                "current_value": round(current_value, 2),
                "current_ltv": round(current_ltv, 1),
                "equity_pct": round(equity_pct, 1),
                "months_in_loan": months_passed,
                "monthly_savings": round(monthly_savings, 2),
                "breakeven_months": round(breakeven_months, 1) if breakeven_months != float('inf') else None,
                "closing_costs_est": round(closing_costs, 2),
            },
            "recommendation": (
                "Strong refinance candidate" if total_score >= 70
                else "Worth exploring" if total_score >= 50
                else "Marginal opportunity" if total_score >= 30
                else "Not recommended at current rates"
            ),
        }

        return ToolResult.success(
            data=data,
            message=f"{client['client_name']}: Refi score {total_score}/100 — {data['recommendation']}",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 2: Calculate Refi Savings
# =============================================================================

@mortgage_tool(
    name="calculate_refi_savings",
    description="Calculate monthly, annual, and lifetime savings from refinancing a MUM client",
    agent_roles=["refinance_advisor", "customer_intelligence"],
    risk_level="low",
    examples=[
        "How much would this client save by refinancing?",
        "Calculate refinance savings",
    ],
)
def calculate_refi_savings(
    mum_client_id: int,
    new_rate: Optional[float] = None,
    new_term: int = 360,
) -> ToolResult:
    """Calculate refinance savings."""
    try:
        client = execute_single("""
            SELECT id, client_name, interest_rate, original_rate,
                   original_loan_amount, term, first_payment_date,
                   original_close_date
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        if new_rate is None:
            new_rate = _get_market_rate()

        current_rate = float(client["interest_rate"] or client["original_rate"] or 0)
        original_amount = float(client["original_loan_amount"] or 0)
        term = client["term"] or 360

        # Months passed
        first_pmt = client["first_payment_date"] or client["original_close_date"]
        if first_pmt:
            if isinstance(first_pmt, str):
                first_pmt = datetime.fromisoformat(first_pmt)
            months_passed = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
        else:
            months_passed = 0

        remaining_balance = calculate_remaining_balance(
            original_amount, current_rate / 100, term, months_passed
        )

        # Current payment
        current_payment = calculate_monthly_payment(original_amount, current_rate / 100, term)

        # New payment on remaining balance at new rate/term
        new_payment = calculate_monthly_payment(remaining_balance, new_rate / 100, new_term)

        monthly_savings = current_payment - new_payment
        annual_savings = monthly_savings * 12
        lifetime_savings = monthly_savings * new_term

        # Closing costs estimate
        closing_costs = remaining_balance * DEFAULT_CLOSING_COST_PCT
        net_lifetime = lifetime_savings - closing_costs
        breakeven_months = (closing_costs / monthly_savings) if monthly_savings > 0 else None

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "current_rate": current_rate,
            "new_rate": new_rate,
            "rate_reduction": round(current_rate - new_rate, 3),
            "remaining_balance": round(remaining_balance, 2),
            "remaining_balance_formatted": format_currency(remaining_balance),
            "current_payment": round(current_payment, 2),
            "current_payment_formatted": format_currency(current_payment),
            "new_payment": round(new_payment, 2),
            "new_payment_formatted": format_currency(new_payment),
            "monthly_savings": round(monthly_savings, 2),
            "monthly_savings_formatted": format_currency(monthly_savings),
            "annual_savings": round(annual_savings, 2),
            "annual_savings_formatted": format_currency(annual_savings),
            "lifetime_savings": round(lifetime_savings, 2),
            "lifetime_savings_formatted": format_currency(lifetime_savings),
            "estimated_closing_costs": round(closing_costs, 2),
            "net_lifetime_savings": round(net_lifetime, 2),
            "breakeven_months": round(breakeven_months, 1) if breakeven_months else None,
            "new_term_months": new_term,
        }

        return ToolResult.success(
            data=data,
            message=f"{client['client_name']}: Save {format_currency(monthly_savings)}/mo ({format_currency(annual_savings)}/yr) at {new_rate}%",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 3: Get Refi Candidates
# =============================================================================

@mortgage_tool(
    name="get_refi_candidates",
    description="Find MUM clients above a refinance score threshold, ranked by opportunity",
    agent_roles=["refinance_advisor", "lead_nurturer"],
    risk_level="low",
    examples=[
        "Show me refinance candidates",
        "Who should we target for refi?",
        "List top refi opportunities",
    ],
)
def get_refi_candidates(
    min_score: int = 50,
    limit: int = 25,
    user_id: Optional[int] = None,
) -> ToolResult:
    """Get MUM clients ranked by refi opportunity."""
    try:
        params = {"min_score": min_score, "lim": limit}
        user_filter = ""
        if user_id:
            user_filter = "AND mc.user_id = :uid"
            params["uid"] = user_id

        candidates = execute_query(f"""
            SELECT id, client_name, interest_rate, original_rate,
                   original_loan_amount, refi_score, estimated_savings,
                   estimated_equity, current_ltv, property_state,
                   first_payment_date, original_close_date, term
            FROM mum_clients mc
            WHERE mc.status = 'Active'
                AND mc.refi_score >= :min_score
                {user_filter}
            ORDER BY mc.refi_score DESC
            LIMIT :lim
        """, params)

        if not candidates:
            return ToolResult.no_data(f"No candidates found with score >= {min_score}")

        result_list = []
        for c in candidates:
            current_rate = float(c["interest_rate"] or c["original_rate"] or 0)
            result_list.append({
                "id": c["id"],
                "client_name": c["client_name"],
                "refi_score": c["refi_score"] or 0,
                "current_rate": current_rate,
                "estimated_savings": float(c["estimated_savings"] or 0),
                "estimated_savings_formatted": format_currency(c["estimated_savings"]),
                "estimated_equity": float(c["estimated_equity"] or 0),
                "estimated_equity_formatted": format_currency(c["estimated_equity"]),
                "current_ltv": round(float(c["current_ltv"] or 0), 1),
                "state": c["property_state"],
            })

        data = {
            "min_score": min_score,
            "total_candidates": len(result_list),
            "candidates": result_list,
        }

        return ToolResult.success(
            data=data,
            message=f"{len(result_list)} refi candidates with score >= {min_score}",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 4: Analyze Breakeven
# =============================================================================

@mortgage_tool(
    name="analyze_breakeven",
    description="Calculate breakeven period — months to recoup closing costs from refinancing",
    agent_roles=["refinance_advisor", "customer_intelligence"],
    risk_level="low",
    examples=[
        "How long to break even on a refi?",
        "Calculate the breakeven period",
    ],
)
def analyze_breakeven(
    mum_client_id: int,
    new_rate: Optional[float] = None,
    closing_costs: Optional[float] = None,
) -> ToolResult:
    """Analyze breakeven for refinance."""
    try:
        client = execute_single("""
            SELECT id, client_name, interest_rate, original_rate,
                   original_loan_amount, term, first_payment_date,
                   original_close_date
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        if new_rate is None:
            new_rate = _get_market_rate()

        current_rate = float(client["interest_rate"] or client["original_rate"] or 0)
        original_amount = float(client["original_loan_amount"] or 0)
        term = client["term"] or 360

        first_pmt = client["first_payment_date"] or client["original_close_date"]
        if first_pmt:
            if isinstance(first_pmt, str):
                first_pmt = datetime.fromisoformat(first_pmt)
            months_passed = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
        else:
            months_passed = 0

        remaining_balance = calculate_remaining_balance(
            original_amount, current_rate / 100, term, months_passed
        )

        if closing_costs is None:
            closing_costs = remaining_balance * DEFAULT_CLOSING_COST_PCT

        current_payment = calculate_monthly_payment(original_amount, current_rate / 100, term)
        new_payment = calculate_monthly_payment(remaining_balance, new_rate / 100, 360)
        monthly_savings = current_payment - new_payment

        if monthly_savings <= 0:
            return ToolResult.success(
                data={
                    "mum_client_id": mum_client_id,
                    "client_name": client["client_name"],
                    "breakeven_months": None,
                    "monthly_savings": round(monthly_savings, 2),
                    "viable": False,
                    "reason": "New payment would be equal or higher",
                },
                message=f"Refinance not viable: no monthly savings at {new_rate}%",
            )

        breakeven_months = closing_costs / monthly_savings
        breakeven_years = breakeven_months / 12

        # Assess viability
        remaining_months = term - months_passed
        viable = breakeven_months < remaining_months and breakeven_months < 60

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "closing_costs": round(closing_costs, 2),
            "closing_costs_formatted": format_currency(closing_costs),
            "monthly_savings": round(monthly_savings, 2),
            "monthly_savings_formatted": format_currency(monthly_savings),
            "breakeven_months": round(breakeven_months, 1),
            "breakeven_years": round(breakeven_years, 1),
            "remaining_loan_months": max(0, remaining_months),
            "savings_after_breakeven": round(monthly_savings * (remaining_months - breakeven_months), 2) if viable else 0,
            "viable": viable,
            "assessment": (
                "Excellent" if breakeven_months <= 12
                else "Good" if breakeven_months <= 24
                else "Acceptable" if breakeven_months <= 36
                else "Marginal" if breakeven_months <= 48
                else "Not recommended"
            ),
        }

        return ToolResult.success(
            data=data,
            message=f"Breakeven: {breakeven_months:.1f} months ({breakeven_years:.1f} yrs) — {data['assessment']}",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 5: Compare Refi Scenarios
# =============================================================================

@mortgage_tool(
    name="compare_refi_scenarios",
    description="Compare rate/term, cash-out, and streamline refinance scenarios side by side",
    agent_roles=["refinance_advisor", "customer_intelligence"],
    risk_level="low",
    examples=[
        "Compare refinance options",
        "Show me different refi scenarios",
    ],
)
def compare_refi_scenarios(
    mum_client_id: int,
    market_rate: Optional[float] = None,
) -> ToolResult:
    """Compare 3 refi scenarios side by side."""
    try:
        client = execute_single("""
            SELECT id, client_name, interest_rate, original_rate,
                   original_loan_amount, appraisal_value_at_closing,
                   term, first_payment_date, original_close_date,
                   property_state
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        if market_rate is None:
            market_rate = _get_market_rate()

        current_rate = float(client["interest_rate"] or client["original_rate"] or 0)
        original_amount = float(client["original_loan_amount"] or 0)
        original_value = float(client["appraisal_value_at_closing"] or 0)
        term = client["term"] or 360
        state = client["property_state"]

        first_pmt = client["first_payment_date"] or client["original_close_date"]
        if first_pmt:
            if isinstance(first_pmt, str):
                first_pmt = datetime.fromisoformat(first_pmt)
            months_passed = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
        else:
            months_passed = 0

        remaining_balance = calculate_remaining_balance(
            original_amount, current_rate / 100, term, months_passed
        )
        appreciation_rate = get_appreciation_rate(state)
        current_value = estimate_current_property_value(original_value, months_passed, appreciation_rate)
        current_payment = calculate_monthly_payment(original_amount, current_rate / 100, term)

        scenarios = []

        # Scenario 1: Rate & Term (30yr at market rate)
        rt_payment = calculate_monthly_payment(remaining_balance, market_rate / 100, 360)
        rt_closing = remaining_balance * DEFAULT_CLOSING_COST_PCT
        rt_savings = current_payment - rt_payment
        scenarios.append({
            "name": "Rate & Term (30yr)",
            "new_rate": market_rate,
            "new_term": 360,
            "new_loan_amount": round(remaining_balance, 2),
            "new_payment": round(rt_payment, 2),
            "monthly_savings": round(rt_savings, 2),
            "closing_costs": round(rt_closing, 2),
            "breakeven_months": round(rt_closing / rt_savings, 1) if rt_savings > 0 else None,
            "lifetime_savings": round(rt_savings * 360, 2) if rt_savings > 0 else 0,
            "cash_out": 0,
        })

        # Scenario 2: Cash-Out (80% LTV)
        max_cash_out_loan = current_value * 0.80
        cash_out_amount = max(0, max_cash_out_loan - remaining_balance)
        co_rate = market_rate + 0.25  # Cash-out usually higher
        co_payment = calculate_monthly_payment(max_cash_out_loan, co_rate / 100, 360)
        co_closing = max_cash_out_loan * 0.025
        co_savings = current_payment - co_payment
        scenarios.append({
            "name": "Cash-Out (80% LTV)",
            "new_rate": co_rate,
            "new_term": 360,
            "new_loan_amount": round(max_cash_out_loan, 2),
            "new_payment": round(co_payment, 2),
            "monthly_savings": round(co_savings, 2),
            "closing_costs": round(co_closing, 2),
            "breakeven_months": round(co_closing / co_savings, 1) if co_savings > 0 else None,
            "lifetime_savings": round(co_savings * 360, 2) if co_savings > 0 else 0,
            "cash_out": round(cash_out_amount, 2),
            "cash_out_formatted": format_currency(cash_out_amount),
        })

        # Scenario 3: 15-year term
        s15_rate = max(market_rate - 0.5, 3.0)  # 15yr typically lower
        s15_payment = calculate_monthly_payment(remaining_balance, s15_rate / 100, 180)
        s15_closing = remaining_balance * DEFAULT_CLOSING_COST_PCT
        s15_total_interest = (s15_payment * 180) - remaining_balance
        current_remaining_interest = (current_payment * (term - months_passed)) - remaining_balance
        s15_interest_savings = max(0, current_remaining_interest - s15_total_interest)
        scenarios.append({
            "name": "15-Year Term",
            "new_rate": s15_rate,
            "new_term": 180,
            "new_loan_amount": round(remaining_balance, 2),
            "new_payment": round(s15_payment, 2),
            "monthly_savings": round(current_payment - s15_payment, 2),  # Often negative (higher pmt)
            "closing_costs": round(s15_closing, 2),
            "breakeven_months": None,  # Different measure for shorter term
            "total_interest_savings": round(s15_interest_savings, 2),
            "total_interest_savings_formatted": format_currency(s15_interest_savings),
            "cash_out": 0,
        })

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "current_situation": {
                "rate": current_rate,
                "payment": round(current_payment, 2),
                "payment_formatted": format_currency(current_payment),
                "remaining_balance": round(remaining_balance, 2),
                "current_value": round(current_value, 2),
                "months_remaining": max(0, term - months_passed),
            },
            "scenarios": scenarios,
            "best_monthly_savings": max(s["monthly_savings"] for s in scenarios),
        }

        return ToolResult.success(
            data=data,
            message=f"{client['client_name']}: 3 scenarios compared (best monthly savings: {format_currency(data['best_monthly_savings'])})",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 6: Get Refi Portfolio Summary
# =============================================================================

@mortgage_tool(
    name="get_refi_portfolio_summary",
    description="Get portfolio-wide refinance metrics including counts by score bucket and total potential savings",
    agent_roles=["refinance_advisor", "pipeline_analyst"],
    risk_level="low",
    examples=[
        "Show me the refi portfolio summary",
        "How many clients are refi candidates?",
    ],
)
def get_refi_portfolio_summary(
    user_id: Optional[int] = None,
) -> ToolResult:
    """Get portfolio-wide refi summary."""
    try:
        params = {}
        user_filter = ""
        if user_id:
            user_filter = "AND mc.user_id = :uid"
            params["uid"] = user_id

        summary = execute_single(f"""
            SELECT
                COUNT(*) as total_clients,
                COUNT(CASE WHEN refi_score >= 70 THEN 1 END) as high_score,
                COUNT(CASE WHEN refi_score >= 50 AND refi_score < 70 THEN 1 END) as medium_score,
                COUNT(CASE WHEN refi_score >= 30 AND refi_score < 50 THEN 1 END) as low_score,
                COUNT(CASE WHEN refi_score < 30 OR refi_score IS NULL THEN 1 END) as no_opportunity,
                COALESCE(SUM(CASE WHEN refi_score >= 50 THEN estimated_savings ELSE 0 END), 0) as total_potential_savings,
                AVG(CASE WHEN refi_score > 0 THEN refi_score END) as avg_score,
                AVG(interest_rate) as avg_current_rate,
                COALESCE(SUM(current_loan_amount), 0) as total_portfolio_balance
            FROM mum_clients mc
            WHERE mc.status = 'Active'
            {user_filter}
        """, params)

        if not summary or summary["total_clients"] == 0:
            return ToolResult.no_data("No active MUM clients found")

        data = {
            "total_clients": summary["total_clients"],
            "score_buckets": {
                "high_70_100": summary["high_score"] or 0,
                "medium_50_69": summary["medium_score"] or 0,
                "low_30_49": summary["low_score"] or 0,
                "none_0_29": summary["no_opportunity"] or 0,
            },
            "total_potential_savings": float(summary["total_potential_savings"] or 0),
            "total_potential_savings_formatted": format_currency(summary["total_potential_savings"]),
            "avg_refi_score": round(float(summary["avg_score"] or 0), 1),
            "avg_current_rate": round(float(summary["avg_current_rate"] or 0), 3),
            "total_portfolio_balance": float(summary["total_portfolio_balance"] or 0),
            "total_portfolio_formatted": format_currency(summary["total_portfolio_balance"]),
            "actionable_pct": round(
                ((summary["high_score"] or 0) + (summary["medium_score"] or 0))
                / summary["total_clients"] * 100, 1
            ) if summary["total_clients"] > 0 else 0,
        }

        return ToolResult.success(
            data=data,
            message=f"{data['score_buckets']['high_70_100']} high + {data['score_buckets']['medium_50_69']} medium refi candidates ({data['actionable_pct']}% actionable)",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 7: Recommend Refi Action
# =============================================================================

@mortgage_tool(
    name="recommend_refi_action",
    description="Provide AI recommendation for a MUM client: refi_now, wait_for_rates, wait_for_equity, or not_viable",
    agent_roles=["refinance_advisor", "customer_intelligence", "lead_nurturer"],
    risk_level="low",
    examples=[
        "Should this client refinance?",
        "What's the recommendation for this refi?",
    ],
)
def recommend_refi_action(
    mum_client_id: int,
    market_rate: Optional[float] = None,
) -> ToolResult:
    """Generate refi recommendation."""
    try:
        client = execute_single("""
            SELECT id, client_name, interest_rate, original_rate,
                   original_loan_amount, appraisal_value_at_closing,
                   term, first_payment_date, original_close_date,
                   property_state, refi_score
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        if market_rate is None:
            market_rate = _get_market_rate()

        current_rate = float(client["interest_rate"] or client["original_rate"] or 0)
        original_amount = float(client["original_loan_amount"] or 0)
        original_value = float(client["appraisal_value_at_closing"] or 0)
        term = client["term"] or 360
        state = client["property_state"]

        first_pmt = client["first_payment_date"] or client["original_close_date"]
        if first_pmt:
            if isinstance(first_pmt, str):
                first_pmt = datetime.fromisoformat(first_pmt)
            months_passed = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
        else:
            months_passed = 0

        remaining_balance = calculate_remaining_balance(
            original_amount, current_rate / 100, term, months_passed
        )
        appreciation_rate = get_appreciation_rate(state)
        current_value = estimate_current_property_value(original_value, months_passed, appreciation_rate)
        current_ltv = (remaining_balance / current_value * 100) if current_value > 0 else 100
        equity_pct = 100 - current_ltv
        rate_diff = current_rate - market_rate

        # Calculate savings
        closing_costs = remaining_balance * DEFAULT_CLOSING_COST_PCT
        savings = calculate_rate_savings(current_rate, market_rate, remaining_balance, 360)
        monthly_savings = savings["monthly_savings"]
        breakeven = (closing_costs / monthly_savings) if monthly_savings > 0 else float('inf')

        # Decision logic
        if rate_diff >= 0.75 and equity_pct >= 20 and breakeven <= 36:
            action = "refi_now"
            reasoning = f"Rate {rate_diff:.2f}% higher than market, {equity_pct:.0f}% equity, {breakeven:.0f}-month breakeven"
            urgency = "high"
            talking_points = [
                f"You're paying {current_rate}% — current market is {market_rate}%",
                f"You'd save {format_currency(monthly_savings)} per month",
                f"With {equity_pct:.0f}% equity, you have strong positioning",
                f"Break even on closing costs in just {breakeven:.0f} months",
            ]
        elif rate_diff >= 0.5 and equity_pct >= 10:
            action = "refi_now" if breakeven <= 24 else "wait_for_rates"
            reasoning = f"Moderate opportunity: {rate_diff:.2f}% rate gap, {equity_pct:.0f}% equity"
            urgency = "medium"
            talking_points = [
                f"Rate differential of {rate_diff:.2f}% offers savings",
                f"Monthly savings of {format_currency(monthly_savings)}",
                f"Consider if you plan to stay 3+ years",
            ]
        elif rate_diff > 0 and equity_pct < 20:
            action = "wait_for_equity"
            reasoning = f"Need more equity ({equity_pct:.0f}% now, target 20%+) for best terms"
            urgency = "low"
            months_to_20 = 0
            # Estimate months until 20% equity
            for m in range(1, 120):
                fut_balance = calculate_remaining_balance(original_amount, current_rate / 100, term, months_passed + m)
                fut_value = estimate_current_property_value(original_value, months_passed + m, appreciation_rate)
                if fut_value > 0 and ((fut_value - fut_balance) / fut_value * 100) >= 20:
                    months_to_20 = m
                    break
            talking_points = [
                f"Current equity is {equity_pct:.0f}% — aim for 20%+ to avoid PMI",
                f"Estimated ~{months_to_20} months to reach 20% equity" if months_to_20 > 0 else "Building equity over time",
                "We'll monitor and reach out when timing is right",
            ]
        elif rate_diff <= 0:
            action = "not_viable"
            reasoning = f"Current rate ({current_rate}%) is at or below market ({market_rate}%)"
            urgency = "none"
            talking_points = [
                f"Your rate of {current_rate}% is excellent for the current market",
                "No refinance benefit at current rates",
                "We'll alert you if rates drop significantly",
            ]
        else:
            action = "wait_for_rates"
            reasoning = f"Small rate gap ({rate_diff:.2f}%), long breakeven ({breakeven:.0f}+ months)"
            urgency = "low"
            talking_points = [
                f"Rate gap of {rate_diff:.2f}% is too small for clear benefit",
                "Monitoring for better rate environment",
            ]

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "action": action,
            "urgency": urgency,
            "reasoning": reasoning,
            "talking_points": talking_points,
            "metrics": {
                "current_rate": current_rate,
                "market_rate": market_rate,
                "rate_differential": round(rate_diff, 3),
                "equity_pct": round(equity_pct, 1),
                "monthly_savings": round(monthly_savings, 2),
                "breakeven_months": round(breakeven, 1) if breakeven != float('inf') else None,
            },
        }

        return ToolResult.success(
            data=data,
            message=f"{client['client_name']}: {action.upper()} ({urgency} urgency) — {reasoning}",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 8: Batch Update Refi Scores
# =============================================================================

@mortgage_tool(
    name="batch_update_refi_scores",
    description="Batch recalculate refinance scores for all active MUM clients",
    agent_roles=["refinance_advisor"],
    risk_level="medium",
    examples=[
        "Update all refi scores",
        "Recalculate refinance opportunities",
    ],
)
def batch_update_refi_scores(
    market_rate: Optional[float] = None,
    limit: int = 500,
    dry_run: bool = False,
) -> ToolResult:
    """Batch update refi scores for all MUM clients."""
    try:
        if market_rate is None:
            market_rate = _get_market_rate()

        clients = execute_query("""
            SELECT id, client_name, interest_rate, original_rate,
                   original_loan_amount, appraisal_value_at_closing,
                   term, first_payment_date, original_close_date,
                   property_state
            FROM mum_clients
            WHERE status = 'Active'
            ORDER BY id
            LIMIT :lim
        """, {"lim": limit})

        if not clients:
            return ToolResult.no_data("No active MUM clients found")

        updated = 0
        errors = 0
        score_distribution = {"high": 0, "medium": 0, "low": 0, "none": 0}

        with get_db() as db:
            for client in clients:
                try:
                    current_rate = float(client["interest_rate"] or client["original_rate"] or 0)
                    original_amount = float(client["original_loan_amount"] or 0)
                    original_value = float(client["appraisal_value_at_closing"] or 0)
                    term = client["term"] or 360
                    state = client["property_state"]

                    if current_rate <= 0 or original_amount <= 0:
                        errors += 1
                        continue

                    first_pmt = client["first_payment_date"] or client["original_close_date"]
                    if first_pmt:
                        if isinstance(first_pmt, str):
                            first_pmt = datetime.fromisoformat(first_pmt)
                        months_passed = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
                    else:
                        months_passed = 0

                    remaining_balance = calculate_remaining_balance(
                        original_amount, current_rate / 100, term, months_passed
                    )
                    appreciation_rate = get_appreciation_rate(state)
                    current_value = estimate_current_property_value(original_value, months_passed, appreciation_rate)
                    current_ltv = (remaining_balance / current_value * 100) if current_value > 0 else 100
                    equity_pct = 100 - current_ltv

                    # Calculate score components
                    rate_diff = current_rate - market_rate
                    score = 0

                    # Rate differential (0-35)
                    if rate_diff >= 2.0: score += 35
                    elif rate_diff >= 1.5: score += 30
                    elif rate_diff >= 1.0: score += 25
                    elif rate_diff >= 0.75: score += 20
                    elif rate_diff >= 0.5: score += 15
                    elif rate_diff >= 0.25: score += 8
                    elif rate_diff > 0: score += 3

                    # Equity (0-20)
                    if equity_pct >= 40: score += 20
                    elif equity_pct >= 30: score += 17
                    elif equity_pct >= 20: score += 14
                    elif equity_pct >= 10: score += 8
                    elif equity_pct >= 5: score += 4

                    # Loan size (0-15)
                    if remaining_balance >= 500000: score += 15
                    elif remaining_balance >= 400000: score += 13
                    elif remaining_balance >= 300000: score += 10
                    elif remaining_balance >= 200000: score += 7
                    elif remaining_balance >= 100000: score += 4
                    else: score += 1

                    # Time in loan (0-10)
                    if months_passed >= 36: score += 10
                    elif months_passed >= 24: score += 8
                    elif months_passed >= 18: score += 6
                    elif months_passed >= 12: score += 4
                    elif months_passed >= 6: score += 2

                    # Rate trend (0-10)
                    score += 5 if rate_diff > 0 else 0

                    # Breakeven (0-10)
                    closing_costs = remaining_balance * DEFAULT_CLOSING_COST_PCT
                    savings = calculate_rate_savings(current_rate, market_rate, remaining_balance, 360)
                    ms = savings["monthly_savings"]
                    if ms > 0:
                        be = closing_costs / ms
                        if be <= 12: score += 10
                        elif be <= 24: score += 7
                        elif be <= 36: score += 4
                        elif be <= 48: score += 2

                    score = min(100, max(0, score))

                    # Determine refi opportunity flag and estimated savings
                    refi_opportunity = score >= 50
                    estimated_savings = round(savings["annual_savings"], 2) if refi_opportunity else 0

                    # Distribution tracking
                    if score >= 70: score_distribution["high"] += 1
                    elif score >= 50: score_distribution["medium"] += 1
                    elif score >= 30: score_distribution["low"] += 1
                    else: score_distribution["none"] += 1

                    if not dry_run:
                        from sqlalchemy import text
                        db.execute(text("""
                            UPDATE mum_clients SET
                                refi_score = :score,
                                refinance_opportunity = :refi_opp,
                                estimated_savings = :est_savings
                            WHERE id = :cid
                        """), {
                            "score": score,
                            "refi_opp": refi_opportunity,
                            "est_savings": estimated_savings,
                            "cid": client["id"],
                        })

                    updated += 1
                except Exception as e:
                    logger.error(f"Error scoring refi for client {client.get('id', 'unknown')}: {e}")
                    errors += 1

            if not dry_run:
                db.commit()

        data = {
            "total_processed": len(clients),
            "updated": updated,
            "errors": errors,
            "dry_run": dry_run,
            "market_rate_used": market_rate,
            "score_distribution": score_distribution,
        }

        return ToolResult.success(
            data=data,
            message=f"{'DRY RUN: ' if dry_run else ''}Scored {updated}/{len(clients)} clients: {score_distribution['high']} high, {score_distribution['medium']} medium ({errors} errors)",
        )
    except Exception as e:
        return ToolResult.error(str(e))
