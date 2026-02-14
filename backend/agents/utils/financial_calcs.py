"""
Shared financial calculation utilities for mortgage agents.

Provides proper amortization math, state-level appreciation rates,
and equity/LTV calculations used by home valuation and refinance agents.
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple


# =============================================================================
# State-Level Appreciation Rates (FHFA regional averages, annual)
# =============================================================================

STATE_APPRECIATION_RATES = {
    # Pacific
    "CA": 0.045, "OR": 0.050, "WA": 0.055, "HI": 0.040, "AK": 0.025,
    # Mountain
    "AZ": 0.055, "CO": 0.045, "ID": 0.065, "MT": 0.060, "NV": 0.050,
    "NM": 0.040, "UT": 0.060, "WY": 0.035,
    # West South Central
    "TX": 0.040, "OK": 0.035, "AR": 0.035, "LA": 0.025,
    # East South Central
    "AL": 0.035, "KY": 0.040, "MS": 0.030, "TN": 0.050,
    # South Atlantic
    "FL": 0.055, "GA": 0.045, "SC": 0.050, "NC": 0.045, "VA": 0.040,
    "WV": 0.025, "MD": 0.035, "DE": 0.040, "DC": 0.035,
    # East North Central
    "IL": 0.035, "IN": 0.045, "MI": 0.040, "OH": 0.040, "WI": 0.045,
    # West North Central
    "IA": 0.035, "KS": 0.035, "MN": 0.045, "MO": 0.035, "NE": 0.040,
    "ND": 0.030, "SD": 0.035,
    # New England
    "CT": 0.040, "MA": 0.045, "ME": 0.055, "NH": 0.050, "RI": 0.045,
    "VT": 0.045,
    # Middle Atlantic
    "NJ": 0.045, "NY": 0.035, "PA": 0.040,
}

NATIONAL_APPRECIATION_RATE = 0.035  # National fallback


def get_appreciation_rate(state: Optional[str] = None, zip_code: Optional[str] = None) -> float:
    """
    Get annual appreciation rate for a location.
    Lookup chain: state code -> national fallback.
    """
    if state:
        rate = STATE_APPRECIATION_RATES.get(state.upper().strip())
        if rate is not None:
            return rate
    return NATIONAL_APPRECIATION_RATE


# =============================================================================
# Proper Amortization Math
# =============================================================================

def calculate_monthly_payment(
    principal: float,
    annual_rate: float,
    term_months: int = 360,
) -> float:
    """
    Calculate monthly P&I payment using standard amortization formula.
    M = P * [r(1+r)^n] / [(1+r)^n - 1]

    Args:
        principal: Loan amount
        annual_rate: Annual interest rate as decimal (e.g., 0.065 for 6.5%)
        term_months: Loan term in months (default 360 = 30 years)
    """
    if principal <= 0 or term_months <= 0:
        return 0.0
    if annual_rate <= 0:
        return principal / term_months

    r = annual_rate / 12  # Monthly rate
    n = term_months
    payment = principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    return round(payment, 2)


def calculate_remaining_balance(
    principal: float,
    annual_rate: float,
    term_months: int = 360,
    payments_made: int = 0,
) -> float:
    """
    Calculate exact remaining balance after N payments.
    B = P * [(1+r)^n - (1+r)^p] / [(1+r)^n - 1]

    Args:
        principal: Original loan amount
        annual_rate: Annual interest rate as decimal (e.g., 0.065 for 6.5%)
        term_months: Original loan term in months
        payments_made: Number of payments already made
    """
    if principal <= 0 or term_months <= 0:
        return 0.0
    if payments_made >= term_months:
        return 0.0
    if payments_made <= 0:
        return principal
    if annual_rate <= 0:
        # Interest-free: linear paydown
        return max(0.0, principal * (1 - payments_made / term_months))

    r = annual_rate / 12
    n = term_months
    p = payments_made
    balance = principal * ((1 + r) ** n - (1 + r) ** p) / ((1 + r) ** n - 1)
    return round(max(0.0, balance), 2)


def calculate_amortization_schedule(
    principal: float,
    annual_rate: float,
    term_months: int = 360,
    start_payment: int = 1,
    count: int = 12,
) -> List[Dict]:
    """
    Generate amortization schedule for a range of payments.

    Returns list of dicts with: payment_number, payment, principal_portion,
    interest_portion, remaining_balance
    """
    if principal <= 0 or term_months <= 0:
        return []

    monthly_payment = calculate_monthly_payment(principal, annual_rate, term_months)
    r = annual_rate / 12 if annual_rate > 0 else 0

    # Fast-forward to start_payment balance
    balance = calculate_remaining_balance(principal, annual_rate, term_months, start_payment - 1)

    schedule = []
    for i in range(count):
        pmt_num = start_payment + i
        if pmt_num > term_months or balance <= 0:
            break

        interest = balance * r if r > 0 else 0
        principal_portion = min(monthly_payment - interest, balance)
        balance -= principal_portion

        schedule.append({
            "payment_number": pmt_num,
            "payment": round(monthly_payment, 2),
            "principal_portion": round(principal_portion, 2),
            "interest_portion": round(interest, 2),
            "remaining_balance": round(max(0, balance), 2),
        })

    return schedule


# =============================================================================
# Property Value / Appreciation
# =============================================================================

def estimate_current_property_value(
    original_value: float,
    months_since_close: int,
    annual_appreciation_rate: Optional[float] = None,
    state: Optional[str] = None,
) -> float:
    """
    Estimate current property value using compound appreciation.
    V = V0 * (1 + r)^years
    """
    if original_value <= 0:
        return 0.0
    if annual_appreciation_rate is None:
        annual_appreciation_rate = get_appreciation_rate(state)
    years = months_since_close / 12
    return round(original_value * (1 + annual_appreciation_rate) ** years, 2)


# =============================================================================
# LTV / Equity
# =============================================================================

def estimate_remaining_balance(
    original_amount: float,
    months_since_close: int,
    annual_rate: float = 0.065,
    term_months: int = 360,
) -> float:
    """
    Estimate remaining balance using proper amortization.
    Wrapper for calculate_remaining_balance with months_since_close interface.
    """
    return calculate_remaining_balance(original_amount, annual_rate, term_months, months_since_close)


def calculate_ltv(
    loan_amount: float,
    property_value: float,
    months_since_close: int = 0,
    annual_appreciation_rate: Optional[float] = None,
    annual_rate: float = 0.065,
    term_months: int = 360,
    state: Optional[str] = None,
) -> Dict[str, float]:
    """
    Calculate original and current LTV with proper amortization and appreciation.
    """
    if property_value <= 0:
        return {
            "original_ltv": 0, "current_ltv": 0, "current_value": 0,
            "current_balance": 0, "equity": 0, "equity_percent": 0,
        }

    original_ltv = (loan_amount / property_value) * 100

    current_value = estimate_current_property_value(
        property_value, months_since_close, annual_appreciation_rate, state
    )
    current_balance = calculate_remaining_balance(
        loan_amount, annual_rate, term_months, months_since_close
    )
    current_ltv = (current_balance / current_value) * 100 if current_value > 0 else 0
    equity = current_value - current_balance
    equity_percent = (equity / current_value) * 100 if current_value > 0 else 0

    return {
        "original_ltv": round(original_ltv, 1),
        "current_ltv": round(current_ltv, 1),
        "current_value": round(current_value, 0),
        "current_balance": round(current_balance, 0),
        "equity": round(equity, 0),
        "equity_percent": round(equity_percent, 1),
    }


def calculate_rate_savings(
    current_rate: float,
    market_rate: float,
    estimated_balance: float,
    term_months: int = 360,
) -> Dict[str, float]:
    """
    Calculate potential refinance savings using proper payment comparison.

    Args:
        current_rate: Current rate as percentage (e.g., 7.5 for 7.5%)
        market_rate: Available rate as percentage
        estimated_balance: Current remaining balance
        term_months: New loan term for comparison
    """
    if estimated_balance <= 0:
        return {"rate_savings": 0, "monthly_savings": 0, "annual_savings": 0, "lifetime_savings": 0}

    rate_diff = current_rate - market_rate
    current_payment = calculate_monthly_payment(estimated_balance, current_rate / 100, term_months)
    new_payment = calculate_monthly_payment(estimated_balance, market_rate / 100, term_months)
    monthly_savings = current_payment - new_payment

    return {
        "rate_savings": round(rate_diff, 3),
        "monthly_savings": round(monthly_savings, 2),
        "annual_savings": round(monthly_savings * 12, 2),
        "lifetime_savings": round(monthly_savings * term_months, 2),
        "current_payment": round(current_payment, 2),
        "new_payment": round(new_payment, 2),
    }


def calculate_margin_bps(profit: float, loan_amount: float) -> float:
    """Calculate margin in basis points."""
    if loan_amount <= 0:
        return 0.0
    return round((profit / loan_amount) * 10000, 1)
