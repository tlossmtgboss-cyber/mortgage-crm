"""Deal Breaker Radar routes — evaluate leads for disqualification flags."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from db import get_db
from services.deal_breaker_service import get_deal_breaker_service
from services.deal_breaker_detector import detect_from_conversation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/deal-breakers", tags=["deal-breakers"])


class EvaluateRequest(BaseModel):
    lead_id: Optional[str] = None
    credit_score: Optional[int] = None
    dti: Optional[float] = None
    ltv: Optional[float] = None
    employment_type: Optional[str] = None
    years_in_current_employment: Optional[int] = None
    property_type: Optional[str] = None
    property_state: Optional[str] = None
    loan_amount: Optional[float] = None
    citizenship_status: Optional[str] = None
    years_since_bankruptcy: Optional[int] = None
    bankruptcy_type: Optional[str] = None
    years_since_foreclosure: Optional[int] = None
    income_verifiable: Optional[bool] = None
    is_veteran: Optional[bool] = False
    is_rural: Optional[bool] = False
    licensed_states: Optional[List[str]] = None


class TranscriptRequest(BaseModel):
    transcript: str
    lead_id: Optional[str] = None


@router.post("/evaluate")
async def evaluate_deal_breakers(request: EvaluateRequest, db=Depends(get_db)):
    """Evaluate borrower data for deal breakers."""
    service = get_deal_breaker_service()

    if request.lead_id and not request.credit_score:
        result = service.evaluate_lead(db, request.lead_id)
    else:
        borrower_data = request.dict(exclude_none=True)
        result = service.evaluate(borrower_data)

    return result.to_dict()


@router.post("/detect-from-transcript")
async def detect_from_transcript(request: TranscriptRequest):
    """Detect deal breaker signals from a conversation transcript."""
    flags = detect_from_conversation(request.transcript)
    return {
        "lead_id": request.lead_id,
        "flags_detected": len(flags),
        "flags": [
            {
                "category": f.category,
                "deal_breaker_name": f.deal_breaker_name,
                "pattern_matched": f.pattern_matched,
                "snippet": f.snippet,
                "confidence": f.confidence,
            }
            for f in flags
        ],
    }
