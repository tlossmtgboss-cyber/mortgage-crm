# Aria Trend Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single `analyze_trends` @mortgage_tool that computes KPIs across 13 business domains and emails a formatted HTML report.

**Architecture:** One tool function dispatches to 13 domain analyzer functions, each returning `List[TrendInsight]`. Results are ranked by significance, rendered to HTML by `trend_email.py`, and emailed via the existing `EmailDeliveryService`. Role-based scoping (LO=own data, manager=team, admin=org) is enforced per-query.

**Tech Stack:** Python, SQLAlchemy raw SQL via `execute_query()`, `@mortgage_tool` decorator, `EmailDeliveryService` (SendGrid/Graph waterfall), HTML email with inline CSS.

**Spec:** `docs/superpowers/specs/2026-05-07-aria-trend-analysis-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/services/trend_email.py` | Create | HTML email rendering + sync send wrapper |
| `backend/agents/tools/trend_analysis.py` | Create | `@mortgage_tool analyze_trends` + 13 domain analyzers |
| `backend/agents/tools/__init__.py` | Modify (line ~109) | Add `from . import trend_analysis` |
| `backend/tests/test_trend_analysis.py` | Create | Unit tests for analyzers (mocked DB) + email rendering |

---

## Shared Constants & Patterns

Every domain analyzer follows this signature:

```python
def _analyze_{domain}(
    current_start: str, current_end: str,
    prior_start: str, prior_end: str,
    user_id: Optional[int], user_role: str,
) -> List[TrendInsight]:
```

Each calls `execute_query()` with parameterized SQL, computes deltas via `calculate_percentage_change()`, and returns a list of `TrendInsight` dicts. Tenant isolation is automatic (execute_query injects org_id). Role scoping is applied via an `owner_filter` SQL fragment injected into WHERE clauses.

---

### Task 1: Create trend email renderer

**Files:**
- Create: `backend/services/trend_email.py`
- Test: `backend/tests/test_trend_analysis.py` (started)

- [ ] **Step 1: Write failing test for HTML rendering**

```python
# backend/tests/test_trend_analysis.py
import pytest
from services.trend_email import render_trend_report_html


def test_render_trend_report_html_notable_changes():
    insights = [
        {
            "domain": "leads",
            "metric": "new_lead_count",
            "label": "New Leads",
            "current_value": 50,
            "prior_value": 30,
            "delta_pct": 66.7,
            "direction": "up",
            "significance": 66.7,
            "context": "Web source drove the increase",
            "is_positive": True,
            "unit": "count",
        },
        {
            "domain": "loans",
            "metric": "funded_volume",
            "label": "Funded Volume",
            "current_value": 2500000,
            "prior_value": 2000000,
            "delta_pct": 25.0,
            "direction": "up",
            "significance": 25.0,
            "context": "",
            "is_positive": True,
            "unit": "currency",
        },
    ]
    html = render_trend_report_html(
        insights=insights,
        period_label="Apr 7 – May 7, 2026 vs Mar 8 – Apr 7, 2026",
        time_window="month",
    )
    assert "Notable Changes" in html
    assert "New Leads" in html
    assert "66.7%" in html
    assert "Funded Volume" in html
    assert "<html" in html


def test_render_empty_insights():
    html = render_trend_report_html(
        insights=[],
        period_label="test period",
        time_window="month",
    )
    assert "No significant trends" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm && .venv/bin/python -m pytest backend/tests/test_trend_analysis.py::test_render_trend_report_html_notable_changes -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.trend_email'`

- [ ] **Step 3: Implement trend_email.py**

```python
# backend/services/trend_email.py
"""
Trend Report Email Renderer & Sender
=====================================
Renders TrendInsight data into an HTML email and sends it via
the existing EmailDeliveryService waterfall (SendGrid → Graph → Gmail).
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import SessionLocal

logger = logging.getLogger(__name__)

# Domain display order and labels
DOMAIN_CONFIG = {
    "leads": {"label": "Lead Pipeline", "icon": "📊"},
    "loans": {"label": "Loan Pipeline", "icon": "🏦"},
    "pipeline": {"label": "Process Flow & SLA", "icon": "⚡"},
    "compliance": {"label": "Compliance", "icon": "✅"},
    "communication": {"label": "Communication & Activity", "icon": "📧"},
    "dialer": {"label": "Dialer & Calls", "icon": "📞"},
    "referrals": {"label": "Referral Partners", "icon": "🤝"},
    "mum": {"label": "Mortgage Under Management", "icon": "🏠"},
    "team": {"label": "Team Performance", "icon": "👥"},
    "ai_ops": {"label": "AI Operations", "icon": "🤖"},
    "documents": {"label": "Document Flow", "icon": "📄"},
    "applications": {"label": "Borrower Applications", "icon": "📝"},
    "system": {"label": "System Health & Security", "icon": "🔒"},
}


def _format_value(value: Any, unit: str) -> str:
    if value is None:
        return "N/A"
    if unit == "currency":
        return f"${float(value):,.0f}"
    if unit == "percent":
        return f"{float(value):.1f}%"
    if unit == "days":
        return f"{float(value):.1f} days"
    return f"{int(value):,}" if isinstance(value, (int, float)) and value == int(value) else str(value)


def _trend_arrow(direction: str, is_positive: bool) -> str:
    if direction == "up":
        color = "#16a34a" if is_positive else "#dc2626"
        return f'<span style="color:{color}">&#9650;</span>'
    elif direction == "down":
        color = "#dc2626" if is_positive else "#16a34a"
        return f'<span style="color:{color}">&#9660;</span>'
    return '<span style="color:#6b7280">&#9644;</span>'


def _delta_badge(delta_pct: float, is_positive: bool, direction: str) -> str:
    if abs(delta_pct) < 5:
        bg, fg = "#f3f4f6", "#6b7280"
    elif (direction == "up" and is_positive) or (direction == "down" and not is_positive):
        bg, fg = "#dcfce7", "#16a34a"
    else:
        bg, fg = "#fee2e2", "#dc2626"
    sign = "+" if delta_pct > 0 else ""
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:12px;font-size:13px;font-weight:600">'
        f'{sign}{delta_pct:.1f}%</span>'
    )


def render_trend_report_html(
    insights: List[Dict],
    period_label: str,
    time_window: str,
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not insights:
        return _wrap_html(
            f'<p style="color:#6b7280;text-align:center;padding:40px 0">'
            f'No significant trends detected for {period_label}.</p>',
            period_label,
            now_str,
        )

    sorted_insights = sorted(insights, key=lambda i: i.get("significance", 0), reverse=True)
    notable = sorted_insights[:5]

    sections = []

    # Notable Changes
    notable_rows = ""
    for ins in notable:
        notable_rows += (
            f'<tr>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">'
            f'{_trend_arrow(ins["direction"], ins["is_positive"])} '
            f'<strong>{ins["label"]}</strong>'
            f'<br><span style="color:#6b7280;font-size:12px">{ins.get("context", "")}</span></td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right">'
            f'{_format_value(ins["prior_value"], ins["unit"])}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right">'
            f'{_format_value(ins["current_value"], ins["unit"])}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right">'
            f'{_delta_badge(ins["delta_pct"], ins["is_positive"], ins["direction"])}</td>'
            f'</tr>'
        )
    sections.append(
        f'<h2 style="color:#1e293b;font-size:18px;margin:24px 0 12px">Notable Changes</h2>'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px">'
        f'<tr style="background:#f8fafc">'
        f'<th style="padding:8px 12px;text-align:left;font-weight:600;color:#64748b;border-bottom:2px solid #e2e8f0">Metric</th>'
        f'<th style="padding:8px 12px;text-align:right;font-weight:600;color:#64748b;border-bottom:2px solid #e2e8f0">Prior</th>'
        f'<th style="padding:8px 12px;text-align:right;font-weight:600;color:#64748b;border-bottom:2px solid #e2e8f0">Current</th>'
        f'<th style="padding:8px 12px;text-align:right;font-weight:600;color:#64748b;border-bottom:2px solid #e2e8f0">Change</th>'
        f'</tr>{notable_rows}</table>'
    )

    # Per-domain sections
    by_domain: Dict[str, List[Dict]] = {}
    for ins in sorted_insights:
        by_domain.setdefault(ins["domain"], []).append(ins)

    for domain_key, config in DOMAIN_CONFIG.items():
        domain_insights = by_domain.get(domain_key, [])
        if not domain_insights:
            continue

        rows = ""
        for ins in domain_insights:
            rows += (
                f'<tr>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9">'
                f'{_trend_arrow(ins["direction"], ins["is_positive"])} {ins["label"]}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right">'
                f'{_format_value(ins["prior_value"], ins["unit"])}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right">'
                f'{_format_value(ins["current_value"], ins["unit"])}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right">'
                f'{_delta_badge(ins["delta_pct"], ins["is_positive"], ins["direction"])}</td>'
                f'</tr>'
            )
        sections.append(
            f'<h2 style="color:#1e293b;font-size:16px;margin:28px 0 8px">'
            f'{config["icon"]} {config["label"]}</h2>'
            f'<table style="width:100%;border-collapse:collapse;font-size:13px">'
            f'<tr style="background:#f8fafc">'
            f'<th style="padding:6px 12px;text-align:left;font-weight:600;color:#64748b;border-bottom:2px solid #e2e8f0">Metric</th>'
            f'<th style="padding:6px 12px;text-align:right;font-weight:600;color:#64748b;border-bottom:2px solid #e2e8f0">Prior</th>'
            f'<th style="padding:6px 12px;text-align:right;font-weight:600;color:#64748b;border-bottom:2px solid #e2e8f0">Current</th>'
            f'<th style="padding:6px 12px;text-align:right;font-weight:600;color:#64748b;border-bottom:2px solid #e2e8f0">Change</th>'
            f'</tr>{rows}</table>'
        )

    body = "\n".join(sections)
    return _wrap_html(body, period_label, now_str)


def _wrap_html(body: str, period_label: str, generated_at: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
<div style="max-width:680px;margin:0 auto;padding:24px">
<div style="background:#0f172a;color:white;padding:20px 24px;border-radius:12px 12px 0 0">
<h1 style="margin:0;font-size:22px;font-weight:700">Perennia Trend Report</h1>
<p style="margin:6px 0 0;color:#94a3b8;font-size:13px">{period_label}</p>
</div>
<div style="background:white;padding:24px;border-radius:0 0 12px 12px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
{body}
</div>
<p style="text-align:center;color:#94a3b8;font-size:11px;margin-top:16px">
Generated {generated_at} &middot; Perennia AI</p>
</div>
</body>
</html>"""


def send_trend_report(
    to_email: str,
    html_body: str,
    period_label: str,
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send the rendered trend report email. Sync wrapper around async EmailDeliveryService."""
    from services.email_delivery_service import EmailDeliveryService

    db = SessionLocal()
    try:
        service = EmailDeliveryService(db)
        coro = service.send_email(
            to=to_email,
            subject=f"Perennia Trend Report — {period_label}",
            html_body=html_body,
            organization_id=organization_id,
            user_id=user_id,
        )
        try:
            asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                result = future.result(timeout=30)
        except RuntimeError:
            result = asyncio.run(coro)

        return {"success": result.success, "error": result.error, "provider": result.provider.value}
    except Exception as e:
        logger.exception("Failed to send trend report email")
        return {"success": False, "error": str(e), "provider": "none"}
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/timothyloss/my-project/mortgage-crm && PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_trend_analysis.py -v -k "render"`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/trend_email.py backend/tests/test_trend_analysis.py
git commit -m "feat: trend report HTML email renderer and sync send wrapper"
```

---

### Task 2: Create trend_analysis.py core infrastructure

**Files:**
- Create: `backend/agents/tools/trend_analysis.py`
- Modify: `backend/tests/test_trend_analysis.py`

- [ ] **Step 1: Write failing test for period computation and insight creation**

Append to `backend/tests/test_trend_analysis.py`:

```python
from unittest.mock import patch
from agents.tools.trend_analysis import (
    _get_period_dates,
    _make_insight,
    _owner_filter,
)


