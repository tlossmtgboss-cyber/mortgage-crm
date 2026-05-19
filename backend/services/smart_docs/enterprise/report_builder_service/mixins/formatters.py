"""Export formatters: JSON, CSV, PDF."""

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


class FormattersMixin:
    # =========================================================================
    # PRIVATE — Export Formatters
    # =========================================================================

    def _export_json(self, report: ReportResult) -> bytes:
        """Serialize report to JSON bytes."""
        return json.dumps(report.to_dict(), indent=2, default=str).encode("utf-8")

    def _export_csv(self, report: ReportResult) -> bytes:
        """Serialize report time-series and data tables to CSV bytes.

        Produces a multi-section CSV:
        1. Summary section (key-value)
        2. Time-series section (if available)
        3. Data breakdown sections
        """
        buf = io.StringIO()
        writer = csv.writer(buf)

        # Section 1: Summary
        writer.writerow(["--- Summary ---"])
        writer.writerow(["Metric", "Value"])
        for key, val in report.summary.items():
            writer.writerow([key, val])
        writer.writerow([])

        # Section 2: Time Series
        if report.series:
            writer.writerow(["--- Time Series ---"])
            headers = list(report.series[0].keys())
            writer.writerow(headers)
            for row in report.series:
                writer.writerow([row.get(h, "") for h in headers])
            writer.writerow([])

        # Section 3: Data breakdowns
        for section_name, section_data in report.data.items():
            if isinstance(section_data, list) and section_data:
                writer.writerow([f"--- {section_name} ---"])
                headers = list(section_data[0].keys())
                writer.writerow(headers)
                for row in section_data:
                    writer.writerow([row.get(h, "") for h in headers])
                writer.writerow([])

        return buf.getvalue().encode("utf-8")

    def _export_pdf(self, report: ReportResult) -> bytes:
        """Generate a PDF-like text report.

        For full PDF rendering, the caller should integrate a library such as
        WeasyPrint or ReportLab.  This method produces a structured text
        representation suitable for PDF generation pipelines.
        """
        lines: List[str] = []
        lines.append(f"REPORT: {report.title}")
        lines.append(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(
            f"Period: {report.date_range.start.isoformat()} - "
            f"{report.date_range.end.isoformat()}"
        )
        lines.append(f"Organization: {report.org_id}")
        lines.append("")
        lines.append("=" * 60)
        lines.append("SUMMARY")
        lines.append("=" * 60)

        for key, val in report.summary.items():
            display_key = key.replace("_", " ").title()
            lines.append(f"  {display_key}: {val}")

        lines.append("")

        if report.series:
            lines.append("=" * 60)
            lines.append("TIME SERIES")
            lines.append("=" * 60)
            for entry in report.series:
                parts = [f"{k}={v}" for k, v in entry.items()]
                lines.append(f"  {', '.join(parts)}")

        lines.append("")

        for section_name, section_data in report.data.items():
            if isinstance(section_data, list) and section_data:
                lines.append("-" * 40)
                lines.append(section_name.replace("_", " ").upper())
                lines.append("-" * 40)
                for row in section_data[:20]:  # Cap for readability
                    parts = [f"{k}={v}" for k, v in row.items()]
                    lines.append(f"  {', '.join(parts)}")

        if report.comparison:
            lines.append("")
            lines.append("=" * 60)
            lines.append("PERIOD COMPARISON")
            lines.append("=" * 60)
            deltas = report.comparison.get("deltas", {})
            for key, delta in deltas.items():
                if isinstance(delta, dict):
                    pct = delta.get("pct_change")
                    pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"
                    lines.append(
                        f"  {key}: {delta.get('current', '')} "
                        f"(was {delta.get('previous', '')}, {pct_str})"
                    )

        return "\n".join(lines).encode("utf-8")

