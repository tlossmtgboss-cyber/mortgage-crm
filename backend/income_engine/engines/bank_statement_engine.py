"""
Bank Statement Income Calculation Engine

Calculates qualifying income from personal/business bank statements
for Non-QM lending programs.

Key Rules:
- 12 or 24 months of statements
- Calculate average monthly deposits
- Apply expense ratio (business type dependent)
- Flag NSF/overdrafts and large unexplained deposits
- If 12-month shows decline, may require 24-month
- Check for consistent deposit patterns
"""

from datetime import datetime, date
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
    BankStatementFacts,
    BankStatementMonth,
)

logger = logging.getLogger(__name__)


class BankStatementEngine(BaseIncomeEngine):
    """
    Bank Statement Income Calculation Engine for Non-QM Programs.

    Calculates self-employed income using bank statement deposits
    when traditional documentation is not available.
    """

    ENGINE_NAME = "BankStatementEngine"
    ENGINE_VERSION = "1.0"

    # Default expense ratios by business type
    DEFAULT_EXPENSE_RATIOS = {
        "service": Decimal("0.50"),       # 50% expense ratio
        "retail": Decimal("0.65"),        # 65% expense ratio
        "restaurant": Decimal("0.70"),    # 70% expense ratio
        "construction": Decimal("0.60"),  # 60% expense ratio
        "medical": Decimal("0.55"),       # 55% expense ratio
        "real_estate": Decimal("0.45"),   # 45% expense ratio
        "default": Decimal("0.50"),       # Default 50%
    }

    # Large deposit threshold (percentage of average)
    LARGE_DEPOSIT_THRESHOLD = Decimal("2.0")  # 200% of average

    # NSF warning threshold
    NSF_WARNING_THRESHOLD = 2  # per statement period

    def get_supported_stream_types(self) -> List[IncomeStreamType]:
        return [IncomeStreamType.BANK_STATEMENT]

    def calculate(
        self,
        bank_statement_facts: BankStatementFacts,
        expense_ratio: Optional[Decimal] = None,
        business_type: Optional[str] = None,
    ) -> EngineResult:
        """
        Calculate income from bank statements.

        Args:
            bank_statement_facts: BankStatementFacts with monthly data
            expense_ratio: Optional custom expense ratio (0-1)
            business_type: Optional business type for default expense ratio

        Returns:
            EngineResult with calculated income and flags
        """
        try:
            if not bank_statement_facts or not bank_statement_facts.monthly_data:
                return self.create_result(
                    success=True,
                    income_streams=[],
                    flags=[
                        self.create_info_flag(
                            FlagRuleId.BANK_INSUFFICIENT_MONTHS,
                            "No bank statement data provided"
                        )
                    ]
                )

            months = bank_statement_facts.monthly_data
            account_type = bank_statement_facts.account_type
            flags = []
            calculation_steps = []

            # Validate minimum months
            if len(months) < 12:
                flags.append(self.create_blocking_flag(
                    FlagRuleId.BANK_INSUFFICIENT_MONTHS,
                    f"Only {len(months)} months of statements provided. "
                    f"Minimum 12 months required.",
                    required_action="Provide at least 12 consecutive months of bank statements.",
                ))
                return self.create_result(
                    success=True,
                    income_streams=[],
                    flags=flags
                )

            # Determine expense ratio
            if expense_ratio is not None:
                final_expense_ratio = Decimal(str(expense_ratio))
            elif business_type:
                final_expense_ratio = self.DEFAULT_EXPENSE_RATIOS.get(
                    business_type.lower(),
                    self.DEFAULT_EXPENSE_RATIOS["default"]
                )
            else:
                final_expense_ratio = self.DEFAULT_EXPENSE_RATIOS["default"]

            calculation_steps.append(self.log_step(
                "Determine expense ratio",
                inputs={
                    "custom_ratio": float(expense_ratio) if expense_ratio else None,
                    "business_type": business_type,
                    "final_ratio": float(final_expense_ratio),
                },
                result=float(final_expense_ratio)
            ))

            # Sort months chronologically (oldest to newest)
            months_sorted = sorted(months, key=lambda x: (x.year, x.month))

            # Calculate deposits and identify issues
            monthly_deposits = []
            total_overdraft_count = 0
            large_deposits = []

            for month_data in months_sorted:
                monthly_deposits.append({
                    "year": month_data.year,
                    "month": month_data.month,
                    "deposits": Decimal(str(month_data.total_deposits)),
                    "ending_balance": Decimal(str(month_data.ending_balance)),
                    "overdraft_count": month_data.overdraft_occurrences or 0,
                })
                total_overdraft_count += month_data.overdraft_occurrences or 0

                # Track large deposits for flagging (from deposits_detail)
                if month_data.deposits_detail:
                    avg_deposit = Decimal(str(month_data.total_deposits)) / max(month_data.deposit_count, 1)
                    for dep in month_data.deposits_detail:
                        dep_amount = Decimal(str(dep.get("amount", 0)))
                        # Flag deposits that are more than 2x average
                        if dep_amount > avg_deposit * 2:
                            large_deposits.append({
                                "year": month_data.year,
                                "month": month_data.month,
                                "amount": float(dep_amount),
                                "description": dep.get("description"),
                                "explained": dep.get("explained", False),
                            })

            # Calculate average monthly deposits
            deposit_amounts = [m["deposits"] for m in monthly_deposits]
            avg_deposits = sum(deposit_amounts) / len(deposit_amounts)

            calculation_steps.append(self.log_step(
                f"Calculate average monthly deposits ({len(monthly_deposits)} months)",
                formula="avg = sum(deposits) / count(months)",
                inputs={
                    "total_deposits": float(sum(deposit_amounts)),
                    "month_count": len(monthly_deposits),
                },
                result=float(avg_deposits)
            ))

            # Analyze trending
            if len(months_sorted) >= 12:
                first_half = deposit_amounts[:len(deposit_amounts)//2]
                second_half = deposit_amounts[len(deposit_amounts)//2:]

                first_avg = sum(first_half) / len(first_half)
                second_avg = sum(second_half) / len(second_half)

                if first_avg > 0:
                    trend_pct = ((second_avg - first_avg) / first_avg) * 100
                else:
                    trend_pct = Decimal("0")

                if trend_pct > Decimal("5"):
                    direction = TrendDirection.INCREASING
                elif trend_pct < Decimal("-5"):
                    direction = TrendDirection.DECLINING
                else:
                    direction = TrendDirection.STABLE

                calculation_steps.append(self.log_step(
                    "Analyze deposit trending",
                    inputs={
                        "first_half_avg": float(first_avg),
                        "second_half_avg": float(second_avg),
                        "trend_percentage": float(trend_pct),
                    },
                    result=direction.value
                ))
            else:
                direction = TrendDirection.STABLE
                trend_pct = Decimal("0")

            # Check for declining income requiring 24 months
            uses_lower = False
            if direction == TrendDirection.DECLINING:
                if len(months_sorted) < 24:
                    flags.append(self.create_warning_flag(
                        FlagRuleId.BANK_12MO_DECLINE_REQUIRES_24MO,
                        f"Deposits declining {abs(trend_pct):.1f}% over period. "
                        f"Consider requiring 24-month bank statements.",
                        metadata={"trend_percentage": float(trend_pct)}
                    ))
                else:
                    flags.append(self.create_warning_flag(
                        FlagRuleId.BANK_24MO_DECLINE_EXPLANATION,
                        f"Deposits declining {abs(trend_pct):.1f}% over 24 months. "
                        f"May require written explanation.",
                    ))
                    # Severe decline check
                    if trend_pct < Decimal("-25"):
                        flags.append(self.create_blocking_flag(
                            FlagRuleId.BANK_24MO_DECLINE_INELIGIBLE,
                            f"Deposits declining {abs(trend_pct):.1f}% - "
                            f"exceeds 25% threshold for program eligibility.",
                            required_action="Review business stability. May not qualify for bank statement program.",
                        ))

                # Use lower period if declining
                uses_lower = True
                avg_deposits = second_avg

            # Apply expense ratio
            net_income = avg_deposits * (Decimal("1") - final_expense_ratio)

            calculation_steps.append(self.log_step(
                "Apply expense ratio to get net income",
                formula="net_income = avg_deposits × (1 - expense_ratio)",
                inputs={
                    "avg_deposits": float(avg_deposits),
                    "expense_ratio": float(final_expense_ratio),
                    "net_factor": float(Decimal("1") - final_expense_ratio),
                },
                result=float(net_income)
            ))

            # Flag NSF/overdrafts
            if total_overdraft_count > self.NSF_WARNING_THRESHOLD * len(months_sorted):
                flags.append(self.create_warning_flag(
                    FlagRuleId.BANK_NSF_WARNING,
                    f"{total_overdraft_count} NSF/overdrafts over {len(months_sorted)} months. "
                    f"Review cash flow management.",
                    metadata={"overdraft_count": total_overdraft_count}
                ))

            # Flag large unexplained deposits
            unexplained_large = [d for d in large_deposits if not d.get("explained")]
            if unexplained_large:
                flags.append(self.create_warning_flag(
                    FlagRuleId.BANK_LARGE_DEPOSIT_UNEXPLAINED,
                    f"{len(unexplained_large)} large deposit(s) without explanation. "
                    f"May require source documentation.",
                    metadata={"unexplained_deposits": unexplained_large}
                ))

            # Create income stream
            stream = self.create_income_stream(
                stream_type=IncomeStreamType.BANK_STATEMENT,
                stream_name=f"Bank Statement - {account_type.replace('_', ' ').title()}",
                monthly_income=self.round_currency(net_income),
                calculation_inputs={
                    "method": "bank_statement_average",
                    "account_type": account_type,
                    "months_analyzed": len(months_sorted),
                    "expense_ratio": float(final_expense_ratio),
                    "business_type": business_type,
                    "avg_monthly_deposits": float(avg_deposits),
                },
                calculation_steps=calculation_steps,
                document_ids=[bank_statement_facts.document_id] if bank_statement_facts.document_id else [],
                trending_direction=direction,
                trending_percentage=self.round_currency(trend_pct),
                uses_lower_year=uses_lower,
            )

            return self.create_result(
                success=True,
                income_streams=[stream],
                flags=flags
            )

        except Exception as e:
            logger.exception(f"BankStatementEngine calculation error: {e}")
            return self.create_error_result(str(e))

    def analyze_deposit_consistency(
        self,
        bank_statement_facts: BankStatementFacts,
    ) -> Dict[str, Any]:
        """
        Analyze deposit consistency for risk assessment.

        Returns statistics about deposit patterns that may indicate
        business stability or risk factors.
        """
        if not bank_statement_facts or not bank_statement_facts.monthly_data:
            return {"error": "No data available"}

        months = sorted(
            bank_statement_facts.monthly_data,
            key=lambda x: (x.year, x.month)
        )

        deposits = [Decimal(str(m.total_deposits)) for m in months]

        avg_deposit = sum(deposits) / len(deposits)
        min_deposit = min(deposits)
        max_deposit = max(deposits)

        # Calculate coefficient of variation (CV)
        if avg_deposit > 0:
            variance = sum((d - avg_deposit) ** 2 for d in deposits) / len(deposits)
            std_dev = variance ** Decimal("0.5")
            cv = (std_dev / avg_deposit) * 100
        else:
            std_dev = Decimal("0")
            cv = Decimal("0")

        # Count months significantly below average
        below_threshold = sum(1 for d in deposits if d < avg_deposit * Decimal("0.7"))

        # Determine consistency rating
        if cv < Decimal("15"):
            consistency_rating = "excellent"
        elif cv < Decimal("25"):
            consistency_rating = "good"
        elif cv < Decimal("40"):
            consistency_rating = "fair"
        else:
            consistency_rating = "poor"

        return {
            "months_analyzed": len(months),
            "average_deposit": float(avg_deposit),
            "min_deposit": float(min_deposit),
            "max_deposit": float(max_deposit),
            "standard_deviation": float(std_dev),
            "coefficient_of_variation": float(cv),
            "months_below_70pct_average": below_threshold,
            "consistency_rating": consistency_rating,
            "range_ratio": float(max_deposit / min_deposit) if min_deposit > 0 else None,
        }

    def calculate_with_multiple_accounts(
        self,
        account_facts_list: List[BankStatementFacts],
        expense_ratio: Optional[Decimal] = None,
        business_type: Optional[str] = None,
    ) -> EngineResult:
        """
        Calculate income from multiple bank accounts.

        Aggregates deposits across accounts before applying expense ratio.
        Useful when business uses multiple accounts.
        """
        if not account_facts_list:
            return self.create_result(
                success=True,
                income_streams=[],
                flags=[
                    self.create_info_flag(
                        FlagRuleId.BANK_INSUFFICIENT_MONTHS,
                        "No bank statement data provided"
                    )
                ]
            )

        all_income_streams = []
        all_flags = []

        # Process each account
        for account in account_facts_list:
            result = self.calculate(
                bank_statement_facts=account,
                expense_ratio=expense_ratio,
                business_type=business_type,
            )
            all_income_streams.extend(result.income_streams)
            all_flags.extend(result.flags)

        # If multiple accounts, create aggregate stream
        if len(account_facts_list) > 1 and all_income_streams:
            total_monthly = sum(s.monthly_income for s in all_income_streams)

            aggregate_stream = self.create_income_stream(
                stream_type=IncomeStreamType.BANK_STATEMENT,
                stream_name="Bank Statement - Combined Accounts",
                monthly_income=total_monthly,
                calculation_inputs={
                    "method": "bank_statement_combined",
                    "account_count": len(account_facts_list),
                    "individual_amounts": [
                        float(s.monthly_income) for s in all_income_streams
                    ],
                },
                calculation_steps=[
                    self.log_step(
                        "Combine income from multiple accounts",
                        inputs={
                            "account_count": len(all_income_streams),
                            "amounts": [float(s.monthly_income) for s in all_income_streams],
                        },
                        result=float(total_monthly)
                    )
                ],
                document_ids=[],
            )

            # Return aggregate only (individual streams for reference in metadata)
            return self.create_result(
                success=True,
                income_streams=[aggregate_stream],
                flags=all_flags
            )

        return self.create_result(
            success=True,
            income_streams=all_income_streams,
            flags=all_flags
        )
