"""
Aria Trend Analysis Tools
==========================
Core @mortgage_tool for period-over-period business intelligence.

Public helpers (imported by tests and other modules)
-----------------------------------------------------
- _get_period_dates(time_window)  -> (start, end, prior_start, prior_end)
- _make_insight(domain, metric, label, current, prior, higher_is_better, unit) -> dict
- _owner_filter(scope, user_id, col) -> (sql_fragment, params)
- _safe_float(val, default) -> float
- _safe_int(val, default) -> int
- analyze_trends(...)            -> ToolResult  (registered @mortgage_tool)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import (
    mortgage_tool,
    ToolResult,
    execute_single,
    calculate_percentage_change,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

_WINDOW_DAYS: Dict[str, int] = {
    "week": 7,
    "month": 30,
    "quarter": 90,
}


def _get_period_dates(time_window: str) -> Tuple[str, str, str, str]:
    """
    Return (start, end, prior_start, prior_end) as YYYY-MM-DD strings.

    ``end`` is today.  ``start`` is ``end - window_days``.
    The prior period covers the same length immediately before start.
    """
    days = _WINDOW_DAYS.get(time_window, 30)
    now = datetime.now()
    end = now
    start = now - timedelta(days=days)
    prior_end = start
    prior_start = start - timedelta(days=days)
    fmt = "%Y-%m-%d"
    return (
        start.strftime(fmt),
        end.strftime(fmt),
        prior_start.strftime(fmt),
        prior_end.strftime(fmt),
    )


# ---------------------------------------------------------------------------
# Insight builder
# ---------------------------------------------------------------------------

_FLAT_THRESHOLD = 2.0  # delta_pct below which direction is "flat"


def _make_insight(
    domain: str,
    metric: str,
    label: str,
    current_value: float,
    prior_value: float,
    up_is_good: bool,
    unit: str = "count",
    context: str = "",
) -> Dict[str, Any]:
    """
    Build a normalised insight dict from raw current/prior values.

    ``up_is_good`` controls whether an upward move is positive.
    Uses calculate_percentage_change for delta (handles zero denominator).
    """
    delta_pct = calculate_percentage_change(prior_value, current_value)
    abs_delta = abs(delta_pct)

    if abs_delta < _FLAT_THRESHOLD:
        direction = "flat"
        is_positive = True  # neutral
    elif current_value > prior_value:
        direction = "up"
        is_positive = up_is_good
    else:
        direction = "down"
        is_positive = not up_is_good

    return {
        "domain": domain,
        "metric": metric,
        "label": label,
        "current_value": current_value,
        "prior_value": prior_value,
        "delta_pct": round(delta_pct, 2),
        "direction": direction,
        "significance": round(abs_delta, 2),
        "context": context,
        "is_positive": is_positive,
        "unit": unit,
    }


# ---------------------------------------------------------------------------
# Scope / owner filter
# ---------------------------------------------------------------------------

_ADMIN_ROLES: Set[str] = {"admin", "site_admin", "leadership", "management"}


def _owner_filter(
    user_role: str,
    user_id: int,
    col: str = "owner_id",
) -> Tuple[str, Dict[str, Any]]:
    """
    Return a (sql_fragment, params) pair for filtering rows by owner.

    Admin/leadership roles → no filter (see all records).
    Other roles → AND {col} = :scope_user_id
    """
    if user_role in _ADMIN_ROLES:
        return ("", {})
    return (f"AND {col} = :scope_user_id", {"scope_user_id": user_id})


# ---------------------------------------------------------------------------
# Safe type converters
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convert val to float, returning default on failure."""
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """Convert val to int, returning default on failure."""
    try:
        if val is None:
            return default
        return int(val)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Stub analyzer functions
# All share the signature: (cs, ce, ps, pe, uid, role) -> List[dict]
# cs = current_start, ce = current_end, ps = prior_start, pe = prior_end
# ---------------------------------------------------------------------------

def _analyze_leads(cs, ce, ps, pe, uid, role): return []
def _analyze_loans(cs, ce, ps, pe, uid, role): return []
def _analyze_pipeline(cs, ce, ps, pe, uid, role): return []
def _analyze_compliance(cs, ce, ps, pe, uid, role): return []
def _analyze_communication(cs, ce, ps, pe, uid, role): return []
def _analyze_dialer(cs, ce, ps, pe, uid, role): return []
def _analyze_referrals(cs, ce, ps, pe, uid, role): return []
def _analyze_mum(cs, ce, ps, pe, uid, role): return []
def _analyze_team(cs, ce, ps, pe, uid, role): return []
def _analyze_ai_ops(cs, ce, ps, pe, uid, role): return []
def _analyze_documents(cs, ce, ps, pe, uid, role): return []
def _analyze_applications(cs, ce, ps, pe, uid, role): return []
def _analyze_system(cs, ce, ps, pe, uid, role): return []


# ---------------------------------------------------------------------------
# Domain → analyzer mapping
# ---------------------------------------------------------------------------

_DOMAIN_ANALYZERS: Dict[str, Any] = {
    "leads":         _analyze_leads,
    "loans":         _analyze_loans,
    "pipeline":      _analyze_pipeline,
    "compliance":    _analyze_compliance,
    "communication": _analyze_communication,
    "dialer":        _analyze_dialer,
    "referrals":     _analyze_referrals,
    "mum":           _analyze_mum,
    "team":          _analyze_team,
    "ai_ops":        _analyze_ai_ops,
    "documents":     _analyze_documents,
    "applications":  _analyze_applications,
    "system":        _analyze_system,
}


# ---------------------------------------------------------------------------
# Role → allowed domain sets
# ---------------------------------------------------------------------------

