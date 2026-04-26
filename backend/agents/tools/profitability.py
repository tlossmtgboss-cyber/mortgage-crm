"""
Perennia AI - Profitability Analysis Tools
Tools for the Profitability Analyst agent to analyze loan economics.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single,
    format_currency, format_percentage, days_between,
    calculate_percentage_change,
    LoanType,
)


# Cost benchmarks by loan type (basis points)
COST_BENCHMARKS = {
    "conventional": {"origination": 50, "processing": 25, "underwriting": 30, "total": 125},
    "fha": {"origination": 55, "processing": 30, "underwriting": 35, "total": 145},
    "va": {"origination": 45, "processing": 25, "underwriting": 30, "total": 120},
    "jumbo": {"origination": 40, "processing": 35, "underwriting": 45, "total": 140},
}

# Target margins by channel
MARGIN_TARGETS = {
    "retail": {"gross": 200, "net": 100},  # basis points
    "wholesale": {"gross": 75, "net": 35},
    "correspondent": {"gross": 50, "net": 20},
}


@mortgage_tool(
    name="calculate_loan_profitability",
    description="Calculate detailed profitability analysis for a specific loan",
    agent_roles=["profitability_analyst"],
    risk_level="LOW",
    examples=[
        "calculate_loan_profitability(loan_id='L123')",
    ],
)
def calculate_loan_profitability(loan_id: str) -> ToolResult:
    """
    Calculate comprehensive profitability for a loan.

    Includes:
    - Gross revenue (origination fee, SRP, pricing adjustments)
    - Direct costs (LO comp, processing, underwriting)
    - Indirect costs (overhead allocation)
    - Net profit and margin
    """
    loan = execute_single("""
        SELECT
            l.*,
            lt.name as loan_type_name,
            COALESCE(loes.full_name, lo.email) as lo_name,
            lo.commission_rate as lo_commission_rate,
            b.name as branch_name
        FROM loans l
        LEFT JOIN loan_types lt ON lt.id = l.loan_type_id
        LEFT JOIN users lo ON lo.id = l.loan_officer_id
        LEFT JOIN email_signatures loes ON loes.user_id = lo.id
        LEFT JOIN branches b ON b.id = l.branch_id
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    loan_amount = float(loan.get("loan_amount", 0))
    if loan_amount == 0:
        return ToolResult.error("Loan amount is zero, cannot calculate profitability")

    # Get fee breakdown
    fees = execute_single("""
        SELECT
            COALESCE(SUM(CASE WHEN fee_type = 'origination' THEN amount END), 0) as origination_fee,
            COALESCE(SUM(CASE WHEN fee_type = 'processing' THEN amount END), 0) as processing_fee,
            COALESCE(SUM(CASE WHEN fee_type = 'underwriting' THEN amount END), 0) as underwriting_fee,
            COALESCE(SUM(CASE WHEN fee_type = 'discount_points' THEN amount END), 0) as discount_points,
            COALESCE(SUM(CASE WHEN fee_type = 'lender_credit' THEN amount END), 0) as lender_credits,
            COALESCE(SUM(amount), 0) as total_fees
        FROM loan_fees
        WHERE loan_id = :loan_id
    """, {"loan_id": loan_id})

    # Get SRP (Service Release Premium) if sold
    srp = execute_single("""
        SELECT
            srp_rate, srp_amount, investor_name, sold_date
        FROM loan_sales
        WHERE loan_id = :loan_id
        ORDER BY sold_date DESC
        LIMIT 1
    """, {"loan_id": loan_id})

    # Revenue calculations
    origination_fee = float(fees.get("origination_fee", 0))
    srp_amount = float(srp.get("srp_amount", 0)) if srp else 0
    discount_points = float(fees.get("discount_points", 0))
    lender_credits = float(fees.get("lender_credits", 0))

    gross_revenue = origination_fee + srp_amount + discount_points - lender_credits

    # Cost calculations
    lo_commission_rate = float(loan.get("lo_commission_rate", 0.0075))  # Default 75 bps
    lo_compensation = loan_amount * lo_commission_rate

    processing_cost = float(fees.get("processing_fee", 0)) * 0.7  # 70% is cost
    underwriting_cost = float(fees.get("underwriting_fee", 0)) * 0.6  # 60% is cost

    # Overhead allocation (based on loan amount tier)
    if loan_amount >= 1000000:
        overhead_bps = 15  # Jumbo = lower overhead per dollar
    elif loan_amount >= 500000:
        overhead_bps = 20
    else:
        overhead_bps = 25
    overhead_cost = loan_amount * (overhead_bps / 10000)

    total_direct_costs = lo_compensation + processing_cost + underwriting_cost
    total_costs = total_direct_costs + overhead_cost

    # Profit calculations
    net_profit = gross_revenue - total_costs
    gross_margin_bps = (gross_revenue / loan_amount) * 10000
    net_margin_bps = (net_profit / loan_amount) * 10000

    # Compare to benchmarks
    loan_type = (loan.get("loan_type") or "conventional").lower()
    benchmark = COST_BENCHMARKS.get(loan_type, COST_BENCHMARKS["conventional"])
    margin_target = MARGIN_TARGETS.get("retail", MARGIN_TARGETS["retail"])

    vs_target = net_margin_bps - margin_target["net"]

    data = {
        "loan_id": loan_id,
        "loan_details": {
            "amount": loan_amount,
            "amount_formatted": format_currency(loan_amount),
            "type": loan.get("loan_type"),
            "lo_name": loan["lo_name"],
            "branch": loan["branch_name"],
        },
        "revenue": {
            "origination_fee": origination_fee,
            "srp": srp_amount,
            "discount_points": discount_points,
            "lender_credits": lender_credits,
            "gross_revenue": gross_revenue,
            "gross_revenue_formatted": format_currency(gross_revenue),
            "gross_margin_bps": round(gross_margin_bps, 1),
        },
        "costs": {
            "lo_compensation": lo_compensation,
            "processing": processing_cost,
            "underwriting": underwriting_cost,
            "overhead": overhead_cost,
            "total_direct": total_direct_costs,
            "total_costs": total_costs,
            "total_costs_formatted": format_currency(total_costs),
            "cost_bps": round((total_costs / loan_amount) * 10000, 1),
        },
        "profitability": {
            "net_profit": net_profit,
            "net_profit_formatted": format_currency(net_profit),
            "net_margin_bps": round(net_margin_bps, 1),
            "roi_percent": round((net_profit / total_costs) * 100, 1) if total_costs > 0 else 0,
        },
        "benchmarks": {
            "target_margin_bps": margin_target["net"],
            "vs_target_bps": round(vs_target, 1),
            "performance": "above_target" if vs_target > 0 else "below_target",
            "cost_benchmark_bps": benchmark["total"],
            "vs_cost_benchmark": round(((total_costs / loan_amount) * 10000) - benchmark["total"], 1),
        },
    }

    performance = "above" if vs_target > 0 else "below"
    return ToolResult.success(
        data=data,
        message=f"Loan profitability: {format_currency(net_profit)} ({round(net_margin_bps, 1)} bps), {performance} target by {abs(round(vs_target, 1))} bps",
    )


