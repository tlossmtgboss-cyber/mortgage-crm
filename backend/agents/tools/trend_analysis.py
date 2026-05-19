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
    execute_query,
    execute_single,
    calculate_percentage_change,
    sql_date_subtract,
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

def _analyze_leads(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "owner_id")
    insights = []

    cur = execute_query(f"SELECT COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri = execute_query(f"SELECT COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    insights.append(_make_insight("leads", "new_lead_count", "New Leads", _safe_int(cur[0]["cnt"]) if cur else 0, _safe_int(pri[0]["cnt"]) if pri else 0, True, "count"))

    cur_sources, pri_sources = {}, {}
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT COALESCE(source, 'Unknown') as source, COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of} GROUP BY source ORDER BY cnt DESC LIMIT 10", {"s": s, "e": e, **op})
        d = {r["source"]: _safe_int(r["cnt"]) for r in rows}
        if tag == "cur":
            cur_sources = d
        else:
            pri_sources = d
    for src in cur_sources:
        if cur_sources[src] >= 3:
            insights.append(_make_insight("leads", f"source_{src}", f"Leads from {src}", cur_sources.get(src, 0), pri_sources.get(src, 0), True, "count"))

    cur_stages, pri_stages = {}, {}
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT stage, COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of} GROUP BY stage", {"s": s, "e": e, **op})
        d = {r["stage"]: _safe_int(r["cnt"]) for r in rows}
        if tag == "cur":
            cur_stages = d
        else:
            pri_stages = d
    for stage in ["Application", "Pre-Qualified", "Pre-Approved", "Closed"]:
        if cur_stages.get(stage, 0) > 0 or pri_stages.get(stage, 0) > 0:
            insights.append(_make_insight("leads", f"stage_{stage}", f"Leads at {stage}", cur_stages.get(stage, 0), pri_stages.get(stage, 0), True, "count"))

    cur_ttc = execute_single(
        f"SELECT AVG(EXTRACT(EPOCH FROM (first_contact_attempt_date - lead_received_date)) / 86400) as avg_days FROM leads WHERE first_contact_attempt_date IS NOT NULL AND lead_received_date IS NOT NULL AND created_at >= :s AND created_at <= :e {of}",
        {"s": cs, "e": ce, **op},
    )
    pri_ttc = execute_single(
        f"SELECT AVG(EXTRACT(EPOCH FROM (first_contact_attempt_date - lead_received_date)) / 86400) as avg_days FROM leads WHERE first_contact_attempt_date IS NOT NULL AND lead_received_date IS NOT NULL AND created_at >= :s AND created_at <= :e {of}",
        {"s": ps, "e": pe, **op},
    )
    cv = _safe_float(cur_ttc.get("avg_days")) if cur_ttc else 0
    pv = _safe_float(pri_ttc.get("avg_days")) if pri_ttc else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("leads", "avg_time_to_contact", "Avg Time to First Contact", cv, pv, False, "days"))

    cur_ai = execute_single(f"SELECT AVG(ai_score) as avg_score FROM leads WHERE ai_score IS NOT NULL AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_ai = execute_single(f"SELECT AVG(ai_score) as avg_score FROM leads WHERE ai_score IS NOT NULL AND created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    cv = _safe_float(cur_ai.get("avg_score")) if cur_ai else 0
    pv = _safe_float(pri_ai.get("avg_score")) if pri_ai else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("leads", "avg_ai_score", "Avg Lead AI Score", cv, pv, True, "count"))

    cur_stale = execute_query(f"SELECT COUNT(*) as cnt FROM leads WHERE last_contact < {sql_date_subtract(30)} AND stage NOT IN ('Closed','Funded','Dead','Withdrawn') {of}", op)
    cv = _safe_int(cur_stale[0]["cnt"]) if cur_stale else 0
    if cv > 0:
        insights.append(_make_insight("leads", "stale_leads", "Stale Leads (no contact 30+ days)", cv, 0, False, "count", "Leads with no contact in over 30 days"))

    return insights


