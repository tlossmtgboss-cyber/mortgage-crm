"""
Trend Report HTML Email Renderer
=================================
Formats Aria trend insights into a professional email and delivers it via
EmailDeliveryService.

Public API
----------
- render_trend_report_html(insights, period_label, time_window) -> str
- send_trend_report(to_email, html_body, period_label, organization_id, user_id) -> dict
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain configuration
# ---------------------------------------------------------------------------

DOMAIN_CONFIG: Dict[str, Dict[str, str]] = {
    "leads":        {"label": "Lead Pipeline",              "icon": "🏠"},
    "loans":        {"label": "Loan Pipeline",              "icon": "📋"},
    "pipeline":     {"label": "Process Flow & SLA",         "icon": "⏱"},
    "compliance":   {"label": "Compliance",                 "icon": "✅"},
    "communication": {"label": "Communication & Activity",  "icon": "💬"},
    "dialer":       {"label": "Dialer & Calls",             "icon": "📞"},
    "referrals":    {"label": "Referral Partners",          "icon": "🤝"},
    "mum":          {"label": "Mortgage Under Management",  "icon": "🏦"},
    "team":         {"label": "Team Performance",           "icon": "👥"},
    "ai_ops":       {"label": "AI Operations",              "icon": "🤖"},
    "documents":    {"label": "Document Flow",              "icon": "📄"},
    "applications": {"label": "Borrower Applications",      "icon": "📝"},
    "system":       {"label": "System Health & Security",   "icon": "🔒"},
}

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_value(value: Any, unit: str) -> str:
    """Format a metric value according to its unit type."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    if unit == "currency":
        return f"${num:,.0f}"
    if unit == "percent":
        return f"{num:.1f}%"
    if unit == "days":
        return f"{num:.1f} days"
    # default: comma-separated integer
    return f"{int(num):,}"


def _trend_arrow(direction: str, is_positive: bool) -> str:
    """Return an HTML <span> with a colored directional arrow."""
    if direction == "up":
        color = "#16a34a" if is_positive else "#dc2626"
        arrow = "▲"
    elif direction == "down":
        color = "#dc2626" if is_positive else "#16a34a"
        arrow = "▼"
    else:
        color = "#6b7280"
        arrow = "━"
    return f'<span style="color:{color};font-weight:bold;">{arrow}</span>'


def _delta_badge(delta_pct: float, is_positive: bool, direction: str) -> str:
    """Return a colored pill badge showing the percentage change."""
    abs_delta = abs(delta_pct)
    sign = "+" if delta_pct >= 0 else "-"

    if abs_delta < 5:
        bg = "#f3f4f6"
        fg = "#374151"
    elif (direction == "up" and is_positive) or (direction == "down" and not is_positive):
        bg = "#dcfce7"
        fg = "#166534"
    else:
        bg = "#fee2e2"
        fg = "#991b1b"

    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:9999px;font-size:12px;font-weight:600;white-space:nowrap;">'
        f"{sign}{abs_delta:.1f}%</span>"
    )


# ---------------------------------------------------------------------------
# Row / section builders
# ---------------------------------------------------------------------------


def _metric_row(insight: Dict) -> str:
    label = insight.get("label", insight.get("metric", ""))
    unit = insight.get("unit", "count")
    prior = _format_value(insight.get("prior_value"), unit)
    current = _format_value(insight.get("current_value"), unit)
    direction = insight.get("direction", "flat")
    is_positive = bool(insight.get("is_positive", True))
    delta_pct = float(insight.get("delta_pct", 0))

    arrow = _trend_arrow(direction, is_positive)
    badge = _delta_badge(delta_pct, is_positive, direction)
    context = insight.get("context", "")
    context_html = (
        f'<br><span style="font-size:11px;color:#6b7280;">{context}</span>'
        if context
        else ""
    )

    return (
        f"<tr>"
        f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;">'
        f"{label}{context_html}</td>"
        f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;color:#6b7280;'
        f'text-align:right;">{prior}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right;">'
        f"{arrow} {current}</td>"
        f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right;">'
        f"{badge}</td>"
        f"</tr>"
    )


