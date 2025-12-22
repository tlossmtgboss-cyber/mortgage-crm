"""
Pre-Approval Letter Settings Routes
Configure the pre-approval letter content and branding
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import logging
import json

from database import get_db, Base

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


# Database Model
class PreApprovalLetterSettings(Base):
    """Pre-approval letter configuration settings"""
    __tablename__ = "pre_approval_letter_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Company Information
    company_name = Column(String(255), default="")
    company_address = Column(Text, default="")
    company_phone = Column(String(50), default="")
    company_nmls = Column(String(50), default="")

    # Letter Content
    letter_header = Column(String(255), default="Pre-Approval Letter")
    opening_paragraph = Column(Text, default="This letter is to confirm that the below-named borrower(s) have been pre-approved for a mortgage loan based on a preliminary review of their credit and financial information.")
    conditions_intro = Column(String(500), default="This pre-approval is subject to the following conditions:")
    default_conditions = Column(Text, default='["Verification of employment and income","Satisfactory property appraisal","Clear title search","Verification of assets and funds for closing","No material changes to financial condition"]')  # Stored as JSON string
    closing_paragraph = Column(Text, default="This pre-approval is valid for 90 days from the date of this letter. Please note that this is not a commitment to lend and is subject to final underwriting approval.")
    disclaimer = Column(Text, default="This pre-approval letter is based on the information provided by the applicant and is subject to verification. Final loan approval is contingent upon satisfactory completion of all underwriting requirements.")

    # Display Options
    show_nmls = Column(Boolean, default=True)
    show_equal_housing = Column(Boolean, default=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# Pydantic Schemas
class PreApprovalLetterSettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    company_phone: Optional[str] = None
    company_nmls: Optional[str] = None
    letter_header: Optional[str] = None
    opening_paragraph: Optional[str] = None
    conditions_intro: Optional[str] = None
    default_conditions: Optional[List[str]] = None
    closing_paragraph: Optional[str] = None
    disclaimer: Optional[str] = None
    show_nmls: Optional[bool] = None
    show_equal_housing: Optional[bool] = None


class PreApprovalLetterSettingsResponse(BaseModel):
    id: int
    company_name: str
    company_address: str
    company_phone: str
    company_nmls: str
    letter_header: str
    opening_paragraph: str
    conditions_intro: str
    default_conditions: List[str]
    closing_paragraph: str
    disclaimer: str
    show_nmls: bool
    show_equal_housing: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Helper function to get or create settings
def get_or_create_settings(db: Session) -> PreApprovalLetterSettings:
    """Get existing settings or create default ones"""
    settings = db.query(PreApprovalLetterSettings).first()
    if not settings:
        settings = PreApprovalLetterSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def parse_conditions(settings: PreApprovalLetterSettings) -> List[str]:
    """Parse the default_conditions JSON string into a list"""
    if not settings.default_conditions:
        return []
    try:
        if isinstance(settings.default_conditions, list):
            return settings.default_conditions
        return json.loads(settings.default_conditions)
    except (json.JSONDecodeError, TypeError):
        return []


def serialize_conditions(conditions: List[str]) -> str:
    """Serialize the conditions list to JSON string"""
    return json.dumps(conditions)


# Routes
@router.get("/pre-approval-letter")
async def get_pre_approval_letter_settings(db: Session = Depends(get_db)):
    """Get current pre-approval letter settings"""
    settings = get_or_create_settings(db)

    return {
        "id": settings.id,
        "company_name": settings.company_name or "",
        "company_address": settings.company_address or "",
        "company_phone": settings.company_phone or "",
        "company_nmls": settings.company_nmls or "",
        "letter_header": settings.letter_header or "Pre-Approval Letter",
        "opening_paragraph": settings.opening_paragraph or "",
        "conditions_intro": settings.conditions_intro or "",
        "default_conditions": parse_conditions(settings),
        "closing_paragraph": settings.closing_paragraph or "",
        "disclaimer": settings.disclaimer or "",
        "show_nmls": settings.show_nmls if settings.show_nmls is not None else True,
        "show_equal_housing": settings.show_equal_housing if settings.show_equal_housing is not None else True,
        "created_at": settings.created_at,
        "updated_at": settings.updated_at
    }


@router.post("/pre-approval-letter")
async def update_pre_approval_letter_settings(
    updates: PreApprovalLetterSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Update pre-approval letter settings"""
    settings = get_or_create_settings(db)

    update_data = updates.dict(exclude_unset=True)

    for field, value in update_data.items():
        if field == "default_conditions":
            # Serialize conditions list to JSON string
            setattr(settings, field, serialize_conditions(value))
        else:
            setattr(settings, field, value)

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)

    logger.info(f"Pre-approval letter settings updated: {list(update_data.keys())}")

    return {
        "id": settings.id,
        "company_name": settings.company_name or "",
        "company_address": settings.company_address or "",
        "company_phone": settings.company_phone or "",
        "company_nmls": settings.company_nmls or "",
        "letter_header": settings.letter_header or "Pre-Approval Letter",
        "opening_paragraph": settings.opening_paragraph or "",
        "conditions_intro": settings.conditions_intro or "",
        "default_conditions": parse_conditions(settings),
        "closing_paragraph": settings.closing_paragraph or "",
        "disclaimer": settings.disclaimer or "",
        "show_nmls": settings.show_nmls if settings.show_nmls is not None else True,
        "show_equal_housing": settings.show_equal_housing if settings.show_equal_housing is not None else True,
        "created_at": settings.created_at,
        "updated_at": settings.updated_at
    }
