"""
PDF Report Generator

Generates weekly operations reports and pipeline summaries as PDF documents
using reportlab. Reports include files by stage, average days in stage,
SLA breaches, team performance, and revenue at risk.

Designed for distribution via email to Branch Manager and Admin users.

Usage:
    from services.pdf_report_generator import PDFReportGenerator

    gen = PDFReportGenerator()
    pdf_bytes = await gen.generate_ops_report(org_id=1, week_start=..., week_end=..., db=session)
    pdf_bytes = await gen.generate_pipeline_summary(org_id=1, db=session)
"""

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, case
from sqlalchemy.orm import Session

from database.models.communication import StageHistory
from database.models.core import Organization, User
from database.models.lead_loan import Loan

logger = logging.getLogger(__name__)

TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

ORDERED_STAGES = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
    "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
    "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
]

SLA_DAYS: dict[str, int] = {
    "APPLICATION": 5, "DISCLOSED": 7, "PROCESSING": 10, "SUBMITTED": 3,
    "UNDERWRITING": 7, "UW_RECEIVED": 3, "CONDITIONAL_APPROVAL": 5,
    "APPROVED": 3, "CTC": 3, "CLEAR_TO_CLOSE": 5, "CLOSING": 5,
    "DOCS": 3, "DOCS_OUT": 3,
}

# reportlab is available (verified at import time via requirements)
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    logger.warning("reportlab not installed; PDF generation will produce plain-text fallback")


