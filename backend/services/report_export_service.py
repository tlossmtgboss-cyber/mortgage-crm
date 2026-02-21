"""
Report Export Service
=====================

Enterprise Readiness Domain 9: Analytics & Reporting

Provides:
1. PDF export for pipeline, scorecard, SLA compliance, and financial reports (Check 9.8)
2. Excel/XLSX export with formatted workbooks (Check 9.9)
3. SLA compliance report generation (Check 9.3)
4. CSV export (already exists, extended here for consistency)

Dependencies (already in requirements.txt):
    - reportlab >= 4.0.0
    - xhtml2pdf >= 0.2.11
    - openpyxl >= 3.1.0
    - pandas >= 2.0.0

Usage:
    from services.report_export_service import report_exporter

    # Generate PDF
    pdf_bytes = report_exporter.generate_pdf(report_data, report_type="pipeline")

    # Generate Excel
    xlsx_bytes = report_exporter.generate_excel(report_data, report_type="scorecard")

    # Generate SLA compliance report
    sla_report = report_exporter.generate_sla_compliance_report(db, org_id=1)
"""

import io
import csv
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List
from decimal import Decimal

logger = logging.getLogger(__name__)


# =============================================================================
# PDF Generation
# =============================================================================

def generate_pdf(
    report_data: Dict[str, Any],
    report_type: str,
    title: Optional[str] = None,
    branding: Optional[Dict] = None,
) -> bytes:
    """
    Generate a PDF report from structured data.

    Args:
        report_data: The report data dict
        report_type: Type of report (pipeline, scorecard, sla_compliance, financial)
        title: Optional custom title
        branding: Optional tenant branding config (company_name, primary_color, logo_url)
                  from white_label_service.get_report_branding()

    Returns:
        PDF file as bytes
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak

    # Use tenant branding colors or defaults
    primary_color = (branding or {}).get("primary_color", "#1a365d")
    company_name = (branding or {}).get("company_name", "Perennia AI")

    buffer = io.BytesIO()
    page_size = landscape(letter) if report_type in ("pipeline", "sla_compliance") else letter
    doc = SimpleDocTemplate(buffer, pagesize=page_size, topMargin=0.75 * inch, bottomMargin=0.75 * inch)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Heading1"], fontSize=18, spaceAfter=12,
        textColor=colors.HexColor(primary_color),
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Heading2"], fontSize=12, spaceAfter=8,
        textColor=colors.HexColor("#4a5568"),
    )
    body_style = styles["Normal"]

    elements = []

    # Header with tenant branding
    report_title = title or _get_default_title(report_type)
    elements.append(Paragraph(report_title, title_style))
    elements.append(Paragraph(
        f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        subtitle_style,
    ))
    elements.append(Spacer(1, 12))

    # Build report-specific content
    if report_type == "pipeline":
        elements.extend(_build_pipeline_pdf(report_data, styles, subtitle_style))
    elif report_type == "scorecard":
        elements.extend(_build_scorecard_pdf(report_data, styles, subtitle_style))
    elif report_type == "sla_compliance":
        elements.extend(_build_sla_compliance_pdf(report_data, styles, subtitle_style))
    elif report_type == "financial":
        elements.extend(_build_financial_pdf(report_data, styles, subtitle_style))
    else:
        # Generic table export
        elements.extend(_build_generic_pdf(report_data, styles, subtitle_style))

    # Footer with timestamp
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        f"{company_name} — Confidential | {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ParagraphStyle("Footer", parent=body_style, fontSize=8, textColor=colors.gray),
    ))

    doc.build(elements)
    return buffer.getvalue()


def _get_default_title(report_type: str) -> str:
    titles = {
        "pipeline": "Pipeline Report",
        "scorecard": "Loan Officer Scorecard",
        "sla_compliance": "SLA Compliance Report",
        "financial": "Financial Report",
    }
    return titles.get(report_type, "Report")


def _make_table(headers: List[str], rows: List[List], col_widths: Optional[List] = None):
    """Create a styled table."""
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, TableStyle

    data = [headers] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    return table


def _build_pipeline_pdf(data, styles, subtitle_style):
    from reportlab.platypus import Paragraph, Spacer

    elements = []

    # Summary metrics
    if "metrics" in data:
        m = data["metrics"]
        elements.append(Paragraph("Pipeline Summary", subtitle_style))
        summary_rows = [
            ["Total Loans", str(m.get("total_count", 0))],
            ["Total Volume", m.get("total_volume_formatted", "$0")],
            ["Closing Soon", str(m.get("closing_soon", 0))],
            ["Avg Days in Status", str(m.get("avg_days_in_status", 0))],
        ]
        elements.append(_make_table(["Metric", "Value"], summary_rows))
        elements.append(Spacer(1, 12))

    # Loans table
    if "loans" in data:
        elements.append(Paragraph("Loan Details", subtitle_style))
        headers = ["Loan #", "Borrower", "Amount", "Status", "Days", "Close Date"]
        rows = []
        for loan in data["loans"][:100]:
            rows.append([
                str(loan.get("loan_number", "")),
                str(loan.get("borrower", "")),
                str(loan.get("amount_formatted", "")),
                str(loan.get("status", "")),
                str(loan.get("days_in_status", "")),
                str(loan.get("expected_close", "")),
            ])
        elements.append(_make_table(headers, rows))

    return elements


def _build_scorecard_pdf(data, styles, subtitle_style):
    from reportlab.platypus import Paragraph, Spacer

    elements = []
    elements.append(Paragraph("Scorecard Metrics", subtitle_style))

    if "conversion" in data:
        c = data["conversion"]
        rows = [
            ["Lead to Application", f"{c.get('lead_to_app', 0)}%"],
            ["Application to Submission", f"{c.get('app_to_submit', 0)}%"],
            ["Submission to Approval", f"{c.get('submit_to_approve', 0)}%"],
            ["Overall Pull-Through", f"{c.get('overall_pull_through', 0)}%"],
        ]
        elements.append(_make_table(["Stage", "Rate"], rows))
        elements.append(Spacer(1, 12))

    if "funded" in data:
        f = data["funded"]
        rows = [
            ["Funded Units", str(f.get("count", 0))],
            ["Funded Volume", f.get("volume_formatted", "$0")],
            ["Avg Loan Size", f.get("avg_size_formatted", "$0")],
        ]
        elements.append(Paragraph("Funding Summary", subtitle_style))
        elements.append(_make_table(["Metric", "Value"], rows))

    return elements


def _build_sla_compliance_pdf(data, styles, subtitle_style):
    from reportlab.platypus import Paragraph, Spacer

    elements = []

    # Overall compliance
    if "overall" in data:
        o = data["overall"]
        elements.append(Paragraph("Overall SLA Compliance", subtitle_style))
        rows = [
            ["Compliance Rate", f"{o.get('compliance_rate', 0):.1f}%"],
            ["Total Milestones", str(o.get("total_milestones", 0))],
            ["On Time", str(o.get("on_time", 0))],
            ["Late", str(o.get("late", 0))],
            ["Overdue", str(o.get("overdue", 0))],
        ]
        elements.append(_make_table(["Metric", "Value"], rows))
        elements.append(Spacer(1, 12))

    # By milestone type
    if "by_milestone" in data:
        elements.append(Paragraph("Compliance by Milestone", subtitle_style))
        headers = ["Milestone", "Total", "On Time", "Late", "Compliance %", "Avg Hours"]
        rows = []
        for m in data["by_milestone"]:
            rows.append([
                str(m.get("milestone_type", "")),
                str(m.get("total", 0)),
                str(m.get("on_time", 0)),
                str(m.get("late", 0)),
                f"{m.get('compliance_rate', 0):.1f}%",
                f"{m.get('avg_completion_hours', 0):.1f}",
            ])
        elements.append(_make_table(headers, rows))
        elements.append(Spacer(1, 12))

    # Bottlenecks
    if "bottlenecks" in data and data["bottlenecks"]:
        elements.append(Paragraph("Bottleneck Analysis", subtitle_style))
        headers = ["Stage", "Avg Delay (hours)", "Affected Loans"]
        rows = [[str(b.get("stage", "")), f"{b.get('avg_delay_hours', 0):.1f}", str(b.get("count", 0))]
                for b in data["bottlenecks"]]
        elements.append(_make_table(headers, rows))

    return elements


def _build_financial_pdf(data, styles, subtitle_style):
    from reportlab.platypus import Paragraph, Spacer

    elements = []
    elements.append(Paragraph("Financial Summary", subtitle_style))

    if "sections" in data:
        for section in data["sections"]:
            elements.append(Paragraph(section.get("name", ""), subtitle_style))
            if "items" in section:
                headers = ["Account", "Amount"]
                rows = [[str(item.get("name", "")), str(item.get("amount_formatted", ""))]
                        for item in section["items"]]
                elements.append(_make_table(headers, rows))
                elements.append(Spacer(1, 8))

    return elements


def _build_generic_pdf(data, styles, subtitle_style):
    from reportlab.platypus import Paragraph, Spacer

    elements = []

    # Try to render any list of dicts as a table
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            elements.append(Paragraph(key.replace("_", " ").title(), subtitle_style))
            headers = list(value[0].keys())
            rows = [[str(item.get(h, "")) for h in headers] for item in value[:100]]
            elements.append(_make_table(headers, rows))
            elements.append(Spacer(1, 12))

    return elements


# =============================================================================
# Excel Generation
# =============================================================================

def generate_excel(report_data: Dict[str, Any], report_type: str, title: Optional[str] = None) -> bytes:
    """
    Generate an Excel workbook from structured data.

    Args:
        report_data: The report data dict
        report_type: Type of report
        title: Optional custom title

    Returns:
        XLSX file as bytes
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()

    # Styles
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill(start_color="2B6CB0", end_color="2B6CB0", fill_type="solid")
    title_font = Font(name="Calibri", bold=True, size=14, color="1A365D")
    subtitle_font = Font(name="Calibri", bold=True, size=11, color="4A5568")
    currency_format = '#,##0.00'
    pct_format = '0.0%'
    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    def style_header_row(ws, row_num, col_count):
        for col in range(1, col_count + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

    def auto_width(ws, min_width=10, max_width=40):
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 2, max_width))

    report_title = title or _get_default_title(report_type)

    if report_type == "pipeline":
        _build_pipeline_excel(wb, report_data, report_title, header_font, header_fill,
                              title_font, subtitle_font, thin_border, style_header_row, auto_width)
    elif report_type == "scorecard":
        _build_scorecard_excel(wb, report_data, report_title, header_font, header_fill,
                               title_font, subtitle_font, thin_border, style_header_row, auto_width)
    elif report_type == "sla_compliance":
        _build_sla_compliance_excel(wb, report_data, report_title, header_font, header_fill,
                                     title_font, subtitle_font, thin_border, style_header_row, auto_width)
    else:
        _build_generic_excel(wb, report_data, report_title, header_font, header_fill,
                             title_font, thin_border, style_header_row, auto_width)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _build_pipeline_excel(wb, data, title, header_font, header_fill,
                          title_font, subtitle_font, border, style_header, auto_width):
    ws = wb.active
    ws.title = "Pipeline"

    # Title
    ws.cell(row=1, column=1, value=title).font = title_font
    ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}").font = subtitle_font

    # Summary
    if "metrics" in data:
        m = data["metrics"]
        ws.cell(row=4, column=1, value="Pipeline Summary").font = subtitle_font
        for i, (label, val) in enumerate([
            ("Total Loans", m.get("total_count", 0)),
            ("Total Volume", m.get("total_volume_formatted", "$0")),
            ("Closing Soon", m.get("closing_soon", 0)),
        ]):
            ws.cell(row=5 + i, column=1, value=label)
            ws.cell(row=5 + i, column=2, value=val)

    # Loan details
    if "loans" in data:
        row = 10
        ws.cell(row=row, column=1, value="Loan Details").font = subtitle_font
        row += 1
        headers = ["Loan #", "Borrower", "Amount", "Type", "Status", "Days in Status", "Close Date", "LO"]
        for col, h in enumerate(headers, 1):
            ws.cell(row=row, column=col, value=h)
        style_header(ws, row, len(headers))

        for loan in data["loans"][:500]:
            row += 1
            ws.cell(row=row, column=1, value=loan.get("loan_number", ""))
            ws.cell(row=row, column=2, value=loan.get("borrower", ""))
            ws.cell(row=row, column=3, value=loan.get("amount", 0))
            ws.cell(row=row, column=4, value=loan.get("loan_type", ""))
            ws.cell(row=row, column=5, value=loan.get("status", ""))
            ws.cell(row=row, column=6, value=loan.get("days_in_status", 0))
            ws.cell(row=row, column=7, value=loan.get("expected_close", ""))
            ws.cell(row=row, column=8, value=loan.get("lo_name", ""))

    auto_width(ws)