@mortgage_tool(
    name="analyze_margins_by_segment",
    description="Analyze profit margins across different loan segments",
    agent_roles=["profitability_analyst"],
    risk_level="LOW",
)
def analyze_margins_by_segment(
    segment_by: str = "loan_type",
    date_range: int = 90,
    branch_id: Optional[str] = None,
) -> ToolResult:
    """
    Analyze margins by segment (loan type, channel, loan size, LO).

    Args:
        segment_by: loan_type, channel, loan_size_tier, lo
        date_range: Days to analyze
        branch_id: Optional branch filter
    """
    valid_segments = ["loan_type", "channel", "loan_size_tier", "lo"]
    if segment_by not in valid_segments:
        raise ToolError(f"Invalid segment_by: {segment_by}. Valid: {valid_segments}")

    segment_column = {
        "loan_type": "l.loan_type",
        "channel": "l.channel",
        "loan_size_tier": """
            CASE
                WHEN l.loan_amount >= 1000000 THEN 'jumbo'
                WHEN l.loan_amount >= 500000 THEN 'high_balance'
                WHEN l.loan_amount >= 250000 THEN 'conforming'
                ELSE 'small_balance'
            END
        """,
        "lo": "COALESCE(loes.full_name, lo.email)",
    }[segment_by]

    params = {"date_range": date_range}
    branch_filter = ""
    if branch_id:
        branch_filter = "AND l.branch_id = :branch_id"
        params["branch_id"] = branch_id

    segments = execute_query(f"""
        WITH loan_profits AS (
            SELECT
                l.id,
                {segment_column} as segment,
                l.loan_amount,
                COALESCE(
                    (SELECT SUM(amount) FROM loan_fees WHERE loan_id = l.id), 0
                ) + COALESCE(ls.srp_amount, 0) as gross_revenue,
                l.loan_amount * COALESCE(lo.commission_rate, 0.0075) as lo_cost
            FROM loans l
            LEFT JOIN users lo ON lo.id = l.loan_officer_id
            LEFT JOIN email_signatures loes ON loes.user_id = lo.id
            LEFT JOIN loan_sales ls ON ls.loan_id = l.id
            WHERE l.funded_date >= CURRENT_DATE - :date_range
                AND l.stage = 'Funded'
                {branch_filter}
        )
        SELECT
            segment,
            COUNT(*) as loan_count,
            SUM(loan_amount) as total_volume,
            AVG(loan_amount) as avg_loan_size,
            SUM(gross_revenue) as total_revenue,
            AVG(gross_revenue / loan_amount * 10000) as avg_gross_margin_bps,
            SUM(gross_revenue - lo_cost) as estimated_profit,
            AVG((gross_revenue - lo_cost) / loan_amount * 10000) as avg_net_margin_bps
        FROM loan_profits
        WHERE segment IS NOT NULL
        GROUP BY segment
        ORDER BY total_volume DESC
    """, params)

    if not segments:
        return ToolResult.no_data(f"No funded loans found in last {date_range} days")

    # Calculate totals
    total_volume = sum(float(s["total_volume"]) for s in segments)
    total_revenue = sum(float(s["total_revenue"]) for s in segments)
    total_profit = sum(float(s["estimated_profit"]) for s in segments)

    segment_data = []
    for s in segments:
        volume_share = (float(s["total_volume"]) / total_volume * 100) if total_volume > 0 else 0
        profit_share = (float(s["estimated_profit"]) / total_profit * 100) if total_profit > 0 else 0

        segment_data.append({
            "segment": s["segment"],
            "loan_count": s["loan_count"],
            "total_volume": float(s["total_volume"]),
            "total_volume_formatted": format_currency(s["total_volume"]),
            "volume_share": round(volume_share, 1),
            "avg_loan_size": float(s["avg_loan_size"]),
            "avg_loan_size_formatted": format_currency(s["avg_loan_size"]),
            "total_revenue": float(s["total_revenue"]),
            "gross_margin_bps": round(float(s["avg_gross_margin_bps"]), 1),
            "estimated_profit": float(s["estimated_profit"]),
            "profit_formatted": format_currency(s["estimated_profit"]),
            "profit_share": round(profit_share, 1),
            "net_margin_bps": round(float(s["avg_net_margin_bps"]), 1),
            "profit_per_loan": format_currency(float(s["estimated_profit"]) / s["loan_count"]),
        })

    # Find best and worst performers
    by_margin = sorted(segment_data, key=lambda x: x["net_margin_bps"], reverse=True)

    data = {
        "segment_type": segment_by,
        "period_days": date_range,
        "totals": {
            "volume": total_volume,
            "volume_formatted": format_currency(total_volume),
            "revenue": total_revenue,
            "profit": total_profit,
            "profit_formatted": format_currency(total_profit),
            "overall_margin_bps": round((total_profit / total_volume) * 10000, 1) if total_volume > 0 else 0,
        },
        "segments": segment_data,
        "insights": {
            "highest_margin": by_margin[0]["segment"] if by_margin else None,
            "highest_margin_bps": by_margin[0]["net_margin_bps"] if by_margin else None,
            "lowest_margin": by_margin[-1]["segment"] if by_margin else None,
            "lowest_margin_bps": by_margin[-1]["net_margin_bps"] if by_margin else None,
            "margin_spread": round(by_margin[0]["net_margin_bps"] - by_margin[-1]["net_margin_bps"], 1) if len(by_margin) >= 2 else 0,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Margin analysis by {segment_by}: {len(segments)} segments, overall margin {data['totals']['overall_margin_bps']} bps",
    )


@mortgage_tool(
    name="forecast_revenue",
    description="Forecast revenue from current pipeline",
    agent_roles=["profitability_analyst"],
    risk_level="LOW",
)
def forecast_revenue(
    lo_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    forecast_months: int = 3,
) -> ToolResult:
    """
    Forecast revenue from current pipeline using pull-through rates.
    """
    params = {"months": forecast_months}
    filters = ["l.stage NOT IN ('Funded')"]

    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id

    # Pull-through rates by stage (historical average)
    pull_through = {
        "application": 0.45,
        "processing": 0.65,
        "underwriting": 0.75,
        "conditional_approval": 0.85,
        "clear_to_close": 0.95,
        "closing": 0.98,
    }

    # Average margin by stage (bps)
    avg_margin_bps = 100

    pipeline = execute_query(f"""
        SELECT
            l.status,
            COUNT(*) as loan_count,
            SUM(l.loan_amount) as total_volume,
            l.expected_close_date
        FROM loans l
        WHERE {' AND '.join(filters)}
            AND l.expected_close_date <= CURRENT_DATE + INTERVAL ':months months'
        GROUP BY l.status, l.expected_close_date
        ORDER BY l.expected_close_date
    """, params)

    if not pipeline:
        return ToolResult.no_data("No loans in pipeline for forecast period")

    # Calculate forecasts by month
    monthly_forecast = {}
    for p in pipeline:
        if not p.get("expected_close_date"):
            continue

        month_key = p["expected_close_date"].strftime("%Y-%m")
        rate = pull_through.get(p["status"], 0.5)
        volume = float(p["total_volume"])
        expected_volume = volume * rate
        expected_revenue = expected_volume * (avg_margin_bps / 10000)

        if month_key not in monthly_forecast:
            monthly_forecast[month_key] = {
                "pipeline_volume": 0,
                "expected_volume": 0,
                "expected_revenue": 0,
                "loan_count": 0,
            }

        monthly_forecast[month_key]["pipeline_volume"] += volume
        monthly_forecast[month_key]["expected_volume"] += expected_volume
        monthly_forecast[month_key]["expected_revenue"] += expected_revenue
        monthly_forecast[month_key]["loan_count"] += p["loan_count"]

    # Stage breakdown
    by_stage = execute_query(f"""
        SELECT
            l.status,
            COUNT(*) as loan_count,
            SUM(l.loan_amount) as volume
        FROM loans l
        WHERE {' AND '.join(filters)}
        GROUP BY l.status
        ORDER BY
            CASE l.status
                WHEN 'application' THEN 1
                WHEN 'processing' THEN 2
                WHEN 'underwriting' THEN 3
                WHEN 'conditional_approval' THEN 4
                WHEN 'clear_to_close' THEN 5
                WHEN 'closing' THEN 6
            END
    """, params)

    stage_forecast = []
    total_pipeline = 0
    total_expected = 0

    for s in by_stage:
        volume = float(s["volume"])
        rate = pull_through.get(s["status"], 0.5)
        expected = volume * rate

        total_pipeline += volume
        total_expected += expected

        stage_forecast.append({
            "stage": s["status"],
            "loan_count": s["loan_count"],
            "volume": volume,
            "volume_formatted": format_currency(volume),
            "pull_through_rate": format_percentage(rate * 100),
            "expected_volume": expected,
            "expected_volume_formatted": format_currency(expected),
            "expected_revenue": format_currency(expected * (avg_margin_bps / 10000)),
        })

    total_expected_revenue = total_expected * (avg_margin_bps / 10000)

    data = {
        "forecast_period_months": forecast_months,
        "pipeline_summary": {
            "total_pipeline_volume": total_pipeline,
            "total_pipeline_formatted": format_currency(total_pipeline),
            "weighted_expected_volume": total_expected,
            "weighted_expected_formatted": format_currency(total_expected),
            "blended_pull_through": format_percentage((total_expected / total_pipeline) * 100) if total_pipeline > 0 else "0%",
            "total_expected_revenue": total_expected_revenue,
            "revenue_formatted": format_currency(total_expected_revenue),
        },
        "by_stage": stage_forecast,
        "monthly_forecast": [
            {
                "month": month,
                "pipeline_volume": format_currency(data["pipeline_volume"]),
                "expected_volume": format_currency(data["expected_volume"]),
                "expected_revenue": format_currency(data["expected_revenue"]),
                "loan_count": data["loan_count"],
            }
            for month, data in sorted(monthly_forecast.items())
        ],
        "assumptions": {
            "margin_bps": avg_margin_bps,
            "pull_through_rates": pull_through,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Revenue forecast: {format_currency(total_expected_revenue)} from {format_currency(total_expected)} expected volume ({forecast_months}mo)",
    )


@mortgage_tool(
    name="compare_lo_profitability",
    description="Compare profitability metrics across loan officers",
    agent_roles=["profitability_analyst", "team_coach"],
    risk_level="LOW",
)
def compare_lo_profitability(
    branch_id: Optional[str] = None,
    date_range: int = 90,
    min_loans: int = 3,
) -> ToolResult:
    """
    Compare profitability across loan officers.
    """
    params = {"date_range": date_range, "min_loans": min_loans}
    branch_filter = ""
    if branch_id:
        branch_filter = "AND l.branch_id = :branch_id"
        params["branch_id"] = branch_id

    los = execute_query(f"""
        WITH lo_metrics AS (
            SELECT
                l.loan_officer_id,
                COALESCE(loes.full_name, lo.email) as lo_name,
                COUNT(*) as funded_count,
                SUM(l.loan_amount) as total_volume,
                AVG(l.loan_amount) as avg_loan_size,
                SUM(COALESCE(
                    (SELECT SUM(amount) FROM loan_fees WHERE loan_id = l.id), 0
                )) as total_fees,
                SUM(COALESCE(ls.srp_amount, 0)) as total_srp,
                lo.commission_rate
            FROM loans l
            JOIN users lo ON lo.id = l.loan_officer_id
            LEFT JOIN email_signatures loes ON loes.user_id = lo.id
            LEFT JOIN loan_sales ls ON ls.loan_id = l.id
            WHERE l.funded_date >= CURRENT_DATE - :date_range
                AND l.stage = 'Funded'
                {branch_filter}
            GROUP BY l.loan_officer_id, COALESCE(loes.full_name, lo.email), lo.commission_rate
            HAVING COUNT(*) >= :min_loans
        )
        SELECT
            *,
            total_fees + total_srp as gross_revenue,
            (total_fees + total_srp) / total_volume * 10000 as gross_margin_bps,
            total_volume * COALESCE(commission_rate, 0.0075) as lo_comp
        FROM lo_metrics
        ORDER BY gross_revenue DESC
    """, params)

    if not los:
        return ToolResult.no_data(f"No LOs with {min_loans}+ funded loans in last {date_range} days")

    # Calculate rankings
    lo_data = []
    for lo in los:
        gross = float(lo["gross_revenue"])
        lo_comp = float(lo["lo_comp"])
        net_profit = gross - lo_comp
        volume = float(lo["total_volume"])

        lo_data.append({
            "lo_id": lo["loan_officer_id"],
            "name": lo["lo_name"],
            "funded_count": lo["funded_count"],
            "total_volume": volume,
            "volume_formatted": format_currency(volume),
            "avg_loan_size": float(lo["avg_loan_size"]),
            "avg_loan_formatted": format_currency(lo["avg_loan_size"]),
            "gross_revenue": gross,
            "gross_margin_bps": round(float(lo["gross_margin_bps"]), 1),
            "lo_compensation": lo_comp,
            "net_profit": net_profit,
            "net_profit_formatted": format_currency(net_profit),
            "net_margin_bps": round((net_profit / volume) * 10000, 1) if volume > 0 else 0,
            "profit_per_loan": format_currency(net_profit / lo["funded_count"]),
            "revenue_per_loan": format_currency(gross / lo["funded_count"]),
        })

    # Add rankings
    by_volume = sorted(lo_data, key=lambda x: x["total_volume"], reverse=True)
    by_profit = sorted(lo_data, key=lambda x: x["net_profit"], reverse=True)
    by_margin = sorted(lo_data, key=lambda x: x["net_margin_bps"], reverse=True)
    by_efficiency = sorted(lo_data, key=lambda x: x["profit_per_loan"], reverse=True)

    for i, lo in enumerate(by_volume):
        lo["rank_volume"] = i + 1
    for i, lo in enumerate(by_profit):
        lo["rank_profit"] = i + 1
    for i, lo in enumerate(by_margin):
        lo["rank_margin"] = i + 1
    for i, lo in enumerate(by_efficiency):
        lo["rank_efficiency"] = i + 1

    # Team totals
    total_volume = sum(lo["total_volume"] for lo in lo_data)
    total_profit = sum(lo["net_profit"] for lo in lo_data)

    data = {
        "period_days": date_range,
        "lo_count": len(lo_data),
        "team_totals": {
            "total_volume": total_volume,
            "volume_formatted": format_currency(total_volume),
            "total_profit": total_profit,
            "profit_formatted": format_currency(total_profit),
            "overall_margin_bps": round((total_profit / total_volume) * 10000, 1) if total_volume > 0 else 0,
        },
        "loan_officers": sorted(lo_data, key=lambda x: x["net_profit"], reverse=True),
        "rankings": {
            "top_volume": by_volume[0]["name"] if by_volume else None,
            "top_profit": by_profit[0]["name"] if by_profit else None,
            "top_margin": by_margin[0]["name"] if by_margin else None,
            "most_efficient": by_efficiency[0]["name"] if by_efficiency else None,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"LO profitability: {len(lo_data)} LOs, {format_currency(total_profit)} total profit, {data['team_totals']['overall_margin_bps']} bps margin",
    )


@mortgage_tool(
    name="optimize_pricing",
    description="Analyze pricing optimization opportunities",
    agent_roles=["profitability_analyst"],
    risk_level="LOW",
)
def optimize_pricing(
    loan_id: Optional[str] = None,
    loan_type: Optional[str] = None,
    date_range: int = 30,
) -> ToolResult:
    """
    Analyze pricing and identify optimization opportunities.
    """
    params = {"date_range": date_range}

    if loan_id:
        # Single loan analysis
        loan = execute_single("""
            SELECT
                l.*,
                (SELECT SUM(amount) FROM loan_fees WHERE loan_id = l.id AND fee_type = 'origination') as orig_fee,
                (SELECT SUM(amount) FROM loan_fees WHERE loan_id = l.id AND fee_type = 'discount_points') as points,
                (SELECT SUM(amount) FROM loan_fees WHERE loan_id = l.id AND fee_type = 'lender_credit') as credits
            FROM loans l
            WHERE l.id = :loan_id
        """, {"loan_id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        # Get comparable loans
        comparables = execute_query("""
            SELECT
                AVG(lf.amount / l.loan_amount * 100) as avg_orig_pct,
                AVG(l.rate) as avg_rate,
                COUNT(*) as comp_count
            FROM loans l
            JOIN loan_fees lf ON lf.loan_id = l.id AND lf.fee_type = 'origination'
            WHERE l.loan_type = :loan_type
                AND l.loan_amount BETWEEN :loan_amount * 0.8 AND :loan_amount * 1.2
                AND l.funded_date >= CURRENT_DATE - 30
                AND l.id != :loan_id
        """, {
            "loan_id": loan_id,
            "loan_type": loan.get("loan_type"),
            "loan_amount": float(loan.get("loan_amount", 0)),
        })

        loan_amount = float(loan.get("loan_amount", 0))
        orig_fee = float(loan.get("orig_fee") or 0)
        actual_orig_pct = (orig_fee / loan_amount * 100) if loan_amount > 0 else 0

        comp = comparables[0] if comparables else {}
        avg_orig_pct = float(comp.get("avg_orig_pct", 1.0) or 1.0)

        opportunity = (avg_orig_pct - actual_orig_pct) * loan_amount / 100

        data = {
            "loan_id": loan_id,
            "current_pricing": {
                "origination_fee": orig_fee,
                "origination_pct": round(actual_orig_pct, 3),
                "discount_points": float(loan.get("points") or 0),
                "lender_credits": float(loan.get("credits") or 0),
                "rate": float(loan.get("rate") or 0),
            },
            "market_comparison": {
                "avg_origination_pct": round(avg_orig_pct, 3),
                "comparable_count": comp.get("comp_count", 0),
                "avg_rate": round(float(comp.get("avg_rate", 0) or 0), 3),
            },
            "opportunity": {
                "pricing_gap_pct": round(avg_orig_pct - actual_orig_pct, 3),
                "potential_revenue": round(opportunity, 2),
                "potential_formatted": format_currency(opportunity),
            },
            "recommendations": _get_pricing_recommendations(actual_orig_pct, avg_orig_pct, loan),
        }

        return ToolResult.success(
            data=data,
            message=f"Pricing analysis: Current {round(actual_orig_pct, 2)}% vs market {round(avg_orig_pct, 2)}%, opportunity {format_currency(opportunity)}",
        )

    else:
        # Portfolio analysis
        type_filter = ""
        if loan_type:
            type_filter = "AND l.loan_type = :loan_type"
            params["loan_type"] = loan_type

        analysis = execute_query(f"""
            SELECT
                l.loan_type,
                l.channel,
                COUNT(*) as loan_count,
                AVG(lf.amount / l.loan_amount * 100) as avg_orig_pct,
                MIN(lf.amount / l.loan_amount * 100) as min_orig_pct,
                MAX(lf.amount / l.loan_amount * 100) as max_orig_pct,
                STDDEV(lf.amount / l.loan_amount * 100) as stddev_orig_pct
            FROM loans l
            JOIN loan_fees lf ON lf.loan_id = l.id AND lf.fee_type = 'origination'
            WHERE l.funded_date >= CURRENT_DATE - :date_range
                {type_filter}
            GROUP BY l.loan_type, l.channel
            ORDER BY l.loan_type, l.channel
        """, params)

        if not analysis:
            return ToolResult.no_data("No pricing data available")

        segments = []
        for a in analysis:
            variance = float(a.get("stddev_orig_pct") or 0)
            segments.append({
                "loan_type": a["loan_type"],
                "channel": a["channel"],
                "loan_count": a["loan_count"],
                "avg_origination_pct": round(float(a["avg_orig_pct"]), 3),
                "min_pct": round(float(a["min_orig_pct"]), 3),
                "max_pct": round(float(a["max_orig_pct"]), 3),
                "variance": round(variance, 3),
                "consistency": "high" if variance < 0.1 else "medium" if variance < 0.25 else "low",
            })

        data = {
            "period_days": date_range,
            "segments": segments,
            "insights": {
                "high_variance_segments": [s for s in segments if s["consistency"] == "low"],
                "optimization_targets": [s for s in segments if s["avg_origination_pct"] < 1.0],
            },
        }

        return ToolResult.success(
            data=data,
            message=f"Pricing analysis: {len(segments)} segments analyzed over {date_range} days",
        )


def _get_pricing_recommendations(actual: float, market: float, loan: Dict) -> List[str]:
    """Generate pricing recommendations."""
    recs = []

    gap = market - actual
    if gap > 0.25:
        recs.append(f"Pricing is {gap:.2f}% below market - consider increasing origination fee")
    elif gap < -0.25:
        recs.append(f"Pricing is {abs(gap):.2f}% above market - may impact competitiveness")

    if float(loan.get("credits") or 0) > 0:
        recs.append("Lender credits being offered - ensure margin impact is justified by volume")

    return recs if recs else ["Pricing appears aligned with market"]


@mortgage_tool(
    name="get_cost_breakdown",
    description="Get detailed cost breakdown for loans",
    agent_roles=["profitability_analyst"],
    risk_level="LOW",
)
def get_cost_breakdown(
    loan_id: Optional[str] = None,
    date_range: int = 30,
    lo_id: Optional[str] = None,
) -> ToolResult:
    """
    Get detailed cost breakdown by category.
    """
    if loan_id:
        # Single loan costs
        costs = execute_query("""
            SELECT
                cost_category,
                cost_type,
                amount,
                is_capitalized,
                vendor_name
            FROM loan_costs
            WHERE loan_id = :loan_id
            ORDER BY cost_category, amount DESC
        """, {"loan_id": loan_id})

        loan = execute_single("""
            SELECT loan_amount, loan_type FROM loans WHERE id = :loan_id
        """, {"loan_id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        # Group by category
        by_category = {}
        total = 0
        for c in costs:
            cat = c["cost_category"]
            if cat not in by_category:
                by_category[cat] = {"items": [], "total": 0}
            by_category[cat]["items"].append({
                "type": c["cost_type"],
                "amount": float(c["amount"]),
                "vendor": c["vendor_name"],
                "capitalized": c["is_capitalized"],
            })
            by_category[cat]["total"] += float(c["amount"])
            total += float(c["amount"])

        loan_amount = float(loan["loan_amount"])
        cost_bps = (total / loan_amount) * 10000 if loan_amount > 0 else 0

        data = {
            "loan_id": loan_id,
            "loan_amount": loan_amount,
            "total_costs": total,
            "total_formatted": format_currency(total),
            "cost_bps": round(cost_bps, 1),
            "by_category": {
                cat: {
                    "total": data["total"],
                    "formatted": format_currency(data["total"]),
                    "pct_of_total": round((data["total"] / total) * 100, 1) if total > 0 else 0,
                    "items": data["items"],
                }
                for cat, data in by_category.items()
            },
        }

        return ToolResult.success(
            data=data,
            message=f"Loan costs: {format_currency(total)} ({round(cost_bps, 1)} bps)",
        )

    else:
        # Aggregate costs
        params = {"date_range": date_range}
        lo_filter = ""
        if lo_id:
            lo_filter = "AND l.loan_officer_id = :lo_id"
            params["lo_id"] = lo_id

        costs = execute_query(f"""
            SELECT
                c.cost_category,
                COUNT(DISTINCT l.id) as loan_count,
                SUM(c.amount) as total_amount,
                AVG(c.amount) as avg_amount,
                SUM(c.amount) / SUM(l.loan_amount) * 10000 as avg_bps
            FROM loan_costs c
            JOIN loans l ON l.id = c.loan_id
            WHERE l.funded_date >= CURRENT_DATE - :date_range
                {lo_filter}
            GROUP BY c.cost_category
            ORDER BY total_amount DESC
        """, params)

        if not costs:
            return ToolResult.no_data("No cost data available")

        total = sum(float(c["total_amount"]) for c in costs)

        data = {
            "period_days": date_range,
            "total_costs": total,
            "total_formatted": format_currency(total),
            "categories": [
                {
                    "category": c["cost_category"],
                    "loan_count": c["loan_count"],
                    "total": float(c["total_amount"]),
                    "total_formatted": format_currency(c["total_amount"]),
                    "avg_per_loan": float(c["avg_amount"]),
                    "avg_bps": round(float(c["avg_bps"]), 1),
                    "pct_of_total": round((float(c["total_amount"]) / total) * 100, 1) if total > 0 else 0,
                }
                for c in costs
            ],
        }

        return ToolResult.success(
            data=data,
            message=f"Cost breakdown: {format_currency(total)} total across {len(costs)} categories",
        )


@mortgage_tool(
    name="calculate_pull_through_impact",
    description="Calculate financial impact of pull-through rate changes",
    agent_roles=["profitability_analyst"],
    risk_level="LOW",
)
def calculate_pull_through_impact(
    current_rate: Optional[float] = None,
    target_rate: Optional[float] = None,
    date_range: int = 90,
) -> ToolResult:
    """
    Calculate revenue impact of pull-through rate improvements.
    """
    # Get current pull-through metrics
    metrics = execute_single("""
        SELECT
            COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as funded,
            COUNT(CASE WHEN stage NOT IN ('Disclosed', 'Processing', 'Submitted', 'UW Received', 'Approved', 'Suspended', 'CTC', 'Docs Out', 'Funded') THEN 1 END) as fallout,
            COUNT(*) as total,
            SUM(CASE WHEN stage = 'Funded' THEN loan_amount END) as funded_volume,
            SUM(CASE WHEN stage NOT IN ('Disclosed', 'Processing', 'Submitted', 'UW Received', 'Approved', 'Suspended', 'CTC', 'Docs Out', 'Funded') THEN loan_amount END) as fallout_volume
        FROM loans
        WHERE created_at >= CURRENT_DATE - :date_range
            AND stage IS NOT NULL
    """, {"date_range": date_range})

    if not metrics or metrics["total"] == 0:
        return ToolResult.no_data("No closed loans in period for analysis")

    actual_rate = (metrics["funded"] / metrics["total"]) if metrics["total"] > 0 else 0
    calc_current = current_rate if current_rate else actual_rate
    calc_target = target_rate if target_rate else min(calc_current + 0.05, 0.95)

    # Calculate impact
    avg_margin_bps = 100
    avg_loan_size = float(metrics["funded_volume"]) / metrics["funded"] if metrics["funded"] > 0 else 350000
    avg_profit_per_loan = avg_loan_size * (avg_margin_bps / 10000)

    # Project forward
    annual_apps = (metrics["total"] / date_range) * 365

    current_funded = annual_apps * calc_current
    target_funded = annual_apps * calc_target
    additional_funded = target_funded - current_funded

    revenue_impact = additional_funded * avg_profit_per_loan

    # Fallout analysis
    fallout_reasons = execute_query("""
        SELECT
            fallout_reason,
            COUNT(*) as count,
            SUM(loan_amount) as volume
        FROM loans
        WHERE created_at >= CURRENT_DATE - :date_range
            AND stage NOT IN ('Disclosed', 'Processing', 'Submitted', 'UW Received', 'Approved', 'Suspended', 'CTC', 'Docs Out', 'Funded')
            AND fallout_reason IS NOT NULL
        GROUP BY fallout_reason
        ORDER BY count DESC
        LIMIT 5
    """, {"date_range": date_range})

    data = {
        "current_metrics": {
            "period_days": date_range,
            "total_applications": metrics["total"],
            "funded": metrics["funded"],
            "fallout": metrics["fallout"],
            "actual_pull_through": format_percentage(actual_rate * 100),
            "funded_volume": format_currency(metrics["funded_volume"]),
            "fallout_volume": format_currency(metrics["fallout_volume"]),
        },
        "scenario_analysis": {
            "current_rate": format_percentage(calc_current * 100),
            "target_rate": format_percentage(calc_target * 100),
            "improvement_pct": format_percentage((calc_target - calc_current) * 100),
            "projected_annual_apps": round(annual_apps),
            "current_annual_funded": round(current_funded),
            "target_annual_funded": round(target_funded),
            "additional_funded_annually": round(additional_funded),
        },
        "financial_impact": {
            "avg_profit_per_loan": format_currency(avg_profit_per_loan),
            "annual_revenue_impact": revenue_impact,
            "impact_formatted": format_currency(revenue_impact),
            "monthly_impact": format_currency(revenue_impact / 12),
        },
        "top_fallout_reasons": [
            {
                "reason": f["fallout_reason"],
                "count": f["count"],
                "volume": format_currency(f["volume"]),
            }
            for f in fallout_reasons
        ],
        "recommendations": _get_pull_through_recommendations(fallout_reasons),
    }

    return ToolResult.success(
        data=data,
        message=f"Pull-through impact: {format_percentage((calc_target - calc_current) * 100)} improvement = {format_currency(revenue_impact)}/year",
    )


def _get_pull_through_recommendations(fallout_reasons: List[Dict]) -> List[str]:
    """Generate recommendations based on fallout analysis."""
    recs = []

    reason_map = {
        "credit": "Implement pre-qualification scoring to identify credit issues early",
        "income": "Enhance income verification early in process",
        "property": "Accelerate property-related diligence",
        "competing_offer": "Improve speed-to-close and rate lock strategy",
        "borrower_withdrew": "Enhance borrower engagement and communication",
    }

    for f in fallout_reasons[:3]:
        reason = f["fallout_reason"].lower()
        for key, rec in reason_map.items():
            if key in reason:
                recs.append(rec)
                break

    return recs if recs else ["Analyze fallout patterns to identify improvement areas"]


@mortgage_tool(
    name="get_profitability_trends",
    description="Get profitability trends over time",
    agent_roles=["profitability_analyst"],
    risk_level="LOW",
)
def get_profitability_trends(
    period: str = "monthly",
    num_periods: int = 6,
    lo_id: Optional[str] = None,
    branch_id: Optional[str] = None,
) -> ToolResult:
    """
    Get profitability trends over time.
    """
    period_expr = {
        "weekly": "DATE_TRUNC('week', l.funded_date)",
        "monthly": "DATE_TRUNC('month', l.funded_date)",
        "quarterly": "DATE_TRUNC('quarter', l.funded_date)",
    }.get(period, "DATE_TRUNC('month', l.funded_date)")

    params = {"num_periods": num_periods}
    filters = []
    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id

    where_clause = f"AND {' AND '.join(filters)}" if filters else ""

    trends = execute_query(f"""
        SELECT
            {period_expr} as period,
            COUNT(*) as loan_count,
            SUM(l.loan_amount) as volume,
            SUM(COALESCE((SELECT SUM(amount) FROM loan_fees WHERE loan_id = l.id), 0)) as fees,
            SUM(COALESCE(ls.srp_amount, 0)) as srp,
            AVG(l.loan_amount) as avg_loan_size
        FROM loans l
        LEFT JOIN loan_sales ls ON ls.loan_id = l.id
        WHERE l.stage = 'Funded'
            AND l.funded_date >= CURRENT_DATE - INTERVAL ':num_periods {period}s'
            {where_clause}
        GROUP BY {period_expr}
        ORDER BY period DESC
        LIMIT :num_periods
    """, params)

    if not trends:
        return ToolResult.no_data("No funded loans in analysis period")

    # Calculate metrics for each period
    period_data = []
    prev_margin = None

    for t in reversed(trends):
        volume = float(t["volume"])
        revenue = float(t["fees"]) + float(t["srp"])
        margin_bps = (revenue / volume) * 10000 if volume > 0 else 0

        change = None
        if prev_margin is not None:
            change = margin_bps - prev_margin

        period_data.append({
            "period": t["period"].strftime("%Y-%m-%d"),
            "loan_count": t["loan_count"],
            "volume": volume,
            "volume_formatted": format_currency(volume),
            "gross_revenue": revenue,
            "revenue_formatted": format_currency(revenue),
            "margin_bps": round(margin_bps, 1),
            "margin_change_bps": round(change, 1) if change is not None else None,
            "avg_loan_size": format_currency(t["avg_loan_size"]),
        })
        prev_margin = margin_bps

    # Calculate trend
    if len(period_data) >= 2:
        first_margin = period_data[0]["margin_bps"]
        last_margin = period_data[-1]["margin_bps"]
        trend_direction = "improving" if last_margin > first_margin else "declining" if last_margin < first_margin else "stable"
    else:
        trend_direction = "insufficient_data"

    data = {
        "period_type": period,
        "num_periods": len(period_data),
        "periods": period_data,
        "trend": {
            "direction": trend_direction,
            "start_margin_bps": period_data[0]["margin_bps"] if period_data else None,
            "end_margin_bps": period_data[-1]["margin_bps"] if period_data else None,
            "total_change_bps": round(period_data[-1]["margin_bps"] - period_data[0]["margin_bps"], 1) if len(period_data) >= 2 else None,
        },
        "summary": {
            "total_volume": sum(p["volume"] for p in period_data),
            "total_revenue": sum(p["gross_revenue"] for p in period_data),
            "avg_margin_bps": round(sum(p["margin_bps"] for p in period_data) / len(period_data), 1) if period_data else 0,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Profitability trend ({period}): {trend_direction}, avg {data['summary']['avg_margin_bps']} bps over {len(period_data)} periods",
    )
