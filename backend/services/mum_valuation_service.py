"""
MUM Valuation Service — Shared calculation functions for MUM client
property valuation, equity, and refinance scoring.

Wraps financial_calcs functions with MUM-client-specific logic and
provides convenience functions for the REST endpoints and AI agents.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from agents.utils.financial_calcs import (
    calculate_remaining_balance,
    estimate_current_property_value,
    get_appreciation_rate,
    calculate_monthly_payment,
    calculate_rate_savings,
)

logger = logging.getLogger(__name__)

DEFAULT_MARKET_RATE = 6.5
DEFAULT_CLOSING_COST_PCT = 0.02


def compute_mum_client_values(
    original_value: float,
    original_amount: float,
    interest_rate: float,
    term: int = 360,
    first_payment_date: Optional[datetime] = None,
    property_state: Optional[str] = None,
    market_rate: float = DEFAULT_MARKET_RATE,
) -> Dict:
    """
    Compute all valuation fields for a single MUM client.

    Args:
        original_value: Appraisal value at closing
        original_amount: Original loan amount
        interest_rate: Annual interest rate as percentage (e.g. 7.5)
        term: Loan term in months
        first_payment_date: Date of first payment (timezone-aware)
        property_state: State code for appreciation lookup
        market_rate: Current market rate for refi scoring

    Returns:
        Dict with: current_value, remaining_balance, equity, ltv,
                   maturity_date, refi_score, refi_opportunity, estimated_savings
    """
    rate_decimal = interest_rate / 100 if interest_rate > 0 else 0.065

    # Months since first payment
    months_passed = 0
    if first_payment_date:
        if first_payment_date.tzinfo is None:
            first_payment_date = first_payment_date.replace(tzinfo=timezone.utc)
        months_passed = max(0, (datetime.now(timezone.utc) - first_payment_date).days // 30)

    # Property value
    appreciation_rate = get_appreciation_rate(property_state)
    current_value = estimate_current_property_value(original_value, months_passed, appreciation_rate)

    # Balance
    remaining_balance = calculate_remaining_balance(original_amount, rate_decimal, term, months_passed)

    # Equity / LTV
    equity = current_value - remaining_balance
    ltv = (remaining_balance / current_value * 100) if current_value > 0 else 0

    # Maturity
    maturity_date = None
    if first_payment_date:
        maturity_date = first_payment_date + timedelta(days=term * 30.44)

    # Refi score
    rate_diff = interest_rate - market_rate
    equity_pct = 100 - ltv
    score = _calculate_refi_score(rate_diff, equity_pct, remaining_balance, months_passed, market_rate, interest_rate)

    refi_opportunity = score >= 50
    savings = calculate_rate_savings(interest_rate, market_rate, remaining_balance, 360)
    estimated_savings = round(savings["annual_savings"], 2) if refi_opportunity else 0

    return {
        "current_value": round(current_value, 2),
        "remaining_balance": round(remaining_balance, 2),
        "equity": round(equity, 2),
        "ltv": round(ltv, 1),
        "maturity_date": maturity_date,
        "refi_score": score,
        "refi_opportunity": refi_opportunity,
        "estimated_savings": estimated_savings,
        "appreciation_rate": round(appreciation_rate * 100, 2),
        "months_passed": months_passed,
    }


def _calculate_refi_score(
    rate_diff: float,
    equity_pct: float,
    remaining_balance: float,
    months_passed: int,
    market_rate: float,
    current_rate: float,
) -> int:
    """Calculate 0-100 refi score."""
    score = 0

    # Rate differential (0-35)
    if rate_diff >= 2.0: score += 35
    elif rate_diff >= 1.5: score += 30
    elif rate_diff >= 1.0: score += 25
    elif rate_diff >= 0.75: score += 20
    elif rate_diff >= 0.5: score += 15
    elif rate_diff >= 0.25: score += 8
    elif rate_diff > 0: score += 3

    # Equity (0-20)
    if equity_pct >= 40: score += 20
    elif equity_pct >= 30: score += 17
    elif equity_pct >= 20: score += 14
    elif equity_pct >= 10: score += 8
    elif equity_pct >= 5: score += 4

    # Loan size (0-15)
    if remaining_balance >= 500000: score += 15
    elif remaining_balance >= 400000: score += 13
    elif remaining_balance >= 300000: score += 10
    elif remaining_balance >= 200000: score += 7
    elif remaining_balance >= 100000: score += 4
    else: score += 1

    # Time in loan (0-10)
    if months_passed >= 36: score += 10
    elif months_passed >= 24: score += 8
    elif months_passed >= 18: score += 6
    elif months_passed >= 12: score += 4
    elif months_passed >= 6: score += 2

    # Rate trend (0-10)
    score += 5 if rate_diff > 0 else 0

    # Breakeven (0-10)
    closing_costs = remaining_balance * DEFAULT_CLOSING_COST_PCT
    savings = calculate_rate_savings(current_rate, market_rate, remaining_balance, 360)
    ms = savings["monthly_savings"]
    if ms > 0:
        be = closing_costs / ms
        if be <= 12: score += 10
        elif be <= 24: score += 7
        elif be <= 36: score += 4
        elif be <= 48: score += 2

    return min(100, max(0, score))