def _build_scorecard_excel(wb, data, title, header_font, header_fill,
                            title_font, subtitle_font, border, style_header, auto_width):
    ws = wb.active
    ws.title = "Scorecard"
    ws.cell(row=1, column=1, value=title).font = title_font
    ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}").font = subtitle_font

    row = 4
    if "conversion" in data:
        ws.cell(row=row, column=1, value="Conversion Rates").font = subtitle_font
        row += 1
        for label, key in [
            ("Lead to App", "lead_to_app"), ("App to Submit", "app_to_submit"),
            ("Submit to Approve", "submit_to_approve"), ("Pull-Through", "overall_pull_through"),
        ]:
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=f"{data['conversion'].get(key, 0)}%")
            row += 1

    if "funded" in data:
        row += 1
        ws.cell(row=row, column=1, value="Funding Summary").font = subtitle_font
        row += 1
        for label, key in [("Units", "count"), ("Volume", "volume_formatted"), ("Avg Size", "avg_size_formatted")]:
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=data["funded"].get(key, ""))
            row += 1

    auto_width(ws)


def _build_sla_compliance_excel(wb, data, title, header_font, header_fill,
                                 title_font, subtitle_font, border, style_header, auto_width):
    ws = wb.active
    ws.title = "SLA Compliance"
    ws.cell(row=1, column=1, value=title).font = title_font
    ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}").font = subtitle_font

    # Overall
    row = 4
    if "overall" in data:
        o = data["overall"]
        ws.cell(row=row, column=1, value="Overall Compliance").font = subtitle_font
        row += 1
        for label, val in [
            ("Compliance Rate", f"{o.get('compliance_rate', 0):.1f}%"),
            ("Total Milestones", o.get("total_milestones", 0)),
            ("On Time", o.get("on_time", 0)),
            ("Late", o.get("late", 0)),
            ("Overdue", o.get("overdue", 0)),
        ]:
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=val)
            row += 1

    # By milestone
    if "by_milestone" in data:
        row += 1
        ws.cell(row=row, column=1, value="By Milestone Type").font = subtitle_font
        row += 1
        headers = ["Milestone", "Total", "On Time", "Late", "Compliance %", "Avg Hours"]
        for col, h in enumerate(headers, 1):
            ws.cell(row=row, column=col, value=h)
        style_header(ws, row, len(headers))

        for m in data["by_milestone"]:
            row += 1
            ws.cell(row=row, column=1, value=m.get("milestone_type", ""))
            ws.cell(row=row, column=2, value=m.get("total", 0))
            ws.cell(row=row, column=3, value=m.get("on_time", 0))
            ws.cell(row=row, column=4, value=m.get("late", 0))
            ws.cell(row=row, column=5, value=f"{m.get('compliance_rate', 0):.1f}%")
            ws.cell(row=row, column=6, value=round(m.get("avg_completion_hours", 0), 1))

    # Bottlenecks sheet
    if "bottlenecks" in data and data["bottlenecks"]:
        ws2 = wb.create_sheet("Bottlenecks")
        ws2.cell(row=1, column=1, value="Bottleneck Analysis").font = title_font
        headers = ["Stage", "Avg Delay (hours)", "Affected Loans"]
        for col, h in enumerate(headers, 1):
            ws2.cell(row=3, column=col, value=h)
        style_header(ws2, 3, len(headers))
        for i, b in enumerate(data["bottlenecks"]):
            ws2.cell(row=4 + i, column=1, value=b.get("stage", ""))
            ws2.cell(row=4 + i, column=2, value=round(b.get("avg_delay_hours", 0), 1))
            ws2.cell(row=4 + i, column=3, value=b.get("count", 0))
        auto_width(ws2)

    auto_width(ws)


