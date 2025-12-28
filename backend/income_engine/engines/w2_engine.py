"""
W-2 and Paystub Income Calculation Engine

Calculates qualifying income from W-2 forms and paystubs following
agency guidelines for:
- Base salary/wages
- Overtime (requires 2-year history)
- Bonus (requires 2-year history)
- Commission (requires 2-year history)

Key Rules:
- YTD annualization for base wages
- 2-year average for variable income (OT, bonus, commission)
- Use lower year if declining
- Verify consistency between paystub YTD and W-2
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
import logging

from ..base import (
    BaseIncomeEngine,
    EngineResult,
    IncomeStream,
    IncomeFlag,
    FlagRuleId,
)
from ..data_contracts import (
    IncomeStreamType,
    FlagSeverity,
    TrendDirection,
    W2Facts,
    PaystubFacts,
)

logger = logging.getLogger(__name__)


class W2Engine(BaseIncomeEngine):
    """
    W-2 and Paystub Income Calculation Engine.

    Handles:
    - Base wages (YTD annualization)
    - Overtime (2-year average)
    - Bonus (2-year average)
    - Commission (2-year average)
    """

    ENGINE_NAME = "W2Engine"
    ENGINE_VERSION = "1.0"

    # Pay frequency multipliers for annualization
    PAY_FREQUENCY_MULTIPLIERS = {
        "WEEKLY": 52,
        "BIWEEKLY": 26,
        "SEMIMONTHLY": 24,
        "MONTHLY": 12,
    }

    def get_supported_stream_types(self) -> List[IncomeStreamType]:
        return [
            IncomeStreamType.W2_BASE,
            IncomeStreamType.W2_OVERTIME,
            IncomeStreamType.W2_BONUS,
            IncomeStreamType.W2_COMMISSION,
        ]

    def calculate(
        self,
        w2_facts: List[W2Facts] = None,
        paystub_facts: List[PaystubFacts] = None,
        employer_name: Optional[str] = None,
    ) -> EngineResult:
        """
        Calculate W-2/paystub income.

        Args:
            w2_facts: List of W2Facts (should have 1-2 years per employer)
            paystub_facts: List of PaystubFacts (most recent paystubs)
            employer_name: Optional filter for specific employer

        Returns:
            EngineResult with calculated income streams
        """
        try:
            w2_list = w2_facts or []
            paystub_list = paystub_facts or []

            if not w2_list and not paystub_list:
                return self.create_result(
                    success=True,
                    income_streams=[],
                    flags=[
                        self.create_info_flag(
                            FlagRuleId.MISSING_REQUIRED_DOCUMENT,
                            "No W-2 or paystub documents provided for W-2 income calculation"
                        )
                    ]
                )

            # Group by employer
            employers = self._group_by_employer(w2_list, paystub_list)

            # Filter by employer if specified
            if employer_name:
                employers = {k: v for k, v in employers.items()
                           if employer_name.lower() in k.lower()}

            income_streams = []
            flags = []

            for emp_name, emp_data in employers.items():
                emp_streams, emp_flags = self._calculate_employer_income(
                    emp_name,
                    emp_data["w2s"],
                    emp_data["paystubs"]
                )
                income_streams.extend(emp_streams)
                flags.extend(emp_flags)

            return self.create_result(
                success=True,
                income_streams=income_streams,
                flags=flags
            )

        except Exception as e:
            logger.exception(f"W2Engine calculation error: {e}")
            return self.create_error_result(str(e))

    def _group_by_employer(
        self,
        w2_list: List[W2Facts],
        paystub_list: List[PaystubFacts]
    ) -> Dict[str, Dict[str, List]]:
        """Group W-2s and paystubs by employer name."""
        employers = {}

        for w2 in w2_list:
            emp_key = w2.employer_name.upper().strip()
            if emp_key not in employers:
                employers[emp_key] = {"w2s": [], "paystubs": []}
            employers[emp_key]["w2s"].append(w2)

        for paystub in paystub_list:
            emp_key = paystub.employer_name.upper().strip()
            if emp_key not in employers:
                employers[emp_key] = {"w2s": [], "paystubs": []}
            employers[emp_key]["paystubs"].append(paystub)

        return employers

    def _calculate_employer_income(
        self,
        employer_name: str,
        w2s: List[W2Facts],
        paystubs: List[PaystubFacts]
    ) -> Tuple[List[IncomeStream], List[IncomeFlag]]:
        """Calculate income for a single employer."""
        income_streams = []
        flags = []

        # Sort W-2s by year (most recent first)
        w2s_sorted = sorted(w2s, key=lambda x: x.tax_year, reverse=True)

        # Get most recent paystub
        paystubs_sorted = sorted(paystubs, key=lambda x: x.pay_date, reverse=True)
        recent_paystub = paystubs_sorted[0] if paystubs_sorted else None

        # Calculate base wages
        base_stream, base_flags = self._calculate_base_wages(
            employer_name, w2s_sorted, recent_paystub
        )
        if base_stream:
            income_streams.append(base_stream)
        flags.extend(base_flags)

        # Calculate variable income components
        for income_type, stream_type in [
            ("overtime", IncomeStreamType.W2_OVERTIME),
            ("bonus", IncomeStreamType.W2_BONUS),
            ("commission", IncomeStreamType.W2_COMMISSION),
        ]:
            var_stream, var_flags = self._calculate_variable_income(
                employer_name, w2s_sorted, recent_paystub, income_type, stream_type
            )
            if var_stream:
                income_streams.append(var_stream)
            flags.extend(var_flags)

        return income_streams, flags

    def _calculate_base_wages(
        self,
        employer_name: str,
        w2s: List[W2Facts],
        recent_paystub: Optional[PaystubFacts]
    ) -> Tuple[Optional[IncomeStream], List[IncomeFlag]]:
        """Calculate base wages income."""
        flags = []
        calculation_steps = []
        document_ids = []
        tax_years = []

        # Prefer paystub YTD annualization if available
        if recent_paystub and recent_paystub.ytd_gross > 0:
            monthly_income, steps = self._annualize_paystub_ytd(recent_paystub)
            calculation_steps.extend(steps)
            document_ids.append(recent_paystub.document_id)

            inputs = {
                "method": "paystub_ytd_annualization",
                "ytd_gross": float(recent_paystub.ytd_gross),
                "pay_date": recent_paystub.pay_date.isoformat(),
                "pay_frequency": recent_paystub.pay_frequency,
            }

        elif w2s:
            # Use W-2 box 1
            latest_w2 = w2s[0]
            annual_income = Decimal(str(latest_w2.box1_wages))
            monthly_income = self.annual_to_monthly(annual_income)

            calculation_steps.append(self.log_step(
                "Using W-2 Box 1 wages",
                formula="monthly = box1_wages / 12",
                inputs={"box1_wages": float(annual_income), "tax_year": latest_w2.tax_year},
                result=float(monthly_income)
            ))

            document_ids.append(latest_w2.document_id)
            tax_years.append(latest_w2.tax_year)

            inputs = {
                "method": "w2_box1",
                "box1_wages": float(annual_income),
                "tax_year": latest_w2.tax_year,
            }

        else:
            return None, [
                self.create_warning_flag(
                    FlagRuleId.MISSING_REQUIRED_DOCUMENT,
                    f"No W-2 or paystub available for {employer_name} base wages"
                )
            ]

        # Verify W-2 vs paystub YTD consistency if both available
        if recent_paystub and w2s and recent_paystub.pay_date.year == w2s[0].tax_year:
            ytd_diff = abs(recent_paystub.ytd_gross - w2s[0].box1_wages)
            if ytd_diff > Decimal("1000"):
                flags.append(self.create_warning_flag(
                    FlagRuleId.W2_YTD_MISMATCH,
                    f"Paystub YTD (${recent_paystub.ytd_gross:,.2f}) differs from "
                    f"W-2 Box 1 (${w2s[0].box1_wages:,.2f}) by ${ytd_diff:,.2f}",
                    affected_stream=f"{employer_name} Base"
                ))

        stream = self.create_income_stream(
            stream_type=IncomeStreamType.W2_BASE,
            stream_name=f"{employer_name} - Base Wages",
            monthly_income=monthly_income,
            calculation_inputs=inputs,
            calculation_steps=calculation_steps,
            document_ids=document_ids,
            tax_years=tax_years,
        )

        return stream, flags

    def _annualize_paystub_ytd(
        self,
        paystub: PaystubFacts
    ) -> Tuple[Decimal, List[Dict]]:
        """
        Annualize paystub YTD earnings.

        Formula: (YTD_Gross / Days_Elapsed) * 365 / 12
        """
        steps = []

        # Calculate days elapsed in year
        year_start = date(paystub.pay_date.year, 1, 1)
        days_elapsed = (paystub.pay_date - year_start).days + 1

        steps.append(self.log_step(
            "Calculate days elapsed in year",
            inputs={"pay_date": paystub.pay_date.isoformat(), "year_start": year_start.isoformat()},
            result=days_elapsed
        ))

        # Annualize
        if days_elapsed > 0:
            daily_income = paystub.ytd_gross / days_elapsed
            annual_income = daily_income * 365
            monthly_income = annual_income / 12
        else:
            monthly_income = Decimal("0")

        steps.append(self.log_step(
            "Annualize YTD gross",
            formula="(ytd_gross / days_elapsed) * 365 / 12",
            inputs={
                "ytd_gross": float(paystub.ytd_gross),
                "days_elapsed": days_elapsed
            },
            result=float(monthly_income)
        ))

        return self.round_currency(monthly_income), steps

    def _calculate_variable_income(
        self,
        employer_name: str,
        w2s: List[W2Facts],
        recent_paystub: Optional[PaystubFacts],
        income_type: str,
        stream_type: IncomeStreamType
    ) -> Tuple[Optional[IncomeStream], List[IncomeFlag]]:
        """
        Calculate variable income (overtime, bonus, commission).

        Requires 2-year history. Uses 2-year average unless declining.
        """
        flags = []
        calculation_steps = []

        # Get YTD amounts from paystub
        ytd_amounts = self._get_variable_ytd(recent_paystub, income_type)

        # Get W-2 history (need to derive from total vs base)
        w2_amounts = self._get_variable_from_w2s(w2s, income_type)

        if not w2_amounts and ytd_amounts.get("current", Decimal("0")) == 0:
            # No variable income of this type
            return None, []

        document_ids = []
        tax_years = []

        if len(w2_amounts) >= 2:
            # Have 2-year history - calculate 2-year average
            year1_income = w2_amounts[0]["amount"]
            year2_income = w2_amounts[1]["amount"]

            average, direction, trend_pct, uses_lower = self.calculate_two_year_average(
                year1_income, year2_income
            )

            monthly_income = self.annual_to_monthly(average)

            calculation_steps.append(self.log_step(
                f"Two-year {income_type} average calculation",
                formula="average = (year1 + year2) / 2, use lower if declining",
                inputs={
                    "year1": float(year1_income),
                    "year2": float(year2_income),
                    "year1_tax_year": w2_amounts[0]["tax_year"],
                    "year2_tax_year": w2_amounts[1]["tax_year"],
                },
                result=float(monthly_income)
            ))

            for w2_data in w2_amounts[:2]:
                document_ids.append(w2_data["document_id"])
                tax_years.append(w2_data["tax_year"])

            # Flag if declining
            if direction == TrendDirection.DECLINING:
                flags.append(self.create_warning_flag(
                    FlagRuleId.W2_VARIABLE_INCOME_DECLINING,
                    f"{income_type.title()} income declining {abs(trend_pct):.1f}% - "
                    f"using lower year (${year1_income:,.2f})",
                    affected_stream=f"{employer_name} {income_type.title()}"
                ))

            stream = self.create_income_stream(
                stream_type=stream_type,
                stream_name=f"{employer_name} - {income_type.title()}",
                monthly_income=monthly_income,
                calculation_inputs={
                    "method": "two_year_average",
                    "year1_income": float(year1_income),
                    "year2_income": float(year2_income),
                },
                calculation_steps=calculation_steps,
                document_ids=document_ids,
                tax_years=tax_years,
                trending_direction=direction,
                trending_percentage=trend_pct,
                year1_income=year1_income,
                year2_income=year2_income,
                uses_lower_year=uses_lower,
            )

            return stream, flags

        elif len(w2_amounts) == 1 or ytd_amounts.get("current", Decimal("0")) > 0:
            # Only 1 year - flag insufficient history
            flags.append(self.create_warning_flag(
                FlagRuleId.W2_INSUFFICIENT_HISTORY,
                f"Only 1 year of {income_type} history available. "
                f"Variable income typically requires 2-year history.",
                affected_stream=f"{employer_name} {income_type.title()}"
            ))

            # Still calculate but flag it
            if w2_amounts:
                year1_income = w2_amounts[0]["amount"]
                monthly_income = self.annual_to_monthly(year1_income)
                document_ids.append(w2_amounts[0]["document_id"])
                tax_years.append(w2_amounts[0]["tax_year"])
            else:
                # Use YTD annualized
                monthly_income = ytd_amounts.get("monthly", Decimal("0"))
                if recent_paystub:
                    document_ids.append(recent_paystub.document_id)

            if monthly_income > 0:
                stream = self.create_income_stream(
                    stream_type=stream_type,
                    stream_name=f"{employer_name} - {income_type.title()}",
                    monthly_income=monthly_income,
                    calculation_inputs={
                        "method": "single_year",
                        "annual_income": float(self.monthly_to_annual(monthly_income)),
                        "warning": "insufficient_history"
                    },
                    calculation_steps=calculation_steps,
                    document_ids=document_ids,
                    tax_years=tax_years,
                )
                return stream, flags

        return None, flags

    def _get_variable_ytd(
        self,
        paystub: Optional[PaystubFacts],
        income_type: str
    ) -> Dict[str, Decimal]:
        """Get YTD variable income from paystub."""
        if not paystub:
            return {}

        ytd_map = {
            "overtime": paystub.ytd_overtime,
            "bonus": paystub.ytd_bonus,
            "commission": paystub.ytd_commission,
        }

        ytd_amount = ytd_map.get(income_type, Decimal("0"))

        if ytd_amount > 0:
            # Annualize
            year_start = date(paystub.pay_date.year, 1, 1)
            days_elapsed = (paystub.pay_date - year_start).days + 1
            if days_elapsed > 0:
                annual = (ytd_amount / days_elapsed) * 365
                monthly = annual / 12
                return {"current": ytd_amount, "monthly": self.round_currency(monthly)}

        return {"current": Decimal("0"), "monthly": Decimal("0")}

    def _get_variable_from_w2s(
        self,
        w2s: List[W2Facts],
        income_type: str
    ) -> List[Dict[str, Any]]:
        """
        Extract variable income component from W-2s.

        Note: W-2 Box 1 is total compensation. We need separate reporting
        or must use paystub YTD breakdown. This is a simplified approach
        that assumes variable income is tracked separately in the system.
        """
        # In real implementation, this would pull from the income_sources
        # table where variable components are tracked separately
        results = []

        # For now, use Box 12 codes if available
        # Code E = Elective deferrals to 401(k)
        # Some employers report bonus/commission breakdown

        for w2 in w2s:
            # This is a placeholder - real implementation would need
            # employer-specific mapping or separate tracking
            if income_type == "bonus" and "BONUS" in w2.box14_other:
                results.append({
                    "tax_year": w2.tax_year,
                    "amount": Decimal(str(w2.box14_other["BONUS"])),
                    "document_id": w2.document_id,
                })
            elif income_type == "commission" and "COMM" in w2.box14_other:
                results.append({
                    "tax_year": w2.tax_year,
                    "amount": Decimal(str(w2.box14_other["COMM"])),
                    "document_id": w2.document_id,
                })

        return results
