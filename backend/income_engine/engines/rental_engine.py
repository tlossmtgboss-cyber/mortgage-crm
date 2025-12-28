"""
Rental Income (Schedule E) Calculation Engine

Calculates qualifying rental income from Schedule E following
agency guidelines.

Key Rules:
- Net income/loss from Schedule E Part I
- Add-back: Depreciation (non-cash expense)
- 2-year average for history
- 75% of gross rent if using lease (vacancy factor)
- Positive = income, Negative = $0 with condition flag
- Handle subject property vs other rentals differently
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
    ScheduleEFacts,
    RentalProperty,
)

logger = logging.getLogger(__name__)


class RentalEngine(BaseIncomeEngine):
    """
    Rental Income (Schedule E) Calculation Engine.

    Follows Fannie Mae Selling Guide B3-3.1-09:
    - Uses Schedule E net income + depreciation add-back
    - 2-year average for trending analysis
    - If using lease, applies 75% vacancy factor
    - Losses result in $0 income with blocking flag
    """

    ENGINE_NAME = "RentalEngine"
    ENGINE_VERSION = "1.0"

    # Default vacancy factor (25% vacancy = 75% of rent usable)
    DEFAULT_VACANCY_FACTOR = Decimal("0.75")

    def get_supported_stream_types(self) -> List[IncomeStreamType]:
        return [IncomeStreamType.SCHEDULE_E_RENTAL]

    def calculate(
        self,
        schedule_e_facts: List[ScheduleEFacts],
        property_address: Optional[str] = None,
    ) -> EngineResult:
        """
        Calculate rental income from Schedule E.

        Args:
            schedule_e_facts: List of ScheduleEFacts (should have 2 years)
            property_address: Optional filter for specific property

        Returns:
            EngineResult with calculated income and flags
        """
        try:
            if not schedule_e_facts:
                return self.create_result(
                    success=True,
                    income_streams=[],
                    flags=[
                        self.create_info_flag(
                            FlagRuleId.RENTAL_NO_SCHEDULE_E,
                            "No Schedule E documents provided for rental income calculation"
                        )
                    ]
                )

            # Extract all properties across all years
            properties = self._extract_all_properties(schedule_e_facts)

            # Filter by property address if specified
            if property_address:
                properties = {k: v for k, v in properties.items()
                             if property_address.lower() in k.lower()}

            income_streams = []
            flags = []

            for prop_address, prop_years in properties.items():
                prop_stream, prop_flags = self._calculate_property_income(
                    prop_address, prop_years
                )
                if prop_stream:
                    income_streams.append(prop_stream)
                flags.extend(prop_flags)

            return self.create_result(
                success=True,
                income_streams=income_streams,
                flags=flags
            )

        except Exception as e:
            logger.exception(f"RentalEngine calculation error: {e}")
            return self.create_error_result(str(e))

    def _extract_all_properties(
        self,
        schedule_e_list: List[ScheduleEFacts]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Extract and group properties by address across all tax years."""
        properties = {}

        for sched_e in schedule_e_list:
            for prop in sched_e.properties:
                prop_key = prop.property_address.upper().strip()
                if prop_key not in properties:
                    properties[prop_key] = []

                properties[prop_key].append({
                    "tax_year": sched_e.tax_year,
                    "document_id": sched_e.document_id,
                    "property_data": prop,
                })

        return properties

    def _calculate_property_income(
        self,
        property_address: str,
        prop_years: List[Dict[str, Any]]
    ) -> Tuple[Optional[IncomeStream], List[IncomeFlag]]:
        """Calculate income for a single rental property."""
        flags = []
        calculation_steps = []

        # Sort by tax year (most recent first)
        years_sorted = sorted(prop_years, key=lambda x: x["tax_year"], reverse=True)

        if len(years_sorted) < 2:
            flags.append(self.create_warning_flag(
                FlagRuleId.INSUFFICIENT_HISTORY,
                f"Only {len(years_sorted)} year(s) of rental history for {property_address[:50]}. "
                f"Rental income typically requires 2-year history.",
                affected_stream=property_address
            ))

        # Calculate adjusted income for each year
        yearly_incomes = []
        document_ids = []
        tax_years = []
        add_backs = {}

        for year_data in years_sorted[:2]:  # Max 2 years
            prop = year_data["property_data"]
            tax_year = year_data["tax_year"]

            # Calculate adjusted net income
            adjusted, year_steps, total_depreciation = self._calculate_adjusted_rental_income(
                prop, tax_year, property_address
            )

            yearly_incomes.append({
                "tax_year": tax_year,
                "adjusted_income": adjusted,
                "document_id": year_data["document_id"],
                "depreciation_addback": total_depreciation,
            })

            calculation_steps.extend(year_steps)
            document_ids.append(year_data["document_id"])
            tax_years.append(tax_year)

            # Track add-backs
            if total_depreciation > 0:
                add_backs[f"depreciation_{tax_year}"] = total_depreciation

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
                    FlagRuleId.RENTAL_INCOME_DECLINING,
                    f"Rental income declining {abs(trend_pct):.1f}% - "
                    f"using lower year (${min(year1_income, year2_income):,.2f})",
                    affected_stream=property_address
                ))

            # Check if final income is a loss
            if average < 0:
                monthly_income = Decimal("0")
                flags.append(self.create_blocking_flag(
                    FlagRuleId.RENTAL_LOSS,
                    f"Rental property shows net loss of ${abs(average):,.2f}/year. "
                    f"Loss is treated as $0 income and creates a condition.",
                    required_action="Document rental loss. Cannot use negative rental income. "
                                   "Consider PITIA offset if subject property.",
                    affected_stream=property_address,
                    metadata={
                        "annual_loss": float(average),
                        "property_address": property_address,
                    }
                ))

            stream = self.create_income_stream(
                stream_type=IncomeStreamType.SCHEDULE_E_RENTAL,
                stream_name=f"Rental - {property_address[:40]}",
                monthly_income=monthly_income,
                calculation_inputs={
                    "method": "schedule_e_two_year_average",
                    "year1_adjusted": float(year1_income),
                    "year2_adjusted": float(year2_income),
                    "property_address": property_address,
                },
                calculation_steps=calculation_steps,
                document_ids=document_ids,
                tax_years=tax_years,
                add_backs=add_backs,
                trending_direction=direction,
                trending_percentage=trend_pct,
                year1_income=year1_income,
                year2_income=year2_income,
                uses_lower_year=uses_lower,
            )

        else:
            # Single year
            year1_income = yearly_incomes[0]["adjusted_income"]

            if year1_income < 0:
                monthly_income = Decimal("0")
                flags.append(self.create_blocking_flag(
                    FlagRuleId.RENTAL_LOSS,
                    f"Rental property shows net loss of ${abs(year1_income):,.2f}/year. "
                    f"Loss is treated as $0 income.",
                    required_action="Document rental loss. Cannot use negative rental income.",
                    affected_stream=property_address
                ))
            else:
                monthly_income = self.annual_to_monthly(year1_income)

            stream = self.create_income_stream(
                stream_type=IncomeStreamType.SCHEDULE_E_RENTAL,
                stream_name=f"Rental - {property_address[:40]}",
                monthly_income=monthly_income,
                calculation_inputs={
                    "method": "schedule_e_single_year",
                    "adjusted_income": float(year1_income),
                    "property_address": property_address,
                },
                calculation_steps=calculation_steps,
                document_ids=document_ids,
                tax_years=tax_years,
                add_backs=add_backs,
            )

        return stream, flags

    def _calculate_adjusted_rental_income(
        self,
        prop: RentalProperty,
        tax_year: int,
        property_address: str
    ) -> Tuple[Decimal, List[Dict], Decimal]:
        """
        Calculate adjusted rental income with depreciation add-back.

        Formula:
        Adjusted = Net Income/Loss + Depreciation
        """
        steps = []

        # Start with net income/loss
        net_income = Decimal(str(prop.net_income_loss))

        steps.append(self.log_step(
            f"Start with Schedule E Net Income/Loss for {tax_year}",
            inputs={
                "net_income_loss": float(net_income),
                "rents_received": float(prop.rents_received),
                "total_expenses": float(prop.total_expenses),
            },
            result=float(net_income)
        ))

        running_total = net_income

        # Add-back: Depreciation
        depreciation = Decimal(str(prop.depreciation))
        if depreciation > 0:
            running_total += depreciation

            steps.append(self.log_step(
                f"Add back Depreciation for {tax_year}",
                formula="running_total += depreciation",
                inputs={"depreciation": float(depreciation)},
                result=float(running_total)
            ))

        steps.append(self.log_step(
            f"Final adjusted rental income for {tax_year}",
            inputs={
                "net_income": float(net_income),
                "depreciation_addback": float(depreciation),
            },
            result=float(running_total)
        ))

        return self.round_currency(running_total), steps, depreciation

    def calculate_from_lease(
        self,
        monthly_rent: Decimal,
        vacancy_factor: Decimal = None,
        pitia: Optional[Dict[str, Decimal]] = None,
    ) -> Tuple[Decimal, List[Dict], List[IncomeFlag]]:
        """
        Calculate rental income from lease (when Schedule E not available).

        Formula:
        Net Rental Income = (Monthly Rent × Vacancy Factor) - PITIA

        Args:
            monthly_rent: Gross monthly rent from lease
            vacancy_factor: Typically 75% (25% vacancy)
            pitia: Principal, Interest, Taxes, Insurance, Association dues

        Returns:
            Tuple of (monthly_income, calculation_steps, flags)
        """
        steps = []
        flags = []

        factor = vacancy_factor or self.DEFAULT_VACANCY_FACTOR

        # Apply vacancy factor
        effective_rent = monthly_rent * factor

        steps.append(self.log_step(
            "Apply vacancy factor to gross rent",
            formula="effective_rent = monthly_rent × vacancy_factor",
            inputs={
                "monthly_rent": float(monthly_rent),
                "vacancy_factor": float(factor),
            },
            result=float(effective_rent)
        ))

        # Subtract PITIA if provided
        if pitia:
            total_pitia = sum(pitia.values())
            net_rental = effective_rent - total_pitia

            steps.append(self.log_step(
                "Subtract PITIA",
                formula="net_rental = effective_rent - PITIA",
                inputs={
                    "effective_rent": float(effective_rent),
                    "principal_interest": float(pitia.get("pi", 0)),
                    "taxes": float(pitia.get("taxes", 0)),
                    "insurance": float(pitia.get("insurance", 0)),
                    "hoa": float(pitia.get("hoa", 0)),
                    "total_pitia": float(total_pitia),
                },
                result=float(net_rental)
            ))
        else:
            net_rental = effective_rent

        # Flag if result is negative
        if net_rental < 0:
            flags.append(self.create_warning_flag(
                FlagRuleId.RENTAL_LOSS,
                f"Lease-based rental calculation shows loss of ${abs(net_rental):,.2f}/month. "
                f"Consider using Schedule E if available.",
            ))
            net_rental = Decimal("0")

        return self.round_currency(net_rental), steps, flags
