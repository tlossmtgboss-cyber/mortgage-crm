"""
Unified Income Calculator Service

Implements all 14 income calculation types from the Unified Income Calculator Excel:
1. W2 Hourly - hourly rate × hours × 52/12
2. W2 Salary - salary with frequency multipliers (Monthly ×1, Bi-weekly ×26/12, etc.)
3. OT & Bonus - overtime/bonus 2-year averaging
4. Commission - commission minus 2106 unreimbursed expenses
5. Other Income - misc income types
6. NonTax SS - Social Security with 25% gross-up
7. NonTax Other - pension, IRA, child support with 25% gross-up
8. Bank Statement Personal - Non-QM personal account analysis
9. Bank Statement Business Method 1 - Deposits minus expenses
10. Bank Statement Business Method 2 - Gross deposits with expense ratio
11. Bank Statement Business Method 3 - P&L with deposits verification
12. Rental Income (Schedule E) - gross rents - expenses + depreciation - PITIA
13. Fannie 1084 Self-Employment - Schedule C, K-1 1065, K-1 1120S, Form 1120

Each calculator:
- Extracts data from uploaded documents using AI
- Calculates qualifying income per underwriting guidelines
- Generates confidence scores for review workflow
- Produces audit trail with calculation steps
"""

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS - All 14 Income Types
# =============================================================================

class UnifiedIncomeType(str, enum.Enum):
    """All 14 income types from the Unified Income Calculator."""
    W2_HOURLY = "W2_HOURLY"
    W2_SALARY = "W2_SALARY"
    OT_BONUS = "OT_BONUS"
    COMMISSION = "COMMISSION"
    OTHER_INCOME = "OTHER_INCOME"
    NONTAX_SS = "NONTAX_SS"
    NONTAX_OTHER = "NONTAX_OTHER"
    BANK_STATEMENT_PERSONAL = "BANK_STATEMENT_PERSONAL"
    BANK_STATEMENT_BUSINESS_M1 = "BANK_STATEMENT_BUSINESS_M1"
    BANK_STATEMENT_BUSINESS_M2 = "BANK_STATEMENT_BUSINESS_M2"
    BANK_STATEMENT_BUSINESS_M3 = "BANK_STATEMENT_BUSINESS_M3"
    RENTAL_SCHEDULE_E = "RENTAL_SCHEDULE_E"
    SELF_EMPLOYMENT_1084 = "SELF_EMPLOYMENT_1084"


class PayFrequency(str, enum.Enum):
    """Payroll frequency with multipliers."""
    MONTHLY = "MONTHLY"           # ×1
    SEMI_MONTHLY = "SEMI_MONTHLY" # ×24/12 = ×2
    BI_WEEKLY = "BI_WEEKLY"       # ×26/12 = ×2.1667
    WEEKLY = "WEEKLY"             # ×52/12 = ×4.333


class AveragingMethod(str, enum.Enum):
    """Income averaging methods."""
    YTD_ONLY = "YTD_ONLY"
    YTD_PLUS_1_YEAR = "YTD_PLUS_1_YEAR"
    YTD_PLUS_2_YEAR = "YTD_PLUS_2_YEAR"
    USE_LOWEST = "USE_LOWEST"


class ConfidenceLevel(str, enum.Enum):
    """AI extraction confidence levels."""
    HIGH = "HIGH"      # 95%+ - Auto-approve eligible
    MEDIUM = "MEDIUM"  # 80-94% - Quick review
    LOW = "LOW"        # 60-79% - Full review required
    MANUAL = "MANUAL"  # <60% - Manual entry required


# =============================================================================
# FREQUENCY MULTIPLIERS - Matching Excel formulas
# =============================================================================

FREQUENCY_MULTIPLIERS = {
    PayFrequency.MONTHLY: Decimal("1"),
    PayFrequency.SEMI_MONTHLY: Decimal("24") / Decimal("12"),  # 2.0
    PayFrequency.BI_WEEKLY: Decimal("26") / Decimal("12"),      # 2.1667
    PayFrequency.WEEKLY: Decimal("52") / Decimal("12"),         # 4.333
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CalculationStep:
    """Single step in income calculation for audit trail."""
    step_number: int
    description: str
    formula: str
    inputs: Dict[str, Any]
    result: Decimal
    notes: Optional[str] = None


@dataclass
class IncomeCalculationResult:
    """Result of any income calculation."""
    success: bool
    income_type: UnifiedIncomeType

    # Qualifying income
    monthly_income: Optional[Decimal] = None
    annual_income: Optional[Decimal] = None

    # Method used
    calculation_method: str = ""
    averaging_method: Optional[AveragingMethod] = None

    # Audit trail
    calculation_steps: List[CalculationStep] = field(default_factory=list)

    # Confidence scoring
    confidence_score: int = 0  # 0-100
    confidence_level: ConfidenceLevel = ConfidenceLevel.MANUAL
    fields_extracted: Dict[str, int] = field(default_factory=dict)  # field: confidence

    # Flags and warnings
    flags: Dict[str, bool] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Source data
    source_documents: List[str] = field(default_factory=list)
    tax_years: List[int] = field(default_factory=list)

    # Error state
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "income_type": self.income_type.value,
            "monthly_income": float(self.monthly_income) if self.monthly_income else None,
            "annual_income": float(self.annual_income) if self.annual_income else None,
            "calculation_method": self.calculation_method,
            "averaging_method": self.averaging_method.value if self.averaging_method else None,
            "calculation_steps": [
                {
                    "step": s.step_number,
                    "description": s.description,
                    "formula": s.formula,
                    "inputs": {k: float(v) if isinstance(v, Decimal) else v for k, v in s.inputs.items()},
                    "result": float(s.result),
                    "notes": s.notes,
                }
                for s in self.calculation_steps
            ],
            "confidence_score": self.confidence_score,
            "confidence_level": self.confidence_level.value,
            "fields_extracted": self.fields_extracted,
            "flags": self.flags,
            "warnings": self.warnings,
            "errors": self.errors,
            "source_documents": self.source_documents,
            "tax_years": self.tax_years,
            "error": self.error,
        }


@dataclass
class W2HourlyData:
    """Data for W2 Hourly calculation."""
    hourly_rate: Decimal
    hours_per_period: Decimal = Decimal("40")
    pay_frequency: PayFrequency = PayFrequency.BI_WEEKLY

    # YTD data
    ytd_earnings: Optional[Decimal] = None
    ytd_months: Optional[int] = None

    # W2 history
    w2_year1_earnings: Optional[Decimal] = None
    w2_year1_months: int = 12
    w2_year2_earnings: Optional[Decimal] = None
    w2_year2_months: int = 12


@dataclass
class W2SalaryData:
    """Data for W2 Salary calculation."""
    base_salary: Decimal
    pay_frequency: PayFrequency = PayFrequency.MONTHLY

    # YTD data
    ytd_salary: Optional[Decimal] = None
    ytd_months: Optional[int] = None

    # W2 history
    w2_year1_earnings: Optional[Decimal] = None
    w2_year1_months: int = 12
    w2_year2_earnings: Optional[Decimal] = None
    w2_year2_months: int = 12


