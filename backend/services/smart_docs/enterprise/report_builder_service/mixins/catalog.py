"""Report catalog and access control."""

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


class CatalogMixin:
    # =========================================================================
    # PUBLIC — Report Catalog & Access Control
    # =========================================================================

    async def get_available_reports(
        self,
        user_role: str,
    ) -> List[ReportInfo]:
        """Return reports accessible to *user_role*.

        Args:
            user_role: One of ``admin``, ``manager``, ``loan_officer``,
                       ``processor``.

        Returns:
            List of :class:`ReportInfo` the user may generate.
        """
        allowed = _ROLE_REPORT_ACCESS.get(user_role, set())
        return [
            info
            for rt, info in _REPORT_CATALOG.items()
            if rt.value in allowed
        ]