def test_get_period_dates_month():
    start, end, prior_start, prior_end = _get_period_dates("month")
    from datetime import datetime, timedelta
    now = datetime.now()
    assert end == now.strftime("%Y-%m-%d")
    expected_start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    assert start == expected_start


def test_get_period_dates_week():
    start, end, prior_start, prior_end = _get_period_dates("week")
    from datetime import datetime, timedelta
    now = datetime.now()
    expected_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    assert start == expected_start


def test_make_insight_up():
    ins = _make_insight("leads", "new_leads", "New Leads", 50, 30, True, "count")
    assert ins["direction"] == "up"
    assert ins["delta_pct"] == pytest.approx(66.67, abs=0.1)
    assert ins["is_positive"] is True


def test_make_insight_zero_prior():
    ins = _make_insight("leads", "new_leads", "New Leads", 10, 0, True, "count")
    assert ins["direction"] == "up"
    assert ins["delta_pct"] == 100.0


def test_owner_filter_lo():
    sql, params = _owner_filter("sales", 42, "owner_id")
    assert "owner_id" in sql
    assert params["scope_user_id"] == 42


def test_owner_filter_admin():
    sql, params = _owner_filter("admin", 42, "owner_id")
    assert sql == ""
    assert params == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/timothyloss/my-project/mortgage-crm && PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_trend_analysis.py -v -k "period or insight or owner"`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.tools.trend_analysis'`

- [ ] **Step 3: Create trend_analysis.py with core infrastructure + main tool function**

```python
# backend/agents/tools/trend_analysis.py
"""
Aria Trend Analysis & Business Intelligence
============================================
Single @mortgage_tool that computes KPIs across 13 business domains,
ranks insights by significance, and emails an HTML report.

Domains: leads, loans, pipeline (SLA), compliance, communication,
dialer, referrals, mum, team, ai_ops, documents, applications, system.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    calculate_percentage_change,
    format_currency,
    format_percentage,
    is_sqlite,
    sql_now,
    sql_date_subtract,
)

logger = logging.getLogger(__name__)

# ─── Period helpers ──────────────────────────────────────────────────────────

_WINDOW_DAYS = {"week": 7, "month": 30, "quarter": 90}


def _get_period_dates(time_window: str) -> Tuple[str, str, str, str]:
    """Return (current_start, current_end, prior_start, prior_end) as YYYY-MM-DD."""
    now = datetime.now()
    days = _WINDOW_DAYS.get(time_window, 30)
    current_end = now.strftime("%Y-%m-%d")
    current_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    prior_end = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    prior_start = (now - timedelta(days=days * 2)).strftime("%Y-%m-%d")
    return current_start, current_end, prior_start, prior_end


def _make_insight(
    domain: str, metric: str, label: str,
    current_value: float, prior_value: float,
    up_is_good: bool, unit: str,
    context: str = "",
) -> Dict[str, Any]:
    """Build a TrendInsight dict with computed delta and direction."""
    delta = calculate_percentage_change(prior_value, current_value)
    if abs(delta) < 2:
        direction = "flat"
    elif delta > 0:
        direction = "up"
    else:
        direction = "down"

    is_positive = (direction == "up" and up_is_good) or (direction == "down" and not up_is_good)
    if direction == "flat":
        is_positive = True

    return {
        "domain": domain,
        "metric": metric,
        "label": label,
        "current_value": round(current_value, 2),
        "prior_value": round(prior_value, 2),
        "delta_pct": round(delta, 2),
        "direction": direction,
        "significance": round(abs(delta), 2),
        "context": context,
        "is_positive": is_positive,
        "unit": unit,
    }


def _owner_filter(user_role: str, user_id: int, col: str = "owner_id") -> Tuple[str, Dict]:
    """Return (SQL fragment, params) for role-based row scoping."""
    if user_role in ("admin", "site_admin", "leadership", "management"):
        return "", {}
    return f"AND {col} = :scope_user_id", {"scope_user_id": user_id}


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ─── Domain analyzers (implemented in subsequent tasks) ──────────────────────

def _analyze_leads(cs, ce, ps, pe, uid, role):
    # Populated in Task 3
    return []

def _analyze_loans(cs, ce, ps, pe, uid, role):
    # Populated in Task 4
    return []

def _analyze_pipeline(cs, ce, ps, pe, uid, role):
    # Populated in Task 5
    return []

def _analyze_compliance(cs, ce, ps, pe, uid, role):
    # Populated in Task 6
    return []

def _analyze_communication(cs, ce, ps, pe, uid, role):
    # Populated in Task 7
    return []

def _analyze_dialer(cs, ce, ps, pe, uid, role):
    # Populated in Task 7
    return []

def _analyze_referrals(cs, ce, ps, pe, uid, role):
    # Populated in Task 8
    return []

def _analyze_mum(cs, ce, ps, pe, uid, role):
    # Populated in Task 8
    return []

def _analyze_team(cs, ce, ps, pe, uid, role):
    # Populated in Task 9
    return []

def _analyze_ai_ops(cs, ce, ps, pe, uid, role):
    # Populated in Task 9
    return []

def _analyze_documents(cs, ce, ps, pe, uid, role):
    # Populated in Task 9
    return []

def _analyze_applications(cs, ce, ps, pe, uid, role):
    # Populated in Task 9
    return []

def _analyze_system(cs, ce, ps, pe, uid, role):
    # Populated in Task 9
    return []


_DOMAIN_ANALYZERS = {
    "leads": _analyze_leads,
    "loans": _analyze_loans,
    "pipeline": _analyze_pipeline,
    "compliance": _analyze_compliance,
    "communication": _analyze_communication,
    "dialer": _analyze_dialer,
    "referrals": _analyze_referrals,
    "mum": _analyze_mum,
    "team": _analyze_team,
    "ai_ops": _analyze_ai_ops,
    "documents": _analyze_documents,
    "applications": _analyze_applications,
    "system": _analyze_system,
}

_ROLE_DOMAINS = {
    "sales": {"leads", "loans", "pipeline", "compliance", "communication", "dialer", "referrals", "mum"},
    "processing": {"loans", "pipeline", "compliance", "documents"},
    "operations": {"loans", "pipeline", "compliance", "documents"},
}


# ─── Main tool ───────────────────────────────────────────────────────────────

@mortgage_tool(
    name="analyze_trends",
    description=(
        "Analyze business trends and KPIs across the CRM. "
        "Computes period-over-period metrics for leads, loans, pipeline velocity, "
        "compliance, communication, dialer, referral partners, MUM portfolio, "
        "team performance, AI operations, documents, borrower applications, and system health. "
        "Results are emailed as a formatted HTML report."
    ),
    agent_roles=[
        "pipeline_analyst", "reporting_engine", "team_coach",
        "customer_intelligence", "compliance_checker", "lead_nurturer",
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
        "domain": "Domain to analyze: all, leads, loans, pipeline, compliance, communication, dialer, referrals, mum, team, ai_ops, documents, applications, system",
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
    """Analyze trends across CRM data and email an HTML report."""
    try:
        cs, ce, ps, pe = _get_period_dates(time_window)

        if domain == "all":
            allowed = _ROLE_DOMAINS.get(user_role, set(_DOMAIN_ANALYZERS.keys()))
            domains_to_run = [d for d in _DOMAIN_ANALYZERS if d in allowed]
        else:
            domains_to_run = [domain] if domain in _DOMAIN_ANALYZERS else []

        if not domains_to_run:
            return ToolResult.error(f"Unknown domain: {domain}")

        all_insights: List[Dict] = []
        errors: List[str] = []
        for d in domains_to_run:
            try:
                insights = _DOMAIN_ANALYZERS[d](cs, ce, ps, pe, user_id, user_role)
                all_insights.extend(insights)
            except Exception as e:
                logger.exception("Analyzer %s failed", d)
                errors.append(f"{d}: {e}")

        window_label = {"week": "7 days", "month": "30 days", "quarter": "90 days"}.get(time_window, "30 days")
        period_label = f"{cs} – {ce} vs {ps} – {pe} ({window_label})"

        from services.trend_email import render_trend_report_html, send_trend_report

        html = render_trend_report_html(
            insights=all_insights,
            period_label=period_label,
            time_window=time_window,
        )

        if not user_email:
            row = execute_single(
                "SELECT email FROM users WHERE id = :uid",
                {"uid": user_id},
            )
            user_email = row["email"] if row else None

        if not user_email:
            return ToolResult.partial(
                data={"insight_count": len(all_insights), "domains": domains_to_run},
                message="Trend analysis complete but no email address found to send report.",
                warnings=["Could not determine user email address"],
            )

        result = send_trend_report(
            to_email=user_email,
            html_body=html,
            period_label=f"{cs} – {ce}",
            organization_id=None,
            user_id=str(user_id) if user_id else None,
        )

        if result["success"]:
            return ToolResult.success(
                data={"insight_count": len(all_insights), "domains": domains_to_run, "emailed_to": user_email},
                message=f"Trend report emailed to {user_email}. Found {len(all_insights)} insights across {len(domains_to_run)} domains.",
            )
        else:
            return ToolResult.error(f"Trend analysis complete ({len(all_insights)} insights) but email failed: {result['error']}")

    except Exception as e:
        logger.exception("analyze_trends failed")
        return ToolResult.error(str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/timothyloss/my-project/mortgage-crm && PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_trend_analysis.py -v`
