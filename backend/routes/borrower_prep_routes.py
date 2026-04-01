"""Borrower prep sequence routes — create, monitor, and manage pre-appointment prep flows."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from db import get_db
from services.borrower_prep_service import BorrowerPrepService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/borrower-prep", tags=["borrower-prep"])

_service = BorrowerPrepService()


class CreatePrepRequest(BaseModel):
    lead_id: str
    appointment_type: str  # pre_approval_consult, rate_lock_call, closing_prep
    appointment_time: str  # ISO datetime
    lo_name: Optional[str] = None
    lo_phone: Optional[str] = None
    organization_id: Optional[str] = None


@router.post("/create/{appointment_id}")
async def create_prep_sequence(appointment_id: str, request: CreatePrepRequest, db=Depends(get_db)):
    """Create a borrower prep sequence for an upcoming appointment."""
    from datetime import datetime as dt
    try:
        appt_time = dt.fromisoformat(request.appointment_time)
    except ValueError:
        return {"error": "Invalid appointment_time format. Use ISO format."}

    result = _service.create_prep_sequence(
        db=db,
        appointment_id=appointment_id,
        lead_id=request.lead_id,
        appointment_type=request.appointment_type,
        appointment_time=appt_time,
        org_id=request.organization_id or "",
    )
    return result


@router.get("/{appointment_id}/status")
async def get_prep_status(appointment_id: str, db=Depends(get_db)):
    """Get status of a borrower prep sequence."""
    result = _service.get_sequence_status(db, appointment_id)
    return result


@router.get("/readiness/{lead_id}")
async def check_readiness(lead_id: str, appointment_type: str = "pre_approval_consult", db=Depends(get_db)):
    """Check document readiness for a lead before an appointment."""
    result = _service.check_document_readiness(db, lead_id, appointment_type)
    return result


@router.delete("/{appointment_id}")
async def cancel_prep_sequence(appointment_id: str, db=Depends(get_db)):
    """Cancel a borrower prep sequence."""
    result = _service.cancel_prep_sequence(db, appointment_id)
    return result


@router.get("/types")
async def list_appointment_types():
    """List all supported appointment types and their prep configs."""
    from services.borrower_prep_service import APPOINTMENT_PREP_CONFIGS
    return {
        "types": [
            {
                "key": key,
                "display_name": config["display_name"],
                "required_docs_count": len(config["required_docs"]),
                "prep_steps_count": len(config["prep_timeline"]),
            }
            for key, config in APPOINTMENT_PREP_CONFIGS.items()
        ]
    }
