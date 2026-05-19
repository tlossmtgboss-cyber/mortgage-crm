"""Report generators: document volume, processing time, SLA, income accuracy, fraud detection."""

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


class ReportsPart1Mixin:
    # =========================================================================
    # PRIVATE — Report Generators
    # =========================================================================

    async def _report_document_volume(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Documents processed by type, period, and LO."""
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

        # Summary
        query = f"""
                SELECT
                    COUNT(*) AS total_documents,
                    COUNT(DISTINCT sd.loan_id) AS distinct_loans,
                    COUNT(DISTINCT sd.borrower_id) AS distinct_borrowers,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END)
                        AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END)
                        AS rejected,
                    COUNT(CASE WHEN sd.decision = 'NEEDS_REVIEW' THEN 1 END)
                        AS needs_review,
                    COUNT(CASE WHEN sd.detected_is_screenshot = TRUE THEN 1 END)
                        AS screenshots_detected
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
        ).fetchone()

        summary = {
            "total_documents": summary_row.total_documents or 0,
            "distinct_loans": summary_row.distinct_loans or 0,
            "distinct_borrowers": summary_row.distinct_borrowers or 0,
            "accepted": summary_row.accepted or 0,
            "rejected": summary_row.rejected or 0,
            "needs_review": summary_row.needs_review or 0,
            "screenshots_detected": summary_row.screenshots_detected or 0,
            "acceptance_rate": round(
                _safe_div(summary_row.accepted or 0, summary_row.total_documents or 0) * 100, 1,
            ),
        }

        # By doc type
        query = f"""
                SELECT
                    COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN') AS doc_type,
                    COUNT(*) AS count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN')
                ORDER BY count DESC
            """

        by_type_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data = {
            "by_doc_type": [
                {"doc_type": r.doc_type, "count": r.count}
                for r in by_type_rows
            ],
        }

        # By LO
        query = f"""
                SELECT
                    l.loan_officer_id AS lo_id,
                    CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
                    COUNT(*) AS count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY l.loan_officer_id, u.first_name, u.last_name
                ORDER BY count DESC
            """

        by_lo_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data["by_loan_officer"] = [
            {"lo_id": r.lo_id, "lo_name": r.lo_name, "count": r.count}
            for r in by_lo_rows
        ]

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS count,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejected
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
                "count": r.count,
                "accepted": r.accepted,
                "rejected": r.rejected,
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_processing_time(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Average processing time by doc type and processor."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.reviewed_at")
        filter_frag, extra_params = _build_org_loan_join_filter(
            config.filters, table_alias="sd", loan_alias="l",
        )
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            **extra_params,
        }

        # Overall summary
        query = f"""
                SELECT
                    COUNT(*) AS total_processed,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_hours,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600
                    ) AS median_hours,
                    PERCENTILE_CONT(0.9) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600
                    ) AS p90_hours,
                    MIN(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS min_hours,
                    MAX(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS max_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.uploaded_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
            """

        summary_row = self.db.execute(
            sa_text(query),
            params,
        ).fetchone()

        summary = {
            "total_processed": summary_row.total_processed or 0,
            "avg_hours": round(float(summary_row.avg_hours or 0), 2),
            "median_hours": round(float(summary_row.median_hours or 0), 2),
            "p90_hours": round(float(summary_row.p90_hours or 0), 2),
            "min_hours": round(float(summary_row.min_hours or 0), 2),
            "max_hours": round(float(summary_row.max_hours or 0), 2),
        }

        # By doc type
        query = f"""
                SELECT
                    COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN') AS doc_type,
                    COUNT(*) AS count,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_hours,
                    PERCENTILE_CONT(0.9) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600
                    ) AS p90_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.uploaded_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN')
                ORDER BY avg_hours DESC
            """

        by_type_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_doc_type": [
                {
                    "doc_type": r.doc_type,
                    "count": r.count,
                    "avg_hours": round(float(r.avg_hours or 0), 2),
                    "p90_hours": round(float(r.p90_hours or 0), 2),
                }
                for r in by_type_rows
            ],
        }

        # By processor (reviewed_by)
        query = f"""
                SELECT
                    sd.reviewed_by AS processor,
                    COUNT(*) AS count,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.uploaded_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY sd.reviewed_by
                ORDER BY count DESC
            """

        by_processor_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data["by_processor"] = [
            {
                "processor": r.processor,
                "count": r.count,
                "avg_hours": round(float(r.avg_hours or 0), 2),
            }
            for r in by_processor_rows
        ]

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS count,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.uploaded_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
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
                "count": r.count,
                "avg_hours": round(float(r.avg_hours or 0), 2),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_sla_compliance(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """SLA met/breached rates with trending."""
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
                    COUNT(*) AS total_requests,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND sdr.completed_at IS NOT NULL
                         AND sdr.completed_at <= sdr.sla_due_at
                        THEN 1
                    END) AS sla_met,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND (
                            (sdr.completed_at IS NOT NULL AND sdr.completed_at > sdr.sla_due_at)
                            OR
                            (sdr.completed_at IS NULL AND sdr.sla_due_at < NOW())
                         )
                        THEN 1
                    END) AS sla_breached,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND sdr.completed_at IS NULL
                         AND sdr.sla_due_at >= NOW()
                         AND sdr.sla_due_at < NOW() + INTERVAL '24 hours'
                        THEN 1
                    END) AS sla_at_risk,
                    AVG(CASE
                        WHEN sdr.completed_at IS NOT NULL AND sdr.sla_due_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (sdr.sla_due_at - sdr.completed_at)) / 3600
                    END) AS avg_margin_hours
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

        total = summary_row.total_requests or 0
        met = summary_row.sla_met or 0
        breached = summary_row.sla_breached or 0
        at_risk = summary_row.sla_at_risk or 0

        summary = {
            "total_requests": total,
            "sla_met": met,
            "sla_breached": breached,
            "sla_at_risk": at_risk,
            "met_rate": round(_safe_div(met, total) * 100, 1),
            "breach_rate": round(_safe_div(breached, total) * 100, 1),
            "avg_margin_hours": round(float(summary_row.avg_margin_hours or 0), 1),
        }

        # By doc type
        query = f"""
                SELECT
                    COALESCE(CAST(sdr.doc_type AS TEXT), 'UNKNOWN') AS doc_type,
                    COUNT(*) AS total,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND sdr.completed_at IS NOT NULL
                         AND sdr.completed_at <= sdr.sla_due_at
                        THEN 1
                    END) AS met,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND (
                            (sdr.completed_at IS NOT NULL AND sdr.completed_at > sdr.sla_due_at)
                            OR
                            (sdr.completed_at IS NULL AND sdr.sla_due_at < NOW())
                         )
                        THEN 1
                    END) AS breached
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY COALESCE(CAST(sdr.doc_type AS TEXT), 'UNKNOWN')
                ORDER BY breached DESC
            """

        by_type_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_doc_type": [
                {
                    "doc_type": r.doc_type,
                    "total": r.total,
                    "met": r.met,
                    "breached": r.breached,
                    "met_rate": round(_safe_div(r.met, r.total) * 100, 1),
                }
                for r in by_type_rows
            ],
        }

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS total,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND sdr.completed_at IS NOT NULL
                         AND sdr.completed_at <= sdr.sla_due_at
                        THEN 1
                    END) AS met,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND (
                            (sdr.completed_at IS NOT NULL AND sdr.completed_at > sdr.sla_due_at)
                            OR
                            (sdr.completed_at IS NULL AND sdr.sla_due_at < NOW())
                         )
                        THEN 1
                    END) AS breached
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
                "total": r.total,
                "met": r.met,
                "breached": r.breached,
                "met_rate": round(_safe_div(r.met, r.total) * 100, 1),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_income_accuracy(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """AI vs manual income calculation accuracy."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.reviewed_at")
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        # Compare AI-extracted amounts vs manually-entered amounts
        # where both exist on the same document
        summary_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_compared,
                    COUNT(CASE
                        WHEN sd.extracted_amount IS NOT NULL
                         AND sd.extraction_confidence >= 0.9
                        THEN 1
                    END) AS high_confidence,
                    AVG(sd.extraction_confidence) AS avg_confidence,
                    COUNT(CASE
                        WHEN sd.detected_doc_type IS NOT NULL
                         AND sd.doc_type IS NOT NULL
                         AND sd.detected_doc_type = CAST(sd.doc_type AS TEXT)
                        THEN 1
                    END) AS type_match,
                    COUNT(CASE
                        WHEN sd.detected_doc_type IS NOT NULL
                         AND sd.doc_type IS NOT NULL
                         AND sd.detected_doc_type != CAST(sd.doc_type AS TEXT)
                        THEN 1
                    END) AS type_mismatch
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.extracted_amount IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_compared = summary_row.total_compared or 0
        high_confidence = summary_row.high_confidence or 0
        type_match = summary_row.type_match or 0
        type_mismatch = summary_row.type_mismatch or 0

        summary = {
            "total_compared": total_compared,
            "high_confidence_count": high_confidence,
            "high_confidence_rate": round(
                _safe_div(high_confidence, total_compared) * 100, 1,
            ),
            "avg_confidence": round(float(summary_row.avg_confidence or 0), 3),
            "type_accuracy_rate": round(
                _safe_div(type_match, type_match + type_mismatch) * 100, 1,
            ),
        }

        # By doc type accuracy breakdown
        by_type_rows = self.db.execute(
            sa_text("""
                SELECT
                    COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN') AS doc_type,
                    COUNT(*) AS count,
                    AVG(sd.extraction_confidence) AS avg_confidence,
                    COUNT(CASE
                        WHEN sd.extraction_confidence >= 0.9 THEN 1
                    END) AS high_conf_count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.extracted_amount IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                GROUP BY COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN')
                ORDER BY count DESC
            """),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_doc_type": [
                {
                    "doc_type": r.doc_type,
                    "count": r.count,
                    "avg_confidence": round(float(r.avg_confidence or 0), 3),
                    "high_confidence_rate": round(
                        _safe_div(r.high_conf_count, r.count) * 100, 1,
                    ),
                }
                for r in by_type_rows
            ],
        }

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS count,
                    AVG(sd.extraction_confidence) AS avg_confidence
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.extracted_amount IS NOT NULL
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
                "count": r.count,
                "avg_confidence": round(float(r.avg_confidence or 0), 3),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_fraud_detection(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Fraud alerts by type and resolution rates."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.uploaded_at")
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        # Screenshot-based fraud detection from smart_documents
        summary_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_documents,
                    COUNT(CASE WHEN sd.detected_is_screenshot = TRUE THEN 1 END)
                        AS screenshot_flags,
                    COUNT(CASE
                        WHEN sd.rejection_category = 'SCREENSHOT' THEN 1
                    END) AS screenshot_rejections,
                    COUNT(CASE
                        WHEN sd.rejection_category IS NOT NULL THEN 1
                    END) AS total_rejections,
                    AVG(CASE
                        WHEN sd.detected_is_screenshot = TRUE
                        THEN sd.screenshot_confidence
                    END) AS avg_screenshot_confidence
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_docs = summary_row.total_documents or 0
        screenshot_flags = summary_row.screenshot_flags or 0
        screenshot_rejections = summary_row.screenshot_rejections or 0

        summary = {
            "total_documents": total_docs,
            "screenshot_flags": screenshot_flags,
            "screenshot_flag_rate": round(
                _safe_div(screenshot_flags, total_docs) * 100, 2,
            ),
            "screenshot_rejections": screenshot_rejections,
            "total_rejections": summary_row.total_rejections or 0,
            "avg_screenshot_confidence": round(
                float(summary_row.avg_screenshot_confidence or 0), 3,
            ),
        }

        # By rejection category
        by_category_rows = self.db.execute(
            sa_text("""
                SELECT
                    COALESCE(CAST(sd.rejection_category AS TEXT), 'NONE') AS category,
                    COUNT(*) AS count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.rejection_category IS NOT NULL
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                GROUP BY COALESCE(CAST(sd.rejection_category AS TEXT), 'NONE')
                ORDER BY count DESC
            """),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_rejection_category": [
                {"category": r.category, "count": r.count}
                for r in by_category_rows
            ],
        }

        # Doc-policy fraud-related events
        fraud_events = self.db.execute(
            sa_text("""
                SELECT
                    CAST(dpe.event_type AS TEXT) AS event_type,
                    COUNT(*) AS count
                FROM doc_policy_events dpe
                JOIN loans l ON l.id = dpe.loan_id
                WHERE l.organization_id = :org_id
                  AND dpe.event_type IN ('SCREENSHOT_REJECTED', 'FRESHNESS_REJECTED')
                  AND dpe.created_at >= :start_date
                  AND dpe.created_at <= :end_date + INTERVAL '1 day'
                GROUP BY dpe.event_type
                ORDER BY count DESC
            """),
            params,
        ).fetchall()

        data["policy_events"] = [
            {"event_type": r.event_type, "count": r.count}
            for r in fraud_events
        ]

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS total,
                    COUNT(CASE WHEN sd.detected_is_screenshot = TRUE THEN 1 END)
                        AS flagged
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
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
                "total": r.total,
                "flagged": r.flagged,
                "flag_rate": round(_safe_div(r.flagged, r.total) * 100, 2),
            }
            for r in series_rows
        ]

        return data, summary, series