Expected: ALL PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agents/tools/trend_analysis.py backend/tests/test_trend_analysis.py
git commit -m "feat: trend analysis tool skeleton with period helpers and main function"
```

---

### Task 3: Implement lead pipeline analyzer

**Files:**
- Modify: `backend/agents/tools/trend_analysis.py` — replace `_analyze_leads` stub

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_trend_analysis.py`:

```python
@patch("agents.tools.trend_analysis.execute_query")
@patch("agents.tools.trend_analysis.execute_single")
def test_analyze_leads_returns_insights(mock_single, mock_query):
    mock_query.side_effect = [
        # Current new leads
        [{"cnt": 50}],
        # Prior new leads
        [{"cnt": 30}],
        # Current by source
        [{"source": "Web", "cnt": 25}, {"source": "Referral", "cnt": 15}],
        # Prior by source
        [{"source": "Web", "cnt": 20}, {"source": "Referral", "cnt": 10}],
        # Current conversion stages
        [{"stage": "New", "cnt": 20}, {"stage": "Application", "cnt": 10}, {"stage": "Closed", "cnt": 5}],
        # Prior conversion stages
        [{"stage": "New", "cnt": 18}, {"stage": "Application", "cnt": 8}, {"stage": "Closed", "cnt": 3}],
        # Current stale leads
        [{"cnt": 8}],
        # Prior stale leads
        [{"cnt": 12}],
    ]
    mock_single.side_effect = [
        # Current avg time to contact
        {"avg_days": 1.5},
        # Prior avg time to contact
        {"avg_days": 2.0},
        # Current avg AI score
        {"avg_score": 65},
        # Prior avg AI score
        {"avg_score": 60},
    ]

    from agents.tools.trend_analysis import _analyze_leads
    results = _analyze_leads("2026-04-07", "2026-05-07", "2026-03-08", "2026-04-07", None, "admin")
    assert len(results) > 0
    labels = [r["label"] for r in results]
    assert "New Leads" in labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm && PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_trend_analysis.py::test_analyze_leads_returns_insights -v`
Expected: FAIL — `_analyze_leads` returns `[]`

- [ ] **Step 3: Implement _analyze_leads**

Replace the `_analyze_leads` stub in `trend_analysis.py` with:

```python
def _analyze_leads(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "owner_id")
    insights = []

    cur = execute_query(f"SELECT COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri = execute_query(f"SELECT COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    cv, pv = _safe_int(cur[0]["cnt"]) if cur else 0, _safe_int(pri[0]["cnt"]) if pri else 0
    insights.append(_make_insight("leads", "new_lead_count", "New Leads", cv, pv, True, "count"))

    for period_label, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(
            f"SELECT COALESCE(source, 'Unknown') as source, COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of} GROUP BY source ORDER BY cnt DESC LIMIT 10",
            {"s": s, "e": e, **op},
        )
        if period_label == "cur":
            cur_sources = {r["source"]: _safe_int(r["cnt"]) for r in rows}
        else:
            pri_sources = {r["source"]: _safe_int(r["cnt"]) for r in rows}
    for src in cur_sources:
        if cur_sources[src] >= 3:
            insights.append(_make_insight("leads", f"source_{src}", f"Leads from {src}", cur_sources.get(src, 0), pri_sources.get(src, 0), True, "count"))

    cur_stages = execute_query(
        f"SELECT stage, COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of} GROUP BY stage",
        {"s": cs, "e": ce, **op},
    )
    pri_stages = execute_query(
        f"SELECT stage, COUNT(*) as cnt FROM leads WHERE created_at >= :s AND created_at <= :e {of} GROUP BY stage",
        {"s": ps, "e": pe, **op},
    )
    cur_map = {r["stage"]: _safe_int(r["cnt"]) for r in cur_stages}
    pri_map = {r["stage"]: _safe_int(r["cnt"]) for r in pri_stages}
    for stage in ["Application", "Pre-Qualified", "Pre-Approved", "Closed"]:
        if cur_map.get(stage, 0) > 0 or pri_map.get(stage, 0) > 0:
            insights.append(_make_insight("leads", f"stage_{stage}", f"Leads at {stage}", cur_map.get(stage, 0), pri_map.get(stage, 0), True, "count"))

    cur_ttc = execute_single(
        f"""SELECT AVG(EXTRACT(EPOCH FROM (first_contact_attempt_date - lead_received_date)) / 86400) as avg_days
            FROM leads WHERE first_contact_attempt_date IS NOT NULL AND lead_received_date IS NOT NULL
            AND created_at >= :s AND created_at <= :e {of}""",
        {"s": cs, "e": ce, **op},
    )
    pri_ttc = execute_single(
        f"""SELECT AVG(EXTRACT(EPOCH FROM (first_contact_attempt_date - lead_received_date)) / 86400) as avg_days
            FROM leads WHERE first_contact_attempt_date IS NOT NULL AND lead_received_date IS NOT NULL
            AND created_at >= :s AND created_at <= :e {of}""",
        {"s": ps, "e": pe, **op},
    )
    cv = _safe_float(cur_ttc.get("avg_days")) if cur_ttc else 0
    pv = _safe_float(pri_ttc.get("avg_days")) if pri_ttc else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("leads", "avg_time_to_contact", "Avg Time to First Contact", cv, pv, False, "days"))

    cur_ai = execute_single(
        f"SELECT AVG(ai_score) as avg_score FROM leads WHERE ai_score IS NOT NULL AND created_at >= :s AND created_at <= :e {of}",
        {"s": cs, "e": ce, **op},
    )
    pri_ai = execute_single(
        f"SELECT AVG(ai_score) as avg_score FROM leads WHERE ai_score IS NOT NULL AND created_at >= :s AND created_at <= :e {of}",
        {"s": ps, "e": pe, **op},
    )
    cv = _safe_float(cur_ai.get("avg_score")) if cur_ai else 0
    pv = _safe_float(pri_ai.get("avg_score")) if pri_ai else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("leads", "avg_ai_score", "Avg Lead AI Score", cv, pv, True, "count"))

    cur_stale = execute_query(f"SELECT COUNT(*) as cnt FROM leads WHERE last_contact < {sql_date_subtract(30)} AND stage NOT IN ('Closed','Funded','Dead','Withdrawn') {of}", op)
    pri_stale_count = 0
    cv = _safe_int(cur_stale[0]["cnt"]) if cur_stale else 0
    if cv > 0:
        insights.append(_make_insight("leads", "stale_leads", "Stale Leads (no contact 30+ days)", cv, pri_stale_count, False, "count", "Leads with no contact in over 30 days"))

    return insights
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/timothyloss/my-project/mortgage-crm && PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_trend_analysis.py::test_analyze_leads_returns_insights -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/tools/trend_analysis.py backend/tests/test_trend_analysis.py
git commit -m "feat: implement lead pipeline trend analyzer"
```

