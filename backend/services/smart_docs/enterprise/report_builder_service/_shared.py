"""
Smart Docs Enterprise Report Builder Service

Generates operational, compliance, and executive reports for Smart Docs
operations.  Provides pre-built report types (document volume, processing
time, SLA compliance, fraud detection, and more), configurable date ranges
and groupings, export to JSON/CSV/PDF, scheduled report delivery, reusable
templates, KPI calculations, trend analysis, and drill-down data structures.

All queries are org_id-scoped for multi-tenant isolation.

Data sources:
    - smart_documents: uploaded docs with review decisions
    - smart_document_requests: request SLA and status
    - doc_policy_events: document lifecycle events
    - document_followup_events: outbound/inbound communication events
    - document_followup_campaigns: campaign lifecycle
    - loans: loan context (stage, LO, org)
    - users: LO/processor names
    - compliance_alerts: compliance alert history

Usage:
    from services.smart_docs.enterprise.report_builder_service import (
        ReportBuilderService,
        get_report_builder_service,
        ReportType,
        ReportConfig,
    )

    svc = get_report_builder_service(db, org_id=42)
    result = await svc.generate_report(
        ReportType.DOCUMENT_VOLUME,
        ReportConfig(
            date_range=DateRange.last_30_days(),
            group_by=GroupBy.WEEK,
        ),
    )

    csv_bytes = await svc.export_report(result.report_id, ExportFormat.CSV)
"""

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

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class ReportType(str, Enum):
    """Pre-built report types."""
    DOCUMENT_VOLUME = "document_volume"
    PROCESSING_TIME = "processing_time"
    SLA_COMPLIANCE = "sla_compliance"
    INCOME_ACCURACY = "income_accuracy"
    FRAUD_DETECTION = "fraud_detection"
    BORROWER_ENGAGEMENT = "borrower_engagement"
    CONDITION_TRACKING = "condition_tracking"
    COMPLIANCE_AUDIT = "compliance_audit"
    TEAM_PRODUCTIVITY = "team_productivity"
    EXECUTIVE_SUMMARY = "executive_summary"


class GroupBy(str, Enum):
    """Time-based grouping for aggregated reports."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"


class ExportFormat(str, Enum):
    """Supported export formats."""
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"


class ScheduleFrequency(str, Enum):
    """Frequency for scheduled reports."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class UserRole(str, Enum):
    """Roles for report access control."""
    ADMIN = "admin"
    MANAGER = "manager"
    LOAN_OFFICER = "loan_officer"
    PROCESSOR = "processor"


# Reports accessible per role (role -> set of allowed ReportType values)
_ROLE_REPORT_ACCESS: Dict[str, set] = {
    UserRole.ADMIN: {rt.value for rt in ReportType},
    UserRole.MANAGER: {rt.value for rt in ReportType},
    UserRole.LOAN_OFFICER: {
        ReportType.DOCUMENT_VOLUME.value,
        ReportType.PROCESSING_TIME.value,
        ReportType.SLA_COMPLIANCE.value,
        ReportType.BORROWER_ENGAGEMENT.value,
        ReportType.CONDITION_TRACKING.value,
    },
    UserRole.PROCESSOR: {
        ReportType.DOCUMENT_VOLUME.value,
        ReportType.PROCESSING_TIME.value,
        ReportType.SLA_COMPLIANCE.value,
        ReportType.CONDITION_TRACKING.value,
    },
}


# =============================================================================
# DATE RANGE
# =============================================================================

@dataclass(frozen=True)
class DateRange:
    """Inclusive date range for report queries."""
    start: date
    end: date

    @classmethod
    def last_n_days(cls, days: int) -> DateRange:
        today = date.today()
        return cls(start=today - timedelta(days=days), end=today)

    @classmethod
    def last_30_days(cls) -> DateRange:
        return cls.last_n_days(30)

    @classmethod
    def last_90_days(cls) -> DateRange:
        return cls.last_n_days(90)

    @classmethod
    def this_month(cls) -> DateRange:
        today = date.today()
        return cls(start=today.replace(day=1), end=today)

    @classmethod
    def last_month(cls) -> DateRange:
        today = date.today()
        first_of_this_month = today.replace(day=1)
        last_of_prev = first_of_this_month - timedelta(days=1)
        first_of_prev = last_of_prev.replace(day=1)
        return cls(start=first_of_prev, end=last_of_prev)

    @property
    def span_days(self) -> int:
        return max((self.end - self.start).days, 1)

    def to_params(self, prefix: str = "") -> Dict[str, date]:
        s = "start_date" if not prefix else f"{prefix}_start"
        e = "end_date" if not prefix else f"{prefix}_end"
        return {s: self.start, e: self.end}


