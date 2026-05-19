"""Eligibility validation for commission income."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP
from typing import Any, Dict, List

from .._shared import (
    COMMISSION_SIGNIFICANCE_THRESHOLD_PCT,
    CommissionSource,
    EligibilityResult,
    EMPLOYMENT_GAP_THRESHOLD_DAYS,
    HISTORY_YEARS_MINIMUM,
    HISTORY_YEARS_REQUIRED,
    MONTHS_PER_YEAR,
    ONE_HUNDRED,
    TWO_PLACES,
    TrendDirection,
    ZERO,
    _audit,
    _parse_date,
    _to_decimal,
)

logger = logging.getLogger(__name__)


class EligibilityMixin:
    # =========================================================================
    # 4. ELIGIBILITY VALIDATION (public API)
    # =========================================================================

    def validate_commission_eligibility(
        self,
        employment_data: Dict[str, Any],
    ) -> EligibilityResult:
        """
        Validate whether commission income is eligible for qualification.

        Checks employment continuity, history requirements, employer
        consistency, and income trajectory per agency guidelines.

        Args:
            employment_data: Dict with keys:
                - employer_name (str)
                - employer_ein (str, optional)
                - start_date (str or date): employment start date
                - current_employer (bool): still employed here
                - prior_employer_name (str, optional)
                - prior_employer_start_date (str or date, optional)
                - prior_employer_end_date (str or date, optional)
                - industry (str, optional)
                - prior_industry (str, optional)
                - years_commission_history (int)
                - commission_pct_of_total (Decimal or float)
                - year1_commission (Decimal or float)
                - year2_commission (Decimal or float, optional)
                - total_gross_income (Decimal or float)

        Returns:
            EligibilityResult with detailed assessment.
        """
        disqualifying: List[str] = []
        warnings: List[str] = []

        # Commission significance check
        commission_pct = _to_decimal(employment_data.get("commission_pct_of_total", 0))
        total_gross = _to_decimal(employment_data.get("total_gross_income", 0))
        year1_commission = _to_decimal(employment_data.get("year1_commission", 0))
        year2_commission_raw = employment_data.get("year2_commission")
        year2_commission = _to_decimal(year2_commission_raw) if year2_commission_raw is not None else None

        if total_gross > ZERO and commission_pct == ZERO:
            # Recalculate from raw amounts
            commission_pct = (year1_commission / total_gross * ONE_HUNDRED).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

        requires_two_year = commission_pct >= COMMISSION_SIGNIFICANCE_THRESHOLD_PCT

        # Employment duration
        start_date = _parse_date(employment_data.get("start_date"))
        today = date.today()
        if start_date:
            employment_days = (today - start_date).days
            employment_months = max(0, employment_days // 30)
        else:
            employment_months = int(employment_data.get("years_commission_history", 0)) * 12

        # History sufficiency
        has_year2 = year2_commission is not None and year2_commission > ZERO
        years_available = 2 if has_year2 else (1 if year1_commission > ZERO else 0)
        has_sufficient_history = years_available >= HISTORY_YEARS_REQUIRED

        # 1-year exception check
        can_use_one_year = False
        if not has_sufficient_history and years_available >= HISTORY_YEARS_MINIMUM:
            # Allowed if: stable/increasing AND >= 12 months with same employer
            is_current = employment_data.get("current_employer", True)
            if is_current and employment_months >= 12:
                # Check trend
                if has_year2:
                    if year1_commission >= year2_commission:
                        can_use_one_year = True
                else:
                    # Only 1 year of data -- allowed with 12+ months tenure
                    can_use_one_year = True

                if can_use_one_year:
                    warnings.append(
                        "Using 1-year commission history exception: income is "
                        "stable/increasing with 12+ months at current employer."
                    )
            else:
                if not is_current:
                    disqualifying.append(
                        "Commission income requires 2-year history. Borrower is no "
                        "longer with the commission-earning employer."
                    )
                elif employment_months < 12:
                    disqualifying.append(
                        f"Commission income requires 2-year history or 12+ months "
                        f"with current employer (currently {employment_months} months)."
                    )

        if requires_two_year and not has_sufficient_history and not can_use_one_year:
            disqualifying.append(
                f"Commission is {commission_pct}% of total income (>= 25% threshold). "
                f"2-year history required but only {years_available} year(s) available."
            )

        # Employer consistency
        employer_name = employment_data.get("employer_name", "")
        prior_employer = employment_data.get("prior_employer_name", "")
        employer_consistent = True

        if prior_employer and employer_name:
            if employer_name.lower().strip() != prior_employer.lower().strip():
                employer_consistent = False
                industry = (employment_data.get("industry") or "").lower()
                prior_industry = (employment_data.get("prior_industry") or "").lower()

                if industry and prior_industry and industry == prior_industry:
                    warnings.append(
                        f"Employer changed ({prior_employer} -> {employer_name}) "
                        f"but same industry ({industry}). May be acceptable with "
                        f"letter of explanation."
                    )
                else:
                    warnings.append(
                        f"Employer changed ({prior_employer} -> {employer_name}). "
                        "Different employer and/or industry may affect commission "
                        "income continuity assessment."
                    )

        # Employment gap detection
        has_gap = False
        gap_days = 0
        prior_end = _parse_date(employment_data.get("prior_employer_end_date"))
        if prior_end and start_date:
            gap_days = (start_date - prior_end).days
            if gap_days > EMPLOYMENT_GAP_THRESHOLD_DAYS:
                has_gap = True
                disqualifying.append(
                    f"Employment gap of {gap_days} days detected between prior "
                    f"employer and current position (threshold: {EMPLOYMENT_GAP_THRESHOLD_DAYS} days). "
                    f"Additional documentation required."
                )
            elif gap_days > 30:
                has_gap = True
                warnings.append(
                    f"Employment gap of {gap_days} days detected. Letter of "
                    f"explanation may be required."
                )

        # Income trajectory check
        if has_year2 and year2_commission > ZERO:
            decline_pct = ZERO
            if year1_commission < year2_commission:
                decline_pct = (
                    (year2_commission - year1_commission) / year2_commission * ONE_HUNDRED
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if decline_pct > DECLINE_CRITICAL_PCT:
                warnings.append(
                    f"Commission income declined {decline_pct}% year-over-year. "
                    "Use lower of 2-year average or most recent 12 months."
                )

        is_eligible = len(disqualifying) == 0

        notes = ""
        if is_eligible and requires_two_year:
            if has_sufficient_history:
                notes = "Commission qualifies with 2-year history. Use appropriate averaging method."
            elif can_use_one_year:
                notes = "Commission qualifies under 1-year exception (stable/increasing, 12+ months tenure)."
        elif is_eligible:
            notes = "Commission < 25% of total income. Standard employment verification sufficient."

        return EligibilityResult(
            is_eligible=is_eligible,
            requires_two_year_history=requires_two_year,
            has_sufficient_history=has_sufficient_history or can_use_one_year,
            commission_pct_of_total=commission_pct,
            employment_months=employment_months,
            employer_consistent=employer_consistent,
            has_employment_gap=has_gap,
            gap_days=gap_days,
            can_use_one_year_exception=can_use_one_year,
            disqualifying_reasons=disqualifying,
            warnings=warnings,
            notes=notes,
        )

    # =========================================================================
    # 5. OVERRIDE CAPABILITY
    # =========================================================================

    # =========================================================================
    # INTERNAL: ELIGIBILITY VALIDATION (for internal pipeline use)
    # =========================================================================

    def _validate_commission_eligibility(
        self,
        sources: List[CommissionSource],
        total_gross_income: Decimal,
        audit_trail: List[Dict[str, Any]],
    ) -> EligibilityResult:
        """
        Run eligibility checks across all commission sources.
        Delegates to the public validate_commission_eligibility method
        after assembling employment data from parsed sources.
        """
        if not sources:
            return EligibilityResult(
                is_eligible=False,
                requires_two_year_history=False,
                has_sufficient_history=False,
                commission_pct_of_total=ZERO,
                employment_months=0,
                employer_consistent=True,
                has_employment_gap=False,
                disqualifying_reasons=["No commission sources found."],
            )

        # Use primary (highest-paying) source for eligibility
        primary = max(sources, key=lambda s: s.qualifying_monthly_commission)

        total_monthly_commission = sum(
            (s.qualifying_monthly_commission for s in sources), ZERO,
        )

        # Commission as % of total income
        if total_gross_income > ZERO:
            commission_pct = (
                total_monthly_commission / total_gross_income * ONE_HUNDRED
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            commission_pct = ONE_HUNDRED if total_monthly_commission > ZERO else ZERO

        employment_data: Dict[str, Any] = {
            "employer_name": primary.employer_name,
            "employer_ein": primary.employer_ein,
            "start_date": primary.start_date,
            "current_employer": True,
            "years_commission_history": HISTORY_YEARS_REQUIRED if primary.year2_tax_year else HISTORY_YEARS_MINIMUM,
            "commission_pct_of_total": commission_pct,
            "year1_commission": primary.year1_commission,
            "year2_commission": primary.year2_commission if primary.year2_commission > ZERO else None,
            "total_gross_income": total_gross_income if total_gross_income > ZERO else total_monthly_commission,
        }

        # Check for employer consistency across sources if multiple
        if len(sources) > 1:
            employers = [s.employer_name for s in sources if s.employer_name]
            unique_employers = set(e.lower().strip() for e in employers if e)
            if len(unique_employers) > 1:
                employment_data["prior_employer_name"] = sorted(unique_employers)[-1]

        eligibility = self.validate_commission_eligibility(employment_data)

        _audit(audit_trail, "eligibility_checked", eligibility.to_dict())

        return eligibility

    # =========================================================================
    # INTERNAL: AGGREGATE HELPERS
