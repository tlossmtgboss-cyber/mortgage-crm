"""Per-source income calculation and method selection logic."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from .._shared import (
    CalculationMethod,
    CommissionSource,
    CommissionType,
    DECLINE_CRITICAL_PCT,
    DECLINE_SEVERE_PCT,
    DECLINE_WARNING_PCT,
    MONTHS_PER_TWO_YEARS,
    MONTHS_PER_YEAR,
    ONE_HUNDRED,
    TWO_PLACES,
    TrendDirection,
    ZERO,
    _audit,
    _to_decimal,
)

logger = logging.getLogger(__name__)


class CalculationMixin:
    # =========================================================================
    # INTERNAL: SINGLE SOURCE CALCULATION
    # =========================================================================

    def _calculate_single_source(
        self,
        parsed: Dict[str, Any],
        audit_trail: List[Dict[str, Any]],
    ) -> CommissionSource:
        """
        Calculate qualifying commission income for a single employer/source.

        Applies the appropriate calculation method based on data availability
        and income trending:
        - 2-year simple average (default)
        - Weighted average (recent year weighted 60%)
        - YTD annualization (if insufficient prior year data)
        - Most-recent-12-months (declining income)
        """
        source_id = str(uuid.uuid4())[:12]
        employer_name = parsed.get("employer_name")
        employer_ein = parsed.get("employer_ein")
        position_title = parsed.get("position_title")
        commission_type = parsed.get("commission_type", CommissionType.W2_COMMISSION)
        yearly_data = parsed.get("yearly_data", {})
        ytd_data = parsed.get("ytd_data")
        voe_data = parsed.get("voe_data")
        expense_data = parsed.get("expense_data", [])
        doc_ids = parsed.get("doc_ids", [])
        flags: List[str] = []

        # Sort years descending
        sorted_years = sorted(yearly_data.keys(), reverse=True)

        # Extract year 1 (most recent) and year 2 (prior)
        year1_tax_year: Optional[int] = None
        year1_commission = ZERO
        year1_base = ZERO
        year1_total_w2 = ZERO

        year2_tax_year: Optional[int] = None
        year2_commission = ZERO
        year2_base = ZERO
        year2_total_w2 = ZERO

        if len(sorted_years) >= 1:
            year1_tax_year = sorted_years[0]
            yd1 = yearly_data[year1_tax_year]
            year1_commission = _to_decimal(yd1.get("commission"))
            year1_base = _to_decimal(yd1.get("base"))
            year1_total_w2 = _to_decimal(yd1.get("total_w2"))

            # If commission not separated, attempt derivation from W-2 total minus base
            if year1_commission == ZERO and year1_total_w2 > year1_base and year1_base > ZERO:
                year1_commission = (year1_total_w2 - year1_base).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
                flags.append(
                    f"COMMISSION_DERIVED: {year1_tax_year} commission derived from "
                    f"W-2 total minus base salary"
                )

            # Schedule C add-backs
            depreciation = _to_decimal(yd1.get("depreciation_addback"))
            amortization = _to_decimal(yd1.get("amortization_addback"))
            if depreciation > ZERO or amortization > ZERO:
                year1_commission = (year1_commission + depreciation + amortization).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
                flags.append(
                    f"ADDBACKS_APPLIED: {year1_tax_year} depreciation "
                    f"(${float(depreciation):,.2f}) and amortization "
                    f"(${float(amortization):,.2f}) added back per Fannie Mae"
                )

        if len(sorted_years) >= 2:
            year2_tax_year = sorted_years[1]
            yd2 = yearly_data[year2_tax_year]
            year2_commission = _to_decimal(yd2.get("commission"))
            year2_base = _to_decimal(yd2.get("base"))
            year2_total_w2 = _to_decimal(yd2.get("total_w2"))

            # Same derivation logic for year 2
            if year2_commission == ZERO and year2_total_w2 > year2_base and year2_base > ZERO:
                year2_commission = (year2_total_w2 - year2_base).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )

            # Schedule C add-backs for year 2
            depreciation2 = _to_decimal(yd2.get("depreciation_addback"))
            amortization2 = _to_decimal(yd2.get("amortization_addback"))
            if depreciation2 > ZERO or amortization2 > ZERO:
                year2_commission = (year2_commission + depreciation2 + amortization2).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )

        # YTD data
        ytd_commission = ZERO
        ytd_base = ZERO
        ytd_total_gross = ZERO
        ytd_months_elapsed = 0
        if ytd_data:
            ytd_commission = _to_decimal(ytd_data.get("commission"))
            ytd_base = _to_decimal(ytd_data.get("base"))
            ytd_total_gross = _to_decimal(ytd_data.get("total_gross"))
            ytd_months_elapsed = ytd_data.get("months_elapsed", 0)

        # VOE-derived start date and tenure
        start_date: Optional[date] = None
        years_in_role: Optional[Decimal] = None
        if voe_data:
            start_date = _parse_date(voe_data.get("start_date"))
            if start_date:
                tenure_days = (date.today() - start_date).days
                years_in_role = (Decimal(tenure_days) / Decimal("365.25")).quantize(
                    FOUR_PLACES, rounding=ROUND_HALF_UP,
                )

            # Supplement with VOE earnings if we lack W-2 data
            if not sorted_years:
                voe_yr1 = _to_decimal(voe_data.get("prior_year1_earnings"))
                voe_yr2 = _to_decimal(voe_data.get("prior_year2_earnings"))
                current_year = date.today().year
                if voe_yr1 > ZERO:
                    # Treat VOE prior year earnings as total (cannot split)
                    yearly_data[current_year - 1] = {
                        "commission": voe_yr1,
                        "base": ZERO,
                        "total_w2": voe_yr1,
                        "source": "VOE",
                    }
                    year1_tax_year = current_year - 1
                    year1_commission = voe_yr1
                    year1_total_w2 = voe_yr1
                    sorted_years.append(current_year - 1)
                    flags.append("VOE_EARNINGS_USED: Prior year earnings from VOE used (no W-2 available)")

                if voe_yr2 > ZERO:
                    yearly_data[current_year - 2] = {
                        "commission": voe_yr2,
                        "base": ZERO,
                        "total_w2": voe_yr2,
                        "source": "VOE",
                    }
                    year2_tax_year = current_year - 2
                    year2_commission = voe_yr2
                    year2_total_w2 = voe_yr2
                    sorted_years.append(current_year - 2)

        # --- Trending analysis ---
        income_history: List[Dict[str, Any]] = []
        if year1_commission > ZERO and year1_tax_year:
            entry1: Dict[str, Any] = {
                "tax_year": year1_tax_year,
                "commission_amount": year1_commission,
            }
            if ytd_commission > ZERO and ytd_months_elapsed > 0:
                entry1["ytd_amount"] = ytd_commission
                entry1["ytd_months"] = ytd_months_elapsed
            income_history.append(entry1)
        if year2_commission > ZERO and year2_tax_year:
            income_history.append({
                "tax_year": year2_tax_year,
                "commission_amount": year2_commission,
            })

        trend = self.analyze_trending(income_history)

        # --- Unreimbursed expense analysis ---
        expense_analysis: Optional[ExpenseAnalysis] = None
        if expense_data:
            expense_analysis = self.calculate_unreimbursed_expenses(expense_data)
            if expense_analysis.exceeds_threshold:
                flags.append(
                    f"UBE_DEDUCTION: Unreimbursed business expenses "
                    f"({expense_analysis.expense_ratio_pct}% of commission) "
                    f"exceed {UBE_DEDUCTION_THRESHOLD_PCT}% threshold. "
                    f"Monthly deduction: ${float(expense_analysis.deduction_amount):,.2f}"
                )

        # --- Determine calculation method and compute qualifying income ---
        method, monthly_commission, monthly_base = self._select_and_calculate(
            year1_commission=year1_commission,
            year2_commission=year2_commission,
            year1_base=year1_base,
            year2_base=year2_base,
            ytd_commission=ytd_commission,
            ytd_base=ytd_base,
            ytd_months_elapsed=ytd_months_elapsed,
            trend=trend,
            has_two_years=year2_tax_year is not None and year2_commission > ZERO,
            flags=flags,
        )

        # Apply UBE deduction if applicable
        if expense_analysis and expense_analysis.exceeds_threshold:
            monthly_commission = max(
                ZERO,
                (monthly_commission - expense_analysis.deduction_amount).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                ),
            )
            flags.append(
                f"UBE_APPLIED: Commission reduced by ${float(expense_analysis.deduction_amount):,.2f}/mo "
                f"for unreimbursed business expenses"
            )

        monthly_total = (monthly_commission + monthly_base).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        # Confidence scoring
        confidence = self._calculate_source_confidence(
            has_w2=any(yd.get("source") == "W2" for yd in yearly_data.values()),
            has_paystub=ytd_data is not None,
            has_voe=voe_data is not None,
            has_two_years=year2_tax_year is not None,
            trend=trend,
            commission_derived="COMMISSION_DERIVED" in " ".join(flags),
        )

        _audit(audit_trail, "source_calculated", {
            "source_id": source_id,
            "employer": employer_name,
            "method": method.value,
            "monthly_commission": float(monthly_commission),
            "monthly_base": float(monthly_base),
            "monthly_total": float(monthly_total),
            "trend": trend.direction.value,
            "confidence": confidence,
        })

        return CommissionSource(
            source_id=source_id,
            commission_type=commission_type,
            employer_name=employer_name,
            employer_ein=employer_ein,
            position_title=position_title,
            start_date=start_date,
            years_in_role=years_in_role,
            year1_commission=year1_commission,
            year1_base_salary=year1_base,
            year1_total_w2=year1_total_w2,
            year1_tax_year=year1_tax_year,
            year2_commission=year2_commission,
            year2_base_salary=year2_base,
            year2_total_w2=year2_total_w2,
            year2_tax_year=year2_tax_year,
            ytd_commission=ytd_commission,
            ytd_base_salary=ytd_base,
            ytd_total_gross=ytd_total_gross,
            ytd_months_elapsed=ytd_months_elapsed,
            qualifying_monthly_commission=monthly_commission,
            qualifying_monthly_base=monthly_base,
            qualifying_monthly_total=monthly_total,
            calculation_method=method,
            trend_analysis=trend,
            expense_analysis=expense_analysis,
            source_doc_ids=doc_ids,
            confidence=confidence,
            flags=flags,
            notes=f"Commission income from {employer_name or 'unknown employer'} "
                  f"calculated using {method.value} method.",
        )

    # =========================================================================
    # INTERNAL: METHOD SELECTION & CALCULATION
    # =========================================================================

    def _select_and_calculate(
        self,
        year1_commission: Decimal,
        year2_commission: Decimal,
        year1_base: Decimal,
        year2_base: Decimal,
        ytd_commission: Decimal,
        ytd_base: Decimal,
        ytd_months_elapsed: int,
        trend: TrendAnalysis,
        has_two_years: bool,
        flags: List[str],
    ) -> Tuple[CalculationMethod, Decimal, Decimal]:
        """
        Select the appropriate calculation method and compute monthly
        qualifying amounts for both commission and base salary.

        Per Fannie Mae B3-3.1:
        - Stable/increasing with 2 years: simple average (Y1+Y2)/24
        - Declining: use lower of 2-year average or most recent 12 months
        - Only 1 year (with exception): single year / 12
        - YTD only: annualize current YTD

        Returns:
            (method, monthly_commission, monthly_base)
        """
        if has_two_years:
            # --- 2-year data available ---

            # Simple average: (Year1 + Year2) / 24
            simple_avg_commission = (
                (year1_commission + year2_commission) / MONTHS_PER_TWO_YEARS
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            simple_avg_base = (
                (year1_base + year2_base) / MONTHS_PER_TWO_YEARS
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Check for declining income
            if trend.direction == TrendDirection.DECLINING:
                decline_pct = abs(trend.yoy_change_pct or ZERO)

                if decline_pct >= DECLINE_CRITICAL_PCT:
                    # Use most recent 12 months only
                    recent_monthly_commission = (year1_commission / MONTHS_PER_YEAR).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP,
                    )
                    recent_monthly_base = (year1_base / MONTHS_PER_YEAR).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP,
                    )

                    # Use the LOWER of 2-year average or most recent year
                    if recent_monthly_commission <= simple_avg_commission:
                        flags.append(
                            f"DECLINING_COMMISSION: Income declined {float(decline_pct):.1f}% "
                            f"YoY. Using most recent year (${float(recent_monthly_commission):,.2f}/mo) "
                            f"which is lower than 2-year average (${float(simple_avg_commission):,.2f}/mo)."
                        )
                        return (
                            CalculationMethod.MOST_RECENT_12_MONTHS,
                            recent_monthly_commission,
                            recent_monthly_base,
                        )
                    else:
                        flags.append(
                            f"DECLINING_COMMISSION: Income declined {float(decline_pct):.1f}% "
                            f"YoY. Using 2-year average (${float(simple_avg_commission):,.2f}/mo) "
                            f"which is lower than most recent year."
                        )
                        return (
                            CalculationMethod.SIMPLE_AVERAGE,
                            simple_avg_commission,
                            simple_avg_base,
                        )

                elif decline_pct >= DECLINE_WARNING_PCT:
                    flags.append(
                        f"COMMISSION_DECLINE_WARNING: Income declined {float(decline_pct):.1f}% "
                        f"YoY. Using 2-year average but flagged for LO review."
                    )

            # Stable or increasing: check if weighted average is more favorable
            if trend.direction == TrendDirection.INCREASING:
                # Weighted: 60% recent year, 40% prior year
                weighted_commission = (
                    year1_commission * Decimal("0.6") + year2_commission * Decimal("0.4")
                ) / MONTHS_PER_YEAR
                weighted_commission = weighted_commission.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                weighted_base = (
                    year1_base * Decimal("0.6") + year2_base * Decimal("0.4")
                ) / MONTHS_PER_YEAR
                weighted_base = weighted_base.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                # Use the LOWER of simple average or weighted (conservative per guidelines)
                if weighted_commission < simple_avg_commission:
                    return (CalculationMethod.WEIGHTED_AVERAGE, weighted_commission, weighted_base)

            # Default to simple average
            return (CalculationMethod.SIMPLE_AVERAGE, simple_avg_commission, simple_avg_base)

        elif year1_commission > ZERO:
            # --- Only 1 year of data ---

            # Check if YTD can supplement
            if ytd_commission > ZERO and ytd_months_elapsed >= 3:
                # Annualize YTD
                ytd_annualized_commission = (
                    ytd_commission / Decimal(ytd_months_elapsed) * MONTHS_PER_YEAR
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                ytd_annualized_base = ZERO
                if ytd_base > ZERO and ytd_months_elapsed > 0:
                    ytd_annualized_base = (
                        ytd_base / Decimal(ytd_months_elapsed) * MONTHS_PER_YEAR
                    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                # Use lower of prior year and YTD annualized (conservative)
                ytd_monthly = (ytd_annualized_commission / MONTHS_PER_YEAR).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
                year1_monthly = (year1_commission / MONTHS_PER_YEAR).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )

                if ytd_monthly < year1_monthly:
                    flags.append(
                        f"YTD_LOWER: YTD annualized commission "
                        f"(${float(ytd_monthly):,.2f}/mo) is lower than prior year "
                        f"(${float(year1_monthly):,.2f}/mo). Using YTD annualized."
                    )
                    monthly_base = (ytd_annualized_base / MONTHS_PER_YEAR).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP,
                    )
                    return (CalculationMethod.YTD_ANNUALIZED, ytd_monthly, monthly_base)
                else:
                    return (CalculationMethod.SINGLE_YEAR, year1_monthly, (year1_base / MONTHS_PER_YEAR).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))

            # Single year only
            flags.append(
                "SINGLE_YEAR_HISTORY: Only 1 year of commission data available. "
                "2-year history preferred per agency guidelines."
            )
            monthly_commission = (year1_commission / MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
            monthly_base = (year1_base / MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
            return (CalculationMethod.SINGLE_YEAR, monthly_commission, monthly_base)

        elif ytd_commission > ZERO and ytd_months_elapsed >= 3:
            # --- YTD only (no prior year) ---
            flags.append(
                "YTD_ONLY: No prior year data. Commission income annualized from "
                f"{ytd_months_elapsed} months of YTD data."
            )
            monthly_commission = (
                ytd_commission / Decimal(ytd_months_elapsed)
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            monthly_base = ZERO
            if ytd_base > ZERO:
                monthly_base = (
                    ytd_base / Decimal(ytd_months_elapsed)
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            return (CalculationMethod.YTD_ANNUALIZED, monthly_commission, monthly_base)

        else:
            # No usable data
            flags.append("INSUFFICIENT_DATA: No commission income data available for calculation.")
            return (CalculationMethod.SIMPLE_AVERAGE, ZERO, ZERO)

    # =========================================================================
    # INTERNAL: ELIGIBILITY VALIDATION (for internal pipeline use)
    # =========================================================================
