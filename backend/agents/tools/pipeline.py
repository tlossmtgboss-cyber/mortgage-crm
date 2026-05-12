"""
Perennia AI - Pipeline Analysis Tools
Tools for the Pipeline Analyst agent to track and analyze loan pipeline metrics.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
    LoanStatus, SLA_TARGETS, get_loan_stage_order, is_loan_active,
    add_business_days,
    # Database-agnostic SQL helpers
    is_sqlite, sql_days_since, sql_now, sql_interval, sql_date_subtract,
)


@mortgage_tool(
    name="get_pipeline_metrics",
    description="Get comprehensive pipeline metrics including volume, velocity, and health indicators",
    agent_roles=["pipeline_analyst", "manager", "executive"],
    risk_level="low",
    examples=[
        "What's our current pipeline look like?",
        "Show me pipeline metrics",
        "How's the pipeline health?",
    ],
)
def get_pipeline_metrics(
    lo_id: Optional[int] = None,
    days_back: int = 30,
) -> ToolResult:
    """Get pipeline metrics with optional LO filter."""
    try:
        lo_filter = "AND l.loan_officer_id = :lo_id" if lo_id else ""

        # Database-agnostic date calculations
        days_in_stage_expr = sql_days_since('l.stage_changed_at')
        date_threshold = sql_date_subtract(days_back)

        # Get pipeline summary by stage
        # Note: Stage values must match LoanStage enum in main.py exactly
        pipeline_query = f"""
            SELECT
                l.stage,
                COUNT(*) as count,
                SUM(l.amount) as total_volume,
                AVG(l.amount) as avg_loan_size,
                AVG({days_in_stage_expr}) as avg_days_in_stage
            FROM loans l
            WHERE l.stage NOT IN ('Funded')
            {lo_filter}
            GROUP BY l.stage
            ORDER BY
                CASE l.stage
                    WHEN 'Disclosed' THEN 1
                    WHEN 'Processing' THEN 2
                    WHEN 'Submitted' THEN 3
                    WHEN 'UW Received' THEN 4
                    WHEN 'Approved' THEN 5
                    WHEN 'Suspended' THEN 6
                    WHEN 'CTC' THEN 7
                    WHEN 'Docs Out' THEN 8
                    ELSE 9
                END
        """

        params = {"lo_id": lo_id} if lo_id else {}
        pipeline_data = execute_query(pipeline_query, params)

        if not pipeline_data:
            return ToolResult.no_data("No active loans in pipeline")

        # Calculate totals
        total_count = sum(row["count"] for row in pipeline_data)
        total_volume = sum(row["total_volume"] or 0 for row in pipeline_data)

        # Get velocity metrics (closings in last N days)
        # Use database-agnostic date calculation for cycle time
        cycle_time_expr = sql_days_since('l.created_at') if is_sqlite() else "EXTRACT(EPOCH FROM (funded_date - created_at)) / 86400"
        velocity_query = f"""
            SELECT
                COUNT(*) as closed_count,
                SUM(amount) as closed_volume,
                AVG({cycle_time_expr}) as avg_cycle_time
            FROM loans l
            WHERE l.stage = 'Funded'
            AND l.funded_date >= {date_threshold}
            {lo_filter}
        """
        velocity_data = execute_single(velocity_query, params)

        # Get at-risk loans (over SLA)
        # Note: Stage values must match LoanStage enum in main.py exactly
        at_risk_query = f"""
            SELECT COUNT(*) as at_risk_count
            FROM loans l
            WHERE l.stage NOT IN ('Funded')
            AND {days_in_stage_expr} >
                CASE l.stage
                    WHEN 'Disclosed' THEN 3
                    WHEN 'Processing' THEN 5
                    WHEN 'Submitted' THEN 2
                    WHEN 'UW Received' THEN 3
                    WHEN 'Approved' THEN 2
                    WHEN 'Suspended' THEN 7
                    WHEN 'CTC' THEN 2
                    WHEN 'Docs Out' THEN 3
                    ELSE 5
                END
            {lo_filter}
        """
        at_risk_data = execute_single(at_risk_query, params)

        # Build response
        stages = []
        for row in pipeline_data:
            sla_target = SLA_TARGETS.get(row["stage"], 5)
            avg_days = row["avg_days_in_stage"] or 0
            health = "healthy" if avg_days <= sla_target else "at_risk" if avg_days <= sla_target * 1.5 else "critical"

            stages.append({
                "stage": row["stage"],
                "count": row["count"],
                "volume": float(row["total_volume"] or 0),
                "volume_formatted": format_currency(row["total_volume"]),
                "avg_loan_size": float(row["avg_loan_size"] or 0),
                "avg_days_in_stage": round(avg_days, 1),
                "sla_target_days": sla_target,
                "health": health,
            })

        return ToolResult.success({
            "summary": {
                "total_loans": total_count,
                "total_volume": float(total_volume),
                "total_volume_formatted": format_currency(total_volume),
                "at_risk_count": at_risk_data["at_risk_count"] if at_risk_data else 0,
                "health_score": round(100 - (at_risk_data["at_risk_count"] / total_count * 100) if total_count > 0 else 100, 1),
            },
            "velocity": {
                "closed_last_30_days": velocity_data["closed_count"] if velocity_data else 0,
                "volume_last_30_days": float(velocity_data["closed_volume"] or 0) if velocity_data else 0,
                "avg_cycle_time_days": round(velocity_data["avg_cycle_time"] or 0, 1) if velocity_data else 0,
            },
            "stages": stages,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get pipeline metrics: {str(e)}")


@mortgage_tool(
    name="get_loans_by_status",
    description="Get list of loans filtered by status/stage with details",
    agent_roles=["pipeline_analyst", "processor", "underwriter", "closer"],
    risk_level="low",
    examples=[
        "Show me all loans in underwriting",
        "What loans are waiting for closing?",
        "List processing loans",
    ],
)
def get_loans_by_status(
    status: str,
    lo_id: Optional[int] = None,
    limit: int = 50,
    include_at_risk_only: bool = False,
) -> ToolResult:
    """Get loans filtered by status."""
    try:
        lo_filter = "AND l.loan_officer_id = :lo_id" if lo_id else ""
        at_risk_filter = ""

        # Database-agnostic date calculation
        days_in_stage_expr = sql_days_since('l.stage_changed_at')

        if include_at_risk_only:
            sla = SLA_TARGETS.get(status.lower(), 5)
            at_risk_filter = f"AND {days_in_stage_expr} > {sla}"

        query = f"""
            SELECT
                l.id,
                l.loan_number,
                l.borrower_name,
                l.amount,
                l.stage,
                l.program,
                l.rate,
                l.stage_changed_at,
                l.closing_date,
                l.loan_officer_id,
                (COALESCE(lo.first_name, '') || ' ' || COALESCE(lo.last_name, '')) as loan_officer_name,
                {days_in_stage_expr} as days_in_stage
            FROM loans l
            LEFT JOIN users lo ON l.loan_officer_id = lo.id
            WHERE LOWER(l.stage) = LOWER(:status)
            {lo_filter}
            {at_risk_filter}
            ORDER BY l.stage_changed_at ASC
            LIMIT :limit
        """

        params = {"status": status, "limit": limit}
        if lo_id:
            params["lo_id"] = lo_id

        loans = execute_query(query, params)

        if not loans:
            return ToolResult.no_data(f"No loans found in {status} status")

        sla_target = SLA_TARGETS.get(status.lower(), 5)

        result_loans = []
        for loan in loans:
            days_in_stage = loan["days_in_stage"] or 0
            is_at_risk = days_in_stage > sla_target

            result_loans.append({
                "id": loan["id"],
                "loan_number": loan["loan_number"],
                "borrower_name": loan["borrower_name"],
                "amount": float(loan["amount"] or 0),
                "amount_formatted": format_currency(loan["amount"]),
                "program": loan["program"],
                "rate": float(loan["rate"]) if loan["rate"] else None,
                "days_in_stage": round(days_in_stage, 1),
                "sla_target": sla_target,
                "is_at_risk": is_at_risk,
                "closing_date": format_date(loan["closing_date"]),
                "loan_officer": loan["loan_officer_name"],
            })

        return ToolResult.success({
            "status": status,
            "count": len(result_loans),
            "at_risk_count": sum(1 for l in result_loans if l["is_at_risk"]),
            "total_volume": sum(l["amount"] for l in result_loans),
            "total_volume_formatted": format_currency(sum(l["amount"] for l in result_loans)),
            "loans": result_loans,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get loans by status: {str(e)}")


@mortgage_tool(
    name="get_loan_aging_report",
    description="Get aging report showing how long loans have been in each stage",
    agent_roles=["pipeline_analyst", "manager"],
    risk_level="low",
    examples=[
        "Show me the aging report",
        "Which loans are stuck?",
        "What's aging in the pipeline?",
    ],
)
def get_loan_aging_report(
    lo_id: Optional[int] = None,
    min_days: int = 0,
) -> ToolResult:
    """Get loan aging analysis."""
    try:
        lo_filter = "AND l.loan_officer_id = :lo_id" if lo_id else ""

        # Database-agnostic date calculations
        days_in_stage_expr = sql_days_since('l.stage_changed_at')
        total_days_open_expr = sql_days_since('l.created_at')

        query = f"""
            SELECT
                l.id,
                l.loan_number,
                l.borrower_name,
                l.amount,
                l.stage,
                l.program,
                l.stage_changed_at,
                l.created_at,
                l.closing_date,
                (COALESCE(lo.first_name, '') || ' ' || COALESCE(lo.last_name, '')) as loan_officer_name,
                {days_in_stage_expr} as days_in_stage,
                {total_days_open_expr} as total_days_open
            FROM loans l
            LEFT JOIN users lo ON l.loan_officer_id = lo.id
            WHERE l.stage NOT IN ('Funded')
            AND {days_in_stage_expr} >= :min_days
            {lo_filter}
            ORDER BY days_in_stage DESC
        """

        params = {"min_days": min_days}
        if lo_id:
            params["lo_id"] = lo_id

        loans = execute_query(query, params)

        if not loans:
            return ToolResult.no_data("No loans found matching criteria")

        # Categorize by aging buckets
        buckets = {
            "on_track": [],      # Within SLA
            "at_risk": [],       # 1-1.5x SLA
            "critical": [],      # >1.5x SLA
        }

        for loan in loans:
            days_in_stage = loan["days_in_stage"] or 0
            sla_target = SLA_TARGETS.get(loan["stage"], 5)

            loan_data = {
                "id": loan["id"],
                "loan_number": loan["loan_number"],
                "borrower_name": loan["borrower_name"],
                "amount_formatted": format_currency(loan["amount"]),
                "stage": loan["stage"],
                "days_in_stage": round(days_in_stage, 1),
                "sla_target": sla_target,
                "sla_variance": round(days_in_stage - sla_target, 1),
                "total_days_open": round(loan["total_days_open"] or 0, 1),
                "closing_date": format_date(loan["closing_date"]),
                "loan_officer": loan["loan_officer_name"],
            }

            if days_in_stage <= sla_target:
                buckets["on_track"].append(loan_data)
            elif days_in_stage <= sla_target * 1.5:
                buckets["at_risk"].append(loan_data)
            else:
                buckets["critical"].append(loan_data)

        return ToolResult.success({
            "summary": {
                "total_loans": len(loans),
                "on_track": len(buckets["on_track"]),
                "at_risk": len(buckets["at_risk"]),
                "critical": len(buckets["critical"]),
            },
            "critical_loans": buckets["critical"][:10],  # Top 10 most aged
            "at_risk_loans": buckets["at_risk"][:10],
            "on_track_loans": buckets["on_track"][:5],
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get aging report: {str(e)}")


@mortgage_tool(
    name="calculate_conversion_rates",
    description="Calculate conversion rates between pipeline stages",
    agent_roles=["pipeline_analyst", "manager", "executive"],
    risk_level="low",
    examples=[
        "What are our conversion rates?",
        "Show me funnel conversion",
        "How many leads convert to applications?",
    ],
)
def calculate_conversion_rates(
    lo_id: Optional[int] = None,
    days_back: int = 90,
) -> ToolResult:
    """Calculate stage-to-stage conversion rates."""
    try:
        lo_filter = "AND loan_officer_id = :lo_id" if lo_id else ""

        # Database-agnostic date calculation
        date_threshold = sql_date_subtract(days_back)

        # Get counts for each outcome
        query = f"""
            SELECT
                stage,
                COUNT(*) as count
            FROM loans
            WHERE created_at >= {date_threshold}
            {lo_filter}
            GROUP BY stage
        """

        params = {"lo_id": lo_id} if lo_id else {}
        stage_counts = execute_query(query, params)

        if not stage_counts:
            return ToolResult.no_data("No loan data found for conversion analysis")

        # Build counts dict
        counts = {row["stage"]: row["count"] for row in stage_counts}

        # Calculate funnel conversions
        # Note: Stage values must match LoanStage enum in main.py exactly
        stages = get_loan_stage_order()
        active_stages = ["Disclosed", "Processing", "Submitted", "UW Received", "Approved", "Suspended", "CTC", "Docs Out"]
        funded_count = counts.get("Funded", 0)
        fallen_out = 0  # No fallout stages in current LoanStage enum

        total_started = sum(counts.values())
        total_active = sum(counts.get(s, 0) for s in active_stages)

        conversions = []
        prev_count = total_started

        for stage in active_stages:
            try:
                stage_idx = stages.index(stage)
                current_count = sum(counts.get(s, 0) for s in stages[stage_idx:])
            except ValueError:
                current_count = 0
            if current_count == 0:
                # Include funded in downstream counts
                current_count = funded_count

            rate = (current_count / prev_count * 100) if prev_count > 0 else 0
            conversions.append({
                "stage": stage,
                "reached": current_count,
                "conversion_rate": round(rate, 1),
            })
            prev_count = current_count

        # Overall pull-through
        pull_through = (funded_count / total_started * 100) if total_started > 0 else 0
        fallout_rate = (fallen_out / total_started * 100) if total_started > 0 else 0

        return ToolResult.success({
            "period_days": days_back,
            "summary": {
                "total_loans_started": total_started,
                "currently_active": total_active,
                "funded_closed": funded_count,
                "fallen_out": fallen_out,
                "pull_through_rate": round(pull_through, 1),
                "fallout_rate": round(fallout_rate, 1),
            },
            "stage_conversions": conversions,
            "raw_counts": counts,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to calculate conversion rates: {str(e)}")


@mortgage_tool(
    name="predict_closing_timeline",
    description="Predict when loans will close based on historical data and current stage",
    agent_roles=["pipeline_analyst", "closer", "manager"],
    risk_level="low",
    examples=[
        "When will this loan close?",
        "Predict closing dates for the pipeline",
        "What's the expected close date?",
    ],
)
def predict_closing_timeline(
    loan_id: Optional[int] = None,
    stage: Optional[str] = None,
) -> ToolResult:
    """Predict closing timeline for loans."""
    try:
        # Get historical average times per stage
        # Note: loan_stage_history table may not exist, so we use SLA_TARGETS as default
        avg_times = {}
        try:
            # Database-agnostic date calculation
            days_since_change_expr = sql_days_since('changed_at')
            avg_times_query = f"""
                SELECT
                    to_stage as stage,
                    AVG({days_since_change_expr}) as avg_days
                FROM stage_history
                WHERE entity_type = 'loan'
                GROUP BY to_stage
            """
            avg_times_result = execute_query(avg_times_query)
            avg_times = {row["stage"]: row["avg_days"] or SLA_TARGETS.get(row["stage"], 3) for row in avg_times_result}
        except Exception as e:
            # Table may not exist, use defaults
            logger.warning(f"Error querying stage_history for avg times: {e}")

        # Fill in defaults for missing stages
        for stage_name, sla in SLA_TARGETS.items():
            if stage_name not in avg_times:
                avg_times[stage_name] = sla

        if loan_id:
            # Predict for specific loan
            loan_query = """
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.stage_changed_at, l.closing_date, l.amount
                FROM loans l
                WHERE l.id = :loan_id
            """
            loan = execute_single(loan_query, {"loan_id": loan_id})

            if not loan:
                return ToolResult.no_data(f"Loan {loan_id} not found")

            current_stage = loan["stage"]
            stages = get_loan_stage_order()

            if current_stage == "Funded":
                return ToolResult.success({
                    "loan_id": loan_id,
                    "status": "complete",
                    "message": f"Loan is already {current_stage}",
                })

            # Calculate remaining days
            try:
                current_idx = stages.index(current_stage)
                funded_idx = stages.index("Funded")
                remaining_stages = stages[current_idx:funded_idx]
            except ValueError:
                remaining_stages = []
            days_in_current = days_between(loan["stage_changed_at"])
            remaining_in_current = max(0, avg_times.get(current_stage, 3) - days_in_current)

            remaining_days = remaining_in_current + sum(avg_times.get(s, 3) for s in remaining_stages[1:])
            predicted_close = add_business_days(datetime.now().date(), int(remaining_days))

            return ToolResult.success({
                "loan_id": loan_id,
                "loan_number": loan["loan_number"],
                "borrower_name": loan["borrower_name"],
                "current_stage": current_stage,
                "days_in_current_stage": days_in_current,
                "remaining_stages": remaining_stages,
                "predicted_days_to_close": round(remaining_days, 1),
                "predicted_close_date": format_date(predicted_close),
                "closing_date": format_date(loan["closing_date"]),
                "on_track": predicted_close <= loan["closing_date"] if loan["closing_date"] else True,
            })

        elif stage:
            # Predict for all loans in a stage
            loans_query = """
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.stage_changed_at, l.closing_date, l.amount
                FROM loans l
                WHERE LOWER(l.stage) = LOWER(:stage)
            """
            loans = execute_query(loans_query, {"stage": stage})

            if not loans:
                return ToolResult.no_data(f"No loans in {stage} stage")

            stages = get_loan_stage_order()
            predictions = []

            for loan in loans:
                current_stage = loan["stage"]
                if current_stage == "Funded":
                    continue

                try:
                    current_idx = stages.index(current_stage)
                    funded_idx = stages.index("Funded")
                    remaining_stages = stages[current_idx:funded_idx]
                except ValueError:
                    continue
                days_in_current = days_between(loan["stage_changed_at"])
                remaining_in_current = max(0, avg_times.get(current_stage, 3) - days_in_current)
                remaining_days = remaining_in_current + sum(avg_times.get(s, 3) for s in remaining_stages[1:])
                predicted_close = add_business_days(datetime.now().date(), int(remaining_days))

                predictions.append({
                    "loan_id": loan["id"],
                    "loan_number": loan["loan_number"],
                    "borrower_name": loan["borrower_name"],
                    "predicted_close_date": format_date(predicted_close),
                    "predicted_days": round(remaining_days, 1),
                    "on_track": predicted_close <= loan["closing_date"] if loan["closing_date"] else True,
                })

            return ToolResult.success({
                "stage": stage,
                "count": len(predictions),
                "predictions": predictions,
                "avg_stage_times": avg_times,
            })

        else:
            return ToolResult.error("Must provide either loan_id or stage parameter")

    except Exception as e:
        return ToolResult.error(f"Failed to predict closing timeline: {str(e)}")


@mortgage_tool(
    name="get_bottleneck_analysis",
    description="Identify bottlenecks and slowdowns in the pipeline",
    agent_roles=["pipeline_analyst", "manager", "executive"],
    risk_level="low",
    examples=[
        "Where are loans getting stuck?",
        "What's causing delays?",
        "Show me pipeline bottlenecks",
    ],
)
def get_bottleneck_analysis(
    days_back: int = 30,
    lo_id: Optional[int] = None,
) -> ToolResult:
    """Analyze pipeline bottlenecks."""
    try:
        lo_filter = "AND l.loan_officer_id = :lo_id" if lo_id else ""

        # Database-agnostic date calculation
        days_in_stage_expr = sql_days_since('l.stage_changed_at')

        # Get average time in each stage vs SLA
        # Note: Stage values must match LoanStage enum in main.py exactly
        stage_analysis_query = f"""
            SELECT
                l.stage,
                COUNT(*) as loan_count,
                SUM(l.amount) as total_volume,
                AVG({days_in_stage_expr}) as avg_days_in_stage,
                MAX({days_in_stage_expr}) as max_days_in_stage,
                COUNT(CASE WHEN {days_in_stage_expr} >
                    CASE l.stage
                        WHEN 'Disclosed' THEN 3
                        WHEN 'Processing' THEN 5
                        WHEN 'Submitted' THEN 2
                        WHEN 'UW Received' THEN 3
                        WHEN 'Approved' THEN 2
                        WHEN 'Suspended' THEN 7
                        WHEN 'CTC' THEN 2
                        WHEN 'Docs Out' THEN 3
                        ELSE 5
                    END THEN 1 END) as over_sla_count
            FROM loans l
            WHERE l.stage NOT IN ('Funded')
            {lo_filter}
            GROUP BY l.stage
        """

        params = {"lo_id": lo_id} if lo_id else {}
        stage_data = execute_query(stage_analysis_query, params)

        if not stage_data:
            return ToolResult.no_data("No active loans for bottleneck analysis")

        # Analyze each stage
        bottlenecks = []
        for row in stage_data:
            stage = row["stage"]
            sla_target = SLA_TARGETS.get(stage, 5)
            avg_days = row["avg_days_in_stage"] or 0
            over_sla_pct = (row["over_sla_count"] / row["loan_count"] * 100) if row["loan_count"] > 0 else 0

            severity = "low"
            if over_sla_pct > 50:
                severity = "critical"
            elif over_sla_pct > 25:
                severity = "high"
            elif over_sla_pct > 10:
                severity = "medium"

            bottlenecks.append({
                "stage": stage,
                "loan_count": row["loan_count"],
                "volume": float(row["total_volume"] or 0),
                "volume_formatted": format_currency(row["total_volume"]),
                "avg_days_in_stage": round(avg_days, 1),
                "max_days_in_stage": round(row["max_days_in_stage"] or 0, 1),
                "sla_target_days": sla_target,
                "over_sla_count": row["over_sla_count"],
                "over_sla_percentage": round(over_sla_pct, 1),
                "severity": severity,
                "recommendation": _get_bottleneck_recommendation(stage, over_sla_pct, avg_days, sla_target),
            })

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        bottlenecks.sort(key=lambda x: severity_order[x["severity"]])

        critical_stages = [b for b in bottlenecks if b["severity"] == "critical"]
        high_risk_stages = [b for b in bottlenecks if b["severity"] == "high"]

        return ToolResult.success({
            "summary": {
                "total_active_loans": sum(b["loan_count"] for b in bottlenecks),
                "critical_bottlenecks": len(critical_stages),
                "high_risk_bottlenecks": len(high_risk_stages),
                "primary_bottleneck": bottlenecks[0]["stage"] if bottlenecks else None,
            },
            "bottlenecks": bottlenecks,
            "critical_stages": critical_stages,
            "recommendations": [b["recommendation"] for b in bottlenecks if b["severity"] in ["critical", "high"]],
        })

    except Exception as e:
        return ToolResult.error(f"Failed to analyze bottlenecks: {str(e)}")


def _get_bottleneck_recommendation(stage: str, over_sla_pct: float, avg_days: float, sla: int) -> str:
    """Generate recommendation for bottleneck."""
    if over_sla_pct < 10:
        return f"{stage.title()} is performing well within SLA"

    # Note: Stage values must match LoanStage enum in main.py exactly
    recommendations = {
        "Disclosed": "Ensure timely processing of initial disclosures",
        "Processing": "Consider adding processing capacity or automating document collection",
        "Submitted": "Follow up with underwriting on submission queue priority",
        "UW Received": "Review underwriter workload distribution; consider condition delegation",
        "Approved": "Move approved loans to CTC quickly",
        "Suspended": "Prioritize clearing suspended conditions",
        "CTC": "Streamline CD preparation and closing coordination",
        "Docs Out": "Improve title/settlement coordination and funding procedures",
    }

    base_rec = recommendations.get(stage, f"Review {stage} process for efficiency improvements")

    if over_sla_pct > 50:
        return f"CRITICAL: {base_rec}. {int(over_sla_pct)}% of loans over SLA."
    elif over_sla_pct > 25:
        return f"HIGH PRIORITY: {base_rec}. {int(over_sla_pct)}% of loans over SLA."
    else:
        return f"{base_rec}. Monitor closely - {int(over_sla_pct)}% over SLA."


@mortgage_tool(
    name="compare_to_benchmark",
    description="Compare pipeline metrics to industry benchmarks",
    agent_roles=["pipeline_analyst", "manager", "executive"],
    risk_level="low",
    examples=[
        "How do we compare to industry benchmarks?",
        "Are we meeting industry standards?",
        "Benchmark our performance",
    ],
)
def compare_to_benchmark(
    lo_id: Optional[int] = None,
    days_back: int = 30,
) -> ToolResult:
    """Compare pipeline metrics to industry benchmarks."""
    try:
        # Industry benchmarks
        benchmarks = {
            "avg_cycle_time_days": 35,
            "pull_through_rate": 75,
            "processing_time_days": 3,
            "underwriting_time_days": 3,
            "application_to_close_days": 30,
            "fallout_rate": 20,
        }

        lo_filter = "AND loan_officer_id = :lo_id" if lo_id else ""
        params = {"lo_id": lo_id} if lo_id else {}

        # Database-agnostic date calculations
        date_threshold = sql_date_subtract(days_back)

        # For cycle time, we need to calculate days between two columns
        if is_sqlite():
            cycle_time_expr = "(julianday(funded_date) - julianday(created_at))"
            cast_float = ""  # SQLite doesn't need explicit cast
        else:
            cycle_time_expr = "EXTRACT(EPOCH FROM (funded_date - created_at)) / 86400"
            cast_float = "::float"

        # Get our metrics
        # Note: Stage values must match LoanStage enum in main.py exactly
        metrics_query = f"""
            SELECT
                AVG({cycle_time_expr}) as avg_cycle_time,
                CAST(COUNT(CASE WHEN stage = 'Funded' THEN 1 END) AS REAL) /
                    NULLIF(COUNT(*), 0) * 100 as pull_through_rate,
                0.0 as fallout_rate
            FROM loans
            WHERE created_at >= {date_threshold}
            {lo_filter}
        """
        metrics = execute_single(metrics_query, params)

        # Get stage-specific times
        # Note: Using stage_history table with graceful fallback
        stage_time_dict = {}
        try:
            days_since_change_expr = sql_days_since('changed_at')
            stage_times_query = f"""
                SELECT
                    to_stage as stage,
                    AVG({days_since_change_expr}) as avg_days
                FROM stage_history
                WHERE entity_type = 'loan'
                AND changed_at >= {date_threshold}
                GROUP BY to_stage
            """
            stage_times = execute_query(stage_times_query, params)
            stage_time_dict = {row["stage"]: row["avg_days"] for row in stage_times}
        except Exception as e:
            # Table may not exist, use empty dict (will fall back to defaults below)
            logger.warning(f"Error querying stage_history for benchmark times: {e}")

        comparisons = []

        # Cycle time
        our_cycle = metrics["avg_cycle_time"] or 0 if metrics else 0
        comparisons.append({
            "metric": "Average Cycle Time",
            "our_value": round(our_cycle, 1),
            "benchmark": benchmarks["avg_cycle_time_days"],
            "unit": "days",
            "variance": round(our_cycle - benchmarks["avg_cycle_time_days"], 1),
            "status": "better" if our_cycle < benchmarks["avg_cycle_time_days"] else "worse",
        })

        # Pull-through rate
        our_pull_through = metrics["pull_through_rate"] or 0 if metrics else 0
        comparisons.append({
            "metric": "Pull-Through Rate",
            "our_value": round(our_pull_through, 1),
            "benchmark": benchmarks["pull_through_rate"],
            "unit": "%",
            "variance": round(our_pull_through - benchmarks["pull_through_rate"], 1),
            "status": "better" if our_pull_through > benchmarks["pull_through_rate"] else "worse",
        })

        # Fallout rate
        our_fallout = metrics["fallout_rate"] or 0 if metrics else 0
        comparisons.append({
            "metric": "Fallout Rate",
            "our_value": round(our_fallout, 1),
            "benchmark": benchmarks["fallout_rate"],
            "unit": "%",
            "variance": round(our_fallout - benchmarks["fallout_rate"], 1),
            "status": "better" if our_fallout < benchmarks["fallout_rate"] else "worse",
        })

        # Processing time
        our_processing = stage_time_dict.get("processing", 0)
        comparisons.append({
            "metric": "Processing Time",
            "our_value": round(our_processing, 1),
            "benchmark": benchmarks["processing_time_days"],
            "unit": "days",
            "variance": round(our_processing - benchmarks["processing_time_days"], 1),
            "status": "better" if our_processing < benchmarks["processing_time_days"] else "worse",
        })

        # Calculate overall score
        better_count = sum(1 for c in comparisons if c["status"] == "better")
        overall_score = (better_count / len(comparisons)) * 100

        return ToolResult.success({
            "period_days": days_back,
            "overall_score": round(overall_score, 1),
            "metrics_above_benchmark": better_count,
            "total_metrics": len(comparisons),
            "comparisons": comparisons,
            "benchmarks_used": benchmarks,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to compare to benchmarks: {str(e)}")


@mortgage_tool(
    name="get_lo_pipeline_breakdown",
    description="Get pipeline breakdown by loan officer",
    agent_roles=["pipeline_analyst", "manager"],
    risk_level="low",
    examples=[
        "Show me each LO's pipeline",
        "Pipeline by loan officer",
        "Who has the most loans in their pipeline?",
    ],
)
def get_lo_pipeline_breakdown(
    include_metrics: bool = True,
) -> ToolResult:
    """Get pipeline breakdown by loan officer."""
    try:
        # Database-agnostic date calculation
        days_in_stage_expr = sql_days_since('l.stage_changed_at')

        # Note: Stage values must match LoanStage enum in main.py exactly
        query = f"""
            SELECT
                lo.id as lo_id,
                (COALESCE(lo.first_name, '') || ' ' || COALESCE(lo.last_name, '')) as lo_name,
                lo.email as lo_email,
                COUNT(l.id) as total_loans,
                SUM(l.amount) as total_volume,
                COUNT(CASE WHEN l.stage IN ('Disclosed', 'Processing') THEN 1 END) as early_stage,
                COUNT(CASE WHEN l.stage IN ('Submitted', 'UW Received', 'Approved', 'Suspended') THEN 1 END) as mid_stage,
                COUNT(CASE WHEN l.stage IN ('CTC', 'Docs Out') THEN 1 END) as late_stage,
                AVG({days_in_stage_expr}) as avg_days_in_stage
            FROM users lo
            LEFT JOIN loans l ON lo.id = l.loan_officer_id
                AND l.stage NOT IN ('Funded')
            WHERE lo.role = 'loan_officer' OR EXISTS (SELECT 1 FROM loans WHERE loan_officer_id = lo.id)
            GROUP BY lo.id, lo.first_name, lo.last_name, lo.email
            ORDER BY total_volume DESC NULLS LAST
        """

        lo_data = execute_query(query)

        if not lo_data:
            return ToolResult.no_data("No loan officer data found")

        # Database-agnostic expressions for metrics
        date_30_days_ago = sql_date_subtract(30)
        if is_sqlite():
            cycle_time_expr = "(julianday(funded_date) - julianday(created_at))"
        else:
            cycle_time_expr = "EXTRACT(EPOCH FROM (funded_date - created_at)) / 86400"

        results = []
        for row in lo_data:
            lo_result = {
                "lo_id": row["lo_id"],
                "lo_name": row["lo_name"],
                "lo_email": row["lo_email"],
                "total_loans": row["total_loans"] or 0,
                "total_volume": float(row["total_volume"] or 0),
                "total_volume_formatted": format_currency(row["total_volume"]),
                "pipeline_breakdown": {
                    "early_stage": row["early_stage"] or 0,
                    "mid_stage": row["mid_stage"] or 0,
                    "late_stage": row["late_stage"] or 0,
                },
                "avg_days_in_stage": round(row["avg_days_in_stage"] or 0, 1),
            }

            if include_metrics and row["total_loans"]:
                # Get additional metrics for this LO
                # Note: Stage values must match LoanStage enum in main.py exactly
                metrics_query = f"""
                    SELECT
                        COUNT(CASE WHEN stage = 'Funded' AND funded_date >= {date_30_days_ago} THEN 1 END) as closed_30d,
                        AVG(CASE WHEN stage = 'Funded' THEN {cycle_time_expr} END) as avg_cycle_time
                    FROM loans
                    WHERE loan_officer_id = :lo_id
                """
                metrics = execute_single(metrics_query, {"lo_id": row["lo_id"]})

                if metrics:
                    lo_result["performance"] = {
                        "closed_last_30_days": metrics["closed_30d"] or 0,
                        "avg_cycle_time_days": round(metrics["avg_cycle_time"] or 0, 1),
                    }

            results.append(lo_result)

        # Calculate team totals
        team_totals = {
            "total_loans": sum(r["total_loans"] for r in results),
            "total_volume": sum(r["total_volume"] for r in results),
            "total_volume_formatted": format_currency(sum(r["total_volume"] for r in results)),
            "lo_count": len([r for r in results if r["total_loans"] > 0]),
        }

        return ToolResult.success({
            "team_summary": team_totals,
            "loan_officers": results,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get LO pipeline breakdown: {str(e)}")


@mortgage_tool(
    name="update_loan_fields",
    description="Update one or more fields on a loan record. Supports all fields: stage, loan_type, program, amount, rate, term, purchase_price, down_payment, property info, team assignments (processor, underwriter, closer, realtor, title company, lender), key dates (closing, lock, lock_expiration), rate lock status, monthly payment, LTV, CLTV, loan_purpose, borrower info, and notes.",
    agent_roles=["pipeline_analyst", "manager", "sales", "voice_os", "ai_receptionist"],
    risk_level="medium",
    requires_confirmation=True,
    examples=[
        "Move this loan to CTC",
        "Update the closing date",
        "Change the rate to 6.5%",
        "Assign the processor",
        "Update the loan amount",
    ],
)
def update_loan_fields(
    loan_id: int,
    stage: Optional[str] = None,
    loan_type: Optional[str] = None,
    program: Optional[str] = None,
    amount: Optional[float] = None,
    purchase_price: Optional[float] = None,
    down_payment: Optional[float] = None,
    rate: Optional[float] = None,
    term: Optional[int] = None,
    property_address: Optional[str] = None,
    property_city: Optional[str] = None,
    property_state: Optional[str] = None,
    property_zip: Optional[str] = None,
    property_type: Optional[str] = None,
    occupancy_type: Optional[str] = None,
    borrower_name: Optional[str] = None,
    borrower_email: Optional[str] = None,
    borrower_phone: Optional[str] = None,
    processor: Optional[str] = None,
    underwriter: Optional[str] = None,
    closer: Optional[str] = None,
    realtor_agent: Optional[str] = None,
    title_company: Optional[str] = None,
    lender: Optional[str] = None,
    loan_purpose: Optional[str] = None,
    closing_date: Optional[str] = None,
    lock_expiration_date: Optional[str] = None,
    rate_lock_status: Optional[str] = None,
    monthly_payment: Optional[float] = None,
    ltv: Optional[float] = None,
    cltv: Optional[float] = None,
    loan_number: Optional[str] = None,
    notes: Optional[str] = None,
) -> ToolResult:
    """Update any combination of fields on a loan record."""
    try:
        from sqlalchemy import text

        loan_check = execute_single(
            "SELECT id, borrower_name, loan_number, stage FROM loans WHERE id = :loan_id",
            {"loan_id": loan_id}
        )
        if not loan_check:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        updates = {}
        if stage is not None:
            updates["stage"] = stage.upper()
        if loan_type is not None:
            updates["loan_type"] = loan_type
        if program is not None:
            updates["program"] = program
        if amount is not None:
            updates["amount"] = amount
        if purchase_price is not None:
            updates["purchase_price"] = purchase_price
        if down_payment is not None:
            updates["down_payment"] = down_payment
        if rate is not None:
            updates["rate"] = rate
        if term is not None:
            updates["term"] = term
        if property_address is not None:
            updates["property_address"] = property_address
        if property_city is not None:
            updates["property_city"] = property_city
        if property_state is not None:
            updates["property_state"] = property_state
        if property_zip is not None:
            updates["property_zip"] = property_zip
        if property_type is not None:
            updates["property_type"] = property_type
        if occupancy_type is not None:
            updates["occupancy_type"] = occupancy_type
        if borrower_name is not None:
            updates["borrower_name"] = borrower_name
        if borrower_email is not None:
            updates["borrower_email"] = borrower_email
        if borrower_phone is not None:
            updates["borrower_phone"] = borrower_phone
        if processor is not None:
            updates["processor"] = processor
        if underwriter is not None:
            updates["underwriter"] = underwriter
        if closer is not None:
            updates["closer"] = closer
        if realtor_agent is not None:
            updates["realtor_agent"] = realtor_agent
        if title_company is not None:
            updates["title_company"] = title_company
        if lender is not None:
            updates["lender"] = lender
        if loan_purpose is not None:
            updates["loan_purpose"] = loan_purpose
        if closing_date is not None:
            updates["closing_date"] = closing_date
        if lock_expiration_date is not None:
            updates["lock_expiration_date"] = lock_expiration_date
        if rate_lock_status is not None:
            updates["rate_lock_status"] = rate_lock_status
        if monthly_payment is not None:
            updates["monthly_payment"] = monthly_payment
        if ltv is not None:
            updates["ltv"] = ltv
        if cltv is not None:
            updates["cltv"] = cltv
        if loan_number is not None:
            updates["loan_number"] = loan_number

        if not updates and not notes:
            return ToolResult.error("No fields provided to update")

        set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
        updates["loan_id"] = loan_id

        if notes:
            if set_clauses:
                set_clauses += ", "
            set_clauses += "ai_insights = COALESCE(ai_insights, '') || E'\\n' || :notes"
            updates["notes"] = notes

        with get_db() as db:
            db.execute(
                text(f"UPDATE loans SET {set_clauses}, updated_at = NOW() WHERE id = :loan_id"),
                updates,
            )

        return ToolResult.success({
            "loan_id": loan_id,
            "borrower_name": loan_check["borrower_name"],
            "loan_number": loan_check["loan_number"],
            "fields_updated": [k for k in updates.keys() if k != "loan_id"],
            "updated": True,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to update loan: {str(e)}")


# Valid loan stages (uppercase, matching database convention)
VALID_LOAN_STAGES = frozenset({
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
    "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
    "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
    "CANCELLED", "DENIED", "DEAD", "WITHDRAWN",
    "DOES_NOT_QUALIFY", "NURTURE",
})


@mortgage_tool(
    name="update_loan_stage",
    description="Move a loan to a new pipeline stage with optional reason",
    agent_roles=["pipeline_analyst", "ops_manager", "closer", "processor"],
    risk_level="HIGH",
    requires_confirmation=True,
    examples=[
        "Move this loan to underwriting",
        "Advance loan to CTC",
        "Update loan stage to FUNDED",
    ],
)
def update_loan_stage(
    loan_id: int,
    new_stage: str,
    reason: Optional[str] = None,
    **kwargs,
) -> ToolResult:
    """Move a loan to a new pipeline stage."""
    try:
        from database.models.lead_loan import Loan

        db = kwargs.get("db")
        current_user = kwargs.get("current_user")

        if not db or not current_user:
            return ToolResult.error("Missing db session or current_user context")

        # Validate stage
        normalized_stage = new_stage.strip().upper()
        if normalized_stage not in VALID_LOAN_STAGES:
            return ToolResult.error(
                f"Invalid stage '{new_stage}'. Valid stages: {', '.join(sorted(VALID_LOAN_STAGES))}"
            )

        loan = db.query(Loan).filter(
            Loan.id == loan_id,
            Loan.organization_id == current_user.organization_id,
        ).first()

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found in your organization")

        previous_stage = loan.stage
        loan.stage = normalized_stage
        loan.stage_changed_at = datetime.now()

        # Append reason to ai_insights if provided
        if reason:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            stage_note = f"\n[{timestamp}] Stage changed {previous_stage} -> {normalized_stage}: {reason}"
            loan.ai_insights = (loan.ai_insights or "") + stage_note

        db.flush()

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "previous_stage": previous_stage,
            "new_stage": normalized_stage,
            "reason": reason,
            "updated": True,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to update loan stage: {str(e)}")


@mortgage_tool(
    name="add_loan_note",
    description="Add a timestamped note to a loan record",
    agent_roles=["pipeline_analyst", "processor", "closer", "underwriter", "borrower_concierge"],
    risk_level="LOW",
    requires_confirmation=False,
    examples=[
        "Add a note to this loan",
        "Log a comment on the loan file",
        "Record underwriting feedback",
    ],
)
def add_loan_note(
    loan_id: int,
    note_text: str,
    **kwargs,
) -> ToolResult:
    """Add a timestamped note to a loan's ai_insights field."""
    try:
        from database.models.lead_loan import Loan

        db = kwargs.get("db")
        current_user = kwargs.get("current_user")

        if not db or not current_user:
            return ToolResult.error("Missing db session or current_user context")

        if not note_text or not note_text.strip():
            return ToolResult.error("Note text cannot be empty")

        loan = db.query(Loan).filter(
            Loan.id == loan_id,
            Loan.organization_id == current_user.organization_id,
        ).first()

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found in your organization")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        formatted_note = f"\n[{timestamp}] {note_text.strip()}"

        loan.ai_insights = (loan.ai_insights or "") + formatted_note
        db.flush()

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "note_added": True,
            "note_preview": note_text.strip()[:100],
        })

    except Exception as e:
        return ToolResult.error(f"Failed to add loan note: {str(e)}")


