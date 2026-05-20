"""
Smart Docs IRS Transcript Routes

Endpoints for IRS 4506-C transcript requests, imports, and income verification
comparisons. Supports Fannie Mae income verification requirements by comparing
borrower-submitted tax returns and W-2s against IRS transcript data.

Endpoints:
    POST /transcript/request/{loan_id}    - Request IRS transcript
    GET  /transcript/{request_id}/status  - Check request status
    POST /transcript/{request_id}/import  - Import transcript data
    POST /transcript/compare/{loan_id}    - Compare transcript to submitted docs
    GET  /transcript/4506c/{loan_id}      - Generate 4506-C form
    GET  /transcript/history/{loan_id}    - Comparison history

All endpoints require authentication and enforce tenant isolation.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_async_db

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IRS Transcript"])


# =============================================================================
# Pydantic Models
# =============================================================================

class TranscriptRequestBody(BaseModel):
    """Request body for creating a transcript request."""
    tax_years: List[int] = Field(..., min_length=1, description="Tax years to request (e.g. [2024, 2025])")
    transcript_type: str = Field(default="tax_return", description="tax_return, wage_income, or account")
    vendor: Optional[str] = Field(default=None, description="Vendor: ives, taxstatus, manual")


class TranscriptImportBody(BaseModel):
    """Request body for importing transcript data."""
    transcript_data: dict = Field(..., description="Parsed transcript fields from IRS/vendor")
    vendor: Optional[str] = Field(default=None, description="Vendor source override")


class TranscriptCompareBody(BaseModel):
    """Request body for comparing transcript to submitted documents."""
    tax_year: int = Field(..., description="Tax year to compare")
    comparison_type: str = Field(default="tax_return", description="tax_return or w2")


class Form4506CRequestBody(BaseModel):
    """Request body for generating a 4506-C form."""
    borrower_id: int = Field(..., description="Borrower/lead ID")
    tax_years: List[int] = Field(..., min_length=1, description="Tax years for the form")


# =============================================================================
# Helper: get service
# =============================================================================

def _get_service(db: Session):
    """Lazily import and instantiate the IRS transcript service."""
    from services.smart_docs.integrations.irs_transcript_service import IRSTranscriptService
    return IRSTranscriptService(db)


# =============================================================================
# Routes
# =============================================================================

@router.post("/transcript/request/{loan_id}")
async def request_transcript(
    loan_id: int,
    body: TranscriptRequestBody,
    borrower_id: int = Query(..., description="Borrower/lead ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Request an IRS transcript for income verification.

    Creates a 4506-C request record. In production, this would also submit
    the request to IRS IVES or a third-party vendor.
    """
    try:
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        user_id = getattr(current_user, "id", None)

        service = _get_service(db)
        result = service.request_transcript(
            borrower_id=borrower_id,
            loan_id=loan_id,
            org_id=org_id,
            tax_years=body.tax_years,
            transcript_type=body.transcript_type,
            vendor=body.vendor,
            requested_by_user_id=user_id,
        )

        return {
            "status": "success",
            "data": {
                "request_id": result.request_id,
                "loan_id": result.loan_id,
                "borrower_id": result.borrower_id,
                "tax_years": result.tax_years,
                "transcript_type": result.transcript_type,
                "status": result.status,
                "requested_at": result.requested_at.isoformat() if result.requested_at else None,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error creating transcript request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create transcript request")


@router.get("/transcript/{request_id}/status")
async def get_transcript_status(
    request_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Check the status of a transcript request."""
    try:
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        service = _get_service(db)
        result = service.get_transcript_status(request_id=request_id, org_id=org_id)

        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error checking transcript status: {e}")
        raise HTTPException(status_code=500, detail="Failed to check transcript status")


@router.post("/transcript/{request_id}/import")
async def import_transcript(
    request_id: int,
    body: TranscriptImportBody,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Import transcript data received from IRS/vendor or manual entry.

    Updates the transcript request with the received data and sets status
    to 'received'.
    """
    try:
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        service = _get_service(db)
        result = service.import_transcript(
            request_id=request_id,
            org_id=org_id,
            transcript_data=body.transcript_data,
            vendor=body.vendor,
        )

        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error importing transcript: {e}")
        raise HTTPException(status_code=500, detail="Failed to import transcript")


@router.post("/transcript/compare/{loan_id}")
async def compare_transcript(
    loan_id: int,
    body: TranscriptCompareBody,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Compare IRS transcript against borrower-submitted documents.

    Performs a field-by-field comparison of income data. Returns pass/fail
    with discrepancy details.
    """
    try:
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        service = _get_service(db)

        if body.comparison_type == "w2":
            comparison = service.compare_to_w2(
                loan_id=loan_id,
                tax_year=body.tax_year,
                org_id=org_id,
            )
        else:
            comparison = service.compare_to_tax_return(
                loan_id=loan_id,
                tax_year=body.tax_year,
                org_id=org_id,
            )

        return {
            "status": "success",
            "data": {
                "passed": comparison.passed,
                "tax_year": comparison.tax_year,
                "summary": comparison.summary,
                "comparison_date": comparison.comparison_date.isoformat() if comparison.comparison_date else None,
                "discrepancies": [
                    {
                        "field": d.field_name,
                        "submitted_value": d.submitted_value,
                        "transcript_value": d.transcript_value,
                        "difference": d.difference,
                        "variance_pct": d.variance_pct,
                        "severity": d.severity,
                    }
                    for d in comparison.discrepancies
                ],
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error comparing transcript: {e}")
        raise HTTPException(status_code=500, detail="Failed to compare transcript")


@router.get("/transcript/4506c/{loan_id}")
async def generate_4506c_form(
    loan_id: int,
    borrower_id: int = Query(..., description="Borrower/lead ID"),
    tax_years: str = Query(..., description="Comma-separated tax years, e.g. '2024,2025'"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Generate a pre-filled IRS Form 4506-C as PDF.

    Returns a PDF with borrower name, address, and tax years pre-filled.
    Borrower must review, sign, and date before submission.
    """
    try:
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        # Parse tax years from comma-separated string
        try:
            years = [int(y.strip()) for y in tax_years.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="tax_years must be comma-separated integers (e.g. '2024,2025')",
            )

        service = _get_service(db)
        pdf_bytes = service.generate_4506c_form(
            borrower_id=borrower_id,
            loan_id=loan_id,
            org_id=org_id,
            tax_years=years,
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="4506C_loan_{loan_id}.pdf"',
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error generating 4506-C: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate 4506-C form")


@router.get("/transcript/history/{loan_id}")
async def get_comparison_history(
    loan_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Get all transcript comparison results for a loan."""
    try:
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        service = _get_service(db)
        history = service.get_comparison_history(loan_id=loan_id, org_id=org_id)

        return {
            "status": "success",
            "data": {
                "loan_id": loan_id,
                "total": len(history),
                "requests": history,
            },
        }
    except SQLAlchemyError as e:
        logger.exception(f"Database error fetching transcript history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch transcript history")
