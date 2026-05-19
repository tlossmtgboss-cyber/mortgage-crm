"""Public report generation entry point."""

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


class GenerationMixin:
    # =========================================================================
    # PUBLIC — Report Generation
    # =========================================================================

    async def generate_report(
        self,
        report_type: ReportType,
        config: Optional[ReportConfig] = None,
    ) -> ReportResult:
        """Generate a report of the given type.

        Args:
            report_type: One of the pre-built :class:`ReportType` values.
            config: Optional configuration (date range, grouping, filters).
                    Defaults to last 30 days grouped by week.

        Returns:
            A :class:`ReportResult` containing summary, time-series, and
            optional drill-down data.
        """
        if config is None:
            config = ReportConfig()

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

        handler = handler_map.get(report_type)
        if handler is None:
            raise ValueError(f"Unknown report type: {report_type}")

        data, summary, series = await handler(config)

        # Build comparison if a comparison range was requested
        comparison = None
        if config.comparison_range is not None:
            comparison = await self._build_comparison(report_type, config)

        # Build drill-down if requested
        drill_down = None
        if config.drill_down_level > 0:
            drill_down = await self._build_drill_down(
                report_type, config,
            )

        report_id = uuid.uuid4().hex[:16]

        return ReportResult(
            report_id=report_id,
            report_type=report_type,
            title=_REPORT_CATALOG[report_type].name,
            generated_at=datetime.now(timezone.utc),
            date_range=config.date_range,
            org_id=self.org_id,
            data=data,
            summary=summary,
            series=series,
            comparison=comparison,
            drill_down=drill_down,
            metadata={
                "group_by": config.group_by.value,
                "page": config.page,
                "page_size": config.page_size,
            },
        )

