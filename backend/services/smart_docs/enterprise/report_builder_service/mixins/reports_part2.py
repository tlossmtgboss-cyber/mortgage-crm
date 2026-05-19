"""Report generators: borrower engagement, condition tracking, compliance audit, team productivity, executive summary."""

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


class ReportsPart2Mixin:
    async def _report_borrower_engagement(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Portal usage, upload patterns, and response rates."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.uploaded_at")
        filter_frag, extra_params = _build_org_loan_join_filter(
            config.filters, table_alias="sd", loan_alias="l",
        )
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            **extra_params,
        }

        # Upload source distribution
        query = f"""
                SELECT
                    COUNT(*) AS total_uploads,
                    COUNT(DISTINCT sd.borrower_id) AS unique_borrowers,
                    COUNT(CASE WHEN sd.upload_source = 'WEB' THEN 1 END) AS web,
                    COUNT(CASE WHEN sd.upload_source = 'MOBILE' THEN 1 END) AS mobile,
                    COUNT(CASE WHEN sd.upload_source = 'EMAIL' THEN 1 END) AS email,
                    AVG(sd.file_size) AS avg_file_size
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
            """

        summary_row = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        sr = summary_row[0] if summary_row else None
        total_uploads = sr.total_uploads if sr else 0
        unique_borrowers = sr.unique_borrowers if sr else 0

        summary = {
            "total_uploads": total_uploads or 0,
            "unique_borrowers": unique_borrowers or 0,
            "uploads_per_borrower": round(
                _safe_div(total_uploads or 0, unique_borrowers or 0), 1,
            ),
            "web_uploads": sr.web if sr else 0,
            "mobile_uploads": sr.mobile if sr else 0,
            "email_uploads": sr.email if sr else 0,
            "avg_file_size_kb": round(float(sr.avg_file_size or 0) / 1024, 1)
            if sr
            else 0,
        }

        # Response time: time between request creation and first upload
        query = f"""
                SELECT
                    AVG(
                        EXTRACT(EPOCH FROM (
                            (SELECT MIN(sd2.uploaded_at)
                             FROM smart_documents sd2
                             WHERE sd2.request_id = sdr.id)
                            - sdr.created_at
                        )) / 3600
                    ) AS avg_response_hours,
                    COUNT(*) AS requests_with_uploads
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.status IN ('ACCEPTED', 'PENDING_REVIEW')
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  AND EXISTS (
                      SELECT 1 FROM smart_documents sd2
                      WHERE sd2.request_id = sdr.id
                  )
            """

        response = self.db.execute(
            sa_text(query),
            params,
        ).fetchone()

        data: Dict[str, Any] = {
            "upload_channels": {
                "web_pct": round(
                    _safe_div(summary["web_uploads"], total_uploads or 0) * 100, 1,
                ),
                "mobile_pct": round(
                    _safe_div(summary["mobile_uploads"], total_uploads or 0) * 100, 1,
                ),
                "email_pct": round(
                    _safe_div(summary["email_uploads"], total_uploads or 0) * 100, 1,
                ),
            },
            "avg_response_hours": round(
                float(response.avg_response_hours or 0), 1,
            ),
            "requests_with_uploads": response.requests_with_uploads or 0,
        }

        # Time series: uploads per period
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS uploads,
                    COUNT(DISTINCT sd.borrower_id) AS unique_borrowers
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "uploads": r.uploads,
                "unique_borrowers": r.unique_borrowers,
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_condition_tracking(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Outstanding conditions, clearance rates, and aging."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sdr.created_at")
        filter_frag, extra_params = _build_org_loan_join_filter(
            config.filters, table_alias="sdr", loan_alias="l",
        )
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            **extra_params,
        }

        query = f"""
                SELECT
                    COUNT(*) AS total_conditions,
                    COUNT(CASE WHEN sdr.status = 'OPEN' THEN 1 END) AS open,
                    COUNT(CASE WHEN sdr.status = 'PENDING_REVIEW' THEN 1 END)
                        AS pending_review,
                    COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END)
                        AS cleared,
                    COUNT(CASE WHEN sdr.status = 'REJECTED' THEN 1 END)
                        AS rejected,
                    COUNT(CASE WHEN sdr.status = 'WAIVED' THEN 1 END)
                        AS waived,
                    AVG(CASE
                        WHEN sdr.completed_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (sdr.completed_at - sdr.created_at)) / 3600
                    END) AS avg_clearance_hours
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
            """


        summary_row = self.db.execute(
            sa_text(query),
            params,
        ).fetchone()

        total = summary_row.total_conditions or 0
        cleared = summary_row.cleared or 0

        summary = {
            "total_conditions": total,
            "open": summary_row.open or 0,
            "pending_review": summary_row.pending_review or 0,
            "cleared": cleared,
            "rejected": summary_row.rejected or 0,
            "waived": summary_row.waived or 0,
            "clearance_rate": round(_safe_div(cleared, total) * 100, 1),
            "avg_clearance_hours": round(
                float(summary_row.avg_clearance_hours or 0), 1,
            ),
        }

        # By priority
        query = f"""
                SELECT
                    COALESCE(CAST(sdr.priority AS TEXT), 'NORMAL') AS priority,
                    COUNT(*) AS total,
                    COUNT(CASE WHEN sdr.status = 'OPEN' THEN 1 END) AS open,
                    COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END) AS cleared
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY COALESCE(CAST(sdr.priority AS TEXT), 'NORMAL')
                ORDER BY total DESC
            """

        by_priority_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_priority": [
                {
                    "priority": r.priority,
                    "total": r.total,
                    "open": r.open,
                    "cleared": r.cleared,
                    "clearance_rate": round(_safe_div(r.cleared, r.total) * 100, 1),
                }
                for r in by_priority_rows
            ],
        }

        # Aging — open conditions grouped by age bucket
        query = f"""
                SELECT
                    CASE
                        WHEN EXTRACT(EPOCH FROM (NOW() - sdr.created_at)) / 86400 <= 3
                            THEN '0-3 days'
                        WHEN EXTRACT(EPOCH FROM (NOW() - sdr.created_at)) / 86400 <= 7
                            THEN '4-7 days'
                        WHEN EXTRACT(EPOCH FROM (NOW() - sdr.created_at)) / 86400 <= 14
                            THEN '8-14 days'
                        ELSE '15+ days'
                    END AS age_bucket,
                    COUNT(*) AS count
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.status IN ('OPEN', 'PENDING_REVIEW')
                  AND sdr.is_active = TRUE
                  {filter_frag}
                GROUP BY age_bucket
                ORDER BY MIN(EXTRACT(EPOCH FROM (NOW() - sdr.created_at)))
            """

        aging_rows = self.db.execute(
            sa_text(query),
            {
                "org_id": self.org_id,
                **extra_params,
            },
        ).fetchall()

        data["aging"] = [
            {"bucket": r.age_bucket, "count": r.count}
            for r in aging_rows
        ]

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS created,
                    COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END) AS cleared
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "created": r.created,
                "cleared": r.cleared,
                "clearance_rate": round(_safe_div(r.cleared, r.created) * 100, 1),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_compliance_audit(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Disclosure timing, consent tracking, and retention compliance."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "l.application_date")
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        # Disclosure timing — LE within 3 days of application
        disclosure_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_loans,
                    COUNT(CASE
                        WHEN l.initial_disclosures_sent_date IS NOT NULL
                         AND l.application_date IS NOT NULL
                         AND (l.initial_disclosures_sent_date - l.application_date) <= 3
                        THEN 1
                    END) AS le_on_time,
                    COUNT(CASE
                        WHEN l.initial_disclosures_sent_date IS NOT NULL
                         AND l.application_date IS NOT NULL
                         AND (l.initial_disclosures_sent_date - l.application_date) > 3
                        THEN 1
                    END) AS le_late,
                    COUNT(CASE
                        WHEN l.application_date IS NOT NULL
                         AND l.initial_disclosures_sent_date IS NULL
                        THEN 1
                    END) AS le_missing,
                    COUNT(CASE
                        WHEN l.cd_sent_to_borrower_date IS NOT NULL
                         AND l.funded_date IS NOT NULL
                         AND (l.funded_date - l.cd_sent_to_borrower_date) >= 3
                        THEN 1
                    END) AS cd_on_time,
                    COUNT(CASE
                        WHEN l.cd_sent_to_borrower_date IS NOT NULL
                         AND l.funded_date IS NOT NULL
                         AND (l.funded_date - l.cd_sent_to_borrower_date) < 3
                        THEN 1
                    END) AS cd_violation
                FROM loans l
                WHERE l.organization_id = :org_id
                  AND l.application_date >= :start_date
                  AND l.application_date <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_loans = disclosure_row.total_loans or 0
        le_on_time = disclosure_row.le_on_time or 0
        le_late = disclosure_row.le_late or 0

        summary = {
            "total_loans": total_loans,
            "le_on_time": le_on_time,
            "le_late": le_late,
            "le_missing": disclosure_row.le_missing or 0,
            "le_compliance_rate": round(
                _safe_div(le_on_time, le_on_time + le_late) * 100, 1,
            ),
            "cd_on_time": disclosure_row.cd_on_time or 0,
            "cd_violation": disclosure_row.cd_violation or 0,
        }

        # Document retention — count of expired documents still active
        retention_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_docs,
                    COUNT(CASE WHEN sd.is_expired = TRUE THEN 1 END) AS expired_docs,
                    COUNT(CASE
                        WHEN sd.doc_expires_at IS NOT NULL
                         AND sd.doc_expires_at < NOW()
                         AND sd.is_expired = FALSE
                        THEN 1
                    END) AS not_marked_expired
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        data: Dict[str, Any] = {
            "retention": {
                "total_docs": retention_row.total_docs or 0,
                "expired_docs": retention_row.expired_docs or 0,
                "not_marked_expired": retention_row.not_marked_expired or 0,
            },
        }

        # Compliance alerts within period
        alerts_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_alerts,
                    COUNT(CASE WHEN ca.status = 'open' THEN 1 END) AS open_alerts,
                    COUNT(CASE WHEN ca.severity = 'critical' THEN 1 END)
                        AS critical_alerts
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id
                WHERE l.organization_id = :org_id
                  AND ca.created_at >= :start_date
                  AND ca.created_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        data["compliance_alerts"] = {
            "total": alerts_row.total_alerts or 0,
            "open": alerts_row.open_alerts or 0,
            "critical": alerts_row.critical_alerts or 0,
        }

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS loans,
                    COUNT(CASE
                        WHEN l.initial_disclosures_sent_date IS NOT NULL
                         AND l.application_date IS NOT NULL
                         AND (l.initial_disclosures_sent_date - l.application_date) <= 3
                        THEN 1
                    END) AS le_compliant
                FROM loans l
                WHERE l.organization_id = :org_id
                  AND l.application_date >= :start_date
                  AND l.application_date <= :end_date + INTERVAL '1 day'
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "loans": r.loans,
                "le_compliant": r.le_compliant,
                "compliance_rate": round(
                    _safe_div(r.le_compliant, r.loans) * 100, 1,
                ),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_team_productivity(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Per-user metrics, workload distribution, and efficiency."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.reviewed_at")
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        # Per-user doc review metrics
        user_rows = self.db.execute(
            sa_text("""
                SELECT
                    sd.reviewed_by AS user_id,
                    COUNT(*) AS docs_reviewed,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejected,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_review_hours,
                    COUNT(DISTINCT sd.loan_id) AS distinct_loans
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_by IS NOT NULL
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                GROUP BY sd.reviewed_by
                ORDER BY docs_reviewed DESC
            """),
            params,
        ).fetchall()

        total_reviewed = sum(r.docs_reviewed for r in user_rows) if user_rows else 0
        total_accepted = sum(r.accepted for r in user_rows) if user_rows else 0

        summary = {
            "total_team_members": len(user_rows),
            "total_documents_reviewed": total_reviewed,
            "total_accepted": total_accepted,
            "overall_acceptance_rate": round(
                _safe_div(total_accepted, total_reviewed) * 100, 1,
            ),
            "avg_docs_per_person": round(
                _safe_div(total_reviewed, len(user_rows) if user_rows else 0), 1,
            ),
        }

        span_days = max(dr.span_days, 1)
        data: Dict[str, Any] = {
            "by_team_member": [
                {
                    "user_id": r.user_id,
                    "docs_reviewed": r.docs_reviewed,
                    "accepted": r.accepted,
                    "rejected": r.rejected,
                    "acceptance_rate": round(
                        _safe_div(r.accepted, r.docs_reviewed) * 100, 1,
                    ),
                    "avg_review_hours": round(float(r.avg_review_hours or 0), 2),
                    "distinct_loans": r.distinct_loans,
                    "docs_per_day": round(
                        _safe_div(r.docs_reviewed, span_days), 2,
                    ),
                    "workload_pct": round(
                        _safe_div(r.docs_reviewed, total_reviewed) * 100, 1,
                    ),
                }
                for r in user_rows
            ],
        }

        # Workload distribution (Gini-like measure)
        if user_rows:
            counts = sorted([r.docs_reviewed for r in user_rows])
            n = len(counts)
            if n > 1:
                mean_val = statistics.mean(counts)
                if mean_val > 0:
                    abs_diffs = sum(
                        abs(counts[i] - counts[j])
                        for i in range(n) for j in range(i + 1, n)
                    )
                    gini = abs_diffs / (n * n * mean_val)
                else:
                    gini = 0.0
            else:
                gini = 0.0
            data["workload_gini"] = round(gini, 3)
        else:
            data["workload_gini"] = 0.0

        # Time series: total reviewed per period
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS reviewed,
                    COUNT(DISTINCT sd.reviewed_by) AS active_reviewers
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_by IS NOT NULL
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "reviewed": r.reviewed,
                "active_reviewers": r.active_reviewers,
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_executive_summary(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """High-level KPIs for leadership.

        Combines document volume, SLA, processing time, and fraud metrics
        into a single summary with trend analysis.
        """
        # Use the KPI dashboard to populate the executive summary
        kpi = await self.get_kpi_dashboard(config.date_range)

        # Get volume time series for the sparkline
        vol_data, vol_summary, vol_series = await self._report_document_volume(config)

        # Get SLA data for the summary
        sla_data, sla_summary, sla_series = await self._report_sla_compliance(config)

        summary = {
            "document_collection_rate": kpi.kpis["document_collection_rate"],
            "first_pass_approval_rate": kpi.kpis["first_pass_approval_rate"],
            "avg_time_to_complete_hours": kpi.kpis["avg_time_to_complete_hours"],
            "ai_accuracy_rate": kpi.kpis["ai_accuracy_rate"],
            "total_documents": vol_summary.get("total_documents", 0),
            "sla_met_rate": sla_summary.get("met_rate", 0),
            "sla_breached": sla_summary.get("sla_breached", 0),
            "active_borrowers": kpi.kpis["active_borrowers"],
        }

        data: Dict[str, Any] = {
            "kpis": kpi.kpis,
            "trends": kpi.trends,
            "alerts": kpi.alerts,
            "volume_by_type": vol_data.get("by_doc_type", [])[:5],
            "sla_by_type": sla_data.get("by_doc_type", [])[:5],
        }

        # Use volume series as the executive time-series
        series = vol_series

        return data, summary, series

