"""
Loans CRUD Routes
=================
Handles Create, Read, Update, Delete operations for Loan entities.
Used by the frontend for lead-to-loan conversion (Disclosed/Funded stages)
and loan pipeline management.

Endpoints:
- POST   /api/v1/loans/           - Create a new loan
- GET    /api/v1/loans/           - Get all loans with optional filtering
- GET    /api/v1/loans/{loan_id}  - Get a single loan by ID
- PATCH  /api/v1/loans/{loan_id}  - Update a loan
- DELETE /api/v1/loans/{loan_id}  - Delete a loan
- POST   /api/v1/loans/bulk-delete - Bulk delete loans
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
import logging
import traceback

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/loans", tags=["Loans CRUD"])


# ============================================================================
# Lazy imports to avoid circular dependency
# ============================================================================

def get_current_user_dep():
    from main import get_current_user_flexible
    return get_current_user_flexible

def get_models():
    from main import Loan, User
    return Loan, User

def get_permission_functions():
    from routes.permission_core_routes import filter_loans_by_permissions
    return filter_loans_by_permissions


# ============================================================================
# Ensure all Loan model columns exist in production DB
# (Production skips Base.metadata.create_all; checkfirst only checks table
# existence, not missing columns. This adds any columns the model defines
# but the DB table lacks.)
# ============================================================================

def _ensure_loans_columns():
    """Add missing columns to the loans table. Safe to run repeatedly."""
    from sqlalchemy import text
    try:
        from db import engine
        # All columns that may be missing, grouped by type
        # Format: (column_name, pg_type)
        columns = [
            # Borrower
            ("preferred_communication", "VARCHAR"),
            ("coborrower_name", "VARCHAR"),
            ("co_borrower_email", "VARCHAR"),
            # Team
            ("realtor_agent", "VARCHAR"),
            ("title_company", "VARCHAR"),
            ("lender", "VARCHAR"),
            ("loan_officer_name", "VARCHAR"),
            ("loan_officer_email", "VARCHAR"),
            ("processor_email", "VARCHAR"),
            ("underwriter_email", "VARCHAR"),
            ("closer", "VARCHAR"),
            ("closer_email", "VARCHAR"),
            # SLA tracking
            ("days_in_stage", "INTEGER DEFAULT 0"),
            ("sla_status", "VARCHAR DEFAULT 'on-track'"),
            ("milestones", "JSONB"),
            ("ai_insights", "TEXT"),
            ("predicted_close_date", "TIMESTAMP"),
            ("risk_score", "INTEGER DEFAULT 0"),
            ("user_metadata", "JSONB"),
            # Appraisal tracking
            ("appraisal_ordered_date", "TIMESTAMP"),
            ("appraisal_scheduled_date", "TIMESTAMP"),
            ("appraisal_completed_date", "TIMESTAMP"),
            ("appraisal_value", "FLOAT"),
            ("appraisal_received_date", "TIMESTAMP"),
            ("appraisal_docs_expire_date", "TIMESTAMP"),
            # Title & Insurance tracking
            ("title_ordered_date", "TIMESTAMP"),
            ("title_received_date", "TIMESTAMP"),
            ("insurance_ordered_date", "TIMESTAMP"),
            ("insurance_received_date", "TIMESTAMP"),
            # Rate lock fields
            ("lock_expiration_date", "TIMESTAMP"),
            ("rate_lock_status", "VARCHAR"),
            ("rate_lock_recommendation", "VARCHAR"),
            ("lock_term_days", "INTEGER"),
            ("float_down_available", "BOOLEAN DEFAULT FALSE"),
            ("float_down_terms", "VARCHAR"),
            ("extension_cost_estimate", "FLOAT"),
            ("volatility_score", "INTEGER DEFAULT 50"),
            ("borrower_risk_profile", "VARCHAR"),
            ("lock_score", "INTEGER"),
            ("lock_decision_date", "TIMESTAMP"),
            ("lock_decision_notes", "TEXT"),
            ("last_rate_check", "TIMESTAMP"),
            ("rate_lock_history", "JSONB"),
            # Disclosure milestones
            ("initial_disclosures_sent_date", "TIMESTAMP"),
            ("initial_disclosures_signed_date", "TIMESTAMP"),
            ("cd_received_signed_date", "TIMESTAMP"),
            ("final_closing_package_sent_date", "TIMESTAMP"),
            # Under Contract Workflow
            ("contract_received_date", "TIMESTAMP"),
            ("loan_estimate_sent_date", "TIMESTAMP"),
            ("conditional_approval_date", "TIMESTAMP"),
            # AMR tracking
            ("last_amr_date", "TIMESTAMP"),
            ("next_amr_date", "TIMESTAMP"),
            ("refi_opportunity_score", "INTEGER DEFAULT 0"),
            # Workflow tracking
            ("current_workflow_id", "VARCHAR"),
            ("last_workflow_action", "TIMESTAMP"),
            ("stage_changed_at", "TIMESTAMP"),
            # SLA Date Fields - Jungo Custom Byte Mappings
            ("prospect_date", "TIMESTAMP"),
            ("application_date", "TIMESTAMP"),
            ("le_pending_date", "TIMESTAMP"),
            ("credit_only_date", "TIMESTAMP"),
            ("file_received_date", "TIMESTAMP"),
            ("preapproval_date", "TIMESTAMP"),
            ("uw_received_date", "TIMESTAMP"),
            ("conditions_for_review_date", "TIMESTAMP"),
            ("suspended_date", "TIMESTAMP"),
            ("loan_approved_date", "TIMESTAMP"),
            ("approved_not_accepted_date", "TIMESTAMP"),
            ("approval_expires_date", "TIMESTAMP"),
            ("cd_requested_date", "TIMESTAMP"),
            ("cd_sent_to_borrower_date", "TIMESTAMP"),
            ("cd_acknowledged_date", "TIMESTAMP"),
            ("clear_to_close_date", "TIMESTAMP"),
            ("docs_ordered_date", "TIMESTAMP"),
            ("docs_out_date", "TIMESTAMP"),
            ("credit_docs_expire_date", "TIMESTAMP"),
            ("scheduled_closing_date", "TIMESTAMP"),
            ("scheduled_funding_date", "TIMESTAMP"),
            ("funds_ordered_date", "TIMESTAMP"),
            ("funds_sent_date", "TIMESTAMP"),
            ("first_payment_date", "TIMESTAMP"),
            ("investor_purchased_date", "TIMESTAMP"),
            ("withdrawn_date", "TIMESTAMP"),
            # Salesforce Sync - Identity
            ("salesforce_id", "VARCHAR"),
            # Salesforce Sync - Property
            ("property_type", "VARCHAR"),
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            # Salesforce Sync - Financials
            ("rate_type", "VARCHAR"),
            ("monthly_payment", "FLOAT"),
            ("property_tax", "FLOAT"),
            ("hazard_insurance", "FLOAT"),
            ("mortgage_insurance", "FLOAT"),
            ("hoa_amount", "FLOAT"),
            ("origination_fee", "FLOAT"),
            ("estimated_prepaid_interest", "FLOAT"),
            ("points", "FLOAT"),
            ("index_rate", "FLOAT"),
            ("margin", "FLOAT"),
            ("ltv", "FLOAT"),
            ("cltv", "FLOAT"),
            ("loan_purpose", "VARCHAR"),
            ("file_state", "VARCHAR"),
            # Salesforce Sync - 2nd Loan
            ("second_loan_amount", "FLOAT"),
            ("second_loan_rate", "FLOAT"),
            ("second_loan_payment", "FLOAT"),
            # Salesforce Sync - Housing Expenses
            ("present_housing_expense", "FLOAT"),
            ("proposed_housing_expense", "FLOAT"),
            ("present_monthly_payment", "FLOAT"),
            ("proposed_monthly_payment", "FLOAT"),
        ]

        with engine.connect() as conn:
            added = 0
            for col_name, col_type in columns:
                try:
                    conn.execute(text(
                        f"ALTER TABLE loans ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    ))
                    added += 1
                except Exception:
                    pass  # Column might already exist or type conflict
            conn.commit()
            logger.info(f"✅ Loans table column sync complete ({len(columns)} checked)")

            # Backfill: Fix "Unknown Borrower" names from leads with matching email
            try:
                result = conn.execute(text("""
                    UPDATE loans l
                    SET borrower_name = COALESCE(
                        (SELECT TRIM(CONCAT(ld.first_name, ' ', ld.last_name))
                         FROM leads ld
                         WHERE ld.email = l.borrower_email
                           AND ld.first_name IS NOT NULL
                           AND ld.first_name != ''
                         LIMIT 1),
                        l.borrower_name
                    ),
                    updated_at = CURRENT_TIMESTAMP
                    WHERE (l.borrower_name IS NULL OR l.borrower_name = 'Unknown Borrower')
                      AND l.borrower_email IS NOT NULL
                """))
                conn.commit()
                fixed = result.rowcount
                if fixed > 0:
                    logger.info(f"Backfilled {fixed} 'Unknown Borrower' loan names from leads")
            except Exception as bf_err:
                logger.warning(f"Borrower name backfill skipped: {bf_err}")

            # Backfill: Fix first-name-only borrower names (no space = likely missing last name)
            try:
                result = conn.execute(text("""
                    UPDATE loans l
                    SET borrower_name = (
                        SELECT TRIM(CONCAT(ld.first_name, ' ', ld.last_name))
                        FROM leads ld
                        WHERE ld.email = l.borrower_email
                          AND ld.first_name IS NOT NULL AND ld.first_name != ''
                          AND ld.last_name IS NOT NULL AND ld.last_name != ''
                        LIMIT 1
                    ),
                    updated_at = CURRENT_TIMESTAMP
                    WHERE l.borrower_name IS NOT NULL
                      AND l.borrower_name != 'Unknown Borrower'
                      AND l.borrower_name NOT LIKE '% %'
                      AND l.borrower_email IS NOT NULL
                      AND EXISTS (
                          SELECT 1 FROM leads ld
                          WHERE ld.email = l.borrower_email
                            AND ld.first_name IS NOT NULL AND ld.first_name != ''
                            AND ld.last_name IS NOT NULL AND ld.last_name != ''
                      )
                """))
                conn.commit()
                fixed = result.rowcount
                if fixed > 0:
                    logger.info(f"Backfilled {fixed} first-name-only loan borrower names from leads")
            except Exception as bf_err:
                logger.warning(f"First-name-only backfill skipped: {bf_err}")

            # Backfill: Mark loans with past closing_date or funded_date as FUNDED
            try:
                result = conn.execute(text("""
                    UPDATE loans
                    SET stage = 'FUNDED',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE (
                        (funded_date IS NOT NULL AND funded_date < CURRENT_TIMESTAMP)
                        OR (closing_date IS NOT NULL AND closing_date < CURRENT_TIMESTAMP)
                    )
                    AND UPPER(stage::text) NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN')
                """))
                conn.commit()
                fixed_stages = result.rowcount
                if fixed_stages > 0:
                    logger.info(f"✅ Corrected {fixed_stages} closed loans to FUNDED stage")
            except Exception as stage_err:
                logger.warning(f"⚠️ Loan stage correction skipped: {stage_err}")

            # Auto-promote funded loans without MUM clients
            try:
                eligible = conn.execute(text("""
                    SELECT l.id, l.loan_number, l.loan_officer_id
                    FROM loans l
                    LEFT JOIN mum_clients mc ON mc.loan_number = l.loan_number
                    WHERE mc.id IS NULL
                      AND (
                        l.funded_date IS NOT NULL
                        OR l.closing_date IS NOT NULL
                        OR UPPER(l.stage::text) = 'FUNDED'
                      )
                """)).fetchall()
                if eligible:
                    logger.info(f"🔄 Found {len(eligible)} funded loans without MUM clients — promoting...")
                    promoted = 0
                    for row in eligible:
                        loan_id, loan_number, lo_id = row[0], row[1], row[2]
                        try:
                            from services.mum_promotion_service import maybe_promote_loan_to_mum
                            from database import SessionLocal
                            session = SessionLocal()
                            try:
                                mum_id = maybe_promote_loan_to_mum(session, loan_id, lo_id or 1)
                                if mum_id:
                                    promoted += 1
                                session.commit()
                            finally:
                                session.close()
                        except Exception as promo_err:
                            logger.warning(f"⚠️ Could not promote loan {loan_id}: {promo_err}")
                    if promoted:
                        logger.info(f"✅ Auto-promoted {promoted} funded loans to MUM clients")
            except Exception as promo_err:
                logger.warning(f"⚠️ Auto-promotion skipped: {promo_err}")
    except Exception as e:
        logger.warning(f"⚠️ Could not sync loans columns: {e}")

# Run on module load
_ensure_loans_columns()


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/", status_code=201)
async def create_loan(
    loan_data: dict,
    skip_duplicate_check: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Create a new loan. Used for lead-to-loan conversion and direct loan creation."""
    try:
        Loan, User = get_models()
    except Exception as e:
        logger.error(f"Failed to import models: {e}")
        return JSONResponse(status_code=422, content={"detail": "Model import error"})

    try:
        # Check for duplicate loan number unless explicitly skipped
        if not skip_duplicate_check and loan_data.get("loan_number"):
            existing = db.query(Loan).filter(
                Loan.loan_number == loan_data["loan_number"]
            ).first()
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Loan with number {loan_data['loan_number']} already exists"
                )

        # Ensure loan_number is set
        loan_number = loan_data.get("loan_number")
        if not loan_number:
            import uuid
            loan_number = f"LOAN-{uuid.uuid4().hex[:8].upper()}"

        # Safely parse amount
        try:
            amount = float(loan_data.get("amount") or 0) or 1.0
        except (ValueError, TypeError):
            amount = 1.0

        # Build the loan object with only fields that exist on the model
        loan_fields = {
            "loan_number": loan_number,
            "borrower_name": loan_data.get("borrower_name") or "Unknown Borrower",
            "borrower_email": loan_data.get("borrower_email"),
            "borrower_phone": loan_data.get("borrower_phone"),
            "amount": amount,
            "stage": loan_data.get("stage") or "DISCLOSED",
            "property_address": loan_data.get("property_address"),
            "loan_officer_id": current_user.id,
            "organization_id": getattr(current_user, "organization_id", None),
        }

        # Set loan officer name/email safely
        lo_name = getattr(current_user, "full_name", "") or ""
        if not lo_name:
            first = getattr(current_user, "first_name", "") or ""
            last = getattr(current_user, "last_name", "") or ""
            lo_name = f"{first} {last}".strip()
        if lo_name:
            loan_fields["loan_officer_name"] = lo_name
        lo_email = getattr(current_user, "email", None)
        if lo_email:
            loan_fields["loan_officer_email"] = lo_email

        # Optional fields the frontend or other callers might send
        optional_fields = [
            "program", "loan_type", "loan_purpose", "rate", "term",
            "purchase_price", "down_payment", "property_city", "property_state",
            "property_zip", "property_type", "occupancy_type",
            "coborrower_name", "co_borrower_email", "preferred_communication",
            "processor", "underwriter", "realtor_agent", "title_company", "lender",
            "ai_insights", "user_metadata",
        ]
        for field in optional_fields:
            if field in loan_data and loan_data[field] is not None:
                loan_fields[field] = loan_data[field]

        # Set funded_date if stage is Funded
        if loan_fields["stage"] in ("Funded", "FUNDED"):
            loan_fields["funded_date"] = datetime.now(timezone.utc)

        logger.info(f"Creating loan with fields: {list(loan_fields.keys())}")

        db_loan = Loan(**loan_fields)
        db.add(db_loan)
        db.commit()
        db.refresh(db_loan)

        logger.info(f"Loan created: {db_loan.loan_number} (ID: {db_loan.id}, Stage: {db_loan.stage})")

        return _loan_to_dict(db_loan)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating loan: {e}", exc_info=True)
        db.rollback()
        logger.error(f"Loan creation traceback: {traceback.format_exc()}")
        return JSONResponse(
            status_code=422,
            content={"detail": "Failed to create loan. Please check required fields and try again."}
        )


