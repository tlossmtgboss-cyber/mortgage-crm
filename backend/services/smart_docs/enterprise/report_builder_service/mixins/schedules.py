"""Scheduled report delivery (recurring runs)."""

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


class SchedulesMixin:
    # =========================================================================
    # PUBLIC — Scheduled Reports
    # =========================================================================

    async def schedule_report(
        self,
        report_type: ReportType,
        frequency: ScheduleFrequency,
        recipients: List[str],
        config: Optional[ReportConfig] = None,
    ) -> ScheduleResult:
        """Create a recurring schedule for automatic report delivery.

        Args:
            report_type: Which report to generate.
            frequency: How often to generate/deliver.
            recipients: Email addresses to send to.
            config: Optional saved config. Defaults to standard settings.

        Returns:
            A :class:`ScheduleResult` with the schedule_id and next run time.
        """
        schedule_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        next_run = self._compute_next_run(frequency, now)

        config_dict: Dict[str, Any] = {}
        if config is not None:
            config_dict = {
                "group_by": config.group_by.value,
                "filters": {
                    "lo_ids": config.filters.lo_ids,
                    "loan_types": config.filters.loan_types,
                    "doc_types": config.filters.doc_types,
                },
                "page_size": config.page_size,
            }

        self.db.execute(
            sa_text("""
                INSERT INTO smart_docs_report_schedules
                    (schedule_id, organization_id, report_type, frequency,
                     recipients, config, next_run_at, is_active,
                     created_by, created_at)
                VALUES
                    (:schedule_id, :org_id, :report_type, :frequency,
                     :recipients, :config, :next_run_at, TRUE,
                     :created_by, :now)
            """),
            {
                "schedule_id": schedule_id,
                "org_id": self.org_id,
                "report_type": report_type.value,
                "frequency": frequency.value,
                "recipients": json.dumps(recipients),
                "config": json.dumps(config_dict),
                "next_run_at": next_run,
                "created_by": self.user_id,
                "now": now,
            },
        )
        self.db.flush()

        return ScheduleResult(
            schedule_id=schedule_id,
            report_type=report_type,
            frequency=frequency,
            recipients=recipients,
            next_run_at=next_run,
            is_active=True,
        )

