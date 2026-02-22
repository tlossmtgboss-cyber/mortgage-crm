"""
Amortization Service
====================
Pure Python loan amortization calculations for the MUM Portal.

No database dependency — accepts numeric inputs and returns computed values.
Used by the post-close data endpoint to calculate current balance, equity, etc.
"""

from datetime import date, datetime
from typing import Optional, Union


def calculate_monthly_payment(
    principal: float,
    annual_rate: float,
    term_months: int = 360,
) -> float:
    """
    Calculate the fixed monthly payment (P&I) for a fully amortizing loan.

    Args:
        principal: Original loan amount
        annual_rate: Annual interest rate as a percentage (e.g. 6.5 for 6.5%)
        term_months: Total loan term in months (default 360 = 30 years)

    Returns:
        Monthly payment amount (principal + interest only, no escrow)
    """
    if principal <= 0 or term_months <= 0:
        return 0.0

    if annual_rate <= 0:
        # Zero interest — simple division
        return principal / term_months

    monthly_rate = annual_rate / 100.0 / 12.0
    factor = (1 + monthly_rate) ** term_months
    payment = principal * (monthly_rate * factor) / (factor - 1)
    return round(payment, 2)


def calculate_current_balance(
    principal: float,
    annual_rate: float,
    term_months: int = 360,
    first_payment_date: Optional[Union[str, date, datetime]] = None,
    as_of_date: Optional[Union[str, date, datetime]] = None,
) -> float:
    """
    Calculate the remaining loan balance as of a given date.

    Uses standard amortization schedule to determine how many payments
    have been made and what the remaining principal is.

    Args:
        principal: Original loan amount
        annual_rate: Annual interest rate as a percentage (e.g. 6.5)
        term_months: Total loan term in months (default 360)
        first_payment_date: Date of the first payment (str or date)
        as_of_date: Calculate balance as of this date (default: today)

    Returns:
        Remaining principal balance
    """
    if principal <= 0:
        return 0.0

    # Parse dates
    if isinstance(first_payment_date, str):
        first_payment_date = _parse_date(first_payment_date)
    elif isinstance(first_payment_date, datetime):
        first_payment_date = first_payment_date.date()

    if isinstance(as_of_date, str):
        as_of_date = _parse_date(as_of_date)
    elif isinstance(as_of_date, datetime):
        as_of_date = as_of_date.date()

    if first_payment_date is None:
        # No first payment date — can't compute, return original principal
        return principal

    if as_of_date is None:
        as_of_date = date.today()

    # Calculate months elapsed
    months_elapsed = (
        (as_of_date.year - first_payment_date.year) * 12
        + (as_of_date.month - first_payment_date.month)
    )

    # If as_of_date is before the first_payment_date, no payments made yet
    if months_elapsed < 0:
        return principal

    # Cap at term_months
    payments_made = min(months_elapsed, term_months)

    if payments_made >= term_months:
        return 0.0

    if annual_rate <= 0:
        # Zero interest
        monthly_pmt = principal / term_months
        return max(0.0, principal - (monthly_pmt * payments_made))

    monthly_rate = annual_rate / 100.0 / 12.0
    monthly_payment = calculate_monthly_payment(principal, annual_rate, term_months)

    # Remaining balance after N payments:
    # B(n) = P * (1+r)^n - PMT * ((1+r)^n - 1) / r
    factor = (1 + monthly_rate) ** payments_made
    balance = principal * factor - monthly_payment * (factor - 1) / monthly_rate

    return max(0.0, round(balance, 2))


def calculate_dti(
    monthly_income: float,
    monthly_debts: float,
    proposed_payment: float = 0.0,
) -> dict:
    """
    Calculate debt-to-income ratios.

    Returns:
        Dict with front_end_dti, back_end_dti
    """
    if monthly_income <= 0:
        return {"front_end_dti": 0.0, "back_end_dti": 0.0}

    front_end = (proposed_payment / monthly_income) * 100
    back_end = ((monthly_debts + proposed_payment) / monthly_income) * 100

    return {
        "front_end_dti": round(front_end, 2),
        "back_end_dti": round(back_end, 2),
    }


def calculate_max_purchase_price(
    annual_income: float,
    monthly_debts: float,
    annual_rate: float,
    term_months: int = 360,
    max_dti: float = 43.0,
    down_payment_pct: float = 20.0,
    tax_rate_pct: float = 1.25,
    insurance_annual: float = 1200.0,
) -> dict:
    """
    Estimate max purchase price based on income and DTI limits.

    Returns:
        Dict with max_purchase_price, max_loan_amount, monthly_payment, dti
    """
    monthly_income = annual_income / 12.0
    if monthly_income <= 0:
        return {
            "max_purchase_price": 0,
            "max_loan_amount": 0,
            "monthly_payment": 0,
            "dti": 0,
        }

    # Max total housing payment based on DTI
    max_total_payment = (monthly_income * max_dti / 100.0) - monthly_debts
    if max_total_payment <= 0:
        return {
            "max_purchase_price": 0,
            "max_loan_amount": 0,
            "monthly_payment": 0,
            "dti": max_dti,
        }

    # Subtract estimated taxes + insurance from max payment to get max P&I
    monthly_insurance = insurance_annual / 12.0
    # We need to iterate since taxes depend on purchase price
    # Use a simple iterative approach
    max_loan = _solve_max_loan(
        max_total_payment, annual_rate, term_months,
        tax_rate_pct, monthly_insurance,
    )

    dp_fraction = down_payment_pct / 100.0
    if dp_fraction >= 1.0:
        dp_fraction = 0.20  # fallback

    max_purchase = max_loan / (1.0 - dp_fraction)
    monthly_pmt = calculate_monthly_payment(max_loan, annual_rate, term_months)

    return {
        "max_purchase_price": round(max_purchase, 0),
        "max_loan_amount": round(max_loan, 0),
        "monthly_payment": round(monthly_pmt, 2),
        "dti": round(max_dti, 2),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> Optional[date]:
    """Parse a date string in common formats."""
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S%z", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.split("+")[0].split("Z")[0], fmt).date()
        except ValueError:
            continue
    return None


def _solve_max_loan(
    max_total_payment: float,
    annual_rate: float,
    term_months: int,
    tax_rate_pct: float,
    monthly_insurance: float,
) -> float:
    """
    Iteratively solve for max loan amount given a total payment budget.
    Total payment = P&I + taxes + insurance.
    Taxes depend on property value which depends on loan amount.
    """
    # Start with an estimate: assume P&I is 70% of total payment
    estimate = max_total_payment * 0.70
    if annual_rate > 0:
        monthly_rate = annual_rate / 100.0 / 12.0
        factor = (1 + monthly_rate) ** term_months
        # max_loan ≈ estimate * ((1+r)^n - 1) / (r * (1+r)^n)
        loan_guess = estimate * (factor - 1) / (monthly_rate * factor)
    else:
        loan_guess = estimate * term_months

    # Iterate a few times to converge
    for _ in range(10):
        pmt = calculate_monthly_payment(loan_guess, annual_rate, term_months)
        # Estimate property value as loan / 0.80
        prop_value = loan_guess / 0.80
        monthly_taxes = prop_value * (tax_rate_pct / 100.0) / 12.0
        total = pmt + monthly_taxes + monthly_insurance

        if total <= 0:
            break

        # Scale loan proportionally
        ratio = max_total_payment / total
        new_guess = loan_guess * ratio

        if abs(new_guess - loan_guess) < 100:
            loan_guess = new_guess
            break

        loan_guess = new_guess

    return max(0.0, loan_guess)
