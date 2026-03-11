"""
Test W2/Paystub Cross-Validator - Comprehensive unit tests for income document
cross-validation between W-2 forms and pay stubs.

The W2PaystubCrossValidator validates consistency between a borrower's W-2
and their most recent pay stub(s). This is a critical underwriting step
because discrepancies indicate data entry errors, employer changes, or
potential fraud.

Covers:
1.  Matching employer name between paystub and W2
2.  Fuzzy employer name matching (Inc vs Incorporated, LLC variations)
3.  YTD gross income proportional check (paystub YTD vs W2 Box 1 prorated)
4.  Federal withholding consistency (paystub vs W2 Box 2)
5.  Social Security wages match (paystub vs W2 Box 3)
6.  Medicare wages match (paystub vs W2 Box 5)
7.  Employee name consistency across documents
8.  Employer EIN match
9.  Pay rate verification (hourly * hours = gross)
10. OT rate verification (1.5x regular rate)
11. 401k contribution consistency
12. Year-to-date accumulation logic check
13. Round number fraud detection
14. Missing standard deductions flag (no FICA = red flag)
15. Pay frequency consistency
16. Hire date vs pay period validation
17. Overall confidence score calculation
18. Multiple W2s for same employer handling
19. Mid-year employer change detection
20. State withholding consistency
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional


# =============================================================================
# DATA CLASSES (mirror what the validator should produce)
# =============================================================================

class ValidationFinding:
    """A single finding from cross-validation."""

    def __init__(
        self,
        check_type: str,
        severity: str,
        description: str,
        expected: Any = None,
        actual: Any = None,
        tolerance_pct: float = 0.0,
        variance_pct: float = 0.0,
    ):
        self.check_type = check_type
        self.severity = severity  # CRITICAL, HIGH, MEDIUM, LOW, INFO
        self.description = description
        self.expected = expected
        self.actual = actual
        self.tolerance_pct = tolerance_pct
        self.variance_pct = variance_pct

    def __repr__(self):
        return f"Finding({self.check_type}, {self.severity})"


class CrossValidationReport:
    """Full cross-validation report for a W2/paystub pair."""

    def __init__(
        self,
        findings: List[ValidationFinding],
        confidence_score: int,
        is_consistent: bool,
        employer_match: bool,
        employee_match: bool,
        income_consistent: bool,
        withholding_consistent: bool,
    ):
        self.findings = findings
        self.confidence_score = confidence_score  # 0-100
        self.is_consistent = is_consistent
        self.employer_match = employer_match
        self.employee_match = employee_match
        self.income_consistent = income_consistent
        self.withholding_consistent = withholding_consistent

    @property
    def critical_findings(self) -> List[ValidationFinding]:
        return [f for f in self.findings if f.severity == "CRITICAL"]

    @property
    def high_findings(self) -> List[ValidationFinding]:
        return [f for f in self.findings if f.severity == "HIGH"]


# =============================================================================
# W2/PAYSTUB CROSS VALIDATOR (self-contained test-driven implementation)
# =============================================================================

# Employer name suffixes to normalize for fuzzy matching
EMPLOYER_SUFFIXES = {
    "inc", "inc.", "incorporated",
    "llc", "l.l.c.", "l.l.c",
    "ltd", "ltd.", "limited",
    "corp", "corp.", "corporation",
    "co", "co.", "company",
    "lp", "l.p.", "limited partnership",
    "llp", "l.l.p.", "limited liability partnership",
    "pllc", "p.l.l.c.", "professional limited liability company",
    "pc", "p.c.", "professional corporation",
    "pa", "p.a.", "professional association",
    "na", "n.a.", "national association",
    "plc", "p.l.c.", "public limited company",
    "dba", "d.b.a.", "doing business as",
    "the",
}

# Pay frequency constants
PAY_FREQUENCY_PERIODS_PER_YEAR = {
    "WEEKLY": 52,
    "BIWEEKLY": 26,
    "SEMIMONTHLY": 24,
    "MONTHLY": 12,
}

# Standard FICA rates for 2025/2026
SOCIAL_SECURITY_RATE = Decimal("0.062")
MEDICARE_RATE = Decimal("0.0145")
SOCIAL_SECURITY_WAGE_BASE_2025 = Decimal("176100")

# Tolerance thresholds
INCOME_TOLERANCE_PCT = Decimal("5")       # 5% variance allowed
WITHHOLDING_TOLERANCE_PCT = Decimal("10")  # 10% variance allowed
ROUND_NUMBER_THRESHOLD = 1000              # Flag amounts that are exact multiples of $1000


def _normalize_employer_name(name: Optional[str]) -> str:
    """Normalize employer name for comparison."""
    if not name:
        return ""
    normalized = name.strip().lower()
    # Remove punctuation except hyphens
    normalized = "".join(c for c in normalized if c.isalnum() or c in (" ", "-"))
    # Remove common suffixes
    words = normalized.split()
    cleaned = [w for w in words if w not in EMPLOYER_SUFFIXES]
    return " ".join(cleaned).strip()


def _normalize_employee_name(name: Optional[str]) -> str:
    """Normalize employee name for comparison."""
    if not name:
        return ""
    normalized = name.strip().lower()
    # Remove suffixes like Jr, Sr, III, IV, etc.
    suffixes = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v", "esq", "esq.", "md", "m.d."}
    words = normalized.split()
    cleaned = [w for w in words if w not in suffixes]
    # Remove punctuation
    cleaned = ["".join(c for c in w if c.isalpha() or c == "-") for w in cleaned]
    return " ".join(cleaned).strip()


def _is_round_number(amount: float, threshold: int = ROUND_NUMBER_THRESHOLD) -> bool:
    """Check if amount is suspiciously round (exact multiple of threshold)."""
    if amount <= 0:
        return False
    return amount % threshold == 0


def _pct_variance(expected: float, actual: float) -> float:
    """Calculate percentage variance between expected and actual."""
    if expected == 0:
        return 100.0 if actual != 0 else 0.0
    return abs((actual - expected) / expected) * 100


def cross_validate_w2_paystub(
    w2_data: Dict[str, Any],
    paystub_data: Dict[str, Any],
    pay_date: Optional[date] = None,
    tax_year: Optional[int] = None,
) -> CrossValidationReport:
    """
    Cross-validate a W2 against a paystub for the same borrower/employer.

    Args:
        w2_data: Extracted W2 fields (Box 1 through Box 20)
        paystub_data: Extracted paystub fields
        pay_date: Pay date on the paystub (for proration calculations)
        tax_year: Tax year of the W2

    Returns:
        CrossValidationReport with findings and confidence score
    """
    findings = []
    if pay_date is None:
        pay_date_str = paystub_data.get("pay_date")
        if pay_date_str:
            pay_date = datetime.strptime(pay_date_str, "%Y-%m-%d").date() if isinstance(pay_date_str, str) else pay_date_str
        else:
            pay_date = date.today()

    if tax_year is None:
        tax_year = w2_data.get("tax_year", pay_date.year - 1)

    # --- 1. Employer name match ---
    w2_employer = w2_data.get("employer_name", "")
    ps_employer = paystub_data.get("employer_name", "")
    employer_match = _normalize_employer_name(w2_employer) == _normalize_employer_name(ps_employer)
    if not employer_match:
        findings.append(ValidationFinding(
            check_type="EMPLOYER_NAME_MISMATCH",
            severity="HIGH",
            description=f"Employer name mismatch: W2='{w2_employer}', Paystub='{ps_employer}'",
            expected=w2_employer,
            actual=ps_employer,
        ))

    # --- 2. Employee name match ---
    w2_employee = w2_data.get("employee_name", "")
    ps_employee = paystub_data.get("employee_name", "")
    employee_match = _normalize_employee_name(w2_employee) == _normalize_employee_name(ps_employee)
    if not employee_match:
        findings.append(ValidationFinding(
            check_type="EMPLOYEE_NAME_MISMATCH",
            severity="HIGH",
            description=f"Employee name mismatch: W2='{w2_employee}', Paystub='{ps_employee}'",
            expected=w2_employee,
            actual=ps_employee,
        ))

    # --- 3. Employer EIN match ---
    w2_ein = w2_data.get("employer_ein", "")
    ps_ein = paystub_data.get("employer_ein", "")
    ein_match = True
    if w2_ein and ps_ein:
        # Normalize EIN (remove dashes)
        w2_ein_clean = w2_ein.replace("-", "").strip()
        ps_ein_clean = ps_ein.replace("-", "").strip()
        ein_match = w2_ein_clean == ps_ein_clean
        if not ein_match:
            findings.append(ValidationFinding(
                check_type="EIN_MISMATCH",
                severity="CRITICAL",
                description=f"Employer EIN mismatch: W2='{w2_ein}', Paystub='{ps_ein}'",
                expected=w2_ein,
                actual=ps_ein,
            ))

    # --- 4. YTD gross income proportional check ---
    w2_box1 = float(w2_data.get("wages_tips_compensation", 0) or 0)  # Box 1
    ps_ytd_gross = float(paystub_data.get("ytd_gross", 0) or 0)
    income_consistent = True

    if w2_box1 > 0 and ps_ytd_gross > 0:
        # If paystub is from the same year as the W2, YTD should not exceed W2 Box 1
        # If paystub is from the following year, prorate the W2 to compare
        if pay_date.year == tax_year:
            # Same year: paystub YTD should roughly equal W2 Box 1 prorated
            # to the pay date
            day_of_year = (pay_date - date(pay_date.year, 1, 1)).days + 1
            proration_factor = day_of_year / 365.0
            expected_ytd = w2_box1 * proration_factor
            variance = _pct_variance(expected_ytd, ps_ytd_gross)
            if variance > float(INCOME_TOLERANCE_PCT):
                income_consistent = False
                severity = "HIGH" if variance > 20 else "MEDIUM"
                findings.append(ValidationFinding(
                    check_type="YTD_INCOME_VARIANCE",
                    severity=severity,
                    description=f"YTD gross ${ps_ytd_gross:,.2f} vs prorated W2 ${expected_ytd:,.2f} ({variance:.1f}% variance)",
                    expected=expected_ytd,
                    actual=ps_ytd_gross,
                    tolerance_pct=float(INCOME_TOLERANCE_PCT),
                    variance_pct=variance,
                ))
        else:
            # Different year: paystub is from year after W2
            # Prorate current YTD to full year and compare against prior W2
            day_of_year = (pay_date - date(pay_date.year, 1, 1)).days + 1
            if day_of_year > 0:
                annualized_current = ps_ytd_gross * (365.0 / day_of_year)
                variance = _pct_variance(w2_box1, annualized_current)
                if variance > float(INCOME_TOLERANCE_PCT):
                    severity = "MEDIUM"  # Different year, so lower severity
                    findings.append(ValidationFinding(
                        check_type="ANNUALIZED_INCOME_VARIANCE",
                        severity=severity,
                        description=f"Annualized current ${annualized_current:,.2f} vs prior W2 ${w2_box1:,.2f} ({variance:.1f}%)",
                        expected=w2_box1,
                        actual=annualized_current,
                        tolerance_pct=float(INCOME_TOLERANCE_PCT),
                        variance_pct=variance,
                    ))

    # --- 5. Federal withholding consistency ---
    w2_box2 = float(w2_data.get("federal_tax_withheld", 0) or 0)  # Box 2
    ps_ytd_fed_tax = float(paystub_data.get("ytd_federal_tax", 0) or 0)
    withholding_consistent = True

    if w2_box2 > 0 and ps_ytd_fed_tax > 0 and pay_date.year == tax_year:
        day_of_year = (pay_date - date(pay_date.year, 1, 1)).days + 1
        proration_factor = day_of_year / 365.0
        expected_fed = w2_box2 * proration_factor
        variance = _pct_variance(expected_fed, ps_ytd_fed_tax)
        if variance > float(WITHHOLDING_TOLERANCE_PCT):
            withholding_consistent = False
            findings.append(ValidationFinding(
                check_type="FEDERAL_WITHHOLDING_VARIANCE",
                severity="MEDIUM",
                description=f"Federal tax YTD ${ps_ytd_fed_tax:,.2f} vs prorated W2 ${expected_fed:,.2f} ({variance:.1f}%)",
                expected=expected_fed,
                actual=ps_ytd_fed_tax,
                tolerance_pct=float(WITHHOLDING_TOLERANCE_PCT),
                variance_pct=variance,
            ))

    # --- 6. Social Security wages (Box 3) ---
    w2_box3 = float(w2_data.get("social_security_wages", 0) or 0)
    ps_ytd_ss_wages = float(paystub_data.get("ytd_social_security_wages", 0) or 0)

    if w2_box3 > 0 and ps_ytd_ss_wages > 0 and pay_date.year == tax_year:
        day_of_year = (pay_date - date(pay_date.year, 1, 1)).days + 1
        proration_factor = day_of_year / 365.0
        expected_ss = w2_box3 * proration_factor
        variance = _pct_variance(expected_ss, ps_ytd_ss_wages)
        if variance > float(WITHHOLDING_TOLERANCE_PCT):
            findings.append(ValidationFinding(
                check_type="SS_WAGES_VARIANCE",
                severity="MEDIUM",
                description=f"SS wages YTD ${ps_ytd_ss_wages:,.2f} vs prorated W2 Box 3 ${expected_ss:,.2f} ({variance:.1f}%)",
                expected=expected_ss,
                actual=ps_ytd_ss_wages,
                tolerance_pct=float(WITHHOLDING_TOLERANCE_PCT),
                variance_pct=variance,
            ))

    # --- 7. Medicare wages (Box 5) ---
    w2_box5 = float(w2_data.get("medicare_wages", 0) or 0)
    ps_ytd_medicare_wages = float(paystub_data.get("ytd_medicare_wages", 0) or 0)

    if w2_box5 > 0 and ps_ytd_medicare_wages > 0 and pay_date.year == tax_year:
        day_of_year = (pay_date - date(pay_date.year, 1, 1)).days + 1
        proration_factor = day_of_year / 365.0
        expected_med = w2_box5 * proration_factor
        variance = _pct_variance(expected_med, ps_ytd_medicare_wages)
        if variance > float(WITHHOLDING_TOLERANCE_PCT):
            findings.append(ValidationFinding(
                check_type="MEDICARE_WAGES_VARIANCE",
                severity="MEDIUM",
                description=f"Medicare wages YTD ${ps_ytd_medicare_wages:,.2f} vs prorated W2 Box 5 ${expected_med:,.2f} ({variance:.1f}%)",
                expected=expected_med,
                actual=ps_ytd_medicare_wages,
                tolerance_pct=float(WITHHOLDING_TOLERANCE_PCT),
                variance_pct=variance,
            ))

    # --- 8. Pay rate verification ---
    hourly_rate = float(paystub_data.get("hourly_rate", 0) or 0)
    hours_worked = float(paystub_data.get("hours_worked", 0) or 0)
    current_gross = float(paystub_data.get("gross_pay", 0) or 0)

    if hourly_rate > 0 and hours_worked > 0 and current_gross > 0:
        # Determine regular hours based on pay frequency
        ot_hours = float(paystub_data.get("overtime_hours", 0) or 0)
        ot_rate = float(paystub_data.get("overtime_rate", 0) or 0)
        regular_hours = hours_worked - ot_hours  # Total hours minus OT hours

        expected_gross = hourly_rate * regular_hours
        if ot_hours > 0 and ot_rate > 0:
            expected_gross += ot_rate * ot_hours
        elif ot_hours > 0:
            expected_gross += hourly_rate * 1.5 * ot_hours

        # Add other earnings
        other_earnings = float(paystub_data.get("other_earnings", 0) or 0)
        expected_gross += other_earnings

        variance = _pct_variance(expected_gross, current_gross)
        if variance > 2.0:  # Tight tolerance for arithmetic
            findings.append(ValidationFinding(
                check_type="PAY_RATE_MISMATCH",
                severity="HIGH",
                description=f"Calculated gross ${expected_gross:,.2f} vs stated gross ${current_gross:,.2f}",
                expected=expected_gross,
                actual=current_gross,
                variance_pct=variance,
            ))

    # --- 9. OT rate verification ---
    if hourly_rate > 0:
        ot_rate = float(paystub_data.get("overtime_rate", 0) or 0)
        if ot_rate > 0:
            expected_ot_rate = hourly_rate * 1.5
            if abs(ot_rate - expected_ot_rate) > 0.01:
                findings.append(ValidationFinding(
                    check_type="OT_RATE_MISMATCH",
                    severity="MEDIUM",
                    description=f"OT rate ${ot_rate:.2f} is not 1.5x regular rate ${hourly_rate:.2f} (expected ${expected_ot_rate:.2f})",
                    expected=expected_ot_rate,
                    actual=ot_rate,
                ))

    # --- 10. 401k contribution consistency ---
    w2_box12_d = float(w2_data.get("box_12_d", 0) or 0)  # 401(k) elective deferrals
    ps_ytd_401k = float(paystub_data.get("ytd_401k", 0) or 0)

    if w2_box12_d > 0 and ps_ytd_401k > 0 and pay_date.year == tax_year:
        day_of_year = (pay_date - date(pay_date.year, 1, 1)).days + 1
        proration_factor = day_of_year / 365.0
        expected_401k = w2_box12_d * proration_factor
        variance = _pct_variance(expected_401k, ps_ytd_401k)
        if variance > float(WITHHOLDING_TOLERANCE_PCT):
            findings.append(ValidationFinding(
                check_type="401K_VARIANCE",
                severity="LOW",
                description=f"401(k) YTD ${ps_ytd_401k:,.2f} vs prorated W2 Box 12D ${expected_401k:,.2f} ({variance:.1f}%)",
                expected=expected_401k,
                actual=ps_ytd_401k,
                variance_pct=variance,
            ))

    # --- 11. YTD accumulation logic ---
    pay_frequency = paystub_data.get("pay_frequency", "")
    if pay_frequency and current_gross > 0 and ps_ytd_gross > 0:
        periods_per_year = PAY_FREQUENCY_PERIODS_PER_YEAR.get(pay_frequency, 0)
        if periods_per_year > 0:
            day_of_year = (pay_date - date(pay_date.year, 1, 1)).days + 1
            expected_periods = max(1, round(day_of_year / (365.0 / periods_per_year)))
            expected_ytd = current_gross * expected_periods
            variance = _pct_variance(expected_ytd, ps_ytd_gross)
            # Allow wide tolerance since bonuses/raises/OT vary per period
            if variance > 30:
                findings.append(ValidationFinding(
                    check_type="YTD_ACCUMULATION_ANOMALY",
                    severity="MEDIUM",
                    description=f"YTD ${ps_ytd_gross:,.2f} vs {expected_periods} periods * ${current_gross:,.2f} = ${expected_ytd:,.2f} ({variance:.1f}% variance)",
                    expected=expected_ytd,
                    actual=ps_ytd_gross,
                    variance_pct=variance,
                ))

    # --- 12. Round number fraud detection ---
    for field_name, amount in [
        ("W2 Box 1", w2_box1),
        ("YTD Gross", ps_ytd_gross),
        ("Current Gross", current_gross),
    ]:
        if _is_round_number(amount) and amount >= 10000:
            findings.append(ValidationFinding(
                check_type="ROUND_NUMBER_FLAG",
                severity="LOW",
                description=f"{field_name} is an exact round number: ${amount:,.2f}",
                actual=amount,
            ))

    # --- 13. Missing standard deductions (no FICA = red flag) ---
    ps_ytd_ss_tax = float(paystub_data.get("ytd_social_security_tax", 0) or 0)
    ps_ytd_medicare_tax = float(paystub_data.get("ytd_medicare_tax", 0) or 0)

    if ps_ytd_gross > 5000 and ps_ytd_ss_tax == 0 and ps_ytd_medicare_tax == 0:
        findings.append(ValidationFinding(
            check_type="MISSING_FICA_DEDUCTIONS",
            severity="CRITICAL",
            description=f"No FICA deductions on paystub with YTD gross ${ps_ytd_gross:,.2f} - potential fabricated document",
            actual=0,
            expected="Non-zero FICA",
        ))

    if ps_ytd_gross > 5000 and ps_ytd_fed_tax == 0 and float(paystub_data.get("federal_exemptions", 99) or 99) < 10:
        findings.append(ValidationFinding(
            check_type="MISSING_FEDERAL_TAX",
            severity="HIGH",
            description=f"No federal tax withheld with YTD gross ${ps_ytd_gross:,.2f}",
            actual=0,
        ))

    # --- 14. Pay frequency consistency ---
    w2_pay_frequency = w2_data.get("pay_frequency")
    if pay_frequency and w2_pay_frequency:
        if pay_frequency != w2_pay_frequency:
            findings.append(ValidationFinding(
                check_type="PAY_FREQUENCY_MISMATCH",
                severity="LOW",
                description=f"Pay frequency changed: W2='{w2_pay_frequency}', Paystub='{pay_frequency}'",
                expected=w2_pay_frequency,
                actual=pay_frequency,
            ))

    # --- 15. Hire date vs pay period ---
    hire_date_str = paystub_data.get("hire_date")
    pay_period_start_str = paystub_data.get("pay_period_start")

    if hire_date_str and pay_period_start_str:
        try:
            hire_date = datetime.strptime(hire_date_str, "%Y-%m-%d").date() if isinstance(hire_date_str, str) else hire_date_str
            pay_period_start = datetime.strptime(pay_period_start_str, "%Y-%m-%d").date() if isinstance(pay_period_start_str, str) else pay_period_start_str

            if pay_period_start < hire_date:
                findings.append(ValidationFinding(
                    check_type="PAY_PERIOD_BEFORE_HIRE",
                    severity="HIGH",
                    description=f"Pay period starts {pay_period_start} before hire date {hire_date}",
                    expected=f"After {hire_date}",
                    actual=str(pay_period_start),
                ))
        except (ValueError, TypeError):
            pass

    # --- 16. State withholding consistency ---
    w2_state_tax = float(w2_data.get("state_income_tax", 0) or 0)  # Box 17
    ps_ytd_state_tax = float(paystub_data.get("ytd_state_tax", 0) or 0)

    if w2_state_tax > 0 and ps_ytd_state_tax > 0 and pay_date.year == tax_year:
        day_of_year = (pay_date - date(pay_date.year, 1, 1)).days + 1
        proration_factor = day_of_year / 365.0
        expected_state = w2_state_tax * proration_factor
        variance = _pct_variance(expected_state, ps_ytd_state_tax)
        if variance > float(WITHHOLDING_TOLERANCE_PCT):
            findings.append(ValidationFinding(
                check_type="STATE_WITHHOLDING_VARIANCE",
                severity="MEDIUM",
                description=f"State tax YTD ${ps_ytd_state_tax:,.2f} vs prorated W2 ${expected_state:,.2f} ({variance:.1f}%)",
                expected=expected_state,
                actual=ps_ytd_state_tax,
                variance_pct=variance,
            ))

    # --- Calculate confidence score ---
    # Start at 100 and deduct based on findings
    confidence = 100
    for f in findings:
        if f.severity == "CRITICAL":
            confidence -= 25
        elif f.severity == "HIGH":
            confidence -= 15
        elif f.severity == "MEDIUM":
            confidence -= 8
        elif f.severity == "LOW":
            confidence -= 3
    confidence = max(0, min(100, confidence))

    is_consistent = confidence >= 70 and len([f for f in findings if f.severity in ("CRITICAL", "HIGH")]) == 0

    return CrossValidationReport(
        findings=findings,
        confidence_score=confidence,
        is_consistent=is_consistent,
        employer_match=employer_match,
        employee_match=employee_match,
        income_consistent=income_consistent,
        withholding_consistent=withholding_consistent,
    )


def validate_multiple_w2s(
    w2_list: List[Dict[str, Any]],
    paystub_data: Dict[str, Any],
    pay_date: Optional[date] = None,
) -> CrossValidationReport:
    """
    Handle multiple W2s for the same borrower (same employer or employer change).

    Returns aggregated findings and detects mid-year employer changes.
    """
    if not w2_list:
        return CrossValidationReport(
            findings=[ValidationFinding(
                check_type="NO_W2",
                severity="CRITICAL",
                description="No W2 provided for cross-validation",
            )],
            confidence_score=0,
            is_consistent=False,
            employer_match=False,
            employee_match=False,
            income_consistent=False,
            withholding_consistent=False,
        )

    ps_employer_norm = _normalize_employer_name(paystub_data.get("employer_name", ""))

    # Find the W2 that matches the paystub employer
    matching_w2 = None
    other_w2s = []
    for w2 in w2_list:
        w2_employer_norm = _normalize_employer_name(w2.get("employer_name", ""))
        if w2_employer_norm == ps_employer_norm:
            matching_w2 = w2
        else:
            other_w2s.append(w2)

    findings = []

    # Detect mid-year employer change
    if matching_w2 is None and other_w2s:
        findings.append(ValidationFinding(
            check_type="MID_YEAR_EMPLOYER_CHANGE",
            severity="MEDIUM",
            description=f"Paystub employer does not match any W2. Possible mid-year employer change.",
        ))
        # Use the most recent W2 for comparison
        matching_w2 = w2_list[-1]

    if len(w2_list) > 1:
        # Multiple W2s for same year might mean employer change or concurrent employment
        employers = set(_normalize_employer_name(w2.get("employer_name", "")) for w2 in w2_list)
        if len(employers) > 1:
            findings.append(ValidationFinding(
                check_type="MULTIPLE_EMPLOYERS_DETECTED",
                severity="INFO",
                description=f"{len(employers)} different employers on W2s for same tax year",
            ))

        # Check for duplicate W2s (same employer, same amounts)
        same_employer_w2s = [
            w2 for w2 in w2_list
            if _normalize_employer_name(w2.get("employer_name", "")) == ps_employer_norm
        ]
        if len(same_employer_w2s) > 1:
            findings.append(ValidationFinding(
                check_type="DUPLICATE_W2_SAME_EMPLOYER",
                severity="MEDIUM",
                description=f"Multiple W2s ({len(same_employer_w2s)}) from the same employer",
            ))

    # Run standard cross-validation against the matching W2
    if matching_w2:
        report = cross_validate_w2_paystub(matching_w2, paystub_data, pay_date)
        findings.extend(report.findings)
        return CrossValidationReport(
            findings=findings,
            confidence_score=report.confidence_score,
            is_consistent=report.is_consistent and len([f for f in findings if f.severity == "CRITICAL"]) == 0,
            employer_match=report.employer_match,
            employee_match=report.employee_match,
            income_consistent=report.income_consistent,
            withholding_consistent=report.withholding_consistent,
        )

    return CrossValidationReport(
        findings=findings,
        confidence_score=30,
        is_consistent=False,
        employer_match=False,
        employee_match=False,
        income_consistent=False,
        withholding_consistent=False,
    )


# =============================================================================
# FIXTURES
# =============================================================================

def _make_w2(**overrides) -> Dict[str, Any]:
    """Helper to create a W2 data dict with sensible defaults."""
    defaults = {
        "employer_name": "Acme Corporation",
        "employer_ein": "12-3456789",
        "employee_name": "John A Smith",
        "wages_tips_compensation": 120000.00,    # Box 1
        "federal_tax_withheld": 24000.00,        # Box 2
        "social_security_wages": 120000.00,      # Box 3
        "social_security_tax": 7440.00,          # Box 4
        "medicare_wages": 120000.00,             # Box 5
        "medicare_tax": 1740.00,                 # Box 6
        "state_income_tax": 6000.00,             # Box 17
        "box_12_d": 10000.00,                    # 401(k)
        "tax_year": 2025,
        "pay_frequency": None,
    }
    defaults.update(overrides)
    return defaults


def _make_paystub(**overrides) -> Dict[str, Any]:
    """Helper to create a paystub data dict with sensible defaults."""
    defaults = {
        "employer_name": "Acme Corporation",
        "employer_ein": "12-3456789",
        "employee_name": "John A Smith",
        "pay_date": "2025-07-01",
        "pay_period_start": "2025-06-16",
        "pay_period_end": "2025-06-30",
        "pay_frequency": "BIWEEKLY",
        "gross_pay": 4615.38,          # ~120k / 26
        "ytd_gross": 60000.00,         # About half year
        "hourly_rate": 0,
        "hours_worked": 0,
        "overtime_hours": 0,
        "overtime_rate": 0,
        "other_earnings": 0,
        "ytd_federal_tax": 12000.00,   # prorated federal
        "ytd_social_security_wages": 60000.00,
        "ytd_social_security_tax": 3720.00,
        "ytd_medicare_wages": 60000.00,
        "ytd_medicare_tax": 870.00,
        "ytd_state_tax": 3000.00,
        "ytd_401k": 5000.00,
        "hire_date": "2020-01-15",
        "federal_exemptions": 2,
    }
    defaults.update(overrides)
    return defaults


# =============================================================================
# TESTS
# =============================================================================

@pytest.mark.unit
class TestEmployerNameMatching:
    """Tests for employer name matching between W2 and paystub."""

    def test_exact_employer_match(self):
        """Identical employer names should produce no employer mismatch."""
        w2 = _make_w2(employer_name="Acme Corporation")
        ps = _make_paystub(employer_name="Acme Corporation")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employer_match is True
        assert not any(f.check_type == "EMPLOYER_NAME_MISMATCH" for f in report.findings)

    def test_employer_name_mismatch_flagged(self):
        """Completely different employer names should flag a HIGH severity finding."""
        w2 = _make_w2(employer_name="Acme Corporation")
        ps = _make_paystub(employer_name="Global Industries")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employer_match is False
        mismatches = [f for f in report.findings if f.check_type == "EMPLOYER_NAME_MISMATCH"]
        assert len(mismatches) == 1
        assert mismatches[0].severity == "HIGH"

    def test_fuzzy_inc_vs_incorporated(self):
        """'Inc' vs 'Incorporated' should be treated as a match."""
        w2 = _make_w2(employer_name="Acme Inc")
        ps = _make_paystub(employer_name="Acme Incorporated")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employer_match is True

    def test_fuzzy_llc_variations(self):
        """LLC vs L.L.C. should match."""
        w2 = _make_w2(employer_name="Smith Consulting LLC")
        ps = _make_paystub(employer_name="Smith Consulting L.L.C.")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employer_match is True

    def test_fuzzy_corp_vs_corporation(self):
        """Corp vs Corporation should match."""
        w2 = _make_w2(employer_name="Acme Corp")
        ps = _make_paystub(employer_name="Acme Corporation")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employer_match is True

    def test_fuzzy_ltd_vs_limited(self):
        """Ltd vs Limited should match."""
        w2 = _make_w2(employer_name="Acme Ltd.")
        ps = _make_paystub(employer_name="Acme Limited")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employer_match is True

    def test_case_insensitive_match(self):
        """Employer names should match case-insensitively."""
        w2 = _make_w2(employer_name="ACME CORPORATION")
        ps = _make_paystub(employer_name="acme corporation")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employer_match is True

    def test_the_prefix_stripped(self):
        """'The' prefix on employer name should be normalized out."""
        w2 = _make_w2(employer_name="The Boeing Company")
        ps = _make_paystub(employer_name="Boeing Company")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employer_match is True


@pytest.mark.unit
class TestYTDGrossIncome:
    """Tests for YTD gross income proportional check against W2 Box 1."""

    def test_consistent_ytd_midyear(self):
        """YTD at mid-year should be approximately half of W2 annual."""
        w2 = _make_w2(wages_tips_compensation=120000.00)
        ps = _make_paystub(ytd_gross=60000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.income_consistent is True
        assert not any(f.check_type == "YTD_INCOME_VARIANCE" for f in report.findings)

    def test_ytd_significantly_over_prorated(self):
        """YTD gross significantly exceeding prorated W2 should flag a finding."""
        w2 = _make_w2(wages_tips_compensation=120000.00)
        # 90k at mid-year when prorated should be ~60k -> 50% variance
        ps = _make_paystub(ytd_gross=90000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        variance_findings = [f for f in report.findings if f.check_type == "YTD_INCOME_VARIANCE"]
        assert len(variance_findings) == 1
        assert variance_findings[0].severity == "HIGH"

    def test_ytd_significantly_under_prorated(self):
        """YTD gross significantly below prorated W2 should flag."""
        w2 = _make_w2(wages_tips_compensation=120000.00)
        ps = _make_paystub(ytd_gross=30000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        variance_findings = [f for f in report.findings if f.check_type == "YTD_INCOME_VARIANCE"]
        assert len(variance_findings) >= 1

    def test_different_year_annualized_check(self):
        """Paystub from year after W2 should use annualized comparison."""
        w2 = _make_w2(wages_tips_compensation=120000.00, tax_year=2025)
        # March 2026 paystub, annualizes to ~120k -> consistent
        ps = _make_paystub(ytd_gross=30000.00, pay_date="2026-04-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        # Annualized = 30000 * (365/91) ~= 120329 -- within tolerance
        assert not any(f.check_type == "ANNUALIZED_INCOME_VARIANCE" for f in report.findings)


@pytest.mark.unit
class TestFederalWithholding:
    """Tests for federal withholding consistency (paystub vs W2 Box 2)."""

    def test_consistent_federal_withholding(self):
        """Prorated federal withholding within tolerance should pass."""
        w2 = _make_w2(federal_tax_withheld=24000.00)
        ps = _make_paystub(ytd_federal_tax=12000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.withholding_consistent is True
        assert not any(f.check_type == "FEDERAL_WITHHOLDING_VARIANCE" for f in report.findings)

    def test_major_federal_withholding_variance(self):
        """Large federal withholding variance should be flagged."""
        w2 = _make_w2(federal_tax_withheld=24000.00)
        # At mid-year, expected ~$12k, actual $3k = massive variance
        ps = _make_paystub(ytd_federal_tax=3000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.withholding_consistent is False
        findings = [f for f in report.findings if f.check_type == "FEDERAL_WITHHOLDING_VARIANCE"]
        assert len(findings) == 1


@pytest.mark.unit
class TestSocialSecurityWages:
    """Tests for Social Security wages match (paystub vs W2 Box 3)."""

    def test_consistent_ss_wages(self):
        """Prorated SS wages within tolerance should produce no finding."""
        w2 = _make_w2(social_security_wages=120000.00)
        ps = _make_paystub(ytd_social_security_wages=60000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert not any(f.check_type == "SS_WAGES_VARIANCE" for f in report.findings)

    def test_ss_wages_variance_flagged(self):
        """SS wages significantly different from prorated W2 Box 3 should be flagged."""
        w2 = _make_w2(social_security_wages=120000.00)
        ps = _make_paystub(ytd_social_security_wages=90000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        findings = [f for f in report.findings if f.check_type == "SS_WAGES_VARIANCE"]
        assert len(findings) == 1


@pytest.mark.unit
class TestMedicareWages:
    """Tests for Medicare wages match (paystub vs W2 Box 5)."""

    def test_consistent_medicare_wages(self):
        """Prorated Medicare wages within tolerance should pass."""
        w2 = _make_w2(medicare_wages=120000.00)
        ps = _make_paystub(ytd_medicare_wages=60000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert not any(f.check_type == "MEDICARE_WAGES_VARIANCE" for f in report.findings)

    def test_medicare_wages_variance_flagged(self):
        """Large Medicare wages variance should be flagged."""
        w2 = _make_w2(medicare_wages=120000.00)
        ps = _make_paystub(ytd_medicare_wages=40000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        findings = [f for f in report.findings if f.check_type == "MEDICARE_WAGES_VARIANCE"]
        assert len(findings) == 1


@pytest.mark.unit
class TestEmployeeNameConsistency:
    """Tests for employee name consistency across documents."""

    def test_exact_employee_name_match(self):
        """Identical employee names should not produce a finding."""
        w2 = _make_w2(employee_name="John A Smith")
        ps = _make_paystub(employee_name="John A Smith")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employee_match is True
        assert not any(f.check_type == "EMPLOYEE_NAME_MISMATCH" for f in report.findings)

    def test_name_with_suffix_stripped(self):
        """Name suffixes (Jr, Sr) should be ignored in comparison."""
        w2 = _make_w2(employee_name="John Smith Jr.")
        ps = _make_paystub(employee_name="John Smith")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employee_match is True

    def test_completely_different_names_flagged(self):
        """Different employee names should produce a HIGH finding."""
        w2 = _make_w2(employee_name="John Smith")
        ps = _make_paystub(employee_name="Jane Doe")
        report = cross_validate_w2_paystub(w2, ps)
        assert report.employee_match is False
        mismatches = [f for f in report.findings if f.check_type == "EMPLOYEE_NAME_MISMATCH"]
        assert len(mismatches) == 1
        assert mismatches[0].severity == "HIGH"


@pytest.mark.unit
class TestEmployerEIN:
    """Tests for Employer EIN match."""

    def test_matching_ein(self):
        """Matching EINs should produce no finding."""
        w2 = _make_w2(employer_ein="12-3456789")
        ps = _make_paystub(employer_ein="12-3456789")
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "EIN_MISMATCH" for f in report.findings)

    def test_ein_mismatch_critical(self):
        """Mismatched EINs should produce a CRITICAL finding."""
        w2 = _make_w2(employer_ein="12-3456789")
        ps = _make_paystub(employer_ein="98-7654321")
        report = cross_validate_w2_paystub(w2, ps)
        findings = [f for f in report.findings if f.check_type == "EIN_MISMATCH"]
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"

    def test_ein_dash_normalization(self):
        """EINs with and without dash should still match."""
        w2 = _make_w2(employer_ein="12-3456789")
        ps = _make_paystub(employer_ein="123456789")
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "EIN_MISMATCH" for f in report.findings)

    def test_ein_only_on_one_document(self):
        """If EIN is only on one document, no comparison is made (no finding)."""
        w2 = _make_w2(employer_ein="12-3456789")
        ps = _make_paystub(employer_ein="")
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "EIN_MISMATCH" for f in report.findings)


@pytest.mark.unit
class TestPayRateVerification:
    """Tests for pay rate verification (hourly * hours = gross)."""

    def test_correct_hourly_calculation(self):
        """Hourly rate * hours should equal gross pay."""
        ps = _make_paystub(
            hourly_rate=50.00,
            hours_worked=80,  # biweekly
            gross_pay=4000.00,
            pay_frequency="BIWEEKLY",
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "PAY_RATE_MISMATCH" for f in report.findings)

    def test_pay_rate_mismatch_detected(self):
        """Gross pay not matching hourly * hours should be flagged."""
        ps = _make_paystub(
            hourly_rate=25.00,
            hours_worked=80,
            gross_pay=5000.00,  # Should be $2000
            pay_frequency="BIWEEKLY",
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        findings = [f for f in report.findings if f.check_type == "PAY_RATE_MISMATCH"]
        assert len(findings) == 1
        assert findings[0].severity == "HIGH"


@pytest.mark.unit
class TestOvertimeRateVerification:
    """Tests for OT rate verification (should be 1.5x regular rate)."""

    def test_correct_ot_rate(self):
        """OT rate at 1.5x regular should not flag."""
        ps = _make_paystub(
            hourly_rate=30.00,
            overtime_rate=45.00,  # 1.5 * 30
            overtime_hours=10,
            hours_worked=90,
            gross_pay=2850.00,  # 80*30 + 10*45
            pay_frequency="BIWEEKLY",
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "OT_RATE_MISMATCH" for f in report.findings)

    def test_ot_rate_not_1_5x(self):
        """OT rate not equal to 1.5x regular should flag MEDIUM severity."""
        ps = _make_paystub(
            hourly_rate=30.00,
            overtime_rate=35.00,  # Not 1.5x
            overtime_hours=10,
            hours_worked=90,
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        findings = [f for f in report.findings if f.check_type == "OT_RATE_MISMATCH"]
        assert len(findings) == 1
        assert findings[0].severity == "MEDIUM"


@pytest.mark.unit
class Test401kContributionConsistency:
    """Tests for 401(k) contribution consistency."""

    def test_consistent_401k(self):
        """Prorated 401(k) within tolerance should pass."""
        w2 = _make_w2(box_12_d=10000.00)
        ps = _make_paystub(ytd_401k=5000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert not any(f.check_type == "401K_VARIANCE" for f in report.findings)

    def test_401k_large_variance_flagged(self):
        """401(k) variance beyond tolerance should flag."""
        w2 = _make_w2(box_12_d=20000.00)
        ps = _make_paystub(ytd_401k=2000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        findings = [f for f in report.findings if f.check_type == "401K_VARIANCE"]
        assert len(findings) == 1


@pytest.mark.unit
class TestYTDAccumulationLogic:
    """Tests for YTD accumulation logic check."""

    def test_reasonable_ytd_accumulation(self):
        """YTD consistent with per-period gross * number of periods should pass."""
        # Biweekly, 13 periods into the year, gross $4615 * 13 = ~$60k
        ps = _make_paystub(
            gross_pay=4615.38,
            ytd_gross=60000.00,
            pay_frequency="BIWEEKLY",
            pay_date="2025-07-01",
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "YTD_ACCUMULATION_ANOMALY" for f in report.findings)

    def test_ytd_far_exceeds_accumulation(self):
        """YTD vastly exceeding expected accumulation should flag."""
        # Biweekly, 13 periods, gross $2000, but YTD $120k (impossibly high)
        ps = _make_paystub(
            gross_pay=2000.00,
            ytd_gross=120000.00,
            pay_frequency="BIWEEKLY",
            pay_date="2025-07-01",
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        findings = [f for f in report.findings if f.check_type == "YTD_ACCUMULATION_ANOMALY"]
        assert len(findings) >= 1


@pytest.mark.unit
class TestRoundNumberFraudDetection:
    """Tests for round number fraud detection."""

    def test_round_w2_income_flagged(self):
        """Exactly round W2 Box 1 ($100,000) should produce a LOW finding."""
        w2 = _make_w2(wages_tips_compensation=100000.00)
        ps = _make_paystub(ytd_gross=50000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        findings = [f for f in report.findings if f.check_type == "ROUND_NUMBER_FLAG"]
        # Both W2 Box 1 ($100k) and YTD ($50k) are round
        round_amounts = [f.actual for f in findings]
        assert 100000.0 in round_amounts

    def test_non_round_amounts_not_flagged(self):
        """Non-round amounts like $87,432.56 should not trigger round number flag."""
        w2 = _make_w2(wages_tips_compensation=87432.56)
        ps = _make_paystub(ytd_gross=43716.28, gross_pay=3362.79, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        findings = [f for f in report.findings if f.check_type == "ROUND_NUMBER_FLAG"]
        assert len(findings) == 0

    def test_small_round_amounts_not_flagged(self):
        """Small round amounts (below $10,000) should not trigger."""
        w2 = _make_w2(wages_tips_compensation=5000.00)
        ps = _make_paystub(ytd_gross=2500.00, gross_pay=500.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        findings = [f for f in report.findings if f.check_type == "ROUND_NUMBER_FLAG"]
        assert len(findings) == 0


@pytest.mark.unit
class TestMissingFICADeductions:
    """Tests for missing standard deductions (no FICA = red flag)."""

    def test_missing_fica_flagged_critical(self):
        """Paystub with income but zero FICA should be CRITICAL."""
        ps = _make_paystub(
            ytd_gross=60000.00,
            ytd_social_security_tax=0,
            ytd_medicare_tax=0,
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        findings = [f for f in report.findings if f.check_type == "MISSING_FICA_DEDUCTIONS"]
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"

    def test_has_fica_not_flagged(self):
        """Paystub with normal FICA deductions should not flag."""
        ps = _make_paystub(
            ytd_gross=60000.00,
            ytd_social_security_tax=3720.00,
            ytd_medicare_tax=870.00,
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "MISSING_FICA_DEDUCTIONS" for f in report.findings)

    def test_low_income_no_fica_not_flagged(self):
        """Very low YTD gross ($3k) with no FICA should not flag (below threshold)."""
        ps = _make_paystub(
            ytd_gross=3000.00,
            ytd_social_security_tax=0,
            ytd_medicare_tax=0,
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "MISSING_FICA_DEDUCTIONS" for f in report.findings)


@pytest.mark.unit
class TestPayFrequencyConsistency:
    """Tests for pay frequency consistency between W2 and paystub."""

    def test_matching_pay_frequency(self):
        """Same pay frequency on both docs should not flag."""
        w2 = _make_w2(pay_frequency="BIWEEKLY")
        ps = _make_paystub(pay_frequency="BIWEEKLY")
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "PAY_FREQUENCY_MISMATCH" for f in report.findings)

    def test_changed_pay_frequency_flagged(self):
        """Different pay frequencies should produce a LOW finding."""
        w2 = _make_w2(pay_frequency="BIWEEKLY")
        ps = _make_paystub(pay_frequency="SEMIMONTHLY")
        report = cross_validate_w2_paystub(w2, ps)
        findings = [f for f in report.findings if f.check_type == "PAY_FREQUENCY_MISMATCH"]
        assert len(findings) == 1
        assert findings[0].severity == "LOW"

    def test_no_w2_pay_frequency_no_flag(self):
        """If W2 has no pay frequency info, skip this check."""
        w2 = _make_w2(pay_frequency=None)
        ps = _make_paystub(pay_frequency="BIWEEKLY")
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "PAY_FREQUENCY_MISMATCH" for f in report.findings)


@pytest.mark.unit
class TestHireDateValidation:
    """Tests for hire date vs pay period validation."""

    def test_pay_period_after_hire_date(self):
        """Pay period starting after hire date should be normal."""
        ps = _make_paystub(
            hire_date="2020-01-15",
            pay_period_start="2025-06-16",
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        assert not any(f.check_type == "PAY_PERIOD_BEFORE_HIRE" for f in report.findings)

    def test_pay_period_before_hire_date_flagged(self):
        """Pay period starting before hire date should flag HIGH."""
        ps = _make_paystub(
            hire_date="2025-07-01",
            pay_period_start="2025-06-16",
        )
        w2 = _make_w2()
        report = cross_validate_w2_paystub(w2, ps)
        findings = [f for f in report.findings if f.check_type == "PAY_PERIOD_BEFORE_HIRE"]
        assert len(findings) == 1
        assert findings[0].severity == "HIGH"


@pytest.mark.unit
class TestConfidenceScoreCalculation:
    """Tests for overall confidence score calculation."""

    def test_perfect_match_high_confidence(self):
        """Fully consistent documents should yield confidence >= 90."""
        w2 = _make_w2()
        ps = _make_paystub()
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.confidence_score >= 90
        assert report.is_consistent is True

    def test_critical_finding_drops_confidence(self):
        """A CRITICAL finding should reduce confidence by 25 points."""
        w2 = _make_w2(employer_ein="12-3456789")
        ps = _make_paystub(
            employer_ein="99-9999999",
            ytd_social_security_tax=3720.00,
            ytd_medicare_tax=870.00,
        )
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.confidence_score <= 75
        assert report.is_consistent is False

    def test_multiple_findings_cumulative(self):
        """Multiple findings should cumulatively reduce confidence."""
        w2 = _make_w2(employer_ein="12-3456789")
        ps = _make_paystub(
            employer_name="Totally Different Company",
            employer_ein="99-9999999",
            employee_name="Jane Doe",
            ytd_federal_tax=1000.00,    # way off
            ytd_social_security_tax=0,  # missing FICA
            ytd_medicare_tax=0,
        )
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        # Employer mismatch (HIGH -15), EIN mismatch (CRITICAL -25),
        # Employee mismatch (HIGH -15), Missing FICA (CRITICAL -25),
        # federal withholding (MEDIUM -8), etc.
        assert report.confidence_score <= 30
        assert report.is_consistent is False

    def test_confidence_never_negative(self):
        """Confidence should be clamped to 0 minimum."""
        w2 = _make_w2(employer_ein="12-3456789")
        ps = _make_paystub(
            employer_name="X",
            employer_ein="99-0000000",
            employee_name="Z",
            ytd_social_security_tax=0,
            ytd_medicare_tax=0,
            ytd_federal_tax=0,
            federal_exemptions=1,
        )
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.confidence_score >= 0


@pytest.mark.unit
class TestMultipleW2sHandling:
    """Tests for handling multiple W2s for the same employer."""

    def test_single_w2_standard_validation(self):
        """Single W2 in list should produce standard validation."""
        w2 = _make_w2()
        ps = _make_paystub()
        report = validate_multiple_w2s([w2], ps)
        assert report.employer_match is True
        assert report.is_consistent is True

    def test_multiple_w2s_same_employer_flagged(self):
        """Multiple W2s from same employer should flag DUPLICATE_W2_SAME_EMPLOYER."""
        w2a = _make_w2(employer_name="Acme Corporation", wages_tips_compensation=60000)
        w2b = _make_w2(employer_name="Acme Corporation", wages_tips_compensation=60000)
        ps = _make_paystub()
        report = validate_multiple_w2s([w2a, w2b], ps)
        findings = [f for f in report.findings if f.check_type == "DUPLICATE_W2_SAME_EMPLOYER"]
        assert len(findings) == 1

    def test_multiple_w2s_different_employers(self):
        """W2s from different employers should produce MULTIPLE_EMPLOYERS_DETECTED."""
        w2a = _make_w2(employer_name="Acme Corporation")
        w2b = _make_w2(employer_name="Global Industries")
        ps = _make_paystub(employer_name="Acme Corporation")
        report = validate_multiple_w2s([w2a, w2b], ps)
        findings = [f for f in report.findings if f.check_type == "MULTIPLE_EMPLOYERS_DETECTED"]
        assert len(findings) == 1

    def test_no_w2s_provided(self):
        """Empty W2 list should produce CRITICAL no-data finding."""
        ps = _make_paystub()
        report = validate_multiple_w2s([], ps)
        assert report.confidence_score == 0
        assert report.is_consistent is False
        assert any(f.check_type == "NO_W2" for f in report.findings)


@pytest.mark.unit
class TestMidYearEmployerChange:
    """Tests for mid-year employer change detection."""

    def test_employer_change_detected(self):
        """Paystub employer not matching any W2 should flag mid-year change."""
        w2 = _make_w2(employer_name="Old Company Inc")
        ps = _make_paystub(employer_name="New Company LLC")
        report = validate_multiple_w2s([w2], ps)
        findings = [f for f in report.findings if f.check_type == "MID_YEAR_EMPLOYER_CHANGE"]
        assert len(findings) == 1
        assert findings[0].severity == "MEDIUM"

    def test_no_employer_change_when_match_exists(self):
        """Paystub matching a W2 employer should not flag employer change."""
        w2a = _make_w2(employer_name="Old Company Inc")
        w2b = _make_w2(employer_name="Acme Corporation")
        ps = _make_paystub(employer_name="Acme Corporation")
        report = validate_multiple_w2s([w2a, w2b], ps)
        assert not any(f.check_type == "MID_YEAR_EMPLOYER_CHANGE" for f in report.findings)


@pytest.mark.unit
class TestStateWithholdingConsistency:
    """Tests for state withholding consistency."""

    def test_consistent_state_withholding(self):
        """Prorated state tax within tolerance should pass."""
        w2 = _make_w2(state_income_tax=6000.00)
        ps = _make_paystub(ytd_state_tax=3000.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert not any(f.check_type == "STATE_WITHHOLDING_VARIANCE" for f in report.findings)

    def test_state_withholding_variance_flagged(self):
        """Large state tax variance should be flagged."""
        w2 = _make_w2(state_income_tax=6000.00)
        ps = _make_paystub(ytd_state_tax=500.00, pay_date="2025-07-01")
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        findings = [f for f in report.findings if f.check_type == "STATE_WITHHOLDING_VARIANCE"]
        assert len(findings) == 1
        assert findings[0].severity == "MEDIUM"

    def test_no_state_tax_on_w2_no_flag(self):
        """If W2 has zero state tax, no comparison is made."""
        w2 = _make_w2(state_income_tax=0)
        ps = _make_paystub(ytd_state_tax=3000.00)
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert not any(f.check_type == "STATE_WITHHOLDING_VARIANCE" for f in report.findings)


# =============================================================================
# INTEGRATION-STYLE TESTS (end-to-end scenarios)
# =============================================================================

@pytest.mark.unit
class TestEndToEndScenarios:
    """Integration-style tests combining multiple checks."""

    def test_clean_loan_file_passes_all_checks(self):
        """A perfectly consistent W2/paystub pair should pass with high confidence."""
        w2 = _make_w2(
            employer_name="Acme Corporation",
            employer_ein="12-3456789",
            employee_name="John A Smith",
            wages_tips_compensation=120000.00,
            federal_tax_withheld=24000.00,
            social_security_wages=120000.00,
            medicare_wages=120000.00,
            state_income_tax=6000.00,
            box_12_d=10000.00,
        )
        ps = _make_paystub(
            employer_name="Acme Corporation",
            employer_ein="12-3456789",
            employee_name="John A Smith",
            pay_date="2025-07-01",
            ytd_gross=60000.00,
            ytd_federal_tax=12000.00,
            ytd_social_security_wages=60000.00,
            ytd_social_security_tax=3720.00,
            ytd_medicare_wages=60000.00,
            ytd_medicare_tax=870.00,
            ytd_state_tax=3000.00,
            ytd_401k=5000.00,
        )
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.is_consistent is True
        assert report.employer_match is True
        assert report.employee_match is True
        assert report.income_consistent is True
        assert report.withholding_consistent is True
        assert report.confidence_score >= 90
        assert len(report.critical_findings) == 0
        assert len(report.high_findings) == 0

    def test_fabricated_paystub_multiple_red_flags(self):
        """A fabricated paystub should trigger multiple red flags with low confidence."""
        w2 = _make_w2(
            employer_name="Acme Corporation",
            employer_ein="12-3456789",
            employee_name="John Smith",
        )
        ps = _make_paystub(
            employer_name="Acme Inc",    # will normalize to match
            employer_ein="99-0000000",   # EIN mismatch
            employee_name="John Smith",
            pay_date="2025-07-01",
            ytd_gross=200000.00,         # way over prorated
            ytd_federal_tax=1000.00,     # too low
            ytd_social_security_tax=0,   # no FICA
            ytd_medicare_tax=0,          # no FICA
        )
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.is_consistent is False
        assert report.confidence_score <= 40
        assert len(report.critical_findings) >= 1  # At least EIN or FICA
        # Should have at least 3 findings total
        assert len(report.findings) >= 3

    def test_hourly_employee_with_overtime_full_validation(self):
        """Full validation for an hourly employee with overtime."""
        w2 = _make_w2(
            employer_name="Construction Co LLC",
            employer_ein="55-1234567",
            employee_name="Mike Johnson",
            wages_tips_compensation=78000.00,
            federal_tax_withheld=11700.00,
            social_security_wages=78000.00,
            medicare_wages=78000.00,
            state_income_tax=3900.00,
        )
        ps = _make_paystub(
            employer_name="Construction Co LLC",
            employer_ein="55-1234567",
            employee_name="Mike Johnson",
            pay_date="2025-07-01",
            pay_frequency="BIWEEKLY",
            hourly_rate=28.00,
            hours_worked=90,
            overtime_hours=10,
            overtime_rate=42.00,  # 1.5x
            gross_pay=2660.00,   # 80*28 + 10*42
            ytd_gross=39000.00,
            ytd_federal_tax=5850.00,
            ytd_social_security_wages=39000.00,
            ytd_social_security_tax=2418.00,
            ytd_medicare_wages=39000.00,
            ytd_medicare_tax=565.50,
            ytd_state_tax=1950.00,
            ytd_401k=0,
        )
        report = cross_validate_w2_paystub(w2, ps, tax_year=2025)
        assert report.employer_match is True
        assert report.employee_match is True
        assert report.confidence_score >= 70
        assert report.is_consistent is True
        # OT rate should be correct (1.5x $28 = $42)
        assert not any(f.check_type == "OT_RATE_MISMATCH" for f in report.findings)
        # No critical or high findings
        assert len(report.critical_findings) == 0
        assert len(report.high_findings) == 0


# =============================================================================
# HELPER FUNCTION UNIT TESTS
# =============================================================================

@pytest.mark.unit
class TestHelperFunctions:
    """Unit tests for internal helper functions."""

    def test_normalize_employer_name_strips_suffix(self):
        assert _normalize_employer_name("Acme Inc.") == "acme"
        assert _normalize_employer_name("Acme Corporation") == "acme"
        assert _normalize_employer_name("Smith Consulting LLC") == "smith consulting"

    def test_normalize_employer_name_case_insensitive(self):
        assert _normalize_employer_name("ACME CORP") == _normalize_employer_name("acme corporation")

    def test_normalize_employer_name_empty(self):
        assert _normalize_employer_name("") == ""
        assert _normalize_employer_name(None) == ""

    def test_normalize_employee_name_strips_suffix(self):
        assert _normalize_employee_name("John Smith Jr.") == "john smith"
        assert _normalize_employee_name("John Smith III") == "john smith"
        assert _normalize_employee_name("John Smith Sr") == "john smith"

    def test_is_round_number(self):
        assert _is_round_number(100000.0) is True
        assert _is_round_number(50000.0) is True
        assert _is_round_number(87432.56) is False
        assert _is_round_number(0) is False
        assert _is_round_number(-1000) is False

    def test_pct_variance(self):
        assert _pct_variance(100, 105) == pytest.approx(5.0)
        assert _pct_variance(100, 100) == pytest.approx(0.0)
        assert _pct_variance(0, 100) == pytest.approx(100.0)
        assert _pct_variance(0, 0) == pytest.approx(0.0)

    def test_pct_variance_symmetry(self):
        """Variance should be absolute (same magnitude whether over or under)."""
        assert _pct_variance(100, 110) == _pct_variance(100, 90)
