"""
Audit Report Share Service

Manages shareable links for CRM workflow audit reports.
Generates self-contained HTML pages for public viewing.
"""

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AuditReportShareService:
    """Service for managing shareable audit report links."""

    def __init__(self, db: Session):
        self.db = db

    def create_share_link(
        self,
        report_data: Dict[str, Any],
        user_id: Optional[int],
        expires_in_days: int = 30,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a shareable link for an audit report."""
        share_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        environment = report_data.get("environment", "unknown")
        report_title = title or report_data.get("title", "CRM Workflow Audit Report")

        self.db.execute(
            text("""
                INSERT INTO audit_report_shares (
                    share_token, report_data, report_title, environment,
                    created_by, created_at, expires_at, is_active
                ) VALUES (
                    :share_token, :report_data, :report_title, :environment,
                    :created_by, :created_at, :expires_at, true
                )
            """),
            {
                "share_token": share_token,
                "report_data": json.dumps(report_data),
                "report_title": report_title,
                "environment": environment,
                "created_by": user_id,
                "created_at": datetime.now(timezone.utc),
                "expires_at": expires_at,
            },
        )
        self.db.commit()

        share_url = f"/api/v1/audit-reports/shared/{share_token}"

        return {
            "share_token": share_token,
            "share_url": share_url,
            "report_title": report_title,
            "expires_at": expires_at.isoformat(),
            "expires_in_days": expires_in_days,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_shared_report(
        self,
        share_token: str,
        viewer_ip: Optional[str] = None,
        viewer_ua: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a shared audit report by token. Returns None if expired/inactive."""
        share = self.db.execute(
            text("""
                SELECT id, share_token, report_data, report_title, environment,
                       expires_at, is_active, view_count
                FROM audit_report_shares
                WHERE share_token = :share_token
            """),
            {"share_token": share_token},
        ).fetchone()

        if not share:
            return None

        if not share.is_active:
            return None

        if share.expires_at and share.expires_at < datetime.now(timezone.utc):
            return None

        # Increment view count
        self.db.execute(
            text("""
                UPDATE audit_report_shares
                SET view_count = view_count + 1,
                    last_viewed_at = :now,
                    last_viewer_ip = :viewer_ip,
                    last_viewer_user_agent = :viewer_ua
                WHERE share_token = :share_token
            """),
            {
                "share_token": share_token,
                "now": datetime.now(timezone.utc),
                "viewer_ip": viewer_ip,
                "viewer_ua": viewer_ua[:500] if viewer_ua else None,
            },
        )
        self.db.commit()

        report_data = share.report_data
        if isinstance(report_data, str):
            report_data = json.loads(report_data)

        return {
            "share_token": share.share_token,
            "report_data": report_data,
            "report_title": share.report_title,
            "environment": share.environment,
            "expires_at": share.expires_at.isoformat() if share.expires_at else None,
            "view_count": share.view_count + 1,
        }

    def deactivate_share(self, share_token: str, user_id: int) -> bool:
        """Deactivate a share link. Returns True if deactivated."""
        result = self.db.execute(
            text("""
                UPDATE audit_report_shares
                SET is_active = false
                WHERE share_token = :share_token
                    AND (created_by = :user_id OR :user_id IN (
                        SELECT id FROM users WHERE role IN ('admin', 'super_admin')
                    ))
            """),
            {"share_token": share_token, "user_id": user_id},
        )
        self.db.commit()
        return result.rowcount > 0

    def get_user_shares(
        self,
        user_id: int,
        include_expired: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get all audit report shares created by a user."""
        query = """
            SELECT id, share_token, report_title, environment,
                   created_at, expires_at, view_count, is_active
            FROM audit_report_shares
            WHERE created_by = :user_id
        """
        if not include_expired:
            query += " AND is_active = true AND (expires_at IS NULL OR expires_at > :now)"

        query += " ORDER BY created_at DESC LIMIT :limit"

        params = {
            "user_id": user_id,
            "now": datetime.now(timezone.utc),
            "limit": limit,
        }

        shares = self.db.execute(text(query), params).fetchall()

        return [
            {
                "id": s.id,
                "share_token": s.share_token,
                "report_title": s.report_title,
                "environment": s.environment,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "view_count": s.view_count,
                "is_active": s.is_active,
                "share_url": f"/api/v1/audit-reports/shared/{s.share_token}",
            }
            for s in shares
        ]


def generate_audit_html(report_data: Dict[str, Any], expires_at: Optional[str] = None) -> str:
    """Generate a self-contained HTML page for an audit report.

    Accepts both normalized format (top-level keys) and the raw
    audit-data.json format (metadata nested under ``audit_metadata``).
    """
    # Normalize: pull values from audit_metadata if present
    meta = report_data.get("audit_metadata", {})
    title = escape(
        report_data.get("title")
        or meta.get("title")
        or "CRM Workflow Audit Report"
    )
    environment = escape(
        report_data.get("environment")
        or meta.get("environment", "unknown")
    )
    generated_at = escape(
        report_data.get("generated_at")
        or meta.get("timestamp")
        or datetime.now(timezone.utc).isoformat()
    )
    summary = report_data.get("summary", {})
    findings = report_data.get("findings", [])
    sla_compliance = report_data.get("sla_compliance", {})
    task_distribution = report_data.get("task_distribution", {})
    trigger_health = report_data.get("trigger_health", {})

    # Health score
    health_score = summary.get("health_score", 0)
    total_checks = summary.get("total_checks", 0)
    critical_count = summary.get("critical", 0)
    warning_count = summary.get("warning", 0)
    pass_count = summary.get("pass", 0)
    skipped_count = summary.get("skipped", 0)

    # Score color
    if health_score >= 80:
        score_color = "#22c55e"
        score_label = "Healthy"
    elif health_score >= 60:
        score_color = "#f59e0b"
        score_label = "Needs Attention"
    else:
        score_color = "#ef4444"
        score_label = "Critical"

    # Gauge angle (0-360)
    gauge_deg = round(health_score / 100 * 360)

    # Build findings rows
    findings_html = _build_findings_table(findings)

    # Build SLA compliance section
    sla_html = _build_sla_section(sla_compliance)

    # Build task distribution section
    task_html = _build_task_distribution(task_distribution)

    # Build trigger health section
    trigger_html = _build_trigger_health(trigger_health)

    # Expiration notice
    expires_notice = ""
    if expires_at:
        expires_notice = f'<div class="expires-notice">This report link expires on {escape(expires_at[:10])}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f1f5f9;
            color: #1e293b;
            line-height: 1.6;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 24px 16px;
        }}
        .header {{
            background: #1a365d;
            color: white;
            padding: 32px 24px;
            border-radius: 12px 12px 0 0;
        }}
        .header h1 {{
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 4px;
        }}
        .header-meta {{
            font-size: 13px;
            opacity: 0.85;
        }}
        .content {{
            background: white;
            padding: 24px;
            border-radius: 0 0 12px 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .section {{
            margin-bottom: 32px;
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 700;
            color: #1a365d;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 2px solid #e2e8f0;
        }}

        /* Health Score Gauge */
        .score-row {{
            display: flex;
            align-items: center;
            gap: 32px;
            flex-wrap: wrap;
        }}
        .gauge {{
            width: 140px;
            height: 140px;
            border-radius: 50%;
            background: conic-gradient(
                {score_color} 0deg {gauge_deg}deg,
                #e2e8f0 {gauge_deg}deg 360deg
            );
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .gauge-inner {{
            width: 100px;
            height: 100px;
            border-radius: 50%;
            background: white;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}
        .gauge-score {{
            font-size: 32px;
            font-weight: 800;
            color: {score_color};
            line-height: 1;
        }}
        .gauge-label {{
            font-size: 11px;
            color: #64748b;
            margin-top: 2px;
        }}

        /* Stat Cards */
        .stat-cards {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            flex: 1;
        }}
        .stat-card {{
            flex: 1;
            min-width: 100px;
            padding: 14px 16px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-card .num {{
            font-size: 28px;
            font-weight: 800;
            line-height: 1;
        }}
        .stat-card .lbl {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 4px;
        }}
        .card-critical {{ background: #fef2f2; }}
        .card-critical .num {{ color: #ef4444; }}
        .card-critical .lbl {{ color: #b91c1c; }}
        .card-warning {{ background: #fffbeb; }}
        .card-warning .num {{ color: #f59e0b; }}
        .card-warning .lbl {{ color: #b45309; }}
        .card-pass {{ background: #f0fdf4; }}
        .card-pass .num {{ color: #22c55e; }}
        .card-pass .lbl {{ color: #15803d; }}
        .card-skipped {{ background: #f9fafb; }}
        .card-skipped .num {{ color: #9ca3af; }}
        .card-skipped .lbl {{ color: #6b7280; }}

        /* Findings Table */
        .findings-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        .findings-table th {{
            background: #f8fafc;
            text-align: left;
            padding: 10px 12px;
            font-weight: 600;
            color: #475569;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 2px solid #e2e8f0;
        }}
        .findings-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #f1f5f9;
            vertical-align: top;
        }}
        .findings-table tr:hover {{
            background: #f8fafc;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge-critical {{ background: #fef2f2; color: #dc2626; }}
        .badge-warning {{ background: #fffbeb; color: #d97706; }}
        .badge-pass {{ background: #f0fdf4; color: #16a34a; }}
        .badge-skipped {{ background: #f3f4f6; color: #6b7280; }}
        .badge-info {{ background: #eff6ff; color: #2563eb; }}

        /* SLA Table */
        .sla-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        .sla-table th {{
            background: #f8fafc;
            text-align: left;
            padding: 10px 12px;
            font-weight: 600;
            color: #475569;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 2px solid #e2e8f0;
        }}
        .sla-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #f1f5f9;
        }}

        /* Bar chart */
        .bar-row {{
            display: flex;
            align-items: center;
            margin-bottom: 10px;
        }}
        .bar-label {{
            width: 160px;
            font-size: 13px;
            color: #475569;
            flex-shrink: 0;
        }}
        .bar-track {{
            flex: 1;
            height: 24px;
            background: #f1f5f9;
            border-radius: 4px;
            overflow: hidden;
            position: relative;
        }}
        .bar-fill {{
            height: 100%;
            background: #2563eb;
            border-radius: 4px;
            min-width: 2px;
        }}
        .bar-value {{
            width: 50px;
            text-align: right;
            font-size: 13px;
            font-weight: 600;
            color: #1e293b;
            flex-shrink: 0;
            margin-left: 8px;
        }}

        /* Trigger health */
        .metrics-row {{
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
        }}
        .metric-box {{
            flex: 1;
            min-width: 120px;
            background: #f8fafc;
            padding: 14px 16px;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }}
        .metric-box .metric-val {{
            font-size: 22px;
            font-weight: 700;
            color: #1a365d;
        }}
        .metric-box .metric-lbl {{
            font-size: 12px;
            color: #64748b;
        }}

        /* Footer */
        .footer {{
            text-align: center;
            padding: 20px;
            font-size: 12px;
            color: #94a3b8;
        }}
        .expires-notice {{
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
            margin-top: 8px;
        }}

        /* Print styles */
        @media print {{
            body {{ background: white; }}
            .container {{ padding: 0; max-width: 100%; }}
            .header {{ border-radius: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .content {{ box-shadow: none; border-radius: 0; }}
            .gauge {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .stat-card {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .badge {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .bar-fill {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .bar-track {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .section {{ page-break-inside: avoid; }}
            .expires-notice {{ display: none; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>Perennia AI &mdash; {title}</h1>
        <div class="header-meta">
            Generated {escape(generated_at[:19].replace('T', ' '))} &middot; Environment: {environment} &middot; {total_checks} checks
        </div>
    </div>
    <div class="content">

        <!-- Executive Summary -->
        <div class="section">
            <div class="section-title">Executive Summary</div>
            <div class="score-row">
                <div class="gauge">
                    <div class="gauge-inner">
                        <div class="gauge-score">{health_score}</div>
                        <div class="gauge-label">{score_label}</div>
                    </div>
                </div>
                <div class="stat-cards">
                    <div class="stat-card card-critical">
                        <div class="num">{critical_count}</div>
                        <div class="lbl">Critical</div>
                    </div>
                    <div class="stat-card card-warning">
                        <div class="num">{warning_count}</div>
                        <div class="lbl">Warning</div>
                    </div>
                    <div class="stat-card card-pass">
                        <div class="num">{pass_count}</div>
                        <div class="lbl">Pass</div>
                    </div>
                    <div class="stat-card card-skipped">
                        <div class="num">{skipped_count}</div>
                        <div class="lbl">Skipped</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Findings -->
        {findings_html}

        <!-- SLA Compliance -->
        {sla_html}

        <!-- Task Distribution -->
        {task_html}

        <!-- Trigger Health -->
        {trigger_html}

    </div>
    <div class="footer">
        Perennia AI &mdash; Confidential
        {expires_notice}
    </div>
</div>
</body>
</html>"""


def _severity_badge(severity: str) -> str:
    """Return an HTML badge span for a severity level."""
    s = (severity or "info").lower()
    cls = f"badge-{s}" if s in ("critical", "warning", "pass", "skipped") else "badge-info"
    return f'<span class="badge {cls}">{escape(severity.upper())}</span>'


def _status_icon(status: str) -> str:
    """Return a text icon for finding status."""
    s = (status or "").lower()
    icons = {
        "critical": "&#10060;",  # red X
        "warning": "&#9888;&#65039;",  # warning sign
        "pass": "&#9989;",  # check
        "skipped": "&#9898;",  # white circle
    }
    return icons.get(s, "&#8226;")


def _build_findings_table(findings: list) -> str:
    """Build the findings table HTML."""
    if not findings:
        return ""

    rows = ""
    for f in findings:
        check_id = escape(str(f.get("check_id", f.get("id", ""))))
        category = escape(str(f.get("category", "")))
        severity = f.get("severity", f.get("status", "info"))
        finding = escape(str(f.get("finding", f.get("message", f.get("description", "")))))
        recommendation = escape(str(f.get("recommendation", "")))

        rows += f"""<tr>
            <td style="text-align:center;">{_status_icon(severity)}</td>
            <td><code>{check_id}</code></td>
            <td>{escape(category)}</td>
            <td>{finding}</td>
            <td>{_severity_badge(severity)}</td>
            <td style="font-size:12px;color:#64748b;">{recommendation}</td>
        </tr>
"""

    return f"""<div class="section">
            <div class="section-title">Findings</div>
            <div style="overflow-x:auto;">
            <table class="findings-table">
                <thead>
                    <tr>
                        <th style="width:36px;"></th>
                        <th>Check</th>
                        <th>Category</th>
                        <th>Finding</th>
                        <th>Severity</th>
                        <th>Recommendation</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            </div>
        </div>"""


def _build_sla_section(sla_compliance: dict) -> str:
    """Build the SLA compliance section HTML."""
    if not sla_compliance:
        return ""

    items = sla_compliance if isinstance(sla_compliance, list) else sla_compliance.get("items", sla_compliance.get("by_type", []))
    if isinstance(sla_compliance, dict) and not isinstance(items, list):
        # Handle flat dict with keys as task types
        flat_items = []
        for key, val in sla_compliance.items():
            if isinstance(val, dict):
                flat_items.append({"task_type": key, **val})
        items = flat_items

    if not items:
        return ""

    rows = ""
    for item in items:
        task_type = escape(str(item.get("task_type", item.get("type", item.get("milestone", "")))))
        compliance_rate = item.get("compliance_rate", item.get("rate", item.get("on_time_pct", 0)))
        total = item.get("total", item.get("count", 0))
        on_time = item.get("on_time", item.get("compliant", 0))
        breached = item.get("breached", item.get("violations", item.get("overdue", 0)))

        rate_val = float(compliance_rate) if compliance_rate else 0
        if rate_val >= 90:
            rate_color = "#22c55e"
        elif rate_val >= 70:
            rate_color = "#f59e0b"
        else:
            rate_color = "#ef4444"

        rows += f"""<tr>
            <td>{task_type}</td>
            <td style="font-weight:600;color:{rate_color};">{rate_val:.0f}%</td>
            <td>{total}</td>
            <td>{on_time}</td>
            <td>{breached}</td>
        </tr>
"""

    return f"""<div class="section">
            <div class="section-title">SLA Compliance</div>
            <table class="sla-table">
                <thead>
                    <tr>
                        <th>Task Type</th>
                        <th>Compliance Rate</th>
                        <th>Total</th>
                        <th>On Time</th>
                        <th>Breached</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>"""


def _build_task_distribution(task_distribution: dict) -> str:
    """Build the task distribution bar chart HTML."""
    if not task_distribution:
        return ""

    items = task_distribution if isinstance(task_distribution, list) else task_distribution.get("items", task_distribution.get("by_type", []))
    if isinstance(task_distribution, dict) and not isinstance(items, list):
        flat_items = []
        for key, val in task_distribution.items():
            if isinstance(val, (int, float)):
                flat_items.append({"type": key, "count": val})
            elif isinstance(val, dict):
                flat_items.append({"type": key, **val})
        items = flat_items

    if not items:
        return ""

    max_count = max((item.get("count", item.get("total", 0)) for item in items), default=1) or 1

    bars = ""
    for item in items:
        label = escape(str(item.get("type", item.get("task_type", item.get("name", "")))))
        count = item.get("count", item.get("total", 0))
        pct = (count / max_count) * 100 if max_count > 0 else 0

        bars += f"""<div class="bar-row">
                <div class="bar-label">{label}</div>
                <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;"></div></div>
                <div class="bar-value">{count}</div>
            </div>
"""

    return f"""<div class="section">
            <div class="section-title">Task Distribution</div>
            {bars}
        </div>"""


def _build_trigger_health(trigger_health: dict) -> str:
    """Build the trigger health metrics section HTML."""
    if not trigger_health:
        return ""

    # Accept either a flat dict of metrics or a structured dict
    metrics = trigger_health if isinstance(trigger_health, dict) else {}
    if not metrics:
        return ""

    # If there are nested items, use those; otherwise treat each key-value as a metric
    items = metrics.get("items", metrics.get("metrics", []))
    if isinstance(items, list) and items:
        boxes = ""
        for item in items:
            label = escape(str(item.get("label", item.get("name", ""))))
            value = item.get("value", 0)
            boxes += f"""<div class="metric-box">
                <div class="metric-val">{escape(str(value))}</div>
                <div class="metric-lbl">{label}</div>
            </div>
"""
    else:
        # Flat dict: show each k/v as a metric box
        skip_keys = {"items", "metrics"}
        boxes = ""
        for key, val in metrics.items():
            if key in skip_keys or isinstance(val, (dict, list)):
                continue
            label = escape(key.replace("_", " ").title())
            boxes += f"""<div class="metric-box">
                <div class="metric-val">{escape(str(val))}</div>
                <div class="metric-lbl">{label}</div>
            </div>
"""

    if not boxes:
        return ""

    return f"""<div class="section">
            <div class="section-title">Trigger Health</div>
            <div class="metrics-row">
                {boxes}
            </div>
        </div>"""


def generate_not_found_html(reason: str = "not found") -> str:
    """Generate a simple HTML page for expired or missing reports."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report Not Available</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f1f5f9;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background: white;
            border-radius: 12px;
            padding: 48px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            max-width: 400px;
        }}
        .card h1 {{ font-size: 20px; color: #1a365d; margin-bottom: 8px; }}
        .card p {{ color: #64748b; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Report Not Available</h1>
        <p>This audit report link has {escape(reason)}. Please request a new link from the report owner.</p>
    </div>
</body>
</html>"""
