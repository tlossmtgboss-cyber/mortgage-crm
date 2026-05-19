"""
Commission Income Calculation Service for Mortgage Qualification

Calculates qualifying commission-based income per Fannie Mae Selling Guide
(Chapter B3-3.1) and Freddie Mac guidelines.

This package is a mechanically decomposed re-arrangement of what was
previously a single ~2,900 line ``commission_income_service.py`` module.
Public API is preserved verbatim — importers continue to use:

    from services.smart_docs.income.commission_income_service import (
        get_commission_income_service,
        CommissionIncomeService,
        CommissionIncomeResult,
        CommissionSource,
        TrendAnalysis,
        ExpenseAnalysis,
        EligibilityResult,
        CalculationMethod,
        CommissionType,
        TrendDirection,
    )

Internal implementation is split into per-domain mixins under
``commission_income_service.mixins``. The ``CommissionIncomeService`` class
is composed by inheriting from all mixins (mechanical move, no behavioral
change).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

# Re-export shared types / constants so existing imports keep working.
from ._shared import (  # noqa: F401
    # constants
    ZERO,
    TWO_PLACES,
    FOUR_PLACES,
    ONE_HUNDRED,
    COMMISSION_SIGNIFICANCE_THRESHOLD_PCT,
    HISTORY_YEARS_REQUIRED,
    HISTORY_YEARS_MINIMUM,
    DECLINE_WARNING_PCT,
    DECLINE_CRITICAL_PCT,
    DECLINE_SEVERE_PCT,
    EMPLOYMENT_GAP_THRESHOLD_DAYS,
    UBE_DEDUCTION_THRESHOLD_PCT,
    PAY_FREQUENCY_MULTIPLIERS,
    COMMISSION_DOC_TYPES,
    MONTHS_PER_YEAR,
    MONTHS_PER_TWO_YEARS,
    # enums
    CalculationMethod,
    CommissionType,
    TrendDirection,
    # dataclasses
    TrendAnalysis,
    ExpenseAnalysis,
    EligibilityResult,
    CommissionSource,
    CommissionIncomeResult,
    # module helpers
    _to_decimal,
    _safe_int,
    _parse_date,
    _months_elapsed_in_year,
    _now_ms,
    _audit,
)

from .mixins.aggregates import AggregatesMixin
from .mixins.calculation import CalculationMixin
from .mixins.documents import DocumentsMixin
from .mixins.eligibility import EligibilityMixin
from .mixins.expenses import ExpensesMixin
from .mixins.generation import GenerationMixin
from .mixins.main_flow import MainFlowMixin
from .mixins.overrides import OverridesMixin
from .mixins.persistence import PersistenceMixin
from .mixins.trending import TrendingMixin

logger = logging.getLogger(__name__)


# =============================================================================
# SERVICE — Composed from mixins
# =============================================================================

class CommissionIncomeService(
    MainFlowMixin,
    TrendingMixin,
    ExpensesMixin,
    EligibilityMixin,
    OverridesMixin,
    DocumentsMixin,
    CalculationMixin,
    AggregatesMixin,
    GenerationMixin,
    PersistenceMixin,
):
    """
    Commission income calculation service for mortgage qualification.

    Implements Fannie Mae Selling Guide B3-3.1 and Freddie Mac requirements
    for commission-based income analysis. Handles W-2 commission earners,
    1099 independent contractors, and Schedule C self-employed agents.

    Key guideline points implemented:
    - Commission > 25% of total income requires 2-year history
    - 1-year exception allowed if stable/increasing and same employer >= 12 months
    - Declining income: use lower of 2-year average or most recent 12 months
    - Unreimbursed business expenses > 25% of income must be deducted
    - Employment gaps > 6 months require additional documentation

    All monetary calculations use Decimal arithmetic to avoid floating-point
    rounding errors in financial computations.
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_commission_income_service(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
) -> CommissionIncomeService:
    """
    Factory function returning a CommissionIncomeService for the given
    session and org context.

    Args:
        db: SQLAlchemy session for the current request.
        org_id: Organization ID for tenant isolation.
        user_id: Optional authenticated user ID.

    Returns:
        A configured CommissionIncomeService instance.
    """
    return CommissionIncomeService(db=db, org_id=org_id, user_id=user_id)


__all__ = [
    # service
    "CommissionIncomeService",
    "get_commission_income_service",
    # enums
    "CalculationMethod",
    "CommissionType",
    "TrendDirection",
    # dataclasses
    "TrendAnalysis",
    "ExpenseAnalysis",
    "EligibilityResult",
    "CommissionSource",
    "CommissionIncomeResult",
]