@router.get("/")
async def get_loans(
    skip: int = 0,
    limit: int = 100,
    stage: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get all loans with optional stage filtering and permission-based access."""
    Loan, User = get_models()
    filter_loans_by_permissions = get_permission_functions()

    try:
        query = db.query(Loan)
        query = filter_loans_by_permissions(query, current_user, db)

        if stage:
            query = query.filter(Loan.stage == stage)

        loans = query.order_by(Loan.created_at.desc()).offset(skip).limit(limit).all()

        return [_loan_to_dict(loan) for loan in loans]

    except Exception as e:
        logger.error(f"get_loans error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{loan_id}")
async def get_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get a single loan by ID."""
    Loan, User = get_models()
    filter_loans_by_permissions = get_permission_functions()

    loan = filter_loans_by_permissions(
        db.query(Loan), current_user, db
    ).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    return _loan_to_dict(loan)


@router.patch("/{loan_id}")
async def update_loan(
    loan_id: int,
    update_data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Update a loan by ID."""
    Loan, User = get_models()
    filter_loans_by_permissions = get_permission_functions()

    loan = filter_loans_by_permissions(
        db.query(Loan), current_user, db
    ).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Fields that can be updated
    updatable_fields = [
        "loan_number", "borrower_name", "borrower_email", "borrower_phone",
        "stage", "program", "loan_type", "loan_purpose", "amount",
        "purchase_price", "down_payment", "rate", "term",
        "property_address", "property_city", "property_state", "property_zip",
        "property_type", "occupancy_type", "coborrower_name", "co_borrower_email",
        "preferred_communication", "processor", "underwriter", "realtor_agent",
        "title_company", "lender", "closing_date", "lock_date", "funded_date",
        "ai_insights", "user_metadata", "sla_status", "days_in_stage",
        "processor_email", "underwriter_email", "closer", "closer_email",
        "loan_officer_name", "loan_officer_email",
    ]

    for field in updatable_fields:
        if field in update_data:
            setattr(loan, field, update_data[field])

    # If stage changed to Funded, set funded_date
    if "stage" in update_data and update_data["stage"] in ("Funded", "FUNDED"):
        if not loan.funded_date:
            loan.funded_date = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(loan)
        logger.info(f"Loan updated: {loan.loan_number} (ID: {loan.id})")
        return _loan_to_dict(loan)
    except Exception as e:
        logger.error(f"Error updating loan: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update loan")


@router.delete("/{loan_id}")
async def delete_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Delete a loan by ID."""
    Loan, User = get_models()
    filter_loans_by_permissions = get_permission_functions()

    loan = filter_loans_by_permissions(
        db.query(Loan), current_user, db
    ).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    try:
        db.delete(loan)
        db.commit()
        logger.info(f"Loan deleted: {loan.loan_number} (ID: {loan_id})")
        return {"message": "Loan deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting loan: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete loan")


@router.post("/bulk-delete")
async def bulk_delete_loans(
    loan_ids: list,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Bulk delete loans by list of IDs."""
    Loan, User = get_models()
    filter_loans_by_permissions = get_permission_functions()

    try:
        deleted = filter_loans_by_permissions(
            db.query(Loan), current_user, db
        ).filter(Loan.id.in_(loan_ids)).delete(synchronize_session=False)
        db.commit()
        logger.info(f"Bulk deleted {deleted} loans")
        return {"deleted": deleted}
    except Exception as e:
        logger.error(f"Error bulk deleting loans: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to bulk delete loans")


# ============================================================================
# HELPERS
# ============================================================================

def _loan_to_dict(loan) -> dict:
    """Convert a Loan ORM object to a dict for JSON response."""
    return {
        "id": loan.id,
        "loan_number": loan.loan_number,
        "borrower_name": loan.borrower_name,
        "borrower_email": loan.borrower_email,
        "borrower_phone": loan.borrower_phone,
        "coborrower_name": loan.coborrower_name,
        "stage": loan.stage,
        "program": loan.program,
        "loan_type": loan.loan_type,
        "loan_purpose": loan.loan_purpose,
        "amount": loan.amount,
        "purchase_price": loan.purchase_price,
        "down_payment": loan.down_payment,
        "rate": loan.rate,
        "term": loan.term,
        "property_address": loan.property_address,
        "property_city": loan.property_city,
        "property_state": loan.property_state,
        "property_zip": loan.property_zip,
        "property_type": loan.property_type,
        "occupancy_type": loan.occupancy_type,
        "lock_date": loan.lock_date.isoformat() if loan.lock_date else None,
        "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
        "funded_date": loan.funded_date.isoformat() if loan.funded_date else None,
        "loan_officer_id": loan.loan_officer_id,
        "loan_officer_name": loan.loan_officer_name,
        "processor": loan.processor,
        "underwriter": loan.underwriter,
        "days_in_stage": loan.days_in_stage,
        "sla_status": loan.sla_status,
        "ai_insights": loan.ai_insights,
        "risk_score": loan.risk_score,
        "monthly_payment": loan.monthly_payment,
        "organization_id": loan.organization_id,
        "created_at": loan.created_at.isoformat() if loan.created_at else None,
        "updated_at": loan.updated_at.isoformat() if loan.updated_at else None,
    }