@dataclass
class OTBonusData:
    """Data for Overtime & Bonus calculation."""
    # YTD
    ytd_ot_bonus: Decimal = Decimal("0")
    ytd_months: int = 0

    # Prior years
    year1_ot_bonus: Optional[Decimal] = None
    year1_months: int = 12
    year2_ot_bonus: Optional[Decimal] = None
    year2_months: int = 12


@dataclass
class CommissionData:
    """Data for Commission calculation."""
    # YTD
    ytd_commission: Decimal = Decimal("0")
    ytd_expenses_2106: Decimal = Decimal("0")
    ytd_months: int = 0

    # Prior years (Commission - 2106 expenses = Net)
    year1_commission: Optional[Decimal] = None
    year1_expenses_2106: Decimal = Decimal("0")
    year1_months: int = 12

    year2_commission: Optional[Decimal] = None
    year2_expenses_2106: Decimal = Decimal("0")
    year2_months: int = 12


@dataclass
class NonTaxSSData:
    """Data for Non-Taxable Social Security calculation."""
    annual_benefit: Decimal
    # With documentation - can separate taxable/non-taxable
    taxable_portion: Optional[Decimal] = None    # Line 5a from 1040
    non_taxable_portion: Optional[Decimal] = None  # Line 5a - 5b from 1040
    # Without documentation - use 85%/15% split
    has_documentation: bool = False


@dataclass
class NonTaxOtherData:
    """Data for other non-taxable income calculation."""
    income_type: str  # pension, ira_distribution, child_support, disability, etc.
    annual_amount: Decimal
    is_taxable: bool = False  # If non-taxable, apply 25% gross-up


@dataclass
class BankStatementPersonalData:
    """Data for personal bank statement income."""
    monthly_deposits: List[Decimal]  # 12 or 24 months
    expense_factor: Decimal = Decimal("50")  # Default 50% expense ratio
    months_analyzed: int = 12


@dataclass
class BankStatementBusinessData:
    """Data for business bank statement income."""
    monthly_deposits: List[Decimal]  # 12 or 24 months
    method: int = 1  # 1, 2, or 3

    # Method 1: Deposits - Expenses
    monthly_expenses: Optional[List[Decimal]] = None

    # Method 2: Gross deposits × (1 - expense_ratio)
    expense_ratio: Decimal = Decimal("50")  # Percentage

    # Method 3: P&L verification
    pl_net_income: Optional[Decimal] = None

    ownership_percentage: Decimal = Decimal("100")


@dataclass
class RentalScheduleEData:
    """Data for Rental Income (Schedule E) calculation."""
    property_address: str

    # Schedule E data (per property, up to 4 per page)
    gross_rents_line3: Decimal = Decimal("0")
    total_expenses_line20: Decimal = Decimal("0")
    depreciation_line18: Decimal = Decimal("0")
    amortization_casualty_line19: Decimal = Decimal("0")

    # PITIA offset
    monthly_insurance: Decimal = Decimal("0")
    monthly_mortgage_interest: Decimal = Decimal("0")
    monthly_taxes: Decimal = Decimal("0")
    monthly_hoa: Decimal = Decimal("0")

    # Second year for averaging
    year2_gross_rents: Optional[Decimal] = None
    year2_total_expenses: Optional[Decimal] = None
    year2_depreciation: Optional[Decimal] = None


@dataclass
class SelfEmployment1084Data:
    """Data for Fannie Mae 1084 Self-Employment calculation."""
    business_name: str
    business_type: str  # sole_prop, s_corp, partnership, c_corp
    ownership_percentage: Decimal = Decimal("100")

    # Schedule C (Lines 4-12)
    schedule_c_net_profit_line31: Decimal = Decimal("0")
    schedule_c_depreciation_line13: Decimal = Decimal("0")
    schedule_c_depletion_line12: Decimal = Decimal("0")
    schedule_c_business_use_home: Decimal = Decimal("0")  # Form 8829 or simplified
    schedule_c_mileage: Decimal = Decimal("0")  # Business miles claimed
    mileage_depreciation_rate: Decimal = Decimal("0.28")  # IRS rate

    # K-1 1065 Partnership (Lines 7a-8p)
    k1_1065_ordinary_income_line1: Decimal = Decimal("0")
    k1_1065_guaranteed_payments_line4: Decimal = Decimal("0")
    k1_1065_section179_line12: Decimal = Decimal("0")
    k1_1065_other_deductions_line13: Decimal = Decimal("0")
    k1_1065_self_employment_earnings: Decimal = Decimal("0")

    # K-1 1120S S-Corp (Lines 9a-10p)
    k1_1120s_ordinary_income_line1: Decimal = Decimal("0")
    k1_1120s_net_rental_line2: Decimal = Decimal("0")
    k1_1120s_section179_line11: Decimal = Decimal("0")
    k1_1120s_other_deductions_line12: Decimal = Decimal("0")

    # Form 1120 C-Corp (Lines 11a-11m) - requires 100% ownership
    form_1120_taxable_income_line30: Decimal = Decimal("0")
    form_1120_total_tax_line31: Decimal = Decimal("0")
    form_1120_depreciation_line20: Decimal = Decimal("0")
    form_1120_depletion_line21: Decimal = Decimal("0")
    form_1120_nol_deduction: Decimal = Decimal("0")
    form_1120_dividends_paid: Decimal = Decimal("0")

    # Year 2 data for 2-year average
    year2_data: Optional[Dict[str, Decimal]] = None


# =============================================================================
# UNIFIED INCOME CALCULATOR
# =============================================================================

