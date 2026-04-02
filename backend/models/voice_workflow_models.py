"""
Voice Workflow Models for Conversational AI Task Completion

Pydantic models and enums for the voice-driven workflow system that enables
loan officers to complete tasks through natural two-way conversations.
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import UUID


# =============================================================================
# Workflow Types and States
# =============================================================================

class WorkflowType(str, Enum):
    """Available workflow types"""
    PRE_APPROVAL_LETTER = "pre_approval_letter"
    SCHEDULE_APPOINTMENT = "schedule_appointment"
    CREATE_TASK = "create_task"
    SEND_EMAIL = "send_email"
    UPDATE_LOAN_STATUS = "update_loan_status"


class PreApprovalWorkflowState(str, Enum):
    """States for pre-approval letter workflow"""
    INTENT_DETECTED = "intent_detected"
    SELECT_APPLICANT = "select_applicant"
    REVIEW_TERMS = "review_terms"
    ADD_PROPERTY = "add_property"
    SELECT_REALTOR = "select_realtor"
    FINAL_CONFIRMATION = "final_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class UserIntent(str, Enum):
    """User intents extracted from voice input"""
    SELECT = "select"           # User is selecting an option
    MODIFY = "modify"           # User wants to change something
    CONFIRM = "confirm"         # User is confirming
    CANCEL = "cancel"           # User wants to cancel
    SKIP = "skip"               # User wants to skip current step
    HELP = "help"               # User needs help/clarification
    REPEAT = "repeat"           # User wants to hear options again
    GO_BACK = "go_back"         # User wants to go to previous step


# =============================================================================
# Slot Schemas
# =============================================================================

class PreApprovalLetterSlots(BaseModel):
    """Slots for pre-approval letter workflow"""
    # Applicant selection
    applicant_id: Optional[int] = None
    applicant_name: Optional[str] = None

    # Loan terms (pre-populated from loan data, can be modified)
    loan_type: Optional[str] = None
    pre_approved_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None  # 15, 20, 30 years

    # Optional property info
    property_address: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None

    # Realtor recipient
    realtor_id: Optional[int] = None
    realtor_name: Optional[str] = None
    realtor_email: Optional[str] = None
    realtor_company: Optional[str] = None

    class Config:
        extra = "allow"  # Allow additional fields for flexibility


class ScheduleAppointmentSlots(BaseModel):
    """Slots for schedule appointment workflow"""
    contact_id: Optional[int] = None
    contact_name: Optional[str] = None
    contact_type: Optional[str] = None  # borrower, realtor, etc.

    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    duration_minutes: Optional[int] = 30

    meeting_type: Optional[str] = None  # call, video, in-person
    location: Optional[str] = None
    notes: Optional[str] = None


class CreateTaskSlots(BaseModel):
    """Slots for create task workflow"""
    task_title: Optional[str] = None
    task_description: Optional[str] = None

    due_date: Optional[str] = None
    priority: Optional[str] = None  # high, medium, low

    related_loan_id: Optional[int] = None
    related_contact_id: Optional[int] = None
    assigned_to: Optional[int] = None


# =============================================================================
# Conversation Models
# =============================================================================

class ConversationTurn(BaseModel):
    """A single turn in the conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audio_duration_ms: Optional[int] = None
    intent: Optional[UserIntent] = None
    slots_extracted: Optional[Dict[str, Any]] = None


class SlotExtractionResult(BaseModel):
    """Result from Claude slot extraction"""
    intent: UserIntent
    confidence: float = Field(ge=0, le=1)
    extracted_slots: Dict[str, Any] = Field(default_factory=dict)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    matched_option_index: Optional[int] = None  # For option selection


class VoiceResponseContext(BaseModel):
    """Context for generating voice responses"""
    workflow_type: WorkflowType
    current_state: str
    slots: Dict[str, Any]
    available_options: Optional[List[Dict[str, Any]]] = None
    error_message: Optional[str] = None
    is_final_confirmation: bool = False


# =============================================================================
# Session Models
# =============================================================================

class VoiceWorkflowSession(BaseModel):
    """Active voice workflow session"""
    id: UUID
    user_id: int
    workflow_type: WorkflowType
    current_state: str
    slots: Dict[str, Any] = Field(default_factory=dict)
    conversation_history: List[ConversationTurn] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

    # Cached context data
    available_applicants: Optional[List[Dict[str, Any]]] = None
    available_realtors: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True


class WorkflowSessionCreate(BaseModel):
    """Request to create a new workflow session"""
    workflow_type: WorkflowType
    initial_transcript: Optional[str] = None


