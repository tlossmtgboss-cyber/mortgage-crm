"""
MUM (Mortgages Under Management) API Routes

API routes for managing MUM (Mortgages Under Management) portfolio -
tracking post-close clients, refinance opportunities, and portfolio metrics.

Endpoints:
- POST  /api/v1/mum/setup        - One-time setup to create MUM tables and seed data
- GET   /api/v1/mum/clients      - Get all MUM clients for portfolio view
- GET   /api/v1/mum/metrics      - Get aggregated MUM portfolio metrics
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from agents.utils.financial_calcs import (
    calculate_remaining_balance,
    estimate_current_property_value,
    get_appreciation_rate,
)

logger = logging.getLogger(__name__)


# ============================================================================
# RUNTIME IMPORTS TO AVOID CIRCULAR DEPENDENCIES
# ============================================================================

def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'MUMClient': main.MUMClient,
        'Loan': main.Loan,
        'LoanStage': main.LoanStage,
    }


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(prefix="/api/v1/mum", tags=["MUM (Mortgages Under Management)"])


# ============================================================================
# MUM API ENDPOINTS
# ============================================================================

@router.post("/setup")
async def setup_mum_database(
    migration_key: str = "",
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Create MUM tables and seed 100 clients (ONE-TIME SETUP)"""
    if migration_key != "setup-mum-database-2025":
        raise HTTPException(status_code=403, detail="Invalid migration key")

    try:
        from migrations.create_mum_tables import upgrade as create_tables

        # Create tables
        create_tables()
        logger.info("MUM tables created")

        # Import and run seed script
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

        from seed_100_mum_clients import generate_mum_clients
        generate_mum_clients()
        logger.info("100 MUM clients generated")

        return {
            "success": True,
            "message": "MUM database setup completed",
            "tables_created": ["mum_clients", "mum_transactions"],
            "clients_generated": 100
        }

    except Exception as e:
        logger.error(f"MUM setup error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Setup failed")


