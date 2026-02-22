"""
Income Calculation Service

Implements mortgage underwriting income calculation logic:
- W-2 income (YTD annualized or 2-year average)
- Self-employed income (2-year average with add-backs)
- Hourly income (standard 2080 hours or actual)
- Rental income (Schedule E or lease with vacancy)
- Variable income trending analysis
- Declining income rules

Uses the lower of YTD-annualized or 2-year average when income is declining.
"""

import logging
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

STANDARD_WORK_HOURS_PER_YEAR = 2080
MONTHS_PER_YEAR = 12
DEFAULT_VACANCY_FACTOR = 0.25  # 25% vacancy for rental income


@dataclass
class IncomeCalculationResult:
    """Result of an income calculation."""
    success: bool
    monthly_qualifying_income: Optional[Decimal] = None
    annual_qualifying_income: Optional[Decimal] = None
    calculation_method: str = ""
    calculation_steps: List[Dict[str, Any]] = field(default_factory=list)
    flags: Dict[str, bool] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "monthly_qualifying_income": float(self.monthly_qualifying_income) if self.monthly_qualifying_income else None,
            "annual_qualifying_income": float(self.annual_qualifying_income) if self.annual_qualifying_income else None,
            "calculation_method": self.calculation_method,
            "calculation_steps": self.calculation_steps,
            "flags": self.flags,
            "notes": self.notes,
            "error": self.error,
        }


