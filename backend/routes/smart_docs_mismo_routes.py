"""
MISMO Data Mapping API Routes

Endpoints for previewing, exporting, and validating MISMO 3.6 data
for GSE delivery and regulatory compliance.

Routes:
- GET /mismo/preview/{loan_id}      — preview MISMO-mapped data
- GET /mismo/xml/{loan_id}          — generate MISMO 3.6 XML
- GET /mismo/completeness/{loan_id} — check field completeness
- GET /mismo/mcd/{loan_id}          — generate MCD v2.0 report

All routes require authentication and enforce tenant isolation.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from services.smart_docs.integrations.mismo_mapper_service import (
    MISMOMapperService,
    get_mismo_mapper_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MISMO Data Mapping"])


# =============================================================================
# Preview MISMO data
# =============================================================================

@router.get("/mismo/preview/{loan_id}")
async def preview_mismo_data(
    loan_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview MISMO-mapped data for a loan.

    Returns the full MISMO 3.6 data structure as JSON for review
    before XML export. Useful for debugging and data validation.
    """
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    try:
        service = get_mismo_mapper_service(db)
        mismo_data = service.map_loan_to_mismo(loan_id, org_id)
        return {
            "status": "success",
            "loan_id": loan_id,
            "mismo_version": "3.6",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data": mismo_data,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"MISMO preview failed for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to generate MISMO preview")


# =============================================================================
# Generate MISMO XML
# =============================================================================

@router.get("/mismo/xml/{loan_id}")
async def generate_mismo_xml(
    loan_id: int,
    version: str = "3.6",
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate MISMO 3.6 XML for a loan.

    Returns the XML as an application/xml response, suitable for
    GSE delivery or LOS import. Optionally specify MISMO version.
    """
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    try:
        service = get_mismo_mapper_service(db)
        xml_str = service.generate_mismo_xml(loan_id, org_id, version=version)
        return Response(
            content=xml_str,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="MISMO_{loan_id}_{version}.xml"',
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"MISMO XML generation failed for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to generate MISMO XML")


# =============================================================================
# Completeness check
# =============================================================================

@router.get("/mismo/completeness/{loan_id}")
async def check_mismo_completeness(
    loan_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check MISMO field completeness for a loan.

    Returns a breakdown of populated vs. required MISMO fields,
    completeness percentages, and a GSE delivery readiness flag.
    """
    try:
        service = get_mismo_mapper_service(db)
        result = service.validate_mismo_completeness(loan_id)
        return {
            "status": "success",
            **result,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"MISMO completeness check failed for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to check MISMO completeness")


# =============================================================================
# MCD Report
# =============================================================================

@router.get("/mismo/mcd/{loan_id}")
async def generate_mcd_report(
    loan_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate Mortgage Compliance Dataset v2.0 report.

    Required for regulatory exams under the Dec 2025 standard.
    Includes HMDA data points, TRID timing, fee analysis, and
    fair lending indicators.
    """
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    try:
        service = get_mismo_mapper_service(db)
        report = service.generate_mcd_report(loan_id, org_id)
        return {
            "status": "success",
            "loan_id": loan_id,
            "report": report,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"MCD report generation failed for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to generate MCD report")
