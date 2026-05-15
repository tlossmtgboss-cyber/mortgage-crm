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
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timezone
import logging
import traceback

from db import get_db
from utils.pagination import clamp_pagination

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/loans", tags=["Loans CRUD"])


# ============================================================================
# Loan stage state machine — valid transitions (DATA-004)
# ============================================================================

VALID_LOAN_TRANSITIONS = {
    "APPLICATION": ["DISCLOSED", "CANCELLED", "WITHDRAWN", "DOES_NOT_QUALIFY"],
    "DISCLOSED": ["PROCESSING", "CANCELLED", "WITHDRAWN"],
    "PROCESSING": ["SUBMITTED", "CANCELLED", "WITHDRAWN", "SUSPENDED"],
    "SUBMITTED": ["UNDERWRITING", "CANCELLED", "WITHDRAWN"],
    "UNDERWRITING": ["UW_RECEIVED", "CANCELLED", "WITHDRAWN", "SUSPENDED"],
    "UW_RECEIVED": ["CONDITIONAL_APPROVAL", "APPROVED", "DENIED", "SUSPENDED"],
    "CONDITIONAL_APPROVAL": ["APPROVED", "DENIED", "SUSPENDED"],
    "APPROVED": ["CTC", "CLEAR_TO_CLOSE", "SUSPENDED"],
    "SUSPENDED": ["PROCESSING", "UNDERWRITING", "CANCELLED"],
    "CTC": ["CLEAR_TO_CLOSE", "SUSPENDED"],
    "CLEAR_TO_CLOSE": ["CLOSING", "DOCS", "SUSPENDED"],
    "CLOSING": ["DOCS", "DOCS_OUT", "SUSPENDED"],
    "DOCS": ["DOCS_OUT", "SUSPENDED"],
    "DOCS_OUT": ["FUNDED", "SUSPENDED"],
    "NURTURE": ["APPLICATION", "CANCELLED", "DEAD"],
}

# Roles allowed to bypass stage transition validation
ADMIN_ROLES = {"admin", "site_admin", "platform_admin"}


def _validate_stage_transition(
    current_stage: str,
    new_stage: str,
    user_role: str = None,
    force: bool = False,
) -> Optional[str]:
    """Validate a loan stage transition against the state machine.

    Returns an error message string if invalid, or None if allowed.
    Admins can bypass with force=True.
    """
    # Normalize stages to uppercase
    current_upper = current_stage.upper() if current_stage else ""
    new_upper = new_stage.upper() if new_stage else ""

    # No change = always allowed
    if current_upper == new_upper:
        return None

    # Admin bypass with force flag
    if force and user_role and user_role.lower() in ADMIN_ROLES:
        logger.info(
            f"Admin stage transition bypass: {current_upper} -> {new_upper} "
            f"(role={user_role}, force=True)"
        )
        return None

    # Check if current stage has defined transitions
    allowed = VALID_LOAN_TRANSITIONS.get(current_upper)
    if allowed is None:
        # Terminal stages (FUNDED, CANCELLED, DENIED, DEAD, WITHDRAWN, DOES_NOT_QUALIFY)
        # have no outgoing transitions defined — block unless admin-forced
        return (
            f"Stage '{current_upper}' is terminal and cannot transition to '{new_upper}'. "
            f"Use force_stage=true with an admin account to override."
        )

    if new_upper not in allowed:
        return (
            f"Invalid stage transition: '{current_upper}' -> '{new_upper}'. "
            f"Allowed transitions from '{current_upper}': {allowed}. "
            f"Use force_stage=true with an admin account to override."
        )

    return None


# ============================================================================
# Lazy imports to avoid circular dependency
# ============================================================================

def get_current_user_dep():
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

def get_models():
    from database.models import Loan, User
    return Loan, User

def get_permission_functions():
    from routes.permission_core_routes import filter_loans_by_permissions
    return filter_loans_by_permissions

def get_has_permission():
    from routes.permission_core_routes import has_permission
    return has_permission


# ============================================================================
# ECOA Adverse Action Auto-Trigger (SEC-ECOA-001)
# ============================================================================

