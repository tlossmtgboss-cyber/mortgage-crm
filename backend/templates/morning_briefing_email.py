"""
Morning Briefing Email Template

Renders BriefingContext into responsive HTML email with inline CSS.
Level-aware: individual, manager, and leadership sections.
"""
from __future__ import annotations
import html
from datetime import date
from typing import Any, Dict, List, Optional


def _esc(value) -> str:
    """HTML-escape a database value for safe insertion into email HTML."""
    return html.escape(str(value)) if value is not None else ""


def _darken_hex(hex_color: str, factor: float = 0.15) -> str:
    """Darken a hex color by a factor (0-1). Used for gradient end-stop."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return f"#{hex_color}"
    r = max(0, int(int(hex_color[0:2], 16) * (1 - factor)))
    g = max(0, int(int(hex_color[2:4], 16) * (1 - factor)))
    b = max(0, int(int(hex_color[4:6], 16) * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def render_briefing_email(
    user_name: str,
    briefing_date: date,
    level: str,
    ai_narrative: Optional[str],
    pipeline: Dict[str, Any],
    at_risk: List[Dict],
    stale_leads: List[Dict],
    appointments: List[Dict],
    conditions: List[Dict],
    yesterday: Dict[str, Any],
    team: Optional[Dict[str, Any]] = None,
    app_url: str = "https://app.perenniaai.com",
    # Branding params:
    company_name: str = "The Tim Loss Team",
    logo_url: Optional[str] = None,
    primary_color: str = "#218d8d",
    secondary_color: Optional[str] = None,
) -> str:
    """Render complete briefing email HTML."""
    date_str = briefing_date.strftime("%B %d, %Y")
    short_date = briefing_date.strftime("%b %d")

    active = pipeline.get("active_count", 0)
    volume = pipeline.get("total_volume", 0)

    if level == "leadership" and team:
        subject_detail = f"${volume / 1_000_000:.1f}M pipeline"
    elif level == "manager" and team:
        member_count = len(team.get("members", []))
        subject_detail = f"{member_count} team members"
    else:
        subject_detail = f"{active} active loans"

    brand = primary_color
    gradient_end = _darken_hex(primary_color)

    sections = []

    # AI narrative
    if ai_narrative:
        sections.append(_section_priorities(ai_narrative, brand_color=brand))
    else:
        sections.append(_section_priorities_unavailable(brand_color=brand))

    sections.append(_divider())

    # Personal pipeline (all levels)
    if active > 0 or level == "individual":
        sections.append(_section_pipeline(pipeline, brand_color=brand))

    # At-risk
    if at_risk:
        sections.append(_section_at_risk(at_risk))

    # Stale leads
    if stale_leads:
        sections.append(_section_stale_leads(stale_leads))

    # Appointments
    if appointments:
        sections.append(_section_appointments(appointments, brand_color=brand))

    # Conditions
    if conditions:
        sections.append(_section_conditions(conditions))

    # Team section (manager)
    if level == "manager" and team:
        sections.append(_divider())
        sections.append(_section_team(team, brand_color=brand))

    # Org section (leadership)
    if level == "leadership" and team:
        sections.append(_divider())
        sections.append(_section_org(team, brand_color=brand))

    body = "\n".join(sections)

    # Optional logo in header
    logo_html = ""
    if logo_url:
        logo_html = f'<img src="{logo_url}" alt="{company_name}" style="max-height:40px;max-width:200px;margin-bottom:12px;display:block;">\n  '

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;max-width:600px;width:100%;">

<!-- Header -->
<tr><td style="background:linear-gradient(135deg,{primary_color},{gradient_end});padding:28px 32px;">
  {logo_html}<h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">Good morning, {_esc(user_name)}</h1>
  <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">{_esc(date_str)}</p>
</td></tr>

<!-- Content -->
<tr><td style="padding:24px 32px 32px;">
{body}
</td></tr>

<!-- CTA -->
<tr><td style="padding:0 32px 32px;" align="center">
  <a href="{app_url}/dashboard" style="display:inline-block;background:{primary_color};color:#ffffff;padding:12px 32px;border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;">Open {_esc(company_name)}</a>
</td></tr>

<!-- Footer -->
<tr><td style="padding:16px 32px;border-top:1px solid #e8e8ed;background:#fafafa;">
  <p style="margin:0;color:#8888a0;font-size:11px;text-align:center;">
    Adjust or disable morning briefings in <a href="{app_url}/settings" style="color:{primary_color};">Settings</a>
  </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _section_priorities(narrative: str, brand_color: str = "#218d8d") -> str:
    # Convert numbered items to styled HTML
    lines = narrative.strip().split("\n")
    items_html = ""
    for line in lines:
        line = line.strip()
        if line:
            items_html += f'<p style="margin:8px 0;color:#1a1a2a;font-size:14px;line-height:1.6;">{_esc(line)}</p>\n'

    return f"""
