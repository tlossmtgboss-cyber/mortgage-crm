"""Pydantic schemas for telephony module"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

# Note: Using string enums to match current implementation in main.py
# When migrating to UUID models, import from telephony.models instead


class SessionStatus:
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class TaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    SKIPPED = "skipped"


class CallOutcome:
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    SKIPPED = "skipped"


class VerificationStatus:
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


def validate_phone_number(v: str) -> str:
    """Normalize phone number to E.164 format"""
    if not v:
        return v
    digits = re.sub(r'\D', '', v)
    if not digits.startswith('1') and len(digits) == 10:
        digits = '1' + digits
    if len(digits) != 11:
        raise ValueError('Phone number must be 10 digits (plus country code)')
    return '+' + digits


# =============================================================================
# Agent Telephony Settings
# =============================================================================

class AgentTelephonySettingsBase(BaseModel):
    cell_phone: Optional[str] = None
    business_caller_id: Optional[str] = None
    dialer_enabled: bool = True
    max_calls_per_day: int = 100
    auto_advance: bool = True
    pause_between_calls: int = 3

    @validator('cell_phone', 'business_caller_id', pre=True)
    def validate_phone(cls, v):
        if v:
            return validate_phone_number(v)
        return v


class AgentTelephonySettingsCreate(AgentTelephonySettingsBase):
    pass


class AgentTelephonySettingsUpdate(BaseModel):
    cell_phone: Optional[str] = None
    business_caller_id: Optional[str] = None
    dialer_enabled: Optional[bool] = None
    max_calls_per_day: Optional[int] = None
    auto_advance: Optional[bool] = None
    pause_between_calls: Optional[int] = None

    @validator('cell_phone', 'business_caller_id', pre=True)
    def validate_phone(cls, v):
        if v:
            return validate_phone_number(v)
        return v


class VerifiedCallerIdInfo(BaseModel):
    phone: str
    name: str
    is_default: bool = False


class AgentTelephonySettingsResponse(AgentTelephonySettingsBase):
    user_id: int
    verified_caller_ids: List[VerifiedCallerIdInfo] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# Click-to-Dial
# =============================================================================

class ClickToDialRequest(BaseModel):
    phone_number: str
    contact_name: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    task_id: Optional[int] = None
    caller_id: Optional[str] = None

    @validator('phone_number')
    def validate_phone(cls, v):
        return validate_phone_number(v)


class ContactInfo(BaseModel):
    name: str
    phone: str
    context: Optional[str] = None


class ClickToDialResponse(BaseModel):
    success: bool
    call_sid: Optional[str] = None
    contact_name: str
    contact_phone: str
    error: Optional[str] = None


# =============================================================================
# Dialer Sessions
# =============================================================================

class StartSessionRequest(BaseModel):
    task_ids: List[int]
    caller_id: Optional[str] = None


class StartSessionResponse(BaseModel):
    success: bool
    session_id: Optional[int] = None
    status: Optional[str] = None
    total_tasks: int = 0
    error: Optional[str] = None


class CurrentTaskInfo(BaseModel):
    id: int
    contact_name: str
    contact_phone: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    call_sid: Optional[str] = None


class NextTaskPreview(BaseModel):
    id: int
    task_id: Optional[int] = None
    contact_name: str
    contact_phone: str
    position: int
    attempts: int = 0


class SessionStatusResponse(BaseModel):
    session_id: int
    status: str
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
    no_answer_tasks: int
    failed_tasks: int
    skipped_tasks: int
    current_task: Optional[CurrentTaskInfo] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


class SessionDetailResponse(BaseModel):
    session_id: int
    status: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    skipped_tasks: int
    current_task: Optional[CurrentTaskInfo] = None
    next_tasks: List[NextTaskPreview] = []


# =============================================================================
# Dispositions
# =============================================================================

class DispositionFlags(BaseModel):
    follow_up_required: bool = False
    referral_opportunity: bool = False
    appointment_set: bool = False


class DispositionRequest(BaseModel):
    disposition: str
    notes: Optional[str] = None
    schedule_callback: Optional[datetime] = None
    voice_note_audio: Optional[str] = None  # Base64 encoded audio for transcription
    flags: DispositionFlags = DispositionFlags()


class TaskCreated(BaseModel):
    id: int
    type: str
    due_date: Optional[datetime] = None


class DispositionResponse(BaseModel):
    success: bool
    task_id: int
    disposition: str
    ai_note_summary: Optional[str] = None
    task_created: Optional[TaskCreated] = None


# =============================================================================
# Call Logs & Analytics
# =============================================================================

class CallLogEntry(BaseModel):
    id: int
    contact_phone: str
    contact_name: Optional[str] = None
    direction: str = "outbound"
    duration_seconds: Optional[int] = None
    outcome: Optional[str] = None
    disposition: Optional[str] = None
    notes: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None

    class Config:
        from_attributes = True


class CallLogsResponse(BaseModel):
    call_logs: List[CallLogEntry]
    total: int = 0


class DailySummaryResponse(BaseModel):
    date: str
    total_calls: int
    total_talk_time_minutes: int
    connect_rate: float
    average_call_duration_seconds: int
    dispositions: dict


# =============================================================================
# Caller ID Verification
# =============================================================================

class VerifyCallerIdRequest(BaseModel):
    phone_number: str
    friendly_name: str

    @validator('phone_number')
    def validate_phone(cls, v):
        return validate_phone_number(v)


class VerifyCallerIdResponse(BaseModel):
    success: bool
    validation_code: Optional[str] = None
    call_sid: Optional[str] = None
    phone_number: Optional[str] = None
    friendly_name: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


class CallerIdResponse(BaseModel):
    id: Optional[int] = None
    sid: Optional[str] = None
    phone_number: str
    friendly_name: str
    verification_status: str = "pending"
    verified_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CallerIdListResponse(BaseModel):
    caller_ids: List[CallerIdResponse]


# =============================================================================
# Compliance
# =============================================================================

class ComplianceCheckRequest(BaseModel):
    phone_number: str

    @validator('phone_number')
    def validate_phone(cls, v):
        return validate_phone_number(v)


class ComplianceCheckResponse(BaseModel):
    can_call: bool
    phone_number: str
    issues: List[str] = []
    warnings: List[str] = []
    timezone_info: Optional[str] = None


class AddToDNCRequest(BaseModel):
    phone_number: str
    reason: str = "customer_request"

    @validator('phone_number')
    def validate_phone(cls, v):
        return validate_phone_number(v)


class DNCResponse(BaseModel):
    success: bool
    message: str
    phone_number: Optional[str] = None