def _trigger_ecoa_adverse_action(
    db: Session,
    loan,
    user_id: int = None,
    organization_id: int = None,
):
    """Auto-trigger ECOA adverse action notice requirement when a loan is DENIED.

    Per Regulation B (12 CFR 1002.9), the creditor must provide an adverse
    action notice within 30 days of the credit decision. This function:
      1. Checks if an adverse action notice already exists for this loan
      2. If not, creates a ComplianceAlert flagging the requirement
      3. Logs the trigger to the audit trail

    This is a trigger/flag, not the full adverse action system. It ensures the
    requirement cannot be silently missed when a loan transitions to DENIED.
    """
    from datetime import timedelta

    denial_date = datetime.now(timezone.utc)
    notice_deadline = denial_date + timedelta(days=30)

    # Check if an adverse action notice already exists for this loan
    try:
        from database.models.compliance import AdverseActionNotice
        existing_notice = db.query(AdverseActionNotice).filter(
            AdverseActionNotice.loan_id == loan.id,
        ).first()
        if existing_notice:
            logger.info(
                f"ECOA adverse action notice already exists for loan {loan.id} "
                f"(notice ID: {existing_notice.id})"
            )
            return
    except Exception as e:
        # Model may not exist yet; proceed to create the alert
        logger.debug(f"Could not check existing adverse action notices: {e}")

    # Create a compliance alert to flag the adverse action requirement
    try:
        from sqlalchemy import text
        db.execute(text("""
            INSERT INTO compliance_alerts (
                organization_id, alert_type, severity, entity_type, entity_id,
                title, description, due_date, status, created_at
            ) VALUES (
                :org_id, 'ecoa_adverse_action', 'critical', 'loan', :loan_id,
                :title, :description, :due_date, 'open', NOW()
            )
            ON CONFLICT DO NOTHING
        """), {
            "org_id": organization_id,
            "loan_id": loan.id,
            "title": f"ECOA Adverse Action Notice Required — Loan {getattr(loan, 'loan_number', loan.id)}",
            "description": (
                f"Loan {getattr(loan, 'loan_number', '')} was denied on "
                f"{denial_date.strftime('%m/%d/%Y')}. Per ECOA Regulation B "
                f"(12 CFR 1002.9), an adverse action notice must be sent to the "
                f"applicant within 30 days (by {notice_deadline.strftime('%m/%d/%Y')}). "
                f"Include specific reason(s) for denial, ECOA rights notice, and "
                f"creditor/federal regulator information."
            ),
            "due_date": notice_deadline,
        })
    except Exception as alert_err:
        # If the compliance_alerts table doesn't exist, fall through to audit log
        logger.warning(f"Could not create compliance alert for ECOA adverse action: {alert_err}")

    # Log to the hash-chained audit trail
    try:
        from services.audit_service import create_audit_entry
        create_audit_entry(
            db=db,
            user_id=user_id or 0,
            changed_by_id=user_id or 0,
            change_type="compliance",
            entity_type="loan",
            entity_id=loan.id,
            before_state=None,
            after_state={
                "stage": "DENIED",
                "ecoa_adverse_action_required": True,
                "denial_date": denial_date.isoformat(),
                "notice_deadline": notice_deadline.isoformat(),
                "borrower_name": getattr(loan, "borrower_name", None),
                "loan_number": getattr(loan, "loan_number", None),
            },
            reason="ECOA adverse action notice auto-triggered on loan denial",
            organization_id=organization_id,
        )
    except Exception as audit_err:
        logger.warning(f"ECOA audit entry creation failed: {audit_err}")

    logger.info(
        "ECOA_ADVERSE_ACTION_REQUIRED",
        extra={
            "loan_id": loan.id,
            "loan_number": getattr(loan, "loan_number", None),
            "organization_id": organization_id,
            "denial_date": denial_date.isoformat(),
            "notice_deadline": notice_deadline.isoformat(),
            "triggered_by_user_id": user_id,
        },
    )


# ============================================================================
# Ensure all Loan model columns exist in production DB
# (Production skips Base.metadata.create_all; checkfirst only checks table
# existence, not missing columns. This adds any columns the model defines
# but the DB table lacks.)
# ============================================================================

_columns_ensured = False