class WorkflowSessionUpdate(BaseModel):
    """Request to update workflow session"""
    user_transcript: str
    audio_duration_ms: Optional[int] = None


# =============================================================================
# WebSocket Message Models
# =============================================================================

class WebSocketMessageType(str, Enum):
    """Types of WebSocket messages"""
    # Client -> Server
    AUDIO = "audio"
    TEXT_INPUT = "text_input"
    CANCEL_WORKFLOW = "cancel_workflow"

    # Server -> Client
    WORKFLOW_STARTED = "workflow_started"
    STATE_CHANGED = "state_changed"
    RESPONSE_AUDIO = "response_audio"
    RESPONSE_TEXT = "response_text"
    SLOTS_UPDATED = "slots_updated"
    OPTIONS_AVAILABLE = "options_available"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    ERROR = "error"


class ClientMessage(BaseModel):
    """Message from client to server"""
    type: WebSocketMessageType
    data: Optional[str] = None  # Base64 audio or text
    text: Optional[str] = None  # For text_input type


class ServerMessage(BaseModel):
    """Message from server to client"""
    type: WebSocketMessageType
    workflow_id: Optional[str] = None
    current_state: Optional[str] = None
    slots_collected: Optional[Dict[str, Any]] = None

    # For audio/text responses
    audio_data: Optional[str] = None  # Base64 encoded
    text: Optional[str] = None

    # For options
    options: Optional[List[Dict[str, Any]]] = None

    # For completion/errors
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# =============================================================================
# Execution Result Models
# =============================================================================

class PreApprovalLetterResult(BaseModel):
    """Result of pre-approval letter execution"""
    success: bool
    letter_id: Optional[int] = None
    pdf_url: Optional[str] = None
    email_sent: bool = False
    sent_to: Optional[str] = None
    sent_at: Optional[datetime] = None
    error: Optional[str] = None


class WorkflowExecutionResult(BaseModel):
    """Generic workflow execution result"""
    success: bool
    workflow_type: WorkflowType
    result_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# CRM Data Models (for voice context)
# =============================================================================

class ApplicantVoiceContext(BaseModel):
    """Applicant data optimized for voice presentation"""
    id: int
    name: str
    loan_amount: float
    loan_amount_formatted: str
    loan_type: str
    loan_status: str
    interest_rate: Optional[float] = None

    # For voice script
    voice_description: str  # e.g., "John Smith with a $450,000 conventional loan"


class RealtorVoiceContext(BaseModel):
    """Realtor data optimized for voice presentation"""
    id: int
    name: str
    company: Optional[str] = None
    email: str
    phone: Optional[str] = None

    # For voice script
    voice_description: str  # e.g., "Sarah Martinez at Coldwell Banker"


# =============================================================================
# Response Templates
# =============================================================================

class VoicePromptTemplates:
    """Templates for voice prompts by state"""

    @staticmethod
    def select_applicant_single(applicant: ApplicantVoiceContext) -> str:
        return f"I found one active applicant: {applicant.voice_description}. Is this correct?"

    @staticmethod
    def select_applicant_multiple(applicants: List[ApplicantVoiceContext]) -> str:
        if len(applicants) <= 3:
            descriptions = ", ".join([a.voice_description for a in applicants[:-1]])
            descriptions += f", and {applicants[-1].voice_description}"
        else:
            descriptions = ", ".join([a.voice_description for a in applicants[:3]])
            descriptions += f", and {len(applicants) - 3} more"
        return f"I found {len(applicants)} applicants. {descriptions}. Which one needs the letter?"

    @staticmethod
    def review_terms(name: str, amount: float, loan_type: str, rate: float) -> str:
        amount_formatted = f"${amount:,.0f}"
        return f"{name} is pre-approved for {amount_formatted} on a {loan_type} at {rate}%. Would you like to make any changes?"

    @staticmethod
    def add_property_prompt() -> str:
        return "Would you like to add a property address to the letter?"

    @staticmethod
    def select_realtor_prompt() -> str:
        return "Which realtor should I send this to?"

    @staticmethod
    def final_confirmation(
        applicant_name: str,
        amount: float,
        realtor_name: str,
        realtor_company: Optional[str] = None
    ) -> str:
        amount_formatted = f"${amount:,.0f}"
        realtor_full = f"{realtor_name} at {realtor_company}" if realtor_company else realtor_name
        return f"I'll send a pre-approval letter for {applicant_name} for {amount_formatted} to {realtor_full}. Send it now?"

    @staticmethod
    def completed(realtor_name: str) -> str:
        return f"Done! Letter sent to {realtor_name}."

    @staticmethod
    def cancelled() -> str:
        return "Pre-approval letter cancelled. Is there anything else you need?"
