"""KPI dashboard computation."""

from __future__ import annotations

import csv
import io
import json
import logging
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from .._shared import (
    _REPORT_CATALOG,
    _ROLE_REPORT_ACCESS,
    _build_org_loan_join_filter,
    _group_by_expression,
    _pct_change,
    _safe_div,
    ComparisonResult,
    DateRange,
    ExportFormat,
    GroupBy,
    KPIDashboard,
    ReportConfig,
    ReportFilter,
    ReportInfo,
    ReportResult,
    ReportTemplate,
    ReportType,
    ScheduleFrequency,
    ScheduleResult,
    UserRole,
)

logger = logging.getLogger(__name__)


class KPIMixin:
    # =========================================================================
    # PUBLIC — KPI Dashboard
    # =========================================================================

    async def get_kpi_dashboard(
        self,
        period: Optional[DateRange] = None,
    ) -> KPIDashboard:
        """Return a high-level KPI dashboard for the organization.

        Computes document collection rate, first-pass approval rate,
        time-to-complete, AI accuracy, borrower engagement score, and
        cost per document.

        Args:
            period: Date range. Defaults to last 30 days.

        Returns:
            A :class:`KPIDashboard` with computed KPIs, trends, and alerts.
        """
        if period is None:
            period = DateRange.last_30_days()

        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **period.to_params(),
        }

        # ---- Document collection rate ---
        collection = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_requested,
                    COUNT(CASE WHEN sdr.status IN ('ACCEPTED', 'WAIVED') THEN 1 END)
                        AS fulfilled
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_requested = collection.total_requested or 0
        fulfilled = collection.fulfilled or 0
        collection_rate = round(_safe_div(fulfilled, total_requested) * 100, 1)

        # ---- First-pass approval rate ---
        first_pass = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_reviewed,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END)
                        AS first_accept
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  AND sd.decision IS NOT NULL
            """),
            params,
        ).fetchone()

        total_reviewed = first_pass.total_reviewed or 0
        first_accept = first_pass.first_accept or 0
        first_pass_rate = round(_safe_div(first_accept, total_reviewed) * 100, 1)

        # ---- Average time-to-complete (request created -> status ACCEPTED) ---
        ttc = self.db.execute(
            sa_text("""
                SELECT
                    AVG(EXTRACT(EPOCH FROM (sdr.completed_at - sdr.created_at)) / 3600)
                        AS avg_hours
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.completed_at IS NOT NULL
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        avg_ttc_hours = round(float(ttc.avg_hours or 0), 1)

        # ---- AI accuracy (classification confirmed by human) ---
        ai_accuracy = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_classified,
                    COUNT(CASE
                        WHEN sd.detected_doc_type IS NOT NULL
                         AND sd.doc_type IS NOT NULL
                         AND sd.detected_doc_type = CAST(sd.doc_type AS TEXT)
                        THEN 1
                    END) AS correct
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.detected_doc_type IS NOT NULL
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_classified = ai_accuracy.total_classified or 0
        correct_classified = ai_accuracy.correct or 0
        ai_accuracy_rate = round(
            _safe_div(correct_classified, total_classified) * 100, 1,
        )

        # ---- Borrower engagement (upload source diversity as proxy) ---
        engagement = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(DISTINCT sd.borrower_id) AS active_borrowers,
                    COUNT(*) AS total_uploads,
                    COUNT(CASE WHEN sd.upload_source = 'WEB' THEN 1 END)
                        AS web_uploads,
                    COUNT(CASE WHEN sd.upload_source = 'MOBILE' THEN 1 END)
                        AS mobile_uploads,
                    COUNT(CASE WHEN sd.upload_source = 'EMAIL' THEN 1 END)
                        AS email_uploads
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        active_borrowers = engagement.active_borrowers or 0
        total_uploads = engagement.total_uploads or 0

        # ---- Cost per document (AI operations) ---
        ai_ops = self.db.execute(
            sa_text("""
                SELECT COUNT(*) AS ai_operations
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.detected_doc_type IS NOT NULL
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        ai_ops_count = ai_ops.ai_operations or 0
        est_cost_per_doc = round(ai_ops_count * 0.08 / max(total_uploads, 1), 4)

        # ---- Trends (compare to previous period of same length) ---
        prev_range = DateRange(
            start=period.start - timedelta(days=period.span_days),
            end=period.start - timedelta(days=1),
        )
        prev_params: Dict[str, Any] = {
            "org_id": self.org_id,
            **prev_range.to_params(),
        }

        prev_collection = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_requested,
                    COUNT(CASE WHEN sdr.status IN ('ACCEPTED', 'WAIVED') THEN 1 END)
                        AS fulfilled
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
            """),
            prev_params,
        ).fetchone()

        prev_total = prev_collection.total_requested or 0
        prev_fulfilled = prev_collection.fulfilled or 0
        prev_rate = round(_safe_div(prev_fulfilled, prev_total) * 100, 1)

        # ---- Alerts ---
        alerts: List[Dict[str, Any]] = []
        if collection_rate < 60:
            alerts.append({
                "severity": "critical",
                "metric": "collection_rate",
                "message": f"Document collection rate is {collection_rate}% (target 80%+)",
            })
        if first_pass_rate < 50:
            alerts.append({
                "severity": "warning",
                "metric": "first_pass_rate",
                "message": f"First-pass approval rate is {first_pass_rate}% (target 70%+)",
            })
        if avg_ttc_hours > 72:
            alerts.append({
                "severity": "warning",
                "metric": "time_to_complete",
                "message": f"Average time-to-complete is {avg_ttc_hours}h (target <48h)",
            })

        return KPIDashboard(
            org_id=self.org_id,
            generated_at=datetime.now(timezone.utc),
            period=period,
            kpis={
                "document_collection_rate": collection_rate,
                "first_pass_approval_rate": first_pass_rate,
                "avg_time_to_complete_hours": avg_ttc_hours,
                "ai_accuracy_rate": ai_accuracy_rate,
                "active_borrowers": active_borrowers,
                "total_uploads": total_uploads,
                "cost_per_document": est_cost_per_doc,
                "total_requested": total_requested,
                "total_fulfilled": fulfilled,
                "total_ai_operations": ai_ops_count,
            },
            trends={
                "collection_rate_change": _pct_change(collection_rate, prev_rate),
                "volume_change": _pct_change(total_requested, prev_total),
                "previous_period": {
                    "start": prev_range.start.isoformat(),
                    "end": prev_range.end.isoformat(),
                    "collection_rate": prev_rate,
                    "total_requested": prev_total,
                },
            },
            alerts=alerts,
        )