def _ensure_loans_columns():
    """Add missing columns to the loans table. Safe to run repeatedly."""
    global _columns_ensured
    if _columns_ensured:
        return
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
                except Exception as e:
                    logger.error(f"Error adding column {col_name}: {e}")
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
                    try:
                        from services.mum_promotion_service import maybe_promote_loan_to_mum
                        from database import SessionLocal
                        # Note: System-level startup task iterating all tenants; no per-tenant RLS
                        session = SessionLocal()
                        try:
                            for row in eligible:
                                loan_id, loan_number, lo_id = row[0], row[1], row[2]
                                try:
                                    mum_id = maybe_promote_loan_to_mum(session, loan_id, lo_id or 1)
                                    if mum_id:
                                        promoted += 1
                                except Exception as promo_err:
                                    logger.warning(f"⚠️ Could not promote loan {loan_id}: {promo_err}")
                            session.commit()
                        finally:
                            session.close()
                    except Exception as promo_err:
                        logger.warning(f"⚠️ MUM promotion batch failed: {promo_err}")
                    if promoted:
                        logger.info(f"✅ Auto-promoted {promoted} funded loans to MUM clients")
            except Exception as promo_err:
                logger.warning(f"⚠️ Auto-promotion skipped: {promo_err}")
        _columns_ensured = True
    except Exception as e:
        logger.warning(f"⚠️ Could not sync loans columns: {e}")

# Run on module load
try:
    _ensure_loans_columns()
