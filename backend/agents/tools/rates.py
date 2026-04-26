"""
Perennia AI - Rate Advisory Tools
Tools for the Rate Advisor agent to manage rate locks and market analysis.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
    LoanType,
)


@mortgage_tool(
    name="get_current_rates",
    description="Get current interest rates by product type and term",
    agent_roles=["rate_advisor", "pipeline_analyst"],
    risk_level="LOW",
    examples=[
        "get_current_rates()",
        "get_current_rates(loan_type='conventional', term=30)",
    ],
)
def get_current_rates(
    loan_type: Optional[str] = None,
    term: Optional[int] = None,
    include_history: bool = False,
) -> ToolResult:
    """
    Get current interest rates from rate sheets.

    Args:
        loan_type: Filter by loan type (conventional, fha, va, jumbo)
        term: Filter by term (15, 20, 30 years)
        include_history: Include rate change history
    """
    params = {}
    filters = ["r.effective_date = (SELECT MAX(effective_date) FROM rate_sheets)"]

    if loan_type:
        filters.append("r.loan_type = :loan_type")
        params["loan_type"] = loan_type
    if term:
        filters.append("r.term_years = :term")
        params["term"] = term

    rates = execute_query(f"""
        SELECT
            r.loan_type,
            r.term_years,
            r.base_rate,
            r.apr,
            r.points,
            r.effective_date,
            r.expires_at,
            r.last_updated
        FROM rate_sheets r
        WHERE {' AND '.join(filters)}
        ORDER BY r.loan_type, r.term_years
    """, params)

    if not rates:
        return ToolResult.no_data("No current rates available")

    rate_data = []
    for r in rates:
        rate_data.append({
            "loan_type": r["loan_type"],
            "term_years": r["term_years"],
            "rate": float(r["base_rate"]),
            "rate_formatted": f"{float(r['base_rate']):.3f}%",
            "apr": float(r["apr"]),
            "apr_formatted": f"{float(r['apr']):.3f}%",
            "points": float(r["points"]),
            "effective_date": format_date(r["effective_date"]),
            "expires": format_date(r["expires_at"]) if r.get("expires_at") else None,
        })

    history_data = None
    if include_history:
        history = execute_query("""
            SELECT
                loan_type, term_years, base_rate, effective_date
            FROM rate_sheets
            WHERE effective_date >= CURRENT_DATE - 30
            ORDER BY loan_type, term_years, effective_date DESC
            LIMIT 50
        """, {})

        history_data = {}
        for h in history:
            key = f"{h['loan_type']}_{h['term_years']}"
            if key not in history_data:
                history_data[key] = []
            history_data[key].append({
                "rate": float(h["base_rate"]),
                "date": format_date(h["effective_date"]),
            })

    # Calculate changes
    if len(rate_data) > 0:
        # Get yesterday's rates for comparison
        yesterday = execute_query("""
            SELECT loan_type, term_years, base_rate
            FROM rate_sheets
            WHERE effective_date = (
                SELECT MAX(effective_date) FROM rate_sheets
                WHERE effective_date < CURRENT_DATE
            )
        """, {})

        yesterday_map = {f"{y['loan_type']}_{y['term_years']}": float(y["base_rate"]) for y in yesterday}

        for r in rate_data:
            key = f"{r['loan_type']}_{r['term_years']}"
            if key in yesterday_map:
                change = r["rate"] - yesterday_map[key]
                r["change_from_yesterday"] = round(change, 3)
                r["direction"] = "up" if change > 0 else "down" if change < 0 else "unchanged"

    data = {
        "as_of": datetime.now().isoformat(),
        "rates": rate_data,
        "history": history_data,
        "market_summary": _get_market_summary(rate_data),
    }

    return ToolResult.success(
        data=data,
        message=f"Current rates: {len(rate_data)} products, 30yr conventional at {rate_data[0]['rate']:.3f}%" if rate_data else "Rates retrieved",
    )


def _get_market_summary(rates: List[Dict]) -> Dict:
    """Generate market summary from rate data."""
    conv_30 = next((r for r in rates if r["loan_type"] == "conventional" and r["term_years"] == 30), None)
    conv_15 = next((r for r in rates if r["loan_type"] == "conventional" and r["term_years"] == 15), None)

    return {
        "benchmark_rate": conv_30["rate"] if conv_30 else None,
        "spread_15_30": round(conv_30["rate"] - conv_15["rate"], 3) if conv_30 and conv_15 else None,
        "market_direction": conv_30.get("direction", "unknown") if conv_30 else "unknown",
    }


@mortgage_tool(
    name="analyze_rate_trends",
    description="Analyze rate trends over time",
    agent_roles=["rate_advisor"],
    risk_level="LOW",
)
def analyze_rate_trends(
    loan_type: str = "conventional",
    term: int = 30,
    days_back: int = 30,
) -> ToolResult:
    """
    Analyze rate trends for a specific product.
    """
    rates = execute_query("""
        SELECT
            effective_date,
            base_rate,
            apr
        FROM rate_sheets
        WHERE loan_type = :loan_type
            AND term_years = :term
            AND effective_date >= CURRENT_DATE - :days_back
        ORDER BY effective_date ASC
    """, {"loan_type": loan_type, "term": term, "days_back": days_back})

    if not rates:
        return ToolResult.no_data(f"No rate history for {loan_type} {term}yr")

    # Calculate statistics
    rate_values = [float(r["base_rate"]) for r in rates]

    current = rate_values[-1]
    period_high = max(rate_values)
    period_low = min(rate_values)
    period_avg = sum(rate_values) / len(rate_values)

    # Volatility (standard deviation)
    variance = sum((r - period_avg) ** 2 for r in rate_values) / len(rate_values)
    volatility = variance ** 0.5

    # Trend calculation (simple linear)
    if len(rate_values) >= 5:
        first_half_avg = sum(rate_values[:len(rate_values)//2]) / (len(rate_values)//2)
        second_half_avg = sum(rate_values[len(rate_values)//2:]) / (len(rate_values) - len(rate_values)//2)
        trend = "rising" if second_half_avg > first_half_avg else "falling" if second_half_avg < first_half_avg else "stable"
    else:
        trend = "insufficient_data"

    # Recent momentum (last 5 days)
    recent = rate_values[-5:] if len(rate_values) >= 5 else rate_values
    momentum = "rising" if recent[-1] > recent[0] else "falling" if recent[-1] < recent[0] else "flat"

    data = {
        "product": f"{loan_type} {term}yr",
        "period_days": days_back,
        "data_points": len(rates),
        "current_rate": current,
        "statistics": {
            "high": period_high,
            "low": period_low,
            "average": round(period_avg, 3),
            "volatility": round(volatility, 4),
            "range": round(period_high - period_low, 3),
        },
        "analysis": {
            "trend": trend,
            "momentum": momentum,
            "current_vs_avg": round(current - period_avg, 3),
            "current_vs_high": round(current - period_high, 3),
            "current_vs_low": round(current - period_low, 3),
            "percentile": round((current - period_low) / (period_high - period_low) * 100, 1) if period_high != period_low else 50,
        },
        "history": [
            {
                "date": format_date(r["effective_date"]),
                "rate": float(r["base_rate"]),
            }
            for r in rates[-10:]  # Last 10 data points
        ],
        "recommendation": _get_trend_recommendation(trend, momentum, current, period_avg),
    }

    return ToolResult.success(
        data=data,
        message=f"Rate trend: {trend}, current {current:.3f}% ({momentum} momentum), range {period_low:.3f}-{period_high:.3f}%",
    )


def _get_trend_recommendation(trend: str, momentum: str, current: float, avg: float) -> str:
    """Generate recommendation based on trend analysis."""
    if momentum == "rising" and current > avg:
        return "Consider locking - rates trending up and above average"
    elif momentum == "falling" and current < avg:
        return "Monitor closely - rates may have room to fall further"
    elif momentum == "rising":
        return "Lock recommended - upward momentum detected"
    elif momentum == "falling":
        return "Float with caution - downward momentum but watch for reversal"
    else:
        return "Market stable - decision depends on loan timeline"


@mortgage_tool(
    name="calculate_lock_cost",
    description="Calculate rate lock cost and break-even analysis",
    agent_roles=["rate_advisor"],
    risk_level="LOW",
)
def calculate_lock_cost(
    loan_amount: float,
    rate: float,
    lock_days: int = 30,
    extension_days: int = 0,
) -> ToolResult:
    """
    Calculate rate lock costs and break-even points.

    Args:
        loan_amount: Loan amount in dollars
        rate: Interest rate to lock
        lock_days: Lock period (15, 30, 45, 60 days)
        extension_days: Days of extension needed
    """
    # Lock pricing (typical market pricing in basis points)
    lock_pricing = {
        15: -0.125,   # Better pricing for shorter locks
        30: 0,        # Par pricing
        45: 0.125,    # Slight cost
        60: 0.25,     # Higher cost
        90: 0.50,     # Extended lock premium
    }

    extension_cost_per_day = 0.0125  # ~12.5 bps per week

    # Find closest lock period
    available_periods = sorted(lock_pricing.keys())
    lock_period = min(available_periods, key=lambda x: abs(x - lock_days))

    base_cost_bps = lock_pricing.get(lock_period, 0.25)
    extension_cost_bps = extension_days * extension_cost_per_day
    total_cost_bps = base_cost_bps + extension_cost_bps

    cost_dollars = loan_amount * (total_cost_bps / 100)

    # Monthly payment impact
    monthly_rate = rate / 100 / 12
    term_months = 360  # 30 year
    monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**term_months) / ((1 + monthly_rate)**term_months - 1)

    # Break-even analysis
    # How much would rates need to rise for lock to be worth it?
    break_even_increase_bps = total_cost_bps

    # Payment impact of rate increase
    rate_increase = 0.125  # 1/8 point
    new_monthly_rate = (rate + rate_increase) / 100 / 12
    new_payment = loan_amount * (new_monthly_rate * (1 + new_monthly_rate)**term_months) / ((1 + new_monthly_rate)**term_months - 1)
    payment_increase = new_payment - monthly_payment

    data = {
        "loan_amount": loan_amount,
        "loan_amount_formatted": format_currency(loan_amount),
        "rate": rate,
        "lock_period": {
            "requested_days": lock_days,
            "actual_days": lock_period,
            "extension_days": extension_days,
            "total_days": lock_period + extension_days,
        },
        "costs": {
            "base_cost_bps": base_cost_bps,
            "extension_cost_bps": round(extension_cost_bps, 3),
            "total_cost_bps": round(total_cost_bps, 3),
            "cost_dollars": round(cost_dollars, 2),
            "cost_formatted": format_currency(cost_dollars),
        },
        "payment_analysis": {
            "monthly_payment": round(monthly_payment, 2),
            "payment_formatted": format_currency(monthly_payment),
            "rate_increase_impact": f"+${round(payment_increase, 2)}/month per 1/8% increase",
        },
        "break_even": {
            "rate_increase_needed_bps": round(break_even_increase_bps, 3),
            "rate_increase_needed_pct": f"{round(break_even_increase_bps / 100, 4)}%",
            "monthly_savings_threshold": format_currency(cost_dollars / 12),
        },
        "recommendation": _get_lock_recommendation(lock_days, total_cost_bps),
    }

    return ToolResult.success(
        data=data,
        message=f"Lock cost: {round(total_cost_bps, 3)} bps ({format_currency(cost_dollars)}) for {lock_period + extension_days} days",
    )


def _get_lock_recommendation(lock_days: int, cost_bps: float) -> str:
    """Generate lock recommendation."""
    if lock_days <= 21:
        return "Short timeline - locking strongly recommended to eliminate rate risk"
    elif lock_days <= 45 and cost_bps <= 0.25:
        return "Standard timeline with acceptable cost - lock recommended"
    elif lock_days > 60:
        return "Extended timeline - consider float-down option or delay lock if market favorable"
    else:
        return "Evaluate current market conditions before deciding"


@mortgage_tool(
    name="recommend_lock_strategy",
    description="Get lock/float recommendation for a specific loan",
    agent_roles=["rate_advisor"],
    risk_level="LOW",
)
def recommend_lock_strategy(
    loan_id: str,
    risk_tolerance: str = "moderate",
) -> ToolResult:
    """
    Get lock strategy recommendation for a loan.

    Args:
        loan_id: The loan ID
        risk_tolerance: conservative, moderate, aggressive
    """
    loan = execute_single("""
        SELECT
            l.*,
            r.base_rate as current_rate,
            r.effective_date as rate_date
        FROM loans l
        LEFT JOIN rate_sheets r ON r.loan_type = l.loan_type
            AND r.term_years = 30
            AND r.effective_date = (SELECT MAX(effective_date) FROM rate_sheets)
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Calculate days to close
    expected_close = loan.get("expected_close_date")
    if expected_close:
        days_to_close = days_between(date.today(), expected_close)
    else:
        days_to_close = 30  # Default assumption

    # Get market trend
    trend_result = analyze_rate_trends(
        loan_type=loan.get("loan_type", "conventional"),
        term=30,
        days_back=14,
    )

    market_trend = "unknown"
    market_momentum = "unknown"
    if trend_result.status.value == "success":
        market_trend = trend_result.data.get("analysis", {}).get("trend", "unknown")
        market_momentum = trend_result.data.get("analysis", {}).get("momentum", "unknown")

    # Lock decision matrix
    lock_score = 0
    factors = []

    # Timeline factor
    if days_to_close <= 21:
        lock_score += 3
        factors.append({"factor": "Short timeline", "impact": "+3", "note": f"{days_to_close} days to close"})
    elif days_to_close <= 45:
        lock_score += 1
        factors.append({"factor": "Standard timeline", "impact": "+1", "note": f"{days_to_close} days to close"})
    else:
        lock_score -= 1
        factors.append({"factor": "Extended timeline", "impact": "-1", "note": f"{days_to_close} days to close"})

    # Market trend factor
    if market_trend == "rising" or market_momentum == "rising":
        lock_score += 2
        factors.append({"factor": "Rising rates", "impact": "+2", "note": f"Trend: {market_trend}, Momentum: {market_momentum}"})
    elif market_trend == "falling" and market_momentum == "falling":
        lock_score -= 2
        factors.append({"factor": "Falling rates", "impact": "-2", "note": "May benefit from waiting"})

    # Risk tolerance factor
    if risk_tolerance == "conservative":
        lock_score += 2
        factors.append({"factor": "Conservative risk profile", "impact": "+2", "note": "Favors certainty"})
    elif risk_tolerance == "aggressive":
        lock_score -= 1
        factors.append({"factor": "Aggressive risk profile", "impact": "-1", "note": "Willing to take rate risk"})

    # Loan size factor (larger loans = more rate sensitivity)
    loan_amount = float(loan.get("loan_amount", 0))
    if loan_amount >= 750000:
        lock_score += 1
        factors.append({"factor": "Large loan size", "impact": "+1", "note": f"{format_currency(loan_amount)} - high rate sensitivity"})

    # Generate recommendation
    if lock_score >= 4:
        recommendation = "LOCK NOW"
        confidence = "high"
        rationale = "Strong factors favor locking immediately"
    elif lock_score >= 2:
        recommendation = "LOCK"
        confidence = "medium"
        rationale = "Majority of factors favor locking"
    elif lock_score >= 0:
        recommendation = "FLOAT WITH CAUTION"
        confidence = "medium"
        rationale = "Balanced factors - monitor daily"
    else:
        recommendation = "FLOAT"
        confidence = "low"
        rationale = "Factors suggest potential benefit from waiting"

    # Calculate payment impact
    current_rate = float(loan.get("current_rate", 0) or loan.get("rate", 7.0))
    monthly_payment = _calculate_monthly_payment(loan_amount, current_rate)
    payment_per_eighth = _calculate_monthly_payment(loan_amount, current_rate + 0.125) - monthly_payment

    data = {
        "loan_id": loan_id,
        "loan_details": {
            "amount": format_currency(loan_amount),
            "type": loan.get("loan_type"),
            "expected_close": format_date(expected_close) if expected_close else None,
            "days_to_close": days_to_close,
        },
        "market_conditions": {
            "current_rate": current_rate,
            "trend": market_trend,
            "momentum": market_momentum,
        },
        "recommendation": {
            "action": recommendation,
            "confidence": confidence,
            "rationale": rationale,
            "lock_score": lock_score,
        },
        "decision_factors": factors,
        "payment_impact": {
            "current_payment": format_currency(monthly_payment),
            "cost_per_eighth": f"+{format_currency(payment_per_eighth)}/month per 1/8% rate increase",
            "annual_impact_per_eighth": format_currency(payment_per_eighth * 12),
        },
        "next_steps": _get_lock_next_steps(recommendation, days_to_close),
    }

    return ToolResult.success(
        data=data,
        message=f"Lock strategy: {recommendation} ({confidence} confidence) - {rationale}",
    )