class PDFReportGenerator:
    """Generates PDF reports for mortgage operations management."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_ops_report(
        self,
        org_id: int,
        week_start: datetime,
        week_end: datetime,
        db: Session,
    ) -> bytes:
        """Generate a weekly operations report PDF.

        Includes:
        - Files by stage
        - Average days in stage
        - SLA breaches
        - Team performance (per LO)
        - Revenue at risk (stalled files)

        Returns:
            Raw PDF bytes (or UTF-8 text bytes if reportlab unavailable).
        """
        self.logger.info("Generating ops report for org %s (%s to %s)", org_id, week_start, week_end)

        org = db.query(Organization).filter(Organization.id == org_id).first()
        org_name = org.name if org else f"Org #{org_id}"

        data = self._collect_ops_data(org_id, week_start, week_end, db)

        if HAS_REPORTLAB:
            return self._render_ops_pdf(org_name, week_start, week_end, data)
        return self._render_ops_text(org_name, week_start, week_end, data)

    async def generate_pipeline_summary(self, org_id: int, db: Session) -> bytes:
        """Generate a point-in-time pipeline summary PDF.

        Lighter than full ops report: current stage distribution,
        top stalled files, SLA breach count.

        Returns:
            Raw PDF bytes.
        """
        self.logger.info("Generating pipeline summary for org %s", org_id)

        org = db.query(Organization).filter(Organization.id == org_id).first()
        org_name = org.name if org else f"Org #{org_id}"
        now = datetime.now(timezone.utc)

        data = self._collect_pipeline_data(org_id, db)

        if HAS_REPORTLAB:
            return self._render_pipeline_pdf(org_name, now, data)
        return self._render_pipeline_text(org_name, now, data)

    def get_admin_recipients(self, org_id: int, db: Session) -> list[dict[str, Any]]:
        """Return Branch Manager + Admin users for email distribution."""
        users = (
            db.query(User)
            .filter(
                User.organization_id == org_id,
                User.is_active == True,  # noqa: E712
                User.role.in_(["Admin", "Branch Manager", "admin", "branch_manager"]),
            )
            .all()
        )
        return [
            {
                "user_id": u.id,
                "email": u.email,
                "name": f"{u.first_name or ''} {u.last_name or ''}".strip(),
                "role": u.role,
            }
            for u in users
        ]

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    def _collect_ops_data(
        self,
        org_id: int,
        week_start: datetime,
        week_end: datetime,
        db: Session,
    ) -> dict[str, Any]:
        """Gather all data needed for the weekly ops report."""
        stage_counts = self._stage_distribution(org_id, db)
        avg_days = self._avg_days_in_stage(org_id, db)
        sla_breaches = self._sla_breaches(org_id, db)
        team_perf = self._team_performance(org_id, week_start, week_end, db)
        revenue_at_risk = self._revenue_at_risk(org_id, db)
        funded_this_week = self._funded_in_period(org_id, week_start, week_end, db)

        return {
            "stage_counts": stage_counts,
            "avg_days_in_stage": avg_days,
            "sla_breaches": sla_breaches,
            "team_performance": team_perf,
            "revenue_at_risk": revenue_at_risk,
            "funded_this_week": funded_this_week,
        }

    def _collect_pipeline_data(self, org_id: int, db: Session) -> dict[str, Any]:
        stage_counts = self._stage_distribution(org_id, db)
        sla_breaches = self._sla_breaches(org_id, db)
        total_active = sum(v for v in stage_counts.values() if v)
        return {
            "stage_counts": stage_counts,
            "total_active": total_active,
            "sla_breaches": sla_breaches,
        }

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def _stage_distribution(self, org_id: int, db: Session) -> dict[str, int]:
        rows = (
            db.query(Loan.stage, func.count(Loan.id))
            .filter(
                Loan.organization_id == org_id,
                ~Loan.stage.in_(TERMINAL_STAGES),
            )
            .group_by(Loan.stage)
            .all()
        )
        return {stage: count for stage, count in rows}

    def _avg_days_in_stage(self, org_id: int, db: Session) -> dict[str, float]:
        """Average days loans spend in each active stage (from StageHistory)."""
        now = datetime.now(timezone.utc)
        results: dict[str, float] = {}

        for stage in ORDERED_STAGES:
            if stage in TERMINAL_STAGES:
                continue
            histories = (
                db.query(StageHistory)
                .filter(
                    StageHistory.organization_id == org_id,
                    StageHistory.new_stage == stage,
                )
                .order_by(StageHistory.changed_at.desc())
                .limit(200)
                .all()
            )
            if not histories:
                continue

            durations: list[float] = []
            for h in histories:
                changed = h.changed_at
                if changed is None:
                    continue
                if changed.tzinfo is None:
                    changed = changed.replace(tzinfo=timezone.utc)
                days = (now - changed).total_seconds() / 86400.0
                durations.append(days)

            if durations:
                results[stage] = round(sum(durations) / len(durations), 1)

        return results

    def _sla_breaches(self, org_id: int, db: Session) -> list[dict[str, Any]]:
        """Loans exceeding SLA for their current stage."""
        now = datetime.now(timezone.utc)
        breaches: list[dict[str, Any]] = []

        active_loans = (
            db.query(Loan)
            .filter(
                Loan.organization_id == org_id,
                ~Loan.stage.in_(TERMINAL_STAGES),
            )
            .all()
        )

        for loan in active_loans:
            sla_limit = SLA_DAYS.get(loan.stage)
            if sla_limit is None:
                continue

            # Use updated_at as proxy for when loan entered current stage
            ref_date = loan.updated_at or loan.created_at
            if ref_date is None:
                continue
            if ref_date.tzinfo is None:
                ref_date = ref_date.replace(tzinfo=timezone.utc)
            days_in_stage = (now - ref_date).total_seconds() / 86400.0

            if days_in_stage > sla_limit:
                breaches.append({
                    "loan_id": loan.id,
                    "stage": loan.stage,
                    "days_in_stage": round(days_in_stage, 1),
                    "sla_limit": sla_limit,
                    "owner_id": loan.owner_id,
                    "loan_amount": float(loan.loan_amount) if loan.loan_amount else 0,
                })

        breaches.sort(key=lambda b: b["days_in_stage"], reverse=True)
        return breaches

    def _team_performance(
        self,
        org_id: int,
        week_start: datetime,
        week_end: datetime,
        db: Session,
    ) -> list[dict[str, Any]]:
        """Per-LO performance: active files, funded count, stage transitions."""
        users = (
            db.query(User)
            .filter(
                User.organization_id == org_id,
                User.is_active == True,  # noqa: E712
            )
            .all()
        )

        results: list[dict[str, Any]] = []
        for u in users:
            active = (
                db.query(func.count(Loan.id))
                .filter(
                    Loan.owner_id == u.id,
                    Loan.organization_id == org_id,
                    ~Loan.stage.in_(TERMINAL_STAGES),
                )
                .scalar()
            ) or 0

            funded = (
                db.query(func.count(Loan.id))
                .filter(
                    Loan.owner_id == u.id,
                    Loan.organization_id == org_id,
                    Loan.stage == "FUNDED",
                    Loan.updated_at >= week_start,
                    Loan.updated_at <= week_end,
                )
                .scalar()
            ) or 0

            if active > 0 or funded > 0:
                results.append({
                    "user_id": u.id,
                    "name": f"{u.first_name or ''} {u.last_name or ''}".strip(),
                    "active_files": active,
                    "funded_this_week": funded,
                })

        results.sort(key=lambda r: r["active_files"], reverse=True)
        return results

    def _revenue_at_risk(self, org_id: int, db: Session) -> dict[str, Any]:
        """Sum of loan_amount for files breaching SLA."""
        breaches = self._sla_breaches(org_id, db)
        total_at_risk = sum(b["loan_amount"] for b in breaches)
        return {
            "total_at_risk": round(total_at_risk, 2),
            "breach_count": len(breaches),
        }

    def _funded_in_period(
        self, org_id: int, start: datetime, end: datetime, db: Session,
    ) -> dict[str, Any]:
        rows = (
            db.query(
                func.count(Loan.id).label("count"),
                func.coalesce(func.sum(Loan.loan_amount), 0).label("volume"),
            )
            .filter(
                Loan.organization_id == org_id,
                Loan.stage == "FUNDED",
                Loan.updated_at >= start,
                Loan.updated_at <= end,
            )
            .first()
        )
        return {
            "count": rows.count if rows else 0,
            "volume": float(rows.volume) if rows else 0.0,
        }

    # ------------------------------------------------------------------
    # PDF rendering (reportlab)
    # ------------------------------------------------------------------

    def _render_ops_pdf(
        self,
        org_name: str,
        week_start: datetime,
        week_end: datetime,
        data: dict,
    ) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18, spaceAfter=12)
        heading_style = ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=13, spaceAfter=6)
        normal = styles["Normal"]

        elements: list[Any] = []

        # Title
        ws = week_start.strftime("%Y-%m-%d")
        we = week_end.strftime("%Y-%m-%d")
        elements.append(Paragraph(f"{org_name} — Weekly Ops Report", title_style))
        elements.append(Paragraph(f"{ws} to {we}", normal))
        elements.append(Spacer(1, 0.25 * inch))

        # Funded summary
        funded = data.get("funded_this_week", {})
        elements.append(Paragraph("Funded This Week", heading_style))
        elements.append(Paragraph(
            f"Count: {funded.get('count', 0)} | Volume: ${funded.get('volume', 0):,.2f}",
            normal,
        ))
        elements.append(Spacer(1, 0.2 * inch))

        # Stage distribution
        elements.append(Paragraph("Pipeline — Files by Stage", heading_style))
        stage_data = [["Stage", "Count"]]
        for stage in ORDERED_STAGES:
            cnt = data["stage_counts"].get(stage, 0)
            if cnt:
                stage_data.append([stage, str(cnt)])
        if len(stage_data) > 1:
            t = Table(stage_data, colWidths=[3 * inch, 1.5 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ]))
            elements.append(t)
        elements.append(Spacer(1, 0.2 * inch))

        # Avg days in stage
        elements.append(Paragraph("Average Days in Stage", heading_style))
        avg_data = [["Stage", "Avg Days", "SLA"]]
        for stage, avg in data.get("avg_days_in_stage", {}).items():
            sla = SLA_DAYS.get(stage, "—")
            avg_data.append([stage, str(avg), str(sla)])
        if len(avg_data) > 1:
            t = Table(avg_data, colWidths=[3 * inch, 1.2 * inch, 1 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(t)
        elements.append(Spacer(1, 0.2 * inch))

        # SLA breaches
        breaches = data.get("sla_breaches", [])
        elements.append(Paragraph(f"SLA Breaches ({len(breaches)} files)", heading_style))
        if breaches:
            b_data = [["Loan ID", "Stage", "Days", "SLA", "Amount"]]
            for b in breaches[:20]:
                b_data.append([
                    str(b["loan_id"]),
                    b["stage"],
                    str(b["days_in_stage"]),
                    str(b["sla_limit"]),
                    f"${b['loan_amount']:,.0f}",
                ])
            t = Table(b_data, colWidths=[1 * inch, 2 * inch, 0.8 * inch, 0.7 * inch, 1.5 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c0392b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(t)
        elements.append(Spacer(1, 0.2 * inch))

        # Revenue at risk
        rar = data.get("revenue_at_risk", {})
        elements.append(Paragraph("Revenue at Risk", heading_style))
        elements.append(Paragraph(
            f"Total at risk: ${rar.get('total_at_risk', 0):,.2f} across {rar.get('breach_count', 0)} file(s)",
            normal,
        ))
        elements.append(Spacer(1, 0.2 * inch))

        # Team performance
        elements.append(Paragraph("Team Performance", heading_style))
        tp = data.get("team_performance", [])
        if tp:
            tp_data = [["Name", "Active Files", "Funded This Week"]]
            for member in tp:
                tp_data.append([
                    member["name"],
                    str(member["active_files"]),
                    str(member["funded_this_week"]),
                ])
            t = Table(tp_data, colWidths=[2.5 * inch, 1.5 * inch, 1.5 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ]))
            elements.append(t)

        # Footer
        elements.append(Spacer(1, 0.3 * inch))
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        elements.append(Paragraph(
            f"Generated by Perennia AI on {generated_at}",
            ParagraphStyle("Footer", parent=normal, fontSize=8, textColor=colors.grey),
        ))

        doc.build(elements)
        return buf.getvalue()

    def _render_pipeline_pdf(self, org_name: str, now: datetime, data: dict) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18, spaceAfter=12)
        heading_style = ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=13, spaceAfter=6)
        normal = styles["Normal"]

        elements: list[Any] = []

        elements.append(Paragraph(f"{org_name} — Pipeline Summary", title_style))
        elements.append(Paragraph(now.strftime("%Y-%m-%d %H:%M UTC"), normal))
        elements.append(Spacer(1, 0.25 * inch))

        elements.append(Paragraph(
            f"Total Active Files: {data.get('total_active', 0)}", heading_style,
        ))
        elements.append(Spacer(1, 0.15 * inch))

        # Stage table
        elements.append(Paragraph("Files by Stage", heading_style))
        stage_data = [["Stage", "Count"]]
        for stage in ORDERED_STAGES:
            cnt = data["stage_counts"].get(stage, 0)
            if cnt:
                stage_data.append([stage, str(cnt)])
        if len(stage_data) > 1:
            t = Table(stage_data, colWidths=[3 * inch, 1.5 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(t)
        elements.append(Spacer(1, 0.2 * inch))

        # SLA breaches
        breaches = data.get("sla_breaches", [])
        elements.append(Paragraph(f"SLA Breaches: {len(breaches)}", heading_style))
        if breaches:
            b_data = [["Loan ID", "Stage", "Days Over SLA"]]
            for b in breaches[:15]:
                b_data.append([str(b["loan_id"]), b["stage"], str(b["days_in_stage"])])
            t = Table(b_data, colWidths=[1.5 * inch, 2.5 * inch, 1.5 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c0392b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(t)

        # Footer
        elements.append(Spacer(1, 0.3 * inch))
        elements.append(Paragraph(
            f"Generated by Perennia AI on {now.strftime('%Y-%m-%d %H:%M UTC')}",
            ParagraphStyle("Footer", parent=normal, fontSize=8, textColor=colors.grey),
        ))

        doc.build(elements)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Plaintext fallback (no reportlab)
    # ------------------------------------------------------------------

    def _render_ops_text(
        self, org_name: str, week_start: datetime, week_end: datetime, data: dict,
    ) -> bytes:
        lines: list[str] = []
        lines.append(f"{'=' * 60}")
        lines.append(f"{org_name} — Weekly Ops Report")
        lines.append(f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
        lines.append(f"{'=' * 60}\n")

        funded = data.get("funded_this_week", {})
        lines.append(f"Funded This Week: {funded.get('count', 0)} | Volume: ${funded.get('volume', 0):,.2f}\n")

        lines.append("--- Pipeline: Files by Stage ---")
        for stage in ORDERED_STAGES:
            cnt = data["stage_counts"].get(stage, 0)
            if cnt:
                lines.append(f"  {stage:<25} {cnt}")

        lines.append("\n--- Average Days in Stage ---")
        for stage, avg in data.get("avg_days_in_stage", {}).items():
            sla = SLA_DAYS.get(stage, "—")
            lines.append(f"  {stage:<25} {avg} days (SLA: {sla})")

        breaches = data.get("sla_breaches", [])
        lines.append(f"\n--- SLA Breaches ({len(breaches)} files) ---")
        for b in breaches[:20]:
            lines.append(f"  Loan {b['loan_id']:>6} | {b['stage']:<25} | {b['days_in_stage']} days (SLA {b['sla_limit']})")

        rar = data.get("revenue_at_risk", {})
        lines.append(f"\n--- Revenue at Risk: ${rar.get('total_at_risk', 0):,.2f} ({rar.get('breach_count', 0)} files) ---")

        lines.append("\n--- Team Performance ---")
        for m in data.get("team_performance", []):
            lines.append(f"  {m['name']:<30} Active: {m['active_files']}  Funded: {m['funded_this_week']}")

        lines.append(f"\nGenerated by Perennia AI on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        return "\n".join(lines).encode("utf-8")

    def _render_pipeline_text(self, org_name: str, now: datetime, data: dict) -> bytes:
        lines: list[str] = []
        lines.append(f"{'=' * 60}")
        lines.append(f"{org_name} — Pipeline Summary")
        lines.append(now.strftime("%Y-%m-%d %H:%M UTC"))
        lines.append(f"{'=' * 60}\n")

        lines.append(f"Total Active Files: {data.get('total_active', 0)}\n")

        lines.append("--- Files by Stage ---")
        for stage in ORDERED_STAGES:
            cnt = data["stage_counts"].get(stage, 0)
            if cnt:
                lines.append(f"  {stage:<25} {cnt}")

        breaches = data.get("sla_breaches", [])
        lines.append(f"\n--- SLA Breaches: {len(breaches)} ---")
        for b in breaches[:15]:
            lines.append(f"  Loan {b['loan_id']:>6} | {b['stage']:<25} | {b['days_in_stage']} days")

        lines.append(f"\nGenerated by Perennia AI on {now.strftime('%Y-%m-%d %H:%M UTC')}")
        return "\n".join(lines).encode("utf-8")