class UnifiedIncomeCalculator:
    """
    Master calculator implementing all 14 income types.

    Each method:
    1. Validates input data
    2. Calculates multiple averaging methods (YTD, 1-yr, 2-yr)
    3. Uses the lowest value (conservative underwriting)
    4. Returns detailed audit trail
    """

    def __init__(self):
        self.step_count = 0

    def _reset_steps(self):
        self.step_count = 0

    def _add_step(
        self,
        description: str,
        formula: str,
        inputs: Dict[str, Any],
        result: Decimal,
        notes: Optional[str] = None
    ) -> CalculationStep:
        self.step_count += 1
        return CalculationStep(
            step_number=self.step_count,
            description=description,
            formula=formula,
            inputs=inputs,
            result=result,
            notes=notes
        )

    def _to_decimal(self, value: Any) -> Decimal:
        """Safely convert value to Decimal."""
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()
                if not value:
                    return Decimal("0")
            return Decimal(str(value))
        except Exception as e:
            logger.warning(f"Error converting value to Decimal: {e}")
            return Decimal("0")

    def _round_currency(self, value: Decimal) -> Decimal:
        """Round to 2 decimal places for currency."""
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # =========================================================================
    # 1. W2 HOURLY INCOME
    # =========================================================================

    def calculate_w2_hourly(self, data: W2HourlyData) -> IncomeCalculationResult:
        """
        Calculate W2 Hourly income.

        Per Fannie Mae B3-3.1-01 (updated 03/04/2026):
        Only the most recent W-2 is required for fixed/stable base hourly
        income. Year 2 W-2 data is optional and used for trending analysis
        only. Confidence is NOT penalized for missing year 2 W-2.

        Formula: Per Hour × # of hours × 52/12 = Monthly Income

        Uses lowest of:
        - Current hourly calculation
        - YTD average
        - YTD + 1 year average
        - YTD + 2 year average (if year 2 W-2 provided)
        """
        self._reset_steps()
        steps = []
        warnings = []

        # Step 1: Calculate from hourly rate
        hours_per_week = data.hours_per_period
        if data.pay_frequency == PayFrequency.BI_WEEKLY:
            hours_per_week = data.hours_per_period / Decimal("2")

        hourly_monthly = data.hourly_rate * hours_per_week * Decimal("52") / Decimal("12")
        steps.append(self._add_step(
            description="Hourly Rate Calculation",
            formula="hourly_rate × hours_per_week × 52 / 12",
            inputs={
                "hourly_rate": data.hourly_rate,
                "hours_per_week": hours_per_week,
            },
            result=self._round_currency(hourly_monthly),
        ))

        candidates = [("Hourly Rate", hourly_monthly)]

        # Step 2: YTD Average
        if data.ytd_earnings and data.ytd_months and data.ytd_months > 0:
            ytd_avg = data.ytd_earnings / Decimal(data.ytd_months)
            steps.append(self._add_step(
                description="YTD Average",
                formula="ytd_earnings / ytd_months",
                inputs={
                    "ytd_earnings": data.ytd_earnings,
                    "ytd_months": data.ytd_months,
                },
                result=self._round_currency(ytd_avg),
            ))
            candidates.append(("YTD Avg", ytd_avg))

        # Step 3: YTD + 1 Year Average
        if data.ytd_earnings and data.w2_year1_earnings:
            total = data.ytd_earnings + data.w2_year1_earnings
            months = (data.ytd_months or 0) + data.w2_year1_months
            if months > 0:
                avg_1yr = total / Decimal(months)
                steps.append(self._add_step(
                    description="YTD + 1 Year Average",
                    formula="(ytd_earnings + w2_year1) / total_months",
                    inputs={
                        "ytd_earnings": data.ytd_earnings,
                        "w2_year1_earnings": data.w2_year1_earnings,
                        "total_months": months,
                    },
                    result=self._round_currency(avg_1yr),
                ))
                candidates.append(("YTD+1Yr", avg_1yr))

        # Step 4: YTD + 2 Year Average
        if data.ytd_earnings and data.w2_year1_earnings and data.w2_year2_earnings:
            total = data.ytd_earnings + data.w2_year1_earnings + data.w2_year2_earnings
            months = (data.ytd_months or 0) + data.w2_year1_months + data.w2_year2_months
            if months > 0:
                avg_2yr = total / Decimal(months)
                steps.append(self._add_step(
                    description="YTD + 2 Year Average",
                    formula="(ytd + year1 + year2) / total_months",
                    inputs={
                        "ytd_earnings": data.ytd_earnings,
                        "w2_year1_earnings": data.w2_year1_earnings,
                        "w2_year2_earnings": data.w2_year2_earnings,
                        "total_months": months,
                    },
                    result=self._round_currency(avg_2yr),
                ))
                candidates.append(("YTD+2Yr", avg_2yr))

        # Step 5: Use lowest income (conservative underwriting)
        lowest_name, monthly_income = min(candidates, key=lambda x: x[1])
        steps.append(self._add_step(
            description="Use Lowest Income",
            formula="min(all_calculations)",
            inputs={name: float(value) for name, value in candidates},
            result=self._round_currency(monthly_income),
            notes=f"Selected: {lowest_name}"
        ))

        # Check for declining income
        declining = False
        if len(candidates) > 1:
            if candidates[-1][1] < candidates[0][1] * Decimal("0.9"):
                declining = True
                warnings.append("Income is declining - used conservative calculation")

        # Per B3-3.1-01 (03/04/2026): Year 2 W-2 is no longer required for
        # stable base income. Confidence is not penalized for missing year 2.
        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.W2_HOURLY,
            monthly_income=self._round_currency(monthly_income),
            annual_income=self._round_currency(monthly_income * Decimal("12")),
            calculation_method="W2_HOURLY_LOWEST",
            averaging_method=AveragingMethod.USE_LOWEST,
            calculation_steps=steps,
            confidence_score=90,
            confidence_level=ConfidenceLevel.HIGH,
            flags={"declining_income": declining},
            warnings=warnings,
        )

    # =========================================================================
    # 2. W2 SALARY INCOME
    # =========================================================================

    def calculate_w2_salary(self, data: W2SalaryData) -> IncomeCalculationResult:
        """
        Calculate W2 Salary income.

        Per Fannie Mae B3-3.1-01 (updated 03/04/2026):
        Only the most recent W-2 is required for fixed/stable base salary
        income. Year 2 W-2 data is optional. Confidence is NOT penalized
        for missing year 2 W-2.

        Frequency multipliers:
        - Monthly × 1
        - Bi-Weekly × 26/12
        - Semi-Monthly × 24/12
        - Weekly × 52/12
        """
        self._reset_steps()
        steps = []
        warnings = []

        # Step 1: Calculate from base salary with frequency
        multiplier = FREQUENCY_MULTIPLIERS.get(data.pay_frequency, Decimal("1"))
        salary_monthly = data.base_salary * multiplier

        steps.append(self._add_step(
            description=f"Salary × {data.pay_frequency.value} Multiplier",
            formula=f"base_salary × {multiplier}",
            inputs={
                "base_salary": data.base_salary,
                "pay_frequency": data.pay_frequency.value,
                "multiplier": multiplier,
            },
            result=self._round_currency(salary_monthly),
        ))

        candidates = [("Salary", salary_monthly)]

        # Step 2: YTD comparison
        if data.ytd_salary and data.ytd_months and data.ytd_months > 0:
            ytd_avg = data.ytd_salary / Decimal(data.ytd_months)
            steps.append(self._add_step(
                description="YTD Salary Average",
                formula="ytd_salary / ytd_months",
                inputs={
                    "ytd_salary": data.ytd_salary,
                    "ytd_months": data.ytd_months,
                },
                result=self._round_currency(ytd_avg),
            ))
            candidates.append(("YTD", ytd_avg))

        # Step 3: W2 year 1 average
        if data.w2_year1_earnings and data.w2_year1_months > 0:
            w2_avg = data.w2_year1_earnings / Decimal(data.w2_year1_months)
            steps.append(self._add_step(
                description="W2 Year 1 Average",
                formula="w2_year1_earnings / months",
                inputs={
                    "w2_year1_earnings": data.w2_year1_earnings,
                    "months": data.w2_year1_months,
                },
                result=self._round_currency(w2_avg),
            ))
            candidates.append(("W2 Yr1", w2_avg))

        # Use salary amount unless significantly different from W2s
        monthly_income = salary_monthly
        method_used = "SALARY_STATED"

        # Check for significant variance
        if len(candidates) > 1:
            lowest_name, lowest_val = min(candidates, key=lambda x: x[1])
            if lowest_val < salary_monthly * Decimal("0.9"):
                monthly_income = lowest_val
                method_used = f"SALARY_{lowest_name.upper()}"
                warnings.append(f"Used {lowest_name} (lower than stated salary)")

        steps.append(self._add_step(
            description="Final Salary Selection",
            formula="Check stated vs historical",
            inputs={name: float(value) for name, value in candidates},
            result=self._round_currency(monthly_income),
            notes=method_used
        ))

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.W2_SALARY,
            monthly_income=self._round_currency(monthly_income),
            annual_income=self._round_currency(monthly_income * Decimal("12")),
            calculation_method=method_used,
            calculation_steps=steps,
            confidence_score=95,
            confidence_level=ConfidenceLevel.HIGH,
            warnings=warnings,
        )

    # =========================================================================
    # 3. OVERTIME & BONUS INCOME
    # =========================================================================

    def calculate_ot_bonus(self, data: OTBonusData) -> IncomeCalculationResult:
        """
        Calculate Overtime & Bonus income.

        Per Fannie Mae B3-3.1-01 (03/04/2026): 2-year W-2 history is STILL
        required for variable income (OT/bonus). The reduced requirement only
        applies to fixed/stable base income.

        Uses 2-year averaging, selecting lowest of:
        - YTD Average
        - YTD + 1 Year Average
        - YTD + 2 Year Average
        """
        self._reset_steps()
        steps = []
        warnings = []
        candidates = []

        # Step 1: YTD Average
        if data.ytd_ot_bonus and data.ytd_months > 0:
            ytd_avg = data.ytd_ot_bonus / Decimal(data.ytd_months)
            steps.append(self._add_step(
                description="YTD OT/Bonus Average",
                formula="ytd_ot_bonus / ytd_months",
                inputs={
                    "ytd_ot_bonus": data.ytd_ot_bonus,
                    "ytd_months": data.ytd_months,
                },
                result=self._round_currency(ytd_avg),
            ))
            candidates.append(("YTD", ytd_avg))

        # Step 2: YTD + 1 Year Average
        if data.ytd_ot_bonus and data.year1_ot_bonus:
            total = data.ytd_ot_bonus + data.year1_ot_bonus
            months = data.ytd_months + data.year1_months
            if months > 0:
                avg = total / Decimal(months)
                steps.append(self._add_step(
                    description="YTD + 1 Year Average",
                    formula="(ytd + year1) / total_months",
                    inputs={
                        "ytd_ot_bonus": data.ytd_ot_bonus,
                        "year1_ot_bonus": data.year1_ot_bonus,
                        "total_months": months,
                    },
                    result=self._round_currency(avg),
                ))
                candidates.append(("YTD+1Yr", avg))

        # Step 3: YTD + 2 Year Average
        if data.ytd_ot_bonus and data.year1_ot_bonus and data.year2_ot_bonus:
            total = data.ytd_ot_bonus + data.year1_ot_bonus + data.year2_ot_bonus
            months = data.ytd_months + data.year1_months + data.year2_months
            if months > 0:
                avg = total / Decimal(months)
                steps.append(self._add_step(
                    description="YTD + 2 Year Average",
                    formula="(ytd + year1 + year2) / total_months",
                    inputs={
                        "ytd_ot_bonus": data.ytd_ot_bonus,
                        "year1_ot_bonus": data.year1_ot_bonus,
                        "year2_ot_bonus": data.year2_ot_bonus,
                        "total_months": months,
                    },
                    result=self._round_currency(avg),
                ))
                candidates.append(("YTD+2Yr", avg))

        if not candidates:
            return IncomeCalculationResult(
                success=False,
                income_type=UnifiedIncomeType.OT_BONUS,
                error="No OT/Bonus data provided",
            )

        # Step 4: Use lowest
        lowest_name, monthly_income = min(candidates, key=lambda x: x[1])
        steps.append(self._add_step(
            description="Use Lowest OT/Bonus Income",
            formula="min(all_calculations)",
            inputs={name: float(value) for name, value in candidates},
            result=self._round_currency(monthly_income),
            notes=f"Selected: {lowest_name}"
        ))

        # Require 2-year history for OT/Bonus
        if not data.year2_ot_bonus:
            warnings.append("2-year history required for OT/Bonus - may need additional documentation")

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.OT_BONUS,
            monthly_income=self._round_currency(monthly_income),
            annual_income=self._round_currency(monthly_income * Decimal("12")),
            calculation_method="OT_BONUS_LOWEST",
            averaging_method=AveragingMethod.USE_LOWEST,
            calculation_steps=steps,
            confidence_score=85 if data.year2_ot_bonus else 65,
            confidence_level=ConfidenceLevel.HIGH if data.year2_ot_bonus else ConfidenceLevel.MEDIUM,
            flags={"requires_2_year_history": True},
            warnings=warnings,
        )

    # =========================================================================
    # 4. COMMISSION INCOME
    # =========================================================================

    def calculate_commission(self, data: CommissionData) -> IncomeCalculationResult:
        """
        Calculate Commission income.

        Per Fannie Mae B3-3.1-01 (03/04/2026): 2-year W-2 history is STILL
        required for commission income. The reduced requirement only applies
        to fixed/stable base income.

        Commission - 2106 Unreimbursed Expenses = Net Commission Income
        Uses 2-year averaging of net income.
        """
        self._reset_steps()
        steps = []
        warnings = []
        candidates = []

        # Step 1: YTD Net Commission
        if data.ytd_commission and data.ytd_months > 0:
            ytd_net = data.ytd_commission - data.ytd_expenses_2106
            ytd_monthly = ytd_net / Decimal(data.ytd_months)
            steps.append(self._add_step(
                description="YTD Net Commission",
                formula="(ytd_commission - ytd_2106_expenses) / ytd_months",
                inputs={
                    "ytd_commission": data.ytd_commission,
                    "ytd_expenses_2106": data.ytd_expenses_2106,
                    "net": ytd_net,
                    "ytd_months": data.ytd_months,
                },
                result=self._round_currency(ytd_monthly),
            ))
            candidates.append(("YTD", ytd_monthly))

        # Step 2: Year 1 Net Commission
        year1_monthly = Decimal("0")
        if data.year1_commission:
            year1_net = data.year1_commission - data.year1_expenses_2106
            year1_monthly = year1_net / Decimal(data.year1_months)
            steps.append(self._add_step(
                description="Year 1 Net Commission",
                formula="(year1_commission - year1_2106_expenses) / months",
                inputs={
                    "year1_commission": data.year1_commission,
                    "year1_expenses_2106": data.year1_expenses_2106,
                    "net": year1_net,
                    "months": data.year1_months,
                },
                result=self._round_currency(year1_monthly),
            ))

        # Step 3: Year 2 Net Commission
        year2_monthly = Decimal("0")
        if data.year2_commission:
            year2_net = data.year2_commission - data.year2_expenses_2106
            year2_monthly = year2_net / Decimal(data.year2_months)
            steps.append(self._add_step(
                description="Year 2 Net Commission",
                formula="(year2_commission - year2_2106_expenses) / months",
                inputs={
                    "year2_commission": data.year2_commission,
                    "year2_expenses_2106": data.year2_expenses_2106,
                    "net": year2_net,
                    "months": data.year2_months,
                },
                result=self._round_currency(year2_monthly),
            ))

        # Step 4: Calculate averages
        if candidates and data.year1_commission:
            ytd_val = candidates[0][1] if candidates else Decimal("0")
            ytd_months = data.ytd_months

            # YTD + 1 Year
            total = (ytd_val * ytd_months) + (year1_monthly * data.year1_months)
            total_months = ytd_months + data.year1_months
            avg_1yr = total / Decimal(total_months) if total_months > 0 else Decimal("0")
            steps.append(self._add_step(
                description="YTD + 1 Year Average",
                formula="weighted_average",
                inputs={"ytd_monthly": ytd_val, "year1_monthly": year1_monthly},
                result=self._round_currency(avg_1yr),
            ))
            candidates.append(("YTD+1Yr", avg_1yr))

            # YTD + 2 Year
            if data.year2_commission:
                total = (ytd_val * ytd_months) + (year1_monthly * data.year1_months) + (year2_monthly * data.year2_months)
                total_months = ytd_months + data.year1_months + data.year2_months
                avg_2yr = total / Decimal(total_months) if total_months > 0 else Decimal("0")
                steps.append(self._add_step(
                    description="YTD + 2 Year Average",
                    formula="weighted_average",
                    inputs={"ytd_monthly": ytd_val, "year1_monthly": year1_monthly, "year2_monthly": year2_monthly},
                    result=self._round_currency(avg_2yr),
                ))
                candidates.append(("YTD+2Yr", avg_2yr))

        if not candidates:
            return IncomeCalculationResult(
                success=False,
                income_type=UnifiedIncomeType.COMMISSION,
                error="No commission data provided",
            )

        # Use lowest
        lowest_name, monthly_income = min(candidates, key=lambda x: x[1])
        steps.append(self._add_step(
            description="Use Lowest Net Commission",
            formula="min(all_calculations)",
            inputs={name: float(value) for name, value in candidates},
            result=self._round_currency(monthly_income),
            notes=f"Selected: {lowest_name}"
        ))

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.COMMISSION,
            monthly_income=self._round_currency(monthly_income),
            annual_income=self._round_currency(monthly_income * Decimal("12")),
            calculation_method="COMMISSION_NET_LOWEST",
            averaging_method=AveragingMethod.USE_LOWEST,
            calculation_steps=steps,
            confidence_score=85 if data.year2_commission else 70,
            confidence_level=ConfidenceLevel.HIGH if data.year2_commission else ConfidenceLevel.MEDIUM,
            flags={"requires_2_year_history": True, "has_2106_expenses": data.ytd_expenses_2106 > 0},
            warnings=warnings,
        )

    # =========================================================================
    # 5. OTHER INCOME
    # =========================================================================

    def calculate_other_income(
        self,
        income_type: str,
        monthly_amount: Decimal,
        is_documented: bool = True,
        continuation_months: Optional[int] = None,
    ) -> IncomeCalculationResult:
        """
        Calculate other income types.

        Requires documentation of:
        - Source and amount
        - Continuation (at least 3 years for most investors)
        """
        self._reset_steps()
        steps = []
        warnings = []

        steps.append(self._add_step(
            description=f"Other Income: {income_type}",
            formula="stated_monthly_amount",
            inputs={
                "income_type": income_type,
                "monthly_amount": monthly_amount,
                "is_documented": is_documented,
            },
            result=self._round_currency(monthly_amount),
        ))

        if not is_documented:
            warnings.append("Income documentation required")

        if continuation_months and continuation_months < 36:
            warnings.append(f"Income must continue for at least 36 months (currently {continuation_months})")

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.OTHER_INCOME,
            monthly_income=self._round_currency(monthly_amount),
            annual_income=self._round_currency(monthly_amount * Decimal("12")),
            calculation_method=f"OTHER_{income_type.upper()}",
            calculation_steps=steps,
            confidence_score=80 if is_documented else 50,
            confidence_level=ConfidenceLevel.MEDIUM if is_documented else ConfidenceLevel.LOW,
            warnings=warnings,
        )

    # =========================================================================
    # 6. NON-TAXABLE SOCIAL SECURITY
    # =========================================================================

    def calculate_nontax_ss(self, data: NonTaxSSData) -> IncomeCalculationResult:
        """
        Calculate Non-Taxable Social Security with 25% gross-up.

        With documentation:
        - Taxable portion × 100%
        - Non-taxable portion × 125% (25% gross-up)

        Without documentation:
        - Annual benefit × 85% = taxable portion
        - Annual benefit × 15% × 125% = non-taxable grossed up
        """
        self._reset_steps()
        steps = []

        if data.has_documentation and data.taxable_portion is not None and data.non_taxable_portion is not None:
            # With documentation - use actual split
            taxable_annual = data.taxable_portion
            nontax_grossed = data.non_taxable_portion * Decimal("1.25")

            steps.append(self._add_step(
                description="Taxable Portion (100%)",
                formula="taxable_portion × 1.00",
                inputs={"taxable_portion": data.taxable_portion},
                result=self._round_currency(taxable_annual),
            ))

            steps.append(self._add_step(
                description="Non-Taxable Portion (125% gross-up)",
                formula="non_taxable_portion × 1.25",
                inputs={
                    "non_taxable_portion": data.non_taxable_portion,
                    "gross_up_factor": Decimal("1.25"),
                },
                result=self._round_currency(nontax_grossed),
            ))

            total_annual = taxable_annual + nontax_grossed
            method = "SS_DOCUMENTED"

        else:
            # Without documentation - use 85%/15% split
            taxable_annual = data.annual_benefit * Decimal("0.85")
            nontax_portion = data.annual_benefit * Decimal("0.15")
            nontax_grossed = nontax_portion * Decimal("1.25")

            steps.append(self._add_step(
                description="Taxable Portion (85% of benefit)",
                formula="annual_benefit × 0.85",
                inputs={
                    "annual_benefit": data.annual_benefit,
                    "taxable_rate": Decimal("0.85"),
                },
                result=self._round_currency(taxable_annual),
            ))

            steps.append(self._add_step(
                description="Non-Taxable (15% × 125% gross-up)",
                formula="annual_benefit × 0.15 × 1.25",
                inputs={
                    "annual_benefit": data.annual_benefit,
                    "nontax_rate": Decimal("0.15"),
                    "gross_up": Decimal("1.25"),
                },
                result=self._round_currency(nontax_grossed),
            ))

            total_annual = taxable_annual + nontax_grossed
            method = "SS_UNDOCUMENTED_85_15"

        total_monthly = total_annual / Decimal("12")

        steps.append(self._add_step(
            description="Total Monthly SS Income",
            formula="(taxable + non_taxable_grossed) / 12",
            inputs={
                "taxable_annual": taxable_annual,
                "nontax_grossed_annual": nontax_grossed,
            },
            result=self._round_currency(total_monthly),
        ))

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.NONTAX_SS,
            monthly_income=self._round_currency(total_monthly),
            annual_income=self._round_currency(total_annual),
            calculation_method=method,
            calculation_steps=steps,
            confidence_score=95 if data.has_documentation else 80,
            confidence_level=ConfidenceLevel.HIGH if data.has_documentation else ConfidenceLevel.MEDIUM,
            flags={"grossed_up": True, "documented": data.has_documentation},
        )

    # =========================================================================
    # 7. NON-TAXABLE OTHER INCOME
    # =========================================================================

    def calculate_nontax_other(self, data: NonTaxOtherData) -> IncomeCalculationResult:
        """
        Calculate other non-taxable income with 25% gross-up.

        Types: Pension, IRA distributions, child support, disability, etc.
        """
        self._reset_steps()
        steps = []

        if data.is_taxable:
            # Taxable income - no gross-up
            annual_income = data.annual_amount
            method = f"NONTAX_OTHER_{data.income_type.upper()}_TAXABLE"
            grossed_up = False
        else:
            # Non-taxable - apply 25% gross-up
            annual_income = data.annual_amount * Decimal("1.25")
            method = f"NONTAX_OTHER_{data.income_type.upper()}_GROSSED"
            grossed_up = True

        steps.append(self._add_step(
            description=f"{data.income_type} Income",
            formula="annual_amount × 1.25" if not data.is_taxable else "annual_amount",
            inputs={
                "income_type": data.income_type,
                "annual_amount": data.annual_amount,
                "is_taxable": data.is_taxable,
                "gross_up_applied": not data.is_taxable,
            },
            result=self._round_currency(annual_income),
        ))

        monthly_income = annual_income / Decimal("12")

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.NONTAX_OTHER,
            monthly_income=self._round_currency(monthly_income),
            annual_income=self._round_currency(annual_income),
            calculation_method=method,
            calculation_steps=steps,
            confidence_score=85,
            confidence_level=ConfidenceLevel.MEDIUM,
            flags={"grossed_up": grossed_up},
        )

    # =========================================================================
    # 8-11. BANK STATEMENT INCOME (Non-QM)
    # =========================================================================

    def calculate_bank_statement_personal(self, data: BankStatementPersonalData) -> IncomeCalculationResult:
        """
        Calculate personal bank statement income.

        Total deposits × (1 - expense_factor) / months
        """
        self._reset_steps()
        steps = []
        warnings = []

        if len(data.monthly_deposits) < 12:
            warnings.append(f"Only {len(data.monthly_deposits)} months of statements (12 recommended)")

        total_deposits = sum(data.monthly_deposits)
        avg_deposits = total_deposits / Decimal(len(data.monthly_deposits))

        steps.append(self._add_step(
            description="Average Monthly Deposits",
            formula="total_deposits / months",
            inputs={
                "total_deposits": total_deposits,
                "months": len(data.monthly_deposits),
            },
            result=self._round_currency(avg_deposits),
        ))

        # Apply expense factor
        expense_deduction = avg_deposits * (data.expense_factor / Decimal("100"))
        net_income = avg_deposits - expense_deduction

        steps.append(self._add_step(
            description=f"Apply {data.expense_factor}% Expense Factor",
            formula=f"avg_deposits × (1 - {data.expense_factor}/100)",
            inputs={
                "avg_deposits": avg_deposits,
                "expense_factor_pct": data.expense_factor,
            },
            result=self._round_currency(net_income),
        ))

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.BANK_STATEMENT_PERSONAL,
            monthly_income=self._round_currency(net_income),
            annual_income=self._round_currency(net_income * Decimal("12")),
            calculation_method=f"BANK_PERSONAL_{data.months_analyzed}MO",
            calculation_steps=steps,
            confidence_score=75,
            confidence_level=ConfidenceLevel.MEDIUM,
            flags={"is_nonqm": True},
            warnings=warnings,
        )

    def calculate_bank_statement_business(self, data: BankStatementBusinessData) -> IncomeCalculationResult:
        """
        Calculate business bank statement income.

        Method 1: Deposits - Expenses
        Method 2: Gross deposits × (1 - expense_ratio)
        Method 3: P&L verification against deposits
        """
        self._reset_steps()
        steps = []
        warnings = []

        if len(data.monthly_deposits) < 12:
            warnings.append(f"Only {len(data.monthly_deposits)} months of statements (12-24 recommended)")

        total_deposits = sum(data.monthly_deposits)
        avg_deposits = total_deposits / Decimal(len(data.monthly_deposits))

        steps.append(self._add_step(
            description="Average Monthly Gross Deposits",
            formula="total_deposits / months",
            inputs={
                "total_deposits": total_deposits,
                "months": len(data.monthly_deposits),
            },
            result=self._round_currency(avg_deposits),
        ))

        if data.method == 1 and data.monthly_expenses:
            # Method 1: Actual deposits minus actual expenses
            total_expenses = sum(data.monthly_expenses)
            avg_expenses = total_expenses / Decimal(len(data.monthly_expenses))
            net_income = avg_deposits - avg_expenses
            method_name = "BANK_BUSINESS_M1_ACTUAL"

            steps.append(self._add_step(
                description="Method 1: Deposits - Expenses",
                formula="avg_deposits - avg_expenses",
                inputs={
                    "avg_deposits": avg_deposits,
                    "avg_expenses": avg_expenses,
                },
                result=self._round_currency(net_income),
            ))

        elif data.method == 2:
            # Method 2: Apply expense ratio
            net_income = avg_deposits * (Decimal("1") - data.expense_ratio / Decimal("100"))
            method_name = f"BANK_BUSINESS_M2_{data.expense_ratio}PCT"

            steps.append(self._add_step(
                description=f"Method 2: Deposits × (1 - {data.expense_ratio}%)",
                formula="avg_deposits × expense_ratio",
                inputs={
                    "avg_deposits": avg_deposits,
                    "expense_ratio_pct": data.expense_ratio,
                },
                result=self._round_currency(net_income),
            ))

        elif data.method == 3 and data.pl_net_income:
            # Method 3: P&L verified against deposits
            pl_monthly = data.pl_net_income / Decimal("12")

            # Verify P&L is within reasonable range of deposits
            deposit_based = avg_deposits * Decimal("0.5")  # 50% expense assumption

            if pl_monthly > deposit_based * Decimal("1.2"):
                warnings.append("P&L income exceeds deposit-based estimate - review required")
                net_income = deposit_based
            else:
                net_income = pl_monthly

            method_name = "BANK_BUSINESS_M3_PL"

            steps.append(self._add_step(
                description="Method 3: P&L Verification",
                formula="p&l_net_income / 12 (verified against deposits)",
                inputs={
                    "pl_net_income": data.pl_net_income,
                    "pl_monthly": pl_monthly,
                    "deposit_based_estimate": deposit_based,
                },
                result=self._round_currency(net_income),
            ))
        else:
            # Default to Method 2 with 50%
            net_income = avg_deposits * Decimal("0.5")
            method_name = "BANK_BUSINESS_M2_DEFAULT"

            steps.append(self._add_step(
                description="Default: 50% Expense Factor",
                formula="avg_deposits × 0.5",
                inputs={"avg_deposits": avg_deposits},
                result=self._round_currency(net_income),
            ))

        # Apply ownership percentage
        if data.ownership_percentage < Decimal("100"):
            net_income = net_income * (data.ownership_percentage / Decimal("100"))
            steps.append(self._add_step(
                description=f"Apply {data.ownership_percentage}% Ownership",
                formula="net_income × ownership_pct",
                inputs={"ownership_percentage": data.ownership_percentage},
                result=self._round_currency(net_income),
            ))

        income_type = {
            1: UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M1,
            2: UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M2,
            3: UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M3,
        }.get(data.method, UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M2)

        return IncomeCalculationResult(
            success=True,
            income_type=income_type,
            monthly_income=self._round_currency(net_income),
            annual_income=self._round_currency(net_income * Decimal("12")),
            calculation_method=method_name,
            calculation_steps=steps,
            confidence_score=70,
            confidence_level=ConfidenceLevel.MEDIUM,
            flags={"is_nonqm": True, "method": data.method},
            warnings=warnings,
        )

    # =========================================================================
    # 12. RENTAL INCOME (SCHEDULE E)
    # =========================================================================

    def calculate_rental_schedule_e(self, data: RentalScheduleEData) -> IncomeCalculationResult:
        """
        Calculate Rental Income from Schedule E.

        Formula:
        Line 3 Gross Rents
        - Line 20 Total Expenses
        + Line 18 Depreciation (add-back)
        + Line 19 Amortization/Casualty (add-back)
        - PITIA (Insurance, Mortgage Int, Taxes, HOA)
        = Annual Rental Income/Loss
        / 12 = Monthly Net Rental Income
        """
        self._reset_steps()
        steps = []
        warnings = []

        # Step 1: Gross Rents
        steps.append(self._add_step(
            description="Line 3: Gross Rents Received",
            formula="schedule_e_line_3",
            inputs={"gross_rents": data.gross_rents_line3},
            result=data.gross_rents_line3,
        ))

        # Step 2: Less Total Expenses
        after_expenses = data.gross_rents_line3 - data.total_expenses_line20
        steps.append(self._add_step(
            description="Less Line 20: Total Expenses",
            formula="gross_rents - total_expenses",
            inputs={
                "gross_rents": data.gross_rents_line3,
                "total_expenses": data.total_expenses_line20,
            },
            result=self._round_currency(after_expenses),
        ))

        # Step 3: Add back Depreciation
        after_depreciation = after_expenses + data.depreciation_line18
        steps.append(self._add_step(
            description="Add Line 18: Depreciation (Add-back)",
            formula="subtotal + depreciation",
            inputs={"depreciation": data.depreciation_line18},
            result=self._round_currency(after_depreciation),
        ))

        # Step 4: Add back Amortization/Casualty
        after_amort = after_depreciation + data.amortization_casualty_line19
        steps.append(self._add_step(
            description="Add Line 19: Amortization/Casualty Loss (Add-back)",
            formula="subtotal + amortization_casualty",
            inputs={"amortization_casualty": data.amortization_casualty_line19},
            result=self._round_currency(after_amort),
        ))

        # Step 5: Calculate Annual PITIA
        annual_insurance = data.monthly_insurance * Decimal("12")
        annual_mortgage_int = data.monthly_mortgage_interest * Decimal("12")
        annual_taxes = data.monthly_taxes * Decimal("12")
        annual_hoa = data.monthly_hoa * Decimal("12")
        total_pitia = annual_insurance + annual_mortgage_int + annual_taxes + annual_hoa

        steps.append(self._add_step(
            description="Calculate Annual PITIA",
            formula="(insurance + mortgage_int + taxes + hoa) × 12",
            inputs={
                "monthly_insurance": data.monthly_insurance,
                "monthly_mortgage_interest": data.monthly_mortgage_interest,
                "monthly_taxes": data.monthly_taxes,
                "monthly_hoa": data.monthly_hoa,
                "annual_pitia": total_pitia,
            },
            result=self._round_currency(total_pitia),
        ))

        # Step 6: Net Rental Income/Loss
        annual_rental_income = after_amort - total_pitia
        steps.append(self._add_step(
            description="Annual Rental Income/Loss",
            formula="subtotal - annual_pitia",
            inputs={
                "subtotal": after_amort,
                "annual_pitia": total_pitia,
            },
            result=self._round_currency(annual_rental_income),
        ))

        # Step 7: Monthly
        monthly_rental_income = annual_rental_income / Decimal("12")
        steps.append(self._add_step(
            description="Monthly Net Rental Income/Loss",
            formula="annual_rental_income / 12",
            inputs={"annual_rental_income": annual_rental_income},
            result=self._round_currency(monthly_rental_income),
        ))

        # Check for rental loss
        if monthly_rental_income < 0:
            warnings.append("Property shows rental loss - will be counted as liability")

        # If we have year 2 data, average
        if data.year2_gross_rents is not None:
            # Calculate year 2
            yr2_after_exp = data.year2_gross_rents - (data.year2_total_expenses or data.total_expenses_line20)
            yr2_after_dep = yr2_after_exp + (data.year2_depreciation or data.depreciation_line18)
            yr2_net = yr2_after_dep - total_pitia
            yr2_monthly = yr2_net / Decimal("12")

            # Average
            avg_monthly = (monthly_rental_income + yr2_monthly) / Decimal("2")

            steps.append(self._add_step(
                description="2-Year Average Monthly Rental",
                formula="(year1_monthly + year2_monthly) / 2",
                inputs={
                    "year1_monthly": monthly_rental_income,
                    "year2_monthly": yr2_monthly,
                },
                result=self._round_currency(avg_monthly),
            ))

            monthly_rental_income = avg_monthly

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.RENTAL_SCHEDULE_E,
            monthly_income=self._round_currency(monthly_rental_income),
            annual_income=self._round_currency(monthly_rental_income * Decimal("12")),
            calculation_method="SCHEDULE_E_WITH_PITIA",
            calculation_steps=steps,
            confidence_score=85,
            confidence_level=ConfidenceLevel.HIGH,
            flags={
                "is_loss": monthly_rental_income < 0,
                "depreciation_added_back": data.depreciation_line18 > 0,
            },
            warnings=warnings,
        )

    # =========================================================================
    # 13. SELF-EMPLOYMENT 1084 (Fannie Mae)
    # =========================================================================

    def calculate_self_employment_1084(self, data: SelfEmployment1084Data) -> IncomeCalculationResult:
        """
        Calculate Self-Employment income per Fannie Mae Form 1084.

        Supports:
        - Schedule C (Sole Proprietorship)
        - K-1 1065 (Partnership)
        - K-1 1120S (S-Corporation)
        - Form 1120 (C-Corporation - requires 100% ownership)
        """
        self._reset_steps()
        steps = []
        warnings = []
        flags = {}

        # Determine business type and calculate accordingly
        total_annual_income = Decimal("0")

        # ==================== SCHEDULE C ====================
        if data.schedule_c_net_profit_line31 != 0 or data.schedule_c_depreciation_line13 > 0:
            # Line 31: Net Profit/Loss
            schedule_c_income = data.schedule_c_net_profit_line31
            steps.append(self._add_step(
                description="Schedule C Line 31: Net Profit/Loss",
                formula="schedule_c_net_profit",
                inputs={"net_profit": data.schedule_c_net_profit_line31},
                result=data.schedule_c_net_profit_line31,
            ))

            # Add-backs
            # Depreciation
            schedule_c_income += data.schedule_c_depreciation_line13
            steps.append(self._add_step(
                description="Add: Depreciation (Line 13)",
                formula="subtotal + depreciation",
                inputs={"depreciation": data.schedule_c_depreciation_line13},
                result=self._round_currency(schedule_c_income),
            ))

            # Depletion
            if data.schedule_c_depletion_line12 > 0:
                schedule_c_income += data.schedule_c_depletion_line12
                steps.append(self._add_step(
                    description="Add: Depletion (Line 12)",
                    formula="subtotal + depletion",
                    inputs={"depletion": data.schedule_c_depletion_line12},
                    result=self._round_currency(schedule_c_income),
                ))

            # Business Use of Home
            if data.schedule_c_business_use_home > 0:
                schedule_c_income += data.schedule_c_business_use_home
                steps.append(self._add_step(
                    description="Add: Business Use of Home",
                    formula="subtotal + business_use_home",
                    inputs={"business_use_home": data.schedule_c_business_use_home},
                    result=self._round_currency(schedule_c_income),
                ))

            # Mileage depreciation add-back
            if data.schedule_c_mileage > 0 and data.mileage_depreciation_rate > 0:
                mileage_addback = data.schedule_c_mileage * data.mileage_depreciation_rate
                schedule_c_income += mileage_addback
                steps.append(self._add_step(
                    description="Add: Mileage Depreciation",
                    formula="miles × depreciation_rate",
                    inputs={
                        "miles": data.schedule_c_mileage,
                        "rate_per_mile": data.mileage_depreciation_rate,
                    },
                    result=self._round_currency(mileage_addback),
                    notes="IRS depreciation component of mileage deduction",
                ))

            total_annual_income += schedule_c_income
            flags["has_schedule_c"] = True

        # ==================== K-1 1065 PARTNERSHIP ====================
        if data.k1_1065_ordinary_income_line1 != 0 or data.k1_1065_guaranteed_payments_line4 > 0:
            k1_income = Decimal("0")

            # Ordinary income
            k1_income += data.k1_1065_ordinary_income_line1
            steps.append(self._add_step(
                description="K-1 1065 Line 1: Ordinary Income",
                formula="ordinary_income",
                inputs={"ordinary_income": data.k1_1065_ordinary_income_line1},
                result=data.k1_1065_ordinary_income_line1,
            ))

            # Guaranteed payments
            k1_income += data.k1_1065_guaranteed_payments_line4
            steps.append(self._add_step(
                description="K-1 1065 Line 4: Guaranteed Payments",
                formula="subtotal + guaranteed_payments",
                inputs={"guaranteed_payments": data.k1_1065_guaranteed_payments_line4},
                result=self._round_currency(k1_income),
            ))

            # Self-employment earnings if provided
            if data.k1_1065_self_employment_earnings > 0:
                # Verify consistency
                if abs(data.k1_1065_self_employment_earnings - k1_income) > Decimal("100"):
                    warnings.append("K-1 self-employment earnings differs from ordinary + guaranteed")

            # Apply ownership percentage
            if data.ownership_percentage < Decimal("100"):
                k1_income = k1_income * (data.ownership_percentage / Decimal("100"))
                steps.append(self._add_step(
                    description=f"Apply {data.ownership_percentage}% Ownership",
                    formula="k1_income × ownership_pct",
                    inputs={"ownership_pct": data.ownership_percentage},
                    result=self._round_currency(k1_income),
                ))

                if data.ownership_percentage < Decimal("25"):
                    warnings.append("Ownership < 25% - income may not be usable")
                    flags["ownership_below_25"] = True

            total_annual_income += k1_income
            flags["has_k1_1065"] = True

        # ==================== K-1 1120S S-CORP ====================
        if data.k1_1120s_ordinary_income_line1 != 0:
            k1s_income = Decimal("0")

            # Ordinary income
            k1s_income += data.k1_1120s_ordinary_income_line1
            steps.append(self._add_step(
                description="K-1 1120S Line 1: Ordinary Income",
                formula="ordinary_income",
                inputs={"ordinary_income": data.k1_1120s_ordinary_income_line1},
                result=data.k1_1120s_ordinary_income_line1,
            ))

            # Net rental income/loss
            if data.k1_1120s_net_rental_line2 != 0:
                k1s_income += data.k1_1120s_net_rental_line2
                steps.append(self._add_step(
                    description="K-1 1120S Line 2: Net Rental Income",
                    formula="subtotal + net_rental",
                    inputs={"net_rental": data.k1_1120s_net_rental_line2},
                    result=self._round_currency(k1s_income),
                ))

            # Apply ownership
            if data.ownership_percentage < Decimal("100"):
                k1s_income = k1s_income * (data.ownership_percentage / Decimal("100"))
                steps.append(self._add_step(
                    description=f"Apply {data.ownership_percentage}% Ownership",
                    formula="k1s_income × ownership_pct",
                    inputs={"ownership_pct": data.ownership_percentage},
                    result=self._round_currency(k1s_income),
                ))

            total_annual_income += k1s_income
            flags["has_k1_1120s"] = True

        # ==================== FORM 1120 C-CORP ====================
        if data.form_1120_taxable_income_line30 != 0:
            if data.ownership_percentage < Decimal("100"):
                warnings.append("C-Corp income requires 100% ownership")
                flags["ccorp_not_100_pct"] = True
            else:
                corp_income = data.form_1120_taxable_income_line30

                steps.append(self._add_step(
                    description="Form 1120 Line 30: Taxable Income",
                    formula="taxable_income",
                    inputs={"taxable_income": data.form_1120_taxable_income_line30},
                    result=data.form_1120_taxable_income_line30,
                ))

                # Add total tax (treated as distribution to owner)
                corp_income += data.form_1120_total_tax_line31
                steps.append(self._add_step(
                    description="Add: Total Tax (Line 31)",
                    formula="subtotal + total_tax",
                    inputs={"total_tax": data.form_1120_total_tax_line31},
                    result=self._round_currency(corp_income),
                ))

                # Add depreciation
                corp_income += data.form_1120_depreciation_line20
                steps.append(self._add_step(
                    description="Add: Depreciation (Line 20)",
                    formula="subtotal + depreciation",
                    inputs={"depreciation": data.form_1120_depreciation_line20},
                    result=self._round_currency(corp_income),
                ))

                # Subtract dividends paid (already received)
                corp_income -= data.form_1120_dividends_paid
                steps.append(self._add_step(
                    description="Less: Dividends Paid",
                    formula="subtotal - dividends_paid",
                    inputs={"dividends_paid": data.form_1120_dividends_paid},
                    result=self._round_currency(corp_income),
                ))

                total_annual_income += corp_income
                flags["has_form_1120"] = True

        # ==================== FINAL CALCULATION ====================
        monthly_income = total_annual_income / Decimal("12")

        steps.append(self._add_step(
            description="Total Annual Self-Employment Income",
            formula="sum(all_business_income)",
            inputs={"total_annual": total_annual_income},
            result=self._round_currency(total_annual_income),
        ))

        steps.append(self._add_step(
            description="Monthly Self-Employment Income",
            formula="total_annual / 12",
            inputs={"total_annual": total_annual_income},
            result=self._round_currency(monthly_income),
        ))

        # Check for loss
        if monthly_income < 0:
            warnings.append("Business shows loss - income is negative")
            flags["is_loss"] = True

        return IncomeCalculationResult(
            success=True,
            income_type=UnifiedIncomeType.SELF_EMPLOYMENT_1084,
            monthly_income=self._round_currency(monthly_income),
            annual_income=self._round_currency(total_annual_income),
            calculation_method="FANNIE_MAE_1084",
            calculation_steps=steps,
            confidence_score=80,
            confidence_level=ConfidenceLevel.MEDIUM,
            flags=flags,
            warnings=warnings,
        )


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_calculator_instance: Optional[UnifiedIncomeCalculator] = None


def get_unified_income_calculator() -> UnifiedIncomeCalculator:
    """Get singleton instance of UnifiedIncomeCalculator."""
    global _calculator_instance
    if _calculator_instance is None:
        _calculator_instance = UnifiedIncomeCalculator()
    return _calculator_instance