---

### Task 4: Implement loan pipeline analyzer

**Files:**
- Modify: `backend/agents/tools/trend_analysis.py` — replace `_analyze_loans` stub

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_trend_analysis.py`:

```python
@patch("agents.tools.trend_analysis.execute_query")
@patch("agents.tools.trend_analysis.execute_single")
def test_analyze_loans_returns_insights(mock_single, mock_query):
    mock_query.side_effect = [
        [{"cnt": 80, "vol": 25000000}],  # current active
        [{"cnt": 70, "vol": 20000000}],  # prior active
        [{"cnt": 12, "vol": 4500000}],   # current funded
        [{"cnt": 10, "vol": 3500000}],   # prior funded
        [{"stage": "PROCESSING", "cnt": 20}, {"stage": "UNDERWRITING", "cnt": 15}],  # cur stages
        [{"stage": "PROCESSING", "cnt": 18}, {"stage": "UNDERWRITING", "cnt": 12}],  # pri stages
        [{"loan_type": "conventional", "cnt": 30}, {"loan_type": "fha", "cnt": 10}], # cur types
        [{"loan_type": "conventional", "cnt": 28}, {"loan_type": "fha", "cnt": 8}],  # pri types
    ]
    mock_single.side_effect = [
        {"avg_amt": 320000},  # current avg loan
        {"avg_amt": 300000},  # prior avg loan
        {"avg_rate": 6.5},    # current avg rate
        {"avg_rate": 6.75},   # prior avg rate
        {"avg_days": 35},     # current cycle time
        {"avg_days": 38},     # prior cycle time
    ]

    from agents.tools.trend_analysis import _analyze_loans
    results = _analyze_loans("2026-04-07", "2026-05-07", "2026-03-08", "2026-04-07", None, "admin")
    assert len(results) > 0
    labels = [r["label"] for r in results]
    assert "Active Pipeline Count" in labels
    assert "Funded Volume" in labels
```

- [ ] **Step 2: Run test — expected FAIL (returns [])**

- [ ] **Step 3: Implement _analyze_loans**

Replace stub:

```python
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
        f"""SELECT AVG(EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400) as avg_days
            FROM loans WHERE funded_date IS NOT NULL AND application_date IS NOT NULL
            AND funded_date >= :s AND funded_date <= :e {of}""",
        {"s": cs, "e": ce, **op},
    )
    pri_cycle = execute_single(
        f"""SELECT AVG(EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400) as avg_days
            FROM loans WHERE funded_date IS NOT NULL AND application_date IS NOT NULL
            AND funded_date >= :s AND funded_date <= :e {of}""",
        {"s": ps, "e": pe, **op},
    )
    cv = _safe_float(cur_cycle.get("avg_days")) if cur_cycle else 0
    pv = _safe_float(pri_cycle.get("avg_days")) if pri_cycle else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("loans", "avg_cycle_time", "Avg Cycle Time (App→Funded)", cv, pv, False, "days"))

    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT stage, COUNT(*) as cnt FROM loans WHERE created_at >= :s AND created_at <= :e {of} GROUP BY stage ORDER BY cnt DESC", {"s": s, "e": e, **op})
        if period_tag == "cur":
            cur_stages = {r["stage"]: _safe_int(r["cnt"]) for r in rows}
        else:
            pri_stages = {r["stage"]: _safe_int(r["cnt"]) for r in rows}
    for stg in ["PROCESSING", "UNDERWRITING", "CONDITIONAL_APPROVAL", "APPROVED", "CTC", "CLEAR_TO_CLOSE"]:
        if cur_stages.get(stg, 0) > 0 or pri_stages.get(stg, 0) > 0:
            insights.append(_make_insight("loans", f"stage_{stg}", f"Loans in {stg.replace('_',' ').title()}", cur_stages.get(stg, 0), pri_stages.get(stg, 0), True, "count"))

    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT COALESCE(loan_type,'Unknown') as loan_type, COUNT(*) as cnt FROM loans WHERE created_at >= :s AND created_at <= :e {of} GROUP BY loan_type", {"s": s, "e": e, **op})
        if period_tag == "cur":
            cur_types = {r["loan_type"]: _safe_int(r["cnt"]) for r in rows}
        else:
            pri_types = {r["loan_type"]: _safe_int(r["cnt"]) for r in rows}
    for lt in cur_types:
        if cur_types[lt] >= 2:
            insights.append(_make_insight("loans", f"type_{lt}", f"{lt.upper()} Loans", cur_types.get(lt, 0), pri_types.get(lt, 0), True, "count"))

    return insights
```

- [ ] **Step 4: Run test — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add backend/agents/tools/trend_analysis.py backend/tests/test_trend_analysis.py
git commit -m "feat: implement loan pipeline trend analyzer"
```

---

### Task 5: Implement process flow/SLA analyzer

**Files:**
- Modify: `backend/agents/tools/trend_analysis.py` — replace `_analyze_pipeline` stub

- [ ] **Step 1: Write test (mock execute_query/execute_single)**

Test verifies `_analyze_pipeline` returns insights with labels for SLA compliance, stage velocity, bottlenecks, task completion, and escalations. Same mock pattern as Tasks 3-4.

- [ ] **Step 2: Implement _analyze_pipeline**

```python
def _analyze_pipeline(cs, ce, ps, pe, uid, role):
    of_loan, op_loan = _owner_filter(role, uid, "loan_officer_id")
    of_task, op_task = _owner_filter(role, uid, "owner_id")
    insights = []

    # Stage velocity from stage_history
    cur_vel = execute_query(
        f"""SELECT to_stage, AVG(duration_in_previous_stage) as avg_days
            FROM stage_history WHERE entity_type = 'loan' AND changed_at >= :s AND changed_at <= :e
            GROUP BY to_stage ORDER BY avg_days DESC LIMIT 20""",
        {"s": cs, "e": ce},
    )
    pri_vel = execute_query(
        f"""SELECT to_stage, AVG(duration_in_previous_stage) as avg_days
            FROM stage_history WHERE entity_type = 'loan' AND changed_at >= :s AND changed_at <= :e
            GROUP BY to_stage ORDER BY avg_days DESC LIMIT 20""",
        {"s": ps, "e": pe},
    )
    cur_vel_map = {r["to_stage"]: _safe_float(r["avg_days"]) for r in cur_vel}
    pri_vel_map = {r["to_stage"]: _safe_float(r["avg_days"]) for r in pri_vel}
    for stage in cur_vel_map:
        cv, pv = cur_vel_map.get(stage, 0), pri_vel_map.get(stage, 0)
        if cv > 0 and pv > 0:
            insights.append(_make_insight("pipeline", f"velocity_{stage}", f"Avg Days to {stage.replace('_',' ').title()}", cv, pv, False, "days"))

    # Task completion rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single(f"SELECT COUNT(*) as cnt FROM tasks WHERE created_at >= :s AND created_at <= :e {of_task}", {"s": s, "e": e, **op_task})
        done = execute_single(f"SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND created_at >= :s AND created_at <= :e {of_task}", {"s": s, "e": e, **op_task})
        t, d = _safe_int(total.get("cnt")) if total else 0, _safe_int(done.get("cnt")) if done else 0
        rate = (d / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_task_rate = rate
        else:
            pri_task_rate = rate
    insights.append(_make_insight("pipeline", "task_completion_rate", "Task Completion Rate", cur_task_rate, pri_task_rate, True, "percent"))

    # Task on-time rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        on_time = execute_single(
            f"SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND due_date IS NOT NULL AND completed_at <= due_date AND created_at >= :s AND created_at <= :e {of_task}",
            {"s": s, "e": e, **op_task},
        )
        total_due = execute_single(
            f"SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND due_date IS NOT NULL AND created_at >= :s AND created_at <= :e {of_task}",
            {"s": s, "e": e, **op_task},
        )
        ot, td = _safe_int(on_time.get("cnt")) if on_time else 0, _safe_int(total_due.get("cnt")) if total_due else 0
        rate = (ot / td * 100) if td > 0 else 0
        if period_tag == "cur":
            cur_on_time = rate
        else:
            pri_on_time = rate
    insights.append(_make_insight("pipeline", "task_on_time_rate", "Task On-Time Rate", cur_on_time, pri_on_time, True, "percent"))

    # Escalation count
    cur_esc = execute_single(f"SELECT COUNT(*) as cnt FROM escalation_records WHERE escalated_at >= :s AND escalated_at <= :e", {"s": cs, "e": ce})
    pri_esc = execute_single(f"SELECT COUNT(*) as cnt FROM escalation_records WHERE escalated_at >= :s AND escalated_at <= :e", {"s": ps, "e": pe})
    cv = _safe_int(cur_esc.get("cnt")) if cur_esc else 0
    pv = _safe_int(pri_esc.get("cnt")) if pri_esc else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("pipeline", "escalation_count", "Escalations", cv, pv, False, "count"))

    # Avg escalation resolution time
    cur_res = execute_single(
        f"SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - escalated_at)) / 3600) as avg_hrs FROM escalation_records WHERE resolved_at IS NOT NULL AND escalated_at >= :s AND escalated_at <= :e",
        {"s": cs, "e": ce},
    )
    pri_res = execute_single(
        f"SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - escalated_at)) / 3600) as avg_hrs FROM escalation_records WHERE resolved_at IS NOT NULL AND escalated_at >= :s AND escalated_at <= :e",
        {"s": ps, "e": pe},
    )
    cv = _safe_float(cur_res.get("avg_hrs")) if cur_res else 0
    pv = _safe_float(pri_res.get("avg_hrs")) if pri_res else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("pipeline", "avg_escalation_resolution_hrs", "Avg Escalation Resolution (hrs)", cv, pv, False, "count"))

    return insights
```

