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
        return JSONResponse(status_code=422, content={"detail": f"Model import error: {str(e)}"})

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
        # Return JSONResponse directly to bypass production error sanitizer
        # so the frontend shows the actual error instead of "Internal server error"
        error_msg = str(e)
        tb = traceback.format_exc()
        logger.error(f"Loan creation traceback: {tb}")
        return JSONResponse(
            status_code=422,
            content={"detail": f"Failed to create loan: {error_msg}"}
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

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
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

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
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

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
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

    try:
        deleted = db.query(Loan).filter(Loan.id.in_(loan_ids)).delete(synchronize_session=False)
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