except Exception as e:
    logger.warning(f"⚠️ _ensure_loans_columns failed on import: {e}")


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

    has_permission = get_has_permission()
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if not is_platform_admin:
        has_create_perm = has_permission(current_user.id, 'loans.create', db)
        if not has_create_perm:
            raise HTTPException(status_code=403, detail="Permission denied: loans.create")

    # ---- Input validation (contact info, amounts, rates) ----
    try:
        from validation.common import (
            validate_email_format,
            validate_phone_format,
            validate_loan_amount_decimal,
            validate_interest_rate,
            sanitize_string,
            sanitize_text,
        )

        # Validate and normalize borrower email (optional field)
        if loan_data.get("borrower_email"):
            try:
                loan_data["borrower_email"] = validate_email_format(loan_data["borrower_email"])
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Invalid borrower email: {e}")

        # Validate and normalize borrower phone (optional field)
        if loan_data.get("borrower_phone"):
            try:
                loan_data["borrower_phone"] = validate_phone_format(loan_data["borrower_phone"])
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Invalid borrower phone: {e}")

        # Validate loan amount if provided and non-zero
        raw_amount = loan_data.get("amount")
        if raw_amount and raw_amount != 0:
            try:
                validated_amount = float(validate_loan_amount_decimal(raw_amount))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Invalid loan amount: {e}")
        else:
            validated_amount = None  # will be handled below

        # Validate interest rate if provided
        if loan_data.get("rate"):
            try:
                loan_data["rate"] = float(validate_interest_rate(loan_data["rate"]))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Invalid interest rate: {e}")

        # Sanitize free-text fields
        for text_field in ("borrower_name", "property_address", "ai_insights",
                           "coborrower_name", "realtor_agent", "title_company", "lender"):
            if loan_data.get(text_field):
                loan_data[text_field] = sanitize_string(loan_data[text_field], max_length=500)
    except HTTPException:
        raise
    except Exception as val_err:
        logger.warning(f"Loan input validation error: {val_err}")
        raise HTTPException(status_code=422, detail=str(val_err))

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

        # Use validated amount, or fall back to 1.0 for conversion loans
        if validated_amount is not None:
            amount = validated_amount
        else:
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

        # Invalidate pipeline + dashboard cache for this org
        try:
            from services.cache_service import cache_delete_pattern
            _org = getattr(db_loan, "organization_id", None)
            if _org:
                cache_delete_pattern(f"pipeline:*:org:{_org}:*")
            from performance_cache import invalidate_dashboard
            invalidate_dashboard(current_user.id)
        except Exception as e:
            logger.debug(f"Cache invalidation after create: {e}")

        # Build response dict BEFORE post-commit operations so a sync failure
        # cannot corrupt the ORM object or prevent returning the result (DATA-008)
        response = _loan_to_dict(db_loan)

        # Portal stage sync — if loan created at DISCLOSED or later, transition workspace
        # Wrapped with error isolation: sync failures must not mask the successful creation
        try:
            from services.portal_stage_transition_service import sync_portal_stage
            sync_portal_stage(db, db_loan.id, db_loan.stage)
        except Exception as e:
            logger.warning(f"Portal stage sync failed for new loan {db_loan.id}: {e}")
            # Ensure session is clean after a failed post-commit operation
            try:
                db.rollback()
            except Exception:
                pass

        return response

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
    from sqlalchemy import text
    from services.cache_service import cache_get, cache_set

    Loan, User = get_models()
    filter_loans_by_permissions = get_permission_functions()

    # Enforce pagination limits (PERF-001)
    limit, skip = clamp_pagination(limit, skip)

    # Redis cache — keyed by user + org + query params, 30s TTL
    user_id = getattr(current_user, "id", None)
    org_id = getattr(current_user, "organization_id", None)
    cache_key = f"pipeline:loans:user:{user_id}:org:{org_id}:s:{skip}:l:{limit}:st:{stage or 'all'}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        query = db.query(Loan)
        query = filter_loans_by_permissions(query, current_user, db)
        # Exclude soft-deleted records
        query = query.filter(Loan.deleted_at.is_(None))

        if stage:
            query = query.filter(func.lower(Loan.stage) == stage.lower())

        total = query.count()
        loans = query.order_by(Loan.created_at.desc()).offset(skip).limit(limit).all()

        # Resolve org-wide Production Assistant 1 name (single query for all loans)
        pa_name = None
        try:
            _org_id = current_user.organization_id
            if not _org_id:
                raise HTTPException(status_code=403, detail="Organization context required")
            pa_row = db.execute(text("""
                SELECT COALESCE(u.first_name || ' ' || u.last_name, u.first_name, u.last_name, '') as name
                FROM default_role_assignments dra
                JOIN roles r ON r.id = dra.role_id
                JOIN users u ON u.id = dra.user_id
                WHERE dra.organization_id = :org_id AND r.name = 'Production Assistant 1'
                LIMIT 1
            """), {"org_id": _org_id}).fetchone()
            if pa_row:
                pa_name = pa_row[0] if pa_row[0] and pa_row[0].strip() else None
        except Exception as e:
            logger.debug(f"Production assistant lookup: {e}")

        result = []
        for loan in loans:
            d = _loan_to_dict(loan)
            d["production_assistant"] = pa_name
            result.append(d)

        response_data = {"items": result, "total": total}
        cache_set(cache_key, response_data, ttl=30)
        return response_data

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
    if not loan or loan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Loan not found")

    return _loan_to_dict(loan)


