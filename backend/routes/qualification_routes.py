"""Mortgage qualification routes — program eligibility, scoring, document checklists."""
import logging
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.mortgage_qualification_engine import (
    evaluate_qualification,
    get_eligible_programs,
    get_required_documents,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qualification", tags=["qualification"])


class QualificationRequest(BaseModel):
    credit_score: int = 0
    dti: Optional[float] = None
    ltv: Optional[float] = None
    loan_amount: Optional[float] = None
    income_type: str = "w2"
    property_type: str = "single_family"
    property_state: str = ""
    is_veteran: bool = False
    is_rural: bool = False
    is_first_time_buyer: bool = False
    years_employed: Optional[int] = None


class ProgramRequest(BaseModel):
    credit_score: int = 0
    dti: Optional[float] = None
    ltv: Optional[float] = None
    loan_amount: Optional[float] = None
    income_type: str = "w2"
    property_type: str = "single_family"
    is_veteran: bool = False
    is_rural: bool = False


@router.post("/evaluate")
async def evaluate(request: QualificationRequest):
    """Full qualification evaluation across all loan programs."""
    result = evaluate_qualification(
        credit_score=request.credit_score,
        dti=request.dti,
        ltv=request.ltv,
        loan_amount=Decimal(str(request.loan_amount)) if request.loan_amount else None,
        income_type=request.income_type,
        property_type=request.property_type,
        property_state=request.property_state,
        is_veteran=request.is_veteran,
        is_rural=request.is_rural,
        is_first_time_buyer=request.is_first_time_buyer,
        years_employed=request.years_employed,
    )
    return result.to_dict()


@router.post("/programs")
async def eligible_programs(request: ProgramRequest):
    """Get eligible loan programs for given criteria."""
    programs = get_eligible_programs(
        credit_score=request.credit_score,
        dti=request.dti,
        ltv=request.ltv,
        loan_amount=Decimal(str(request.loan_amount)) if request.loan_amount else None,
        income_type=request.income_type,
        property_type=request.property_type,
        is_veteran=request.is_veteran,
        is_rural=request.is_rural,
    )
    return {
        "programs": [
            {"program": p.program, "eligible": p.eligible, "reasons": p.reasons,
             "conditions": p.conditions, "notes": p.notes,
             "min_down_payment_pct": float(p.min_down_payment_pct) if p.min_down_payment_pct else None,
             "max_dti": p.max_dti}
            for p in programs
        ]
    }


@router.get("/documents/{income_type}/{program}")
async def document_checklist(income_type: str, program: str):
    """Get required document checklist for income type and loan program."""
    docs = get_required_documents(income_type, program)
    return {"income_type": income_type, "program": program, "documents": docs}
