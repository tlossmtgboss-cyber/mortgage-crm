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


# =============================================================================
# REPORT BUILDER SERVICE
# =============================================================================

class ReportBuilderService:
    """Generates operational, compliance, and executive reports for Smart Docs.

    All queries are scoped to ``org_id`` — cross-tenant data is never
    returned.  The service is designed to be instantiated per-request via
    :func:`get_report_builder_service`.
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        if not org_id:
            raise ValueError("org_id is required for ReportBuilderService")
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

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

    # =========================================================================
    # PUBLIC — KPI Dashboard
    # =========================================================================

    async def get_kpi_dashboard(
        self,
        period: Optional[DateRange] = None,
    ) -> KPIDashboard:
        """Return a high-level KPI dashboard for the organization.

        Computes document collection rate, first-pass approval rate,
        time-to-complete, AI accuracy, borrower engagement score, and
        cost per document.

        Args:
            period: Date range. Defaults to last 30 days.

        Returns:
            A :class:`KPIDashboard` with computed KPIs, trends, and alerts.
        """
        if period is None:
            period = DateRange.last_30_days()

        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **period.to_params(),
        }

        # ---- Document collection rate ---
        collection = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_requested,
                    COUNT(CASE WHEN sdr.status IN ('ACCEPTED', 'WAIVED') THEN 1 END)
                        AS fulfilled
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_requested = collection.total_requested or 0
        fulfilled = collection.fulfilled or 0
        collection_rate = round(_safe_div(fulfilled, total_requested) * 100, 1)

        # ---- First-pass approval rate ---
        first_pass = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_reviewed,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END)
                        AS first_accept
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  AND sd.decision IS NOT NULL
            """),
            params,
        ).fetchone()

        total_reviewed = first_pass.total_reviewed or 0
        first_accept = first_pass.first_accept or 0
        first_pass_rate = round(_safe_div(first_accept, total_reviewed) * 100, 1)

        # ---- Average time-to-complete (request created -> status ACCEPTED) ---
        ttc = self.db.execute(
            sa_text("""
                SELECT
                    AVG(EXTRACT(EPOCH FROM (sdr.completed_at - sdr.created_at)) / 3600)
                        AS avg_hours
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.completed_at IS NOT NULL
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        avg_ttc_hours = round(float(ttc.avg_hours or 0), 1)

        # ---- AI accuracy (classification confirmed by human) ---
        ai_accuracy = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_classified,
                    COUNT(CASE
                        WHEN sd.detected_doc_type IS NOT NULL
                         AND sd.doc_type IS NOT NULL
                         AND sd.detected_doc_type = CAST(sd.doc_type AS TEXT)
                        THEN 1
                    END) AS correct
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.detected_doc_type IS NOT NULL
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_classified = ai_accuracy.total_classified or 0
        correct_classified = ai_accuracy.correct or 0
        ai_accuracy_rate = round(
            _safe_div(correct_classified, total_classified) * 100, 1,
        )

        # ---- Borrower engagement (upload source diversity as proxy) ---
        engagement = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(DISTINCT sd.borrower_id) AS active_borrowers,
                    COUNT(*) AS total_uploads,
                    COUNT(CASE WHEN sd.upload_source = 'WEB' THEN 1 END)
                        AS web_uploads,
                    COUNT(CASE WHEN sd.upload_source = 'MOBILE' THEN 1 END)
                        AS mobile_uploads,
                    COUNT(CASE WHEN sd.upload_source = 'EMAIL' THEN 1 END)
                        AS email_uploads
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        active_borrowers = engagement.active_borrowers or 0
        total_uploads = engagement.total_uploads or 0

        # ---- Cost per document (AI operations) ---
        ai_ops = self.db.execute(
            sa_text("""
                SELECT COUNT(*) AS ai_operations
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.detected_doc_type IS NOT NULL
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        ai_ops_count = ai_ops.ai_operations or 0
        est_cost_per_doc = round(ai_ops_count * 0.08 / max(total_uploads, 1), 4)

        # ---- Trends (compare to previous period of same length) ---
        prev_range = DateRange(
            start=period.start - timedelta(days=period.span_days),
            end=period.start - timedelta(days=1),
        )
        prev_params: Dict[str, Any] = {
            "org_id": self.org_id,
            **prev_range.to_params(),
        }

        prev_collection = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_requested,
                    COUNT(CASE WHEN sdr.status IN ('ACCEPTED', 'WAIVED') THEN 1 END)
                        AS fulfilled
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
            """),
            prev_params,
        ).fetchone()

        prev_total = prev_collection.total_requested or 0
        prev_fulfilled = prev_collection.fulfilled or 0
        prev_rate = round(_safe_div(prev_fulfilled, prev_total) * 100, 1)

        # ---- Alerts ---
        alerts: List[Dict[str, Any]] = []
        if collection_rate < 60:
            alerts.append({
                "severity": "critical",
                "metric": "collection_rate",
                "message": f"Document collection rate is {collection_rate}% (target 80%+)",
            })
        if first_pass_rate < 50:
            alerts.append({
                "severity": "warning",
                "metric": "first_pass_rate",
                "message": f"First-pass approval rate is {first_pass_rate}% (target 70%+)",
            })
        if avg_ttc_hours > 72:
            alerts.append({
                "severity": "warning",
                "metric": "time_to_complete",
                "message": f"Average time-to-complete is {avg_ttc_hours}h (target <48h)",
            })

        return KPIDashboard(
            org_id=self.org_id,
            generated_at=datetime.now(timezone.utc),
            period=period,
            kpis={
                "document_collection_rate": collection_rate,
                "first_pass_approval_rate": first_pass_rate,
                "avg_time_to_complete_hours": avg_ttc_hours,
                "ai_accuracy_rate": ai_accuracy_rate,
                "active_borrowers": active_borrowers,
                "total_uploads": total_uploads,
                "cost_per_document": est_cost_per_doc,
                "total_requested": total_requested,
                "total_fulfilled": fulfilled,
                "total_ai_operations": ai_ops_count,
            },
            trends={
                "collection_rate_change": _pct_change(collection_rate, prev_rate),
                "volume_change": _pct_change(total_requested, prev_total),
                "previous_period": {
                    "start": prev_range.start.isoformat(),
                    "end": prev_range.end.isoformat(),
                    "collection_rate": prev_rate,
                    "total_requested": prev_total,
                },
            },
            alerts=alerts,
        )

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

    # =========================================================================
    # PRIVATE — Report Generators
    # =========================================================================

    async def _report_document_volume(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Documents processed by type, period, and LO."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.uploaded_at")
        filter_frag, extra_params = _build_org_loan_join_filter(
            config.filters, table_alias="sd", loan_alias="l",
        )
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            **extra_params,
        }

        # Summary
        query = f"""
                SELECT
                    COUNT(*) AS total_documents,
                    COUNT(DISTINCT sd.loan_id) AS distinct_loans,
                    COUNT(DISTINCT sd.borrower_id) AS distinct_borrowers,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END)
                        AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END)
                        AS rejected,
                    COUNT(CASE WHEN sd.decision = 'NEEDS_REVIEW' THEN 1 END)
                        AS needs_review,
                    COUNT(CASE WHEN sd.detected_is_screenshot = TRUE THEN 1 END)
                        AS screenshots_detected
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
            """

        summary_row = self.db.execute(
            sa_text(query),
            params,
        ).fetchone()

        summary = {
            "total_documents": summary_row.total_documents or 0,
            "distinct_loans": summary_row.distinct_loans or 0,
            "distinct_borrowers": summary_row.distinct_borrowers or 0,
            "accepted": summary_row.accepted or 0,
            "rejected": summary_row.rejected or 0,
            "needs_review": summary_row.needs_review or 0,
            "screenshots_detected": summary_row.screenshots_detected or 0,
            "acceptance_rate": round(
                _safe_div(summary_row.accepted or 0, summary_row.total_documents or 0) * 100, 1,
            ),
        }

        # By doc type
        query = f"""
                SELECT
                    COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN') AS doc_type,
                    COUNT(*) AS count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN')
                ORDER BY count DESC
            """

        by_type_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data = {
            "by_doc_type": [
                {"doc_type": r.doc_type, "count": r.count}
                for r in by_type_rows
            ],
        }

        # By LO
        query = f"""
                SELECT
                    l.loan_officer_id AS lo_id,
                    CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
                    COUNT(*) AS count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY l.loan_officer_id, u.first_name, u.last_name
                ORDER BY count DESC
            """

        by_lo_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data["by_loan_officer"] = [
            {"lo_id": r.lo_id, "lo_name": r.lo_name, "count": r.count}
            for r in by_lo_rows
        ]

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS count,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejected
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "count": r.count,
                "accepted": r.accepted,
                "rejected": r.rejected,
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_processing_time(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Average processing time by doc type and processor."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.reviewed_at")
        filter_frag, extra_params = _build_org_loan_join_filter(
            config.filters, table_alias="sd", loan_alias="l",
        )
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            **extra_params,
        }

        # Overall summary
        query = f"""
                SELECT
                    COUNT(*) AS total_processed,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_hours,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600
                    ) AS median_hours,
                    PERCENTILE_CONT(0.9) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600
                    ) AS p90_hours,
                    MIN(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS min_hours,
                    MAX(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS max_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.uploaded_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
            """

        summary_row = self.db.execute(
            sa_text(query),
            params,
        ).fetchone()

        summary = {
            "total_processed": summary_row.total_processed or 0,
            "avg_hours": round(float(summary_row.avg_hours or 0), 2),
            "median_hours": round(float(summary_row.median_hours or 0), 2),
            "p90_hours": round(float(summary_row.p90_hours or 0), 2),
            "min_hours": round(float(summary_row.min_hours or 0), 2),
            "max_hours": round(float(summary_row.max_hours or 0), 2),
        }

        # By doc type
        query = f"""
                SELECT
                    COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN') AS doc_type,
                    COUNT(*) AS count,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_hours,
                    PERCENTILE_CONT(0.9) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600
                    ) AS p90_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.uploaded_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN')
                ORDER BY avg_hours DESC
            """

        by_type_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_doc_type": [
                {
                    "doc_type": r.doc_type,
                    "count": r.count,
                    "avg_hours": round(float(r.avg_hours or 0), 2),
                    "p90_hours": round(float(r.p90_hours or 0), 2),
                }
                for r in by_type_rows
            ],
        }

        # By processor (reviewed_by)
        query = f"""
                SELECT
                    sd.reviewed_by AS processor,
                    COUNT(*) AS count,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.uploaded_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY sd.reviewed_by
                ORDER BY count DESC
            """

        by_processor_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data["by_processor"] = [
            {
                "processor": r.processor,
                "count": r.count,
                "avg_hours": round(float(r.avg_hours or 0), 2),
            }
            for r in by_processor_rows
        ]

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS count,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.uploaded_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "count": r.count,
                "avg_hours": round(float(r.avg_hours or 0), 2),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_sla_compliance(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """SLA met/breached rates with trending."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sdr.created_at")
        filter_frag, extra_params = _build_org_loan_join_filter(
            config.filters, table_alias="sdr", loan_alias="l",
        )
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            **extra_params,
        }

        query = f"""
                SELECT
                    COUNT(*) AS total_requests,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND sdr.completed_at IS NOT NULL
                         AND sdr.completed_at <= sdr.sla_due_at
                        THEN 1
                    END) AS sla_met,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND (
                            (sdr.completed_at IS NOT NULL AND sdr.completed_at > sdr.sla_due_at)
                            OR
                            (sdr.completed_at IS NULL AND sdr.sla_due_at < NOW())
                         )
                        THEN 1
                    END) AS sla_breached,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND sdr.completed_at IS NULL
                         AND sdr.sla_due_at >= NOW()
                         AND sdr.sla_due_at < NOW() + INTERVAL '24 hours'
                        THEN 1
                    END) AS sla_at_risk,
                    AVG(CASE
                        WHEN sdr.completed_at IS NOT NULL AND sdr.sla_due_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (sdr.sla_due_at - sdr.completed_at)) / 3600
                    END) AS avg_margin_hours
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
            """


        summary_row = self.db.execute(
            sa_text(query),
            params,
        ).fetchone()

        total = summary_row.total_requests or 0
        met = summary_row.sla_met or 0
        breached = summary_row.sla_breached or 0
        at_risk = summary_row.sla_at_risk or 0

        summary = {
            "total_requests": total,
            "sla_met": met,
            "sla_breached": breached,
            "sla_at_risk": at_risk,
            "met_rate": round(_safe_div(met, total) * 100, 1),
            "breach_rate": round(_safe_div(breached, total) * 100, 1),
            "avg_margin_hours": round(float(summary_row.avg_margin_hours or 0), 1),
        }

        # By doc type
        query = f"""
                SELECT
                    COALESCE(CAST(sdr.doc_type AS TEXT), 'UNKNOWN') AS doc_type,
                    COUNT(*) AS total,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND sdr.completed_at IS NOT NULL
                         AND sdr.completed_at <= sdr.sla_due_at
                        THEN 1
                    END) AS met,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND (
                            (sdr.completed_at IS NOT NULL AND sdr.completed_at > sdr.sla_due_at)
                            OR
                            (sdr.completed_at IS NULL AND sdr.sla_due_at < NOW())
                         )
                        THEN 1
                    END) AS breached
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY COALESCE(CAST(sdr.doc_type AS TEXT), 'UNKNOWN')
                ORDER BY breached DESC
            """

        by_type_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_doc_type": [
                {
                    "doc_type": r.doc_type,
                    "total": r.total,
                    "met": r.met,
                    "breached": r.breached,
                    "met_rate": round(_safe_div(r.met, r.total) * 100, 1),
                }
                for r in by_type_rows
            ],
        }

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS total,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND sdr.completed_at IS NOT NULL
                         AND sdr.completed_at <= sdr.sla_due_at
                        THEN 1
                    END) AS met,
                    COUNT(CASE
                        WHEN sdr.sla_due_at IS NOT NULL
                         AND (
                            (sdr.completed_at IS NOT NULL AND sdr.completed_at > sdr.sla_due_at)
                            OR
                            (sdr.completed_at IS NULL AND sdr.sla_due_at < NOW())
                         )
                        THEN 1
                    END) AS breached
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "total": r.total,
                "met": r.met,
                "breached": r.breached,
                "met_rate": round(_safe_div(r.met, r.total) * 100, 1),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_income_accuracy(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """AI vs manual income calculation accuracy."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.reviewed_at")
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        # Compare AI-extracted amounts vs manually-entered amounts
        # where both exist on the same document
        summary_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_compared,
                    COUNT(CASE
                        WHEN sd.extracted_amount IS NOT NULL
                         AND sd.extraction_confidence >= 0.9
                        THEN 1
                    END) AS high_confidence,
                    AVG(sd.extraction_confidence) AS avg_confidence,
                    COUNT(CASE
                        WHEN sd.detected_doc_type IS NOT NULL
                         AND sd.doc_type IS NOT NULL
                         AND sd.detected_doc_type = CAST(sd.doc_type AS TEXT)
                        THEN 1
                    END) AS type_match,
                    COUNT(CASE
                        WHEN sd.detected_doc_type IS NOT NULL
                         AND sd.doc_type IS NOT NULL
                         AND sd.detected_doc_type != CAST(sd.doc_type AS TEXT)
                        THEN 1
                    END) AS type_mismatch
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.extracted_amount IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_compared = summary_row.total_compared or 0
        high_confidence = summary_row.high_confidence or 0
        type_match = summary_row.type_match or 0
        type_mismatch = summary_row.type_mismatch or 0

        summary = {
            "total_compared": total_compared,
            "high_confidence_count": high_confidence,
            "high_confidence_rate": round(
                _safe_div(high_confidence, total_compared) * 100, 1,
            ),
            "avg_confidence": round(float(summary_row.avg_confidence or 0), 3),
            "type_accuracy_rate": round(
                _safe_div(type_match, type_match + type_mismatch) * 100, 1,
            ),
        }

        # By doc type accuracy breakdown
        by_type_rows = self.db.execute(
            sa_text("""
                SELECT
                    COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN') AS doc_type,
                    COUNT(*) AS count,
                    AVG(sd.extraction_confidence) AS avg_confidence,
                    COUNT(CASE
                        WHEN sd.extraction_confidence >= 0.9 THEN 1
                    END) AS high_conf_count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.extracted_amount IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                GROUP BY COALESCE(CAST(sd.doc_type AS TEXT), 'UNKNOWN')
                ORDER BY count DESC
            """),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_doc_type": [
                {
                    "doc_type": r.doc_type,
                    "count": r.count,
                    "avg_confidence": round(float(r.avg_confidence or 0), 3),
                    "high_confidence_rate": round(
                        _safe_div(r.high_conf_count, r.count) * 100, 1,
                    ),
                }
                for r in by_type_rows
            ],
        }

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS count,
                    AVG(sd.extraction_confidence) AS avg_confidence
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.extracted_amount IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "count": r.count,
                "avg_confidence": round(float(r.avg_confidence or 0), 3),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_fraud_detection(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Fraud alerts by type and resolution rates."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.uploaded_at")
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        # Screenshot-based fraud detection from smart_documents
        summary_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_documents,
                    COUNT(CASE WHEN sd.detected_is_screenshot = TRUE THEN 1 END)
                        AS screenshot_flags,
                    COUNT(CASE
                        WHEN sd.rejection_category = 'SCREENSHOT' THEN 1
                    END) AS screenshot_rejections,
                    COUNT(CASE
                        WHEN sd.rejection_category IS NOT NULL THEN 1
                    END) AS total_rejections,
                    AVG(CASE
                        WHEN sd.detected_is_screenshot = TRUE
                        THEN sd.screenshot_confidence
                    END) AS avg_screenshot_confidence
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_docs = summary_row.total_documents or 0
        screenshot_flags = summary_row.screenshot_flags or 0
        screenshot_rejections = summary_row.screenshot_rejections or 0

        summary = {
            "total_documents": total_docs,
            "screenshot_flags": screenshot_flags,
            "screenshot_flag_rate": round(
                _safe_div(screenshot_flags, total_docs) * 100, 2,
            ),
            "screenshot_rejections": screenshot_rejections,
            "total_rejections": summary_row.total_rejections or 0,
            "avg_screenshot_confidence": round(
                float(summary_row.avg_screenshot_confidence or 0), 3,
            ),
        }

        # By rejection category
        by_category_rows = self.db.execute(
            sa_text("""
                SELECT
                    COALESCE(CAST(sd.rejection_category AS TEXT), 'NONE') AS category,
                    COUNT(*) AS count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.rejection_category IS NOT NULL
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                GROUP BY COALESCE(CAST(sd.rejection_category AS TEXT), 'NONE')
                ORDER BY count DESC
            """),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_rejection_category": [
                {"category": r.category, "count": r.count}
                for r in by_category_rows
            ],
        }

        # Doc-policy fraud-related events
        fraud_events = self.db.execute(
            sa_text("""
                SELECT
                    CAST(dpe.event_type AS TEXT) AS event_type,
                    COUNT(*) AS count
                FROM doc_policy_events dpe
                JOIN loans l ON l.id = dpe.loan_id
                WHERE l.organization_id = :org_id
                  AND dpe.event_type IN ('SCREENSHOT_REJECTED', 'FRESHNESS_REJECTED')
                  AND dpe.created_at >= :start_date
                  AND dpe.created_at <= :end_date + INTERVAL '1 day'
                GROUP BY dpe.event_type
                ORDER BY count DESC
            """),
            params,
        ).fetchall()

        data["policy_events"] = [
            {"event_type": r.event_type, "count": r.count}
            for r in fraud_events
        ]

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS total,
                    COUNT(CASE WHEN sd.detected_is_screenshot = TRUE THEN 1 END)
                        AS flagged
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "total": r.total,
                "flagged": r.flagged,
                "flag_rate": round(_safe_div(r.flagged, r.total) * 100, 2),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_borrower_engagement(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Portal usage, upload patterns, and response rates."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.uploaded_at")
        filter_frag, extra_params = _build_org_loan_join_filter(
            config.filters, table_alias="sd", loan_alias="l",
        )
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            **extra_params,
        }

        # Upload source distribution
        query = f"""
                SELECT
                    COUNT(*) AS total_uploads,
                    COUNT(DISTINCT sd.borrower_id) AS unique_borrowers,
                    COUNT(CASE WHEN sd.upload_source = 'WEB' THEN 1 END) AS web,
                    COUNT(CASE WHEN sd.upload_source = 'MOBILE' THEN 1 END) AS mobile,
                    COUNT(CASE WHEN sd.upload_source = 'EMAIL' THEN 1 END) AS email,
                    AVG(sd.file_size) AS avg_file_size
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
            """

        summary_row = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        sr = summary_row[0] if summary_row else None
        total_uploads = sr.total_uploads if sr else 0
        unique_borrowers = sr.unique_borrowers if sr else 0

        summary = {
            "total_uploads": total_uploads or 0,
            "unique_borrowers": unique_borrowers or 0,
            "uploads_per_borrower": round(
                _safe_div(total_uploads or 0, unique_borrowers or 0), 1,
            ),
            "web_uploads": sr.web if sr else 0,
            "mobile_uploads": sr.mobile if sr else 0,
            "email_uploads": sr.email if sr else 0,
            "avg_file_size_kb": round(float(sr.avg_file_size or 0) / 1024, 1)
            if sr
            else 0,
        }

        # Response time: time between request creation and first upload
        query = f"""
                SELECT
                    AVG(
                        EXTRACT(EPOCH FROM (
                            (SELECT MIN(sd2.uploaded_at)
                             FROM smart_documents sd2
                             WHERE sd2.request_id = sdr.id)
                            - sdr.created_at
                        )) / 3600
                    ) AS avg_response_hours,
                    COUNT(*) AS requests_with_uploads
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.status IN ('ACCEPTED', 'PENDING_REVIEW')
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  AND EXISTS (
                      SELECT 1 FROM smart_documents sd2
                      WHERE sd2.request_id = sdr.id
                  )
            """

        response = self.db.execute(
            sa_text(query),
            params,
        ).fetchone()

        data: Dict[str, Any] = {
            "upload_channels": {
                "web_pct": round(
                    _safe_div(summary["web_uploads"], total_uploads or 0) * 100, 1,
                ),
                "mobile_pct": round(
                    _safe_div(summary["mobile_uploads"], total_uploads or 0) * 100, 1,
                ),
                "email_pct": round(
                    _safe_div(summary["email_uploads"], total_uploads or 0) * 100, 1,
                ),
            },
            "avg_response_hours": round(
                float(response.avg_response_hours or 0), 1,
            ),
            "requests_with_uploads": response.requests_with_uploads or 0,
        }

        # Time series: uploads per period
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS uploads,
                    COUNT(DISTINCT sd.borrower_id) AS unique_borrowers
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "uploads": r.uploads,
                "unique_borrowers": r.unique_borrowers,
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_condition_tracking(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Outstanding conditions, clearance rates, and aging."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sdr.created_at")
        filter_frag, extra_params = _build_org_loan_join_filter(
            config.filters, table_alias="sdr", loan_alias="l",
        )
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            **extra_params,
        }

        query = f"""
                SELECT
                    COUNT(*) AS total_conditions,
                    COUNT(CASE WHEN sdr.status = 'OPEN' THEN 1 END) AS open,
                    COUNT(CASE WHEN sdr.status = 'PENDING_REVIEW' THEN 1 END)
                        AS pending_review,
                    COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END)
                        AS cleared,
                    COUNT(CASE WHEN sdr.status = 'REJECTED' THEN 1 END)
                        AS rejected,
                    COUNT(CASE WHEN sdr.status = 'WAIVED' THEN 1 END)
                        AS waived,
                    AVG(CASE
                        WHEN sdr.completed_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (sdr.completed_at - sdr.created_at)) / 3600
                    END) AS avg_clearance_hours
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
            """


        summary_row = self.db.execute(
            sa_text(query),
            params,
        ).fetchone()

        total = summary_row.total_conditions or 0
        cleared = summary_row.cleared or 0

        summary = {
            "total_conditions": total,
            "open": summary_row.open or 0,
            "pending_review": summary_row.pending_review or 0,
            "cleared": cleared,
            "rejected": summary_row.rejected or 0,
            "waived": summary_row.waived or 0,
            "clearance_rate": round(_safe_div(cleared, total) * 100, 1),
            "avg_clearance_hours": round(
                float(summary_row.avg_clearance_hours or 0), 1,
            ),
        }

        # By priority
        query = f"""
                SELECT
                    COALESCE(CAST(sdr.priority AS TEXT), 'NORMAL') AS priority,
                    COUNT(*) AS total,
                    COUNT(CASE WHEN sdr.status = 'OPEN' THEN 1 END) AS open,
                    COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END) AS cleared
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY COALESCE(CAST(sdr.priority AS TEXT), 'NORMAL')
                ORDER BY total DESC
            """

        by_priority_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        data: Dict[str, Any] = {
            "by_priority": [
                {
                    "priority": r.priority,
                    "total": r.total,
                    "open": r.open,
                    "cleared": r.cleared,
                    "clearance_rate": round(_safe_div(r.cleared, r.total) * 100, 1),
                }
                for r in by_priority_rows
            ],
        }

        # Aging — open conditions grouped by age bucket
        query = f"""
                SELECT
                    CASE
                        WHEN EXTRACT(EPOCH FROM (NOW() - sdr.created_at)) / 86400 <= 3
                            THEN '0-3 days'
                        WHEN EXTRACT(EPOCH FROM (NOW() - sdr.created_at)) / 86400 <= 7
                            THEN '4-7 days'
                        WHEN EXTRACT(EPOCH FROM (NOW() - sdr.created_at)) / 86400 <= 14
                            THEN '8-14 days'
                        ELSE '15+ days'
                    END AS age_bucket,
                    COUNT(*) AS count
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.status IN ('OPEN', 'PENDING_REVIEW')
                  AND sdr.is_active = TRUE
                  {filter_frag}
                GROUP BY age_bucket
                ORDER BY MIN(EXTRACT(EPOCH FROM (NOW() - sdr.created_at)))
            """

        aging_rows = self.db.execute(
            sa_text(query),
            {
                "org_id": self.org_id,
                **extra_params,
            },
        ).fetchall()

        data["aging"] = [
            {"bucket": r.age_bucket, "count": r.count}
            for r in aging_rows
        ]

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS created,
                    COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END) AS cleared
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  {filter_frag}
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "created": r.created,
                "cleared": r.cleared,
                "clearance_rate": round(_safe_div(r.cleared, r.created) * 100, 1),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_compliance_audit(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Disclosure timing, consent tracking, and retention compliance."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "l.application_date")
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        # Disclosure timing — LE within 3 days of application
        disclosure_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_loans,
                    COUNT(CASE
                        WHEN l.initial_disclosures_sent_date IS NOT NULL
                         AND l.application_date IS NOT NULL
                         AND (l.initial_disclosures_sent_date - l.application_date) <= 3
                        THEN 1
                    END) AS le_on_time,
                    COUNT(CASE
                        WHEN l.initial_disclosures_sent_date IS NOT NULL
                         AND l.application_date IS NOT NULL
                         AND (l.initial_disclosures_sent_date - l.application_date) > 3
                        THEN 1
                    END) AS le_late,
                    COUNT(CASE
                        WHEN l.application_date IS NOT NULL
                         AND l.initial_disclosures_sent_date IS NULL
                        THEN 1
                    END) AS le_missing,
                    COUNT(CASE
                        WHEN l.cd_sent_to_borrower_date IS NOT NULL
                         AND l.funded_date IS NOT NULL
                         AND (l.funded_date - l.cd_sent_to_borrower_date) >= 3
                        THEN 1
                    END) AS cd_on_time,
                    COUNT(CASE
                        WHEN l.cd_sent_to_borrower_date IS NOT NULL
                         AND l.funded_date IS NOT NULL
                         AND (l.funded_date - l.cd_sent_to_borrower_date) < 3
                        THEN 1
                    END) AS cd_violation
                FROM loans l
                WHERE l.organization_id = :org_id
                  AND l.application_date >= :start_date
                  AND l.application_date <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        total_loans = disclosure_row.total_loans or 0
        le_on_time = disclosure_row.le_on_time or 0
        le_late = disclosure_row.le_late or 0

        summary = {
            "total_loans": total_loans,
            "le_on_time": le_on_time,
            "le_late": le_late,
            "le_missing": disclosure_row.le_missing or 0,
            "le_compliance_rate": round(
                _safe_div(le_on_time, le_on_time + le_late) * 100, 1,
            ),
            "cd_on_time": disclosure_row.cd_on_time or 0,
            "cd_violation": disclosure_row.cd_violation or 0,
        }

        # Document retention — count of expired documents still active
        retention_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_docs,
                    COUNT(CASE WHEN sd.is_expired = TRUE THEN 1 END) AS expired_docs,
                    COUNT(CASE
                        WHEN sd.doc_expires_at IS NOT NULL
                         AND sd.doc_expires_at < NOW()
                         AND sd.is_expired = FALSE
                        THEN 1
                    END) AS not_marked_expired
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.uploaded_at >= :start_date
                  AND sd.uploaded_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        data: Dict[str, Any] = {
            "retention": {
                "total_docs": retention_row.total_docs or 0,
                "expired_docs": retention_row.expired_docs or 0,
                "not_marked_expired": retention_row.not_marked_expired or 0,
            },
        }

        # Compliance alerts within period
        alerts_row = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) AS total_alerts,
                    COUNT(CASE WHEN ca.status = 'open' THEN 1 END) AS open_alerts,
                    COUNT(CASE WHEN ca.severity = 'critical' THEN 1 END)
                        AS critical_alerts
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id
                WHERE l.organization_id = :org_id
                  AND ca.created_at >= :start_date
                  AND ca.created_at <= :end_date + INTERVAL '1 day'
            """),
            params,
        ).fetchone()

        data["compliance_alerts"] = {
            "total": alerts_row.total_alerts or 0,
            "open": alerts_row.open_alerts or 0,
            "critical": alerts_row.critical_alerts or 0,
        }

        # Time series
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS loans,
                    COUNT(CASE
                        WHEN l.initial_disclosures_sent_date IS NOT NULL
                         AND l.application_date IS NOT NULL
                         AND (l.initial_disclosures_sent_date - l.application_date) <= 3
                        THEN 1
                    END) AS le_compliant
                FROM loans l
                WHERE l.organization_id = :org_id
                  AND l.application_date >= :start_date
                  AND l.application_date <= :end_date + INTERVAL '1 day'
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "loans": r.loans,
                "le_compliant": r.le_compliant,
                "compliance_rate": round(
                    _safe_div(r.le_compliant, r.loans) * 100, 1,
                ),
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_team_productivity(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """Per-user metrics, workload distribution, and efficiency."""
        dr = config.date_range
        grp_expr = _group_by_expression(config.group_by, "sd.reviewed_at")
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        # Per-user doc review metrics
        user_rows = self.db.execute(
            sa_text("""
                SELECT
                    sd.reviewed_by AS user_id,
                    COUNT(*) AS docs_reviewed,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejected,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600)
                        AS avg_review_hours,
                    COUNT(DISTINCT sd.loan_id) AS distinct_loans
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_by IS NOT NULL
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                GROUP BY sd.reviewed_by
                ORDER BY docs_reviewed DESC
            """),
            params,
        ).fetchall()

        total_reviewed = sum(r.docs_reviewed for r in user_rows) if user_rows else 0
        total_accepted = sum(r.accepted for r in user_rows) if user_rows else 0

        summary = {
            "total_team_members": len(user_rows),
            "total_documents_reviewed": total_reviewed,
            "total_accepted": total_accepted,
            "overall_acceptance_rate": round(
                _safe_div(total_accepted, total_reviewed) * 100, 1,
            ),
            "avg_docs_per_person": round(
                _safe_div(total_reviewed, len(user_rows) if user_rows else 0), 1,
            ),
        }

        span_days = max(dr.span_days, 1)
        data: Dict[str, Any] = {
            "by_team_member": [
                {
                    "user_id": r.user_id,
                    "docs_reviewed": r.docs_reviewed,
                    "accepted": r.accepted,
                    "rejected": r.rejected,
                    "acceptance_rate": round(
                        _safe_div(r.accepted, r.docs_reviewed) * 100, 1,
                    ),
                    "avg_review_hours": round(float(r.avg_review_hours or 0), 2),
                    "distinct_loans": r.distinct_loans,
                    "docs_per_day": round(
                        _safe_div(r.docs_reviewed, span_days), 2,
                    ),
                    "workload_pct": round(
                        _safe_div(r.docs_reviewed, total_reviewed) * 100, 1,
                    ),
                }
                for r in user_rows
            ],
        }

        # Workload distribution (Gini-like measure)
        if user_rows:
            counts = sorted([r.docs_reviewed for r in user_rows])
            n = len(counts)
            if n > 1:
                mean_val = statistics.mean(counts)
                if mean_val > 0:
                    abs_diffs = sum(
                        abs(counts[i] - counts[j])
                        for i in range(n) for j in range(i + 1, n)
                    )
                    gini = abs_diffs / (n * n * mean_val)
                else:
                    gini = 0.0
            else:
                gini = 0.0
            data["workload_gini"] = round(gini, 3)
        else:
            data["workload_gini"] = 0.0

        # Time series: total reviewed per period
        query = f"""
                SELECT
                    {grp_expr} AS period,
                    COUNT(*) AS reviewed,
                    COUNT(DISTINCT sd.reviewed_by) AS active_reviewers
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE l.organization_id = :org_id
                  AND sd.reviewed_by IS NOT NULL
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.reviewed_at >= :start_date
                  AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
                GROUP BY {grp_expr}
                ORDER BY period
            """

        series_rows = self.db.execute(
            sa_text(query),
            params,
        ).fetchall()

        series = [
            {
                "period": r.period.isoformat() if r.period else None,
                "reviewed": r.reviewed,
                "active_reviewers": r.active_reviewers,
            }
            for r in series_rows
        ]

        return data, summary, series

    async def _report_executive_summary(
        self, config: ReportConfig,
    ) -> Tuple[Dict, Dict, List]:
        """High-level KPIs for leadership.

        Combines document volume, SLA, processing time, and fraud metrics
        into a single summary with trend analysis.
        """
        # Use the KPI dashboard to populate the executive summary
        kpi = await self.get_kpi_dashboard(config.date_range)

        # Get volume time series for the sparkline
        vol_data, vol_summary, vol_series = await self._report_document_volume(config)

        # Get SLA data for the summary
        sla_data, sla_summary, sla_series = await self._report_sla_compliance(config)

        summary = {
            "document_collection_rate": kpi.kpis["document_collection_rate"],
            "first_pass_approval_rate": kpi.kpis["first_pass_approval_rate"],
            "avg_time_to_complete_hours": kpi.kpis["avg_time_to_complete_hours"],
            "ai_accuracy_rate": kpi.kpis["ai_accuracy_rate"],
            "total_documents": vol_summary.get("total_documents", 0),
            "sla_met_rate": sla_summary.get("met_rate", 0),
            "sla_breached": sla_summary.get("sla_breached", 0),
            "active_borrowers": kpi.kpis["active_borrowers"],
        }

        data: Dict[str, Any] = {
            "kpis": kpi.kpis,
            "trends": kpi.trends,
            "alerts": kpi.alerts,
            "volume_by_type": vol_data.get("by_doc_type", [])[:5],
            "sla_by_type": sla_data.get("by_doc_type", [])[:5],
        }

        # Use volume series as the executive time-series
        series = vol_series

        return data, summary, series

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


# =============================================================================
# FACTORY
# =============================================================================

def get_report_builder_service(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
) -> ReportBuilderService:
    """Create a :class:`ReportBuilderService` instance.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID for tenant isolation.
        user_id: Optional authenticated user ID.

    Returns:
        A configured :class:`ReportBuilderService`.
    """
    return ReportBuilderService(db=db, org_id=org_id, user_id=user_id)
