"""Internal scheduling helpers (next-run computation)."""

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


class ScheduleHelpersMixin:
    # =========================================================================
    # PRIVATE — Schedule Helpers
    # =========================================================================

    @staticmethod
    def _compute_next_run(
        frequency: ScheduleFrequency,
        now: datetime,
    ) -> datetime:
        """Compute the next run timestamp for a schedule frequency."""
        if frequency == ScheduleFrequency.DAILY:
            # Next day at 06:00 UTC
            next_day = now.date() + timedelta(days=1)
            return datetime(
                next_day.year, next_day.month, next_day.day,
                6, 0, 0, tzinfo=timezone.utc,
            )
        elif frequency == ScheduleFrequency.WEEKLY:
            # Next Monday at 06:00 UTC
            days_ahead = 7 - now.weekday()  # 0=Monday
            if days_ahead == 0:
                days_ahead = 7
            next_monday = now.date() + timedelta(days=days_ahead)
            return datetime(
                next_monday.year, next_monday.month, next_monday.day,
                6, 0, 0, tzinfo=timezone.utc,
            )
        elif frequency == ScheduleFrequency.MONTHLY:
            # First of next month at 06:00 UTC
            if now.month == 12:
                first_next = date(now.year + 1, 1, 1)
            else:
                first_next = date(now.year, now.month + 1, 1)
            return datetime(
                first_next.year, first_next.month, first_next.day,
                6, 0, 0, tzinfo=timezone.utc,
            )
        else:
            # Custom: default to daily
            return ReportBuilderService._compute_next_run(
                ScheduleFrequency.DAILY, now,
            )
