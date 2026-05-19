"""Public export endpoint (delegates to per-format formatters)."""

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


class ExportMixin:
    # =========================================================================
    # PUBLIC — Export
    # =========================================================================

    async def export_report(
        self,
        report_result: ReportResult,
        fmt: ExportFormat,
    ) -> bytes:
        """Export a previously-generated report to the requested format.

        Args:
            report_result: The :class:`ReportResult` to export.
            fmt: One of JSON, CSV, or PDF.

        Returns:
            The serialized report as raw bytes.
        """
        if fmt == ExportFormat.JSON:
            return self._export_json(report_result)
        elif fmt == ExportFormat.CSV:
            return self._export_csv(report_result)
        elif fmt == ExportFormat.PDF:
            return self._export_pdf(report_result)
        raise ValueError(f"Unsupported export format: {fmt}")

