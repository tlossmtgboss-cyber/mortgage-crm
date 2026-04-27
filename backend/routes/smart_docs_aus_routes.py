"""
Smart Docs AUS (Automated Underwriting System) Routes

Endpoints for submitting loans to Desktop Underwriter (DU) and Loan Product
Advisor (LPA), reviewing findings, comparing income calculations, and
importing conditions back into the CRM.

All endpoints require authentication and enforce tenant isolation via
organization_id on the current user.

Prefix: /aus (mounted under /api/smart-docs by smart_docs_v2_registration.py)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

_AUS_ENABLED = bool(os.getenv("DU_API_URL") or os.getenv("LPA_API_URL"))


def _require_aus_enabled():
    """Raise 501 if no AUS API URLs are configured."""
    if not _AUS_ENABLED:
        raise HTTPException(
            status_code=501,
            detail="AUS integration not configured. Set DU_API_URL or LPA_API_URL environment variables.",
        )

router = APIRouter(prefix="/aus", tags=["AUS Integration"])


# =============================================================================
# Pydantic Request/Response Models
# =============================================================================

class AUSSubmitRequest(BaseModel):
    """Request body for submitting a loan to DU or LPA."""
    aus_type: str = Field(..., pattern="^(DU|LPA)$", description="AUS type: 'DU' or 'LPA'")
    include_income: bool = Field(True, description="Include latest income calculation data")
    income_data: Optional[dict] = Field(None, description="Custom income data override (optional)")


class CompareIncomeRequest(BaseModel):
    """Request body for comparing our income to AUS income."""
    submission_id: Optional[int] = Field(None, description="AUS submission ID to compare against")
    custom_income: Optional[dict] = Field(None, description="Custom income data to compare (overrides DB lookup)")


class ImportFindingsRequest(BaseModel):
    """Request body for importing AUS findings into loan conditions."""
    submission_id: int = Field(..., description="AUS submission ID to import from")


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/submit/{loan_id}")
async def submit_to_aus(
    loan_id: int,
    body: AUSSubmitRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit a loan to DU or LPA for automated underwriting.

    Builds MISMO 3.4 data from the loan, optionally includes income
    calculation results, and submits to the selected AUS. Returns the
    AUS recommendation, conditions, and findings.
    """
    _require_aus_enabled()
    from database.models.lead_loan import Loan
    from database.models.aus_submission import AUSSubmission
    from services.smart_docs.integrations.aus_integration_service import (
        AUSIntegrationService,
    )

    org_id = getattr(current_user, "organization_id", None)
    user_id = getattr(current_user, "id", None)

    # Verify loan exists and belongs to this org
    loan = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.organization_id == org_id,
    ).first()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    service = AUSIntegrationService(db)

    try:
        # Determine income data to include
        income_data = body.income_data
        if not income_data and body.include_income:
            income_data = service._load_income_data(loan_id)

        # Submit to the appropriate AUS
        if body.aus_type == "DU":
            result = service.submit_to_du(loan_id, org_id, income_data)
        else:
            result = service.submit_to_lpa(loan_id, org_id, income_data)

        # Persist the submission record
        submission = AUSSubmission(
            organization_id=org_id,
            loan_id=loan_id,
            aus_type=body.aus_type,
            case_id=result.case_id,
            recommendation=result.recommendation,
            risk_class=result.risk_class,
            conditions=[c.to_dict() for c in result.conditions],
            findings=[f.to_dict() for f in result.findings],
            income_data_submitted=income_data,
            income_data_returned=result.income_used,
            submission_status="complete",
            submitted_at=result.submitted_at,
            completed_at=datetime.now(timezone.utc),
            submitted_by_user_id=user_id,
            raw_response=result.raw_response,
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)

        return {
            "status": "success",
            "submission_id": submission.id,
            "data": result.to_dict(),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"AUS submission failed for loan {loan_id}")

        # Record failed submission
        try:
            failed = AUSSubmission(
                organization_id=org_id,
                loan_id=loan_id,
                aus_type=body.aus_type,
                submission_status="error",
                error_message=str(e),
                submitted_at=datetime.now(timezone.utc),
                submitted_by_user_id=user_id,
            )
            db.add(failed)
            db.commit()
        except Exception as db_err:
            logger.error(f"Failed to record AUS error: {db_err}")

        raise HTTPException(
            status_code=500,
            detail="AUS submission failed. The error has been logged.",
        )


