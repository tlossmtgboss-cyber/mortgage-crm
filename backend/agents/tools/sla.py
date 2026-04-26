"""
Perennia AI - SLA Tracker Tools
===============================
Tools for the SLA Tracker Agent monitoring service level agreements.
8 tools for SLA monitoring, alerts, compliance tracking, and reporting.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
    days_between,
    SLA_TARGETS,
)


# =============================================================================
# SLA Tracker Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="check_sla_status",
    description="Check SLA status for a specific loan or across pipeline",
    agent_roles=["sla_tracker", "pipeline_analyst"],
    risk_level="LOW",
    parameters={
        "loan_id": "Optional specific loan ID",
        "stage": "Optional stage filter",
        "include_at_risk": "Include at-risk loans (approaching SLA)",
    },
)
def check_sla_status(
    loan_id: Optional[str] = None,
    stage: Optional[str] = None,
    include_at_risk: bool = True,
) -> ToolResult:
    """Check SLA compliance status."""
    if loan_id:
        # Check specific loan
        loan = execute_single("""
            SELECT id, loan_number, borrower_name, stage,
                   stage_changed_at as stage_entered_at,
                   created_at, expected_close_date as target_close_date
            FROM loans
            WHERE id = :id
        """, {"id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        sla_status = _calculate_loan_sla(loan)
        return ToolResult.success(
            data=sla_status,
            message=f"Loan {loan.get('loan_number')}: {sla_status['status']}",
        )

    # Check pipeline SLA
    params = {}
    filters = ["stage NOT IN ('Funded')"]

    if stage:
        filters.append("stage = :stage")
        params["stage"] = stage

    where_sql = " AND ".join(filters)

    loans = execute_query(f"""
        SELECT id, loan_number, borrower_name, stage,
               stage_changed_at as stage_entered_at,
               created_at, expected_close_date as target_close_date
        FROM loans
        WHERE {where_sql}
        ORDER BY stage_changed_at ASC
    """, params)

    sla_results = {
        "compliant": [],
        "at_risk": [],
        "breached": [],
    }

    for loan in loans:
        status = _calculate_loan_sla(loan)
        if status["status"] == "breached":
            sla_results["breached"].append(status)
        elif status["status"] == "at_risk":
            sla_results["at_risk"].append(status)
        else:
            sla_results["compliant"].append(status)

    total = len(loans)
    compliance_rate = round(len(sla_results["compliant"]) / total * 100, 1) if total > 0 else 100

    data = {
        "total_loans": total,
        "compliant_count": len(sla_results["compliant"]),
        "at_risk_count": len(sla_results["at_risk"]),
        "breached_count": len(sla_results["breached"]),
        "compliance_rate": compliance_rate,
        "breached_loans": sla_results["breached"][:10],
        "at_risk_loans": sla_results["at_risk"][:10] if include_at_risk else [],
    }

    return ToolResult.success(
        data=data,
        message=f"SLA Compliance: {compliance_rate}% ({len(sla_results['breached'])} breached)",
    )


@mortgage_tool(
    name="get_sla_alerts",
    description="Get active SLA alerts requiring attention",
    agent_roles=["sla_tracker"],
    risk_level="LOW",
    parameters={
        "severity": "Filter by severity: warning, critical",
        "stage": "Optional stage filter",
        "user_id": "Optional LO filter",
        "limit": "Maximum alerts to return",
    },
)
def get_sla_alerts(
    severity: Optional[str] = None,
    stage: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 20,
) -> ToolResult:
    """Get active SLA alerts."""
    params = {"limit": limit * 2}
    filters = ["stage NOT IN ('Funded')"]

    if stage:
        filters.append("stage = :stage")
        params["stage"] = stage

    if user_id:
        filters.append("loan_officer_id = :user_id")
        params["user_id"] = user_id

    where_sql = " AND ".join(filters)

    loans = execute_query(f"""
        SELECT id, loan_number, borrower_name, stage,
               stage_changed_at as stage_entered_at,
               loan_officer_id, loan_amount
        FROM loans
        WHERE {where_sql}
        ORDER BY stage_changed_at ASC
        LIMIT :limit
    """, params)

    alerts = []
    for loan in loans:
        sla_status = _calculate_loan_sla(loan)

        if sla_status["status"] == "compliant":
            continue

        alert_severity = "critical" if sla_status["status"] == "breached" else "warning"

        if severity and alert_severity != severity:
            continue

        alerts.append({
            "loan_id": loan.get("id"),
            "loan_number": loan.get("loan_number"),
            "borrower_name": loan.get("borrower_name"),
            "stage": loan.get("stage"),
            "severity": alert_severity,
            "days_in_stage": sla_status["days_in_stage"],
            "sla_target": sla_status["sla_target"],
            "days_over": sla_status.get("days_over", 0),
            "days_remaining": sla_status.get("days_remaining", 0),
            "recommended_action": _get_sla_action(sla_status),
        })

        if len(alerts) >= limit:
            break

    data = {
        "alerts": alerts,
        "total_count": len(alerts),
        "critical_count": sum(1 for a in alerts if a["severity"] == "critical"),
        "warning_count": sum(1 for a in alerts if a["severity"] == "warning"),
    }

    return ToolResult.success(
        data=data,
        message=f"Found {len(alerts)} SLA alerts ({data['critical_count']} critical)",
    )


@mortgage_tool(
    name="calculate_stage_sla",
    description="Calculate SLA metrics for a specific pipeline stage",
    agent_roles=["sla_tracker", "pipeline_analyst"],
    risk_level="LOW",
    parameters={
        "stage": "Pipeline stage to analyze",
        "date_from": "Start date (YYYY-MM-DD)",
        "date_to": "End date (YYYY-MM-DD)",
        "user_id": "Optional LO filter",
    },
)
def calculate_stage_sla(
    stage: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_id: Optional[str] = None,
) -> ToolResult:
    """Calculate SLA metrics for a stage."""
    sla_target = SLA_TARGETS.get(stage.lower(), 5)

    params = {"stage": stage, "sla_target": sla_target}
    filters = ["(stage = :stage OR previous_stage = :stage)"]

    if date_from:
        filters.append("stage_changed_at >= :date_from")
        params["date_from"] = date_from

    if date_to:
        filters.append("stage_changed_at <= :date_to")
        params["date_to"] = date_to

    if user_id:
        filters.append("loan_officer_id = :user_id")
        params["user_id"] = user_id

    where_sql = " AND ".join(filters)

    result = execute_single(f"""
        SELECT
            COUNT(*) as total_loans,
            AVG(EXTRACT(EPOCH FROM (
                COALESCE(stage_exited_at, NOW()) - stage_changed_at
            ))/86400) as avg_days,
            MIN(EXTRACT(EPOCH FROM (
                COALESCE(stage_exited_at, NOW()) - stage_changed_at
            ))/86400) as min_days,
            MAX(EXTRACT(EPOCH FROM (
                COALESCE(stage_exited_at, NOW()) - stage_changed_at
            ))/86400) as max_days,
            COUNT(CASE WHEN EXTRACT(EPOCH FROM (
                COALESCE(stage_exited_at, NOW()) - stage_changed_at
            ))/86400 <= :sla_target THEN 1 END) as within_sla
        FROM loans
        WHERE {where_sql}
    """, params)

    total = result.get("total_loans", 0) or 0
    within_sla = result.get("within_sla", 0) or 0
    compliance_rate = round(within_sla / total * 100, 1) if total > 0 else 100

    data = {
        "stage": stage,
        "sla_target_days": sla_target,
        "period": {
            "from": date_from or "all_time",
            "to": date_to or "today",
        },
        "metrics": {
            "total_loans": total,
            "avg_days_in_stage": round(result.get("avg_days", 0) or 0, 1),
            "min_days": round(result.get("min_days", 0) or 0, 1),
            "max_days": round(result.get("max_days", 0) or 0, 1),
            "within_sla_count": within_sla,
            "breached_count": total - within_sla,
            "compliance_rate": compliance_rate,
        },
        "performance": _get_stage_performance(
            result.get("avg_days", 0) or 0,
            sla_target
        ),
    }

    return ToolResult.success(
        data=data,
        message=f"Stage {stage}: {compliance_rate}% SLA compliance",
    )


@mortgage_tool(
    name="project_sla_breach",
    description="Project which loans are likely to breach SLA",
    agent_roles=["sla_tracker"],
    risk_level="LOW",
    parameters={
        "days_ahead": "Days to look ahead for projections",
        "min_confidence": "Minimum confidence threshold (0-1)",
        "stage": "Optional stage filter",
    },
)
def project_sla_breach(
    days_ahead: int = 3,
    min_confidence: float = 0.7,
    stage: Optional[str] = None,
) -> ToolResult:
    """Project potential SLA breaches."""
    params = {}
    filters = ["stage NOT IN ('Funded')"]

    if stage:
        filters.append("stage = :stage")
        params["stage"] = stage

    where_sql = " AND ".join(filters)

    loans = execute_query(f"""
        SELECT id, loan_number, borrower_name, stage,
               stage_changed_at as stage_entered_at,
               loan_amount, loan_type, loan_officer_id
        FROM loans
        WHERE {where_sql}
    """, params)

    projections = []
    for loan in loans:
        sla_status = _calculate_loan_sla(loan)

        # Skip already breached
        if sla_status["status"] == "breached":
            continue

        # Calculate breach probability
        days_remaining = sla_status["sla_target"] - sla_status["days_in_stage"]
        if days_remaining <= days_ahead and days_remaining > 0:
            confidence = 1 - (days_remaining / days_ahead) if days_ahead > 0 else 1

            if confidence >= min_confidence:
                projected_date = datetime.now() + timedelta(days=max(0, days_remaining))
                projections.append({
                    "loan_id": loan.get("id"),
                    "loan_number": loan.get("loan_number"),
                    "borrower_name": loan.get("borrower_name"),
                    "stage": loan.get("stage"),
                    "current_days_in_stage": sla_status["days_in_stage"],
                    "sla_target": sla_status["sla_target"],
                    "days_remaining": max(0, days_remaining),
                    "projected_breach_date": projected_date.strftime("%Y-%m-%d"),
                    "confidence": round(confidence, 2),
                    "risk_level": "high" if confidence >= 0.9 else "medium",
                    "recommended_action": _get_proactive_action(loan.get("stage")),
                })

    # Sort by confidence (most likely first)
    projections.sort(key=lambda x: x["confidence"], reverse=True)

    data = {
        "projections": projections[:20],
        "total_at_risk": len(projections),
        "high_risk_count": sum(1 for p in projections if p["risk_level"] == "high"),
        "projection_window_days": days_ahead,
        "min_confidence": min_confidence,
    }

    return ToolResult.success(
        data=data,
        message=f"Projected {len(projections)} potential SLA breaches in next {days_ahead} days",
    )


@mortgage_tool(
    name="get_sla_report",
    description="Generate comprehensive SLA compliance report",
    agent_roles=["sla_tracker", "reporting_engine"],
    risk_level="LOW",
    parameters={
        "report_type": "Type: daily, weekly, monthly",
        "date_from": "Report start date",
        "date_to": "Report end date",
        "user_id": "Optional LO filter",
        "include_details": "Include loan-level details",
    },
)
def get_sla_report(
    report_type: str = "weekly",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_id: Optional[str] = None,
    include_details: bool = False,
) -> ToolResult:
    """Generate SLA compliance report."""
    # Default date ranges
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")
    if not date_from:
        if report_type == "daily":
            date_from = date_to
        elif report_type == "weekly":
            date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        else:  # monthly
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Get stage-by-stage metrics
    stage_metrics = {}
    for stage, target in SLA_TARGETS.items():
        params = {
            "stage": stage,
            "target": target,
            "date_from": date_from,
            "date_to": date_to,
        }
        filters = [
            "(stage = :stage OR previous_stage = :stage)",
            "stage_changed_at >= :date_from",
            "stage_changed_at <= :date_to",
        ]

        if user_id:
            filters.append("loan_officer_id = :user_id")
            params["user_id"] = user_id

        where_sql = " AND ".join(filters)

        result = execute_single(f"""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN EXTRACT(EPOCH FROM (
                    COALESCE(stage_exited_at, NOW()) - stage_changed_at
                ))/86400 <= :target THEN 1 END) as compliant,
                AVG(EXTRACT(EPOCH FROM (
                    COALESCE(stage_exited_at, NOW()) - stage_changed_at
                ))/86400) as avg_days
            FROM loans
            WHERE {where_sql}
        """, params)

        total = result.get("total", 0) or 0
        compliant = result.get("compliant", 0) or 0

        stage_metrics[stage] = {
            "target_days": target,
            "total": total,
            "compliant": compliant,
            "breached": total - compliant,
            "compliance_rate": round(compliant / total * 100, 1) if total > 0 else 100,
            "avg_days": round(result.get("avg_days", 0) or 0, 1),
        }

    # Calculate overall metrics
    total_all = sum(m["total"] for m in stage_metrics.values())
    compliant_all = sum(m["compliant"] for m in stage_metrics.values())
    overall_rate = round(compliant_all / total_all * 100, 1) if total_all > 0 else 100

    # Identify worst performers
    worst_stages = sorted(
        [(k, v) for k, v in stage_metrics.items() if v["total"] > 0],
        key=lambda x: x[1]["compliance_rate"]
    )[:3]

    data = {
        "report_type": report_type,
        "period": {"from": date_from, "to": date_to},
        "user_id": user_id,
        "overall": {
            "total_stage_transitions": total_all,
            "compliant_transitions": compliant_all,
            "breached_transitions": total_all - compliant_all,
            "compliance_rate": overall_rate,
        },
        "by_stage": stage_metrics,
        "worst_performing_stages": [
            {"stage": s[0], "compliance_rate": s[1]["compliance_rate"]}
            for s in worst_stages
        ],
        "generated_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"SLA Report: {overall_rate}% overall compliance",
    )


@mortgage_tool(
    name="configure_sla_rules",
    description="Configure SLA rules and thresholds for stages",
    agent_roles=["sla_tracker"],
    risk_level="MEDIUM",
    parameters={
        "stage": "Pipeline stage",
        "target_days": "SLA target in days",
        "warning_days": "Days before breach to trigger warning",
        "escalation_rules": "Escalation configuration",
    },
)
def configure_sla_rules(
    stage: str,
    target_days: int,
    warning_days: Optional[int] = None,
    escalation_rules: Optional[Dict] = None,
) -> ToolResult:
    """Configure SLA rules for a stage."""
    if warning_days is None:
        warning_days = max(1, target_days - 1)

    default_escalation = {
        "warning": {"notify": ["assigned_lo"], "action": "alert"},
        "breach": {"notify": ["assigned_lo", "manager"], "action": "escalate"},
        "critical": {"notify": ["assigned_lo", "manager", "ops_lead"], "action": "urgent_escalate"},
    }

    rules = {
        "stage": stage,
        "target_days": target_days,
        "warning_threshold_days": warning_days,
        "escalation_rules": escalation_rules or default_escalation,
        "is_active": True,
        "updated_at": datetime.now().isoformat(),
    }

    # Validate configuration
    if target_days < 1:
        return ToolResult.error("Target days must be at least 1")
    if warning_days >= target_days:
        return ToolResult.error("Warning threshold must be less than target days")

    return ToolResult.success(
        data=rules,
        message=f"SLA rules configured: {stage} = {target_days} days (warning at {warning_days})",
    )


@mortgage_tool(
    name="escalate_sla_breach",
    description="Escalate SLA breach to appropriate personnel",
    agent_roles=["sla_tracker"],
    risk_level="MEDIUM",
    parameters={
        "loan_id": "Loan ID with SLA breach",
        "breach_type": "Type: stage_sla, closing_target, response_time",
        "severity": "Severity: warning, critical, severe",
        "notes": "Additional context for escalation",
    },
)
def escalate_sla_breach(
    loan_id: str,
    breach_type: str = "stage_sla",
    severity: str = "critical",
    notes: Optional[str] = None,
) -> ToolResult:
    """Escalate SLA breach."""
    loan = execute_single("""
        SELECT id, loan_number, borrower_name, stage,
               loan_officer_id, loan_amount
        FROM loans
        WHERE id = :id
    """, {"id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Get LO and manager info
    lo_info = execute_single("""
        SELECT u.id, COALESCE(es.full_name, u.email) as lo_name, u.email as lo_email,
               m.id as manager_id, COALESCE(ms.full_name, m.email) as manager_name, m.email as manager_email
        FROM users u
        LEFT JOIN email_signatures es ON es.user_id = u.id
        LEFT JOIN users m ON u.manager_id = m.id
        LEFT JOIN email_signatures ms ON ms.user_id = m.id
        WHERE u.id = :lo_id
    """, {"lo_id": loan.get("loan_officer_id")})

    import uuid
    escalation_id = f"ESC-{str(uuid.uuid4())[:8].upper()}"

    escalation_target = _get_escalation_target(severity)

    data = {
        "escalation_id": escalation_id,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "borrower_name": loan.get("borrower_name"),
        "current_stage": loan.get("stage"),
        "loan_amount": float(loan.get("loan_amount", 0)),
        "breach_type": breach_type,
        "severity": severity,
        "notes": notes,
        "escalated_to": {
            "role": escalation_target,
            "name": lo_info.get("manager_name") if lo_info and severity != "warning" else lo_info.get("lo_name") if lo_info else None,
            "email": lo_info.get("manager_email") if lo_info and severity != "warning" else lo_info.get("lo_email") if lo_info else None,
        },
        "lo_info": {
            "name": lo_info.get("lo_name") if lo_info else None,
            "email": lo_info.get("lo_email") if lo_info else None,
        },
        "escalated_at": datetime.now().isoformat(),
        "status": "open",
        "sla_due_date": (datetime.now() + timedelta(hours=4 if severity == "severe" else 24)).isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"SLA breach escalated: {loan.get('loan_number')} ({severity})",
    )


@mortgage_tool(
    name="get_sla_dashboard",
    description="Get SLA dashboard with key metrics and trends",
    agent_roles=["sla_tracker", "pipeline_analyst"],
    risk_level="LOW",
    parameters={
        "user_id": "Optional LO filter",
        "branch_id": "Optional branch filter",
        "period_days": "Number of days for trend analysis",
    },
)
def get_sla_dashboard(
    user_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    period_days: int = 30,
) -> ToolResult:
    """Get SLA dashboard metrics."""
    params = {}
    filters = ["stage NOT IN ('Funded')"]

    if user_id:
        filters.append("loan_officer_id = :user_id")
        params["user_id"] = user_id

    if branch_id:
        filters.append("branch_id = :branch_id")
        params["branch_id"] = branch_id

    where_sql = " AND ".join(filters)

    # Current pipeline status
    pipeline = execute_query(f"""
        SELECT id, loan_number, borrower_name, stage,
               stage_changed_at as stage_entered_at, loan_amount
        FROM loans
        WHERE {where_sql}
    """, params)

    # Categorize by SLA status
    compliant = []
    at_risk = []
    breached = []

    for loan in pipeline:
        sla = _calculate_loan_sla(loan)
        if sla["status"] == "breached":
            breached.append(sla)
        elif sla["status"] == "at_risk":
            at_risk.append(sla)
        else:
            compliant.append(sla)

    total = len(pipeline)
    compliance_rate = round(len(compliant) / total * 100, 1) if total > 0 else 100

    # By stage breakdown
    by_stage = {}
    for loan in pipeline:
        stage = loan.get("stage")
        if stage not in by_stage:
            by_stage[stage] = {"count": 0, "breached": 0, "at_risk": 0}
        by_stage[stage]["count"] += 1

    for b in breached:
        if b["stage"] in by_stage:
            by_stage[b["stage"]]["breached"] += 1

    for r in at_risk:
        if r["stage"] in by_stage:
            by_stage[r["stage"]]["at_risk"] += 1

    # Historical trend (simplified)
    params["days"] = period_days
    historical = execute_single(f"""
        SELECT
            COUNT(*) as total_funded,
            COUNT(CASE WHEN days_to_fund <= 30 THEN 1 END) as within_target
        FROM (
            SELECT
                id,
                EXTRACT(EPOCH FROM (funded_at - created_at))/86400 as days_to_fund
            FROM loans
            WHERE funded_at >= CURRENT_DATE - :days
            {"AND loan_officer_id = :user_id" if user_id else ""}
            {"AND branch_id = :branch_id" if branch_id else ""}
        ) funded_loans
    """, params)

    historical_rate = 0
    if historical and historical.get("total_funded"):
        historical_rate = round(
            (historical.get("within_target", 0) / historical.get("total_funded")) * 100, 1
        )

    data = {
        "current_pipeline": {
            "total": total,
            "compliant": len(compliant),
            "at_risk": len(at_risk),
            "breached": len(breached),
            "compliance_rate": compliance_rate,
        },
        "by_stage": by_stage,
        "breached_loans": breached[:5],
        "at_risk_loans": at_risk[:5],
        "historical": {
            "period_days": period_days,
            "total_funded": historical.get("total_funded", 0) if historical else 0,
            "target_compliance_rate": historical_rate,
        },
        "alerts": {
            "critical": len(breached),
            "warning": len(at_risk),
        },
        "generated_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"SLA Dashboard: {compliance_rate}% current compliance, {len(breached)} breached",
    )


# =============================================================================
# Helper Functions
# =============================================================================

def _calculate_loan_sla(loan: Dict) -> Dict:
    """Calculate SLA status for a loan."""
    stage = loan.get("stage", "")
    stage_entered = loan.get("stage_entered_at")

    sla_target = SLA_TARGETS.get(stage.lower(), 5)

    if stage_entered:
        if isinstance(stage_entered, str):
            stage_entered = datetime.strptime(stage_entered[:10], "%Y-%m-%d")
        days_in_stage = days_between(stage_entered, datetime.now())
    else:
        days_in_stage = 0

    if days_in_stage > sla_target:
        status = "breached"
        days_over = days_in_stage - sla_target
    elif days_in_stage >= sla_target - 1:
        status = "at_risk"
        days_over = 0
    else:
        status = "compliant"
        days_over = 0

    return {
        "loan_id": loan.get("id"),
        "loan_number": loan.get("loan_number"),
        "borrower_name": loan.get("borrower_name"),
        "stage": stage,
        "days_in_stage": days_in_stage,
        "sla_target": sla_target,
        "status": status,
        "days_over": days_over,
        "days_remaining": max(0, sla_target - days_in_stage),
    }


def _get_sla_action(sla_status: Dict) -> str:
    """Get recommended action for SLA status."""
    if sla_status["status"] == "breached":
        return f"URGENT: Escalate immediately. {sla_status['days_over']} days over SLA."
    elif sla_status["status"] == "at_risk":
        return f"Review loan status. Only {sla_status['days_remaining']} day(s) remaining."
    return "No action needed."


def _get_stage_performance(avg_days: float, target: int) -> str:
    """Classify stage performance."""
    if avg_days <= target * 0.7:
        return "excellent"
    elif avg_days <= target:
        return "good"
    elif avg_days <= target * 1.3:
        return "needs_improvement"
    return "critical"


def _get_proactive_action(stage: str) -> str:
    """Get proactive action for preventing SLA breach."""
    actions = {
        "processing": "Verify all documents received and complete initial review",
        "submitted": "Follow up with underwriting on submission status",
        "underwriting": "Check for pending conditions or questions",
        "approved": "Confirm all conditions cleared",
        "clear_to_close": "Confirm closing date and CD delivery",
        "docs_out": "Verify borrower received closing docs",
    }
    return actions.get(stage, "Review loan status and identify blockers")


def _get_escalation_target(severity: str) -> str:
    """Get escalation target based on severity."""
    targets = {
        "warning": "loan_officer",
        "critical": "manager",
        "severe": "senior_management",
    }
    return targets.get(severity, "manager")