def _calculate_monthly_payment(loan_amount: float, rate: float) -> float:
    """Calculate monthly P&I payment."""
    monthly_rate = rate / 100 / 12
    term_months = 360
    if monthly_rate == 0:
        return loan_amount / term_months
    return loan_amount * (monthly_rate * (1 + monthly_rate)**term_months) / ((1 + monthly_rate)**term_months - 1)


def _get_lock_next_steps(recommendation: str, days_to_close: int) -> List[str]:
    """Generate next steps based on recommendation."""
    steps = []

    if recommendation in ("LOCK NOW", "LOCK"):
        steps.append("Request rate lock from pricing desk")
        steps.append("Confirm lock period covers expected close date + buffer")
        steps.append("Document lock confirmation and expiration")
    else:
        steps.append("Set rate alerts for target levels")
        steps.append("Review market conditions daily")
        if days_to_close <= 30:
            steps.append("Must lock within 7 days regardless of market conditions")

    return steps


@mortgage_tool(
    name="monitor_float_position",
    description="Monitor unlocked (floating) loan positions",
    agent_roles=["rate_advisor", "pipeline_analyst"],
    risk_level="LOW",
)
def monitor_float_position(
    lo_id: Optional[str] = None,
    branch_id: Optional[str] = None,
) -> ToolResult:
    """
    Monitor all unlocked loans and their rate exposure.
    """
    params = {}
    # Note: Stage values must match LoanStage enum in main.py exactly
    filters = ["l.rate_lock_status = 'floating'", "l.stage NOT IN ('Funded')"]

    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id

    floating = execute_query(f"""
        SELECT
            l.id,
            l.loan_amount,
            l.loan_type,
            l.rate,
            l.expected_close_date,
            l.borrower_first_name || ' ' || l.borrower_last_name as borrower,
            COALESCE(loes.full_name, lo.email) as lo_name
        FROM loans l
        LEFT JOIN users lo ON lo.id = l.loan_officer_id
        LEFT JOIN email_signatures loes ON loes.user_id = lo.id
        WHERE {' AND '.join(filters)}
        ORDER BY l.expected_close_date ASC
    """, params)

    if not floating:
        return ToolResult.no_data("No floating loans in pipeline")

    # Get current rates for exposure calculation
    current_rates = execute_single("""
        SELECT base_rate FROM rate_sheets
        WHERE loan_type = 'conventional' AND term_years = 30
        ORDER BY effective_date DESC LIMIT 1
    """, {})

    current_rate = float(current_rates["base_rate"]) if current_rates else 7.0

    total_float_volume = 0
    urgent = []
    at_risk = []

    loan_data = []
    today = date.today()

    for loan in floating:
        loan_amount = float(loan["loan_amount"])
        total_float_volume += loan_amount

        days_to_close = days_between(today, loan["expected_close_date"]) if loan.get("expected_close_date") else None

        # Rate exposure (impact of 1/8 point move)
        rate_exposure = loan_amount * 0.00125  # 12.5 bps per eighth

        entry = {
            "loan_id": loan["id"],
            "borrower": loan["borrower"],
            "lo_name": loan["lo_name"],
            "amount": loan_amount,
            "amount_formatted": format_currency(loan_amount),
            "loan_type": loan["loan_type"],
            "quoted_rate": float(loan["rate"]) if loan.get("rate") else None,
            "current_market_rate": current_rate,
            "expected_close": format_date(loan["expected_close_date"]) if loan.get("expected_close_date") else None,
            "days_to_close": days_to_close,
            "rate_exposure_per_eighth": format_currency(rate_exposure),
        }

        # Categorize risk
        if days_to_close is not None:
            if days_to_close <= 7:
                entry["urgency"] = "critical"
                urgent.append(entry)
            elif days_to_close <= 21:
                entry["urgency"] = "high"
                at_risk.append(entry)
            elif days_to_close <= 45:
                entry["urgency"] = "moderate"
            else:
                entry["urgency"] = "low"
        else:
            entry["urgency"] = "unknown"

        loan_data.append(entry)

    # Portfolio exposure
    portfolio_exposure = total_float_volume * 0.00125

    data = {
        "summary": {
            "floating_loans": len(floating),
            "total_volume": total_float_volume,
            "volume_formatted": format_currency(total_float_volume),
            "portfolio_exposure_per_eighth": format_currency(portfolio_exposure),
            "urgent_count": len(urgent),
            "at_risk_count": len(at_risk),
        },
        "current_market_rate": current_rate,
        "urgent_locks_needed": urgent,
        "at_risk_loans": at_risk,
        "all_floating": loan_data,
        "recommendations": _get_float_recommendations(len(urgent), len(at_risk), portfolio_exposure),
    }

    return ToolResult.success(
        data=data,
        message=f"Float position: {len(floating)} loans, {format_currency(total_float_volume)} volume, {len(urgent)} urgent locks needed",
    )