def _analyze_loans(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "loan_officer_id")
    insights = []
    terminal = "('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE')"

    cur = execute_query(f"SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as vol FROM loans WHERE stage NOT IN {terminal} AND created_at <= :e {of}", {"e": ce, **op})
    pri = execute_query(f"SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as vol FROM loans WHERE stage NOT IN {terminal} AND created_at <= :e {of}", {"e": pe, **op})
    insights.append(_make_insight("loans", "active_count", "Active Pipeline Count", _safe_int(cur[0]["cnt"]) if cur else 0, _safe_int(pri[0]["cnt"]) if pri else 0, True, "count"))
    insights.append(_make_insight("loans", "active_volume", "Active Pipeline Volume", _safe_float(cur[0]["vol"]) if cur else 0, _safe_float(pri[0]["vol"]) if pri else 0, True, "currency"))

    cur_f = execute_query(f"SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as vol FROM loans WHERE funded_date >= :s AND funded_date <= :e {of}", {"s": cs, "e": ce, **op})
    pri_f = execute_query(f"SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as vol FROM loans WHERE funded_date >= :s AND funded_date <= :e {of}", {"s": ps, "e": pe, **op})
    insights.append(_make_insight("loans", "funded_count", "Funded Count", _safe_int(cur_f[0]["cnt"]) if cur_f else 0, _safe_int(pri_f[0]["cnt"]) if pri_f else 0, True, "count"))
    insights.append(_make_insight("loans", "funded_volume", "Funded Volume", _safe_float(cur_f[0]["vol"]) if cur_f else 0, _safe_float(pri_f[0]["vol"]) if pri_f else 0, True, "currency"))

    cur_avg = execute_single(f"SELECT AVG(amount) as avg_amt FROM loans WHERE created_at >= :s AND created_at <= :e AND amount > 0 {of}", {"s": cs, "e": ce, **op})
    pri_avg = execute_single(f"SELECT AVG(amount) as avg_amt FROM loans WHERE created_at >= :s AND created_at <= :e AND amount > 0 {of}", {"s": ps, "e": pe, **op})
    insights.append(_make_insight("loans", "avg_loan_amount", "Avg Loan Amount", _safe_float(cur_avg.get("avg_amt")) if cur_avg else 0, _safe_float(pri_avg.get("avg_amt")) if pri_avg else 0, True, "currency"))

    cur_rate = execute_single(f"SELECT AVG(rate) as avg_rate FROM loans WHERE created_at >= :s AND created_at <= :e AND rate > 0 {of}", {"s": cs, "e": ce, **op})
    pri_rate = execute_single(f"SELECT AVG(rate) as avg_rate FROM loans WHERE created_at >= :s AND created_at <= :e AND rate > 0 {of}", {"s": ps, "e": pe, **op})
    insights.append(_make_insight("loans", "avg_rate", "Avg Interest Rate", _safe_float(cur_rate.get("avg_rate")) if cur_rate else 0, _safe_float(pri_rate.get("avg_rate")) if pri_rate else 0, False, "percent"))

    cur_cycle = execute_single(
        f"SELECT AVG(EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400) as avg_days FROM loans WHERE funded_date IS NOT NULL AND application_date IS NOT NULL AND funded_date >= :s AND funded_date <= :e {of}",
        {"s": cs, "e": ce, **op},
    )
    pri_cycle = execute_single(
        f"SELECT AVG(EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400) as avg_days FROM loans WHERE funded_date IS NOT NULL AND application_date IS NOT NULL AND funded_date >= :s AND funded_date <= :e {of}",
        {"s": ps, "e": pe, **op},
    )
    cv = _safe_float(cur_cycle.get("avg_days")) if cur_cycle else 0
    pv = _safe_float(pri_cycle.get("avg_days")) if pri_cycle else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("loans", "avg_cycle_time", "Avg Cycle Time (App to Funded)", cv, pv, False, "days"))

    cur_stg, pri_stg = {}, {}
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT stage, COUNT(*) as cnt FROM loans WHERE created_at >= :s AND created_at <= :e {of} GROUP BY stage ORDER BY cnt DESC", {"s": s, "e": e, **op})
        d = {r["stage"]: _safe_int(r["cnt"]) for r in rows}
        if tag == "cur":
            cur_stg = d
        else:
            pri_stg = d
    for stg in ["PROCESSING", "UNDERWRITING", "CONDITIONAL_APPROVAL", "APPROVED", "CTC", "CLEAR_TO_CLOSE"]:
        if cur_stg.get(stg, 0) > 0 or pri_stg.get(stg, 0) > 0:
            insights.append(_make_insight("loans", f"stage_{stg}", f"Loans in {stg.replace('_', ' ').title()}", cur_stg.get(stg, 0), pri_stg.get(stg, 0), True, "count"))

    cur_types, pri_types = {}, {}
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT COALESCE(loan_type,'Unknown') as loan_type, COUNT(*) as cnt FROM loans WHERE created_at >= :s AND created_at <= :e {of} GROUP BY loan_type", {"s": s, "e": e, **op})
        d = {r["loan_type"]: _safe_int(r["cnt"]) for r in rows}
        if tag == "cur":
            cur_types = d
        else:
            pri_types = d
    for lt in cur_types:
        if cur_types[lt] >= 2:
            insights.append(_make_insight("loans", f"type_{lt}", f"{lt.upper()} Loans", cur_types.get(lt, 0), pri_types.get(lt, 0), True, "count"))

    return insights