def _table(rows_html: str) -> str:
    header = (
        "<tr>"
        '<th style="padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;'
        'font-weight:600;border-bottom:2px solid #e2e8f0;">Metric</th>'
        '<th style="padding:8px 12px;text-align:right;font-size:12px;color:#6b7280;'
        'font-weight:600;border-bottom:2px solid #e2e8f0;">Prior</th>'
        '<th style="padding:8px 12px;text-align:right;font-size:12px;color:#6b7280;'
        'font-weight:600;border-bottom:2px solid #e2e8f0;">Current</th>'
        '<th style="padding:8px 12px;text-align:right;font-size:12px;color:#6b7280;'
        'font-weight:600;border-bottom:2px solid #e2e8f0;">Change</th>'
        "</tr>"
    )
    return (
        '<table style="width:100%;border-collapse:collapse;margin-bottom:24px;">'
        f"<thead>{header}</thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


def _domain_section(domain_key: str, insights: List[Dict]) -> str:
    cfg = DOMAIN_CONFIG.get(domain_key, {"label": domain_key.title(), "icon": "•"})
    icon = cfg["icon"]
    label = cfg["label"]
    rows = "".join(_metric_row(i) for i in insights)
    return (
        f'<div style="margin-bottom:32px;">'
        f'<h3 style="margin:0 0 12px 0;font-size:15px;font-weight:700;color:#1e293b;">'
        f"{icon} {label}</h3>"
        f"{_table(rows)}"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------


def render_trend_report_html(
    insights: List[Dict],
    period_label: str,
    time_window: str,
) -> str:
    """Render trend insights into a complete HTML email string."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not insights:
        body = (
            '<div style="text-align:center;padding:48px 24px;color:#6b7280;">'
            "<p>No significant trends detected for this period.</p>"
            "</div>"
        )
        return _wrap_html(body, period_label, generated_at)

    # Sort by significance descending
    sorted_insights = sorted(
        insights, key=lambda i: abs(float(i.get("significance", i.get("delta_pct", 0)))), reverse=True
    )

    sections: List[str] = []

    # Notable Changes — top 5
    top5 = sorted_insights[:5]
    top5_rows = "".join(_metric_row(i) for i in top5)
    sections.append(
        '<div style="margin-bottom:32px;">'
        '<h2 style="margin:0 0 16px 0;font-size:18px;font-weight:700;color:#0f172a;'
        'border-left:4px solid #6366f1;padding-left:12px;">Notable Changes</h2>'
        + _table(top5_rows)
        + "</div>"
    )

    # Remaining grouped by domain (DOMAIN_CONFIG order)
    remaining = sorted_insights[5:]
    if remaining:
        # Group by domain preserving DOMAIN_CONFIG order
        domain_order = list(DOMAIN_CONFIG.keys())
        by_domain: Dict[str, List[Dict]] = {}
        for insight in remaining:
            d = insight.get("domain", "system")
            by_domain.setdefault(d, []).append(insight)

        sections.append(
            '<h2 style="margin:0 0 24px 0;font-size:16px;font-weight:700;color:#0f172a;">'
            "All Metrics by Domain</h2>"
        )
        # Emit in DOMAIN_CONFIG order, then any unknown domains
        emitted = set()
        for dk in domain_order:
            if dk in by_domain:
                sections.append(_domain_section(dk, by_domain[dk]))
                emitted.add(dk)
        for dk, group in by_domain.items():
            if dk not in emitted:
                sections.append(_domain_section(dk, group))

    body = "\n".join(sections)
    return _wrap_html(body, period_label, generated_at)


# ---------------------------------------------------------------------------
# HTML wrapper
# ---------------------------------------------------------------------------


def _wrap_html(body: str, period_label: str, generated_at: str) -> str:
    """Wrap content in a full HTML email document with Perennia branding."""
    return f"""<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Perennia Trend Report</title>
</head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <div style="max-width:680px;width:100%;">
        <!-- Header -->
        <div style="background:#0f172a;border-radius:12px 12px 0 0;padding:32px 40px;">
          <h1 style="margin:0 0 8px 0;font-size:24px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">
            Perennia Trend Report
          </h1>
          <p style="margin:0;font-size:14px;color:#94a3b8;">{period_label}</p>
        </div>
        <!-- Content -->
        <div style="background:#ffffff;padding:40px;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0;">
          {body}
        </div>
        <!-- Footer -->
        <div style="background:#f1f5f9;border-radius:0 0 12px 12px;padding:16px 40px;
             border:1px solid #e2e8f0;border-top:none;text-align:center;">
          <p style="margin:0;font-size:12px;color:#94a3b8;">
            Generated {generated_at} &mdash; Perennia AI
          </p>
        </div>
      </div>
    </td>
  </tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Sync send wrapper
# ---------------------------------------------------------------------------


def send_trend_report(
    to_email: str,
    html_body: str,
    period_label: str,
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sync wrapper around EmailDeliveryService.send_email().

    Returns {"success": bool, "error": str|None, "provider": str}.
    """
    subject = f"Perennia Trend Report — {period_label}"

    async def _send() -> Dict[str, Any]:
        # Import inside coroutine to defer heavy imports and avoid circular refs
        from database import SessionLocal
        from services.email_delivery_service import EmailDeliveryService

        db = SessionLocal()
        try:
            service = EmailDeliveryService(db)
            result = await service.send_email(
                to=to_email,
                subject=subject,
                html_body=html_body,
                organization_id=organization_id,
                user_id=user_id,
            )
            provider = getattr(result, "provider", None)
            return {
                "success": result.success,
                "error": None if result.success else getattr(result, "error", "unknown"),
                "provider": str(provider) if provider else "unknown",
            }
        finally:
            db.close()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if loop is not None and loop.is_running():
            # We're inside a running event loop (e.g., FastAPI request context).
            # Run the coroutine in a fresh thread with its own event loop.
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, _send())
                return future.result()
        else:
            return asyncio.run(_send())
    except Exception as exc:
        logger.exception("send_trend_report failed for %s", to_email)
        return {"success": False, "error": str(exc), "provider": "unknown"}