def _get_float_recommendations(urgent: int, at_risk: int, exposure: float) -> List[str]:
    """Generate float monitoring recommendations."""
    recs = []

    if urgent > 0:
        recs.append(f"IMMEDIATE ACTION: {urgent} loans closing within 7 days must be locked today")
    if at_risk > 0:
        recs.append(f"Lock {at_risk} loans closing within 21 days before week's end")
    if exposure > 50000:
        recs.append(f"High portfolio exposure ({format_currency(exposure)}/eighth) - consider bulk lock")

    return recs if recs else ["Float position manageable - continue daily monitoring"]


@mortgage_tool(
    name="get_extension_pricing",
    description="Get rate lock extension pricing",
    agent_roles=["rate_advisor"],
    risk_level="LOW",
)
def get_extension_pricing(
    loan_id: str,
    extension_days: int,
) -> ToolResult:
    """
    Get cost of extending a rate lock.
    """
    loan = execute_single("""
        SELECT
            l.*,
            rl.lock_date,
            rl.expiration_date,
            rl.locked_rate,
            rl.lock_days as original_lock_days
        FROM loans l
        LEFT JOIN rate_locks rl ON rl.loan_id = l.id AND rl.status = 'active'
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    if not loan.get("lock_date"):
        return ToolResult.error(f"Loan {loan_id} does not have an active rate lock")

    # Extension pricing tiers
    extension_pricing = {
        (1, 7): 0.0625,      # 1-7 days: 6.25 bps
        (8, 15): 0.125,      # 8-15 days: 12.5 bps
        (16, 30): 0.25,      # 16-30 days: 25 bps
        (31, 60): 0.50,      # 31-60 days: 50 bps (if available)
    }

    cost_bps = 0
    for (min_days, max_days), rate in extension_pricing.items():
        if min_days <= extension_days <= max_days:
            cost_bps = rate
            break

    if cost_bps == 0:
        cost_bps = 0.50  # Default for longer extensions

    loan_amount = float(loan.get("loan_amount", 0))
    cost_dollars = loan_amount * (cost_bps / 100)

    # Calculate new expiration
    current_exp = loan["expiration_date"]
    new_exp = current_exp + timedelta(days=extension_days) if current_exp else None

    data = {
        "loan_id": loan_id,
        "current_lock": {
            "locked_rate": float(loan["locked_rate"]),
            "lock_date": format_date(loan["lock_date"]),
            "original_days": loan["original_lock_days"],
            "current_expiration": format_date(current_exp) if current_exp else None,
        },
        "extension": {
            "days_requested": extension_days,
            "cost_bps": cost_bps,
            "cost_dollars": round(cost_dollars, 2),
            "cost_formatted": format_currency(cost_dollars),
            "new_expiration": format_date(new_exp) if new_exp else None,
        },
        "alternatives": {
            "relock_option": "May be able to relock at current market if rates have improved",
            "float_down": "Check if float-down option available on original lock",
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Extension cost: {cost_bps} bps ({format_currency(cost_dollars)}) for {extension_days} days",
    )


@mortgage_tool(
    name="compare_rate_scenarios",
    description="Compare payment scenarios at different rates",
    agent_roles=["rate_advisor"],
    risk_level="LOW",
)
def compare_rate_scenarios(
    loan_amount: float,
    base_rate: float,
    term_years: int = 30,
    scenarios: Optional[List[float]] = None,
) -> ToolResult:
    """
    Compare payment scenarios at different rate levels.
    """
    if scenarios is None:
        # Default: compare -0.25, -0.125, base, +0.125, +0.25
        scenarios = [
            base_rate - 0.25,
            base_rate - 0.125,
            base_rate,
            base_rate + 0.125,
            base_rate + 0.25,
        ]

    base_payment = _calculate_monthly_payment(loan_amount, base_rate)
    term_months = term_years * 12

    scenario_data = []
    for rate in scenarios:
        payment = _calculate_monthly_payment(loan_amount, rate)
        total_interest = (payment * term_months) - loan_amount

        diff = payment - base_payment
        annual_diff = diff * 12
        lifetime_diff = diff * term_months

        scenario_data.append({
            "rate": rate,
            "rate_formatted": f"{rate:.3f}%",
            "monthly_payment": round(payment, 2),
            "payment_formatted": format_currency(payment),
            "total_interest": round(total_interest, 2),
            "interest_formatted": format_currency(total_interest),
            "vs_base": {
                "monthly_diff": round(diff, 2),
                "monthly_diff_formatted": f"{'+' if diff > 0 else ''}{format_currency(diff)}",
                "annual_diff": round(annual_diff, 2),
                "annual_diff_formatted": f"{'+' if annual_diff > 0 else ''}{format_currency(annual_diff)}",
                "lifetime_diff": round(lifetime_diff, 2),
                "lifetime_diff_formatted": f"{'+' if lifetime_diff > 0 else ''}{format_currency(lifetime_diff)}",
            },
            "is_base": rate == base_rate,
        })

    data = {
        "loan_amount": loan_amount,
        "loan_formatted": format_currency(loan_amount),
        "term_years": term_years,
        "base_rate": base_rate,
        "scenarios": scenario_data,
        "sensitivity": {
            "payment_per_eighth": round((_calculate_monthly_payment(loan_amount, base_rate + 0.125) - base_payment), 2),
            "annual_cost_per_eighth": round((_calculate_monthly_payment(loan_amount, base_rate + 0.125) - base_payment) * 12, 2),
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Rate scenarios for {format_currency(loan_amount)}: {len(scenarios)} options compared",
    )


@mortgage_tool(
    name="get_market_events",
    description="Get upcoming market events that may impact rates",
    agent_roles=["rate_advisor"],
    risk_level="LOW",
)
def get_market_events(days_ahead: int = 14) -> ToolResult:
    """
    Get upcoming economic events that may impact mortgage rates.
    """
    events = execute_query("""
        SELECT
            event_date,
            event_name,
            event_type,
            importance,
            expected_impact,
            notes
        FROM market_events
        WHERE event_date >= CURRENT_DATE
            AND event_date <= CURRENT_DATE + :days_ahead
        ORDER BY event_date ASC, importance DESC
    """, {"days_ahead": days_ahead})

    # If no events in DB, provide standard Fed calendar (fallback)
    if not events:
        today = date.today()
        events = _get_standard_market_events(today, days_ahead)

    high_impact = []
    all_events = []

    for e in events:
        event_data = {
            "date": format_date(e["event_date"]) if hasattr(e, "get") else format_date(e.get("date")),
            "name": e.get("event_name") or e.get("name"),
            "type": e.get("event_type") or e.get("type"),
            "importance": e.get("importance", "medium"),
            "expected_impact": e.get("expected_impact") or e.get("impact", "unknown"),
            "notes": e.get("notes"),
        }

        all_events.append(event_data)
        if event_data["importance"] == "high":
            high_impact.append(event_data)

    data = {
        "period_days": days_ahead,
        "total_events": len(all_events),
        "high_impact_count": len(high_impact),
        "high_impact_events": high_impact,
        "all_events": all_events,
        "guidance": _get_market_event_guidance(high_impact),
    }

    return ToolResult.success(
        data=data,
        message=f"Market calendar: {len(all_events)} events in next {days_ahead} days, {len(high_impact)} high-impact",
    )


def _get_standard_market_events(start_date: date, days_ahead: int) -> List[Dict]:
    """Generate standard market events when DB is empty."""
    events = []

    # Standard monthly events (approximate)
    monthly_events = [
        {"name": "Employment Report (NFP)", "type": "economic", "importance": "high", "impact": "Major rate mover"},
        {"name": "CPI Inflation Data", "type": "economic", "importance": "high", "impact": "Key inflation indicator"},
        {"name": "FOMC Meeting", "type": "federal_reserve", "importance": "high", "impact": "Rate policy decision"},
    ]

    # Add events for the period
    for i in range(min(days_ahead, 30)):
        event_date = start_date + timedelta(days=i)
        if event_date.weekday() < 5:  # Weekdays only
            # First Friday - NFP
            if event_date.day <= 7 and event_date.weekday() == 4:
                events.append({
                    "date": event_date,
                    "name": "Employment Report (NFP)",
                    "type": "economic",
                    "importance": "high",
                    "impact": "Major rate mover",
                    "notes": "Monthly jobs data typically moves rates",
                })

    return events


def _get_market_event_guidance(high_impact: List[Dict]) -> str:
    """Generate guidance based on upcoming events."""
    if not high_impact:
        return "No high-impact events in forecast period - standard rate volatility expected"

    if len(high_impact) >= 3:
        return "Multiple high-impact events - consider locking before volatility increases"

    event_names = [e["name"] for e in high_impact]
    if any("FOMC" in name for name in event_names):
        return "FOMC meeting ahead - expect heightened volatility around decision time"
    if any("NFP" in name or "Employment" in name for name in event_names):
        return "Jobs report ahead - lock before if risk-averse"

    return f"High-impact events coming: {', '.join(event_names[:2])} - monitor closely"
