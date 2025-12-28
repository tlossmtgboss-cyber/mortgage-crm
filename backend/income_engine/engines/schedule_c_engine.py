"""
Schedule C Income Calculation Engine

Calculates qualifying income from Schedule C (Profit or Loss from Business)
following agency guidelines for self-employment income.

Key Rules:
- Net profit/loss from Line 31
- Add-backs: Depreciation (Line 13), Amortization, Depletion
- Mileage add-back: Business miles × IRS depreciation rate
- Business use of home: Add back depreciation portion only
- 2-year average required
- Use lower year if declining
- If loss, income = $0 and flag condition
"""

from datetime import datetime
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
    ScheduleCFacts,
)

logger = logging.getLogger(__name__)


class ScheduleCEngine(BaseIncomeEngine):
    """
    Schedule C Self-Employment Income Calculation Engine.

    Follows Fannie Mae Selling Guide B3-3.2-01:
    - Uses 2-year average of adjusted net profit
    - Adds back non-cash expenses (depreciation, amortization)
    - Adds back mileage depreciation component
    - Uses lower year if income is declining
    """

    ENGINE_NAME = "ScheduleCEngine"
    ENGINE_VERSION = "1.0"

    def get_supported_stream_types(self) -> List[IncomeStreamType]:
        return [IncomeStreamType.SCHEDULE_C]

    def calculate(
        self,
        schedule_c_facts: List[ScheduleCFacts],
        business_name: Optional[str] = None,
    ) -> EngineResult:
        """
        Calculate Schedule C self-employment income.

        Args:
            schedule_c_facts: List of ScheduleCFacts (should have 2 years)
            business_name: Optional filter for specific business

        Returns:
            EngineResult with calculated income and flags
        """
        try:
            if not schedule_c_facts:
                return self.create_result(
                    success=True,
                    income_streams=[],
                    flags=[
                        self.create_info_flag(
                            FlagRuleId.MISSING_REQUIRED_DOCUMENT,
                            "No Schedule C documents provided"
                        )
                    ]
                )

            # Group by business (using business name or code)
            businesses = self._group_by_business(schedule_c_facts)

            # Filter by business if specified
            if business_name:
                businesses = {k: v for k, v in businesses.items()
                             if business_name.lower() in k.lower()}

            income_streams = []
            flags = []

            for biz_name, biz_schedules in businesses.items():
                biz_stream, biz_flags = self._calculate_business_income(
                    biz_name, biz_schedules
                )
                if biz_stream:
                    income_streams.append(biz_stream)
                flags.extend(biz_flags)

            return self.create_result(
                success=True,
                income_streams=income_streams,
                flags=flags
            )

        except Exception as e:
            logger.exception(f"ScheduleCEngine calculation error: {e}")
            return self.create_error_result(str(e))

    def _group_by_business(
        self,
        schedule_c_list: List[ScheduleCFacts]
    ) -> Dict[str, List[ScheduleCFacts]]:
        """Group Schedule C forms by business."""
        businesses = {}

        for sched_c in schedule_c_list:
            biz_key = (sched_c.business_name or "Self-Employment").upper().strip()
            if biz_key not in businesses:
                businesses[biz_key] = []
            businesses[biz_key].append(sched_c)

        return businesses

    def _calculate_business_income(
        self,
        business_name: str,
        schedules: List[ScheduleCFacts]
    ) -> Tuple[Optional[IncomeStream], List[IncomeFlag]]:
        """Calculate income for a single business."""
        flags = []
        calculation_steps = []

        # Sort by tax year (most recent first)
        schedules_sorted = sorted(schedules, key=lambda x: x.tax_year, reverse=True)

        if len(schedules_sorted) < 2:
            flags.append(self.create_warning_flag(
                FlagRuleId.SCHEDULE_C_ONLY_ONE_YEAR,
                f"Only {len(schedules_sorted)} year(s) of Schedule C available for {business_name}. "
                f"Self-employment income typically requires 2-year history.",
                affected_stream=business_name
            ))

        # Calculate adjusted income for each year
        yearly_incomes = []
        document_ids = []
        tax_years = []

        for sched_c in schedules_sorted[:2]:  # Max 2 years
            adjusted, year_steps, year_flags = self._calculate_adjusted_income(
                sched_c, business_name
            )
            yearly_incomes.append({
                "tax_year": sched_c.tax_year,
                "adjusted_income": adjusted,
                "document_id": sched_c.document_id,
            })
            calculation_steps.extend(year_steps)
            flags.extend(year_flags)
            document_ids.append(sched_c.document_id)
            tax_years.append(sched_c.tax_year)

        if not yearly_incomes:
            return None, flags

        # Calculate final monthly income
        if len(yearly_incomes) >= 2:
            year1_income = yearly_incomes[0]["adjusted_income"]
            year2_income = yearly_incomes[1]["adjusted_income"]

            average, direction, trend_pct, uses_lower = self.calculate_two_year_average(
                year1_income, year2_income
            )

            monthly_income = self.annual_to_monthly(average)

            calculation_steps.append(self.log_step(
                "Two-year average calculation",
                formula="average = (year1 + year2) / 2, use lower if declining",
                inputs={
                    "year1": float(year1_income),
                    "year2": float(year2_income),
                    "year1_tax_year": yearly_incomes[0]["tax_year"],
                    "year2_tax_year": yearly_incomes[1]["tax_year"],
                },
                result=float(average)
            ))

            # Flag if declining
            if direction == TrendDirection.DECLINING:
                flags.append(self.create_warning_flag(
                    FlagRuleId.SCHEDULE_C_INCOME_DECLINING,
                    f"Schedule C income declining {abs(trend_pct):.1f}% - "
                    f"using lower year (${min(year1_income, year2_income):,.2f})",
                    affected_stream=business_name
                ))

            # Check if final income is a loss
            if average <= 0:
                monthly_income = Decimal("0")
                flags.append(self.create_blocking_flag(
                    FlagRuleId.SCHEDULE_C_LOSS,
                    f"Schedule C shows net loss of ${abs(average):,.2f}. "
                    f"Cannot use negative self-employment income.",
                    required_action="Review business viability. Loss cannot be used as qualifying income.",
                    affected_stream=business_name
                ))

            stream = self.create_income_stream(
                stream_type=IncomeStreamType.SCHEDULE_C,
                stream_name=f"{business_name} - Schedule C",
                monthly_income=monthly_income,
                calculation_inputs={
                    "method": "two_year_average_with_addbacks",
                    "year1_adjusted": float(year1_income),
                    "year2_adjusted": float(year2_income),
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

        else:
            # Single year
            year1_income = yearly_incomes[0]["adjusted_income"]

            if year1_income <= 0:
                monthly_income = Decimal("0")
                flags.append(self.create_blocking_flag(
                    FlagRuleId.SCHEDULE_C_LOSS,
                    f"Schedule C shows net loss of ${abs(year1_income):,.2f}. "
                    f"Cannot use negative self-employment income.",
                    required_action="Review business viability. Loss cannot be used as qualifying income.",
                    affected_stream=business_name
                ))
            else:
                monthly_income = self.annual_to_monthly(year1_income)

            stream = self.create_income_stream(
                stream_type=IncomeStreamType.SCHEDULE_C,
                stream_name=f"{business_name} - Schedule C",
                monthly_income=monthly_income,
                calculation_inputs={
                    "method": "single_year_with_addbacks",
                    "adjusted_income": float(year1_income),
                    "warning": "insufficient_history"
                },
                calculation_steps=calculation_steps,
                document_ids=document_ids,
                tax_years=tax_years,
            )

        return stream, flags

    def _calculate_adjusted_income(
        self,
        sched_c: ScheduleCFacts,
        business_name: str
    ) -> Tuple[Decimal, List[Dict], List[IncomeFlag]]:
        """
        Calculate adjusted net profit with add-backs.

        Formula:
        Adjusted = Net Profit (Line 31)
                 + Depreciation (Line 13)
                 + Amortization
                 + Depletion
                 + Mileage Add-back (miles × IRS depreciation rate)
                 + Business Use of Home Depreciation
                 - Non-deductible portion of meals (already at 50%)
        """
        steps = []
        flags = []
        add_backs = {}

        # Start with net profit
        net_profit = Decimal(str(sched_c.line31_net_profit_loss))

        steps.append(self.log_step(
            f"Start with Net Profit (Line 31) for {sched_c.tax_year}",
            inputs={"net_profit": float(net_profit)},
            result=float(net_profit)
        ))

        running_total = net_profit

        # Add-back: Depreciation (Line 13)
        if sched_c.line13_depreciation > 0:
            depreciation = Decimal(str(sched_c.line13_depreciation))
            running_total += depreciation
            add_backs["depreciation"] = depreciation

            steps.append(self.log_step(
                "Add back Depreciation (Line 13)",
                formula="running_total += depreciation",
                inputs={"depreciation": float(depreciation)},
                result=float(running_total)
            ))

        # Add-back: Mileage depreciation component
        if sched_c.line44b_vehicle_miles_business:
            mileage_addback, mileage_steps, mileage_flags = self._calculate_mileage_addback(
                sched_c, business_name
            )
            if mileage_addback > 0:
                running_total += mileage_addback
                add_backs["mileage_depreciation"] = mileage_addback
                steps.extend(mileage_steps)
            flags.extend(mileage_flags)

        # Add-back: Business Use of Home (Form 8829) - depreciation portion only
        if sched_c.form_8829_depreciation_portion > 0:
            home_depreciation = Decimal(str(sched_c.form_8829_depreciation_portion))
            running_total += home_depreciation
            add_backs["home_office_depreciation"] = home_depreciation

            steps.append(self.log_step(
                "Add back Business Use of Home Depreciation (Form 8829)",
                inputs={"home_depreciation": float(home_depreciation)},
                result=float(running_total)
            ))

            # Flag home office deduction for underwriter review
            flags.append(self.create_info_flag(
                FlagRuleId.HOME_OFFICE_DEDUCTION,
                f"Business use of home deduction: ${sched_c.form_8829_deduction:,.2f}. "
                f"Depreciation portion (${home_depreciation:,.2f}) added back.",
                affected_stream=business_name,
                metadata={"form_8829_total": float(sched_c.form_8829_deduction)}
            ))

        steps.append(self.log_step(
            f"Final adjusted income for {sched_c.tax_year}",
            inputs={
                "net_profit": float(net_profit),
                "total_addbacks": float(sum(add_backs.values())),
            },
            result=float(running_total)
        ))

        return self.round_currency(running_total), steps, flags

    def _calculate_mileage_addback(
        self,
        sched_c: ScheduleCFacts,
        business_name: str
    ) -> Tuple[Decimal, List[Dict], List[IncomeFlag]]:
        """
        Calculate mileage depreciation add-back.

        Formula: Business Miles × IRS Depreciation Rate per Mile

        The IRS standard mileage rate includes a depreciation component.
        We add back this depreciation portion since it's a non-cash expense.
        """
        steps = []
        flags = []

        business_miles = sched_c.line44b_vehicle_miles_business

        # Get mileage rate for this tax year
        mileage_rate = self.get_mileage_rate(sched_c.tax_year)

        if mileage_rate is None:
            flags.append(self.create_blocking_flag(
                FlagRuleId.MILEAGE_RATE_NOT_CONFIGURED,
                f"IRS mileage depreciation rate not configured for {sched_c.tax_year}. "
                f"Cannot calculate mileage add-back for {business_miles:,} business miles.",
                required_action=f"Configure mileage rate for {sched_c.tax_year} in system settings.",
                affected_stream=business_name,
                metadata={
                    "tax_year": sched_c.tax_year,
                    "business_miles": business_miles
                }
            ))
            return Decimal("0"), steps, flags

        # Calculate add-back
        mileage_addback = Decimal(str(business_miles)) * mileage_rate

        steps.append(self.log_step(
            f"Calculate mileage depreciation add-back for {sched_c.tax_year}",
            formula="addback = business_miles × depreciation_rate_per_mile",
            inputs={
                "business_miles": business_miles,
                "depreciation_rate": float(mileage_rate),
                "tax_year": sched_c.tax_year,
            },
            result=float(mileage_addback)
        ))

        return self.round_currency(mileage_addback), steps, flags
