"""
Perennia AI - Home Valuation Agent Tools
Tools for calculating home values, equity positions, amortization,
maturity dates, and batch updating MUM client valuations.
"""

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
    is_sqlite, sql_now,
)

from ..utils.financial_calcs import (
    get_appreciation_rate,
    STATE_APPRECIATION_RATES,
    NATIONAL_APPRECIATION_RATE,
    calculate_monthly_payment,
    calculate_remaining_balance,
    calculate_amortization_schedule,
    estimate_current_property_value,
)


# =============================================================================
# Tool 1: Calculate Home Value
# =============================================================================

@mortgage_tool(
    name="calculate_home_value",
    description="Calculate current estimated home value for a MUM client using state-level appreciation rates",
    agent_roles=["home_valuation", "customer_intelligence", "pipeline_analyst"],
    risk_level="low",
    examples=[
        "What's the current home value for client X?",
        "Estimate the property value for this MUM client",
    ],
)
def calculate_home_value(
    mum_client_id: Optional[int] = None,
    original_value: Optional[float] = None,
    months_since_close: Optional[int] = None,
    state: Optional[str] = None,
) -> ToolResult:
    """Calculate current home value for a MUM client or from raw inputs."""
    try:
        if mum_client_id:
            client = execute_single("""
                SELECT id, client_name, appraisal_value_at_closing,
                       original_close_date, property_state, property_zip,
                       current_property_value
                FROM mum_clients WHERE id = :cid
            """, {"cid": mum_client_id})

            if not client:
                return ToolResult.no_data(f"MUM client {mum_client_id} not found")

            original_value = float(client["appraisal_value_at_closing"] or 0)
            state = client["property_state"] or state
            if client["original_close_date"]:
                close_dt = client["original_close_date"]
                if isinstance(close_dt, str):
                    close_dt = datetime.fromisoformat(close_dt)
                months_since_close = max(0, (datetime.now(timezone.utc) - close_dt.replace(tzinfo=timezone.utc)).days // 30)
            else:
                months_since_close = months_since_close or 0

        if not original_value or original_value <= 0:
            return ToolResult.error("Original property value is required and must be > 0")

        months_since_close = months_since_close or 0
        appreciation_rate = get_appreciation_rate(state)
        current_value = estimate_current_property_value(
            original_value, months_since_close, appreciation_rate, state
        )
        appreciation_amount = current_value - original_value
        years = months_since_close / 12

        data = {
            "original_value": round(original_value, 2),
            "original_value_formatted": format_currency(original_value),
            "current_value": round(current_value, 2),
            "current_value_formatted": format_currency(current_value),
            "appreciation_amount": round(appreciation_amount, 2),
            "appreciation_amount_formatted": format_currency(appreciation_amount),
            "appreciation_rate_annual": round(appreciation_rate * 100, 2),
            "total_appreciation_pct": round(((current_value / original_value) - 1) * 100, 2) if original_value > 0 else 0,
            "years_since_close": round(years, 1),
            "state": state,
        }

        if mum_client_id:
            data["mum_client_id"] = mum_client_id
            data["client_name"] = client["client_name"]

        return ToolResult.success(
            data=data,
            message=f"Current value: {format_currency(current_value)} ({state or 'national'} rate: {appreciation_rate*100:.1f}%/yr)",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 2: Get Appreciation Rates
# =============================================================================

@mortgage_tool(
    name="get_appreciation_rates",
    description="Look up home appreciation rates by state or ZIP code",
    agent_roles=["home_valuation", "customer_intelligence"],
    risk_level="low",
    examples=[
        "What's the appreciation rate in California?",
        "Show me appreciation rates by state",
    ],
)
def get_appreciation_rates(
    state: Optional[str] = None,
    zip_code: Optional[str] = None,
    show_all: bool = False,
) -> ToolResult:
    """Look up appreciation rates."""
    try:
        if show_all:
            rates = {
                st: round(rate * 100, 2)
                for st, rate in sorted(STATE_APPRECIATION_RATES.items())
            }
            top_5 = sorted(STATE_APPRECIATION_RATES.items(), key=lambda x: x[1], reverse=True)[:5]
            bottom_5 = sorted(STATE_APPRECIATION_RATES.items(), key=lambda x: x[1])[:5]

            data = {
                "all_rates": rates,
                "national_average": round(NATIONAL_APPRECIATION_RATE * 100, 2),
                "top_5": [{"state": s, "rate": round(r * 100, 2)} for s, r in top_5],
                "bottom_5": [{"state": s, "rate": round(r * 100, 2)} for s, r in bottom_5],
                "total_states": len(rates),
            }
            return ToolResult.success(data=data, message=f"{len(rates)} state rates loaded")

        rate = get_appreciation_rate(state, zip_code)
        data = {
            "state": state,
            "zip_code": zip_code,
            "annual_rate_pct": round(rate * 100, 2),
            "annual_rate_decimal": rate,
            "national_average_pct": round(NATIONAL_APPRECIATION_RATE * 100, 2),
            "vs_national": round((rate - NATIONAL_APPRECIATION_RATE) * 100, 2),
        }
        return ToolResult.success(
            data=data,
            message=f"{state or 'National'}: {rate*100:.1f}% annual appreciation",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 3: Calculate Equity Position
# =============================================================================

@mortgage_tool(
    name="calculate_equity_position",
    description="Calculate full equity position for a MUM client including home value minus amortized balance",
    agent_roles=["home_valuation", "customer_intelligence", "lead_nurturer"],
    risk_level="low",
    examples=[
        "What's the equity position for client X?",
        "How much equity does this client have?",
    ],
)
def calculate_equity_position(
    mum_client_id: int,
) -> ToolResult:
    """Calculate equity position for a MUM client."""
    try:
        client = execute_single("""
            SELECT id, client_name, appraisal_value_at_closing, original_loan_amount,
                   current_loan_amount, interest_rate, original_rate, term,
                   original_close_date, first_payment_date,
                   property_state, property_zip, current_property_value
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        original_value = float(client["appraisal_value_at_closing"] or 0)
        original_amount = float(client["original_loan_amount"] or 0)
        rate = float(client["interest_rate"] or client["original_rate"] or 6.5) / 100
        term = client["term"] or 360
        state = client["property_state"]

        # Calculate months since first payment
        first_pmt = client["first_payment_date"] or client["original_close_date"]
        if first_pmt:
            if isinstance(first_pmt, str):
                first_pmt = datetime.fromisoformat(first_pmt)
            months_passed = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
        else:
            months_passed = 0

        # Calculate current property value
        appreciation_rate = get_appreciation_rate(state)
        current_value = estimate_current_property_value(original_value, months_passed, appreciation_rate)

        # Calculate remaining balance using proper amortization
        remaining_balance = calculate_remaining_balance(original_amount, rate, term, months_passed)

        # Equity
        equity = current_value - remaining_balance
        equity_pct = (equity / current_value * 100) if current_value > 0 else 0
        ltv = (remaining_balance / current_value * 100) if current_value > 0 else 0

        # Original equity
        original_equity = original_value - original_amount
        original_ltv = (original_amount / original_value * 100) if original_value > 0 else 0

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "current_home_value": round(current_value, 2),
            "current_home_value_formatted": format_currency(current_value),
            "remaining_balance": round(remaining_balance, 2),
            "remaining_balance_formatted": format_currency(remaining_balance),
            "equity": round(equity, 2),
            "equity_formatted": format_currency(equity),
            "equity_percent": round(equity_pct, 1),
            "current_ltv": round(ltv, 1),
            "original_value": round(original_value, 2),
            "original_amount": round(original_amount, 2),
            "original_equity": round(original_equity, 2),
            "original_ltv": round(original_ltv, 1),
            "equity_gained": round(equity - original_equity, 2),
            "equity_gained_formatted": format_currency(equity - original_equity),
            "months_since_close": months_passed,
            "appreciation_rate": round(appreciation_rate * 100, 2),
            "interest_rate": round(rate * 100, 3),
        }

        return ToolResult.success(
            data=data,
            message=f"{client['client_name']}: {format_currency(equity)} equity ({equity_pct:.1f}%), LTV {ltv:.1f}%",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 4: Calculate Amortization
# =============================================================================

@mortgage_tool(
    name="calculate_amortization",
    description="Calculate remaining balance and amortization schedule for a MUM client",
    agent_roles=["home_valuation", "customer_intelligence"],
    risk_level="low",
    examples=[
        "Show the amortization for this client",
        "What's the remaining balance?",
    ],
)
def calculate_amortization(
    mum_client_id: Optional[int] = None,
    principal: Optional[float] = None,
    annual_rate: Optional[float] = None,
    term_months: Optional[int] = None,
    payments_made: Optional[int] = None,
    show_schedule: bool = False,
    schedule_months: int = 12,
) -> ToolResult:
    """Calculate amortization details."""
    try:
        if mum_client_id:
            client = execute_single("""
                SELECT id, client_name, original_loan_amount, interest_rate,
                       original_rate, term, first_payment_date, original_close_date
                FROM mum_clients WHERE id = :cid
            """, {"cid": mum_client_id})

            if not client:
                return ToolResult.no_data(f"MUM client {mum_client_id} not found")

            principal = float(client["original_loan_amount"] or 0)
            annual_rate = float(client["interest_rate"] or client["original_rate"] or 6.5) / 100
            term_months = client["term"] or 360

            first_pmt = client["first_payment_date"] or client["original_close_date"]
            if first_pmt:
                if isinstance(first_pmt, str):
                    first_pmt = datetime.fromisoformat(first_pmt)
                payments_made = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
            else:
                payments_made = payments_made or 0
        else:
            principal = principal or 0
            annual_rate = (annual_rate or 6.5) / 100
            term_months = term_months or 360
            payments_made = payments_made or 0

        if principal <= 0:
            return ToolResult.error("Loan amount must be > 0")

        monthly_payment = calculate_monthly_payment(principal, annual_rate, term_months)
        remaining_balance = calculate_remaining_balance(principal, annual_rate, term_months, payments_made)
        total_paid = monthly_payment * payments_made
        total_interest_paid = total_paid - (principal - remaining_balance)
        remaining_payments = term_months - payments_made

        data = {
            "principal": round(principal, 2),
            "annual_rate": round(annual_rate * 100, 3),
            "term_months": term_months,
            "payments_made": payments_made,
            "monthly_payment": round(monthly_payment, 2),
            "monthly_payment_formatted": format_currency(monthly_payment),
            "remaining_balance": round(remaining_balance, 2),
            "remaining_balance_formatted": format_currency(remaining_balance),
            "principal_paid": round(principal - remaining_balance, 2),
            "total_interest_paid": round(max(0, total_interest_paid), 2),
            "remaining_payments": max(0, remaining_payments),
            "pct_complete": round((payments_made / term_months) * 100, 1) if term_months > 0 else 0,
        }

        if mum_client_id:
            data["mum_client_id"] = mum_client_id
            data["client_name"] = client["client_name"]

        if show_schedule:
            schedule = calculate_amortization_schedule(
                principal, annual_rate, term_months,
                start_payment=payments_made + 1,
                count=schedule_months,
            )
            data["schedule"] = schedule

        return ToolResult.success(
            data=data,
            message=f"Balance: {format_currency(remaining_balance)} ({data['pct_complete']}% paid, {remaining_payments} payments left)",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 5: Get Maturity Date
# =============================================================================

@mortgage_tool(
    name="get_maturity_date",
    description="Get maturity date from first payment date + term for a MUM client",
    agent_roles=["home_valuation", "customer_intelligence"],
    risk_level="low",
    examples=[
        "When does this loan mature?",
        "What's the maturity date?",
    ],
)
def get_maturity_date(
    mum_client_id: int,
) -> ToolResult:
    """Get maturity date for a MUM client."""
    try:
        client = execute_single("""
            SELECT id, client_name, first_payment_date, original_close_date,
                   term, maturity_date
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        term = client["term"] or 360
        first_pmt = client["first_payment_date"] or client["original_close_date"]

        if not first_pmt:
            return ToolResult.error("No first payment date available for this client")

        if isinstance(first_pmt, str):
            first_pmt = datetime.fromisoformat(first_pmt)

        # Calculate maturity: first_payment + term months
        maturity = first_pmt + timedelta(days=term * 30.44)  # Average days per month

        now = datetime.now(timezone.utc)
        first_pmt_utc = first_pmt.replace(tzinfo=timezone.utc) if first_pmt.tzinfo is None else first_pmt
        maturity_utc = maturity.replace(tzinfo=timezone.utc) if maturity.tzinfo is None else maturity

        months_elapsed = max(0, (now - first_pmt_utc).days // 30)
        months_remaining = max(0, term - months_elapsed)
        pct_complete = round((months_elapsed / term) * 100, 1) if term > 0 else 0

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "first_payment_date": format_date(first_pmt),
            "maturity_date": format_date(maturity),
            "term_months": term,
            "term_years": round(term / 12, 1),
            "months_elapsed": months_elapsed,
            "months_remaining": months_remaining,
            "years_remaining": round(months_remaining / 12, 1),
            "pct_complete": pct_complete,
        }

        return ToolResult.success(
            data=data,
            message=f"{client['client_name']}: matures {format_date(maturity)} ({months_remaining} months / {round(months_remaining/12, 1)} years remaining, {pct_complete}% complete)",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 6: Batch Update Valuations
# =============================================================================

@mortgage_tool(
    name="batch_update_valuations",
    description="Batch recalculate home values, equity, LTV, and maturity dates for all MUM clients",
    agent_roles=["home_valuation"],
    risk_level="medium",
    examples=[
        "Update all MUM client valuations",
        "Recalculate property values",
    ],
)
def batch_update_valuations(
    limit: int = 500,
    dry_run: bool = False,
) -> ToolResult:
    """Batch recalculate valuations for all MUM clients."""
    try:
        clients = execute_query("""
            SELECT id, client_name, appraisal_value_at_closing, original_loan_amount,
                   interest_rate, original_rate, term, first_payment_date,
                   original_close_date, property_state, property_zip
            FROM mum_clients
            WHERE status = 'Active'
            ORDER BY id
            LIMIT :lim
        """, {"lim": limit})

        if not clients:
            return ToolResult.no_data("No active MUM clients found")

        updated = 0
        errors = 0
        results = []

        with get_db() as db:
            for client in clients:
                try:
                    original_value = float(client["appraisal_value_at_closing"] or 0)
                    original_amount = float(client["original_loan_amount"] or 0)
                    rate = float(client["interest_rate"] or client["original_rate"] or 6.5) / 100
                    term = client["term"] or 360
                    state = client["property_state"]

                    first_pmt = client["first_payment_date"] or client["original_close_date"]
                    if first_pmt:
                        if isinstance(first_pmt, str):
                            first_pmt = datetime.fromisoformat(first_pmt)
                        months_passed = max(0, (datetime.now(timezone.utc) - first_pmt.replace(tzinfo=timezone.utc)).days // 30)
                    else:
                        months_passed = 0

                    # Calculate values
                    appreciation_rate = get_appreciation_rate(state)
                    current_value = estimate_current_property_value(original_value, months_passed, appreciation_rate)
                    remaining_balance = calculate_remaining_balance(original_amount, rate, term, months_passed)
                    equity = current_value - remaining_balance
                    ltv = (remaining_balance / current_value * 100) if current_value > 0 else 0

                    # Maturity date
                    maturity = None
                    if first_pmt:
                        maturity = first_pmt + timedelta(days=term * 30.44)

                    if not dry_run:
                        from sqlalchemy import text
                        db.execute(text("""
                            UPDATE mum_clients SET
                                current_property_value = :val,
                                estimated_equity = :equity,
                                current_ltv = :ltv,
                                maturity_date = :maturity
                            WHERE id = :cid
                        """), {
                            "val": round(current_value, 2),
                            "equity": round(equity, 2),
                            "ltv": round(ltv, 1),
                            "maturity": maturity,
                            "cid": client["id"],
                        })

                    updated += 1
                    results.append({
                        "id": client["id"],
                        "name": client["client_name"],
                        "value": round(current_value, 2),
                        "equity": round(equity, 2),
                        "ltv": round(ltv, 1),
                    })
                except Exception as e:
                    logger.error(f"Error updating valuation for client {client['id']}: {e}")
                    errors += 1

            if not dry_run:
                db.commit()

        data = {
            "total_processed": len(clients),
            "updated": updated,
            "errors": errors,
            "dry_run": dry_run,
            "sample_results": results[:10],
        }

        return ToolResult.success(
            data=data,
            message=f"{'DRY RUN: ' if dry_run else ''}Updated {updated}/{len(clients)} MUM clients ({errors} errors)",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 7: Get Value History
# =============================================================================

@mortgage_tool(
    name="get_value_history",
    description="Get historical property value snapshots based on retroactive appreciation calculation",
    agent_roles=["home_valuation", "customer_intelligence"],
    risk_level="low",
    examples=[
        "Show the value history for this property",
        "How has the home value changed over time?",
    ],
)
def get_value_history(
    mum_client_id: int,
    interval_months: int = 6,
) -> ToolResult:
    """Get retroactive value history for a MUM client."""
    try:
        client = execute_single("""
            SELECT id, client_name, appraisal_value_at_closing,
                   original_close_date, property_state
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        original_value = float(client["appraisal_value_at_closing"] or 0)
        if original_value <= 0:
            return ToolResult.error("No original appraisal value available")

        close_date = client["original_close_date"]
        if not close_date:
            return ToolResult.error("No close date available")
        if isinstance(close_date, str):
            close_date = datetime.fromisoformat(close_date)

        state = client["property_state"]
        appreciation_rate = get_appreciation_rate(state)

        now = datetime.now(timezone.utc)
        total_months = max(0, (now - close_date.replace(tzinfo=timezone.utc)).days // 30)

        history = []
        for m in range(0, total_months + 1, interval_months):
            value = estimate_current_property_value(original_value, m, appreciation_rate)
            dt = close_date + timedelta(days=m * 30.44)
            history.append({
                "month": m,
                "date": format_date(dt),
                "value": round(value, 2),
                "value_formatted": format_currency(value),
                "appreciation_from_original": round(value - original_value, 2),
                "appreciation_pct": round(((value / original_value) - 1) * 100, 2) if original_value > 0 else 0,
            })

        # Add current if not already at end
        if total_months % interval_months != 0:
            current_value = estimate_current_property_value(original_value, total_months, appreciation_rate)
            history.append({
                "month": total_months,
                "date": format_date(now),
                "value": round(current_value, 2),
                "value_formatted": format_currency(current_value),
                "appreciation_from_original": round(current_value - original_value, 2),
                "appreciation_pct": round(((current_value / original_value) - 1) * 100, 2),
            })

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "original_value": round(original_value, 2),
            "state": state,
            "appreciation_rate": round(appreciation_rate * 100, 2),
            "total_months": total_months,
            "history": history,
        }

        return ToolResult.success(
            data=data,
            message=f"{len(history)} value snapshots over {total_months} months",
        )
    except Exception as e:
        return ToolResult.error(str(e))


# =============================================================================
# Tool 8: Compare Market Appreciation
# =============================================================================

@mortgage_tool(
    name="compare_market_appreciation",
    description="Compare a client's property appreciation against state and national averages",
    agent_roles=["home_valuation", "customer_intelligence"],
    risk_level="low",
    examples=[
        "How does this client's appreciation compare to the market?",
        "Compare appreciation rates",
    ],
)
def compare_market_appreciation(
    mum_client_id: int,
) -> ToolResult:
    """Compare client's appreciation to benchmarks."""
    try:
        client = execute_single("""
            SELECT id, client_name, appraisal_value_at_closing,
                   current_property_value, original_close_date,
                   property_state
            FROM mum_clients WHERE id = :cid
        """, {"cid": mum_client_id})

        if not client:
            return ToolResult.no_data(f"MUM client {mum_client_id} not found")

        original_value = float(client["appraisal_value_at_closing"] or 0)
        if original_value <= 0:
            return ToolResult.error("No original appraisal value available")

        close_date = client["original_close_date"]
        if not close_date:
            return ToolResult.error("No close date available")
        if isinstance(close_date, str):
            close_date = datetime.fromisoformat(close_date)

        months = max(1, (datetime.now(timezone.utc) - close_date.replace(tzinfo=timezone.utc)).days // 30)
        state = client["property_state"]

        state_rate = get_appreciation_rate(state) if state else NATIONAL_APPRECIATION_RATE
        national_rate = NATIONAL_APPRECIATION_RATE

        # Compute values at each rate
        state_value = estimate_current_property_value(original_value, months, state_rate)
        national_value = estimate_current_property_value(original_value, months, national_rate)

        # Actual current value (from DB or state-calculated)
        actual_value = float(client["current_property_value"] or state_value)

        data = {
            "mum_client_id": mum_client_id,
            "client_name": client["client_name"],
            "state": state,
            "months_since_close": months,
            "original_value": round(original_value, 2),
            "comparison": {
                "actual": {
                    "value": round(actual_value, 2),
                    "value_formatted": format_currency(actual_value),
                    "total_pct": round(((actual_value / original_value) - 1) * 100, 2),
                },
                "state_average": {
                    "rate": round(state_rate * 100, 2),
                    "value": round(state_value, 2),
                    "value_formatted": format_currency(state_value),
                    "total_pct": round(((state_value / original_value) - 1) * 100, 2),
                },
                "national_average": {
                    "rate": round(national_rate * 100, 2),
                    "value": round(national_value, 2),
                    "value_formatted": format_currency(national_value),
                    "total_pct": round(((national_value / original_value) - 1) * 100, 2),
                },
            },
            "vs_state": round(actual_value - state_value, 2),
            "vs_national": round(actual_value - national_value, 2),
        }

        return ToolResult.success(
            data=data,
            message=f"{client['client_name']}: {format_currency(actual_value)} vs state avg {format_currency(state_value)}",
        )
    except Exception as e:
        return ToolResult.error(str(e))