<h2 style="margin:0 0 12px;color:{brand_color};font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Top 3 Priorities</h2>
{items_html}"""


def _section_priorities_unavailable(brand_color: str = "#218d8d") -> str:
    return f"""
<h2 style="margin:0 0 12px;color:{brand_color};font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Your Pipeline</h2>
<p style="margin:0;color:#8888a0;font-size:13px;font-style:italic;">AI priorities unavailable today — here's your pipeline data.</p>"""


def _divider() -> str:
    return '<hr style="border:none;border-top:1px solid #e8e8ed;margin:20px 0;">'


def _section_pipeline(pipeline: Dict, brand_color: str = "#218d8d") -> str:
    active = pipeline.get("active_count", 0)
    volume = pipeline.get("total_volume", 0)
    closing = pipeline.get("closing_soon", 0)
    by_stage = pipeline.get("by_stage", {})

    stage_rows = ""
    for stage, cnt in by_stage.items():
        stage_rows += f'<tr><td style="padding:6px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;color:#4a4a5a;">{_esc(stage)}</td><td style="padding:6px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;color:#1a1a2a;font-weight:600;text-align:right;">{_esc(cnt)}</td></tr>\n'

    return f"""
<h2 style="margin:0 0 8px;color:{brand_color};font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Pipeline Snapshot</h2>
<p style="margin:0 0 12px;color:#4a4a5a;font-size:14px;">{active} active loans &middot; ${volume:,.0f} volume &middot; {closing} closing this week</p>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;border-radius:6px;overflow:hidden;">
<tr><th style="padding:8px 12px;text-align:left;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Stage</th><th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Count</th></tr>
{stage_rows}</table>"""


def _section_at_risk(items: List[Dict]) -> str:
    rows = ""
    for item in items:
        rows += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{_esc(item["borrower"])}</strong> ({_esc(item.get("loan_number", ""))}) — {_esc(item["reason"])}</li>\n'
    return f"""
<h2 style="margin:20px 0 8px;color:#e74c3c;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">&#9888; At-Risk ({len(items)} loans)</h2>
<ul style="margin:0;padding-left:20px;">{rows}</ul>"""


def _section_stale_leads(items: List[Dict]) -> str:
    rows = ""
    for item in items:
        rows += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{_esc(item["name"])}</strong> (score {_esc(item.get("score", "?"))}) — {item["days_silent"]:.0f} days quiet</li>\n'
    return f"""
<h2 style="margin:20px 0 8px;color:#f39c12;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">&#128293; Leads Going Cold ({len(items)})</h2>
<ul style="margin:0;padding-left:20px;">{rows}</ul>"""


def _section_appointments(items: List[Dict], brand_color: str = "#218d8d") -> str:
    rows = ""
    for item in items:
        rows += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{_esc(item["time"])}</strong> — {_esc(item["attendee"])}, {_esc(item["type"])}</li>\n'
    return f"""
<h2 style="margin:20px 0 8px;color:{brand_color};font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">&#128197; Today's Appointments ({len(items)})</h2>
<ul style="margin:0;padding-left:20px;">{rows}</ul>"""