- [ ] **Step 3: Run test — expected PASS**
- [ ] **Step 4: Commit**

```bash
git add backend/agents/tools/trend_analysis.py backend/tests/test_trend_analysis.py
git commit -m "feat: implement process flow/SLA trend analyzer"
```

---

### Task 6: Implement compliance analyzer

**Files:**
- Modify: `backend/agents/tools/trend_analysis.py` — replace `_analyze_compliance` stub

- [ ] **Step 1: Implement _analyze_compliance**

```python
def _analyze_compliance(cs, ce, ps, pe, uid, role):
    insights = []

    # TRID LE compliance
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM disclosure_events WHERE disclosure_type = 'LOAN_ESTIMATE' AND sent_at >= :s AND sent_at <= :e", {"s": s, "e": e})
        on_time = execute_single("SELECT COUNT(*) as cnt FROM disclosure_events WHERE disclosure_type = 'LOAN_ESTIMATE' AND is_on_time = true AND sent_at >= :s AND sent_at <= :e", {"s": s, "e": e})
        t, ot = _safe_int(total.get("cnt")) if total else 0, _safe_int(on_time.get("cnt")) if on_time else 0
        rate = (ot / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_le = rate
        else:
            pri_le = rate
    insights.append(_make_insight("compliance", "trid_le_compliance", "TRID LE Compliance", cur_le, pri_le, True, "percent"))

    # TRID CD compliance
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM disclosure_events WHERE disclosure_type = 'CLOSING_DISCLOSURE' AND sent_at >= :s AND sent_at <= :e", {"s": s, "e": e})
        on_time = execute_single("SELECT COUNT(*) as cnt FROM disclosure_events WHERE disclosure_type = 'CLOSING_DISCLOSURE' AND is_on_time = true AND sent_at >= :s AND sent_at <= :e", {"s": s, "e": e})
        t, ot = _safe_int(total.get("cnt")) if total else 0, _safe_int(on_time.get("cnt")) if on_time else 0
        rate = (ot / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_cd = rate
        else:
            pri_cd = rate
    insights.append(_make_insight("compliance", "trid_cd_compliance", "TRID CD Compliance", cur_cd, pri_cd, True, "percent"))

    # Adverse action timeliness
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM adverse_action_notices WHERE denial_date >= :s AND denial_date <= :e", {"s": s, "e": e})
        on_time = execute_single("SELECT COUNT(*) as cnt FROM adverse_action_notices WHERE is_on_time = true AND denial_date >= :s AND denial_date <= :e", {"s": s, "e": e})
        t, ot = _safe_int(total.get("cnt")) if total else 0, _safe_int(on_time.get("cnt")) if on_time else 0
        rate = (ot / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_aa = rate
        else:
            pri_aa = rate
    if cur_aa > 0 or pri_aa > 0:
        insights.append(_make_insight("compliance", "adverse_action_timeliness", "Adverse Action Timeliness", cur_aa, pri_aa, True, "percent"))

    # Fee tolerance violations
    cur_viol = execute_single("SELECT COUNT(*) as cnt FROM loan_fees WHERE is_violation = true AND created_at >= :s AND created_at <= :e", {"s": cs, "e": ce})
    pri_viol = execute_single("SELECT COUNT(*) as cnt FROM loan_fees WHERE is_violation = true AND created_at >= :s AND created_at <= :e", {"s": ps, "e": pe})
    cv = _safe_int(cur_viol.get("cnt")) if cur_viol else 0
    pv = _safe_int(pri_viol.get("cnt")) if pri_viol else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("compliance", "fee_violations", "Fee Tolerance Violations", cv, pv, False, "count"))

    # Open compliance alerts by severity
    for severity in ["critical", "high"]:
        cur_a = execute_single(f"SELECT COUNT(*) as cnt FROM compliance_alerts WHERE severity = :sev AND status = 'open' AND created_at <= :e", {"sev": severity, "e": ce})
        pri_a = execute_single(f"SELECT COUNT(*) as cnt FROM compliance_alerts WHERE severity = :sev AND status = 'open' AND created_at <= :e", {"sev": severity, "e": pe})
        cv = _safe_int(cur_a.get("cnt")) if cur_a else 0
        pv = _safe_int(pri_a.get("cnt")) if pri_a else 0
        if cv > 0 or pv > 0:
            insights.append(_make_insight("compliance", f"open_alerts_{severity}", f"Open {severity.title()} Alerts", cv, pv, False, "count"))

    return insights
```

- [ ] **Step 2: Write test, run, verify pass**
- [ ] **Step 3: Commit**

```bash
git add backend/agents/tools/trend_analysis.py backend/tests/test_trend_analysis.py
git commit -m "feat: implement compliance trend analyzer"
```

---

### Task 7: Implement communication & dialer analyzers

**Files:**
- Modify: `backend/agents/tools/trend_analysis.py` — replace `_analyze_communication` and `_analyze_dialer` stubs

- [ ] **Step 1: Implement _analyze_communication**

```python
def _analyze_communication(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "user_id")
    insights = []

    # Total activities by type
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT type, COUNT(*) as cnt FROM activities WHERE created_at >= :s AND created_at <= :e {of} GROUP BY type", {"s": s, "e": e, **op})
        if period_tag == "cur":
            cur_acts = {r["type"]: _safe_int(r["cnt"]) for r in rows}
        else:
            pri_acts = {r["type"]: _safe_int(r["cnt"]) for r in rows}
    cur_total = sum(cur_acts.values())
    pri_total = sum(pri_acts.values())
    insights.append(_make_insight("communication", "total_activities", "Total Activities", cur_total, pri_total, True, "count"))
    for atype in ["EMAIL", "CALL", "SMS", "MEETING"]:
        if cur_acts.get(atype, 0) > 0 or pri_acts.get(atype, 0) > 0:
            insights.append(_make_insight("communication", f"activity_{atype.lower()}", f"{atype.title()} Activities", cur_acts.get(atype, 0), pri_acts.get(atype, 0), True, "count"))

    # Email inbound/outbound
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT direction, COUNT(*) as cnt FROM email_messages WHERE created_at >= :s AND created_at <= :e {of} GROUP BY direction", {"s": s, "e": e, **op})
        d = {r["direction"]: _safe_int(r["cnt"]) for r in rows}
        if period_tag == "cur":
            cur_email_in, cur_email_out = d.get("inbound", 0), d.get("outbound", 0)
        else:
            pri_email_in, pri_email_out = d.get("inbound", 0), d.get("outbound", 0)
    insights.append(_make_insight("communication", "emails_inbound", "Inbound Emails", cur_email_in, pri_email_in, True, "count"))
    insights.append(_make_insight("communication", "emails_outbound", "Outbound Emails", cur_email_out, pri_email_out, True, "count"))

    # SMS delivery rate
    cur_sms_total = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE direction = 'outbound' AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    cur_sms_del = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE direction = 'outbound' AND status = 'delivered' AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_sms_total = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE direction = 'outbound' AND created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    pri_sms_del = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE direction = 'outbound' AND status = 'delivered' AND created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    ct = _safe_int(cur_sms_total.get("cnt")) if cur_sms_total else 0
    cd = _safe_int(cur_sms_del.get("cnt")) if cur_sms_del else 0
    pt = _safe_int(pri_sms_total.get("cnt")) if pri_sms_total else 0
    pd_val = _safe_int(pri_sms_del.get("cnt")) if pri_sms_del else 0
    cur_rate = (cd / ct * 100) if ct > 0 else 0
    pri_rate = (pd_val / pt * 100) if pt > 0 else 0
    if ct > 0 or pt > 0:
        insights.append(_make_insight("communication", "sms_delivery_rate", "SMS Delivery Rate", cur_rate, pri_rate, True, "percent"))

    # AI-generated message %
    cur_ai = execute_single(f"SELECT COUNT(*) as cnt FROM sms_messages WHERE ai_generated = true AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    cv = _safe_int(cur_ai.get("cnt")) if cur_ai else 0
    ai_pct = (cv / ct * 100) if ct > 0 else 0
    insights.append(_make_insight("communication", "ai_message_pct", "AI-Generated SMS %", ai_pct, 0, True, "percent", "Percentage of outbound SMS generated by AI"))

    return insights
```