@mortgage_tool(
    name="update_borrower_contact_info",
    description="Update borrower contact details (email, phone, name) on a loan",
    agent_roles=["pipeline_analyst", "borrower_concierge", "processor"],
    risk_level="MEDIUM",
    requires_confirmation=True,
    examples=[
        "Update borrower email on this loan",
        "Change borrower phone number",
        "Update borrower contact info",
    ],
)
def update_borrower_contact_info(
    loan_id: int,
    borrower_email: Optional[str] = None,
    borrower_phone: Optional[str] = None,
    borrower_name: Optional[str] = None,
    **kwargs,
) -> ToolResult:
    """Update borrower contact details on a loan."""
    try:
        from database.models.lead_loan import Loan

        db = kwargs.get("db")
        current_user = kwargs.get("current_user")

        if not db or not current_user:
            return ToolResult.error("Missing db session or current_user context")

        if not borrower_email and not borrower_phone and not borrower_name:
            return ToolResult.error("At least one field (borrower_email, borrower_phone, or borrower_name) is required")

        loan = db.query(Loan).filter(
            Loan.id == loan_id,
            Loan.organization_id == current_user.organization_id,
        ).first()

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found in your organization")

        updated_fields = []

        if borrower_email is not None:
            loan.borrower_email = borrower_email
            updated_fields.append("borrower_email")

        if borrower_phone is not None:
            loan.borrower_phone = borrower_phone
            updated_fields.append("borrower_phone")

        if borrower_name is not None:
            loan.borrower_name = borrower_name
            updated_fields.append("borrower_name")

        db.flush()

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "fields_updated": updated_fields,
            "updated": True,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to update borrower contact info: {str(e)}")