@router.get("/clients")
async def get_mum_clients_portfolio(
    status: str = None,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get all MUM clients for portfolio view - includes both MUMClient table AND funded loans"""
    try:
        models = get_models()
        MUMClient = models['MUMClient']
        Loan = models['Loan']
        LoanStage = models['LoanStage']

        client_list = []
        refinance_count = 0
        seen_loan_numbers = set()  # Track loan numbers to avoid duplicates

        # 1. First, get MUM clients from the mum_clients table
        query = db.query(MUMClient).filter(MUMClient.user_id == current_user.id)
        if status and status != "all":
            query = query.filter(MUMClient.status == status)

        mum_clients = query.order_by(MUMClient.created_at.desc()).all()

        # Batch lookup loan details (loan_type, occupancy_type) and lead details (first_time_buyer)
        loan_details_map = {}
        loan_numbers = [c.loan_number for c in mum_clients if c.loan_number]
        if loan_numbers:
            try:
                loan_rows = db.execute(text("""
                    SELECT loan_number, loan_type, occupancy_type, program
                    FROM loans WHERE loan_number = ANY(:lns)
                """), {"lns": loan_numbers}).fetchall()
                for row in loan_rows:
                    loan_details_map[row[0]] = {
                        "loan_type": row[1], "occupancy_type": row[2], "program": row[3]
                    }
            except Exception as e:
                logger.warning(f"Failed to batch lookup loan details for MUM: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

        lead_details_map = {}
        if loan_numbers:
            try:
                lead_rows = db.execute(text("""
                    SELECT loan_number, first_time_buyer, loan_type, occupancy_type
                    FROM leads WHERE loan_number = ANY(:lns) AND loan_number IS NOT NULL
                """), {"lns": loan_numbers}).fetchall()
                for row in lead_rows:
                    lead_details_map[row[0]] = {
                        "first_time_buyer": row[1], "loan_type": row[2], "occupancy_type": row[3]
                    }
            except Exception as e:
                logger.warning(f"Failed to batch lookup lead details for MUM: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

        for client in mum_clients:
            # Track this loan number
            if client.loan_number:
                seen_loan_numbers.add(client.loan_number)

            # Calculate days since funding
            days_since = 0
            if client.original_close_date:
                close_dt = client.original_close_date
                if hasattr(close_dt, 'tzinfo') and close_dt.tzinfo is None:
                    close_dt = close_dt.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - close_dt).days

            # Calculate estimated current balance using proper amortization
            original_balance = float(client.loan_balance or client.original_loan_amount or 0)
            months_passed = days_since // 30
            loan_rate = float(client.interest_rate or client.original_rate or 6.5) / 100
            loan_term = getattr(client, 'term', None) or 360
            current_balance = calculate_remaining_balance(original_balance, loan_rate, loan_term, months_passed)

            # Estimate property value using state-level compound appreciation
            original_value = float(client.appraisal_value_at_closing or original_balance * 1.25)
            client_state = getattr(client, 'property_state', None)
            current_value = estimate_current_property_value(original_value, months_passed, state=client_state)

            # Calculate equity
            equity_amount = current_value - current_balance
            equity_pct = (equity_amount / current_value * 100) if current_value > 0 else 0

            # Check refinance opportunity
            is_refinance_opportunity = client.refinance_opportunity or False
            if is_refinance_opportunity:
                refinance_count += 1

            # Resolve client name — detect Salesforce IDs stored as names
            display_name = client.client_name or getattr(client, 'name', None) or ""
            _is_sf_id = (
                display_name
                and len(display_name) >= 15
                and len(display_name) <= 18
                and " " not in display_name
                and display_name[:3].isalnum()
            )
            if not display_name or _is_sf_id:
                # Try to resolve from associated lead by email
                try:
                    _lead = db.execute(text(
                        "SELECT first_name, last_name FROM leads "
                        "WHERE LOWER(email) = LOWER(:email) LIMIT 1"
                    ), {"email": client.email}).fetchone()
                    if _lead and (_lead[0] or _lead[1]):
                        resolved = f"{_lead[0] or ''} {_lead[1] or ''}".strip()
                        display_name = resolved
                        # Also fix the record in-place for future loads
                        try:
                            client.client_name = resolved
                            db.commit()
                        except Exception as e:
                            db.rollback()
                            logger.warning(f"Failed to update client_name in get_mum_clients_portfolio: {e}")
                except Exception as e:
                    logger.warning(f"Failed to resolve lead name in get_mum_clients_portfolio: {e}")
            if not display_name or _is_sf_id:
                display_name = f"Client - {client.loan_number}"

            client_data = {
                "id": client.id,
                "source": "mum_client",  # Mark source for debugging
                "client_name": display_name,
                "email": client.email,
                "phone": client.phone,
                "loan_number": client.loan_number,
                "servicing_loan_number": client.loan_number,
                "original_loan_amount": original_balance,
                "current_loan_amount": round(current_balance, 2),
                "loan_balance": round(current_balance, 2),
                "interest_rate": float(client.original_rate or client.interest_rate or 0),
                "original_rate": float(client.original_rate or 0),
                "current_rate": float(client.current_rate or client.original_rate or 0),
                "appraisal_value_at_closing": original_value,
                "current_property_value": round(current_value, 2),
                "closing_date": client.original_close_date.isoformat() if client.original_close_date else None,
                "original_close_date": client.original_close_date.isoformat() if client.original_close_date else None,
                "days_since_funding": days_since,
                "ltv": round((current_balance / current_value * 100) if current_value > 0 else 0, 2),
                "equity_amount": round(equity_amount, 2),
                "equity_percentage": round(equity_pct, 2),
                "refinance_opportunity": is_refinance_opportunity,
                "estimated_savings": float(client.estimated_savings or 0),
                "engagement_score": client.engagement_score or 0,
                "referrals_sent": client.referrals_sent or 0,
                "status": client.status or "Active",
                "last_contact": client.last_contact.isoformat() if client.last_contact else None,
                "notes": client.notes,
                "loan_officer": client.loan_officer,
                "processor": client.processor,
                "loan_type": (loan_details_map.get(client.loan_number, {}).get("loan_type")
                              or lead_details_map.get(client.loan_number, {}).get("loan_type")),
                "program": loan_details_map.get(client.loan_number, {}).get("program"),
                "occupancy_type": (loan_details_map.get(client.loan_number, {}).get("occupancy_type")
                                   or lead_details_map.get(client.loan_number, {}).get("occupancy_type")),
                "first_time_buyer": lead_details_map.get(client.loan_number, {}).get("first_time_buyer", False),
            }

            client_list.append(client_data)

        # 2. Now get funded loans from the loans table that aren't already in MUM clients
        funded_loans = db.query(Loan).filter(
            Loan.loan_officer_id == current_user.id,
            Loan.stage == LoanStage.FUNDED
        ).all()

        for loan in funded_loans:
            # Skip if this loan is already in MUM clients
            if loan.loan_number and loan.loan_number in seen_loan_numbers:
                continue

            # Calculate days since funding
            days_since = 0
            close_dt = loan.funded_date or loan.closing_date
            if close_dt:
                if hasattr(close_dt, 'tzinfo') and close_dt.tzinfo is None:
                    close_dt = close_dt.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - close_dt).days

            # Get loan amount — proper amortization
            original_balance = float(loan.amount or 0)
            months_passed = max(0, days_since // 30)
            loan_rate_raw = float(loan.rate or 6.5)
            loan_term = getattr(loan, 'term', None) or 360
            loan_state = getattr(loan, 'property_state', None)
            current_balance = calculate_remaining_balance(original_balance, loan_rate_raw / 100, loan_term, months_passed)

            # Estimate property value — compound appreciation
            original_value = float(loan.purchase_price or loan.appraisal_value or original_balance * 1.25)
            current_value = estimate_current_property_value(original_value, months_passed, state=loan_state)

            # Calculate equity
            equity_amount = current_value - current_balance
            equity_pct = (equity_amount / current_value * 100) if current_value > 0 else 0

            # Check refinance opportunity (if rate is above 6.5%, consider it a refi opportunity)
            loan_rate = float(loan.rate or 0)
            is_refinance_opportunity = loan_rate >= 6.5
            if is_refinance_opportunity:
                refinance_count += 1

            # Format closing date
            closing_date_str = None
            if close_dt:
                closing_date_str = close_dt.isoformat() if hasattr(close_dt, 'isoformat') else str(close_dt)

            client_data = {
                "id": f"loan_{loan.id}",  # Prefix with loan_ to distinguish from MUM client IDs
                "source": "funded_loan",  # Mark source for debugging
                "client_name": loan.borrower_name,
                "email": loan.borrower_email,
                "phone": loan.borrower_phone,
                "loan_number": loan.loan_number,
                "servicing_loan_number": loan.loan_number,
                "original_loan_amount": original_balance,
                "current_loan_amount": round(current_balance, 2),
                "loan_balance": round(current_balance, 2),
                "interest_rate": loan_rate,
                "original_rate": loan_rate,
                "current_rate": loan_rate,
                "appraisal_value_at_closing": original_value,
                "current_property_value": round(current_value, 2),
                "closing_date": closing_date_str,
                "original_close_date": closing_date_str,
                "days_since_funding": days_since,
                "ltv": round((current_balance / current_value * 100) if current_value > 0 else 0, 2),
                "equity_amount": round(equity_amount, 2),
                "equity_percentage": round(equity_pct, 2),
                "refinance_opportunity": is_refinance_opportunity,
                "estimated_savings": 0,  # Would need rate comparison to calculate
                "engagement_score": 50,  # Default score for funded loans
                "referrals_sent": 0,
                "status": "Active",
                "last_contact": None,
                "notes": None,
                "loan_officer": loan.loan_officer_name,
                "processor": loan.processor,
                "property_address": loan.property_address,
                "loan_type": loan.loan_type,
                "occupancy_type": getattr(loan, 'occupancy_type', None),
                "program": loan.program,
                "first_time_buyer": False,  # Not stored on loan; lead-level data
            }

            client_list.append(client_data)

        # Sort by closing date (most recent first)
        client_list.sort(key=lambda x: x.get("closing_date") or "", reverse=True)

        return {
            "clients": client_list,
            "count": len(client_list),
            "refinance_opportunities": refinance_count
        }

    except Exception as e:
        logger.error(f"Get MUM clients error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics")
async def get_mum_metrics(
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get aggregated MUM portfolio metrics - includes both MUM clients and funded loans"""
    try:
        models = get_models()
        MUMClient = models['MUMClient']
        Loan = models['Loan']
        LoanStage = models['LoanStage']

        # Calculate metrics
        total_upb = 0
        total_revenue = 0
        total_equity = 0
        ltv_sum = 0
        client_count = 0

        refinance_opps = 0
        heloc_opps = 0
        rate_rebound_opps = 0
        seen_loan_numbers = set()

        # 1. Process MUM clients scoped to user's organization
        try:
            if hasattr(current_user, 'organization_id') and current_user.organization_id:
                mum_clients = db.query(MUMClient).filter(
                    MUMClient.organization_id == current_user.organization_id,
                    MUMClient.status == 'active'
                ).all()
            else:
                # No organization_id — return empty to prevent cross-tenant leakage
                logger.warning(f"User {current_user.id} has no organization_id, returning empty MUM metrics")
                mum_clients = []
        except Exception as e:
            logger.warning(f"MUM client query failed, returning empty: {e}")
            mum_clients = []

        for client in mum_clients:
            try:
                if hasattr(client, 'loan_number') and client.loan_number:
                    seen_loan_numbers.add(client.loan_number)

                # Calculate days since funding
                days_since = 0
                close_dt = getattr(client, 'original_close_date', None) or getattr(client, 'close_date', None)
                if close_dt:
                    if hasattr(close_dt, 'tzinfo') and close_dt.tzinfo is None:
                        close_dt = close_dt.replace(tzinfo=timezone.utc)
                    days_since = (datetime.now(timezone.utc) - close_dt).days

                # Get balance with multiple fallbacks
                original_balance = float(
                    getattr(client, 'loan_balance', 0) or
                    getattr(client, 'original_loan_amount', 0) or
                    getattr(client, 'current_loan_amount', 0) or 0
                )
                months_passed = max(0, days_since // 30)
                m_rate = float(getattr(client, 'interest_rate', 0) or getattr(client, 'original_rate', 0) or 6.5) / 100
                m_term = getattr(client, 'term', None) or 360
                current_balance = calculate_remaining_balance(original_balance, m_rate, m_term, months_passed)

                # Get property value with fallbacks — compound appreciation
                original_value = float(
                    getattr(client, 'appraisal_value_at_closing', 0) or
                    getattr(client, 'current_property_value', 0) or
                    original_balance * 1.25
                )
                m_state = getattr(client, 'property_state', None)
                current_value = estimate_current_property_value(original_value, months_passed, state=m_state) if original_value > 0 else 0

                total_upb += current_balance
                total_revenue += current_balance * 0.0025  # Servicing revenue
                equity_amount = current_value - current_balance
                total_equity += equity_amount
                ltv_sum += (current_balance / current_value) if current_value > 0 else 0
                client_count += 1

                if getattr(client, 'refinance_opportunity', False):
                    refinance_opps += 1
                if getattr(client, 'heloc_opportunity', False):
                    heloc_opps += 1
                if getattr(client, 'rate_rebound_opportunity', False):
                    rate_rebound_opps += 1
            except Exception as client_error:
                logger.warning(f"Error processing MUM client {getattr(client, 'id', 'unknown')}: {client_error}")
                continue

        # 2. Process funded loans not already in MUM clients
        try:
            # Try multiple approaches to find funded loans
            funded_loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage == LoanStage.FUNDED
            ).all()
        except Exception as e:
            logger.warning(f"Funded loans query with enum failed, trying text match: {e}")
            try:
                # Fallback: try string comparison or funded_date not null
                from sqlalchemy import or_, text
                funded_loans = db.query(Loan).filter(
                    Loan.loan_officer_id == current_user.id,
                    or_(
                        Loan.funded_date.isnot(None),
                        text("LOWER(CAST(stage AS TEXT)) LIKE '%fund%'")
                    )
                ).all()
            except Exception as e2:
                logger.warning(f"Fallback funded loans query also failed: {e2}")
                funded_loans = []

        for loan in funded_loans:
            if loan.loan_number and loan.loan_number in seen_loan_numbers:
                continue

            days_since = 0
            close_dt = loan.funded_date or loan.closing_date
            if close_dt:
                if hasattr(close_dt, 'tzinfo') and close_dt.tzinfo is None:
                    close_dt = close_dt.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - close_dt).days

            original_balance = float(loan.amount or 0)
            months_passed = max(0, days_since // 30)
            fl_rate = float(loan.rate or 6.5) / 100
            fl_term = getattr(loan, 'term', None) or 360
            fl_state = getattr(loan, 'property_state', None)
            current_balance = calculate_remaining_balance(original_balance, fl_rate, fl_term, months_passed)

            original_value = float(loan.purchase_price or loan.appraisal_value or original_balance * 1.25)
            current_value = estimate_current_property_value(original_value, months_passed, state=fl_state)

            total_upb += current_balance
            total_revenue += current_balance * 0.0025
            equity_amount = current_value - current_balance
            total_equity += equity_amount
            ltv_sum += (current_balance / current_value) if current_value > 0 else 0
            client_count += 1

            # Check refinance opportunity
            loan_rate = float(loan.rate or 0)
            if loan_rate >= 6.5:
                refinance_opps += 1
                rate_rebound_opps += 1

        if client_count == 0:
            return {
                "total_upb": 0,
                "client_count": 0,
                "net_growth_mom": 0,
                "portfolio_yield": 0,
                "avg_client_ltv": 0,
                "avg_annual_revenue_per_client": 0,
                "total_annual_revenue": 0,
                "refinance_opportunities": 0,
                "heloc_opportunities": 0,
                "rate_rebound_opportunities": 0,
                "loans_added_30d": 0,
                "loans_lost_30d": 0
            }

        # Calculate month-over-month growth from funded loans in last 30 days
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        try:
            recent_funded = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage == LoanStage.FUNDED,
                Loan.funded_date >= thirty_days_ago
            ).all()
        except Exception as e:
            logger.warning(f"Recent funded query failed: {e}")
            recent_funded = []
        added_upb = sum([float(getattr(l, 'amount', 0) or 0) for l in recent_funded])

        # Calculate final metrics
        portfolio_yield = (total_revenue / total_upb * 100) if total_upb > 0 else 0
        avg_ltv = (ltv_sum / client_count) if client_count > 0 else 0
        avg_client_value = total_revenue / client_count if client_count > 0 else 0

        return {
            "total_upb": round(total_upb, 2),
            "client_count": client_count,
            "net_growth_mom": round(added_upb, 2),
            "portfolio_yield": round(portfolio_yield, 4),
            "avg_client_ltv": round(avg_ltv, 4),
            "avg_annual_revenue_per_client": round(avg_client_value, 2),
            "total_annual_revenue": round(total_revenue, 2),
            "refinance_opportunities": refinance_opps,
            "heloc_opportunities": heloc_opps,
            "rate_rebound_opportunities": rate_rebound_opps,
            "loans_added_30d": len(recent_funded),
            "loans_lost_30d": 0  # Would need to track separately
        }

    except Exception as e:
        logger.error(f"Get MUM metrics error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")