def _analyze_pipeline(cs, ce, ps, pe, uid, role):
    of_task, op_task = _owner_filter(role, uid, "owner_id")
    insights = []

    cur_vel = execute_query(
        "SELECT to_stage, AVG(duration_in_previous_stage) as avg_days FROM stage_history WHERE entity_type = 'loan' AND changed_at >= :s AND changed_at <= :e GROUP BY to_stage ORDER BY avg_days DESC LIMIT 20",
        {"s": cs, "e": ce},
    )
    pri_vel = execute_query(
        "SELECT to_stage, AVG(duration_in_previous_stage) as avg_days FROM stage_history WHERE entity_type = 'loan' AND changed_at >= :s AND changed_at <= :e GROUP BY to_stage ORDER BY avg_days DESC LIMIT 20",
        {"s": ps, "e": pe},
    )
    cur_vel_map = {r["to_stage"]: _safe_float(r["avg_days"]) for r in cur_vel}
    pri_vel_map = {r["to_stage"]: _safe_float(r["avg_days"]) for r in pri_vel}
    for stage in cur_vel_map:
        cv, pv = cur_vel_map.get(stage, 0), pri_vel_map.get(stage, 0)
        if cv > 0 and pv > 0:
            insights.append(_make_insight("pipeline", f"velocity_{stage}", f"Avg Days to {stage.replace('_', ' ').title()}", cv, pv, False, "days"))

    cur_task_rate, pri_task_rate = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single(f"SELECT COUNT(*) as cnt FROM tasks WHERE created_at >= :s AND created_at <= :e {of_task}", {"s": s, "e": e, **op_task})
        done = execute_single(f"SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND created_at >= :s AND created_at <= :e {of_task}", {"s": s, "e": e, **op_task})
        t = _safe_int(total.get("cnt")) if total else 0
        d = _safe_int(done.get("cnt")) if done else 0
        rate = (d / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_task_rate = rate
        else:
            pri_task_rate = rate
    insights.append(_make_insight("pipeline", "task_completion_rate", "Task Completion Rate", cur_task_rate, pri_task_rate, True, "percent"))

    cur_on_time, pri_on_time = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        on_time = execute_single(f"SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND due_date IS NOT NULL AND completed_at <= due_date AND created_at >= :s AND created_at <= :e {of_task}", {"s": s, "e": e, **op_task})
        total_due = execute_single(f"SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND due_date IS NOT NULL AND created_at >= :s AND created_at <= :e {of_task}", {"s": s, "e": e, **op_task})
        ot = _safe_int(on_time.get("cnt")) if on_time else 0
        td = _safe_int(total_due.get("cnt")) if total_due else 0
        rate = (ot / td * 100) if td > 0 else 0
        if tag == "cur":
            cur_on_time = rate
        else:
            pri_on_time = rate
    insights.append(_make_insight("pipeline", "task_on_time_rate", "Task On-Time Rate", cur_on_time, pri_on_time, True, "percent"))

    cur_esc = execute_single("SELECT COUNT(*) as cnt FROM escalation_records WHERE escalated_at >= :s AND escalated_at <= :e", {"s": cs, "e": ce})
    pri_esc = execute_single("SELECT COUNT(*) as cnt FROM escalation_records WHERE escalated_at >= :s AND escalated_at <= :e", {"s": ps, "e": pe})
    cv = _safe_int(cur_esc.get("cnt")) if cur_esc else 0
    pv = _safe_int(pri_esc.get("cnt")) if pri_esc else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("pipeline", "escalation_count", "Escalations", cv, pv, False, "count"))

    cur_res = execute_single("SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - escalated_at)) / 3600) as avg_hrs FROM escalation_records WHERE resolved_at IS NOT NULL AND escalated_at >= :s AND escalated_at <= :e", {"s": cs, "e": ce})
    pri_res = execute_single("SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - escalated_at)) / 3600) as avg_hrs FROM escalation_records WHERE resolved_at IS NOT NULL AND escalated_at >= :s AND escalated_at <= :e", {"s": ps, "e": pe})
    cv = _safe_float(cur_res.get("avg_hrs")) if cur_res else 0
    pv = _safe_float(pri_res.get("avg_hrs")) if pri_res else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("pipeline", "avg_escalation_resolution_hrs", "Avg Escalation Resolution (hrs)", cv, pv, False, "count"))

    return insights


