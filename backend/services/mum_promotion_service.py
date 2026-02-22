"""
MUM Promotion Service
Handles automatic promotion of funded loans to MUM (Mortgages Under Management).

Extracted from mum_activity_routes.py copy_loan_to_mum_client() so it can be called
from both the manual convert endpoint AND the Salesforce sync hooks.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _get_fresh_session():
    """Create a fresh, independent DB session for MUM promotion.

    This isolates MUM promotion from any upstream transaction poisoning
    (e.g. failed SLA/reconciliation commits on the caller's session).
    """
    from db import SessionLocal
    return SessionLocal()


def maybe_promote_loan_to_mum(
    db: Session,
    loan_id: int,
    user_id: int,
) -> Optional[int]:
    """
    Check if a loan is eligible for MUM promotion and create a MUMClient if so.

    Eligibility: loan has funded_date or closing_date set, OR stage is 'FUNDED'.
    Idempotent: skips if a MUMClient with matching loan_number already exists.

    Uses a fresh independent DB session to avoid transaction poisoning from
    upstream operations (SLA triggers, reconciliation) that may have left the
    caller's session in a failed state.

    Args:
        db: Caller's database session (NOT used — only kept for signature compat)
        loan_id: The loan ID to check
        user_id: Owner user ID for the new MUMClient

    Returns:
        The MUMClient ID if created, or existing MUMClient ID if already exists, or None on failure.
    """
    from database.models import Loan, MUMClient, Task

    # Use a fresh session to avoid inheriting poisoned transaction state
    # from upstream SLA/reconciliation operations on the caller's session.
    fresh_db = _get_fresh_session()
    try:
        # Verify connection is clean before doing anything
        try:
            fresh_db.execute(text("SELECT 1"))
            logger.debug(f"MUM promotion loan {loan_id}: fresh session health check OK")
        except Exception as e:
            logger.warning(f"MUM promotion loan {loan_id}: fresh session poisoned on checkout, resetting: {e}")
            fresh_db.rollback()

        # Use raw SQL for loan lookup to avoid ORM column mismatches poisoning the session
        loan_row = fresh_db.execute(text("""
            SELECT id, stage, funded_date, closing_date, loan_number,
                   loan_officer_id, organization_id, amount, rate,
                   appraisal_value, borrower_name, borrower_email, borrower_phone,
                   first_payment_date, term, property_state, property_zip,
                   program, loan_officer_name, loan_officer_email,
                   processor, processor_email, underwriter, underwriter_email,
                   closer, closer_email
            FROM loans WHERE id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

        if not loan_row:
            logger.warning(f"MUM promotion: Loan {loan_id} not found")
            return None

        # Map row to dict for easier access
        cols = ['id', 'stage', 'funded_date', 'closing_date', 'loan_number',
                'loan_officer_id', 'organization_id', 'amount', 'rate',
                'appraisal_value', 'borrower_name', 'borrower_email', 'borrower_phone',
                'first_payment_date', 'term', 'property_state', 'property_zip',
                'program', 'loan_officer_name', 'loan_officer_email',
                'processor', 'processor_email', 'underwriter', 'underwriter_email',
                'closer', 'closer_email']
        loan = dict(zip(cols, loan_row))

        # Check eligibility: funded_date, closing_date, or stage == FUNDED
        stage_str = str(loan['stage']).upper() if loan['stage'] else ""
        is_funded = bool(loan['funded_date']) or bool(loan['closing_date']) or stage_str == "FUNDED"
        if not is_funded:
            return None

        # Idempotent check: use raw SQL to avoid ORM SELECT issues
        if loan['loan_number']:
            try:
                existing_row = fresh_db.execute(text("""
                    SELECT id FROM mum_clients WHERE loan_number = :ln LIMIT 1
                """), {"ln": loan['loan_number']}).fetchone()
                if existing_row:
                    logger.info(f"MUM client already exists for loan {loan['loan_number']} (mum_id={existing_row[0]})")
                    return existing_row[0]
            except Exception as e:
                logger.warning(f"MUM idempotent check failed for loan {loan_id}: {e}")
                try:
                    fresh_db.rollback()
                except Exception as e2:
                    logger.exception(f"Failed to rollback after MUM idempotent check failure for loan {loan_id}: {e2}")

        # Determine the owner: use the loan officer, fall back to the triggering user
        owner_user_id = loan['loan_officer_id'] or user_id
        org_id = loan['organization_id']

        # Determine funded date
        funded_date = loan['funded_date'] or loan['closing_date'] or datetime.now(timezone.utc)
        if hasattr(funded_date, 'tzinfo') and funded_date.tzinfo is None:
            funded_date = funded_date.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - funded_date).days

        # Get loan amount
        loan_amount = loan['amount'] or 0.0

        # Get interest rate
        loan_rate = loan['rate'] or 0.0
        if not loan_rate:
            try:
                row = fresh_db.execute(
                    text("SELECT interest_rate FROM loans WHERE id = :lid"),
                    {"lid": loan_id}
                ).fetchone()
                if row and row[0]:
                    loan_rate = float(row[0])
            except Exception as e:
                logger.exception(f"Failed to fetch interest_rate for loan {loan_id}: {e}")
                try:
                    fresh_db.rollback()
                except Exception as e2:
                    logger.exception(f"Failed to rollback after interest_rate fetch failure for loan {loan_id}: {e2}")

        # Estimate property value (80% LTV assumption)
        estimated_property_value = loan['appraisal_value'] or (loan_amount * 1.25 if loan_amount else 0.0)

        # Build client name — resolve Salesforce IDs to real names
        client_name = loan['borrower_name'] or ""
        _looks_like_sf_id = (
            client_name
            and len(client_name) >= 15
            and len(client_name) <= 18
            and client_name[:3].isalnum()
            and " " not in client_name
        )
        if not client_name or _looks_like_sf_id:
            try:
                lead_row = fresh_db.execute(
                    text("""
                        SELECT l.first_name, l.last_name
                        FROM leads l
                        JOIN loans lo ON lo.borrower_email = l.email
                        WHERE lo.id = :loan_id
                        LIMIT 1
                    """),
                    {"loan_id": loan_id}
                ).fetchone()
                if lead_row and (lead_row[0] or lead_row[1]):
                    client_name = f"{lead_row[0] or ''} {lead_row[1] or ''}".strip()
            except Exception as e:
                logger.exception(f"Failed to resolve client name from leads for loan {loan_id}: {e}")
                try:
                    fresh_db.rollback()
                except Exception as e2:
                    logger.exception(f"Failed to rollback after client name resolution failure for loan {loan_id}: {e2}")
        if not client_name or _looks_like_sf_id:
            client_name = f"Client - {loan['loan_number']}"

        # First payment date
        first_payment = loan['first_payment_date'] or (funded_date + timedelta(days=45))
        if hasattr(first_payment, 'tzinfo') and first_payment.tzinfo is None:
            first_payment = first_payment.replace(tzinfo=timezone.utc)

        # Copy term and property location from loan
        loan_term = loan['term'] or 360
        prop_state = loan['property_state']
        prop_zip = loan['property_zip']

        # Compute maturity date from first payment + term
        maturity = first_payment + timedelta(days=loan_term * 30)  # Approximate

        # INSERT using raw SQL to avoid ORM column mismatch issues
        logger.info(f"MUM promotion: inserting MUM client for loan {loan_id} ({client_name})")
        result = fresh_db.execute(text("""
            INSERT INTO mum_clients (
                organization_id, client_name, email, phone, loan_number,
                original_close_date, closing_date, first_payment_date,
                days_since_funding, original_rate, current_rate, interest_rate,
                original_loan_amount, current_loan_amount,
                appraisal_value_at_closing, current_property_value,
                loan_balance, refinance_opportunity, engagement_score,
                status, notes,
                loan_officer, loan_officer_email,
                processor, processor_email,
                underwriter, underwriter_email,
                closer, closer_email,
                user_id, term, maturity_date,
                property_state, property_zip
            ) VALUES (
                :org_id, :client_name, :email, :phone, :loan_number,
                :original_close_date, :closing_date, :first_payment_date,
                :days_since_funding, :original_rate, :current_rate, :interest_rate,
                :original_loan_amount, :current_loan_amount,
                :appraisal_value_at_closing, :current_property_value,
                :loan_balance, :refinance_opportunity, :engagement_score,
                :status, :notes,
                :loan_officer, :loan_officer_email,
                :processor, :processor_email,
                :underwriter, :underwriter_email,
                :closer, :closer_email,
                :user_id, :term, :maturity_date,
                :property_state, :property_zip
            ) RETURNING id
        """), {
            "org_id": org_id,
            "client_name": client_name,
            "email": loan['borrower_email'],
            "phone": loan['borrower_phone'],
            "loan_number": loan['loan_number'],
            "original_close_date": funded_date,
            "closing_date": funded_date,
            "first_payment_date": first_payment,
            "days_since_funding": days_since,
            "original_rate": loan_rate,
            "current_rate": loan_rate,
            "interest_rate": loan_rate,
            "original_loan_amount": loan_amount,
            "current_loan_amount": loan_amount,
            "appraisal_value_at_closing": estimated_property_value or 0.0,
            "current_property_value": estimated_property_value or 0.0,
            "loan_balance": loan_amount,
            "refinance_opportunity": False,
            "engagement_score": 100,
            "status": "Active",
            "notes": f"Auto-created from funded loan on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. Program: {loan['program'] or 'N/A'}",
            "loan_officer": loan['loan_officer_name'],
            "loan_officer_email": loan['loan_officer_email'],
            "processor": loan['processor'],
            "processor_email": loan['processor_email'],
            "underwriter": loan['underwriter'],
            "underwriter_email": loan['underwriter_email'],
            "closer": loan['closer'],
            "closer_email": loan['closer_email'],
            "user_id": owner_user_id,
            "term": loan_term,
            "maturity_date": maturity,
            "property_state": prop_state,
            "property_zip": prop_zip,
        })

        mum_id_row = result.fetchone()
        mum_client_id = mum_id_row[0] if mum_id_row else None

        if not mum_client_id:
            logger.error(f"MUM INSERT returned no ID for loan {loan_id}")
            fresh_db.rollback()
            return None

        logger.info(
            f"Created MUM client {mum_client_id} from funded loan {loan['loan_number']} "
            f"({client_name})"
        )

        # Create post-close welcome task
        fresh_db.execute(text("""
            INSERT INTO tasks (title, description, priority, loan_id, owner_id,
                             related_contact_name, related_type, due_date, status)
            VALUES (:title, :desc, 'high', :loan_id, :owner_id,
                    :contact, 'post_close', :due_date, 'pending')
        """), {
            "title": f"Post-Close Welcome Call - {client_name}",
            "desc": f"Congratulations! {client_name}'s loan has funded!\n\nAction items:\n1. Make welcome call\n2. Set up AMR reminder\n3. Request reviews\n4. Ask for referrals\n5. Add to retention campaigns\n\nLoan #: {loan['loan_number']}\nAmount: ${loan_amount:,.2f}\nRate: {loan_rate}%",
            "loan_id": loan_id,
            "owner_id": owner_user_id,
            "contact": client_name,
            "due_date": datetime.now(timezone.utc) + timedelta(days=1),
        })

        # Create AMR reminder task for 11 months from now
        fresh_db.execute(text("""
            INSERT INTO tasks (title, description, priority, loan_id, owner_id,
                             related_contact_name, related_type, due_date, status)
            VALUES (:title, :desc, 'medium', :loan_id, :owner_id,
                    :contact, 'amr', :due_date, 'pending')
        """), {
            "title": f"Annual Mortgage Review Due - {client_name}",
            "desc": f"AMR coming up for {client_name}.\n\nReview: rates vs {loan_rate}%, refi opps, home value, life changes.\n\nLoan #: {loan['loan_number']}\nOriginal: ${loan_amount:,.2f} at {loan_rate}%",
            "loan_id": loan_id,
            "owner_id": owner_user_id,
            "contact": client_name,
            "due_date": datetime.now(timezone.utc) + timedelta(days=335),
        })

        logger.info(f"Created post-close tasks for MUM client {mum_client_id}")

        fresh_db.commit()
        return mum_client_id

    except Exception as e:
        logger.error(f"Error creating MUM client from loan {loan_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            fresh_db.rollback()
        except Exception as e2:
            logger.exception(f"Failed to rollback after MUM promotion failure for loan {loan_id}: {e2}")
        return None
    finally:
        try:
            fresh_db.close()
        except Exception as e:
            logger.exception(f"Failed to close fresh DB session after MUM promotion for loan {loan_id}: {e}")


def maybe_promote_loan_to_mum_by_raw_data(
    db: Session,
    loan_id: int,
    user_id: int,
    loan_data: dict,
    old_data: dict = None,
) -> Optional[int]:
    """
    Check if a loan should be promoted to MUM based on raw sync data (no ORM load).

    This is the lightweight check used in sync hooks to avoid loading the full ORM
    object unless promotion is actually needed.

    Args:
        db: Active database session
        loan_id: The loan ID
        user_id: Owner user ID
        loan_data: New data dict from sync (may contain funded_date, closing_date, stage)
        old_data: Previous data dict for comparison (optional)

    Returns:
        MUMClient ID if created, or None
    """
    # Check if this sync made the loan "funded"
    new_stage = str(loan_data.get("stage", "")).upper()
    old_stage = str((old_data or {}).get("stage", "")).upper() if old_data else ""

    has_funded_date = loan_data.get("funded_date") is not None
    has_closing_date = loan_data.get("closing_date") is not None
    stage_became_funded = new_stage == "FUNDED" and old_stage != "FUNDED"

    # Only proceed if funded_date/closing_date was just set, or stage just became FUNDED
    newly_funded = False
    if has_funded_date and (old_data is None or old_data.get("funded_date") is None):
        newly_funded = True
    if has_closing_date and (old_data is None or old_data.get("closing_date") is None):
        newly_funded = True
    if stage_became_funded:
        newly_funded = True

    if not newly_funded:
        return None

    logger.info(f"Loan {loan_id} appears newly funded — attempting MUM promotion")
    return maybe_promote_loan_to_mum(db, loan_id, user_id)
