"""
Shared financial calculation utilities for mortgage agents.

Extracted from portfolio_agent.py, analytics_agent.py, and profitability_agent.py
to eliminate duplication of LTV, equity, and amortization calculations.
"""

from typing import Dict, Optional, Tuple


# Default market assumptions
DEFAULT_APPRECIATION_RATE = 0.05  # 5% annual
DEFAULT_BALANCE_DECAY_RATE = 0.002  # Simplified monthly principal paydown factor
MIN_BALANCE_FACTOR = 0.5  # Floor for estimated balance (never below 50% of original)


def estimate_current_property_value(
    original_value: float,
    months_since_close: int,
    annual_appreciation_rate: float = DEFAULT_APPRECIATION_RATE,
) -> float:
    """Estimate current property value based on appreciation."""
    appreciation_factor = 1 + (annual_appreciation_rate * months_since_close / 12)
    return original_value * appreciation_factor


def estimate_remaining_balance(
    original_amount: float,
    months_since_close: int,
    decay_rate: float = DEFAULT_BALANCE_DECAY_RATE,
) -> float:
    """Estimate remaining loan balance using simplified amortization."""
    balance_factor = 1 - (months_since_close * decay_rate)
    return original_amount * max(MIN_BALANCE_FACTOR, balance_factor)


def calculate_ltv(
    loan_amount: float,
    property_value: float,
    months_since_close: int = 0,
    annual_appreciation_rate: float = DEFAULT_APPRECIATION_RATE,
) -> Dict[str, float]:
    """
    Calculate original and current LTV with equity estimates.

    Returns dict with: original_ltv, current_ltv, current_value,
    current_balance, equity, equity_percent
    """
    original_ltv = (loan_amount / property_value) * 100

    current_value = estimate_current_property_value(
        property_value, months_since_close, annual_appreciation_rate
    )
    current_balance = estimate_remaining_balance(loan_amount, months_since_close)
    current_ltv = (current_balance / current_value) * 100
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
) -> Dict[str, float]:
    """Calculate potential rate savings for refinance candidates."""
    rate_diff = current_rate - market_rate
    monthly_savings = (rate_diff / 100 / 12) * estimated_balance
    return {
        "rate_savings": round(rate_diff, 3),
        "monthly_savings": round(monthly_savings, 2),
        "annual_savings": round(monthly_savings * 12, 2),
    }


def calculate_margin_bps(profit: float, loan_amount: float) -> float:
    """Calculate margin in basis points."""
    if loan_amount <= 0:
        return 0.0
    return round((profit / loan_amount) * 10000, 1)
