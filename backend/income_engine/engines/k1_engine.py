"""
K-1 Income Calculation Engine

Calculates qualifying income from Schedule K-1 forms:
- Partnership (Form 1065 K-1)
- S-Corporation (Form 1120S K-1)
- C-Corporation (Form 1120 - 100% ownership required)

Key Rules:
- Partnership/S-Corp: 25%+ ownership OR documented distributions
- C-Corp: Must have 100% ownership
- Add-backs: Depreciation, amortization, depletion
- 2-year average required
- Use lower year if declining
- Losses = $0 income with condition flag
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
    K1Facts,
)

# Field mappings for K1Facts (mapping to internal engine names)
# K1Facts uses: k1_type, box1_ordinary_income, box4_guaranteed_payments
# Engine uses: entity_type, ordinary_income_loss, guaranteed_payments

logger = logging.getLogger(__name__)


class K1Engine(BaseIncomeEngine):
    """
    K-1 Income Calculation Engine.

    Follows Fannie Mae Selling Guide B3-3.3-01 through B3-3.3-05:
    - Partnership/S-Corp: 25%+ ownership OR proof of distributions
    - C-Corp: 100% ownership required
    - Uses 2-year average with depreciation add-backs
    - Declining income uses lower year
    """

    ENGINE_NAME = "K1Engine"
    ENGINE_VERSION = "1.0"

    # Minimum ownership for partnership/S-Corp without distribution proof
    MIN_OWNERSHIP_PERCENTAGE = Decimal("25.0")

    def get_supported_stream_types(self) -> List[IncomeStreamType]:
        return [
            IncomeStreamType.K1_PARTNERSHIP,
            IncomeStreamType.K1_SCORP,
            IncomeStreamType.K1_CCORP,
        ]

    def calculate(
        self,
        k1_facts: List[K1Facts],
        entity_name: Optional[str] = None,
    ) -> EngineResult:
        """
        Calculate K-1 income from partnership, S-Corp, or C-Corp.

        Args:
            k1_facts: List of K1Facts (should have 2 years per entity)
            entity_name: Optional filter for specific entity

        Returns:
            EngineResult with calculated income and flags
        """
        try:
            if not k1_facts:
                return self.create_result(
                    success=True,
                    income_streams=[],
                    flags=[
                        self.create_info_flag(
                            FlagRuleId.MISSING_REQUIRED_DOCUMENT,
                            "No K-1 documents provided for business income calculation"
                        )
                    ]
                )

            # Group by entity
            entities = self._group_by_entity(k1_facts)

            # Filter by entity if specified
            if entity_name:
                entities = {k: v for k, v in entities.items()
                           if entity_name.lower() in k.lower()}

            income_streams = []
            flags = []

            for ent_name, ent_k1s in entities.items():
                ent_stream, ent_flags = self._calculate_entity_income(
                    ent_name, ent_k1s
                )
                if ent_stream:
                    income_streams.append(ent_stream)
                flags.extend(ent_flags)

            return self.create_result(
                success=True,
                income_streams=income_streams,
                flags=flags
            )

        except Exception as e:
            logger.exception(f"K1Engine calculation error: {e}")
            return self.create_error_result(str(e))

    def _group_by_entity(
        self,
        k1_list: List[K1Facts]
    ) -> Dict[str, List[K1Facts]]:
        """Group K-1s by entity name."""
        entities = {}

        for k1 in k1_list:
            entity_key = (k1.entity_name or "Business").upper().strip()
            if entity_key not in entities:
                entities[entity_key] = []
            entities[entity_key].append(k1)

        return entities

    def _calculate_entity_income(
        self,
        entity_name: str,
        k1s: List[K1Facts]
    ) -> Tuple[Optional[IncomeStream], List[IncomeFlag]]:
        """Calculate income for a single entity."""
        flags = []
        calculation_steps = []

        # All K-1s for this entity should be same type
        k1_type = k1s[0].k1_type.lower() if k1s[0].k1_type else "partnership"

        # Determine stream type
        if k1_type == "partnership":
            stream_type = IncomeStreamType.K1_PARTNERSHIP
        elif k1_type == "scorp":
            stream_type = IncomeStreamType.K1_SCORP
        elif k1_type == "ccorp":
            stream_type = IncomeStreamType.K1_CCORP
        else:
            stream_type = IncomeStreamType.K1_PARTNERSHIP

        # Sort by tax year (most recent first)
        k1s_sorted = sorted(k1s, key=lambda x: x.tax_year, reverse=True)

        # Validate ownership requirements
        ownership_flags = self._validate_ownership(k1s_sorted[0], entity_name)
        flags.extend(ownership_flags)

        # Check for blocking ownership issues
        has_blocking = any(f.severity == FlagSeverity.BLOCKING for f in ownership_flags)
        if has_blocking:
            return None, flags

        if len(k1s_sorted) < 2:
            flags.append(self.create_warning_flag(
                FlagRuleId.K1_ONLY_ONE_YEAR,
                f"Only {len(k1s_sorted)} year(s) of K-1 available for {entity_name}. "
                f"Business income typically requires 2-year history.",
                affected_stream=entity_name
            ))

        # Calculate adjusted income for each year
        yearly_incomes = []
        document_ids = []
        tax_years = []
        add_backs = {}

        for k1 in k1s_sorted[:2]:  # Max 2 years
            adjusted, year_steps, year_addbacks = self._calculate_adjusted_income(
                k1, entity_name
            )
            yearly_incomes.append({
                "tax_year": k1.tax_year,
                "adjusted_income": adjusted,
                "document_id": k1.document_id,
            })
            calculation_steps.extend(year_steps)
            document_ids.append(k1.document_id)
            tax_years.append(k1.tax_year)

            # Track add-backs
            for key, value in year_addbacks.items():
                add_backs[f"{key}_{k1.tax_year}"] = value

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
                    FlagRuleId.K1_INCOME_DECLINING,
                    f"K-1 income declining {abs(trend_pct):.1f}% - "
                    f"using lower year (${min(year1_income, year2_income):,.2f})",
                    affected_stream=entity_name
                ))

            # Check if final income is a loss
            if average <= 0:
                monthly_income = Decimal("0")
                flags.append(self.create_blocking_flag(
                    FlagRuleId.K1_NO_DISTRIBUTIONS_OR_LIQUIDITY,
                    f"K-1 shows net loss of ${abs(average):,.2f}. "
                    f"Cannot use negative business income.",
                    required_action="Review business viability. Loss cannot be used as qualifying income.",
                    affected_stream=entity_name
                ))

            stream = self.create_income_stream(
                stream_type=stream_type,
                stream_name=f"{entity_name} - K-1 ({k1_type.replace('_', ' ').title()})",
                monthly_income=monthly_income,
                calculation_inputs={
                    "method": "k1_two_year_average_with_addbacks",
                    "entity_type": k1_type,
                    "year1_adjusted": float(year1_income),
                    "year2_adjusted": float(year2_income),
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

            if year1_income <= 0:
                monthly_income = Decimal("0")
                flags.append(self.create_blocking_flag(
                    FlagRuleId.K1_NO_DISTRIBUTIONS_OR_LIQUIDITY,
                    f"K-1 shows net loss of ${abs(year1_income):,.2f}. "
                    f"Cannot use negative business income.",
                    required_action="Review business viability. Loss cannot be used as qualifying income.",
                    affected_stream=entity_name
                ))
            else:
                monthly_income = self.annual_to_monthly(year1_income)

            stream = self.create_income_stream(
                stream_type=stream_type,
                stream_name=f"{entity_name} - K-1 ({k1_type.replace('_', ' ').title()})",
                monthly_income=monthly_income,
                calculation_inputs={
                    "method": "k1_single_year_with_addbacks",
                    "entity_type": k1_type,
                    "adjusted_income": float(year1_income),
                    "warning": "insufficient_history"
                },
                calculation_steps=calculation_steps,
                document_ids=document_ids,
                tax_years=tax_years,
                add_backs=add_backs,
            )

        return stream, flags

    def _validate_ownership(
        self,
        k1: K1Facts,
        entity_name: str
    ) -> List[IncomeFlag]:
        """Validate ownership requirements based on entity type."""
        flags = []

        ownership_pct = Decimal(str(k1.ownership_percentage or 0))
        k1_type = (k1.k1_type or "partnership").lower()

        # Check if distributions are documented (cash distributions > 0)
        has_distributions = (k1.distributions_cash or Decimal("0")) > Decimal("0")

        if k1_type == "ccorp":
            # C-Corp requires 100% ownership
            if ownership_pct < Decimal("100"):
                flags.append(self.create_blocking_flag(
                    FlagRuleId.CCORP_NOT_100_PERCENT,
                    f"C-Corporation income requires 100% ownership. "
                    f"Current ownership: {ownership_pct:.1f}%.",
                    required_action="C-Corp income cannot be used without 100% ownership. "
                                   "Consider if borrower can document salary from W-2 instead.",
                    affected_stream=entity_name,
                    metadata={"ownership_percentage": float(ownership_pct)}
                ))
        else:
            # Partnership/S-Corp: 25%+ ownership OR distributions
            if ownership_pct < self.MIN_OWNERSHIP_PERCENTAGE:
                if not has_distributions:
                    flags.append(self.create_blocking_flag(
                        FlagRuleId.K1_OWNERSHIP_BELOW_25,
                        f"Ownership ({ownership_pct:.1f}%) is below 25% minimum "
                        f"and distributions are not documented.",
                        required_action="Document consistent distributions or liquidity access "
                                       "to support income continuance.",
                        affected_stream=entity_name,
                        metadata={"ownership_percentage": float(ownership_pct)}
                    ))
                else:
                    flags.append(self.create_info_flag(
                        FlagRuleId.K1_OWNERSHIP_BELOW_25,
                        f"Ownership ({ownership_pct:.1f}%) is below 25%, "
                        f"but distributions are documented.",
                        affected_stream=entity_name,
                        metadata={"ownership_percentage": float(ownership_pct)}
                    ))

            # Check for distribution documentation when needed
            if ownership_pct >= self.MIN_OWNERSHIP_PERCENTAGE and not has_distributions:
                flags.append(self.create_info_flag(
                    FlagRuleId.K1_NO_DISTRIBUTIONS_OR_LIQUIDITY,
                    f"Distributions not documented for {entity_name}. "
                    f"Ownership at {ownership_pct:.1f}% meets minimum threshold.",
                    affected_stream=entity_name
                ))

        return flags

    def _calculate_adjusted_income(
        self,
        k1: K1Facts,
        entity_name: str
    ) -> Tuple[Decimal, List[Dict], Dict[str, Decimal]]:
        """
        Calculate adjusted K-1 income with add-backs.

        Formula:
        Adjusted = Ordinary Income/Loss (Box 1)
                 + Guaranteed Payments (Box 4, Partnership only)
                 + Depreciation (from entity depreciation)
                 + Amortization
                 + Depletion
                 - Section 179 Expense (if claimed)

        Multiplied by ownership percentage if < 100%
        """
        steps = []
        add_backs = {}

        k1_type = (k1.k1_type or "partnership").lower()

        # Start with ordinary income (box1_ordinary_income)
        ordinary_income = Decimal(str(k1.box1_ordinary_income or 0))

        steps.append(self.log_step(
            f"Start with Ordinary Income/Loss (Box 1) for {k1.tax_year}",
            inputs={
                "ordinary_income_loss": float(ordinary_income),
                "entity_type": k1_type,
            },
            result=float(ordinary_income)
        ))

        running_total = ordinary_income

        # Add guaranteed payments (Partnership only - box4_guaranteed_payments)
        if k1_type == "partnership" and k1.box4_guaranteed_payments:
            guaranteed = Decimal(str(k1.box4_guaranteed_payments))
            running_total += guaranteed
            add_backs["guaranteed_payments"] = guaranteed

            steps.append(self.log_step(
                f"Add Guaranteed Payments (Box 4) for {k1.tax_year}",
                formula="running_total += guaranteed_payments",
                inputs={"guaranteed_payments": float(guaranteed)},
                result=float(running_total)
            ))

        # Apply ownership percentage to get borrower's share
        ownership_pct = Decimal(str(k1.ownership_percentage or 100)) / Decimal("100")

        # Get add-backs from entity (proportional to ownership)
        if k1.depreciation:
            depreciation = Decimal(str(k1.depreciation)) * ownership_pct
            running_total += depreciation
            add_backs["depreciation"] = depreciation

            steps.append(self.log_step(
                f"Add back Depreciation (ownership share) for {k1.tax_year}",
                formula="running_total += depreciation × ownership_percentage",
                inputs={
                    "entity_depreciation": float(k1.depreciation),
                    "ownership_percentage": float(ownership_pct * 100),
                    "borrower_share": float(depreciation),
                },
                result=float(running_total)
            ))

        if k1.amortization:
            amortization = Decimal(str(k1.amortization)) * ownership_pct
            running_total += amortization
            add_backs["amortization"] = amortization

            steps.append(self.log_step(
                f"Add back Amortization (ownership share) for {k1.tax_year}",
                inputs={"amortization": float(amortization)},
                result=float(running_total)
            ))

        if k1.depletion:
            depletion = Decimal(str(k1.depletion)) * ownership_pct
            running_total += depletion
            add_backs["depletion"] = depletion

            steps.append(self.log_step(
                f"Add back Depletion (ownership share) for {k1.tax_year}",
                inputs={"depletion": float(depletion)},
                result=float(running_total)
            ))

        # Subtract Section 179 (if borrower claimed it personally - box12_section_179)
        if k1.box12_section_179:
            sec_179 = Decimal(str(k1.box12_section_179))
            running_total -= sec_179

            steps.append(self.log_step(
                f"Subtract Section 179 Deduction for {k1.tax_year}",
                formula="running_total -= section_179",
                inputs={"section_179": float(sec_179)},
                result=float(running_total)
            ))

        steps.append(self.log_step(
            f"Final adjusted K-1 income for {k1.tax_year}",
            inputs={
                "ordinary_income": float(ordinary_income),
                "total_addbacks": float(sum(add_backs.values())),
                "entity_type": k1_type,
                "ownership_percentage": float(ownership_pct * 100),
            },
            result=float(running_total)
        ))

        return self.round_currency(running_total), steps, add_backs

    def calculate_with_business_returns(
        self,
        k1_facts: List[K1Facts],
        business_return_analysis: Optional[Dict[str, Any]] = None,
    ) -> EngineResult:
        """
        Enhanced calculation using business tax return analysis.

        When business returns (1065, 1120S, 1120) are available,
        use them to verify K-1 amounts and extract entity-level add-backs.

        Args:
            k1_facts: List of K1Facts
            business_return_analysis: Optional analysis from business returns

        Returns:
            EngineResult with enhanced calculations
        """
        # Base calculation
        result = self.calculate(k1_facts)

        if not business_return_analysis or not result.success:
            return result

        # Enhance with business return data
        enhanced_flags = list(result.flags)

        # Verify K-1 matches business return
        for stream in result.income_streams:
            entity_name = stream.calculation_inputs.get("entity_name")
            if entity_name and entity_name in business_return_analysis:
                entity_data = business_return_analysis[entity_name]

                # Check for discrepancies
                reported_income = entity_data.get("total_income")
                if reported_income:
                    # Add verification note
                    enhanced_flags.append(self.create_info_flag(
                        "K1_VERIFIED_AGAINST_RETURN",
                        f"K-1 income verified against business return for {entity_name}",
                        affected_stream=entity_name,
                        metadata={"business_return_income": reported_income}
                    ))

        return self.create_result(
            success=True,
            income_streams=result.income_streams,
            flags=enhanced_flags
        )