def _section_conditions(items: List[Dict]) -> str:
    rows = ""
    for item in items:
        pd = ' <span style="color:#e74c3c;font-weight:700;">PAST DUE</span>' if item.get("past_due") else ""
        rows += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;">{_esc(item["title"])} on {_esc(item.get("loan_number", ""))}{pd}</li>\n'
    return f"""
<h2 style="margin:20px 0 8px;color:#8e44ad;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Pending Conditions ({len(items)})</h2>
<ul style="margin:0;padding-left:20px;">{rows}</ul>"""


def _health_dot(health: str) -> str:
    colors = {"green": "#27ae60", "yellow": "#f39c12", "red": "#e74c3c"}
    return f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{colors.get(health, "#ccc")};"></span>'


def _section_team(team: Dict, brand_color: str = "#218d8d") -> str:
    members = team.get("members", [])
    attention = team.get("attention_items", [])

    member_rows = ""
    for m in members:
        health = _health_dot(m.get("health", "green"))
        detail = ""
        if m.get("at_risk_count", 0) > 0:
            detail = f' &middot; {m["at_risk_count"]} at-risk'
        member_rows += f'''<tr>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;">{health} {_esc(m["name"])}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;">{_esc(m.get("loan_count", 0))}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;">${m.get("volume", 0):,.0f}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;color:#8888a0;">{_esc(m.get("health", "green"))}{detail}</td>
</tr>\n'''

    attention_html = ""
    if attention:
        items = ""
        for a in attention:
            items += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{_esc(a["user_name"])}</strong> — {_esc(a["issue"])}</li>\n'
        attention_html = f"""
<h3 style="margin:16px 0 8px;color:#e74c3c;font-size:13px;font-weight:700;text-transform:uppercase;">Team Attention Needed</h3>
<ul style="margin:0;padding-left:20px;">{items}</ul>"""

    return f"""
<h2 style="margin:0 0 12px;color:{brand_color};font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Your Team</h2>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;border-radius:6px;overflow:hidden;">
<tr>
<th style="padding:8px 12px;text-align:left;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Name</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Loans</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Volume</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Health</th>
</tr>
{member_rows}</table>
{attention_html}"""


def _section_org(team: Dict, brand_color: str = "#218d8d") -> str:
    snap = team.get("org_snapshot", {})
    branches = team.get("branches", [])
    risks = team.get("top_risks", [])

    trend_arrow = {"up": "&#8593;", "down": "&#8595;", "flat": "&#8594;"}.get(snap.get("funded_trend", "flat"), "&#8594;")

    branch_rows = ""
    for b in branches:
        health = _health_dot(b.get("health", "green"))
        branch_rows += f'''<tr>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;">{health} {_esc(b["name"])}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;">{_esc(b.get("loan_count", 0))}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;">${b.get("volume", 0):,.0f}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;color:#8888a0;">{_esc(b.get("health", "green"))}</td>
</tr>\n'''

    risk_items = ""
    if risks:
        for r in risks:
            risk_items += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{_esc(r["borrower"])}</strong> ({_esc(r["branch"])}, LO: {_esc(r["lo_name"])}) — {_esc(r["issue"])}</li>\n'

    risk_section = ""
    if risk_items:
        risk_section = f"""
<h3 style="margin:16px 0 8px;color:#e74c3c;font-size:13px;font-weight:700;text-transform:uppercase;">Top Risks (Org-Wide)</h3>
<ul style="margin:0;padding-left:20px;">{risk_items}</ul>"""

    return f"""
<h2 style="margin:0 0 8px;color:{brand_color};font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Organization Overview</h2>
<p style="margin:0 0 16px;color:#4a4a5a;font-size:14px;">
  ${snap.get('total_volume', 0):,.0f} pipeline &middot; {snap.get('active_count', 0)} active loans &middot;
  {snap.get('funded_this_week', 0)} funded this week {trend_arrow} vs {snap.get('funded_last_week', 0)} last week
</p>

<h3 style="margin:0 0 8px;color:#4a4a5a;font-size:13px;font-weight:700;text-transform:uppercase;">Branch Performance</h3>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;border-radius:6px;overflow:hidden;">
<tr>
<th style="padding:8px 12px;text-align:left;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Branch</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Loans</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Volume</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Health</th>
</tr>
{branch_rows}</table>
{risk_section}"""