class IncomeCalculationService:
    """
    Service for calculating qualifying income per underwriting guidelines.

    Supports all major income types and applies appropriate calculation
    methods based on income characteristics.
    """

    def __init__(self):
        pass

    # =========================================================================
    # W-2 INCOME CALCULATIONS
    # =========================================================================

    def calculate_w2_income(
        self,
        paystubs: List[Dict[str, Any]],
        w2s: Optional[List[Dict[str, Any]]] = None,
    ) -> IncomeCalculationResult:
        """
        Calculate qualifying W-2 income.

        IMPORTANT: For paystubs, gross_pay is the PAY PERIOD amount, not annual!
        We must annualize using: gross_pay × pay_frequency_multiplier

        YTD annualization is unreliable for new employees or early in the year
        because YTD may only represent a few pay periods.

        Uses the lower of:
        - Period-annualized income (most accurate for current pay rate)
        - 2-year average from W-2s (if available)

        This protects against declining income situations.
        """
        steps = []
        flags = {
            "declining_income": False,
            "variable_income": False,
            "requires_2_year_history": False,
        }
        notes = []

        if not paystubs:
            return IncomeCalculationResult(
                success=False,
                error="No paystub data found. Please upload a paystub document and click 'Extract from Docs' first."
            )

        # Sort paystubs by pay date, most recent first
        sorted_stubs = sorted(
            paystubs,
            key=lambda x: x.get("pay_date", ""),
            reverse=True
        )
        latest_stub = sorted_stubs[0]

        # PRIMARY METHOD: Period annualization (most accurate for paystubs)
        # gross_pay × frequency multiplier gives the true annualized rate
        gross_pay = self._to_decimal(latest_stub.get("gross_pay"))
        pay_frequency = latest_stub.get("pay_frequency", "").upper()
        period_annualized = None

        if gross_pay:
            multiplier = self._get_pay_frequency_multiplier(pay_frequency)
            period_annualized = gross_pay * Decimal(multiplier)
            steps.append({
                "step": "Period Annualized",
                "gross_pay": float(gross_pay),
                "pay_frequency": pay_frequency,
                "multiplier": multiplier,
                "annualized": float(period_annualized.quantize(Decimal("0.01"))),
                "formula": f"{gross_pay} * {multiplier}"
            })

        # SECONDARY: YTD annualized (for validation/comparison only)
        # This can be misleading for new employees or early in year
        ytd_gross = self._to_decimal(latest_stub.get("ytd_gross"))
        pay_date = latest_stub.get("pay_date")
        ytd_annualized = None

        if ytd_gross and pay_date:
            try:
                pay_dt = datetime.strptime(pay_date, "%Y-%m-%d")
                days_elapsed = (pay_dt - datetime(pay_dt.year, 1, 1)).days + 1

                # Only use YTD annualization if we have substantial YTD data
                # (employee has worked at least 60 days this year)
                if days_elapsed >= 60:
                    ytd_annualized = (ytd_gross / Decimal(days_elapsed)) * Decimal(365)
                    steps.append({
                        "step": "YTD Annualized (validation)",
                        "ytd_gross": float(ytd_gross),
                        "days_elapsed": days_elapsed,
                        "annualized": float(ytd_annualized.quantize(Decimal("0.01"))),
                        "formula": f"({ytd_gross} / {days_elapsed}) * 365"
                    })
                else:
                    notes.append(f"YTD only covers {days_elapsed} days - using period annualization")
            except (ValueError, ZeroDivisionError) as e:
                notes.append(f"YTD annualization error: {e}")

        # Use period annualization as primary (it's based on current pay rate)
        current_annual = period_annualized or ytd_annualized

        if not current_annual:
            return IncomeCalculationResult(
                success=False,
                error="Could not calculate current income from paystubs"
            )

        # Calculate 2-year average from W-2s if available
        two_year_average = None
        if w2s and len(w2s) >= 2:
            w2_incomes = []
            for w2 in sorted(w2s, key=lambda x: x.get("tax_year", 0), reverse=True)[:2]:
                wages = self._to_decimal(w2.get("wages_tips_compensation"))
                if wages:
                    w2_incomes.append(wages)
                    steps.append({
                        "step": f"W-2 Year {w2.get('tax_year')}",
                        "wages": float(wages)
                    })

            if len(w2_incomes) == 2:
                two_year_average = sum(w2_incomes) / Decimal(2)
                steps.append({
                    "step": "2-Year Average",
                    "year1": float(w2_incomes[0]),
                    "year2": float(w2_incomes[1]),
                    "average": float(two_year_average.quantize(Decimal("0.01")))
                })

                # Check for declining income
                if w2_incomes[0] < w2_incomes[1]:
                    decline_pct = ((w2_incomes[1] - w2_incomes[0]) / w2_incomes[1]) * 100
                    if decline_pct > 10:
                        flags["declining_income"] = True
                        notes.append(f"Income declined {float(decline_pct):.1f}% year-over-year")

        # Use lower of current or 2-year average (standard underwriting practice)
        if two_year_average and current_annual > two_year_average:
            annual_qualifying = two_year_average
            calculation_method = "TWO_YEAR_AVERAGE"
            notes.append("Using 2-year average (lower than current)")
        else:
            annual_qualifying = current_annual
            calculation_method = "YTD_ANNUALIZED" if ytd_annualized else "PERIOD_MULTIPLIER"

        monthly_qualifying = (annual_qualifying / Decimal(12)).quantize(Decimal("0.01"))
        annual_qualifying = annual_qualifying.quantize(Decimal("0.01"))

        steps.append({
            "step": "Final Qualifying Income",
            "method": calculation_method,
            "annual": float(annual_qualifying),
            "monthly": float(monthly_qualifying)
        })

        return IncomeCalculationResult(
            success=True,
            monthly_qualifying_income=monthly_qualifying,
            annual_qualifying_income=annual_qualifying,
            calculation_method=calculation_method,
            calculation_steps=steps,
            flags=flags,
            notes=notes,
        )

    def calculate_hourly_income(
        self,
        hourly_rate: Decimal,
        actual_hours_per_week: Optional[Decimal] = None,
        use_standard_hours: bool = True,
        has_overtime: bool = False,
        overtime_rate: Optional[Decimal] = None,
        avg_overtime_hours: Optional[Decimal] = None,
    ) -> IncomeCalculationResult:
        """
        Calculate qualifying hourly income.

        Options:
        - Standard: hourly_rate * 2080 hours/year
        - Actual: hourly_rate * actual_hours * 52 weeks
        - With overtime: base + (overtime_rate * avg_overtime_hours * 52)
        """
        steps = []
        notes = []

        if not hourly_rate or hourly_rate <= 0:
            return IncomeCalculationResult(
                success=False,
                error="Invalid hourly rate"
            )

        # Base calculation
        if use_standard_hours or not actual_hours_per_week:
            annual_base = hourly_rate * Decimal(STANDARD_WORK_HOURS_PER_YEAR)
            method = "HOURLY_STANDARD"
            steps.append({
                "step": "Base Income (Standard)",
                "hourly_rate": float(hourly_rate),
                "hours_per_year": STANDARD_WORK_HOURS_PER_YEAR,
                "annual": float(annual_base.quantize(Decimal("0.01"))),
                "formula": f"{hourly_rate} * 2080"
            })
        else:
            annual_hours = actual_hours_per_week * Decimal(52)
            annual_base = hourly_rate * annual_hours
            method = "HOURLY_ACTUAL"
            steps.append({
                "step": "Base Income (Actual Hours)",
                "hourly_rate": float(hourly_rate),
                "hours_per_week": float(actual_hours_per_week),
                "weeks_per_year": 52,
                "annual": float(annual_base.quantize(Decimal("0.01"))),
            })
            if actual_hours_per_week < 40:
                notes.append(f"Part-time: {actual_hours_per_week} hours/week")

        # Add overtime if applicable
        annual_overtime = Decimal(0)
        if has_overtime and overtime_rate and avg_overtime_hours:
            annual_overtime = overtime_rate * avg_overtime_hours * Decimal(52)
            steps.append({
                "step": "Overtime Income",
                "overtime_rate": float(overtime_rate),
                "avg_weekly_hours": float(avg_overtime_hours),
                "annual": float(annual_overtime.quantize(Decimal("0.01"))),
            })
            notes.append("Overtime income included - requires 2-year history")

        annual_qualifying = (annual_base + annual_overtime).quantize(Decimal("0.01"))
        monthly_qualifying = (annual_qualifying / Decimal(12)).quantize(Decimal("0.01"))

        return IncomeCalculationResult(
            success=True,
            monthly_qualifying_income=monthly_qualifying,
            annual_qualifying_income=annual_qualifying,
            calculation_method=method,
            calculation_steps=steps,
            notes=notes,
            flags={"requires_2_year_history": has_overtime},
        )

    # =========================================================================
    # SELF-EMPLOYED INCOME CALCULATIONS
    # =========================================================================

    def calculate_self_employed_income(
        self,
        tax_returns: List[Dict[str, Any]],
        ownership_percentage: Decimal = Decimal(100),
    ) -> IncomeCalculationResult:
        """
        Calculate self-employed qualifying income from tax returns.

        Uses 2-year average of:
        - Net profit/loss
        + Depreciation add-back
        + Amortization add-back
        + Depletion add-back
        + Business use of home (optional add-back)

        Applies ownership percentage for partnerships/S-Corps.
        """
        steps = []
        flags = {
            "declining_income": False,
            "variable_income": False,
            "requires_2_year_history": True,
        }
        notes = []

        if len(tax_returns) < 2:
            notes.append("Less than 2 years of tax returns - using available data")
            if not tax_returns:
                return IncomeCalculationResult(
                    success=False,
                    error="No tax returns provided for self-employed calculation"
                )

        # Sort by tax year, most recent first
        sorted_returns = sorted(
            tax_returns,
            key=lambda x: x.get("tax_year", 0),
            reverse=True
        )[:2]  # Max 2 years

        yearly_incomes = []

        for ret in sorted_returns:
            tax_year = ret.get("tax_year")

            # Base income
            net_profit = self._to_decimal(ret.get("net_profit_loss", 0))

            # Non-cash add-backs
            depreciation = self._to_decimal(ret.get("depreciation_addback", 0))
            amortization = self._to_decimal(ret.get("amortization_addback", 0))
            depletion = self._to_decimal(ret.get("depletion_addback", 0))

            # K-1 data (for S-Corp/Partnership)
            k1_ordinary = self._to_decimal(ret.get("k1_ordinary_income", 0))
            k1_guaranteed = self._to_decimal(ret.get("k1_guaranteed_payments", 0))

            # Calculate adjusted income
            if k1_ordinary or k1_guaranteed:
                # S-Corp or Partnership
                adjusted = (k1_ordinary + k1_guaranteed + depreciation + amortization)
                adjusted = adjusted * (ownership_percentage / Decimal(100))
                income_type = "K-1"
            else:
                # Schedule C
                adjusted = net_profit + depreciation + amortization + depletion
                income_type = "Schedule C"

            yearly_incomes.append(adjusted)

            steps.append({
                "step": f"Tax Year {tax_year} ({income_type})",
                "net_profit": float(net_profit),
                "depreciation_addback": float(depreciation),
                "amortization_addback": float(amortization),
                "k1_ordinary": float(k1_ordinary) if k1_ordinary else None,
                "k1_guaranteed": float(k1_guaranteed) if k1_guaranteed else None,
                "ownership_pct": float(ownership_percentage),
                "adjusted_income": float(adjusted.quantize(Decimal("0.01"))),
            })

        # Calculate average
        if len(yearly_incomes) == 2:
            average = sum(yearly_incomes) / Decimal(2)
            calculation_method = "TWO_YEAR_AVERAGE"

            # Check for declining income
            if yearly_incomes[0] < yearly_incomes[1]:
                decline_pct = ((yearly_incomes[1] - yearly_incomes[0]) / abs(yearly_incomes[1])) * 100
                if decline_pct > 20:
                    flags["declining_income"] = True
                    notes.append(f"Self-employment income declined {float(decline_pct):.1f}%")
                    # Use lower year when declining significantly
                    average = yearly_incomes[0]
                    notes.append("Using most recent year due to declining trend")

            steps.append({
                "step": "2-Year Average",
                "year1": float(yearly_incomes[0]),
                "year2": float(yearly_incomes[1]),
                "average": float(average.quantize(Decimal("0.01"))),
            })
        else:
            average = yearly_incomes[0]
            calculation_method = "SINGLE_YEAR"
            notes.append("Only 1 year of tax returns available")

        annual_qualifying = average.quantize(Decimal("0.01"))
        monthly_qualifying = (annual_qualifying / Decimal(12)).quantize(Decimal("0.01"))

        # Check for loss
        if annual_qualifying < 0:
            notes.append("Business shows a loss - income is negative")
            flags["declining_income"] = True

        return IncomeCalculationResult(
            success=True,
            monthly_qualifying_income=monthly_qualifying,
            annual_qualifying_income=annual_qualifying,
            calculation_method=calculation_method,
            calculation_steps=steps,
            flags=flags,
            notes=notes,
        )

    # =========================================================================
    # RENTAL INCOME CALCULATIONS
    # =========================================================================

    def calculate_rental_income(
        self,
        schedule_e_data: Optional[List[Dict[str, Any]]] = None,
        lease_data: Optional[Dict[str, Any]] = None,
        pitia: Optional[Decimal] = None,
        is_subject_property: bool = False,
        vacancy_factor: Decimal = Decimal(DEFAULT_VACANCY_FACTOR),
    ) -> IncomeCalculationResult:
        """
        Calculate rental property qualifying income.

        Methods:
        1. Schedule E: 2-year average of net income + depreciation add-back
        2. Lease: Monthly rent * (1 - vacancy_factor) * 12

        For subject property, offsets against PITIA.
        """
        steps = []
        notes = []
        flags = {"variable_income": True}

        annual_income = Decimal(0)
        calculation_method = ""

        # Method 1: Schedule E from tax returns
        if schedule_e_data:
            yearly_incomes = []

            for schedule in sorted(schedule_e_data, key=lambda x: x.get("tax_year", 0), reverse=True)[:2]:
                tax_year = schedule.get("tax_year")
                gross_rents = self._to_decimal(schedule.get("schedule_e_gross_rents", 0))
                total_expenses = self._to_decimal(schedule.get("schedule_e_total_expenses", 0))
                depreciation = self._to_decimal(schedule.get("schedule_e_depreciation", 0))

                # Net income + depreciation add-back
                net_income = gross_rents - total_expenses + depreciation
                yearly_incomes.append(net_income)

                steps.append({
                    "step": f"Schedule E Year {tax_year}",
                    "gross_rents": float(gross_rents),
                    "total_expenses": float(total_expenses),
                    "depreciation_addback": float(depreciation),
                    "net_income": float(net_income.quantize(Decimal("0.01"))),
                })

            if len(yearly_incomes) >= 2:
                average = sum(yearly_incomes) / Decimal(2)
                calculation_method = "SCHEDULE_E_AVERAGE"
            else:
                average = yearly_incomes[0] if yearly_incomes else Decimal(0)
                calculation_method = "SCHEDULE_E_SINGLE_YEAR"

            annual_income = average

            steps.append({
                "step": "Schedule E Average",
                "average": float(annual_income.quantize(Decimal("0.01"))),
            })

        # Method 2: Lease-based calculation
        elif lease_data:
            monthly_rent = self._to_decimal(lease_data.get("current_monthly_rent", 0))
            if monthly_rent:
                # Apply vacancy factor
                effective_rent = monthly_rent * (Decimal(1) - vacancy_factor)
                annual_income = effective_rent * Decimal(12)
                calculation_method = "LEASE_WITH_VACANCY"

                steps.append({
                    "step": "Lease Income",
                    "monthly_rent": float(monthly_rent),
                    "vacancy_factor": float(vacancy_factor * 100),
                    "effective_monthly": float(effective_rent.quantize(Decimal("0.01"))),
                    "annual": float(annual_income.quantize(Decimal("0.01"))),
                })

                notes.append(f"Applied {float(vacancy_factor * 100):.0f}% vacancy factor")

        # Subject property offset
        if is_subject_property and pitia:
            steps.append({
                "step": "PITIA Offset (Subject Property)",
                "pitia_monthly": float(pitia),
                "pitia_annual": float(pitia * 12),
            })
            annual_income = annual_income - (pitia * Decimal(12))
            notes.append("Subject property - PITIA offset applied")

        annual_qualifying = annual_income.quantize(Decimal("0.01"))
        monthly_qualifying = (annual_qualifying / Decimal(12)).quantize(Decimal("0.01"))

        return IncomeCalculationResult(
            success=True,
            monthly_qualifying_income=monthly_qualifying,
            annual_qualifying_income=annual_qualifying,
            calculation_method=calculation_method,
            calculation_steps=steps,
            flags=flags,
            notes=notes,
        )

    # =========================================================================
    # AGGREGATE INCOME
    # =========================================================================

    def aggregate_borrower_income(
        self,
        income_sources: List[Dict[str, Any]],
    ) -> IncomeCalculationResult:
        """
        Aggregate all income sources for a borrower.

        Sums monthly/annual qualifying income from all active income sources.
        """
        steps = []
        notes = []
        total_monthly = Decimal(0)
        total_annual = Decimal(0)

        for source in income_sources:
            if not source.get("is_active", True):
                continue

            monthly = self._to_decimal(source.get("monthly_qualifying_income", 0))
            annual = self._to_decimal(source.get("annual_qualifying_income", 0))

            if monthly or annual:
                total_monthly += monthly or (annual / Decimal(12))
                total_annual += annual or (monthly * Decimal(12))

                steps.append({
                    "source": source.get("source_name", "Unknown"),
                    "income_type": source.get("income_type", "OTHER"),
                    "monthly": float(monthly) if monthly else None,
                    "annual": float(annual) if annual else None,
                })

        # Check for declining flags across sources
        declining_count = sum(1 for s in income_sources if s.get("declining_income_flag"))
        if declining_count > 0:
            notes.append(f"{declining_count} income source(s) showing declining trend")

        return IncomeCalculationResult(
            success=True,
            monthly_qualifying_income=total_monthly.quantize(Decimal("0.01")),
            annual_qualifying_income=total_annual.quantize(Decimal("0.01")),
            calculation_method="AGGREGATE",
            calculation_steps=steps,
            notes=notes,
            flags={"has_declining_sources": declining_count > 0},
        )

    # =========================================================================
    # TRENDING ANALYSIS
    # =========================================================================

    def analyze_income_trend(
        self,
        income_values: List[Tuple[str, Decimal]],  # (period, amount)
    ) -> Dict[str, Any]:
        """
        Analyze income trend over time.

        Returns:
        - direction: increasing, stable, declining
        - percentage: YoY or period change %
        - volatility: low, medium, high
        """
        if len(income_values) < 2:
            return {
                "direction": "unknown",
                "percentage": 0,
                "volatility": "unknown",
                "insufficient_data": True,
            }

        # Sort by period
        sorted_values = sorted(income_values, key=lambda x: x[0])
        amounts = [v[1] for v in sorted_values]

        # Calculate trend
        first = amounts[0]
        last = amounts[-1]

        if first == 0:
            pct_change = 100 if last > 0 else 0
        else:
            pct_change = float(((last - first) / abs(first)) * 100)

        if pct_change > 5:
            direction = "increasing"
        elif pct_change < -5:
            direction = "declining"
        else:
            direction = "stable"

        # Calculate volatility (coefficient of variation)
        mean = sum(amounts) / len(amounts)
        if mean > 0:
            variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
            std_dev = variance ** Decimal("0.5")
            cv = float(std_dev / mean)

            if cv < 0.1:
                volatility = "low"
            elif cv < 0.25:
                volatility = "medium"
            else:
                volatility = "high"
        else:
            volatility = "unknown"

        return {
            "direction": direction,
            "percentage": round(pct_change, 2),
            "volatility": volatility,
            "data_points": len(amounts),
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _to_decimal(self, value: Any) -> Decimal:
        """Safely convert value to Decimal."""
        if value is None:
            return Decimal(0)
        try:
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()
                if not value:
                    return Decimal(0)
            return Decimal(str(value))
        except Exception as e:
            logger.warning(f"Error converting value to Decimal: {e}")
            return Decimal(0)

    def _get_pay_frequency_multiplier(self, frequency: str) -> int:
        """Get annual multiplier for pay frequency."""
        multipliers = {
            "WEEKLY": 52,
            "BIWEEKLY": 26,
            "SEMIMONTHLY": 24,
            "MONTHLY": 12,
        }
        return multipliers.get(frequency.upper(), 12)


# Singleton instance
_calculation_service: Optional[IncomeCalculationService] = None


def get_income_calculation_service() -> IncomeCalculationService:
    """Get the singleton income calculation service."""
    global _calculation_service
    if _calculation_service is None:
        _calculation_service = IncomeCalculationService()
    return _calculation_service
