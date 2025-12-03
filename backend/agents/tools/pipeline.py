"""
Perennia AI - Pipeline Analysis Tools
Tools for the Pipeline Analyst agent to track and analyze loan pipeline metrics.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
    LoanStatus, SLA_TARGETS, get_loan_stage_order, is_loan_active,
    add_business_days,
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

        # Get pipeline summary by stage
        pipeline_query = f"""
            SELECT
                l.stage,
                COUNT(*) as count,
                SUM(l.amount) as total_volume,
                AVG(l.amount) as avg_loan_size,
                AVG(EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400) as avg_days_in_stage
            FROM loans l
            WHERE l.stage NOT IN ('funded', 'closed', 'denied', 'withdrawn', 'cancelled')
            {lo_filter}
            GROUP BY l.stage
            ORDER BY
                CASE l.stage
                    WHEN 'application' THEN 1
                    WHEN 'processing' THEN 2
                    WHEN 'submitted' THEN 3
                    WHEN 'underwriting' THEN 4
                    WHEN 'conditional' THEN 5
                    WHEN 'clear_to_close' THEN 6
                    WHEN 'closing' THEN 7
                    ELSE 8
                END
        """

        params = {"lo_id": lo_id} if lo_id else {}
        pipeline_data = execute_query(pipeline_query, params)

        if not pipeline_data:
            return ToolResult.no_data("No active loans in pipeline")

        # Calculate totals
        total_count = sum(row["count"] for row in pipeline_data)
        total_volume = sum(row["total_volume"] or 0 for row in pipeline_data)

        # Get velocity metrics (closings in last 30 days)
        velocity_query = f"""
            SELECT
                COUNT(*) as closed_count,
                SUM(amount) as closed_volume,
                AVG(EXTRACT(EPOCH FROM (funded_at - created_at)) / 86400) as avg_cycle_time
            FROM loans l
            WHERE l.stage IN ('funded', 'closed')
            AND l.funded_at >= NOW() - INTERVAL '{days_back} days'
            {lo_filter}
        """
        velocity_data = execute_single(velocity_query, params)

        # Get at-risk loans (over SLA)
        at_risk_query = f"""
            SELECT COUNT(*) as at_risk_count
            FROM loans l
            WHERE l.stage NOT IN ('funded', 'closed', 'denied', 'withdrawn', 'cancelled')
            AND EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400 >
                CASE l.stage
                    WHEN 'application' THEN 1
                    WHEN 'processing' THEN 3
                    WHEN 'submitted' THEN 2
                    WHEN 'underwriting' THEN 3
                    WHEN 'conditional' THEN 5
                    WHEN 'clear_to_close' THEN 2
                    WHEN 'closing' THEN 3
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

        if include_at_risk_only:
            sla = SLA_TARGETS.get(status.lower(), 5)
            at_risk_filter = f"AND EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400 > {sla}"

        query = f"""
            SELECT
                l.id,
                l.loan_number,
                l.borrower_name,
                l.amount,
                l.stage,
                l.program,
                l.rate,
                l.stage_entered_at,
                l.target_close_date,
                l.loan_officer_id,
                lo.name as loan_officer_name,
                EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400 as days_in_stage
            FROM loans l
            LEFT JOIN loan_officers lo ON l.loan_officer_id = lo.id
            WHERE LOWER(l.stage) = LOWER(:status)
            {lo_filter}
            {at_risk_filter}
            ORDER BY l.stage_entered_at ASC
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
                "target_close_date": format_date(loan["target_close_date"]),
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

        query = f"""
            SELECT
                l.id,
                l.loan_number,
                l.borrower_name,
                l.amount,
                l.stage,
                l.program,
                l.stage_entered_at,
                l.created_at,
                l.target_close_date,
                lo.name as loan_officer_name,
                EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400 as days_in_stage,
                EXTRACT(EPOCH FROM (NOW() - l.created_at)) / 86400 as total_days_open
            FROM loans l
            LEFT JOIN loan_officers lo ON l.loan_officer_id = lo.id
            WHERE l.stage NOT IN ('funded', 'closed', 'denied', 'withdrawn', 'cancelled')
            AND EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400 >= :min_days
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
                "target_close_date": format_date(loan["target_close_date"]),
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

        # Get counts for each outcome
        query = f"""
            SELECT
                stage,
                COUNT(*) as count
            FROM loans
            WHERE created_at >= NOW() - INTERVAL '{days_back} days'
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
        stages = get_loan_stage_order()
        active_stages = ["application", "processing", "submitted", "underwriting", "conditional", "clear_to_close", "closing"]
        funded_count = counts.get("funded", 0) + counts.get("closed", 0)
        fallen_out = counts.get("denied", 0) + counts.get("withdrawn", 0) + counts.get("cancelled", 0)

        total_started = sum(counts.values())
        total_active = sum(counts.get(s, 0) for s in active_stages)

        conversions = []
        prev_count = total_started

        for stage in active_stages:
            current_count = sum(counts.get(s, 0) for s in stages[stages.index(stage):] if s not in ["denied", "withdrawn", "cancelled"])
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
        avg_times_query = """
            SELECT
                stage,
                AVG(EXTRACT(EPOCH FROM (stage_exited_at - stage_entered_at)) / 86400) as avg_days
            FROM loan_stage_history
            WHERE stage_exited_at IS NOT NULL
            AND EXTRACT(EPOCH FROM (stage_exited_at - stage_entered_at)) / 86400 < 30
            GROUP BY stage
        """
        avg_times_result = execute_query(avg_times_query)
        avg_times = {row["stage"]: row["avg_days"] or SLA_TARGETS.get(row["stage"], 3) for row in avg_times_result}

        # Fill in defaults for missing stages
        for stage_name, sla in SLA_TARGETS.items():
            if stage_name not in avg_times:
                avg_times[stage_name] = sla

        if loan_id:
            # Predict for specific loan
            loan_query = """
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.stage_entered_at, l.target_close_date, l.amount
                FROM loans l
                WHERE l.id = :loan_id
            """
            loan = execute_single(loan_query, {"loan_id": loan_id})

            if not loan:
                return ToolResult.no_data(f"Loan {loan_id} not found")

            current_stage = loan["stage"]
            stages = get_loan_stage_order()

            if current_stage in ["funded", "closed", "denied", "withdrawn", "cancelled"]:
                return ToolResult.success({
                    "loan_id": loan_id,
                    "status": "complete",
                    "message": f"Loan is already {current_stage}",
                })

            # Calculate remaining days
            remaining_stages = stages[stages.index(current_stage):stages.index("funded")]
            days_in_current = days_between(loan["stage_entered_at"])
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
                "target_close_date": format_date(loan["target_close_date"]),
                "on_track": predicted_close <= loan["target_close_date"] if loan["target_close_date"] else True,
            })

        elif stage:
            # Predict for all loans in a stage
            loans_query = """
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.stage_entered_at, l.target_close_date, l.amount
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
                if current_stage in ["funded", "closed", "denied", "withdrawn", "cancelled"]:
                    continue

                remaining_stages = stages[stages.index(current_stage):stages.index("funded")]
                days_in_current = days_between(loan["stage_entered_at"])
                remaining_in_current = max(0, avg_times.get(current_stage, 3) - days_in_current)
                remaining_days = remaining_in_current + sum(avg_times.get(s, 3) for s in remaining_stages[1:])
                predicted_close = add_business_days(datetime.now().date(), int(remaining_days))

                predictions.append({
                    "loan_id": loan["id"],
                    "loan_number": loan["loan_number"],
                    "borrower_name": loan["borrower_name"],
                    "predicted_close_date": format_date(predicted_close),
                    "predicted_days": round(remaining_days, 1),
                    "on_track": predicted_close <= loan["target_close_date"] if loan["target_close_date"] else True,
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

        # Get average time in each stage vs SLA
        stage_analysis_query = f"""
            SELECT
                l.stage,
                COUNT(*) as loan_count,
                SUM(l.amount) as total_volume,
                AVG(EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400) as avg_days_in_stage,
                MAX(EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400) as max_days_in_stage,
                COUNT(CASE WHEN EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400 >
                    CASE l.stage
                        WHEN 'application' THEN 1
                        WHEN 'processing' THEN 3
                        WHEN 'submitted' THEN 2
                        WHEN 'underwriting' THEN 3
                        WHEN 'conditional' THEN 5
                        WHEN 'clear_to_close' THEN 2
                        WHEN 'closing' THEN 3
                        ELSE 5
                    END THEN 1 END) as over_sla_count
            FROM loans l
            WHERE l.stage NOT IN ('funded', 'closed', 'denied', 'withdrawn', 'cancelled')
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

    recommendations = {
        "processing": "Consider adding processing capacity or automating document collection",
        "underwriting": "Review underwriter workload distribution; consider condition delegation",
        "conditional": "Expedite condition clearing with borrower outreach automation",
        "clear_to_close": "Streamline CD preparation and closing coordination",
        "closing": "Improve title/settlement coordination and funding procedures",
        "submitted": "Follow up with underwriting on submission queue priority",
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

        # Get our metrics
        metrics_query = f"""
            SELECT
                AVG(EXTRACT(EPOCH FROM (funded_at - created_at)) / 86400) as avg_cycle_time,
                COUNT(CASE WHEN stage IN ('funded', 'closed') THEN 1 END)::float /
                    NULLIF(COUNT(*), 0) * 100 as pull_through_rate,
                COUNT(CASE WHEN stage IN ('denied', 'withdrawn', 'cancelled') THEN 1 END)::float /
                    NULLIF(COUNT(*), 0) * 100 as fallout_rate
            FROM loans
            WHERE created_at >= NOW() - INTERVAL '{days_back} days'
            {lo_filter}
        """
        metrics = execute_single(metrics_query, params)

        # Get stage-specific times
        stage_times_query = f"""
            SELECT
                stage,
                AVG(EXTRACT(EPOCH FROM (stage_exited_at - stage_entered_at)) / 86400) as avg_days
            FROM loan_stage_history
            WHERE stage_entered_at >= NOW() - INTERVAL '{days_back} days'
            AND stage_exited_at IS NOT NULL
            GROUP BY stage
        """
        stage_times = execute_query(stage_times_query, params)
        stage_time_dict = {row["stage"]: row["avg_days"] for row in stage_times}

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
        query = """
            SELECT
                lo.id as lo_id,
                lo.name as lo_name,
                lo.email as lo_email,
                COUNT(l.id) as total_loans,
                SUM(l.amount) as total_volume,
                COUNT(CASE WHEN l.stage IN ('application', 'processing') THEN 1 END) as early_stage,
                COUNT(CASE WHEN l.stage IN ('submitted', 'underwriting', 'conditional') THEN 1 END) as mid_stage,
                COUNT(CASE WHEN l.stage IN ('clear_to_close', 'closing') THEN 1 END) as late_stage,
                AVG(EXTRACT(EPOCH FROM (NOW() - l.stage_entered_at)) / 86400) as avg_days_in_stage
            FROM loan_officers lo
            LEFT JOIN loans l ON lo.id = l.loan_officer_id
                AND l.stage NOT IN ('funded', 'closed', 'denied', 'withdrawn', 'cancelled')
            GROUP BY lo.id, lo.name, lo.email
            ORDER BY total_volume DESC NULLS LAST
        """

        lo_data = execute_query(query)

        if not lo_data:
            return ToolResult.no_data("No loan officer data found")

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
                metrics_query = """
                    SELECT
                        COUNT(CASE WHEN stage IN ('funded', 'closed') AND funded_at >= NOW() - INTERVAL '30 days' THEN 1 END) as closed_30d,
                        AVG(CASE WHEN stage IN ('funded', 'closed') THEN EXTRACT(EPOCH FROM (funded_at - created_at)) / 86400 END) as avg_cycle_time
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
