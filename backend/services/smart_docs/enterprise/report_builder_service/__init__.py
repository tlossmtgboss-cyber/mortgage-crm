"""
Smart Docs Enterprise Report Builder Service

Generates operational, compliance, and executive reports for Smart Docs
operations.

This package is a mechanically decomposed re-arrangement of what was
previously a single ~2,800 line ``report_builder_service.py`` module.
Public API is preserved verbatim — importers continue to use:

    from services.smart_docs.enterprise.report_builder_service import (
        ReportBuilderService,
        get_report_builder_service,
        ReportType,
        ReportConfig,
        ...
    )

Internal implementation is split into per-domain mixins under
``report_builder_service.mixins``. The ``ReportBuilderService`` class is
composed by inheriting from all mixins (mechanical move, no behavioral
change).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

# Re-export everything that was previously module-level so existing
# importers continue to work.
from ._shared import (  # noqa: F401
    # enums
    ReportType,
    GroupBy,
    ExportFormat,
    ScheduleFrequency,
    UserRole,
    # dataclasses
    DateRange,
    ReportFilter,
    ReportConfig,
    ReportInfo,
    ReportResult,
    KPIDashboard,
    ComparisonResult,
    ReportTemplate,
    ScheduleResult,
    # catalog + helpers
    _REPORT_CATALOG,
    _ROLE_REPORT_ACCESS,
    _group_by_expression,
    _build_org_loan_join_filter,
    _safe_div,
    _pct_change,
)

from .mixins.catalog import CatalogMixin
from .mixins.compare import CompareMixin
from .mixins.comparison import ComparisonMixin
from .mixins.export import ExportMixin
from .mixins.formatters import FormattersMixin
from .mixins.generation import GenerationMixin
from .mixins.kpi import KPIMixin
from .mixins.reports_part1 import ReportsPart1Mixin
from .mixins.reports_part2 import ReportsPart2Mixin
from .mixins.schedule_helpers import ScheduleHelpersMixin
from .mixins.schedules import SchedulesMixin
from .mixins.templates import TemplatesMixin

logger = logging.getLogger(__name__)


# =============================================================================
# REPORT BUILDER SERVICE — Composed from mixins
# =============================================================================

class ReportBuilderService(
    GenerationMixin,
    CatalogMixin,
    TemplatesMixin,
    SchedulesMixin,
    ExportMixin,
    KPIMixin,
    CompareMixin,
    ReportsPart1Mixin,
    ReportsPart2Mixin,
    ComparisonMixin,
    FormattersMixin,
    ScheduleHelpersMixin,
):
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


__all__ = [
    "ReportBuilderService",
    "get_report_builder_service",
    "ReportType",
    "GroupBy",
    "ExportFormat",
    "ScheduleFrequency",
    "UserRole",
    "DateRange",
    "ReportFilter",
    "ReportConfig",
    "ReportInfo",
    "ReportResult",
    "KPIDashboard",
    "ComparisonResult",
    "ReportTemplate",
    "ScheduleResult",
]