@router.patch("/{loan_id}")
async def update_loan(
    loan_id: int,
    update_data: dict,
    force_closing: bool = Query(False, description="Override CD waiting period (admin/site_admin only)"),
    force_stage: bool = Query(False, description="Override stage transition validation (admin/site_admin only)"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Update a loan by ID.

    Compliance enforcement:
    - Changed circumstances (rate, amount, loan_type, program, property_address)
      auto-trigger a Revised LE DisclosureEvent and ComplianceAlert.
    - Setting closing_date enforces the 3 business day CD waiting period.
      Use force_closing=true (admin/site_admin only) to override.
    - Stage transitions are validated against the loan state machine.
      Use force_stage=true (admin/site_admin only) to override.
    """
    Loan, User = get_models()
    filter_loans_by_permissions = get_permission_functions()
    has_permission = get_has_permission()

    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if not is_platform_admin:
        has_update_perm = (
            has_permission(current_user.id, 'loans.update', db)
            or has_permission(current_user.id, 'loans.update_all', db)
        )
        if not has_update_perm:
            raise HTTPException(status_code=403, detail="Permission denied: loans.update")

    loan = filter_loans_by_permissions(
        db.query(Loan), current_user, db
    ).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # ========================================================================
    # Critical Failure 2.5: CD Waiting Period Enforcement
    # Block closing if CD not sent >= 3 business days before closing date
    # ========================================================================
    if "closing_date" in update_data and update_data["closing_date"]:
        try:
            from services.disclosure_trigger import validate_cd_waiting_period

            new_closing = update_data["closing_date"]
            # Parse string dates if needed
            if isinstance(new_closing, str):
                new_closing = datetime.fromisoformat(new_closing.replace("Z", "+00:00"))

            user_role = getattr(current_user, "permission_role", None) or getattr(current_user, "role", None)
            user_id = getattr(current_user, "id", None)

            cd_error = validate_cd_waiting_period(
                db=db,
                loan=loan,
                new_closing_date=new_closing,
                force_closing=force_closing,
                user_role=user_role,
                user_id=user_id,
            )
            if cd_error:
                raise HTTPException(status_code=422, detail=cd_error)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"CD waiting period check failed: {e}", exc_info=True)
            # Don't block the update if the check itself errors

    # ========================================================================
    # Critical Failure 2.3: Capture old values for changed circumstance detection
    # ========================================================================
    tracked_fields = ["rate", "amount", "loan_type", "program", "property_address"]
    old_values = {}
    for field in tracked_fields:
        if field in update_data:
            old_values[field] = getattr(loan, field, None)

    # Capture old stage for SLA tracking before any updates
    old_stage = getattr(loan, 'stage', None)
    if old_stage and hasattr(old_stage, 'value'):
        old_stage = old_stage.value  # Convert enum to string

    # ========================================================================
    # DATA-004: Loan stage state machine validation
    # ========================================================================
    if "stage" in update_data and update_data["stage"]:
        new_stage = update_data["stage"]
        user_role = getattr(current_user, "permission_role", None) or getattr(current_user, "role", None)
        transition_error = _validate_stage_transition(
            current_stage=old_stage or "",
            new_stage=new_stage,
            user_role=user_role,
            force=force_stage,
        )
        if transition_error:
            raise HTTPException(status_code=422, detail=transition_error)

    # ========================================================================
    # Input validation for updated fields (contact info, amounts, rates)
    # ========================================================================
    try:
        from validation.common import (
            validate_email_format as _val_email,
            validate_phone_format as _val_phone,
            validate_loan_amount_decimal as _val_amount,
            validate_interest_rate as _val_rate,
            sanitize_string as _san_str,
        )

        # Validate email fields
        for email_field in ("borrower_email", "co_borrower_email",
                            "processor_email", "underwriter_email",
                            "closer_email", "loan_officer_email"):
            if update_data.get(email_field):
                try:
                    update_data[email_field] = _val_email(update_data[email_field])
                except ValueError as e:
                    raise HTTPException(status_code=422, detail=f"Invalid {email_field}: {e}")

        # Validate phone field
        if update_data.get("borrower_phone"):
            try:
                update_data["borrower_phone"] = _val_phone(update_data["borrower_phone"])
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Invalid borrower_phone: {e}")

        # Validate loan amount
        if "amount" in update_data and update_data["amount"]:
            try:
                update_data["amount"] = float(_val_amount(update_data["amount"]))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Invalid loan amount: {e}")

        # Validate interest rate
        if "rate" in update_data and update_data["rate"]:
            try:
                update_data["rate"] = float(_val_rate(update_data["rate"]))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Invalid interest rate: {e}")

        # Sanitize free-text fields
        for text_field in ("borrower_name", "property_address", "coborrower_name",
                           "realtor_agent", "title_company", "lender",
                           "loan_officer_name", "ai_insights"):
            if update_data.get(text_field):
                update_data[text_field] = _san_str(update_data[text_field], max_length=500)
    except HTTPException:
        raise
    except Exception as val_err:
        logger.warning(f"Loan update validation error: {val_err}")

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

    # ========================================================================
    # Critical Failure 2.3: Check for changed circumstances and auto-trigger
    # re-disclosure events after applying the update
    # ========================================================================
    changes_detected = []
    if old_values:
        try:
            from services.disclosure_trigger import check_changed_circumstances

            new_values = {field: update_data[field] for field in tracked_fields if field in update_data}
            changes_detected = check_changed_circumstances(
                db=db,
                loan_id=loan_id,
                old_values=old_values,
                new_values=new_values,
                organization_id=getattr(loan, "organization_id", None),
                triggered_by_user_id=getattr(current_user, "id", None),
            )
        except Exception as e:
            logger.error(f"Changed circumstance check failed: {e}", exc_info=True)
            # Don't block the update if the compliance check itself errors

    try:
        db.commit()
        db.refresh(loan)
        logger.info(f"Loan updated: {loan.loan_number} (ID: {loan.id})")

        # Invalidate pipeline + dashboard cache for this org
        try:
            from services.cache_service import cache_delete_pattern
            _org = getattr(loan, "organization_id", None)
            if _org:
                cache_delete_pattern(f"pipeline:*:org:{_org}:*")
            from performance_cache import invalidate_dashboard
            invalidate_dashboard(current_user.id)
        except Exception as e:
            logger.debug(f"Cache invalidation after update: {e}")

        # Wire to SLA tracking — detect stage changes
        if "stage" in update_data:
            new_stage = update_data["stage"]
            if new_stage != old_stage:
                try:
                    from services.sla_tracking_service import track_loan_stage_change
                    track_loan_stage_change(
                        db, loan.id, old_stage, new_stage,
                        user_id=getattr(current_user, "id", None),
                        loan_number=loan.loan_number,
                        organization_id=getattr(loan, "organization_id", None),
                    )
                except Exception as e:
                    logger.warning(f"SLA tracking hook failed for loan {loan.id} stage change: {e}")

                # Portal stage sync — transition PURL workspace if applicable
                try:
                    from services.portal_stage_transition_service import sync_portal_stage
                    sync_portal_stage(db, loan.id, new_stage, old_stage)
                except Exception as e:
                    logger.warning(f"Portal stage sync failed for loan {loan.id}: {e}")

                # Event-driven workflow enrollment (eliminates 60s polling delay)
                try:
                    from services.workflow_scheduler import trigger_workflow_evaluation_for_loan
                    trigger_workflow_evaluation_for_loan(
                        db, loan.id, new_stage,
                        user_id=getattr(current_user, "id", None),
                    )
                except Exception as e:
                    logger.warning(f"Workflow evaluation trigger failed for loan {loan.id}: {e}")

                # ACO trigger — run completeness review on key stage transitions
                ACO_TRIGGER_STAGES = (
                    "APPLICATION", "DISCLOSED", "SUBMITTED",
                    "UW_RECEIVED", "CONDITIONAL_APPROVAL",
                )
                if new_stage in ACO_TRIGGER_STAGES:
                    try:
                        from tasks.app_completion_tasks import trigger_application_review_task
                        trigger_application_review_task.delay(
                            loan_id=loan.id,
                            triggered_by=f"STAGE_CHANGE_{new_stage}",
                        )
                        logger.info(f"ACO review queued for loan {loan.id} on stage {new_stage}")
                    except Exception as e:
                        logger.warning(f"ACO review trigger failed for loan {loan.id}: {e}")

                # Push notification to LO on stage change
                try:
                    from routes.push_notification_routes import notify_loan_update
                    lo_id = getattr(loan, "loan_officer_id", None) or getattr(current_user, "id", None)
                    borrower = getattr(loan, "borrower_name", None) or getattr(loan, "loan_number", None) or f"Loan #{loan.id}"
                    if lo_id:
                        notify_loan_update(db, lo_id, borrower, new_stage, str(loan.id))
                except Exception as e:
                    logger.debug(f"Push notification on stage change failed for loan {loan.id}: {e}")

                # Calendar-Pipeline Bridge: suggest closing appointment on conditional approval
                try:
                    from services.calendar_pipeline_bridge import on_loan_stage_change
                    bridge_result = on_loan_stage_change(
                        db, loan.id, new_stage,
                        organization_id=getattr(loan, "organization_id", None),
                    )
                    if bridge_result.get("action") == "task_created":
                        db.commit()
                        logger.info(f"Calendar-Pipeline Bridge: {bridge_result}")
                except Exception as e:
                    logger.warning(f"Calendar-Pipeline Bridge failed for loan {loan.id}: {e}")

                # =============================================================
                # ECOA Adverse Action Trigger (Finding SEC-ECOA-001)
                # When a loan transitions to a denial stage, auto-generate
                # an adverse action notice per Regulation B (12 CFR 1002.9).
                # The 30-day notice clock starts on the denial date.
                # Covers: DENIED, DOES_NOT_QUALIFY
                # =============================================================
                _ADVERSE_ACTION_STAGES = ("DENIED", "DOES_NOT_QUALIFY")
                if new_stage.upper() in _ADVERSE_ACTION_STAGES:
                    try:
                        from services.adverse_action_service import generate_adverse_action_notice
                        generate_adverse_action_notice(
                            db=db,
                            loan=loan,
                            denial_reason_codes=None,  # Will default to ["other"]; caller can enrich later
                            user_id=getattr(current_user, "id", None),
                            organization_id=getattr(loan, "organization_id", None),
                        )
                    except Exception as ecoa_err:
                        logger.error(
                            f"ECOA adverse action trigger failed for loan {loan.id}: {ecoa_err}",
                            exc_info=True,
                        )

        result = _loan_to_dict(loan)

        # Include compliance actions in the response so the frontend can alert users
        if changes_detected:
            result["_compliance_actions"] = {
                "changed_circumstances": changes_detected,
                "message": (
                    f"{len(changes_detected)} changed circumstance(s) detected. "
                    f"Revised Loan Estimate(s) must be sent within 3 business days."
                ),
            }

        return result
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
    has_permission = get_has_permission()

    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if not is_platform_admin:
        has_delete_perm = (
            has_permission(current_user.id, 'loans.delete', db)
            or has_permission(current_user.id, 'loans.delete_all', db)
        )
        if not has_delete_perm:
            raise HTTPException(status_code=403, detail="Permission denied: loans.delete")

    loan = filter_loans_by_permissions(
        db.query(Loan), current_user, db
    ).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    try:
        _org = getattr(loan, "organization_id", None)
        # Soft-delete: set deleted_at timestamp instead of removing data
        loan.deleted_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Loan soft-deleted: {loan.loan_number} (ID: {loan_id})")

        # Invalidate pipeline + dashboard cache for this org
        try:
            from services.cache_service import cache_delete_pattern
            if _org:
                cache_delete_pattern(f"pipeline:*:org:{_org}:*")
            from performance_cache import invalidate_dashboard
            invalidate_dashboard(current_user.id)
        except Exception as e:
            logger.debug(f"Cache invalidation after delete: {e}")

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
    has_permission = get_has_permission()

    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if not is_platform_admin:
        has_delete_perm = (
            has_permission(current_user.id, 'loans.delete', db)
            or has_permission(current_user.id, 'loans.delete_all', db)
        )
        if not has_delete_perm:
            raise HTTPException(status_code=403, detail="Permission denied: loans.delete")

    try:
        # Soft-delete: set deleted_at timestamp instead of removing data
        now = datetime.now(timezone.utc)
        deleted = filter_loans_by_permissions(
            db.query(Loan), current_user, db
        ).filter(Loan.id.in_(loan_ids)).update(
            {"deleted_at": now}, synchronize_session=False
        )
        db.commit()
        logger.info(f"Bulk soft-deleted {deleted} loans")

        # Invalidate pipeline + dashboard cache for this org
        if deleted:
            try:
                from services.cache_service import cache_delete_pattern
                _org = getattr(current_user, "organization_id", None)
                if _org:
                    cache_delete_pattern(f"pipeline:*:org:{_org}:*")
                from performance_cache import invalidate_dashboard
                invalidate_dashboard(current_user.id)
            except Exception as e:
                logger.debug(f"Cache invalidation after bulk delete: {e}")

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
        "production_assistant": getattr(loan, 'production_assistant', None),
        "days_in_stage": loan.days_in_stage,
        "sla_status": loan.sla_status,
        "ai_insights": loan.ai_insights,
        "risk_score": loan.risk_score,
        "monthly_payment": loan.monthly_payment,
        "organization_id": loan.organization_id,
        "created_at": loan.created_at.isoformat() if loan.created_at else None,
        "updated_at": loan.updated_at.isoformat() if loan.updated_at else None,
    }
