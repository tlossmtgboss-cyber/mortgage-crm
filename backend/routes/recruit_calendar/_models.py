"""Pydantic models for the recruiting calendar module."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InterviewType(str, Enum):
    PHONE_SCREEN = "phone_screen"
    VIDEO_INTERVIEW = "video_interview"
    IN_PERSON = "in_person"
    PANEL_INTERVIEW = "panel_interview"
    CULTURE_FIT = "culture_fit"
    REFERENCE_CHECK = "reference_check"
    OFFER_CALL = "offer_call"
    TECHNICAL = "technical"


class MilestoneType(str, Enum):
    START_DATE = "start_date"
    DAY_30_CHECKIN = "30_day_checkin"
    DAY_90_CHECKIN = "90_day_checkin"
    LICENSE_RENEWAL = "license_renewal"
    BACKGROUND_CHECK_DUE = "background_check_due"
    ONBOARDING_COMPLETE = "onboarding_complete"
    PROBATION_END = "probation_end"
    CUSTOM = "custom"


class InterviewOutcome(str, Enum):
    PENDING = "pending"
    ADVANCED = "advanced"
    HIRED = "hired"
    REJECTED = "rejected"
    NO_SHOW = "no_show"
    WITHDRAWN = "withdrawn"


# ── Request models ────────────────────────────────────────────────────────────

class InterviewCreate(BaseModel):
    candidate_id: int
    interviewer_user_id: int
    interview_type: InterviewType = InterviewType.PHONE_SCREEN
    scheduled_start: datetime
    scheduled_end: datetime
    location: Optional[str] = None
    zoom_link: Optional[str] = None
    notes: Optional[str] = None
    panel_members: Optional[List[int]] = Field(default_factory=list)
    title: Optional[str] = None


class InterviewUpdate(BaseModel):
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    location: Optional[str] = None
    zoom_link: Optional[str] = None
    notes: Optional[str] = None
    outcome: Optional[InterviewOutcome] = None
    scorecard: Optional[Dict[str, Any]] = None
    interviewer_notes: Optional[str] = None


class InterviewCompleteRequest(BaseModel):
    outcome: InterviewOutcome
    interviewer_notes: Optional[str] = None
    scorecard: Optional[Dict[str, Any]] = Field(default_factory=dict)


class MilestoneCreate(BaseModel):
    candidate_id: int
    milestone_type: MilestoneType
    scheduled_date: Optional[datetime] = None
    assigned_to_user_id: Optional[int] = None
    notes: Optional[str] = None


class MilestoneUpdate(BaseModel):
    scheduled_date: Optional[datetime] = None
    assigned_to_user_id: Optional[int] = None
    notes: Optional[str] = None


class BookingLinkCreate(BaseModel):
    candidate_id: int
    interview_type: InterviewType
    expires_hours: int = Field(default=72, ge=1, le=720)
    title: Optional[str] = None
    interviewer_user_id: Optional[int] = None


class BookingConfirm(BaseModel):
    slot_start: datetime
    slot_end: datetime
    candidate_name: str
    candidate_email: str
    notes: Optional[str] = None
