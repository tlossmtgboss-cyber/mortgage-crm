"""Internal comparison & drill-down builders."""

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


class ComparisonMixin:
    # =========================================================================
    # PRIVATE — Comparison & Drill-down
    # =========================================================================

    async def _build_comparison(
        self,
        report_type: ReportType,
        config: ReportConfig,
    ) -> Dict[str, Any]:
        """Build a period-over-period comparison block."""
        if config.comparison_range is None:
            return {}

        comparison_config = ReportConfig(
            date_range=config.comparison_range,
            group_by=config.group_by,
            filters=config.filters,
        )

        _, comparison_summary, _ = await self._dispatch_report(
            report_type, comparison_config,
        )

        _, current_summary, _ = await self._dispatch_report(
            report_type, config,
        )

        deltas: Dict[str, Any] = {}
        for key in current_summary:
            cv = current_summary[key]
            pv = comparison_summary.get(key)
            if isinstance(cv, (int, float)) and isinstance(pv, (int, float)):
                deltas[key] = {
                    "current": cv,
                    "previous": pv,
                    "absolute_change": round(cv - pv, 2),
                    "pct_change": _pct_change(cv, pv),
                }

        return {
            "comparison_period": {
                "start": config.comparison_range.start.isoformat(),
                "end": config.comparison_range.end.isoformat(),
            },
            "comparison_summary": comparison_summary,
            "deltas": deltas,
        }

    async def _build_drill_down(
        self,
        report_type: ReportType,
        config: ReportConfig,
    ) -> Dict[str, Any]:
        """Build hierarchical drill-down data.

        Level 0: org summary (default, already in the main report)
        Level 1: by-team (group by LO)
        Level 2: by-individual loan (per LO)
        Level 3: by-document (per loan)
        """
        dr = config.date_range
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        drill: Dict[str, Any] = {"level": config.drill_down_level}

        if config.drill_down_level >= 1:
            # Level 1: by LO
            lo_rows = self.db.execute(
                sa_text("""
                    SELECT
                        l.loan_officer_id AS lo_id,
                        CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
                        COUNT(DISTINCT sd.id) AS doc_count,
                        COUNT(DISTINCT l.id) AS loan_count,
                        COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted
                    FROM smart_documents sd
                    JOIN loans l ON l.id = sd.loan_id
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.organization_id = :org_id
                      AND sd.uploaded_at >= :start_date
                      AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                    GROUP BY l.loan_officer_id, u.first_name, u.last_name
                    ORDER BY doc_count DESC
                """),
                params,
            ).fetchall()

            drill["by_team"] = [
                {
                    "lo_id": r.lo_id,
                    "lo_name": r.lo_name,
                    "doc_count": r.doc_count,
                    "loan_count": r.loan_count,
                    "accepted": r.accepted,
                    "acceptance_rate": round(
                        _safe_div(r.accepted, r.doc_count) * 100, 1,
                    ),
                }
                for r in lo_rows
            ]

        if config.drill_down_level >= 2:
            # Level 2: by loan
            loan_rows = self.db.execute(
                sa_text("""
                    SELECT
                        l.id AS loan_id,
                        l.loan_number,
                        l.borrower_name,
                        l.stage,
                        l.loan_officer_id,
                        COUNT(sd.id) AS doc_count,
                        COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted,
                        COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejected
                    FROM loans l
                    LEFT JOIN smart_documents sd ON sd.loan_id = l.id
                        AND sd.uploaded_at >= :start_date
                        AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                    WHERE l.organization_id = :org_id
                    GROUP BY l.id, l.loan_number, l.borrower_name, l.stage,
                             l.loan_officer_id
                    HAVING COUNT(sd.id) > 0
                    ORDER BY doc_count DESC
                    LIMIT 100
                """),
                params,
            ).fetchall()

            drill["by_loan"] = [
                {
                    "loan_id": r.loan_id,
                    "loan_number": r.loan_number,
                    "borrower_name": r.borrower_name,
                    "stage": r.stage,
                    "lo_id": r.loan_officer_id,
                    "doc_count": r.doc_count,
                    "accepted": r.accepted,
                    "rejected": r.rejected,
                }
                for r in loan_rows
            ]

        return drill

    async def _dispatch_report(
        self,
        report_type: ReportType,
        config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Dispatch to the correct report handler (internal helper)."""
        handler_map = {
            ReportType.DOCUMENT_VOLUME: self._report_document_volume,
            ReportType.PROCESSING_TIME: self._report_processing_time,
            ReportType.SLA_COMPLIANCE: self._report_sla_compliance,
            ReportType.INCOME_ACCURACY: self._report_income_accuracy,
            ReportType.FRAUD_DETECTION: self._report_fraud_detection,
            ReportType.BORROWER_ENGAGEMENT: self._report_borrower_engagement,
            ReportType.CONDITION_TRACKING: self._report_condition_tracking,
            ReportType.COMPLIANCE_AUDIT: self._report_compliance_audit,
            ReportType.TEAM_PRODUCTIVITY: self._report_team_productivity,
            ReportType.EXECUTIVE_SUMMARY: self._report_executive_summary,
        }
        return await handler_map[report_type](config)

