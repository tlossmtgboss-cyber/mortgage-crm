"""
UVIP - Video Meeting Pydantic Schemas
Extracted from video_meeting_routes.py

All request/response schemas used across video meeting route files.
"""

from datetime import date
from typing import List, Optional, Dict
from pydantic import BaseModel, EmailStr, validator

from video_meeting_models import (
    MeetingRoomStatus, ParticipantRole, ParticipantStatus,
    MeetingProvider, AIAnalysisType,
)


# ============================================================================
# MEETING ROOM SCHEMAS
# ============================================================================

class MeetingRoomCreate(BaseModel):
    room_name: str
    room_description: Optional[str] = None
    provider: str = "internal"
    scheduled_start: Optional[str] = None  # datetime as string
    scheduled_end: Optional[str] = None
    duration_minutes: int = 30
    waiting_room_enabled: bool = True
    recording_enabled: bool = True
    transcription_enabled: bool = True
    ai_assistant_enabled: bool = True
    password_protected: bool = False
    room_password: Optional[str] = None
    max_participants: int = 50
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    appointment_id: Optional[int] = None
    meeting_type: str = "general"
    template_id: Optional[int] = None


class MeetingRoomUpdate(BaseModel):
    room_name: Optional[str] = None
    room_description: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    duration_minutes: Optional[int] = None
    waiting_room_enabled: Optional[bool] = None
    recording_enabled: Optional[bool] = None
    transcription_enabled: Optional[bool] = None
    ai_assistant_enabled: Optional[bool] = None
    password_protected: Optional[bool] = None
    room_password: Optional[str] = None
    max_participants: Optional[int] = None
    status: Optional[MeetingRoomStatus] = None


# ============================================================================
# PARTICIPANT SCHEMAS
# ============================================================================

class ParticipantAdd(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: ParticipantRole = ParticipantRole.PARTICIPANT
    send_invite: bool = True


class ParticipantUpdate(BaseModel):
    role: Optional[ParticipantRole] = None
    status: Optional[ParticipantStatus] = None
    can_share_screen: Optional[bool] = None
    can_unmute: Optional[bool] = None
    can_chat: Optional[bool] = None


# ============================================================================
# TEMPLATE SCHEMAS
# ============================================================================

class MeetingTemplateCreate(BaseModel):
    template_name: str
    template_key: str
    description: Optional[str] = None
    default_duration_minutes: int = 30
    waiting_room_enabled: bool = True
    recording_enabled: bool = True
    transcription_enabled: bool = True
    ai_assistant_enabled: bool = True
    default_agenda: Optional[List[Dict]] = None
    color: str = "#3b82f6"
    icon: str = "video"


class MeetingTemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    description: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    waiting_room_enabled: Optional[bool] = None
    recording_enabled: Optional[bool] = None
    transcription_enabled: Optional[bool] = None
    ai_assistant_enabled: Optional[bool] = None
    default_agenda: Optional[List[Dict]] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None


# ============================================================================
# AI ANALYSIS SCHEMAS
# ============================================================================

class AvailableSlotsRequest(BaseModel):
    start_date: date
    end_date: date
    duration_minutes: int = 30


class AIAnalysisRequest(BaseModel):
    analysis_types: List[AIAnalysisType] = [AIAnalysisType.SUMMARY, AIAnalysisType.ACTION_ITEMS]
    custom_prompt: Optional[str] = None


# ============================================================================
# MEETING INVITE / WAITING ROOM SCHEMAS
# ============================================================================

class MeetingInviteRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    join_url: str
    meeting_name: Optional[str] = "Video Meeting"
    host_name: Optional[str] = None


class WaitingRoomRequest(BaseModel):
    display_name: str
    email: Optional[str] = None


class AdmitParticipantRequest(BaseModel):
    action: str  # "admit" or "reject"


# ============================================================================
# RECORDING CONSENT SCHEMAS
# ============================================================================

class StartRecordingRequest(BaseModel):
    consent_type: Optional[str] = None  # "all_party" or "one_party"
    state_code: Optional[str] = None
    disclosure_script: Optional[str] = None


class RecordingConsentRequest(BaseModel):
    consent_given: bool
    method: str = "dialog_click"  # "dialog_click", "verbal", "implied"


# ============================================================================
# ORGANIZATION SETTINGS SCHEMAS
# ============================================================================

class OrgVideoSettingsUpdate(BaseModel):
    recording_allowed: Optional[bool] = None
    recording_consent_required: Optional[bool] = None
    default_consent_type: Optional[str] = None
    default_waiting_room: Optional[bool] = None
    max_participants: Optional[int] = None
    allowed_providers: Optional[List[MeetingProvider]] = None

    @validator('default_consent_type')
    def validate_consent_type(cls, v):
        if v is not None and v not in ('one_party', 'two_party', 'all_party'):
            raise ValueError("consent_type must be one_party, two_party, or all_party")
        return v


# ============================================================================
# BREAKOUT ROOM SCHEMAS
# ============================================================================

class BreakoutRoomCreate(BaseModel):
    room_name: str
    max_participants: Optional[int] = 10
    duration_limit_minutes: Optional[int] = None
