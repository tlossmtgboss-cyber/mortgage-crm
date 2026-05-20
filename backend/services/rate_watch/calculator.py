"""
Rate math. Pure functions. No I/O. Fully unit-tested in tests/test_calculator.py.

Three responsibilities:
  1. compute_perennia_rate(market_rate, margin_bps) — the rate we quote.
  2. monthly_payment(...) — standard amortization.
  3. evaluate_savings(...) — compares current vs projected, returns the snapshot.

Every monetary value is Decimal. Never float. The QA agent will block any PR
that introduces float into this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


# -----------------------------------------------------------------------------
# Rate math
# -----------------------------------------------------------------------------
def compute_perennia_rate(market_rate: Decimal, margin_bps: int) -> Decimal:
    """
    Perennia rate = market_rate - margin (in basis points).

    Examples:
      compute_perennia_rate(Decimal("6.6500"), 25) → Decimal("6.4000")
      compute_perennia_rate(Decimal("6.1000"), 25) → Decimal("5.8500")

    Margin is allowed to be negative (i.e. we'd quote *above* market) but
    that's a rare config decision — defended in the DB CHECK constraint.
    """
    if not isinstance(market_rate, Decimal):
        raise TypeError("market_rate must be Decimal — never float")

    margin = Decimal(margin_bps) / Decimal("100")  # bps → percentage points
    return (market_rate - margin).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


# -----------------------------------------------------------------------------
# Amortization
# -----------------------------------------------------------------------------
def monthly_payment(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    """
    Standard fixed-rate fully-amortizing monthly payment.

    P = L * (c * (1+c)^n) / ((1+c)^n - 1)

    where c = monthly rate as a fraction, n = term in months, L = principal.

    Returns payment rounded to cents (2 dp, half-up).

    Zero-rate edge case (annual_rate == 0): payment is principal / term_months.
    """
    if principal < 0:
        raise ValueError("principal must be non-negative")
    if term_months <= 0:
        raise ValueError("term_months must be positive")
    if annual_rate < 0:
        raise ValueError("annual_rate must be non-negative")

    if annual_rate == 0:
        return (principal / Decimal(term_months)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Monthly rate as fraction. annual_rate is a percentage like 6.6500.
    c = annual_rate / Decimal("100") / Decimal("12")

    # Use higher precision intermediate. Decimal handles ** with non-integer
    # exponents poorly; we use the closed-form with integer exponent via pow.
    one_plus_c = Decimal("1") + c
    one_plus_c_n = one_plus_c ** term_months

    numerator = principal * c * one_plus_c_n
    denominator = one_plus_c_n - Decimal("1")
    payment = numerator / denominator

    return payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# -----------------------------------------------------------------------------
# Savings evaluation
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class SavingsSnapshot:
    current_payment: Decimal
    projected_payment: Decimal
    monthly_savings: Decimal
    annual_savings: Decimal
    estimated_break_even_months: int | None
    notes: tuple[str, ...] = ()


# Industry-typical default refi closing-cost rule of thumb: 2-5% of loan amount.
# We use 2.5% as the planning default. LO can override per-loan in the future.
DEFAULT_CLOSING_COST_RATE = Decimal("0.025")


def evaluate_savings(
    *,
    current_balance: Decimal,
    current_rate: Decimal,
    current_payment: Decimal,
    new_rate: Decimal,
    new_term_months: int,
    closing_costs: Decimal | None = None,
) -> SavingsSnapshot:
    """
    Given the borrower's current loan state and a proposed new rate/term,
    compute monthly savings, annual savings, and break-even.

    Notes returned in the snapshot flag things a human should be aware of:
      - "payment_increased" if new payment > current (term extension can do this)
      - "rate_increased" if new rate >= current (shouldn't happen but guard anyway)
      - "short_break_even" / "long_break_even"
    """
    if closing_costs is None:
        closing_costs = (current_balance * DEFAULT_CLOSING_COST_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    projected_payment = monthly_payment(
        principal=current_balance,
        annual_rate=new_rate,
        term_months=new_term_months,
    )

    monthly_savings = (current_payment - projected_payment).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    annual_savings = (monthly_savings * Decimal("12")).quantize(Decimal("0.01"))

    notes: list[str] = []
    if new_rate >= current_rate:
        notes.append("rate_increased")
    if monthly_savings <= 0:
        notes.append("payment_increased")

    break_even: int | None
    if monthly_savings <= 0:
        break_even = None
    else:
        # break-even in months = closing_costs / monthly_savings, ceiling.
        raw = closing_costs / monthly_savings
        break_even = int(raw.to_integral_value(rounding=ROUND_HALF_UP))
        if raw > Decimal(break_even):
            break_even += 1
        if break_even <= 18:
            notes.append("short_break_even")
        elif break_even >= 60:
            notes.append("long_break_even")

    return SavingsSnapshot(
        current_payment=current_payment,
        projected_payment=projected_payment,
        monthly_savings=monthly_savings,
        annual_savings=annual_savings,
        estimated_break_even_months=break_even,
        notes=tuple(notes),
    )
