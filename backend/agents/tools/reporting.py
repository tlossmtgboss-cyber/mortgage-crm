"""
Perennia AI - Reporting Engine Tools
====================================
Tools for the Reporting Engine Agent generating reports and analytics.
8 tools for report generation, dashboards, and data export.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_currency,
    format_date,
    format_percentage,
)


# =============================================================================
# Reporting Engine Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="generate_pipeline_report",
    description="Generate comprehensive pipeline report with stage breakdown",
    agent_roles=["reporting_engine", "pipeline_analyst"],
    risk_level="LOW",
    parameters={
        "report_type": "Type: summary, detailed, executive",
        "date_from": "Report start date (ISO)",
        "date_to": "Report end date (ISO)",
        "group_by": "Group by: stage, lo, source, program",
        "include_charts": "Include chart data for visualization",
    },
)
def generate_pipeline_report(
    report_type: str = "summary",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "stage",
    include_charts: bool = True,
) -> ToolResult:
    """Generate pipeline report."""
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Get pipeline data by stage
    stage_data = execute_query("""
        SELECT
            stage,
            COUNT(*) as count,
            COALESCE(SUM(loan_amount), 0) as volume,
            COALESCE(AVG(loan_amount), 0) as avg_amount
        FROM loans
        WHERE created_at >= :date_from AND created_at <= :date_to
        GROUP BY stage
        ORDER BY
            CASE stage
                WHEN 'Disclosed' THEN 1
                WHEN 'Processing' THEN 2
                WHEN 'Submitted' THEN 3
                WHEN 'UW Received' THEN 4
                WHEN 'Approved' THEN 5
                WHEN 'Suspended' THEN 6
                WHEN 'CTC' THEN 7
                WHEN 'Docs Out' THEN 8
                WHEN 'Funded' THEN 9
                ELSE 10
            END
    """, {"date_from": date_from, "date_to": date_to})

    pipeline_data = []
    total_count = 0
    total_volume = 0

    for r in stage_data:
        count = r.get("count", 0)
        volume = float(r.get("volume", 0) or 0)
        total_count += count
        total_volume += volume

        pipeline_data.append({
            "stage": r.get("stage"),
            "count": count,
            "volume": volume,
            "volume_formatted": format_currency(volume),
            "avg_loan_size": format_currency(r.get("avg_amount", 0) or 0),
            "pct_of_total": round((count / total_count * 100), 1) if total_count > 0 else 0,
        })

    # Get velocity metrics
    velocity = execute_single("""
        SELECT
            COUNT(CASE WHEN funded_at >= CURRENT_DATE - 30 THEN 1 END) as funded_30d,
            COUNT(CASE WHEN funded_at >= CURRENT_DATE - 7 THEN 1 END) as funded_7d,
            AVG(EXTRACT(EPOCH FROM (funded_at - application_date)) / 86400) as avg_cycle_time
        FROM loans
        WHERE funded_at IS NOT NULL
    """)

    report = {
        "report_id": f"RPT-PL-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "report_type": report_type,
        "period": {"from": date_from, "to": date_to},
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_loans": total_count,
            "total_volume": total_volume,
            "total_volume_formatted": format_currency(total_volume),
            "avg_loan_size": format_currency(total_volume / total_count) if total_count > 0 else "$0.00",
        },
        "velocity": {
            "funded_last_30_days": velocity.get("funded_30d", 0) if velocity else 0,
            "funded_last_7_days": velocity.get("funded_7d", 0) if velocity else 0,
            "avg_cycle_time_days": round(float(velocity.get("avg_cycle_time", 0) or 0), 1) if velocity else 0,
        },
        "by_stage": pipeline_data,
    }

    if include_charts:
        report["chart_data"] = {
            "funnel": {
                "labels": [d["stage"] for d in pipeline_data],
                "values": [d["count"] for d in pipeline_data],
            },
            "volume_by_stage": {
                "labels": [d["stage"] for d in pipeline_data],
                "values": [d["volume"] for d in pipeline_data],
            },
        }

    return ToolResult.success(
        data=report,
        message=f"Pipeline report: {total_count} loans, {format_currency(total_volume)} volume",
    )


@mortgage_tool(
    name="generate_production_report",
    description="Generate production report for funded loans and volume",
    agent_roles=["reporting_engine", "team_coach"],
    risk_level="LOW",
    parameters={
        "period": "Period: mtd, qtd, ytd, custom",
        "date_from": "Custom start date (ISO)",
        "date_to": "Custom end date (ISO)",
        "branch_id": "Optional branch filter",
        "include_rankings": "Include peer rankings",
    },
)
def generate_production_report(
    period: str = "mtd",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[str] = None,
    include_rankings: bool = True,
) -> ToolResult:
    """Generate production report."""
    # Calculate date range based on period
    date_to = date_to or datetime.now().strftime("%Y-%m-%d")

    if period == "mtd":
        date_from = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    elif period == "qtd":
        quarter_start_month = ((datetime.now().month - 1) // 3) * 3 + 1
        date_from = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
    elif period == "ytd":
        date_from = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
    elif not date_from:
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Query production data by LO
    params = {"date_from": date_from, "date_to": date_to}
    branch_filter = ""
    if branch_id:
        branch_filter = "AND l.branch_id = :branch_id"
        params["branch_id"] = branch_id

    production = execute_query(f"""
        SELECT
            u.id as lo_id,
            COALESCE(es.full_name, u.email) as lo_name,
            COUNT(CASE WHEN l.funded_at IS NOT NULL THEN 1 END) as funded_count,
            COALESCE(SUM(CASE WHEN l.funded_at IS NOT NULL THEN l.loan_amount ELSE 0 END), 0) as funded_volume,
            COUNT(*) as total_pipeline,
            COALESCE(SUM(l.loan_amount), 0) as total_volume
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        LEFT JOIN email_signatures es ON es.user_id = u.id
        WHERE l.created_at >= :date_from AND l.created_at <= :date_to
            {branch_filter}
        GROUP BY u.id, COALESCE(es.full_name, u.email)
        ORDER BY funded_volume DESC
    """, params)

    production_data = []
    for i, r in enumerate(production):
        production_data.append({
            "rank": i + 1 if include_rankings else None,
            "lo_id": r.get("lo_id"),
            "lo_name": r.get("lo_name"),
            "funded_loans": r.get("funded_count", 0),
            "funded_volume": float(r.get("funded_volume", 0) or 0),
            "funded_volume_formatted": format_currency(r.get("funded_volume", 0) or 0),
            "pipeline_loans": r.get("total_pipeline", 0),
            "pipeline_volume": float(r.get("total_volume", 0) or 0),
            "pipeline_volume_formatted": format_currency(r.get("total_volume", 0) or 0),
        })

    total_funded = sum(p["funded_loans"] for p in production_data)
    total_funded_volume = sum(p["funded_volume"] for p in production_data)

    report = {
        "report_id": f"RPT-PR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "period": period,
        "date_range": {"from": date_from, "to": date_to},
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_funded_loans": total_funded,
            "total_funded_volume": total_funded_volume,
            "total_funded_volume_formatted": format_currency(total_funded_volume),
            "lo_count": len(production_data),
            "avg_per_lo": round(total_funded / len(production_data), 1) if production_data else 0,
        },
        "production_by_lo": production_data,
    }

    if include_rankings:
        report["top_producers"] = production_data[:5]

    return ToolResult.success(
        data=report,
        message=f"Production report: {total_funded} funded, {format_currency(total_funded_volume)}",
    )


@mortgage_tool(
    name="generate_lo_performance_report",
    description="Generate detailed loan officer performance report with KPIs",
    agent_roles=["reporting_engine", "team_coach"],
    risk_level="LOW",
    parameters={
        "lo_id": "Loan officer ID",
        "period": "Period: mtd, qtd, ytd, custom",
        "date_from": "Custom start date",
        "date_to": "Custom end date",
        "include_benchmarks": "Include peer benchmarks",
    },
)
def generate_lo_performance_report(
    lo_id: str,
    period: str = "mtd",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_benchmarks: bool = True,
) -> ToolResult:
    """Generate LO performance report."""
    # Calculate date range
    date_to = date_to or datetime.now().strftime("%Y-%m-%d")

    if period == "mtd":
        date_from = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    elif period == "qtd":
        quarter_start_month = ((datetime.now().month - 1) // 3) * 3 + 1
        date_from = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
    elif period == "ytd":
        date_from = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
    elif not date_from:
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Get LO info
    lo = execute_single("""
        SELECT u.id, COALESCE(es.full_name, u.email) AS name, u.email, u.branch_id
        FROM users u LEFT JOIN email_signatures es ON es.user_id = u.id
        WHERE u.id = :lo_id
    """, {"lo_id": lo_id})

    if not lo:
        return ToolResult.no_data(f"Loan officer {lo_id} not found")

    # Get LO metrics
    params = {"lo_id": lo_id, "date_from": date_from, "date_to": date_to}

    metrics = execute_single("""
        SELECT
            COUNT(*) as total_loans,
            COUNT(CASE WHEN funded_at IS NOT NULL THEN 1 END) as funded_count,
            COALESCE(SUM(CASE WHEN funded_at IS NOT NULL THEN loan_amount END), 0) as funded_volume,
            COALESCE(AVG(CASE WHEN funded_at IS NOT NULL THEN loan_amount END), 0) as avg_loan_size,
            AVG(EXTRACT(EPOCH FROM (funded_at - application_date)) / 86400) as avg_cycle_time,
            0 as fallout_count
        FROM loans
        WHERE loan_officer_id = :lo_id
            AND created_at >= :date_from AND created_at <= :date_to
    """, params)

    # Get conversion rates
    conversion = execute_single("""
        SELECT
            COUNT(CASE WHEN application_date IS NOT NULL THEN 1 END) as applications,
            COUNT(CASE WHEN submitted_to_uw_at IS NOT NULL THEN 1 END) as submitted,
            COUNT(CASE WHEN approval_date IS NOT NULL THEN 1 END) as approved,
            COUNT(CASE WHEN funded_at IS NOT NULL THEN 1 END) as funded
        FROM loans
        WHERE loan_officer_id = :lo_id
            AND created_at >= :date_from AND created_at <= :date_to
    """, params)

    # Calculate pull-through rate
    apps = conversion.get("applications", 0) or 0
    funded = conversion.get("funded", 0) or 0
    pull_through = round((funded / apps * 100), 1) if apps > 0 else 0

    performance = {
        "lo_id": lo_id,
        "lo_name": lo.get("name"),
        "period": period,
        "date_range": {"from": date_from, "to": date_to},
        "production": {
            "funded_loans": metrics.get("funded_count", 0) if metrics else 0,
            "funded_volume": float(metrics.get("funded_volume", 0) or 0) if metrics else 0,
            "funded_volume_formatted": format_currency(metrics.get("funded_volume", 0) or 0) if metrics else "$0.00",
            "avg_loan_size": format_currency(metrics.get("avg_loan_size", 0) or 0) if metrics else "$0.00",
        },
        "efficiency": {
            "avg_cycle_time_days": round(float(metrics.get("avg_cycle_time", 0) or 0), 1) if metrics else 0,
            "pull_through_rate": pull_through,
            "fallout_count": metrics.get("fallout_count", 0) if metrics else 0,
        },
        "conversion_funnel": {
            "applications": apps,
            "submitted": conversion.get("submitted", 0) or 0,
            "approved": conversion.get("approved", 0) or 0,
            "funded": funded,
        },
    }

    # Get benchmarks if requested
    if include_benchmarks:
        benchmarks = execute_single("""
            SELECT
                AVG(funded_count) as avg_funded,
                AVG(funded_volume) as avg_volume,
                AVG(cycle_time) as avg_cycle
            FROM (
                SELECT
                    loan_officer_id,
                    COUNT(CASE WHEN funded_at IS NOT NULL THEN 1 END) as funded_count,
                    SUM(CASE WHEN funded_at IS NOT NULL THEN loan_amount ELSE 0 END) as funded_volume,
                    AVG(EXTRACT(EPOCH FROM (funded_at - application_date)) / 86400) as cycle_time
                FROM loans
                WHERE created_at >= :date_from AND created_at <= :date_to
                GROUP BY loan_officer_id
            ) lo_stats
        """, {"date_from": date_from, "date_to": date_to})

        performance["benchmarks"] = {
            "avg_funded_loans": round(float(benchmarks.get("avg_funded", 0) or 0), 1) if benchmarks else 0,
            "avg_funded_volume": format_currency(benchmarks.get("avg_volume", 0) or 0) if benchmarks else "$0.00",
            "avg_cycle_time": round(float(benchmarks.get("avg_cycle", 0) or 0), 1) if benchmarks else 0,
        }

        # Calculate vs benchmark
        lo_funded = performance["production"]["funded_loans"]
        avg_funded = benchmarks.get("avg_funded", 0) or 0 if benchmarks else 0
        performance["vs_benchmark"] = {
            "funded_diff": lo_funded - avg_funded,
            "funded_diff_pct": round(((lo_funded - avg_funded) / avg_funded * 100), 1) if avg_funded > 0 else 0,
        }

    report = {
        "report_id": f"RPT-LO-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now().isoformat(),
        "performance": performance,
    }

    return ToolResult.success(
        data=report,
        message=f"LO Performance: {performance['production']['funded_loans']} funded, {performance['production']['funded_volume_formatted']}",
    )


@mortgage_tool(
    name="get_report_templates",
    description="Get available report templates for generation",
    agent_roles=["reporting_engine"],
    risk_level="LOW",
    parameters={
        "category": "Optional category filter: pipeline, production, compliance, financial",
    },
)
def get_report_templates(
    category: Optional[str] = None,
) -> ToolResult:
    """Get available report templates."""
    templates = [
        {
            "id": "pipeline_summary",
            "name": "Pipeline Summary Report",
            "category": "pipeline",
            "description": "Overview of current pipeline by stage with volume breakdown",
            "parameters": ["date_from", "date_to", "group_by"],
        },
        {
            "id": "pipeline_detailed",
            "name": "Detailed Pipeline Report",
            "category": "pipeline",
            "description": "Comprehensive pipeline analysis with loan-level details",
            "parameters": ["date_from", "date_to", "include_loans"],
        },
        {
            "id": "production_monthly",
            "name": "Monthly Production Report",
            "category": "production",
            "description": "LO production metrics and rankings for the month",
            "parameters": ["period", "branch_id", "include_rankings"],
        },
        {
            "id": "production_ytd",
            "name": "Year-to-Date Production Report",
            "category": "production",
            "description": "Cumulative production metrics year-to-date",
            "parameters": ["branch_id"],
        },
        {
            "id": "lo_performance",
            "name": "LO Performance Report",
            "category": "production",
            "description": "Individual LO performance with KPIs and benchmarks",
            "parameters": ["lo_id", "period", "include_benchmarks"],
        },
        {
            "id": "compliance_audit",
            "name": "Compliance Audit Report",
            "category": "compliance",
            "description": "Compliance status, violations, and audit results",
            "parameters": ["date_from", "date_to", "scope"],
        },
        {
            "id": "sla_performance",
            "name": "SLA Performance Report",
            "category": "operations",
            "description": "SLA compliance by stage and breach analysis",
            "parameters": ["date_from", "date_to", "lo_id"],
        },
        {
            "id": "lead_conversion",
            "name": "Lead Conversion Report",
            "category": "leads",
            "description": "Lead-to-application conversion funnel analysis",
            "parameters": ["date_from", "date_to", "source"],
        },
    ]

    if category:
        templates = [t for t in templates if t["category"] == category]

    return ToolResult.success(
        data={
            "templates": templates,
            "count": len(templates),
            "categories": list(set(t["category"] for t in templates)),
        },
        message=f"Found {len(templates)} report templates",
    )


@mortgage_tool(
    name="schedule_report",
    description="Schedule recurring report generation and delivery",
    agent_roles=["reporting_engine"],
    risk_level="MEDIUM",
    parameters={
        "report_template": "Template ID or report type",
        "frequency": "Frequency: daily, weekly, monthly",
        "recipients": "List of email recipients",
        "format": "Report format: pdf, excel, csv",
        "parameters": "Report-specific parameters",
    },
)
def schedule_report(
    report_template: str,
    frequency: str = "weekly",
    recipients: Optional[List[str]] = None,
    format: str = "pdf",
    parameters: Optional[Dict] = None,
) -> ToolResult:
    """Schedule recurring report."""
    import uuid
    schedule_id = str(uuid.uuid4())[:8].upper()

    # Calculate next run time
    next_run = _calculate_next_run(frequency)

    schedule = {
        "schedule_id": f"SCH-{schedule_id}",
        "report_template": report_template,
        "frequency": frequency,
        "recipients": recipients or [],
        "format": format,
        "parameters": parameters or {},
        "next_run": next_run,
        "last_run": None,
        "run_count": 0,
        "status": "active",
        "created_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=schedule,
        message=f"Report scheduled: {report_template} ({frequency}), next run {next_run[:10]}",
    )


@mortgage_tool(
    name="export_report",
    description="Export report data to file format for download",
    agent_roles=["reporting_engine"],
    risk_level="LOW",
    parameters={
        "report_id": "Report ID to export",
        "format": "Export format: csv, excel, pdf, json",
        "include_charts": "Include charts in export (PDF only)",
        "email_to": "Optional email address to send export",
    },
)
def export_report(
    report_id: str,
    format: str = "csv",
    include_charts: bool = False,
    email_to: Optional[str] = None,
) -> ToolResult:
    """Export report data."""
    import uuid
    export_id = str(uuid.uuid4())[:8].upper()

    # Validate format
    valid_formats = ["csv", "excel", "pdf", "json"]
    if format not in valid_formats:
        return ToolResult.error(f"Invalid format. Must be one of: {valid_formats}")

    export = {
        "export_id": f"EXP-{export_id}",
        "report_id": report_id,
        "format": format,
        "include_charts": include_charts and format == "pdf",
        "status": "processing",
        "requested_at": datetime.now().isoformat(),
        "download_url": None,
        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat(),
    }

    if email_to:
        export["delivery"] = {
            "method": "email",
            "email_to": email_to,
            "status": "pending",
        }

    # Simulate processing
    export["download_url"] = f"https://reports.perennia.ai/download/{export_id}"
    export["status"] = "ready"

    return ToolResult.success(
        data=export,
        message=f"Export ready: {format.upper()} format",
    )


@mortgage_tool(
    name="get_dashboard_metrics",
    description="Get real-time dashboard metrics and KPIs",
    agent_roles=["reporting_engine", "pipeline_analyst", "team_coach"],
    risk_level="LOW",
    parameters={
        "dashboard_type": "Dashboard: executive, lo, operations, compliance",
        "lo_id": "Optional LO ID for personal dashboard",
        "branch_id": "Optional branch filter",
    },
)
def get_dashboard_metrics(
    dashboard_type: str = "executive",
    lo_id: Optional[str] = None,
    branch_id: Optional[str] = None,
) -> ToolResult:
    """Get dashboard metrics."""
    params = {}
    filters = ["1=1"]

    if lo_id:
        filters.append("loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("branch_id = :branch_id")
        params["branch_id"] = branch_id

    where_sql = " AND ".join(filters)

    # Pipeline summary
    pipeline = execute_single(f"""
        SELECT
            COUNT(*) as total_active,
            COALESCE(SUM(loan_amount), 0) as total_volume,
            COUNT(CASE WHEN status IN ('clear_to_close', 'docs_out', 'docs_back') THEN 1 END) as closing_soon,
            COUNT(CASE WHEN status = 'underwriting' THEN 1 END) as in_underwriting
        FROM loans
        WHERE stage NOT IN ('Funded')
            AND {where_sql}
    """, params)

    # MTD production
    mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    mtd = execute_single(f"""
        SELECT
            COUNT(*) as funded_count,
            COALESCE(SUM(loan_amount), 0) as funded_volume
        FROM loans
        WHERE funded_at >= :mtd_start
            AND {where_sql}
    """, {**params, "mtd_start": mtd_start})

    # Today's activity
    today = execute_single(f"""
        SELECT
            COUNT(CASE WHEN DATE(created_at) = CURRENT_DATE THEN 1 END) as new_apps,
            COUNT(CASE WHEN DATE(funded_at) = CURRENT_DATE THEN 1 END) as funded_today,
            COUNT(CASE WHEN DATE(status_changed_at) = CURRENT_DATE THEN 1 END) as status_changes
        FROM loans
        WHERE {where_sql}
    """, params)

    # SLA alerts
    sla_alerts = execute_single(f"""
        SELECT COUNT(*) as overdue_count
        FROM loans
        WHERE stage NOT IN ('Funded')
            AND status_changed_at < CURRENT_TIMESTAMP - INTERVAL '5 days'
            AND {where_sql}
    """, params)

    metrics = {
        "dashboard_type": dashboard_type,
        "as_of": datetime.now().isoformat(),
        "pipeline": {
            "active_loans": pipeline.get("total_active", 0) if pipeline else 0,
            "total_volume": float(pipeline.get("total_volume", 0) or 0) if pipeline else 0,
            "total_volume_formatted": format_currency(pipeline.get("total_volume", 0) or 0) if pipeline else "$0.00",
            "closing_soon": pipeline.get("closing_soon", 0) if pipeline else 0,
            "in_underwriting": pipeline.get("in_underwriting", 0) if pipeline else 0,
        },
        "mtd_production": {
            "funded_loans": mtd.get("funded_count", 0) if mtd else 0,
            "funded_volume": float(mtd.get("funded_volume", 0) or 0) if mtd else 0,
            "funded_volume_formatted": format_currency(mtd.get("funded_volume", 0) or 0) if mtd else "$0.00",
        },
        "today": {
            "new_applications": today.get("new_apps", 0) if today else 0,
            "funded_today": today.get("funded_today", 0) if today else 0,
            "status_changes": today.get("status_changes", 0) if today else 0,
        },
        "alerts": {
            "sla_overdue": sla_alerts.get("overdue_count", 0) if sla_alerts else 0,
        },
    }

    if lo_id:
        metrics["lo_id"] = lo_id
    if branch_id:
        metrics["branch_id"] = branch_id

    return ToolResult.success(
        data=metrics,
        message=f"Dashboard: {metrics['pipeline']['active_loans']} active, {metrics['mtd_production']['funded_volume_formatted']} MTD",
    )


@mortgage_tool(
    name="create_custom_report",
    description="Create a custom report with specified metrics and dimensions",
    agent_roles=["reporting_engine"],
    risk_level="LOW",
    parameters={
        "name": "Report name",
        "metrics": "List of metrics: count, volume, avg_loan_size, cycle_time, etc.",
        "dimensions": "Grouping dimensions: stage, lo, source, loan_type, date",
        "filters": "Data filters to apply",
        "date_range": "Date range for the report",
    },
)
def create_custom_report(
    name: str,
    metrics: List[str],
    dimensions: Optional[List[str]] = None,
    filters: Optional[Dict] = None,
    date_range: Optional[Dict] = None,
) -> ToolResult:
    """Create custom report."""
    import uuid
    report_id = str(uuid.uuid4())[:8].upper()

    # Validate metrics
    valid_metrics = ["count", "volume", "avg_loan_size", "cycle_time", "pull_through", "fallout_rate"]
    invalid_metrics = [m for m in metrics if m not in valid_metrics]
    if invalid_metrics:
        return ToolResult.error(f"Invalid metrics: {invalid_metrics}. Valid: {valid_metrics}")

    # Default date range
    if not date_range:
        date_range = {
            "from": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "to": datetime.now().strftime("%Y-%m-%d"),
        }

    custom_report = {
        "report_id": f"RPT-CUS-{report_id}",
        "name": name,
        "metrics": metrics,
        "dimensions": dimensions or ["stage"],
        "filters": filters or {},
        "date_range": date_range,
        "created_at": datetime.now().isoformat(),
        "status": "created",
        "is_custom": True,
    }

    # Generate preview data structure
    custom_report["preview"] = {
        "columns": (dimensions or ["stage"]) + metrics,
        "sample_rows": [],
        "total_rows_estimate": 0,
    }

    return ToolResult.success(
        data=custom_report,
        message=f"Custom report created: {name}",
    )


# =============================================================================
# Helper Functions
# =============================================================================

@mortgage_tool(
    name="generate_structured_report",
    description="Generate and return a structured summary report for pipeline, production, team performance, or lead conversion metrics",
    agent_roles=["reporting_engine", "ops_manager", "manager", "executive"],
    risk_level="LOW",
    requires_confirmation=False,
    parameters={
        "report_type": "Report type: pipeline, production, team_performance, lead_conversion",
        "time_period": "Time period: 7d, 14d, 30d, 60d, 90d (default 30d)",
    },
)
def generate_structured_report(
    report_type: str,
    time_period: str = "30d",
) -> ToolResult:
    """Generate and return a structured report dict."""
    valid_types = ["pipeline", "production", "team_performance", "lead_conversion"]
    if report_type not in valid_types:
        return ToolResult.error(
            f"Invalid report_type '{report_type}'. Must be one of: {', '.join(valid_types)}"
        )

    # Parse time period
    days = int(time_period.replace("d", "")) if time_period.endswith("d") else 30

    import uuid
    report_id = f"RPT-{report_type.upper()[:4]}-{str(uuid.uuid4())[:8].upper()}"

    if report_type == "pipeline":
        rows = execute_query("""
            SELECT
                stage,
                COUNT(*) as count,
                COALESCE(SUM(loan_amount), 0) as volume,
                COALESCE(AVG(loan_amount), 0) as avg_amount
            FROM loans
            WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days'
                AND stage NOT IN ('Funded')
            GROUP BY stage
            ORDER BY count DESC
        """.format(days=days))

        stages = []
        total_count = 0
        total_volume = 0.0
        for r in rows:
            count = r.get("count", 0)
            volume = float(r.get("volume", 0) or 0)
            total_count += count
            total_volume += volume
            stages.append({
                "stage": r.get("stage"),
                "count": count,
                "volume": format_currency(volume),
                "avg_loan_size": format_currency(r.get("avg_amount", 0) or 0),
            })

        report_data = {
            "total_active_loans": total_count,
            "total_volume": format_currency(total_volume),
            "by_stage": stages,
        }

    elif report_type == "production":
        summary = execute_single("""
            SELECT
                COUNT(*) as funded_count,
                COALESCE(SUM(loan_amount), 0) as funded_volume,
                COALESCE(AVG(loan_amount), 0) as avg_loan_size
            FROM loans
            WHERE funded_at >= CURRENT_DATE - INTERVAL '{days} days'
        """.format(days=days))

        report_data = {
            "funded_loans": summary.get("funded_count", 0) if summary else 0,
            "funded_volume": format_currency(summary.get("funded_volume", 0) or 0) if summary else "$0.00",
            "avg_loan_size": format_currency(summary.get("avg_loan_size", 0) or 0) if summary else "$0.00",
        }

    elif report_type == "team_performance":
        rows = execute_query("""
            SELECT
                u.id as lo_id,
                COALESCE(es.full_name, u.email) as lo_name,
                COUNT(CASE WHEN l.funded_at IS NOT NULL THEN 1 END) as funded,
                COALESCE(SUM(CASE WHEN l.funded_at IS NOT NULL THEN l.loan_amount ELSE 0 END), 0) as funded_volume,
                COUNT(*) as pipeline_count
            FROM loans l
            JOIN users u ON u.id = l.loan_officer_id
            LEFT JOIN email_signatures es ON es.user_id = u.id
            WHERE l.created_at >= CURRENT_DATE - INTERVAL '{days} days'
            GROUP BY u.id, COALESCE(es.full_name, u.email)
            ORDER BY funded_volume DESC
        """.format(days=days))

        team = []
        for r in rows:
            team.append({
                "lo_id": r.get("lo_id"),
                "lo_name": r.get("lo_name"),
                "funded_loans": r.get("funded", 0),
                "funded_volume": format_currency(r.get("funded_volume", 0) or 0),
                "pipeline_count": r.get("pipeline_count", 0),
            })

        report_data = {
            "team_members": len(team),
            "by_lo": team,
        }

    elif report_type == "lead_conversion":
        funnel = execute_single("""
            SELECT
                COUNT(*) as total_leads,
                COUNT(CASE WHEN stage NOT IN ('New') THEN 1 END) as contacted,
                COUNT(CASE WHEN stage IN ('Qualified', 'Application') THEN 1 END) as qualified,
                COUNT(CASE WHEN stage = 'Application' THEN 1 END) as applied,
                COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as funded
            FROM leads
            WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days'
        """.format(days=days))

        total = funnel.get("total_leads", 0) or 0 if funnel else 0
        funded = funnel.get("funded", 0) or 0 if funnel else 0
        conversion = round((funded / total) * 100, 1) if total > 0 else 0.0

        report_data = {
            "total_leads": total,
            "contacted": funnel.get("contacted", 0) or 0 if funnel else 0,
            "qualified": funnel.get("qualified", 0) or 0 if funnel else 0,
            "applied": funnel.get("applied", 0) or 0 if funnel else 0,
            "funded": funded,
            "overall_conversion_rate": f"{conversion}%",
        }

    else:
        report_data = {}

    report = {
        "report_id": report_id,
        "report_type": report_type,
        "time_period": time_period,
        "generated_at": datetime.now().isoformat(),
        "data": report_data,
    }

    return ToolResult.success(
        data=report,
        message=f"Generated {report_type} report for last {time_period}",
    )


# =============================================================================
# Helper Functions
# =============================================================================

def _calculate_next_run(frequency: str) -> str:
    """Calculate next run time based on frequency."""
    now = datetime.now()

    if frequency == "daily":
        next_run = (now + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
    elif frequency == "weekly":
        days_until_monday = (7 - now.weekday()) % 7 or 7
        next_run = (now + timedelta(days=days_until_monday)).replace(hour=6, minute=0, second=0, microsecond=0)
    elif frequency == "monthly":
        if now.month == 12:
            next_run = now.replace(year=now.year + 1, month=1, day=1, hour=6, minute=0, second=0, microsecond=0)
        else:
            next_run = now.replace(month=now.month + 1, day=1, hour=6, minute=0, second=0, microsecond=0)
    else:
        next_run = now + timedelta(days=1)

    return next_run.isoformat()
