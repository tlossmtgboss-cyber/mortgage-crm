"""Save/load reusable report configuration templates."""

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


class TemplatesMixin:
    # =========================================================================
    # PUBLIC — Templates
    # =========================================================================

    async def save_report_template(
        self,
        name: str,
        description: str,
        report_type: ReportType,
        config: ReportConfig,
        is_shared: bool = False,
    ) -> ReportTemplate:
        """Persist a report configuration as a reusable template.

        Args:
            name: Human-readable name for the template.
            description: Short description.
            report_type: The report type this template configures.
            config: The full :class:`ReportConfig` to save.
            is_shared: Whether other users in the org can see this template.

        Returns:
            The saved :class:`ReportTemplate`.
        """
        template_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)

        config_dict = {
            "date_range": {
                "start": config.date_range.start.isoformat(),
                "end": config.date_range.end.isoformat(),
            },
            "group_by": config.group_by.value,
            "filters": {
                "lo_ids": config.filters.lo_ids,
                "loan_types": config.filters.loan_types,
                "branch_ids": config.filters.branch_ids,
                "doc_types": config.filters.doc_types,
                "loan_stages": config.filters.loan_stages,
            },
            "sort_by": config.sort_by,
            "sort_desc": config.sort_desc,
            "page_size": config.page_size,
        }

        self.db.execute(
            sa_text("""
                INSERT INTO smart_docs_report_templates
                    (template_id, organization_id, name, description,
                     report_type, config, created_by, is_shared, created_at)
                VALUES
                    (:template_id, :org_id, :name, :description,
                     :report_type, :config, :created_by, :is_shared, :created_at)
                ON CONFLICT (template_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    config = EXCLUDED.config,
                    is_shared = EXCLUDED.is_shared
            """),
            {
                "template_id": template_id,
                "org_id": self.org_id,
                "name": name,
                "description": description,
                "report_type": report_type.value,
                "config": json.dumps(config_dict),
                "created_by": self.user_id,
                "is_shared": is_shared,
                "created_at": now,
            },
        )
        self.db.flush()

        return ReportTemplate(
            template_id=template_id,
            org_id=self.org_id,
            name=name,
            description=description,
            report_type=report_type,
            config=config_dict,
            created_by=self.user_id,
            is_shared=is_shared,
            created_at=now,
        )