_ROLE_DOMAINS: Dict[str, Set[str]] = {
    "sales":      {"leads", "loans", "pipeline", "compliance", "communication", "dialer", "referrals", "mum"},
    "processing": {"loans", "pipeline", "compliance", "documents"},
    "operations": {"loans", "pipeline", "compliance", "documents"},
}

_ALL_DOMAINS: Set[str] = set(_DOMAIN_ANALYZERS.keys())


def _domains_for_role(role: str) -> Set[str]:
    """Return the set of domains the given role may access."""
    return _ROLE_DOMAINS.get(role, _ALL_DOMAINS)


# ---------------------------------------------------------------------------
# Main @mortgage_tool
# ---------------------------------------------------------------------------

@mortgage_tool(
    name="analyze_trends",
    description=(
        "Analyze business trends and KPIs across the CRM. Computes period-over-period "
        "metrics for leads, loans, pipeline velocity, compliance, communication, dialer, "
        "referral partners, MUM portfolio, team performance, AI operations, documents, "
        "borrower applications, and system health. Results are emailed as a formatted "
        "HTML report."
    ),
    agent_roles=[
        "pipeline_analyst",
        "reporting_engine",
        "team_coach",
        "customer_intelligence",
        "compliance_checker",
        "lead_nurturer",
    ],
    risk_level="low",
    examples=[
        "What trends do you see?",
        "What trends do you see in my leads?",
        "Show me loan pipeline trends",
        "How is my team performing this month vs last?",
        "Any trends in referral partner activity?",
        "Give me a trend report for this quarter",
        "Email me a business intelligence report",
    ],
    parameters={
        "domain": (
            "Domain to analyze: all, leads, loans, pipeline, compliance, communication, "
            "dialer, referrals, mum, team, ai_ops, documents, applications, system"
        ),
        "time_window": "Comparison window: week, month, quarter",
        "user_email": "Email address to send the report to",
        "user_id": "ID of the requesting user",
        "user_role": "Permission role of the requesting user",
    },
)
def analyze_trends(
    domain: str = "all",
    time_window: str = "month",
    user_email: Optional[str] = None,
    user_id: Optional[int] = None,
    user_role: str = "sales",
) -> ToolResult:
    """
    Run period-over-period analysis across requested domains and email results.
    """
    # 1. Resolve period dates
    cs, ce, ps, pe = _get_period_dates(time_window)

    # 2. Determine domains to run
    allowed = _domains_for_role(user_role)
    if domain == "all":
        domains_to_run = allowed
    else:
        if domain not in _DOMAIN_ANALYZERS:
            return ToolResult.error(
                f"Unknown domain '{domain}'. Choose from: {', '.join(sorted(_DOMAIN_ANALYZERS))}"
            )
        if domain not in allowed:
            return ToolResult.error(
                f"Your role '{user_role}' does not have access to domain '{domain}'."
            )
        domains_to_run = {domain}

    # 3. Run each analyzer; collect insights; catch per-analyzer exceptions
    insights: List[Dict[str, Any]] = []
    errors: List[str] = []
    for dom in sorted(domains_to_run):
        analyzer = _DOMAIN_ANALYZERS[dom]
        try:
            result = analyzer(cs, ce, ps, pe, user_id, user_role)
            insights.extend(result)
        except Exception as e:
            logger.exception("Trend analyzer '%s' failed: %s", dom, e)
            errors.append(f"{dom}: {e}")

    # 4. Build period label
    fmt_display = "%b %-d"  # e.g. "Apr 7"
    try:
        cs_dt = datetime.strptime(cs, "%Y-%m-%d")
        ce_dt = datetime.strptime(ce, "%Y-%m-%d")
        ps_dt = datetime.strptime(ps, "%Y-%m-%d")
        pe_dt = datetime.strptime(pe, "%Y-%m-%d")
        period_label = (
            f"{cs_dt.strftime(fmt_display)} – {ce_dt.strftime(fmt_display)}, {ce_dt.year}"
            f" vs {ps_dt.strftime(fmt_display)} – {pe_dt.strftime(fmt_display)}, {pe_dt.year}"
        )
    except Exception:
        period_label = f"{cs} – {ce} vs {ps} – {pe}"

    # 5. Resolve email address
    resolved_email = user_email
    if not resolved_email and user_id is not None:
        row = execute_single(
            "SELECT email FROM users WHERE id = :uid",
            {"uid": user_id},
        )
        if row:
            resolved_email = row.get("email")

    if not resolved_email:
        warnings = ["No email address available — report not sent."]
        if errors:
            warnings.append(f"Analyzer errors: {'; '.join(errors)}")
        return ToolResult.partial(
            data={"insights": insights, "period_label": period_label},
            message="Trend analysis complete but no recipient email found.",
            warnings=warnings,
        )

    # 6. Render and send
    try:
        from services.trend_email import render_trend_report_html, send_trend_report

        html_body = render_trend_report_html(
            insights=insights,
            period_label=period_label,
            time_window=time_window,
        )
        send_result = send_trend_report(
            to_email=resolved_email,
            html_body=html_body,
            period_label=period_label,
            organization_id=None,
            user_id=user_id,
        )
    except Exception as e:
        logger.exception("Failed to send trend report: %s", e)
        return ToolResult.error(f"Failed to send trend report: {e}")

    base_msg = f"Trend report ({time_window}) sent to {resolved_email}. {len(insights)} insights across {len(domains_to_run)} domain(s)."
    if errors:
        return ToolResult.partial(
            data={"send_result": send_result, "insights_count": len(insights)},
            message=base_msg,
            warnings=[f"Analyzer errors: {'; '.join(errors)}"],
        )

    return ToolResult.success(
        data={"send_result": send_result, "insights_count": len(insights)},
        message=base_msg,
    )
