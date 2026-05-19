"""Flag, recommendation, and follow-up task generation."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List

from .._shared import (
    COMMISSION_SIGNIFICANCE_THRESHOLD_PCT,
    CommissionSource,
    DECLINE_CRITICAL_PCT,
    DECLINE_SEVERE_PCT,
    DECLINE_WARNING_PCT,
    EligibilityResult,
    EMPLOYMENT_GAP_THRESHOLD_DAYS,
    TrendDirection,
    UBE_DEDUCTION_THRESHOLD_PCT,
)

logger = logging.getLogger(__name__)


class GenerationMixin:
    # =========================================================================
    # INTERNAL: FLAG / RECOMMENDATION / TASK GENERATION
    # =========================================================================

    def _generate_flags(
        self,
        sources: List[CommissionSource],
        eligibility: EligibilityResult,
        commission_pct: Decimal,
        overall_trend: TrendDirection,
    ) -> List[str]:
        """Consolidate flags from all sources plus eligibility."""
        flags: List[str] = []

        # Collect per-source flags
        for source in sources:
            for flag in source.flags:
                if flag not in flags:
                    flags.append(flag)

        # Eligibility flags
        for reason in eligibility.disqualifying_reasons:
            flag = f"ELIGIBILITY_ISSUE: {reason}"
            if flag not in flags:
                flags.append(flag)

        for warning in eligibility.warnings:
            flag = f"ELIGIBILITY_WARNING: {warning}"
            if flag not in flags:
                flags.append(flag)

        # Overall commission ratio
        if commission_pct >= COMMISSION_SIGNIFICANCE_THRESHOLD_PCT:
            flag = (
                f"HIGH_COMMISSION_RATIO: Commission is {float(commission_pct):.1f}% "
                f"of total income (threshold: {float(COMMISSION_SIGNIFICANCE_THRESHOLD_PCT)}%)"
            )
            if flag not in flags:
                flags.append(flag)

        # Overall trend
        if overall_trend == TrendDirection.DECLINING:
            flag = "OVERALL_DECLINING_TREND: Commission income is declining across sources"
            if flag not in flags:
                flags.append(flag)

        return flags

    def _generate_recommendations(
        self,
        flags: List[str],
        eligibility: EligibilityResult,
    ) -> List[str]:
        """Generate LO-facing recommendations based on flags."""
        recs: List[str] = []

        flag_text = " ".join(flags)

        if "DECLINING_COMMISSION" in flag_text:
            recs.append(
                "Commission income is declining. Per Fannie Mae B3-3.1, use the "
                "lower of the 2-year average or the most recent 12 months. "
                "Request a written explanation from the borrower and verify "
                "current commission structure with the employer."
            )

        if "HIGH_COMMISSION_RATIO" in flag_text:
            recs.append(
                "Commission exceeds 25% of total income. Ensure 2-year history "
                "is documented with W-2s and tax returns. VOE should confirm "
                "the commission pay structure and probability of continuance."
            )

        if "SINGLE_YEAR_HISTORY" in flag_text or "INSUFFICIENT_DATA" in flag_text:
            recs.append(
                "Less than 2 years of commission history available. "
                "Request additional W-2s, 1099s, or tax returns. If borrower "
                "has 12+ months with current employer and income is stable, "
                "the 1-year exception may apply."
            )

        if "UBE_DEDUCTION" in flag_text:
            recs.append(
                "Unreimbursed business expenses exceed 25% of commission income. "
                "The monthly expense average has been deducted from qualifying "
                "income. Verify expenses with most recent tax returns and "
                "determine if the borrower has since changed to an expense "
                "reimbursement arrangement."
            )

        if "COMMISSION_DERIVED" in flag_text:
            recs.append(
                "Commission amount was derived from W-2 total minus base salary "
                "rather than being explicitly stated. Request VOE with commission "
                "breakdown or paystubs showing commission detail to confirm."
            )

        if "EMPLOYMENT_GAP" in flag_text or "ELIGIBILITY_ISSUE" in flag_text:
            recs.append(
                "Employment gap or eligibility concern detected. Obtain a "
                "letter of explanation from the borrower and VOE from both "
                "current and prior employers."
            )

        if eligibility.can_use_one_year_exception:
            recs.append(
                "1-year commission history exception applied. Document that "
                "income is stable/increasing and borrower has been with "
                "current employer for 12+ months. VOE required."
            )

        if "VOE_EARNINGS_USED" in flag_text:
            recs.append(
                "Prior year earnings from VOE were used due to lack of W-2 "
                "documentation. Obtain W-2s for the applicable tax years "
                "to strengthen the income calculation."
            )

        if not eligibility.is_eligible:
            recs.append(
                "Commission income does NOT currently qualify per agency "
                "guidelines. Review disqualifying reasons and determine if "
                "additional documentation can resolve the issues."
            )

        # Deduplicate
        seen: set = set()
        unique: List[str] = []
        for r in recs:
            key = r[:60]
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique

    def _generate_tasks(
        self,
        flags: List[str],
        eligibility: EligibilityResult,
        loan_id: int,
    ) -> List[Dict[str, Any]]:
        """Generate verification tasks for the LO queue."""
        tasks: List[Dict[str, Any]] = []
        flag_text = " ".join(flags)

        if "DECLINING_COMMISSION" in flag_text:
            tasks.append({
                "task_type": "review_commission_trend",
                "title": "Review declining commission income",
                "description": "Commission income shows a year-over-year decline. "
                               "Review trending data and determine appropriate calculation method.",
                "priority": "high",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Use the lower of 2-year average or most recent 12 months. "
                    "Request written explanation from borrower regarding the decline. "
                    "Consider whether commission should be excluded from qualifying income."
                ),
            })

        if "HIGH_COMMISSION_RATIO" in flag_text:
            tasks.append({
                "task_type": "verify_commission_history",
                "title": "Verify 2-year commission history",
                "description": "Commission exceeds 25% of total income. "
                               "2-year documentation required per Fannie Mae B3-3.1.",
                "priority": "high",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Obtain 2 years of W-2s showing commission earnings. "
                    "Request VOE confirming commission structure and probability of continuance."
                ),
            })

        if "SINGLE_YEAR_HISTORY" in flag_text:
            tasks.append({
                "task_type": "request_additional_docs",
                "title": "Obtain additional commission income documentation",
                "description": "Only 1 year of commission history available. "
                               "2-year history preferred.",
                "priority": "medium",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Request prior year W-2 or 1099 forms. If unavailable, "
                    "document the 1-year exception criteria (stable income, "
                    "12+ months with employer)."
                ),
            })

        if "UBE_DEDUCTION" in flag_text:
            tasks.append({
                "task_type": "review_business_expenses",
                "title": "Review unreimbursed business expenses",
                "description": "Business expenses exceed 25% of commission income. "
                               "Deduction applied to qualifying income.",
                "priority": "medium",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Verify expense amounts from most recent tax returns. "
                    "Check if borrower's expense reimbursement arrangement has changed."
                ),
            })

        if not eligibility.is_eligible:
            tasks.append({
                "task_type": "commission_eligibility_review",
                "title": "Commission income eligibility review required",
                "description": "Commission income does not currently meet agency "
                               "qualification requirements. Manual review needed.",
                "priority": "critical",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Review disqualifying reasons and determine if additional "
                    "documentation can resolve the issues. Consider restructuring "
                    "the income calculation to exclude commission if needed."
                ),
            })

        if "EMPLOYMENT_GAP" in flag_text or eligibility.has_employment_gap:
            tasks.append({
                "task_type": "verify_employment_continuity",
                "title": "Verify employment continuity for commission earner",
                "description": f"Employment gap of {eligibility.gap_days} days detected.",
                "priority": "high",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Obtain letter of explanation for the employment gap. "
                    "VOE from both current and prior employers may be required."
                ),
            })

        if "COMMISSION_DERIVED" in flag_text:
            tasks.append({
                "task_type": "request_voe",
                "title": "Obtain VOE with commission breakdown",
                "description": "Commission amount was derived (not explicitly documented). "
                               "VOE or detailed paystubs needed to confirm.",
                "priority": "medium",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Request VOE that itemizes base salary vs. commission earnings. "
                    "Alternatively, obtain paystubs showing commission detail."
                ),
            })

        return tasks

    # =========================================================================
    # INTERNAL: PERSISTENCE
    # =========================================================================