def _build_generic_excel(wb, data, title, header_font, header_fill,
                         title_font, border, style_header, auto_width):
    ws = wb.active
    ws.title = "Report"
    ws.cell(row=1, column=1, value=title).font = title_font

    row = 3
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            ws.cell(row=row, column=1, value=key.replace("_", " ").title()).font = title_font
            row += 1
            headers = list(value[0].keys())
            for col, h in enumerate(headers, 1):
                ws.cell(row=row, column=col, value=h)
            style_header(ws, row, len(headers))
            for item in value[:1000]:
                row += 1
                for col, h in enumerate(headers, 1):
                    ws.cell(row=row, column=col, value=str(item.get(h, "")))
            row += 2

    auto_width(ws)


# =============================================================================
# SLA Compliance Report Generation (Check 9.3)
# =============================================================================

def generate_sla_compliance_report(
    db,
    org_id: int,
    period_days: int = 30,
    scope_type: str = "organization",
    scope_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate comprehensive SLA compliance report from database.

    Args:
        db: SQLAlchemy session
        org_id: Organization ID
        period_days: Lookback period in days
        scope_type: "organization", "team", or "user"
        scope_id: Optional team_id or user_id for scoping

    Returns:
        Report data dict ready for PDF/Excel/JSON export
    """
    from sqlalchemy import text

    params = {"org_id": org_id, "period_days": period_days}
    scope_filter = "lmh.organization_id = :org_id"
    if scope_type == "user" and scope_id:
        scope_filter += " AND lmh.assigned_to_id = :scope_id"
        params["scope_id"] = scope_id
    elif scope_type == "team" and scope_id:
        scope_filter += " AND lmh.team_id = :scope_id"
        params["scope_id"] = scope_id

    try:
        # Overall compliance
        overall = db.execute(text(f"""
            SELECT
                COUNT(*) AS total_milestones,
                COUNT(CASE WHEN status = 'COMPLETED' AND variance_hours <= 0 THEN 1 END) AS on_time,
                COUNT(CASE WHEN status = 'COMPLETED' AND variance_hours > 0 THEN 1 END) AS late,
                COUNT(CASE WHEN status = 'OVERDUE' THEN 1 END) AS overdue,
                COUNT(CASE WHEN status IN ('IN_PROGRESS', 'ON_TRACK') THEN 1 END) AS in_progress,
                AVG(CASE WHEN status = 'COMPLETED' THEN actual_hours END) AS avg_completion_hours,
                AVG(CASE WHEN status = 'COMPLETED' THEN variance_pct END) AS avg_variance_pct
            FROM loan_milestone_history lmh
            WHERE {scope_filter}
                AND lmh.created_at >= CURRENT_DATE - :period_days
        """), params).fetchone()

        total = overall[0] or 0
        on_time = overall[1] or 0
        late = overall[2] or 0
        overdue = overall[3] or 0
        compliance_rate = (on_time / total * 100) if total > 0 else 0

        # By milestone type
        by_milestone_rows = db.execute(text(f"""
            SELECT
                milestone_type,
                COUNT(*) AS total,
                COUNT(CASE WHEN status = 'COMPLETED' AND variance_hours <= 0 THEN 1 END) AS on_time,
                COUNT(CASE WHEN status = 'COMPLETED' AND variance_hours > 0 THEN 1 END) AS late,
                AVG(CASE WHEN status = 'COMPLETED' THEN actual_hours END) AS avg_completion_hours
            FROM loan_milestone_history lmh
            WHERE {scope_filter}
                AND lmh.created_at >= CURRENT_DATE - :period_days
            GROUP BY milestone_type
            ORDER BY COUNT(*) DESC
        """), params).fetchall()

        by_milestone = []
        for row in by_milestone_rows:
            mt_total = row[1] or 0
            mt_on_time = row[2] or 0
            by_milestone.append({
                "milestone_type": str(row[0]),
                "total": mt_total,
                "on_time": mt_on_time,
                "late": row[3] or 0,
                "compliance_rate": (mt_on_time / mt_total * 100) if mt_total > 0 else 0,
                "avg_completion_hours": float(row[4] or 0),
            })

        # Bottlenecks (stages with highest average delay)
        bottleneck_rows = db.execute(text(f"""
            SELECT
                milestone_type AS stage,
                AVG(variance_hours) AS avg_delay_hours,
                COUNT(*) AS count
            FROM loan_milestone_history lmh
            WHERE {scope_filter}
                AND lmh.created_at >= CURRENT_DATE - :period_days
                AND variance_hours > 0
                AND status = 'COMPLETED'
            GROUP BY milestone_type
            HAVING AVG(variance_hours) > 2
            ORDER BY AVG(variance_hours) DESC
            LIMIT 10
        """), params).fetchall()

        bottlenecks = [
            {"stage": str(row[0]), "avg_delay_hours": float(row[1] or 0), "count": row[2] or 0}
            for row in bottleneck_rows
        ]

        # Alerts summary
        alerts_summary = db.execute(text("""
            SELECT
                alert_type,
                COUNT(*) AS count,
                COUNT(CASE WHEN status = 'ACTIVE' THEN 1 END) AS active
            FROM sla_alerts
            WHERE organization_id = :org_id
                AND triggered_at >= CURRENT_DATE - :period_days
            GROUP BY alert_type
        """), params).fetchall()

        alerts = [
            {"type": row[0], "total": row[1], "active": row[2]}
            for row in alerts_summary
        ]

        return {
            "report_type": "sla_compliance",
            "organization_id": org_id,
            "period_days": period_days,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "scope": {"type": scope_type, "id": scope_id},
            "overall": {
                "compliance_rate": round(compliance_rate, 1),
                "total_milestones": total,
                "on_time": on_time,
                "late": late,
                "overdue": overdue,
                "in_progress": overall[4] or 0,
                "avg_completion_hours": round(float(overall[5] or 0), 1),
                "avg_variance_pct": round(float(overall[6] or 0), 1),
            },
            "by_milestone": by_milestone,
            "bottlenecks": bottlenecks,
            "alerts": alerts,
        }

    except Exception as e:
        logger.error(f"SLA compliance report generation failed: {e}")
        return {
            "report_type": "sla_compliance",
            "organization_id": org_id,
            "period_days": period_days,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "error": str(e),
            "overall": {
                "compliance_rate": 0, "total_milestones": 0,
                "on_time": 0, "late": 0, "overdue": 0, "in_progress": 0,
                "avg_completion_hours": 0, "avg_variance_pct": 0,
            },
            "by_milestone": [],
            "bottlenecks": [],
            "alerts": [],
        }


# =============================================================================
# CSV Export (Extended for consistency)
# =============================================================================

def generate_csv(report_data: Dict[str, Any], report_type: str) -> bytes:
    """Generate CSV from report data."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # Find the primary list of dicts in the data
    rows_key = None
    for key, value in report_data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            rows_key = key
            break

    if rows_key:
        items = report_data[rows_key]
        headers = list(items[0].keys())
        writer.writerow(headers)
        for item in items:
            writer.writerow([str(item.get(h, "")) for h in headers])
    else:
        # Flat key-value export
        writer.writerow(["Key", "Value"])
        for key, value in report_data.items():
            if not isinstance(value, (list, dict)):
                writer.writerow([key, str(value)])

    return buffer.getvalue().encode("utf-8")


# =============================================================================
# Module-Level Convenience
# =============================================================================

class ReportExporter:
    """Convenience class aggregating all export functions."""
    generate_pdf = staticmethod(generate_pdf)
    generate_excel = staticmethod(generate_excel)
    generate_csv = staticmethod(generate_csv)
    generate_sla_compliance_report = staticmethod(generate_sla_compliance_report)


report_exporter = ReportExporter()
