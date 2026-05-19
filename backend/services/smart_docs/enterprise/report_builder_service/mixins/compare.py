"""Period-over-period comparison."""

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


class CompareMixin:
    # =========================================================================
    # PUBLIC — Period Comparison
    # =========================================================================

    async def compare_periods(
        self,
        report_type: ReportType,
        period_1: DateRange,
        period_2: DateRange,
    ) -> ComparisonResult:
        """Compare two periods for the same report type.

        Generates summary-level data for each period and computes deltas.

        Args:
            report_type: The report to compare.
            period_1: First (typically earlier) period.
            period_2: Second (typically later/current) period.

        Returns:
            A :class:`ComparisonResult` with both periods' data and deltas.
        """
        cfg1 = ReportConfig(date_range=period_1)
        cfg2 = ReportConfig(date_range=period_2)

        r1 = await self.generate_report(report_type, cfg1)
        r2 = await self.generate_report(report_type, cfg2)

        deltas: Dict[str, Any] = {}
        for key in r1.summary:
            v1 = r1.summary[key]
            v2 = r2.summary[key]
            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                deltas[key] = {
                    "absolute": round(v2 - v1, 2),
                    "pct_change": _pct_change(v2, v1),
                }

        return ComparisonResult(
            report_type=report_type,
            period_1=period_1,
            period_2=period_2,
            period_1_data=r1.summary,
            period_2_data=r2.summary,
            deltas=deltas,
        )

