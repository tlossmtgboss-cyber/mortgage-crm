"""
Income Calculator Module

Calculates qualifying income per Fannie Mae, Freddie Mac, FHA, and VA guidelines.
Supports all income types including:
- W-2 base employment
- Overtime, bonus, commission (variable income)
- Self-employment (Schedule C, S-Corp, Partnership)
- Rental income (Schedule E)
- Retirement/pension/Social Security
- Other income (alimony, child support, disability)

References:
- Fannie Mae Selling Guide B3-3.1 (Employment and Other Sources of Income)
- Freddie Mac Guide Chapter 5300 (Income Assessment)
- FHA 4000.1 II.A.4 (Effective Income)
- VA Pamphlet 26-7 Chapter 4 (Credit Underwriting)
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)


class IncomeType(str, Enum):
    """Types of income for qualification."""
    BASE_EMPLOYMENT = "base_employment"
    OVERTIME = "overtime"
    BONUS = "bonus"
    COMMISSION = "commission"
    SELF_EMPLOYMENT = "self_employment"
    PARTNERSHIP = "partnership"
    S_CORP = "s_corp"
    RENTAL = "rental"
    SOCIAL_SECURITY = "social_security"
    PENSION = "pension"
    DISABILITY = "disability"
    ALIMONY = "alimony"
    CHILD_SUPPORT = "child_support"
    MILITARY = "military"
    INTEREST_DIVIDENDS = "interest_dividends"
    NOTES_RECEIVABLE = "notes_receivable"
    OTHER = "other"


class IncomeStatus(str, Enum):
    """Status of income calculation."""
    CALCULATED = "calculated"
    NEEDS_DOCUMENTATION = "needs_documentation"
    TRENDING_ANALYSIS_REQUIRED = "trending_analysis_required"
    INELIGIBLE = "ineligible"
    EXCLUDED = "excluded"


@dataclass
class IncomeItem:
    """Individual income item with calculation details."""
    income_type: IncomeType
    source_name: str
    gross_monthly: Decimal
    qualifying_monthly: Decimal
    calculation_method: str
    status: IncomeStatus
    documentation_status: str  # complete, partial, missing
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    guideline_reference: str = ""
    notes: str = ""
    # For trending analysis
    year1_income: Optional[Decimal] = None
    year2_income: Optional[Decimal] = None
    ytd_income: Optional[Decimal] = None
    ytd_months: Optional[int] = None
    trending: Optional[str] = None  # stable, increasing, declining


@dataclass
class IncomeResult:
    """Complete income calculation result."""
    total_qualifying_monthly: Decimal
    total_gross_monthly: Decimal
    borrower_items: List[IncomeItem]
    coborrower_items: List[IncomeItem]
    household_monthly: Decimal
    is_complete: bool
    issues: List[str]
    warnings: List[str]
    conditions_needed: List[Dict[str, Any]]
    calculation_summary: Dict[str, Any]


class IncomeCalculator:
    """
    Calculates qualifying income per agency guidelines.

    Key principles:
    1. Use conservative (lower) income when doubt exists
    2. Require 2-year history for variable income
    3. Decline trending income must be addressed
    4. Non-taxable income can be grossed up (125% for conv, varies by program)
    5. Income must be stable and likely to continue
    """

    # Gross-up factors for non-taxable income by program
    GROSS_UP_FACTORS = {
        "conventional": Decimal("1.25"),
        "fha": Decimal("1.25"),
        "va": Decimal("1.25"),
        "usda": Decimal("1.00"),  # USDA uses actual income
    }

    # Minimum history requirements (in months)
    HISTORY_REQUIREMENTS = {
        IncomeType.BASE_EMPLOYMENT: 0,  # Current employed is sufficient with 2yr work history
        IncomeType.OVERTIME: 24,
        IncomeType.BONUS: 24,
        IncomeType.COMMISSION: 24,
        IncomeType.SELF_EMPLOYMENT: 24,
        IncomeType.RENTAL: 12,  # Or 2 years tax returns
        IncomeType.ALIMONY: 6,  # Must continue 3+ years
        IncomeType.CHILD_SUPPORT: 6,  # Must continue 3+ years
    }

    def __init__(self, loan_program: str = "conventional"):
        """Initialize calculator for specific loan program."""
        self.loan_program = loan_program.lower()
        self.gross_up_factor = self.GROSS_UP_FACTORS.get(
            self.loan_program, Decimal("1.25")
        )

    def calculate_all_income(
        self,
        borrower_income_data: Dict[str, Any],
        coborrower_income_data: Optional[Dict[str, Any]] = None,
    ) -> IncomeResult:
        """
        Calculate total qualifying income for all borrowers.

        Args:
            borrower_income_data: Dictionary containing borrower income details
            coborrower_income_data: Optional co-borrower income

        Returns:
            IncomeResult with complete calculation
        """
        borrower_items = self._calculate_borrower_income(borrower_income_data)
        coborrower_items = []

        if coborrower_income_data:
            coborrower_items = self._calculate_borrower_income(coborrower_income_data)

        # Sum up qualifying income
        borrower_total = sum(item.qualifying_monthly for item in borrower_items)
        coborrower_total = sum(item.qualifying_monthly for item in coborrower_items)
        household_total = borrower_total + coborrower_total

        # Sum up gross income
        borrower_gross = sum(item.gross_monthly for item in borrower_items)
        coborrower_gross = sum(item.gross_monthly for item in coborrower_items)
        total_gross = borrower_gross + coborrower_gross

        # Collect all issues and warnings
        all_issues = []
        all_warnings = []
        conditions_needed = []

        for item in borrower_items + coborrower_items:
            all_issues.extend(item.issues)
            all_warnings.extend(item.warnings)

            # Generate conditions based on status
            if item.status == IncomeStatus.NEEDS_DOCUMENTATION:
                conditions_needed.append({
                    "type": "prior_to_docs",
                    "category": "income",
                    "title": f"Income Documentation - {item.source_name}",
                    "description": f"Provide documentation for {item.income_type.value} income from {item.source_name}",
                    "guideline": item.guideline_reference,
                })
            elif item.status == IncomeStatus.TRENDING_ANALYSIS_REQUIRED:
                conditions_needed.append({
                    "type": "prior_to_approval",
                    "category": "income",
                    "title": f"Income Trending Review - {item.source_name}",
                    "description": f"Declining income trend detected for {item.source_name}. Provide explanation and YTD documentation.",
                    "guideline": item.guideline_reference,
                })

        is_complete = all(
            item.documentation_status == "complete" and
            item.status in [IncomeStatus.CALCULATED, IncomeStatus.EXCLUDED]
            for item in borrower_items + coborrower_items
        )

        return IncomeResult(
            total_qualifying_monthly=household_total,
            total_gross_monthly=total_gross,
            borrower_items=borrower_items,
            coborrower_items=coborrower_items,
            household_monthly=household_total,
            is_complete=is_complete,
            issues=all_issues,
            warnings=all_warnings,
            conditions_needed=conditions_needed,
            calculation_summary={
                "borrower_qualifying": float(borrower_total),
                "coborrower_qualifying": float(coborrower_total),
                "household_qualifying": float(household_total),
                "income_sources": len(borrower_items) + len(coborrower_items),
                "program": self.loan_program,
            }
        )

    def _calculate_borrower_income(
        self,
        income_data: Dict[str, Any]
    ) -> List[IncomeItem]:
        """Calculate all income items for a single borrower."""
        items = []

        # W-2 Employment Income
        if income_data.get("employment"):
            for emp in self._ensure_list(income_data["employment"]):
                item = self._calculate_employment_income(emp)
                items.append(item)

        # Self-Employment Income
        if income_data.get("self_employment"):
            for se in self._ensure_list(income_data["self_employment"]):
                item = self._calculate_self_employment_income(se)
                items.append(item)

        # Variable Income (OT, Bonus, Commission)
        if income_data.get("variable_income"):
            for var in self._ensure_list(income_data["variable_income"]):
                item = self._calculate_variable_income(var)
                items.append(item)

        # Rental Income
        if income_data.get("rental_income"):
            for rental in self._ensure_list(income_data["rental_income"]):
                item = self._calculate_rental_income(rental)
                items.append(item)

        # Retirement/Pension/SS
        if income_data.get("retirement_income"):
            for ret in self._ensure_list(income_data["retirement_income"]):
                item = self._calculate_retirement_income(ret)
                items.append(item)

        # Other Income (Alimony, Child Support, etc.)
        if income_data.get("other_income"):
            for other in self._ensure_list(income_data["other_income"]):
                item = self._calculate_other_income(other)
                items.append(item)

        return items

    def _calculate_employment_income(self, emp: Dict[str, Any]) -> IncomeItem:
        """
        Calculate W-2 employment income.

        Per Fannie Mae B3-3.1-01 (updated 03/04/2026):
        - Use current pay stub to verify employment and year-to-date earnings
        - Base income uses most recent pay period annualized
        - Only the most recent W-2 is required for fixed/stable base income
        - Must verify 2-year employment history (can be different employers)
        - NOTE: 2-year W-2 requirement STILL applies to variable income
          (overtime, bonus, commission) -- see _calculate_variable_income()
        """
        employer_name = emp.get("employer_name", "Unknown Employer")
        base_monthly = Decimal(str(emp.get("base_monthly", 0)))
        pay_frequency = emp.get("pay_frequency", "monthly")
        years_employed = emp.get("years_employed", 0)
        months_employed = emp.get("months_employed", 0)

        # Annualize based on pay frequency
        if pay_frequency == "weekly":
            base_monthly = base_monthly * 52 / 12
        elif pay_frequency == "biweekly":
            base_monthly = base_monthly * 26 / 12
        elif pay_frequency == "semimonthly":
            base_monthly = base_monthly * 24 / 12

        # Round to 2 decimal places
        base_monthly = base_monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        issues = []
        warnings = []
        doc_status = "complete"
        status = IncomeStatus.CALCULATED

        # Check employment duration
        total_months = years_employed * 12 + months_employed
        if total_months < 24:
            warnings.append(
                f"Less than 2 years at current employer ({total_months} months). "
                "Verify 2-year employment history across all employers."
            )

        # Check for required docs
        if not emp.get("has_paystubs"):
            issues.append("Current pay stubs required (30 days)")
            doc_status = "partial"
            status = IncomeStatus.NEEDS_DOCUMENTATION

        # Per B3-3.1-01 (03/04/2026): Only most recent W-2 required for fixed base income.
        # 2-year W-2 requirement still applies to variable income (OT/bonus/commission).
        if not emp.get("has_w2s"):
            issues.append("Most recent W-2 required for base employment income")
            doc_status = "partial" if doc_status == "complete" else doc_status
            status = IncomeStatus.NEEDS_DOCUMENTATION

        return IncomeItem(
            income_type=IncomeType.BASE_EMPLOYMENT,
            source_name=employer_name,
            gross_monthly=base_monthly,
            qualifying_monthly=base_monthly,
            calculation_method="Base salary annualized from current pay stub",
            status=status,
            documentation_status=doc_status,
            issues=issues,
            warnings=warnings,
            guideline_reference="Fannie Mae B3-3.1-01 (03/04/2026)",
        )

    def _calculate_variable_income(self, var: Dict[str, Any]) -> IncomeItem:
        """
        Calculate variable income (overtime, bonus, commission).

        Per Fannie Mae B3-3.1-01 (03/04/2026):
        - Require 2-year W-2 history (UNCHANGED for variable income)
        - Average over 2 years (or 1 year if trending up)
        - If declining, use lower of 1-year average or 2-year average
        - Commission > 25% of income requires tax returns

        NOTE: The 03/04/2026 update reduced W-2 requirements for fixed base
        income only. Variable income (OT, bonus, commission) STILL requires
        2 years of W-2s.
        """
        income_type_str = var.get("type", "overtime").lower()
        income_type_map = {
            "overtime": IncomeType.OVERTIME,
            "bonus": IncomeType.BONUS,
            "commission": IncomeType.COMMISSION,
        }
        income_type = income_type_map.get(income_type_str, IncomeType.OVERTIME)

        source_name = var.get("employer_name", "Employer")
        year1 = Decimal(str(var.get("year1_amount", 0)))  # Prior year
        year2 = Decimal(str(var.get("year2_amount", 0)))  # 2 years ago
        ytd = Decimal(str(var.get("ytd_amount", 0)))
        ytd_months = var.get("ytd_months", 0)

        issues = []
        warnings = []
        doc_status = "complete"
        status = IncomeStatus.CALCULATED

        # Need 2-year history
        if year2 == 0:
            issues.append(f"2-year history required for {income_type_str} income")
            doc_status = "partial"
            status = IncomeStatus.NEEDS_DOCUMENTATION

        # Calculate averages
        year1_monthly = year1 / 12
        year2_monthly = year2 / 12

        # Determine trending
        trending = "stable"
        if year1 > 0 and year2 > 0:
            change_pct = ((year1 - year2) / year2) * 100
            if change_pct > 10:
                trending = "increasing"
            elif change_pct < -10:
                trending = "declining"

        # Calculate qualifying amount based on trending
        if trending == "declining":
            # Use lower of 1-year or 2-year average
            two_year_avg = (year1 + year2) / 24
            one_year_avg = year1 / 12
            qualifying_monthly = min(one_year_avg, two_year_avg)
            warnings.append(
                f"Declining {income_type_str} income trend detected. "
                f"Year 1: ${year1:,.0f}, Year 2: ${year2:,.0f}"
            )
            status = IncomeStatus.TRENDING_ANALYSIS_REQUIRED
        elif trending == "increasing" and ytd_months >= 6:
            # Can use YTD annualized if trending up with sufficient history
            ytd_annualized = (ytd / ytd_months) * 12 if ytd_months > 0 else 0
            two_year_avg = (year1 + year2) / 24
            qualifying_monthly = max(two_year_avg, ytd_annualized / 12)
        else:
            # Standard 2-year average
            qualifying_monthly = (year1 + year2) / 24

        qualifying_monthly = qualifying_monthly.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return IncomeItem(
            income_type=income_type,
            source_name=source_name,
            gross_monthly=year1_monthly,
            qualifying_monthly=qualifying_monthly,
            calculation_method=f"2-year average ({trending} trend)",
            status=status,
            documentation_status=doc_status,
            issues=issues,
            warnings=warnings,
            guideline_reference="Fannie Mae B3-3.1-01",
            year1_income=year1,
            year2_income=year2,
            ytd_income=ytd,
            ytd_months=ytd_months,
            trending=trending,
        )

    def _calculate_self_employment_income(self, se: Dict[str, Any]) -> IncomeItem:
        """
        Calculate self-employment income.

        Per Fannie Mae B3-3.2:
        - Require 2 years tax returns (personal and business if > 25% ownership)
        - For Sole Proprietor: Net Profit + Depreciation + Depletion + Amortization
        - For Partnership/S-Corp: (Net Profit + Depreciation - Mtg/Notes < 1yr) x Ownership%
        - Declining income must be addressed
        - Business must be verified as currently operating
        """
        business_name = se.get("business_name", "Self-Employment")
        business_type = se.get("business_type", "sole_proprietor")
        ownership_pct = Decimal(str(se.get("ownership_percent", 100))) / 100

        # Get tax return data
        year1_net = Decimal(str(se.get("year1_net_profit", 0)))
        year1_depreciation = Decimal(str(se.get("year1_depreciation", 0)))
        year1_depletion = Decimal(str(se.get("year1_depletion", 0)))
        year1_amortization = Decimal(str(se.get("year1_amortization", 0)))
        year1_meals = Decimal(str(se.get("year1_meals_entertainment", 0))) * Decimal("0.5")
        year1_home_office = Decimal(str(se.get("year1_home_office", 0)))

        year2_net = Decimal(str(se.get("year2_net_profit", 0)))
        year2_depreciation = Decimal(str(se.get("year2_depreciation", 0)))
        year2_depletion = Decimal(str(se.get("year2_depletion", 0)))
        year2_amortization = Decimal(str(se.get("year2_amortization", 0)))
        year2_meals = Decimal(str(se.get("year2_meals_entertainment", 0))) * Decimal("0.5")
        year2_home_office = Decimal(str(se.get("year2_home_office", 0)))

        # For S-Corp/Partnership, subtract notes/mortgages payable < 1 year
        year1_notes_payable = Decimal(str(se.get("year1_notes_payable_1yr", 0)))
        year2_notes_payable = Decimal(str(se.get("year2_notes_payable_1yr", 0)))

        issues = []
        warnings = []
        doc_status = "complete"
        status = IncomeStatus.CALCULATED

        # Calculate adjusted net income per Fannie Mae addbacks
        if business_type == "sole_proprietor":
            # Schedule C calculation
            year1_adjusted = (year1_net + year1_depreciation + year1_depletion +
                             year1_amortization + year1_home_office)
            year2_adjusted = (year2_net + year2_depreciation + year2_depletion +
                             year2_amortization + year2_home_office)
        else:
            # Partnership/S-Corp calculation
            year1_adjusted = ((year1_net + year1_depreciation + year1_depletion +
                              year1_amortization - year1_notes_payable) * ownership_pct)
            year2_adjusted = ((year2_net + year2_depreciation + year2_depletion +
                              year2_amortization - year2_notes_payable) * ownership_pct)

        # Check for business losses
        if year1_adjusted < 0 or year2_adjusted < 0:
            issues.append("Business shows loss in one or more years")
            if year1_adjusted < 0 and year2_adjusted < 0:
                return IncomeItem(
                    income_type=IncomeType.SELF_EMPLOYMENT,
                    source_name=business_name,
                    gross_monthly=Decimal("0"),
                    qualifying_monthly=Decimal("0"),
                    calculation_method="Business losses - income excluded",
                    status=IncomeStatus.EXCLUDED,
                    documentation_status="complete",
                    issues=["Consecutive business losses - cannot use income"],
                    warnings=[],
                    guideline_reference="Fannie Mae B3-3.2-01",
                    year1_income=year1_adjusted,
                    year2_income=year2_adjusted,
                )

        # Determine trending
        trending = "stable"
        if year1_adjusted > 0 and year2_adjusted > 0:
            change_pct = ((year1_adjusted - year2_adjusted) / year2_adjusted) * 100
            if change_pct > 20:
                trending = "increasing"
            elif change_pct < -20:
                trending = "declining"

        # Calculate qualifying income
        if trending == "declining":
            # Use more recent year only
            qualifying_annual = year1_adjusted
            warnings.append(
                f"Declining self-employment income. "
                f"Year 1: ${year1_adjusted:,.0f}, Year 2: ${year2_adjusted:,.0f}. "
                f"Using Year 1 only."
            )
            status = IncomeStatus.TRENDING_ANALYSIS_REQUIRED
        else:
            # Average the two years
            qualifying_annual = (year1_adjusted + year2_adjusted) / 2

        qualifying_monthly = (qualifying_annual / 12).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Check documentation
        if not se.get("has_tax_returns_2yr"):
            issues.append("2 years personal tax returns required")
            doc_status = "partial"
            status = IncomeStatus.NEEDS_DOCUMENTATION

        if ownership_pct >= Decimal("0.25") and not se.get("has_business_returns"):
            issues.append("Business tax returns required (25%+ ownership)")
            doc_status = "partial"
            status = IncomeStatus.NEEDS_DOCUMENTATION

        if not se.get("has_ytd_pl"):
            warnings.append("YTD Profit & Loss recommended for current income verification")

        if not se.get("business_verified"):
            issues.append("Business existence must be verified (license, state filing, or CPA letter)")
            doc_status = "partial" if doc_status == "complete" else doc_status

        # Calculate months in business
        months_in_business = se.get("months_in_business", 0)
        if months_in_business < 24:
            issues.append(
                f"Self-employment history is {months_in_business} months. "
                f"2 years (24 months) required per Fannie Mae B3-3.2-01."
            )
            status = IncomeStatus.NEEDS_DOCUMENTATION

        return IncomeItem(
            income_type=IncomeType.SELF_EMPLOYMENT,
            source_name=business_name,
            gross_monthly=year1_adjusted / 12,
            qualifying_monthly=qualifying_monthly,
            calculation_method=f"{business_type} - 2yr average w/ addbacks ({trending})",
            status=status,
            documentation_status=doc_status,
            issues=issues,
            warnings=warnings,
            guideline_reference="Fannie Mae B3-3.2-01",
            year1_income=year1_adjusted,
            year2_income=year2_adjusted,
            trending=trending,
            notes=f"Ownership: {float(ownership_pct)*100:.0f}%",
        )

    def _calculate_rental_income(self, rental: Dict[str, Any]) -> IncomeItem:
        """
        Calculate rental income from investment property.

        Per Fannie Mae B3-3.1-09:
        - Use Schedule E from tax returns (2 years)
        - Gross rents less expenses = net rental income
        - For new rental: Use 75% of market rent from appraisal
        - Add back depreciation to net income
        - If negative cash flow, count as liability
        """
        property_address = rental.get("property_address", "Rental Property")

        # From Schedule E
        year1_gross_rent = Decimal(str(rental.get("year1_gross_rent", 0)))
        year1_expenses = Decimal(str(rental.get("year1_expenses", 0)))
        year1_depreciation = Decimal(str(rental.get("year1_depreciation", 0)))

        year2_gross_rent = Decimal(str(rental.get("year2_gross_rent", 0)))
        year2_expenses = Decimal(str(rental.get("year2_expenses", 0)))
        year2_depreciation = Decimal(str(rental.get("year2_depreciation", 0)))

        # Current PITIA (Principal, Interest, Taxes, Insurance, HOA)
        monthly_pitia = Decimal(str(rental.get("monthly_pitia", 0)))

        # For new rental (no tax history)
        is_new_rental = rental.get("is_new_rental", False)
        market_rent = Decimal(str(rental.get("market_rent", 0)))  # From appraisal

        issues = []
        warnings = []
        doc_status = "complete"
        status = IncomeStatus.CALCULATED

        if is_new_rental:
            # Use 75% of market rent per Fannie Mae
            gross_monthly = market_rent * Decimal("0.75")
            net_monthly = gross_monthly - monthly_pitia

            if not rental.get("has_lease"):
                issues.append("Executed lease agreement required")
                doc_status = "partial"
                status = IncomeStatus.NEEDS_DOCUMENTATION

            if not rental.get("has_appraisal_rent"):
                issues.append("Appraisal with rental survey required")
                doc_status = "partial"
                status = IncomeStatus.NEEDS_DOCUMENTATION

            calculation_method = "New rental: 75% of market rent"
        else:
            # Calculate from Schedule E with depreciation addback
            year1_net = year1_gross_rent - year1_expenses + year1_depreciation
            year2_net = year2_gross_rent - year2_expenses + year2_depreciation

            # Average the two years
            avg_annual = (year1_net + year2_net) / 2
            net_monthly = (avg_annual / 12).quantize(Decimal("0.01"))
            gross_monthly = ((year1_gross_rent + year2_gross_rent) / 2) / 12

            if not rental.get("has_schedule_e"):
                issues.append("Schedule E from 2 years tax returns required")
                doc_status = "partial"
                status = IncomeStatus.NEEDS_DOCUMENTATION

            calculation_method = "Schedule E 2-year average with depreciation addback"

        # Negative cash flow is counted as liability, not income
        if net_monthly < 0:
            warnings.append(
                f"Negative rental cash flow of ${abs(net_monthly):,.2f}/month "
                f"will be added to liabilities"
            )
            qualifying_monthly = Decimal("0")
            notes = f"Negative cash flow: ${net_monthly:,.2f} added to debts"
        else:
            qualifying_monthly = net_monthly
            notes = ""

        return IncomeItem(
            income_type=IncomeType.RENTAL,
            source_name=property_address,
            gross_monthly=gross_monthly,
            qualifying_monthly=qualifying_monthly,
            calculation_method=calculation_method,
            status=status,
            documentation_status=doc_status,
            issues=issues,
            warnings=warnings,
            guideline_reference="Fannie Mae B3-3.1-09",
            notes=notes,
        )

    def _calculate_retirement_income(self, ret: Dict[str, Any]) -> IncomeItem:
        """
        Calculate retirement/pension/Social Security income.

        Per Fannie Mae B3-3.1-09:
        - Social Security: Use award letter + bank deposits
        - Pension: Use award letter or 1099-R + bank deposits
        - Retirement distributions: Must be likely to continue 3+ years
        - Non-taxable income can be grossed up
        """
        income_type_str = ret.get("type", "pension").lower()
        income_type_map = {
            "social_security": IncomeType.SOCIAL_SECURITY,
            "pension": IncomeType.PENSION,
            "disability": IncomeType.DISABILITY,
        }
        income_type = income_type_map.get(income_type_str, IncomeType.PENSION)

        source_name = ret.get("source", "Retirement Income")
        monthly_amount = Decimal(str(ret.get("monthly_amount", 0)))
        is_taxable = ret.get("is_taxable", True)

        issues = []
        warnings = []
        doc_status = "complete"
        status = IncomeStatus.CALCULATED

        # Apply gross-up for non-taxable income
        if not is_taxable:
            qualifying_monthly = monthly_amount * self.gross_up_factor
            calculation_method = f"Non-taxable, grossed up {float(self.gross_up_factor)*100:.0f}%"
        else:
            qualifying_monthly = monthly_amount
            calculation_method = "Taxable amount per award letter"

        # Check documentation
        if not ret.get("has_award_letter"):
            if income_type in [IncomeType.SOCIAL_SECURITY, IncomeType.DISABILITY]:
                issues.append("Social Security/Disability award letter required")
            else:
                issues.append("Pension award letter or 1099-R required")
            doc_status = "partial"
            status = IncomeStatus.NEEDS_DOCUMENTATION

        if not ret.get("has_bank_deposits"):
            warnings.append("Bank statements showing deposits recommended")

        # Check if income will continue
        if ret.get("has_expiration"):
            issues.append("Income with expiration date - must continue 3+ years")
            status = IncomeStatus.TRENDING_ANALYSIS_REQUIRED

        return IncomeItem(
            income_type=income_type,
            source_name=source_name,
            gross_monthly=monthly_amount,
            qualifying_monthly=qualifying_monthly.quantize(Decimal("0.01")),
            calculation_method=calculation_method,
            status=status,
            documentation_status=doc_status,
            issues=issues,
            warnings=warnings,
            guideline_reference="Fannie Mae B3-3.1-09",
        )

    def _calculate_other_income(self, other: Dict[str, Any]) -> IncomeItem:
        """
        Calculate other income types (alimony, child support, etc.).

        Per Fannie Mae B3-3.1-09:
        - Must document 6 months receipt history
        - Must continue for 3+ years
        - Must provide divorce decree/court order
        """
        income_type_str = other.get("type", "other").lower()
        income_type_map = {
            "alimony": IncomeType.ALIMONY,
            "child_support": IncomeType.CHILD_SUPPORT,
            "interest": IncomeType.INTEREST_DIVIDENDS,
            "dividends": IncomeType.INTEREST_DIVIDENDS,
            "notes_receivable": IncomeType.NOTES_RECEIVABLE,
        }
        income_type = income_type_map.get(income_type_str, IncomeType.OTHER)

        source_name = other.get("source", "Other Income")
        monthly_amount = Decimal(str(other.get("monthly_amount", 0)))

        issues = []
        warnings = []
        doc_status = "complete"
        status = IncomeStatus.CALCULATED

        if income_type in [IncomeType.ALIMONY, IncomeType.CHILD_SUPPORT]:
            # Check continuation
            years_remaining = other.get("years_remaining", 0)
            if years_remaining < 3:
                issues.append(
                    f"Income must continue for 3+ years. "
                    f"Only {years_remaining} years remaining - cannot use."
                )
                return IncomeItem(
                    income_type=income_type,
                    source_name=source_name,
                    gross_monthly=monthly_amount,
                    qualifying_monthly=Decimal("0"),
                    calculation_method="Excluded - less than 3 years remaining",
                    status=IncomeStatus.EXCLUDED,
                    documentation_status=doc_status,
                    issues=issues,
                    warnings=[],
                    guideline_reference="Fannie Mae B3-3.1-09",
                )

            # Check documentation
            if not other.get("has_court_order"):
                issues.append("Divorce decree or court order required")
                doc_status = "partial"
                status = IncomeStatus.NEEDS_DOCUMENTATION

            if not other.get("has_receipt_history"):
                issues.append("6 months receipt history required (bank statements)")
                doc_status = "partial"
                status = IncomeStatus.NEEDS_DOCUMENTATION

        return IncomeItem(
            income_type=income_type,
            source_name=source_name,
            gross_monthly=monthly_amount,
            qualifying_monthly=monthly_amount,
            calculation_method="Per documentation provided",
            status=status,
            documentation_status=doc_status,
            issues=issues,
            warnings=warnings,
            guideline_reference="Fannie Mae B3-3.1-09",
        )

    def _ensure_list(self, item: Any) -> List:
        """Ensure item is a list."""
        if isinstance(item, list):
            return item
        return [item] if item else []

    def calculate_from_paystub(
        self,
        gross_ytd: Decimal,
        pay_date: date,
        pay_frequency: str = "biweekly",
    ) -> Decimal:
        """
        Calculate monthly income from paystub YTD earnings.

        Args:
            gross_ytd: Year-to-date gross earnings
            pay_date: Date of the pay stub
            pay_frequency: weekly, biweekly, semimonthly, monthly

        Returns:
            Calculated monthly income
        """
        # Calculate months elapsed in year
        year_start = date(pay_date.year, 1, 1)
        days_elapsed = (pay_date - year_start).days
        months_elapsed = Decimal(str(days_elapsed)) / Decimal("30.4375")

        if months_elapsed < 1:
            months_elapsed = Decimal("1")

        # Annualize and divide by 12
        annual = gross_ytd / months_elapsed * 12
        monthly = (annual / 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return monthly
