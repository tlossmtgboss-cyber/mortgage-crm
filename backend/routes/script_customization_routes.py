"""Script customization routes — per-tenant AI persona, questions, thresholds, and settings."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from db import get_db
from services.script_customization_service import get_script_customization_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/script-config", tags=["script-customization"])


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    voice: Optional[str] = None
    personality: Optional[str] = None
    greeting_style: Optional[str] = None


class QuestionItem(BaseModel):
    id: str
    question: str
    options: Optional[List[str]] = None
    required: bool = True
    order: int = 0
    show_for: Optional[List[str]] = None


class TransferThresholdUpdate(BaseModel):
    min_credit_score: Optional[int] = None
    max_timeline: Optional[str] = None
    loan_types: Optional[List[str]] = None
    require_employment: Optional[bool] = None


class QuietHoursUpdate(BaseModel):
    start: Optional[str] = None  # "21:00"
    end: Optional[str] = None    # "08:00"
    timezone: Optional[str] = None
    weekend_calls: Optional[bool] = None


class DripSettingsUpdate(BaseModel):
    purchase_12_month: Optional[bool] = None
    refinance_12_month: Optional[bool] = None
    post_close: Optional[bool] = None
    reengagement: Optional[bool] = None


@router.get("/config/{organization_id}")
async def get_config(organization_id: str, db=Depends(get_db)):
    """Get full script customization config for an organization."""
    service = get_script_customization_service()
    return service.get_config(db, organization_id)


@router.put("/persona/{organization_id}")
async def update_persona(organization_id: str, request: PersonaUpdate, db=Depends(get_db)):
    """Update AI persona (name, voice, personality)."""
    service = get_script_customization_service()
    return service.update_persona(db, organization_id, request.dict(exclude_none=True))


@router.put("/questions/{organization_id}")
async def update_questions(organization_id: str, questions: List[QuestionItem], db=Depends(get_db)):
    """Update qualifying questions (add, remove, reorder)."""
    service = get_script_customization_service()
    return service.update_questions(db, organization_id, [q.dict() for q in questions])


@router.put("/transfer-threshold/{organization_id}")
async def update_transfer_threshold(organization_id: str, request: TransferThresholdUpdate, db=Depends(get_db)):
    """Update transfer/qualification threshold."""
    service = get_script_customization_service()
    return service.update_transfer_threshold(db, organization_id, request.dict(exclude_none=True))


@router.put("/quiet-hours/{organization_id}")
async def update_quiet_hours(organization_id: str, request: QuietHoursUpdate, db=Depends(get_db)):
    """Update quiet hours (TCPA compliance)."""
    service = get_script_customization_service()
    return service.update_quiet_hours(db, organization_id, request.dict(exclude_none=True))


@router.put("/drip-settings/{organization_id}")
async def update_drip_settings(organization_id: str, request: DripSettingsUpdate, db=Depends(get_db)):
    """Enable/disable drip sequence phases."""
    service = get_script_customization_service()
    return service.update_drip_settings(db, organization_id, request.dict(exclude_none=True))


@router.get("/question-bank")
async def get_question_bank():
    """Get master question bank (all available qualifying questions)."""
    service = get_script_customization_service()
    return {"questions": service.get_question_bank()}