# =============================================================================
# CONFIG & FILTER DATACLASSES
# =============================================================================

@dataclass
class ReportFilter:
    """Filtering criteria for reports."""
    lo_ids: Optional[List[int]] = None
    loan_types: Optional[List[str]] = None
    branch_ids: Optional[List[int]] = None
    doc_types: Optional[List[str]] = None
    loan_stages: Optional[List[str]] = None


@dataclass
class ReportConfig:
    """Full configuration for generating a report."""
    date_range: DateRange = field(default_factory=DateRange.last_30_days)
    group_by: GroupBy = GroupBy.WEEK
    filters: ReportFilter = field(default_factory=ReportFilter)
    comparison_range: Optional[DateRange] = None
    sort_by: Optional[str] = None
    sort_desc: bool = True
    page: int = 1
    page_size: int = 50
    drill_down_level: int = 0  # 0=summary, 1=team, 2=individual, 3=loan


@dataclass
class ReportInfo:
    """Metadata about an available report."""
    report_type: ReportType
    name: str
    description: str
    category: str
    required_role: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_type": self.report_type.value,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "required_role": self.required_role,
        }


# =============================================================================
# RESULT DATACLASSES
# =============================================================================

@dataclass
class ReportResult:
    """Complete result from report generation."""
    report_id: str
    report_type: ReportType
    title: str
    generated_at: datetime
    date_range: DateRange
    org_id: int
    data: Dict[str, Any]
    summary: Dict[str, Any]
    series: List[Dict[str, Any]] = field(default_factory=list)
    comparison: Optional[Dict[str, Any]] = None
    drill_down: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "report_type": self.report_type.value,
            "title": self.title,
            "generated_at": self.generated_at.isoformat(),
            "date_range": {
                "start": self.date_range.start.isoformat(),
                "end": self.date_range.end.isoformat(),
                "span_days": self.date_range.span_days,
            },
            "org_id": self.org_id,
            "data": self.data,
            "summary": self.summary,
            "series": self.series,
            "comparison": self.comparison,
            "drill_down": self.drill_down,
            "metadata": self.metadata,
        }


@dataclass
class KPIDashboard:
    """High-level KPI dashboard data."""
    org_id: int
    generated_at: datetime
    period: DateRange
    kpis: Dict[str, Any]
    trends: Dict[str, Any]
    alerts: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at.isoformat(),
            "period": {
                "start": self.period.start.isoformat(),
                "end": self.period.end.isoformat(),
            },
            "kpis": self.kpis,
            "trends": self.trends,
            "alerts": self.alerts,
        }


@dataclass
class ComparisonResult:
    """Period-over-period comparison result."""
    report_type: ReportType
    period_1: DateRange
    period_2: DateRange
    period_1_data: Dict[str, Any]
    period_2_data: Dict[str, Any]
    deltas: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_type": self.report_type.value,
            "period_1": {
                "start": self.period_1.start.isoformat(),
                "end": self.period_1.end.isoformat(),
            },
            "period_2": {
                "start": self.period_2.start.isoformat(),
                "end": self.period_2.end.isoformat(),
            },
            "period_1_data": self.period_1_data,
            "period_2_data": self.period_2_data,
            "deltas": self.deltas,
        }


@dataclass
class ReportTemplate:
    """Saved report configuration template."""
    template_id: str
    org_id: int
    name: str
    description: str
    report_type: ReportType
    config: Dict[str, Any]
    created_by: Optional[int]
    is_shared: bool
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "org_id": self.org_id,
            "name": self.name,
            "description": self.description,
            "report_type": self.report_type.value,
            "config": self.config,
            "created_by": self.created_by,
            "is_shared": self.is_shared,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ScheduleResult:
    """Result from scheduling a recurring report."""
    schedule_id: str
    report_type: ReportType
    frequency: ScheduleFrequency
    recipients: List[str]
    next_run_at: datetime
    is_active: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "report_type": self.report_type.value,
            "frequency": self.frequency.value,
            "recipients": self.recipients,
            "next_run_at": self.next_run_at.isoformat(),
            "is_active": self.is_active,
        }


# =============================================================================
# REPORT CATALOG — Static metadata for every report type
# =============================================================================