- [ ] **Step 2: Implement _analyze_dialer**

```python
def _analyze_dialer(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "agent_id")
    insights = []

    # Total calls
    cur_calls = execute_single(f"SELECT COUNT(*) as cnt FROM call_logs WHERE created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_calls = execute_single(f"SELECT COUNT(*) as cnt FROM call_logs WHERE created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    insights.append(_make_insight("dialer", "total_calls", "Total Calls", _safe_int(cur_calls.get("cnt")) if cur_calls else 0, _safe_int(pri_calls.get("cnt")) if pri_calls else 0, True, "count"))

    # Avg call duration
    cur_dur = execute_single(f"SELECT AVG(duration_seconds) as avg_dur FROM call_logs WHERE duration_seconds > 0 AND created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_dur = execute_single(f"SELECT AVG(duration_seconds) as avg_dur FROM call_logs WHERE duration_seconds > 0 AND created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    cv = _safe_float(cur_dur.get("avg_dur")) / 60 if cur_dur and cur_dur.get("avg_dur") else 0
    pv = _safe_float(pri_dur.get("avg_dur")) / 60 if pri_dur and pri_dur.get("avg_dur") else 0
    insights.append(_make_insight("dialer", "avg_call_duration_min", "Avg Call Duration (min)", round(cv, 1), round(pv, 1), True, "count"))

    # Connect rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single(f"SELECT COUNT(*) as cnt FROM call_logs WHERE created_at >= :s AND created_at <= :e {of}", {"s": s, "e": e, **op})
        connected = execute_single(f"SELECT COUNT(*) as cnt FROM call_logs WHERE outcome = 'COMPLETED' AND created_at >= :s AND created_at <= :e {of}", {"s": s, "e": e, **op})
        t = _safe_int(total.get("cnt")) if total else 0
        c = _safe_int(connected.get("cnt")) if connected else 0
        rate = (c / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_connect = rate
        else:
            pri_connect = rate
    insights.append(_make_insight("dialer", "connect_rate", "Call Connect Rate", cur_connect, pri_connect, True, "percent"))

    # Call outcome distribution
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        rows = execute_query(f"SELECT outcome, COUNT(*) as cnt FROM call_logs WHERE created_at >= :s AND created_at <= :e {of} GROUP BY outcome", {"s": s, "e": e, **op})
        if period_tag == "cur":
            cur_outcomes = {r["outcome"]: _safe_int(r["cnt"]) for r in rows}
        else:
            pri_outcomes = {r["outcome"]: _safe_int(r["cnt"]) for r in rows}
    for outcome in ["NO_ANSWER", "BUSY", "FAILED"]:
        if cur_outcomes.get(outcome, 0) > 0 or pri_outcomes.get(outcome, 0) > 0:
            insights.append(_make_insight("dialer", f"outcome_{outcome.lower()}", f"{outcome.replace('_',' ').title()} Calls", cur_outcomes.get(outcome, 0), pri_outcomes.get(outcome, 0), False, "count"))

    # Dialer session completion rate
    cur_sess = execute_single(f"SELECT AVG(CASE WHEN total_tasks > 0 THEN completed_tasks * 100.0 / total_tasks ELSE 0 END) as avg_rate FROM dialer_sessions WHERE created_at >= :s AND created_at <= :e {of}", {"s": cs, "e": ce, **op})
    pri_sess = execute_single(f"SELECT AVG(CASE WHEN total_tasks > 0 THEN completed_tasks * 100.0 / total_tasks ELSE 0 END) as avg_rate FROM dialer_sessions WHERE created_at >= :s AND created_at <= :e {of}", {"s": ps, "e": pe, **op})
    cv = _safe_float(cur_sess.get("avg_rate")) if cur_sess else 0
    pv = _safe_float(pri_sess.get("avg_rate")) if pri_sess else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("dialer", "session_completion_rate", "Dialer Session Completion", cv, pv, True, "percent"))

    return insights
```

- [ ] **Step 3: Write tests, run, verify pass**
- [ ] **Step 4: Commit**

```bash
git add backend/agents/tools/trend_analysis.py backend/tests/test_trend_analysis.py
git commit -m "feat: implement communication and dialer trend analyzers"
```

---

### Task 8: Implement referral & MUM analyzers

**Files:**
- Modify: `backend/agents/tools/trend_analysis.py` — replace `_analyze_referrals` and `_analyze_mum` stubs

- [ ] **Step 1: Implement _analyze_referrals**

```python
def _analyze_referrals(cs, ce, ps, pe, uid, role):
    insights = []

    cur_total = execute_single("SELECT SUM(referrals_in) as total_in, SUM(referrals_out) as total_out, SUM(closed_loans) as closed, COALESCE(SUM(volume),0) as vol FROM referral_partners WHERE status = 'active'")
    # Referral partners don't have period dates on referrals_in counter — use created_at for new partners
    cur_new = execute_single("SELECT COUNT(*) as cnt FROM referral_partners WHERE created_at >= :s AND created_at <= :e", {"s": cs, "e": ce})
    pri_new = execute_single("SELECT COUNT(*) as cnt FROM referral_partners WHERE created_at >= :s AND created_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("referrals", "new_partners", "New Referral Partners", _safe_int(cur_new.get("cnt")) if cur_new else 0, _safe_int(pri_new.get("cnt")) if pri_new else 0, True, "count"))

    # Total active partner count
    cur_active = execute_single("SELECT COUNT(*) as cnt FROM referral_partners WHERE status = 'active' AND last_interaction >= :s", {"s": cs})
    pri_active = execute_single("SELECT COUNT(*) as cnt FROM referral_partners WHERE status = 'active' AND last_interaction >= :s", {"s": ps})
    insights.append(_make_insight("referrals", "active_partners", "Active Partners (contacted this period)", _safe_int(cur_active.get("cnt")) if cur_active else 0, _safe_int(pri_active.get("cnt")) if pri_active else 0, True, "count"))

    # Dormant partners (no interaction 90+ days)
    cur_dormant = execute_single(f"SELECT COUNT(*) as cnt FROM referral_partners WHERE status = 'active' AND (last_interaction IS NULL OR last_interaction < {sql_date_subtract(90)})")
    if cur_dormant:
        cv = _safe_int(cur_dormant.get("cnt"))
        if cv > 0:
            insights.append(_make_insight("referrals", "dormant_partners", "Dormant Partners (90+ days)", cv, 0, False, "count"))

    # Avg reciprocity score
    cur_recip = execute_single("SELECT AVG(reciprocity_score) as avg_score FROM referral_partners WHERE status = 'active' AND reciprocity_score IS NOT NULL")
    if cur_recip and cur_recip.get("avg_score"):
        insights.append(_make_insight("referrals", "avg_reciprocity", "Avg Reciprocity Score", _safe_float(cur_recip.get("avg_score")), 0, True, "count", "Current snapshot — higher means more balanced give/get"))

    # Tier distribution
    tiers = execute_query("SELECT COALESCE(loyalty_tier,'none') as tier, COUNT(*) as cnt FROM referral_partners WHERE status = 'active' GROUP BY loyalty_tier ORDER BY cnt DESC")
    for row in tiers:
        if row.get("tier") and _safe_int(row["cnt"]) > 0:
            insights.append(_make_insight("referrals", f"tier_{row['tier']}", f"{row['tier'].title()} Tier Partners", _safe_int(row["cnt"]), 0, True, "count"))

    # Top 5 partners by volume (snapshot, not period-over-period)
    top = execute_query("SELECT name, COALESCE(volume,0) as vol, referrals_in, closed_loans FROM referral_partners WHERE status = 'active' ORDER BY volume DESC LIMIT 5")
    for i, row in enumerate(top):
        insights.append(_make_insight("referrals", f"top_partner_{i+1}", f"#{i+1} {row['name']}", _safe_float(row["vol"]), 0, True, "currency", f"{_safe_int(row.get('referrals_in',0))} referrals, {_safe_int(row.get('closed_loans',0))} closed"))

    return insights
```

- [ ] **Step 2: Implement _analyze_mum**