@router.get("/findings/{loan_id}")
async def get_aus_findings(
    loan_id: int,
    aus_type: Optional[str] = Query(None, pattern="^(DU|LPA)$"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the latest AUS findings for a loan.

    Returns the most recent completed submission's findings, conditions,
    and recommendation. Optionally filter by AUS type.
    """
    _require_aus_enabled()
    from database.models.aus_submission import AUSSubmission

    org_id = getattr(current_user, "organization_id", None)

    query = db.query(AUSSubmission).filter(
        AUSSubmission.loan_id == loan_id,
        AUSSubmission.organization_id == org_id,
        AUSSubmission.submission_status == "complete",
    )

    if aus_type:
        query = query.filter(AUSSubmission.aus_type == aus_type)

    submission = query.order_by(AUSSubmission.submitted_at.desc()).first()

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="No AUS findings found for this loan",
        )

    return {
        "status": "success",
        "data": {
            "submission_id": submission.id,
            "aus_type": submission.aus_type,
            "case_id": submission.case_id,
            "recommendation": submission.recommendation,
            "risk_class": submission.risk_class,
            "conditions": submission.conditions or [],
            "findings": submission.findings or [],
            "income_data_returned": submission.income_data_returned,
            "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
            "completed_at": submission.completed_at.isoformat() if submission.completed_at else None,
        },
    }


@router.get("/history/{loan_id}")
async def get_submission_history(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all AUS submission history for a loan."""
    _require_aus_enabled()
    from services.smart_docs.integrations.aus_integration_service import (
        AUSIntegrationService,
    )

    org_id = getattr(current_user, "organization_id", None)
    service = AUSIntegrationService(db)
    history = service.get_submission_history(loan_id, org_id)

    return {
        "status": "success",
        "data": {
            "loan_id": loan_id,
            "total_submissions": len(history),
            "submissions": history,
        },
    }


@router.post("/compare-income/{loan_id}")
async def compare_income(
    loan_id: int,
    body: CompareIncomeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Compare our income calculation to what the AUS calculated.

    Uses the most recent AUS submission (or a specific one by ID) and
    compares the income data to our latest income calculation. Returns
    a variance report with flags.
    """
    _require_aus_enabled()
    from database.models.aus_submission import AUSSubmission
    from services.smart_docs.integrations.aus_integration_service import (
        AUSIntegrationService,
    )

    org_id = getattr(current_user, "organization_id", None)
    service = AUSIntegrationService(db)

    # Get the AUS submission to compare against
    if body.submission_id:
        submission = db.query(AUSSubmission).filter(
            AUSSubmission.id == body.submission_id,
            AUSSubmission.organization_id == org_id,
            AUSSubmission.loan_id == loan_id,
        ).first()
    else:
        submission = (
            db.query(AUSSubmission)
            .filter(
                AUSSubmission.loan_id == loan_id,
                AUSSubmission.organization_id == org_id,
                AUSSubmission.submission_status == "complete",
            )
            .order_by(AUSSubmission.submitted_at.desc())
            .first()
        )

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="No AUS submission found for comparison",
        )

    # Get our income data
    our_income = body.custom_income
    if not our_income:
        our_income = service._load_income_data(loan_id)
        if not our_income:
            raise HTTPException(
                status_code=404,
                detail="No income calculation found for this loan. Calculate income first.",
            )

    # Build the findings dict from the submission
    findings_data = {
        "income_used": submission.income_data_returned or {},
    }

    # Run comparison
    variance_report = service.compare_income_to_findings(
        loan_id=loan_id,
        our_income=our_income,
        findings=findings_data,
    )

    # Persist variance on the submission record
    submission.income_variance = variance_report
    db.commit()

    return {
        "status": "success",
        "data": variance_report,
    }


@router.post("/import-findings/{loan_id}")
async def import_aus_findings(
    loan_id: int,
    body: ImportFindingsRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Import AUS findings and conditions into the loan's compliance alerts.

    Creates ComplianceAlert records from the AUS conditions so they
    appear in the loan's condition tracker for the processor to clear.
    """
    _require_aus_enabled()
    from database.models.aus_submission import AUSSubmission
    from services.smart_docs.integrations.aus_integration_service import (
        AUSIntegrationService,
    )

    org_id = getattr(current_user, "organization_id", None)

    submission = db.query(AUSSubmission).filter(
        AUSSubmission.id == body.submission_id,
        AUSSubmission.organization_id == org_id,
        AUSSubmission.loan_id == loan_id,
    ).first()

    if not submission:
        raise HTTPException(status_code=404, detail="AUS submission not found")

    if submission.submission_status != "complete":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot import from submission with status '{submission.submission_status}'",
        )

    service = AUSIntegrationService(db)
    findings_data = {
        "conditions": submission.conditions or [],
        "findings": submission.findings or [],
    }

    result = service.import_findings(
        loan_id=loan_id,
        findings=findings_data,
        source=submission.aus_type,
    )

    db.commit()

    return {
        "status": "success",
        "data": result,
    }


@router.get("/mismo-preview/{loan_id}")
async def mismo_preview(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Preview the MISMO 3.4 data that would be sent to the AUS.

    Useful for verifying data accuracy before submission. Does NOT
    submit to any AUS — purely a read-only preview.
    """
    _require_aus_enabled()
    from services.smart_docs.integrations.aus_integration_service import (
        AUSIntegrationService,
    )

    org_id = getattr(current_user, "organization_id", None)
    service = AUSIntegrationService(db)

    try:
        mismo_data = service.map_loan_to_mismo(loan_id, org_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "status": "success",
        "data": {
            "loan_id": loan_id,
            "mismo_version": "3.4",
            "preview": mismo_data,
            "note": "This is a preview only. No data has been submitted to any AUS.",
        },
    }