def _analyze_compliance(cs, ce, ps, pe, uid, role):
    insights = []

    cur_le, pri_le = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM disclosure_events WHERE disclosure_type = 'LOAN_ESTIMATE' AND sent_at >= :s AND sent_at <= :e", {"s": s, "e": e})
        on_time = execute_single("SELECT COUNT(*) as cnt FROM disclosure_events WHERE disclosure_type = 'LOAN_ESTIMATE' AND is_on_time = true AND sent_at >= :s AND sent_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        ot = _safe_int(on_time.get("cnt")) if on_time else 0
        rate = (ot / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_le = rate
        else:
            pri_le = rate
    insights.append(_make_insight("compliance", "trid_le_compliance", "TRID LE Compliance", cur_le, pri_le, True, "percent"))

    cur_cd, pri_cd = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM disclosure_events WHERE disclosure_type = 'CLOSING_DISCLOSURE' AND sent_at >= :s AND sent_at <= :e", {"s": s, "e": e})
        on_time = execute_single("SELECT COUNT(*) as cnt FROM disclosure_events WHERE disclosure_type = 'CLOSING_DISCLOSURE' AND is_on_time = true AND sent_at >= :s AND sent_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        ot = _safe_int(on_time.get("cnt")) if on_time else 0
        rate = (ot / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_cd = rate
        else:
            pri_cd = rate
    insights.append(_make_insight("compliance", "trid_cd_compliance", "TRID CD Compliance", cur_cd, pri_cd, True, "percent"))

    cur_aa, pri_aa = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM adverse_action_notices WHERE denial_date >= :s AND denial_date <= :e", {"s": s, "e": e})
        on_time = execute_single("SELECT COUNT(*) as cnt FROM adverse_action_notices WHERE is_on_time = true AND denial_date >= :s AND denial_date <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        ot = _safe_int(on_time.get("cnt")) if on_time else 0
        rate = (ot / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_aa = rate
        else:
            pri_aa = rate
    if cur_aa > 0 or pri_aa > 0:
        insights.append(_make_insight("compliance", "adverse_action_timeliness", "Adverse Action Timeliness", cur_aa, pri_aa, True, "percent"))

    cur_viol = execute_single("SELECT COUNT(*) as cnt FROM loan_fees WHERE is_violation = true AND created_at >= :s AND created_at <= :e", {"s": cs, "e": ce})
    pri_viol = execute_single("SELECT COUNT(*) as cnt FROM loan_fees WHERE is_violation = true AND created_at >= :s AND created_at <= :e", {"s": ps, "e": pe})
    cv = _safe_int(cur_viol.get("cnt")) if cur_viol else 0
    pv = _safe_int(pri_viol.get("cnt")) if pri_viol else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("compliance", "fee_violations", "Fee Tolerance Violations", cv, pv, False, "count"))

    for severity in ["critical", "high"]:
        cur_a = execute_single("SELECT COUNT(*) as cnt FROM compliance_alerts WHERE severity = :sev AND status = 'open' AND created_at <= :e", {"sev": severity, "e": ce})
        pri_a = execute_single("SELECT COUNT(*) as cnt FROM compliance_alerts WHERE severity = :sev AND status = 'open' AND created_at <= :e", {"sev": severity, "e": pe})
        cv = _safe_int(cur_a.get("cnt")) if cur_a else 0
        pv = _safe_int(pri_a.get("cnt")) if pri_a else 0
        if cv > 0 or pv > 0:
            insights.append(_make_insight("compliance", f"open_alerts_{severity}", f"Open {severity.title()} Alerts", cv, pv, False, "count"))

    return insights


def _analyze_communication(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "user_id")
    insights = []

    cur_acts, pri_acts = {}, {}
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT type, COUNT(*) as cnt FROM activities WHERE created_at >= :s AND created_at <= :e {of} GROUP BY type", {"s": s, "e": e, **op})
        d = {r["type"]: _safe_int(r["cnt"]) for r in rows}
        if tag == "cur":
            cur_acts = d
        else:
            pri_acts = d
    insights.append(_make_insight("communication", "total_activities", "Total Activities", sum(cur_acts.values()), sum(pri_acts.values()), True, "count"))
    for atype in ["EMAIL", "CALL", "SMS", "MEETING"]:
        if cur_acts.get(atype, 0) > 0 or pri_acts.get(atype, 0) > 0:
            insights.append(_make_insight("communication", f"activity_{atype.lower()}", f"{atype.title()} Activities", cur_acts.get(atype, 0), pri_acts.get(atype, 0), True, "count"))

    cur_email_in, cur_email_out, pri_email_in, pri_email_out = 0, 0, 0, 0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT direction, COUNT(*) as cnt FROM email_messages WHERE created_at >= :s AND created_at <= :e {of} GROUP BY direction", {"s": s, "e": e, **op})
        d = {r["direction"]: _safe_int(r["cnt"]) for r in rows}
        if tag == "cur":
            cur_email_in, cur_email_out = d.get("inbound", 0), d.get("outbound", 0)
        else:
            pri_email_in, pri_email_out = d.get("inbound", 0), d.get("outbound", 0)
    insights.append(_make_insight("communication", "emails_inbound", "Inbound Emails", cur_email_in, pri_email_in, True, "count"))
    insights.append(_make_insight("communication", "emails_outbound", "Outbound Emails", cur_email_out, pri_email_out, True, "count"))

    cur_sms_total = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE direction = 'outbound' AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    cur_sms_del = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE direction = 'outbound' AND status = 'delivered' AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_sms_total = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE direction = 'outbound' AND created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    pri_sms_del = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE direction = 'outbound' AND status = 'delivered' AND created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    ct = _safe_int(cur_sms_total.get("cnt")) if cur_sms_total else 0
    cd = _safe_int(cur_sms_del.get("cnt")) if cur_sms_del else 0
    pt = _safe_int(pri_sms_total.get("cnt")) if pri_sms_total else 0
    pd_v = _safe_int(pri_sms_del.get("cnt")) if pri_sms_del else 0
    cur_sms_rate = (cd / ct * 100) if ct > 0 else 0
    pri_sms_rate = (pd_v / pt * 100) if pt > 0 else 0
    if ct > 0 or pt > 0:
        insights.append(_make_insight("communication", "sms_delivery_rate", "SMS Delivery Rate", cur_sms_rate, pri_sms_rate, True, "percent"))

    cur_ai_sms = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE ai_generated = true AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    ai_cnt = _safe_int(cur_ai_sms.get("cnt")) if cur_ai_sms else 0
    ai_pct = (ai_cnt / ct * 100) if ct > 0 else 0
    if ai_cnt > 0:
        insights.append(_make_insight("communication", "ai_message_pct", "AI-Generated SMS %", ai_pct, 0, True, "percent"))

    return insights


def _analyze_dialer(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "agent_id")
    insights = []

    cur_calls = execute_single(f"SELECT COUNT(*) as cnt FROM call_logs WHERE created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_calls = execute_single(f"SELECT COUNT(*) as cnt FROM call_logs WHERE created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    insights.append(_make_insight("dialer", "total_calls", "Total Calls", _safe_int(cur_calls.get("cnt")) if cur_calls else 0, _safe_int(pri_calls.get("cnt")) if pri_calls else 0, True, "count"))

    cur_dur = execute_single(f"SELECT AVG(duration_seconds) as avg_dur FROM call_logs WHERE duration_seconds > 0 AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_dur = execute_single(f"SELECT AVG(duration_seconds) as avg_dur FROM call_logs WHERE duration_seconds > 0 AND created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    cv = _safe_float(cur_dur.get("avg_dur")) / 60 if cur_dur and cur_dur.get("avg_dur") else 0
    pv = _safe_float(pri_dur.get("avg_dur")) / 60 if pri_dur and pri_dur.get("avg_dur") else 0
    insights.append(_make_insight("dialer", "avg_call_duration_min", "Avg Call Duration (min)", round(cv, 1), round(pv, 1), True, "count"))

    cur_connect, pri_connect = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single(f"SELECT COUNT(*) as cnt FROM call_logs WHERE created_at >= :s AND created_at <= :e {of}", {"s": s, "e": e, **op})
        connected = execute_single(f"SELECT COUNT(*) as cnt FROM call_logs WHERE outcome = 'COMPLETED' AND created_at >= :s AND created_at <= :e {of}", {"s": s, "e": e, **op})
        t = _safe_int(total.get("cnt")) if total else 0
        c = _safe_int(connected.get("cnt")) if connected else 0
        rate = (c / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_connect = rate
        else:
            pri_connect = rate
    insights.append(_make_insight("dialer", "connect_rate", "Call Connect Rate", cur_connect, pri_connect, True, "percent"))

    cur_outcomes, pri_outcomes = {}, {}
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT outcome, COUNT(*) as cnt FROM call_logs WHERE created_at >= :s AND created_at <= :e {of} GROUP BY outcome", {"s": s, "e": e, **op})
        d = {r["outcome"]: _safe_int(r["cnt"]) for r in rows}
        if tag == "cur":
            cur_outcomes = d
        else:
            pri_outcomes = d
    for outcome in ["NO_ANSWER", "BUSY", "FAILED"]:
        if cur_outcomes.get(outcome, 0) > 0 or pri_outcomes.get(outcome, 0) > 0:
            insights.append(_make_insight("dialer", f"outcome_{outcome.lower()}", f"{outcome.replace('_', ' ').title()} Calls", cur_outcomes.get(outcome, 0), pri_outcomes.get(outcome, 0), False, "count"))

    cur_sess = execute_single(f"SELECT AVG(CASE WHEN total_tasks > 0 THEN completed_tasks * 100.0 / total_tasks ELSE 0 END) as avg_rate FROM dialer_sessions WHERE created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_sess = execute_single(f"SELECT AVG(CASE WHEN total_tasks > 0 THEN completed_tasks * 100.0 / total_tasks ELSE 0 END) as avg_rate FROM dialer_sessions WHERE created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    cv = _safe_float(cur_sess.get("avg_rate")) if cur_sess else 0
    pv = _safe_float(pri_sess.get("avg_rate")) if pri_sess else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("dialer", "session_completion_rate", "Dialer Session Completion", cv, pv, True, "percent"))

    return insights


def _analyze_referrals(cs, ce, ps, pe, uid, role):
    insights = []

    cur_new = execute_single("SELECT COUNT(*) as cnt FROM referral_partners WHERE created_at >= :s AND created_at <= :e", {"s": cs, "e": ce})
    pri_new = execute_single("SELECT COUNT(*) as cnt FROM referral_partners WHERE created_at >= :s AND created_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("referrals", "new_partners", "New Referral Partners", _safe_int(cur_new.get("cnt")) if cur_new else 0, _safe_int(pri_new.get("cnt")) if pri_new else 0, True, "count"))

    cur_active = execute_single("SELECT COUNT(*) as cnt FROM referral_partners WHERE status = 'active' AND last_interaction >= :s", {"s": cs})
    pri_active = execute_single("SELECT COUNT(*) as cnt FROM referral_partners WHERE status = 'active' AND last_interaction >= :s", {"s": ps})
    insights.append(_make_insight("referrals", "active_partners", "Active Partners (contacted)", _safe_int(cur_active.get("cnt")) if cur_active else 0, _safe_int(pri_active.get("cnt")) if pri_active else 0, True, "count"))

    cur_dormant = execute_single(f"SELECT COUNT(*) as cnt FROM referral_partners WHERE status = 'active' AND (last_interaction IS NULL OR last_interaction < {sql_date_subtract(90)})")
    cv = _safe_int(cur_dormant.get("cnt")) if cur_dormant else 0
    if cv > 0:
        insights.append(_make_insight("referrals", "dormant_partners", "Dormant Partners (90+ days)", cv, 0, False, "count"))

    cur_recip = execute_single("SELECT AVG(reciprocity_score) as avg_score FROM referral_partners WHERE status = 'active' AND reciprocity_score IS NOT NULL")
    if cur_recip and cur_recip.get("avg_score"):
        insights.append(_make_insight("referrals", "avg_reciprocity", "Avg Reciprocity Score", _safe_float(cur_recip.get("avg_score")), 0, True, "count", "Higher = more balanced give/get"))

    tiers = execute_query("SELECT COALESCE(loyalty_tier,'none') as tier, COUNT(*) as cnt FROM referral_partners WHERE status = 'active' GROUP BY loyalty_tier ORDER BY cnt DESC")
    for row in tiers:
        if row.get("tier") and _safe_int(row["cnt"]) > 0:
            insights.append(_make_insight("referrals", f"tier_{row['tier']}", f"{row['tier'].title()} Tier Partners", _safe_int(row["cnt"]), 0, True, "count"))

    top = execute_query("SELECT name, COALESCE(volume,0) as vol, referrals_in, closed_loans FROM referral_partners WHERE status = 'active' ORDER BY volume DESC LIMIT 5")
    for i, row in enumerate(top):
        insights.append(_make_insight("referrals", f"top_partner_{i+1}", f"#{i+1} {row['name']}", _safe_float(row["vol"]), 0, True, "currency", f"{_safe_int(row.get('referrals_in', 0))} referrals, {_safe_int(row.get('closed_loans', 0))} closed"))

    return insights


def _analyze_mum(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "user_id")
    insights = []

    cur_port = execute_single(f"SELECT COUNT(*) as cnt, COALESCE(SUM(current_loan_amount),0) as bal FROM mum_clients WHERE status = 'active' {of}", op)
    insights.append(_make_insight("mum", "portfolio_size", "MUM Portfolio Size", _safe_int(cur_port.get("cnt")) if cur_port else 0, 0, True, "count"))
    insights.append(_make_insight("mum", "portfolio_balance", "Portfolio Total Balance", _safe_float(cur_port.get("bal")) if cur_port else 0, 0, True, "currency"))

    cur_refi = execute_single(f"SELECT COUNT(*) as cnt, COALESCE(SUM(estimated_savings),0) as savings FROM mum_clients WHERE refinance_opportunity = true {of}", op)
    insights.append(_make_insight("mum", "refi_opportunities", "Refi Opportunities", _safe_int(cur_refi.get("cnt")) if cur_refi else 0, 0, True, "count"))
    insights.append(_make_insight("mum", "refi_potential_savings", "Potential Refi Savings", _safe_float(cur_refi.get("savings")) if cur_refi else 0, 0, True, "currency"))

    cur_eng = execute_single(f"SELECT AVG(engagement_score) as avg_eng FROM mum_clients WHERE engagement_score IS NOT NULL {of}", op)
    insights.append(_make_insight("mum", "avg_engagement", "Avg Engagement Score", _safe_float(cur_eng.get("avg_eng")) if cur_eng else 0, 0, True, "count"))

    stale = execute_single(f"SELECT COUNT(*) as cnt FROM mum_clients WHERE status = 'active' AND (last_contact IS NULL OR last_contact < {sql_date_subtract(60)}) {of}", op)
    cv = _safe_int(stale.get("cnt")) if stale else 0
    if cv > 0:
        insights.append(_make_insight("mum", "stale_mum_contacts", "MUM Clients Needing Contact (60+ days)", cv, 0, False, "count"))

    upcoming = execute_single(f"SELECT COUNT(*) as cnt FROM mum_clients WHERE next_touchpoint >= :s AND next_touchpoint <= :e {of}", {"s": cs, "e": ce, **op})
    insights.append(_make_insight("mum", "upcoming_touchpoints", "Upcoming Touchpoints", _safe_int(upcoming.get("cnt")) if upcoming else 0, 0, True, "count"))

    refs = execute_single(f"SELECT COALESCE(SUM(referrals_sent),0) as total FROM mum_clients {of}", op)
    insights.append(_make_insight("mum", "client_referrals", "Client Referrals Generated", _safe_int(refs.get("total")) if refs else 0, 0, True, "count"))

    return insights


def _analyze_team(cs, ce, ps, pe, uid, role):
    if role in ("sales", "processing", "operations"):
        return []
    insights = []

    cur_lo = execute_query(
        "SELECT u.first_name || ' ' || u.last_name as lo_name, COUNT(l.id) as cnt, COALESCE(SUM(l.amount),0) as vol FROM loans l JOIN users u ON l.loan_officer_id = u.id WHERE l.funded_date >= :s AND l.funded_date <= :e GROUP BY u.id, u.first_name, u.last_name ORDER BY vol DESC LIMIT 10",
        {"s": cs, "e": ce},
    )
    pri_lo = execute_query(
        "SELECT u.first_name || ' ' || u.last_name as lo_name, COUNT(l.id) as cnt, COALESCE(SUM(l.amount),0) as vol FROM loans l JOIN users u ON l.loan_officer_id = u.id WHERE l.funded_date >= :s AND l.funded_date <= :e GROUP BY u.id, u.first_name, u.last_name ORDER BY vol DESC LIMIT 10",
        {"s": ps, "e": pe},
    )
    pri_lo_map = {r["lo_name"]: _safe_float(r["vol"]) for r in pri_lo}
    for row in cur_lo:
        name = row["lo_name"]
        insights.append(_make_insight("team", f"lo_volume_{name}", f"{name} — Funded Volume", _safe_float(row["vol"]), pri_lo_map.get(name, 0), True, "currency"))

    cur_leads = execute_query(
        "SELECT u.first_name || ' ' || u.last_name as lo_name, COUNT(l.id) as cnt FROM leads l JOIN users u ON l.owner_id = u.id WHERE l.created_at >= :s AND l.created_at <= :e GROUP BY u.id, u.first_name, u.last_name ORDER BY cnt DESC LIMIT 10",
        {"s": cs, "e": ce},
    )
    pri_leads = execute_query(
        "SELECT u.first_name || ' ' || u.last_name as lo_name, COUNT(l.id) as cnt FROM leads l JOIN users u ON l.owner_id = u.id WHERE l.created_at >= :s AND l.created_at <= :e GROUP BY u.id, u.first_name, u.last_name ORDER BY cnt DESC LIMIT 10",
        {"s": ps, "e": pe},
    )
    pri_leads_map = {r["lo_name"]: _safe_int(r["cnt"]) for r in pri_leads}
    for row in cur_leads:
        name = row["lo_name"]
        insights.append(_make_insight("team", f"lo_leads_{name}", f"{name} — New Leads", _safe_int(row["cnt"]), pri_leads_map.get(name, 0), True, "count"))

    cur_resp = execute_query(
        "SELECT u.first_name || ' ' || u.last_name as lo_name, AVG(EXTRACT(EPOCH FROM (l.first_contact_attempt_date - l.lead_received_date)) / 86400) as avg_days FROM leads l JOIN users u ON l.owner_id = u.id WHERE l.first_contact_attempt_date IS NOT NULL AND l.lead_received_date IS NOT NULL AND l.created_at >= :s AND l.created_at <= :e GROUP BY u.id, u.first_name, u.last_name ORDER BY avg_days ASC LIMIT 10",
        {"s": cs, "e": ce},
    )
    for row in cur_resp:
        if row.get("avg_days") is not None:
            insights.append(_make_insight("team", f"lo_response_{row['lo_name']}", f"{row['lo_name']} — Avg Response Time", _safe_float(row["avg_days"]), 0, False, "days"))

    return insights


def _analyze_ai_ops(cs, ce, ps, pe, uid, role):
    if role not in ("admin", "site_admin", "leadership", "management"):
        return []
    insights = []

    cur_approval, pri_approval = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM ai_actions WHERE created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        approved = execute_single("SELECT COUNT(*) as cnt FROM ai_actions WHERE status IN ('approved','auto_approved') AND created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        a = _safe_int(approved.get("cnt")) if approved else 0
        rate = (a / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_approval = rate
        else:
            pri_approval = rate
    insights.append(_make_insight("ai_ops", "ai_approval_rate", "AI Action Approval Rate", cur_approval, pri_approval, True, "percent"))

    cur_auto, pri_auto = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM ai_actions WHERE created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        auto = execute_single("SELECT COUNT(*) as cnt FROM ai_actions WHERE status = 'auto_approved' AND created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        a = _safe_int(auto.get("cnt")) if auto else 0
        rate = (a / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_auto = rate
        else:
            pri_auto = rate
    insights.append(_make_insight("ai_ops", "autonomous_rate", "Autonomous Execution Rate", cur_auto, pri_auto, True, "percent"))

    cur_fb = execute_single("SELECT COUNT(*) as cnt FROM ai_feedback_logs WHERE created_at >= :s AND created_at <= :e", {"s": cs, "e": ce})
    pri_fb = execute_single("SELECT COUNT(*) as cnt FROM ai_feedback_logs WHERE created_at >= :s AND created_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("ai_ops", "feedback_volume", "AI Feedback Reports", _safe_int(cur_fb.get("cnt")) if cur_fb else 0, _safe_int(pri_fb.get("cnt")) if pri_fb else 0, False, "count"))

    cur_cost = execute_single("SELECT COALESCE(SUM(cost_estimate),0) as cost, COALESCE(SUM(tokens_used),0) as tokens FROM ai_audit_logs WHERE created_at >= :s AND created_at <= :e", {"s": cs, "e": ce})
    pri_cost = execute_single("SELECT COALESCE(SUM(cost_estimate),0) as cost, COALESCE(SUM(tokens_used),0) as tokens FROM ai_audit_logs WHERE created_at >= :s AND created_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("ai_ops", "ai_cost", "AI Cost", _safe_float(cur_cost.get("cost")) if cur_cost else 0, _safe_float(pri_cost.get("cost")) if pri_cost else 0, False, "currency"))
    insights.append(_make_insight("ai_ops", "ai_tokens", "AI Tokens Used", _safe_float(cur_cost.get("tokens")) if cur_cost else 0, _safe_float(pri_cost.get("tokens")) if pri_cost else 0, False, "count"))

    return insights


def _analyze_documents(cs, ce, ps, pe, uid, role):
    insights = []

    cur_docs = execute_single("SELECT COUNT(*) as cnt FROM documents WHERE uploaded_at >= :s AND uploaded_at <= :e", {"s": cs, "e": ce})
    pri_docs = execute_single("SELECT COUNT(*) as cnt FROM documents WHERE uploaded_at >= :s AND uploaded_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("documents", "docs_uploaded", "Documents Uploaded", _safe_int(cur_docs.get("cnt")) if cur_docs else 0, _safe_int(pri_docs.get("cnt")) if pri_docs else 0, True, "count"))

    cur_match, pri_match = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM email_intakes WHERE received_at >= :s AND received_at <= :e", {"s": s, "e": e})
        matched = execute_single("SELECT COUNT(*) as cnt FROM email_intakes WHERE match_status = 'MATCHED' AND received_at >= :s AND received_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        m = _safe_int(matched.get("cnt")) if matched else 0
        rate = (m / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_match = rate
        else:
            pri_match = rate
    if cur_match > 0 or pri_match > 0:
        insights.append(_make_insight("documents", "intake_match_rate", "Email Intake Match Rate", cur_match, pri_match, True, "percent"))

    cur_class, pri_class = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM attachment_intakes WHERE created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        classified = execute_single("SELECT COUNT(*) as cnt FROM attachment_intakes WHERE classification_status = 'CLASSIFIED' AND created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        c = _safe_int(classified.get("cnt")) if classified else 0
        rate = (c / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_class = rate
        else:
            pri_class = rate
    insights.append(_make_insight("documents", "classification_rate", "AI Classification Rate", cur_class, pri_class, True, "percent"))

    return insights


def _analyze_applications(cs, ce, ps, pe, uid, role):
    insights = []

    cur_starts = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE started_at >= :s AND started_at <= :e", {"s": cs, "e": ce})
    pri_starts = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE started_at >= :s AND started_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("applications", "app_starts", "Application Starts", _safe_int(cur_starts.get("cnt")) if cur_starts else 0, _safe_int(pri_starts.get("cnt")) if pri_starts else 0, True, "count"))

    cur_comp, pri_comp = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE started_at >= :s AND started_at <= :e", {"s": s, "e": e})
        submitted = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE status = 'SUBMITTED' AND started_at >= :s AND started_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        sub = _safe_int(submitted.get("cnt")) if submitted else 0
        rate = (sub / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_comp = rate
        else:
            pri_comp = rate
    insights.append(_make_insight("applications", "completion_rate", "Application Completion Rate", cur_comp, pri_comp, True, "percent"))

    cur_time = execute_single("SELECT AVG(time_spent_seconds) / 60 as avg_min FROM borrower_applications WHERE status = 'SUBMITTED' AND started_at >= :s AND started_at <= :e", {"s": cs, "e": ce})
    pri_time = execute_single("SELECT AVG(time_spent_seconds) / 60 as avg_min FROM borrower_applications WHERE status = 'SUBMITTED' AND started_at >= :s AND started_at <= :e", {"s": ps, "e": pe})
    cv = _safe_float(cur_time.get("avg_min")) if cur_time else 0
    pv = _safe_float(pri_time.get("avg_min")) if pri_time else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("applications", "avg_completion_time", "Avg Completion Time (min)", cv, pv, False, "count"))

    cur_exp = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE status = 'EXPIRED' AND started_at >= :s AND started_at <= :e", {"s": cs, "e": ce})
    pri_exp = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE status = 'EXPIRED' AND started_at >= :s AND started_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("applications", "expired_apps", "Expired Applications", _safe_int(cur_exp.get("cnt")) if cur_exp else 0, _safe_int(pri_exp.get("cnt")) if pri_exp else 0, False, "count"))

    return insights


def _analyze_system(cs, ce, ps, pe, uid, role):
    if role not in ("admin", "site_admin"):
        return []
    insights = []

    cur_snap = execute_single("SELECT active_users_total, active_users_with_2fa, failed_login_attempts_24h FROM security_snapshot_daily ORDER BY date DESC LIMIT 1")
    if cur_snap:
        total = _safe_int(cur_snap.get("active_users_total"))
        insights.append(_make_insight("system", "daily_active_users", "Daily Active Users", total, 0, True, "count"))
        mfa = _safe_int(cur_snap.get("active_users_with_2fa"))
        mfa_pct = (mfa / total * 100) if total > 0 else 0
        insights.append(_make_insight("system", "2fa_adoption", "2FA Adoption Rate", mfa_pct, 0, True, "percent"))
        insights.append(_make_insight("system", "failed_logins", "Failed Login Attempts (24h)", _safe_int(cur_snap.get("failed_login_attempts_24h")), 0, False, "count"))

    integrations = execute_query("SELECT integration_name, status, error_count_24h, latency_ms FROM integration_status_log ORDER BY checked_at DESC LIMIT 10")
    degraded = sum(1 for i in integrations if i.get("status") != "connected")
    insights.append(_make_insight("system", "integration_health", "Integrations Healthy", len(integrations) - degraded, len(integrations), True, "count", f"{degraded} degraded/down" if degraded > 0 else "All healthy"))

    cur_job, pri_job = 0.0, 0.0
    for tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM system_jobs_log WHERE last_run_at >= :s AND last_run_at <= :e", {"s": s, "e": e})
        success = execute_single("SELECT COUNT(*) as cnt FROM system_jobs_log WHERE status = 'success' AND last_run_at >= :s AND last_run_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        su = _safe_int(success.get("cnt")) if success else 0
        rate = (su / t * 100) if t > 0 else 0
        if tag == "cur":
            cur_job = rate
        else:
            pri_job = rate
    insights.append(_make_insight("system", "job_success_rate", "Batch Job Success Rate", cur_job, pri_job, True, "percent"))

    cur_alerts = execute_single("SELECT COUNT(*) as cnt FROM system_alerts WHERE is_resolved = false")
    if cur_alerts:
        insights.append(_make_insight("system", "open_alerts", "Open System Alerts", _safe_int(cur_alerts.get("cnt")), 0, False, "count"))

    return insights


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
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
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