```python
def _analyze_mum(cs, ce, ps, pe, uid, role):
    of, op = _owner_filter(role, uid, "user_id")
    insights = []

    # Portfolio size and balance
    cur_port = execute_single(f"SELECT COUNT(*) as cnt, COALESCE(SUM(current_loan_amount),0) as bal FROM mum_clients WHERE status = 'active' {of}", op)
    insights.append(_make_insight("mum", "portfolio_size", "MUM Portfolio Size", _safe_int(cur_port.get("cnt")) if cur_port else 0, 0, True, "count", "Active clients in portfolio"))
    insights.append(_make_insight("mum", "portfolio_balance", "Portfolio Total Balance", _safe_float(cur_port.get("bal")) if cur_port else 0, 0, True, "currency"))

    # Refi opportunities
    cur_refi = execute_single(f"SELECT COUNT(*) as cnt, COALESCE(SUM(estimated_savings),0) as savings FROM mum_clients WHERE refinance_opportunity = true {of}", op)
    insights.append(_make_insight("mum", "refi_opportunities", "Refi Opportunities", _safe_int(cur_refi.get("cnt")) if cur_refi else 0, 0, True, "count"))
    insights.append(_make_insight("mum", "refi_potential_savings", "Potential Refi Savings", _safe_float(cur_refi.get("savings")) if cur_refi else 0, 0, True, "currency"))

    # Avg engagement score
    cur_eng = execute_single(f"SELECT AVG(engagement_score) as avg_eng FROM mum_clients WHERE engagement_score IS NOT NULL {of}", op)
    insights.append(_make_insight("mum", "avg_engagement", "Avg Engagement Score", _safe_float(cur_eng.get("avg_eng")) if cur_eng else 0, 0, True, "count"))

    # Stale contacts (no contact 60+ days)
    stale = execute_single(f"SELECT COUNT(*) as cnt FROM mum_clients WHERE status = 'active' AND (last_contact IS NULL OR last_contact < {sql_date_subtract(60)}) {of}", op)
    cv = _safe_int(stale.get("cnt")) if stale else 0
    if cv > 0:
        insights.append(_make_insight("mum", "stale_mum_contacts", "MUM Clients Needing Contact (60+ days)", cv, 0, False, "count"))

    # Upcoming touchpoints
    upcoming = execute_single(f"SELECT COUNT(*) as cnt FROM mum_clients WHERE next_touchpoint >= :s AND next_touchpoint <= :e {of}", {"s": cs, "e": ce, **op})
    insights.append(_make_insight("mum", "upcoming_touchpoints", "Upcoming Touchpoints", _safe_int(upcoming.get("cnt")) if upcoming else 0, 0, True, "count"))

    # Client referrals generated
    refs = execute_single(f"SELECT COALESCE(SUM(referrals_sent),0) as total FROM mum_clients {of}", op)
    insights.append(_make_insight("mum", "client_referrals", "Client Referrals Generated", _safe_int(refs.get("total")) if refs else 0, 0, True, "count"))

    return insights
```

- [ ] **Step 3: Write tests, run, verify pass**
- [ ] **Step 4: Commit**

```bash
git add backend/agents/tools/trend_analysis.py backend/tests/test_trend_analysis.py
git commit -m "feat: implement referral partner and MUM trend analyzers"
```

---

### Task 9: Implement team, AI ops, documents, applications, system analyzers

**Files:**
- Modify: `backend/agents/tools/trend_analysis.py` — replace remaining 5 stubs

- [ ] **Step 1: Implement _analyze_team**

```python
def _analyze_team(cs, ce, ps, pe, uid, role):
    if role in ("sales", "processing", "operations"):
        return []
    insights = []

    # Per-LO funded volume (top 10)
    cur_lo = execute_query(
        f"SELECT u.first_name || ' ' || u.last_name as lo_name, COUNT(l.id) as cnt, COALESCE(SUM(l.amount),0) as vol "
        f"FROM loans l JOIN users u ON l.loan_officer_id = u.id "
        f"WHERE l.funded_date >= :s AND l.funded_date <= :e "
        f"GROUP BY u.id, u.first_name, u.last_name ORDER BY vol DESC LIMIT 10",
        {"s": cs, "e": ce},
    )
    pri_lo = execute_query(
        f"SELECT u.first_name || ' ' || u.last_name as lo_name, COUNT(l.id) as cnt, COALESCE(SUM(l.amount),0) as vol "
        f"FROM loans l JOIN users u ON l.loan_officer_id = u.id "
        f"WHERE l.funded_date >= :s AND l.funded_date <= :e "
        f"GROUP BY u.id, u.first_name, u.last_name ORDER BY vol DESC LIMIT 10",
        {"s": ps, "e": pe},
    )
    pri_lo_map = {r["lo_name"]: _safe_float(r["vol"]) for r in pri_lo}
    for row in cur_lo:
        name = row["lo_name"]
        insights.append(_make_insight("team", f"lo_volume_{name}", f"{name} — Funded Volume", _safe_float(row["vol"]), pri_lo_map.get(name, 0), True, "currency"))

    # Per-LO lead count
    cur_leads = execute_query(
        f"SELECT u.first_name || ' ' || u.last_name as lo_name, COUNT(l.id) as cnt "
        f"FROM leads l JOIN users u ON l.owner_id = u.id "
        f"WHERE l.created_at >= :s AND l.created_at <= :e "
        f"GROUP BY u.id, u.first_name, u.last_name ORDER BY cnt DESC LIMIT 10",
        {"s": cs, "e": ce},
    )
    pri_leads = execute_query(
        f"SELECT u.first_name || ' ' || u.last_name as lo_name, COUNT(l.id) as cnt "
        f"FROM leads l JOIN users u ON l.owner_id = u.id "
        f"WHERE l.created_at >= :s AND l.created_at <= :e "
        f"GROUP BY u.id, u.first_name, u.last_name ORDER BY cnt DESC LIMIT 10",
        {"s": ps, "e": pe},
    )
    pri_leads_map = {r["lo_name"]: _safe_int(r["cnt"]) for r in pri_leads}
    for row in cur_leads:
        name = row["lo_name"]
        insights.append(_make_insight("team", f"lo_leads_{name}", f"{name} — New Leads", _safe_int(row["cnt"]), pri_leads_map.get(name, 0), True, "count"))

    # Per-LO avg response time
    cur_resp = execute_query(
        f"SELECT u.first_name || ' ' || u.last_name as lo_name, "
        f"AVG(EXTRACT(EPOCH FROM (l.first_contact_attempt_date - l.lead_received_date)) / 86400) as avg_days "
        f"FROM leads l JOIN users u ON l.owner_id = u.id "
        f"WHERE l.first_contact_attempt_date IS NOT NULL AND l.lead_received_date IS NOT NULL "
        f"AND l.created_at >= :s AND l.created_at <= :e "
        f"GROUP BY u.id, u.first_name, u.last_name ORDER BY avg_days ASC LIMIT 10",
        {"s": cs, "e": ce},
    )
    for row in cur_resp:
        if row.get("avg_days") is not None:
            insights.append(_make_insight("team", f"lo_response_{row['lo_name']}", f"{row['lo_name']} — Avg Response Time", _safe_float(row["avg_days"]), 0, False, "days"))

    return insights
```

- [ ] **Step 2: Implement _analyze_ai_ops**

```python
def _analyze_ai_ops(cs, ce, ps, pe, uid, role):
    if role not in ("admin", "site_admin", "leadership", "management"):
        return []
    insights = []

    # AI action approval rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM ai_actions WHERE created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        approved = execute_single("SELECT COUNT(*) as cnt FROM ai_actions WHERE status IN ('approved','auto_approved') AND created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        a = _safe_int(approved.get("cnt")) if approved else 0
        rate = (a / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_approval = rate
        else:
            pri_approval = rate
    insights.append(_make_insight("ai_ops", "ai_approval_rate", "AI Action Approval Rate", cur_approval, pri_approval, True, "percent"))

    # Autonomous execution rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM ai_actions WHERE created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        auto = execute_single("SELECT COUNT(*) as cnt FROM ai_actions WHERE status = 'auto_approved' AND created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        a = _safe_int(auto.get("cnt")) if auto else 0
        rate = (a / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_auto = rate
        else:
            pri_auto = rate
    insights.append(_make_insight("ai_ops", "autonomous_rate", "Autonomous Execution Rate", cur_auto, pri_auto, True, "percent"))

    # AI feedback volume
    cur_fb = execute_single("SELECT COUNT(*) as cnt FROM ai_feedback_logs WHERE created_at >= :s AND created_at <= :e", {"s": cs, "e": ce})
    pri_fb = execute_single("SELECT COUNT(*) as cnt FROM ai_feedback_logs WHERE created_at >= :s AND created_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("ai_ops", "feedback_volume", "AI Feedback Reports", _safe_int(cur_fb.get("cnt")) if cur_fb else 0, _safe_int(pri_fb.get("cnt")) if pri_fb else 0, False, "count"))

    # AI cost trend
    cur_cost = execute_single("SELECT COALESCE(SUM(cost_estimate),0) as cost, COALESCE(SUM(tokens_used),0) as tokens FROM ai_audit_logs WHERE created_at >= :s AND created_at <= :e", {"s": cs, "e": ce})
    pri_cost = execute_single("SELECT COALESCE(SUM(cost_estimate),0) as cost, COALESCE(SUM(tokens_used),0) as tokens FROM ai_audit_logs WHERE created_at >= :s AND created_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("ai_ops", "ai_cost", "AI Cost", _safe_float(cur_cost.get("cost")) if cur_cost else 0, _safe_float(pri_cost.get("cost")) if pri_cost else 0, False, "currency"))
    insights.append(_make_insight("ai_ops", "ai_tokens", "AI Tokens Used", _safe_float(cur_cost.get("tokens")) if cur_cost else 0, _safe_float(pri_cost.get("tokens")) if pri_cost else 0, False, "count"))

    return insights
```

