"""
MUM Utility Functions for Calculations
"""
import math
from datetime import datetime, date
from decimal import Decimal
from dateutil.relativedelta import relativedelta


def calculate_monthly_payment(principal, annual_rate, num_payments):
    """
    Calculate monthly mortgage payment using standard amortization formula

    Args:
        principal: Original loan amount
        annual_rate: Annual interest rate (e.g., 6.5 for 6.5%)
        num_payments: Total number of payments (e.g., 360 for 30-year)

    Returns:
        Monthly payment amount
    """
    if annual_rate == 0:
        return principal / num_payments

    monthly_rate = (annual_rate / 100) / 12

    # M = P * [r(1+r)^n] / [(1+r)^n - 1]
    payment = principal * (monthly_rate * math.pow(1 + monthly_rate, num_payments)) / \
              (math.pow(1 + monthly_rate, num_payments) - 1)

    return round(payment, 2)


def calculate_remaining_balance(original_principal, annual_rate, num_payments, payments_made):
    """
    Calculate remaining loan balance after n payments

    Args:
        original_principal: Original loan amount
        annual_rate: Annual interest rate (e.g., 6.5 for 6.5%)
        num_payments: Total number of payments (e.g., 360 for 30-year)
        payments_made: Number of payments already made

    Returns:
        Remaining balance
    """
    if payments_made >= num_payments:
        return 0

    if annual_rate == 0:
        return original_principal - (original_principal / num_payments * payments_made)

    monthly_rate = (annual_rate / 100) / 12

    # B = P * [(1+r)^n - (1+r)^p] / [(1+r)^n - 1]
    balance = original_principal * \
              (math.pow(1 + monthly_rate, num_payments) - math.pow(1 + monthly_rate, payments_made)) / \
              (math.pow(1 + monthly_rate, num_payments) - 1)

    return max(0, round(balance, 2))


def calculate_current_balance(original_amount, annual_rate, first_payment_date, loan_term_years=30):
    """
    Calculate current loan balance based on first payment date and today's date

    Args:
        original_amount: Original loan amount
        annual_rate: Annual interest rate
        first_payment_date: Date of first payment
        loan_term_years: Loan term in years (default 30)

    Returns:
        Current remaining balance
    """
    if isinstance(first_payment_date, str):
        first_payment_date = datetime.strptime(first_payment_date, '%Y-%m-%d').date()

    today = date.today()

    # Calculate months since first payment
    months_diff = (today.year - first_payment_date.year) * 12 + (today.month - first_payment_date.month)

    # Add 1 if we're past the payment day of the month
    if today.day >= first_payment_date.day:
        months_diff += 1

    payments_made = max(0, months_diff)
    total_payments = loan_term_years * 12

    return calculate_remaining_balance(original_amount, annual_rate, total_payments, payments_made)


def calculate_property_value(original_value, first_payment_date, annual_appreciation_rate=4.0):
    """
    Calculate current property value based on appreciation

    Args:
        original_value: Appraisal value at closing
        first_payment_date: Date of first payment
        annual_appreciation_rate: Annual appreciation percentage (default 4%)

    Returns:
        Current estimated property value
    """
    if isinstance(first_payment_date, str):
        first_payment_date = datetime.strptime(first_payment_date, '%Y-%m-%d').date()

    today = date.today()

    # Calculate years since first payment
    years_diff = (today - first_payment_date).days / 365.25

    # Compound appreciation: V = P * (1 + r)^t
    current_value = original_value * math.pow(1 + (annual_appreciation_rate / 100), years_diff)

    return round(current_value, 2)


def calculate_ltv(loan_balance, property_value):
    """
    Calculate Loan-to-Value ratio

    Args:
        loan_balance: Current loan balance
        property_value: Current property value

    Returns:
        LTV as a percentage (e.g., 0.80 for 80%)
    """
    if property_value == 0:
        return 0

    ltv = loan_balance / property_value
    return round(ltv, 4)


def calculate_principal_payment(remaining_balance, annual_rate, num_payments_remaining):
    """
    Calculate the principal portion of the next payment

    Args:
        remaining_balance: Current loan balance
        annual_rate: Annual interest rate
        num_payments_remaining: Number of payments left

    Returns:
        Principal amount in next payment
    """
    if num_payments_remaining == 0 or annual_rate == 0:
        return remaining_balance

    monthly_rate = (annual_rate / 100) / 12

    # Calculate monthly payment
    monthly_payment = calculate_monthly_payment(remaining_balance, annual_rate, num_payments_remaining)

    # Interest portion
    interest_payment = remaining_balance * monthly_rate

    # Principal portion
    principal_payment = monthly_payment - interest_payment

    return round(principal_payment, 2)


def calculate_equity(property_value, loan_balance):
    """
    Calculate equity amount and percentage

    Args:
        property_value: Current property value
        loan_balance: Current loan balance

    Returns:
        Tuple of (equity_amount, equity_percentage)
    """
    equity_amount = max(0, property_value - loan_balance)
    equity_percentage = equity_amount / property_value if property_value > 0 else 0

    return (round(equity_amount, 2), round(equity_percentage, 4))


def determine_loan_term_from_type(loan_type):
    """
    Determine loan term in years from loan type

    Args:
        loan_type: Loan type string (e.g., "30-Year Fixed", "15-Year Fixed")

    Returns:
        Loan term in years (default 30)
    """
    loan_type_lower = loan_type.lower()

    if '15' in loan_type_lower or 'fifteen' in loan_type_lower:
        return 15
    elif '20' in loan_type_lower or 'twenty' in loan_type_lower:
        return 20
    elif '10' in loan_type_lower or 'ten' in loan_type_lower:
        return 10
    else:
        return 30  # Default to 30-year


def calculate_days_since_funding(closing_date):
    """
    Calculate days since loan funding

    Args:
        closing_date: Date of closing

    Returns:
        Number of days since funding
    """
    if isinstance(closing_date, str):
        closing_date = datetime.strptime(closing_date, '%Y-%m-%d').date()

    today = date.today()
    return (today - closing_date).days


def calculate_servicing_revenue(loan_balance, servicing_rate=0.0025):
    """
    Calculate annual servicing revenue

    Args:
        loan_balance: Current loan balance
        servicing_rate: Annual servicing rate (default 0.25% = 0.0025)

    Returns:
        Annual servicing revenue
    """
    return round(loan_balance * servicing_rate, 2)


def should_flag_refinance_opportunity(current_rate, market_rate_threshold=6.0, rate_drop_threshold=0.75):
    """
    Determine if client should be flagged for refinance opportunity

    Args:
        current_rate: Client's current interest rate
        market_rate_threshold: Current market rate
        rate_drop_threshold: Minimum rate drop to make refinancing worthwhile

    Returns:
        Boolean indicating if refinance opportunity exists
    """
    return current_rate >= (market_rate_threshold + rate_drop_threshold)


def should_flag_heloc_opportunity(equity_percentage, equity_amount, min_equity_pct=0.20, min_equity_amount=50000):
    """
    Determine if client should be flagged for HELOC opportunity

    Args:
        equity_percentage: Current equity percentage (e.g., 0.30 for 30%)
        equity_amount: Current equity amount in dollars
        min_equity_pct: Minimum equity percentage required
        min_equity_amount: Minimum equity dollar amount required

    Returns:
        Boolean indicating if HELOC opportunity exists
    """
    return equity_percentage >= min_equity_pct and equity_amount >= min_equity_amount