_REPORT_CATALOG: Dict[ReportType, ReportInfo] = {
    ReportType.DOCUMENT_VOLUME: ReportInfo(
        report_type=ReportType.DOCUMENT_VOLUME,
        name="Document Volume",
        description="Documents processed by type, by period, and by loan officer",
        category="operational",
        required_role=UserRole.PROCESSOR,
    ),
    ReportType.PROCESSING_TIME: ReportInfo(
        report_type=ReportType.PROCESSING_TIME,
        name="Processing Time",
        description="Average processing time by document type and by processor",
        category="operational",
        required_role=UserRole.PROCESSOR,
    ),
    ReportType.SLA_COMPLIANCE: ReportInfo(
        report_type=ReportType.SLA_COMPLIANCE,
        name="SLA Compliance",
        description="SLA met/breached rates with trending analysis",
        category="compliance",
        required_role=UserRole.PROCESSOR,
    ),
    ReportType.INCOME_ACCURACY: ReportInfo(
        report_type=ReportType.INCOME_ACCURACY,
        name="Income Accuracy",
        description="AI vs manual income calculation accuracy comparison",
        category="analytics",
        required_role=UserRole.MANAGER,
    ),
    ReportType.FRAUD_DETECTION: ReportInfo(
        report_type=ReportType.FRAUD_DETECTION,
        name="Fraud Detection",
        description="Fraud alerts by type and resolution rates",
        category="compliance",
        required_role=UserRole.MANAGER,
    ),
    ReportType.BORROWER_ENGAGEMENT: ReportInfo(
        report_type=ReportType.BORROWER_ENGAGEMENT,
        name="Borrower Engagement",
        description="Portal usage, upload patterns, and response rates",
        category="analytics",
        required_role=UserRole.LOAN_OFFICER,
    ),
    ReportType.CONDITION_TRACKING: ReportInfo(
        report_type=ReportType.CONDITION_TRACKING,
        name="Condition Tracking",
        description="Outstanding conditions, clearance rates, and aging",
        category="operational",
        required_role=UserRole.PROCESSOR,
    ),
    ReportType.COMPLIANCE_AUDIT: ReportInfo(
        report_type=ReportType.COMPLIANCE_AUDIT,
        name="Compliance Audit",
        description="Disclosure timing, consent tracking, and retention compliance",
        category="compliance",
        required_role=UserRole.MANAGER,
    ),
    ReportType.TEAM_PRODUCTIVITY: ReportInfo(
        report_type=ReportType.TEAM_PRODUCTIVITY,
        name="Team Productivity",
        description="Per-user metrics, workload distribution, and efficiency",
        category="management",
        required_role=UserRole.MANAGER,
    ),
    ReportType.EXECUTIVE_SUMMARY: ReportInfo(
        report_type=ReportType.EXECUTIVE_SUMMARY,
        name="Executive Summary",
        description="High-level KPIs for leadership review",
        category="executive",
        required_role=UserRole.MANAGER,
    ),
}


# =============================================================================
# SQL HELPERS
# =============================================================================

def _group_by_expression(group_by: GroupBy, column: str = "created_at") -> str:
    """Return the SQL expression for time-based grouping.

    Uses PostgreSQL ``date_trunc()`` which returns a timestamp truncated to
    the requested precision.  ``quarter`` is natively supported.
    """
    precision_map = {
        GroupBy.DAY: "day",
        GroupBy.WEEK: "week",
        GroupBy.MONTH: "month",
        GroupBy.QUARTER: "quarter",
    }
    precision = precision_map[group_by]
    return f"date_trunc('{precision}', {column})"


def _build_org_loan_join_filter(
    filters: ReportFilter,
    table_alias: str = "sd",
    loan_alias: str = "l",
    extra_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Build WHERE clause fragments and params from ReportFilter.

    Returns (where_clause_fragment, params_dict).  The fragment always starts
    with "AND" so it can be appended to an existing WHERE.
    """
    clauses: List[str] = []
    params: Dict[str, Any] = dict(extra_params or {})

    if filters.lo_ids:
        clauses.append(f"{loan_alias}.loan_officer_id = ANY(:lo_ids)")
        params["lo_ids"] = filters.lo_ids
    if filters.loan_types:
        clauses.append(f"{loan_alias}.loan_type = ANY(:loan_types)")
        params["loan_types"] = filters.loan_types
    if filters.doc_types:
        clauses.append(f"{table_alias}.doc_type = ANY(:doc_types)")
        params["doc_types"] = filters.doc_types
    if filters.loan_stages:
        clauses.append(f"{loan_alias}.stage = ANY(:loan_stages)")
        params["loan_stages"] = filters.loan_stages

    fragment = ""
    if clauses:
        fragment = " AND " + " AND ".join(clauses)
    return fragment, params


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that returns *default* when the denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def _pct_change(current: float, previous: float) -> Optional[float]:
    """Percentage change from *previous* to *current*. Returns None when
    *previous* is zero (undefined)."""
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 2)