- [ ] **Step 3: Implement _analyze_documents**

```python
def _analyze_documents(cs, ce, ps, pe, uid, role):
    insights = []

    cur_docs = execute_single("SELECT COUNT(*) as cnt FROM documents WHERE uploaded_at >= :s AND uploaded_at <= :e", {"s": cs, "e": ce})
    pri_docs = execute_single("SELECT COUNT(*) as cnt FROM documents WHERE uploaded_at >= :s AND uploaded_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("documents", "docs_uploaded", "Documents Uploaded", _safe_int(cur_docs.get("cnt")) if cur_docs else 0, _safe_int(pri_docs.get("cnt")) if pri_docs else 0, True, "count"))

    # Email intake match rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM email_intakes WHERE received_at >= :s AND received_at <= :e", {"s": s, "e": e})
        matched = execute_single("SELECT COUNT(*) as cnt FROM email_intakes WHERE match_status = 'MATCHED' AND received_at >= :s AND received_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        m = _safe_int(matched.get("cnt")) if matched else 0
        rate = (m / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_match = rate
        else:
            pri_match = rate
    if (_safe_int(total.get("cnt")) if total else 0) > 0:
        insights.append(_make_insight("documents", "intake_match_rate", "Email Intake Match Rate", cur_match, pri_match, True, "percent"))

    # AI classification rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM attachment_intakes WHERE created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        classified = execute_single("SELECT COUNT(*) as cnt FROM attachment_intakes WHERE classification_status = 'CLASSIFIED' AND created_at >= :s AND created_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        c = _safe_int(classified.get("cnt")) if classified else 0
        rate = (c / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_class = rate
        else:
            pri_class = rate
    insights.append(_make_insight("documents", "classification_rate", "AI Classification Rate", cur_class, pri_class, True, "percent"))

    return insights
```

- [ ] **Step 4: Implement _analyze_applications**

```python
def _analyze_applications(cs, ce, ps, pe, uid, role):
    insights = []

    # Application starts
    cur_starts = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE started_at >= :s AND started_at <= :e", {"s": cs, "e": ce})
    pri_starts = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE started_at >= :s AND started_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("applications", "app_starts", "Application Starts", _safe_int(cur_starts.get("cnt")) if cur_starts else 0, _safe_int(pri_starts.get("cnt")) if pri_starts else 0, True, "count"))

    # Completion rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE started_at >= :s AND started_at <= :e", {"s": s, "e": e})
        submitted = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE status = 'SUBMITTED' AND started_at >= :s AND started_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        sub = _safe_int(submitted.get("cnt")) if submitted else 0
        rate = (sub / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_comp = rate
        else:
            pri_comp = rate
    insights.append(_make_insight("applications", "completion_rate", "Application Completion Rate", cur_comp, pri_comp, True, "percent"))

    # Avg time to complete
    cur_time = execute_single("SELECT AVG(time_spent_seconds) / 60 as avg_min FROM borrower_applications WHERE status = 'SUBMITTED' AND started_at >= :s AND started_at <= :e", {"s": cs, "e": ce})
    pri_time = execute_single("SELECT AVG(time_spent_seconds) / 60 as avg_min FROM borrower_applications WHERE status = 'SUBMITTED' AND started_at >= :s AND started_at <= :e", {"s": ps, "e": pe})
    cv = _safe_float(cur_time.get("avg_min")) if cur_time else 0
    pv = _safe_float(pri_time.get("avg_min")) if pri_time else 0
    if cv > 0 or pv > 0:
        insights.append(_make_insight("applications", "avg_completion_time", "Avg Completion Time (min)", cv, pv, False, "count"))

    # Expired applications
    cur_exp = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE status = 'EXPIRED' AND started_at >= :s AND started_at <= :e", {"s": cs, "e": ce})
    pri_exp = execute_single("SELECT COUNT(*) as cnt FROM borrower_applications WHERE status = 'EXPIRED' AND started_at >= :s AND started_at <= :e", {"s": ps, "e": pe})
    insights.append(_make_insight("applications", "expired_apps", "Expired Applications", _safe_int(cur_exp.get("cnt")) if cur_exp else 0, _safe_int(pri_exp.get("cnt")) if pri_exp else 0, False, "count"))

    return insights
```

- [ ] **Step 5: Implement _analyze_system**

```python
def _analyze_system(cs, ce, ps, pe, uid, role):
    if role not in ("admin", "site_admin"):
        return []
    insights = []

    # Daily active users (latest snapshot)
    cur_snap = execute_single("SELECT active_users_total, active_users_with_2fa, failed_login_attempts_24h FROM security_snapshot_daily ORDER BY date DESC LIMIT 1")
    if cur_snap:
        insights.append(_make_insight("system", "daily_active_users", "Daily Active Users", _safe_int(cur_snap.get("active_users_total")), 0, True, "count"))
        total = _safe_int(cur_snap.get("active_users_total"))
        mfa = _safe_int(cur_snap.get("active_users_with_2fa"))
        mfa_pct = (mfa / total * 100) if total > 0 else 0
        insights.append(_make_insight("system", "2fa_adoption", "2FA Adoption Rate", mfa_pct, 0, True, "percent"))
        insights.append(_make_insight("system", "failed_logins", "Failed Login Attempts (24h)", _safe_int(cur_snap.get("failed_login_attempts_24h")), 0, False, "count"))

    # Integration health
    integrations = execute_query("SELECT integration_name, status, error_count_24h, latency_ms FROM integration_status_log ORDER BY checked_at DESC LIMIT 10")
    degraded = sum(1 for i in integrations if i.get("status") != "connected")
    insights.append(_make_insight("system", "integration_health", "Integrations Healthy", len(integrations) - degraded, len(integrations), True, "count", f"{degraded} degraded/down" if degraded > 0 else "All healthy"))

    # Batch job success rate
    for period_tag, s, e in [("cur", cs, ce), ("pri", ps, pe)]:
        total = execute_single("SELECT COUNT(*) as cnt FROM system_jobs_log WHERE last_run_at >= :s AND last_run_at <= :e", {"s": s, "e": e})
        success = execute_single("SELECT COUNT(*) as cnt FROM system_jobs_log WHERE status = 'success' AND last_run_at >= :s AND last_run_at <= :e", {"s": s, "e": e})
        t = _safe_int(total.get("cnt")) if total else 0
        su = _safe_int(success.get("cnt")) if success else 0
        rate = (su / t * 100) if t > 0 else 0
        if period_tag == "cur":
            cur_job = rate
        else:
            pri_job = rate
    insights.append(_make_insight("system", "job_success_rate", "Batch Job Success Rate", cur_job, pri_job, True, "percent"))

    # System alerts
    cur_alerts = execute_single("SELECT COUNT(*) as cnt FROM system_alerts WHERE is_resolved = false")
    if cur_alerts:
        insights.append(_make_insight("system", "open_alerts", "Open System Alerts", _safe_int(cur_alerts.get("cnt")), 0, False, "count"))

    return insights
```

- [ ] **Step 6: Write tests for team analyzer (mock pattern), run all, verify pass**
- [ ] **Step 7: Commit**

```bash
git add backend/agents/tools/trend_analysis.py backend/tests/test_trend_analysis.py
git commit -m "feat: implement team, AI ops, document, application, and system trend analyzers"
```

---

### Task 10: Register tool and smoke test

**Files:**
- Modify: `backend/agents/tools/__init__.py` (add import)

- [ ] **Step 1: Add import to __init__.py**

After the line `from . import historical` (line ~100), add:

```python
# Trend Analysis
from . import trend_analysis
```

- [ ] **Step 2: Verify tool registers**

```bash
cd /Users/timothyloss/my-project/mortgage-crm && PYTHONPATH=backend .venv/bin/python -c "
from agents.tools import tool_registry
t = tool_registry.get('analyze_trends')
print(f'Tool: {t.name}')
print(f'Roles: {t.agent_roles}')
print(f'Description: {t.description[:80]}...')
"
```

Expected: Prints tool name, roles, description without errors.

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/timothyloss/my-project/mortgage-crm && PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_trend_analysis.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/agents/tools/__init__.py
git commit -m "feat: register analyze_trends tool in agent tools package"
```

---

## Self-Review Notes

- **Spec coverage:** All 13 domains implemented. All KPIs from spec covered. Email rendering, role scoping, period comparison all present.
- **Placeholder scan:** No TBDs or TODOs in implementation code. Stubs are created in Task 2 and filled in Tasks 3-9.
- **Type consistency:** `_make_insight` returns `Dict[str, Any]` throughout. All analyzers follow same `(cs, ce, ps, pe, uid, role)` signature. `_owner_filter` returns `Tuple[str, Dict]` used consistently.
- **SQLite note:** The `EXTRACT(EPOCH FROM ...)` syntax is PostgreSQL-only. Since production runs PostgreSQL and these are aggregate analytics queries, this is acceptable. Local SQLite testing uses mocked `execute_query`.
