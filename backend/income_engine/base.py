"""
Base Engine Class for Income Intelligence Engine

All income calculation engines inherit from this base class.
Provides standardized calculation flow, flag generation, and audit trail.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
import logging

from .data_contracts import (
    IncomeStreamType,
    FlagSeverity,
    TrendDirection,
    IncomeStreamResult,
    CalculationFlag,
)

logger = logging.getLogger(__name__)


# =============================================================================
# FLAG RULE IDs (Standard across all engines)
# =============================================================================

class FlagRuleId:
    """Standard flag rule IDs used across all engines."""

    # General
    MISSING_REQUIRED_DOCUMENT = "MISSING_REQUIRED_DOCUMENT"
    DOCUMENT_EXPIRED = "DOCUMENT_EXPIRED"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"

    # W-2 / Paystub
    W2_VARIABLE_INCOME_DECLINING = "W2_VARIABLE_INCOME_DECLINING"
    W2_NO_DOCUMENTED_HOURS = "W2_NO_DOCUMENTED_HOURS"
    W2_INSUFFICIENT_HISTORY = "W2_INSUFFICIENT_HISTORY"
    W2_YTD_MISMATCH = "W2_YTD_MISMATCH"
    PAYSTUB_FREQUENCY_UNCLEAR = "PAYSTUB_FREQUENCY_UNCLEAR"

    # Schedule C
    SCHEDULE_C_LOSS = "SCHEDULE_C_LOSS"
    SCHEDULE_C_INCOME_DECLINING = "SCHEDULE_C_INCOME_DECLINING"
    MILEAGE_RATE_NOT_CONFIGURED = "MILEAGE_RATE_NOT_CONFIGURED"
    HOME_OFFICE_DEDUCTION = "HOME_OFFICE_DEDUCTION"
    SCHEDULE_C_ONLY_ONE_YEAR = "SCHEDULE_C_ONLY_ONE_YEAR"

    # Schedule E / Rental
    RENTAL_LOSS = "RENTAL_LOSS"
    RENTAL_INCOME_DECLINING = "RENTAL_INCOME_DECLINING"
    RENTAL_NO_SCHEDULE_E = "RENTAL_NO_SCHEDULE_E"
    RENTAL_VACANCY_WARNING = "RENTAL_VACANCY_WARNING"

    # K-1
    K1_NO_DISTRIBUTIONS_OR_LIQUIDITY = "K1_NO_DISTRIBUTIONS_OR_LIQUIDITY"
    K1_OWNERSHIP_BELOW_25 = "K1_OWNERSHIP_BELOW_25"
    K1_INCOME_DECLINING = "K1_INCOME_DECLINING"
    CCORP_NOT_100_PERCENT = "CCORP_NOT_100_PERCENT"
    K1_ONLY_ONE_YEAR = "K1_ONLY_ONE_YEAR"

    # Bank Statement
    BANK_12MO_DECLINE_REQUIRES_24MO = "BANK_12MO_DECLINE_REQUIRES_24MO"
    BANK_24MO_DECLINE_EXPLANATION = "BANK_24MO_DECLINE_EXPLANATION"
    BANK_24MO_DECLINE_INELIGIBLE = "BANK_24MO_DECLINE_INELIGIBLE"
    BANK_INSUFFICIENT_MONTHS = "BANK_INSUFFICIENT_MONTHS"
    BANK_NSF_WARNING = "BANK_NSF_WARNING"
    BANK_LARGE_DEPOSIT_UNEXPLAINED = "BANK_LARGE_DEPOSIT_UNEXPLAINED"


# =============================================================================
# ENGINE RESULT DATACLASS
# =============================================================================

@dataclass
class IncomeStream:
    """Single income stream from a calculation engine."""
    stream_type: IncomeStreamType
    stream_name: str
    monthly_income: Decimal
    annual_income: Decimal

    # Audit trail
    calculation_inputs: Dict[str, Any] = field(default_factory=dict)
    calculation_steps: List[Dict[str, Any]] = field(default_factory=list)
    add_backs: Dict[str, Decimal] = field(default_factory=dict)
    subtractions: Dict[str, Decimal] = field(default_factory=dict)

    # Source tracking
    document_ids: List[str] = field(default_factory=list)
    tax_years: List[int] = field(default_factory=list)

    # Trending analysis
    trending_direction: Optional[TrendDirection] = None
    trending_percentage: Optional[Decimal] = None
    year1_income: Optional[Decimal] = None
    year2_income: Optional[Decimal] = None
    uses_lower_year: bool = False


@dataclass
class IncomeFlag:
    """Flag generated during calculation."""
    rule_id: str
    severity: FlagSeverity
    message: str
    required_action: Optional[str] = None
    affected_stream: Optional[str] = None
    affected_document_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_create_condition: bool = False


@dataclass
class EngineResult:
    """Result from a calculation engine."""
    engine_name: str
    engine_version: str
    success: bool

    # Income streams calculated
    income_streams: List[IncomeStream] = field(default_factory=list)

    # Flags generated
    flags: List[IncomeFlag] = field(default_factory=list)

    # Total from this engine
    total_monthly_income: Decimal = Decimal("0")

    # Metadata
    calculation_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None


# =============================================================================
# BASE ENGINE CLASS
# =============================================================================

class BaseIncomeEngine(ABC):
    """
    Abstract base class for all income calculation engines.

    Each engine:
    1. Takes standardized DocumentFacts as input
    2. Performs calculations following agency guidelines
    3. Returns EngineResult with income streams and flags
    4. Maintains complete audit trail
    """

    ENGINE_NAME: str = "BaseEngine"
    ENGINE_VERSION: str = "1.0"

    def __init__(self, db_session=None):
        """
        Initialize engine with optional database session.

        Args:
            db_session: SQLAlchemy session for lookups (mileage rates, etc.)
        """
        self.db = db_session
        self._mileage_rates_cache: Dict[int, Decimal] = {}

    # -------------------------------------------------------------------------
    # Abstract Methods (must be implemented by subclasses)
    # -------------------------------------------------------------------------

    @abstractmethod
    def calculate(self, *args, **kwargs) -> EngineResult:
        """
        Perform income calculation.

        Returns:
            EngineResult with calculated income streams and flags
        """
        pass

    @abstractmethod
    def get_supported_stream_types(self) -> List[IncomeStreamType]:
        """Return list of income stream types this engine handles."""
        pass

    # -------------------------------------------------------------------------
    # Common Calculation Helpers
    # -------------------------------------------------------------------------

    def round_currency(self, amount: Decimal, decimals: int = 2) -> Decimal:
        """Round currency to specified decimal places."""
        if amount is None:
            return Decimal("0")
        return Decimal(str(amount)).quantize(
            Decimal(10) ** -decimals,
            rounding=ROUND_HALF_UP
        )

    def annual_to_monthly(self, annual: Decimal) -> Decimal:
        """Convert annual income to monthly."""
        return self.round_currency(annual / 12)

    def monthly_to_annual(self, monthly: Decimal) -> Decimal:
        """Convert monthly income to annual."""
        return self.round_currency(monthly * 12)

    def calculate_two_year_average(
        self,
        year1_income: Decimal,
        year2_income: Decimal
    ) -> Tuple[Decimal, TrendDirection, Decimal, bool]:
        """
        Calculate two-year average with trending analysis.

        Per agency guidelines:
        - If declining, use lower of the two years (most recent)
        - Calculate trending percentage

        Args:
            year1_income: Most recent year income
            year2_income: Prior year income

        Returns:
            Tuple of (average_income, trend_direction, trend_percentage, uses_lower_year)
        """
        if year1_income is None or year2_income is None:
            return Decimal("0"), TrendDirection.STABLE, Decimal("0"), False

        year1 = Decimal(str(year1_income))
        year2 = Decimal(str(year2_income))

        # Calculate average
        average = (year1 + year2) / 2

        # Determine trending
        if year2 > 0:
            trend_pct = ((year1 - year2) / year2) * 100
        else:
            trend_pct = Decimal("100") if year1 > 0 else Decimal("0")

        # Determine direction
        if trend_pct > Decimal("5"):
            direction = TrendDirection.INCREASING
        elif trend_pct < Decimal("-5"):
            direction = TrendDirection.DECLINING
        else:
            direction = TrendDirection.STABLE

        # If declining, use lower year (most recent)
        uses_lower = direction == TrendDirection.DECLINING
        if uses_lower:
            final_income = min(year1, year2)
        else:
            final_income = average

        return (
            self.round_currency(final_income),
            direction,
            self.round_currency(trend_pct),
            uses_lower
        )

    def get_mileage_rate(self, tax_year: int) -> Optional[Decimal]:
        """
        Get IRS mileage depreciation rate for a tax year.

        Returns None if not configured (should trigger BLOCKING flag).
        """
        # Check cache first
        if tax_year in self._mileage_rates_cache:
            return self._mileage_rates_cache[tax_year]

        if not self.db:
            return None

        try:
            from models.income_engine_models import MileageDepreciationRate

            rate = self.db.query(MileageDepreciationRate).filter(
                MileageDepreciationRate.tax_year == tax_year
            ).first()

            if rate:
                self._mileage_rates_cache[tax_year] = Decimal(str(rate.rate_per_mile))
                return self._mileage_rates_cache[tax_year]
        except Exception as e:
            logger.warning(f"Error fetching mileage rate for {tax_year}: {e}")

        return None

    # -------------------------------------------------------------------------
    # Flag Generation Helpers
    # -------------------------------------------------------------------------

    def create_flag(
        self,
        rule_id: str,
        severity: FlagSeverity,
        message: str,
        required_action: Optional[str] = None,
        affected_stream: Optional[str] = None,
        affected_document_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_create_condition: bool = False
    ) -> IncomeFlag:
        """Create a standardized income flag."""
        return IncomeFlag(
            rule_id=rule_id,
            severity=severity,
            message=message,
            required_action=required_action,
            affected_stream=affected_stream,
            affected_document_id=affected_document_id,
            metadata=metadata or {},
            auto_create_condition=auto_create_condition,
        )

    def create_blocking_flag(
        self,
        rule_id: str,
        message: str,
        required_action: str,
        **kwargs
    ) -> IncomeFlag:
        """Create a blocking flag (cannot proceed)."""
        return self.create_flag(
            rule_id=rule_id,
            severity=FlagSeverity.BLOCKING,
            message=message,
            required_action=required_action,
            auto_create_condition=True,
            **kwargs
        )

    def create_error_flag(
        self,
        rule_id: str,
        message: str,
        required_action: Optional[str] = None,
        **kwargs
    ) -> IncomeFlag:
        """Create an error flag (calculation issue)."""
        return self.create_flag(
            rule_id=rule_id,
            severity=FlagSeverity.ERROR,
            message=message,
            required_action=required_action,
            **kwargs
        )

    def create_warning_flag(
        self,
        rule_id: str,
        message: str,
        **kwargs
    ) -> IncomeFlag:
        """Create a warning flag (potential issue)."""
        return self.create_flag(
            rule_id=rule_id,
            severity=FlagSeverity.WARNING,
            message=message,
            **kwargs
        )

    def create_info_flag(
        self,
        rule_id: str,
        message: str,
        **kwargs
    ) -> IncomeFlag:
        """Create an info flag (informational only)."""
        return self.create_flag(
            rule_id=rule_id,
            severity=FlagSeverity.INFO,
            message=message,
            **kwargs
        )

    # -------------------------------------------------------------------------
    # Calculation Step Logging
    # -------------------------------------------------------------------------

    def log_step(
        self,
        description: str,
        formula: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        result: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Create a calculation step entry for audit trail."""
        step = {
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if formula:
            step["formula"] = formula

        if inputs:
            # Convert Decimals to float for JSON serialization
            step["inputs"] = {
                k: float(v) if isinstance(v, Decimal) else v
                for k, v in inputs.items()
            }

        if result is not None:
            step["result"] = float(result) if isinstance(result, Decimal) else result

        return step

    # -------------------------------------------------------------------------
    # Result Building Helpers
    # -------------------------------------------------------------------------

    def create_income_stream(
        self,
        stream_type: IncomeStreamType,
        stream_name: str,
        monthly_income: Decimal,
        calculation_inputs: Dict[str, Any],
        calculation_steps: List[Dict[str, Any]],
        document_ids: List[str],
        tax_years: List[int] = None,
        add_backs: Dict[str, Decimal] = None,
        subtractions: Dict[str, Decimal] = None,
        trending_direction: TrendDirection = None,
        trending_percentage: Decimal = None,
        year1_income: Decimal = None,
        year2_income: Decimal = None,
        uses_lower_year: bool = False,
    ) -> IncomeStream:
        """Create a standardized income stream result."""
        return IncomeStream(
            stream_type=stream_type,
            stream_name=stream_name,
            monthly_income=self.round_currency(monthly_income),
            annual_income=self.monthly_to_annual(monthly_income),
            calculation_inputs=calculation_inputs,
            calculation_steps=calculation_steps,
            document_ids=document_ids,
            tax_years=tax_years or [],
            add_backs=add_backs or {},
            subtractions=subtractions or {},
            trending_direction=trending_direction,
            trending_percentage=trending_percentage,
            year1_income=year1_income,
            year2_income=year2_income,
            uses_lower_year=uses_lower_year,
        )

    def create_result(
        self,
        success: bool = True,
        income_streams: List[IncomeStream] = None,
        flags: List[IncomeFlag] = None,
        error_message: str = None
    ) -> EngineResult:
        """Create engine result."""
        streams = income_streams or []
        total_monthly = sum(s.monthly_income for s in streams)

        return EngineResult(
            engine_name=self.ENGINE_NAME,
            engine_version=self.ENGINE_VERSION,
            success=success,
            income_streams=streams,
            flags=flags or [],
            total_monthly_income=self.round_currency(total_monthly),
            error_message=error_message,
        )

    def create_error_result(self, error_message: str) -> EngineResult:
        """Create an error result."""
        return self.create_result(
            success=False,
            error_message=error_message,
            flags=[
                self.create_error_flag(
                    FlagRuleId.CALCULATION_ERROR,
                    f"Calculation error: {error_message}"
                )
            ]
        )
