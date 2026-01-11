"""
Voice Co-Presenter Models
Models for the AI Voice Co-Presenter feature in video conferences.
Includes: Call Sessions, Rate Sheets, Scenarios, Training System, AI Event Logging
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class CallSessionStatus(str, Enum):
    SCHEDULED = "scheduled"
    WAITING = "waiting"
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


class VideoProvider(str, Enum):
    DAILY = "daily"
    TWILIO = "twilio"
    AGORA = "agora"
    INTERNAL = "internal"


class AIMode(str, Enum):
    SILENT = "silent"
    PRESENTER = "presenter"
    QNA = "qna"


class TabType(str, Enum):
    PROCESS = "process"
    PROGRAMS = "programs"
    RATES = "rates"
    COMPARISON = "comparison"
    CLOSING_COSTS = "closing_costs"


class RateSheetStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class LoanProductFamily(str, Enum):
    AGENCY = "AGENCY"
    GOV = "GOV"
    JUMBO = "JUMBO"
    NON_QM = "NON_QM"


class TrainingSourceType(str, Enum):
    YOUTUBE = "YOUTUBE"
    PDF = "PDF"
    TEXT = "TEXT"
    RECORDING = "RECORDING"


class TrainingSourceStatus(str, Enum):
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    INGESTED = "INGESTED"
    FAILED = "FAILED"


class PlaybookModule(str, Enum):
    AGENDA = "AGENDA"
    DISCOVERY = "DISCOVERY"
    OPTIONS = "OPTIONS"
    TRADEOFFS = "TRADEOFFS"
    DECISION = "DECISION"
    NEXT_STEPS = "NEXT_STEPS"


class AIEventType(str, Enum):
    TRANSCRIPT_SEGMENT = "TRANSCRIPT_SEGMENT"
    AI_UTTERANCE = "AI_UTTERANCE"
    TAB_CHANGED = "TAB_CHANGED"
    TOOL_CALL = "TOOL_CALL"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    ACTION_APPROVED = "ACTION_APPROVED"
    ACTION_REJECTED = "ACTION_REJECTED"
    PACKET_PUBLISHED = "PACKET_PUBLISHED"


class PendingActionType(str, Enum):
    SELECT_RATE = "SELECT_RATE"
    UPDATE_ASSUMPTION = "UPDATE_ASSUMPTION"
    SET_RECOMMENDED = "SET_RECOMMENDED"
    DRAFT_PACKET = "DRAFT_PACKET"


class PendingActionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# =============================================================================
# CALL SESSION MODELS
# =============================================================================

class ParticipantInfo(BaseModel):
    user_id: str
    role: str  # "lo" | "borrower" | "realtor"
    joined_at: datetime
    left_at: Optional[datetime] = None
    display_name: Optional[str] = None


class CallSessionBase(BaseModel):
    client_id: str
    provider: VideoProvider = VideoProvider.DAILY
    context_type: str = "client"  # "client" | "lead" | "unknown"


class CallSessionCreate(CallSessionBase):
    pass


class CallSessionUpdate(BaseModel):
    active_tab: Optional[TabType] = None
    ai_enabled: Optional[bool] = None
    ai_mode: Optional[AIMode] = None
    active_playbook_id: Optional[str] = None
    state_snapshot: Optional[Dict[str, Any]] = None


class CallSessionResponse(CallSessionBase):
    id: str
    created_by_user_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    channel_id: str
    active_tab: TabType = TabType.PROCESS
    ai_enabled: bool = False
    ai_mode: AIMode = AIMode.SILENT
    active_playbook_id: Optional[str] = None
    participants: List[ParticipantInfo] = []
    state_snapshot: Dict[str, Any] = {}
    recording_url: Optional[str] = None
    recording_duration: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# RATE SHEET MODELS
# =============================================================================

class RateSheetBase(BaseModel):
    name: str
    branch_code: Optional[str] = None
    effective_at: datetime
    expires_at: Optional[datetime] = None
    source: str = "upload"  # "upload" | "email"
    price_cap_discount: float = 4.0
    price_cap_credit: float = -4.0


class RateSheetCreate(RateSheetBase):
    pass


class RateSheetResponse(RateSheetBase):
    id: str
    uploaded_by_user_id: str
    raw_file_url: str
    status: RateSheetStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RateProductBase(BaseModel):
    family: LoanProductFamily
    program: str  # "30 Year Fixed" | "15 Year Fixed" | etc.
    program_code: Optional[str] = None
    term: str  # "30Y" | "15Y" | "5/6"


class RateProductResponse(RateProductBase):
    id: str
    rate_sheet_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RateLockResponse(BaseModel):
    id: str
    rate_product_id: str
    lock_days: int  # 15, 21, 30, 45, 60
    created_at: datetime

    model_config = {"from_attributes": True}


class RateRowBase(BaseModel):
    rate: float  # e.g., 5.625
    price: float  # e.g., -0.391 (credit) or +0.173 (points)


class RateRowResponse(RateRowBase):
    id: str
    rate_lock_id: str
    is_par: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class RateLadderRequest(BaseModel):
    rate_sheet_id: str
    product_family: LoanProductFamily
    program: str
    lock_days: int = 30


class RateLadderResponse(BaseModel):
    rate_sheet_id: str
    rate_sheet_name: str
    effective_at: datetime
    product_family: LoanProductFamily
    program: str
    lock_days: int
    rates: List[RateRowResponse]


# =============================================================================
# SCENARIO & DECISION PACKET MODELS
# =============================================================================

class ScenarioBase(BaseModel):
    name: str
    program_id: str
    rate_row_id: str
    loan_amount: float


class ScenarioCreate(ScenarioBase):
    client_id: str
    call_session_id: Optional[str] = None


class ScenarioUpdate(BaseModel):
    name: Optional[str] = None
    program_id: Optional[str] = None
    rate_row_id: Optional[str] = None
    loan_amount: Optional[float] = None
    is_recommended: Optional[bool] = None


class ScenarioResponse(ScenarioBase):
    id: str
    decision_packet_id: Optional[str] = None
    client_id: str
    call_session_id: Optional[str] = None
    rate: float
    price: float
    points_dollars: float
    payment_pi: float
    payment_piti: float
    cash_to_close: float
    breakeven_months: Optional[int] = None
    total_cost_year_1: Optional[float] = None
    total_cost_year_5: Optional[float] = None
    is_recommended: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScenarioComparisonResponse(BaseModel):
    scenarios: List[ScenarioResponse]
    client_id: str
    call_session_id: Optional[str] = None


class DecisionPacketBase(BaseModel):
    rate_sheet_id: str
    approved_tabs: List[TabType] = []
    disclaimer_text: str


class DecisionPacketCreate(DecisionPacketBase):
    call_session_id: str
    client_id: str


class DecisionPacketResponse(DecisionPacketBase):
    id: str
    call_session_id: str
    client_id: str
    created_by_user_id: str
    published_at: datetime
    effective_at: datetime
    scenarios: List[Dict[str, Any]] = []
    assumptions: Dict[str, Any] = {}
    disclosures: Dict[str, Any] = {}
    pdf_url: Optional[str] = None
    version: int
    supersedes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# TRAINING SYSTEM MODELS
# =============================================================================

class TrainingSourceBase(BaseModel):
    type: TrainingSourceType
    title: str
    url: Optional[str] = None


class TrainingSourceCreate(TrainingSourceBase):
    pass


class TrainingSourceResponse(TrainingSourceBase):
    id: str
    status: TrainingSourceStatus
    error: Optional[str] = None
    total_chunks: Optional[int] = None
    processed_chunks: Optional[int] = None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TranscriptChunkResponse(BaseModel):
    id: str
    training_source_id: str
    start_sec: Optional[int] = None
    end_sec: Optional[int] = None
    text: str
    speaker: Optional[str] = None
    tokens: int
    embedding_id: Optional[str] = None
    module: Optional[PlaybookModule] = None
    tab_relevance: Optional[List[TabType]] = None
    intent: Optional[str] = None  # "explain" | "ask_question" | "handle_objection" | "summarize"
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaybookBase(BaseModel):
    name: str
    version: int = 1
    active: bool = False


class PlaybookCreate(PlaybookBase):
    training_source_id: str


class PlaybookResponse(PlaybookBase):
    id: str
    training_source_id: str
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlaybookModuleResponse(BaseModel):
    id: str
    playbook_id: str
    module: PlaybookModule
    summary: str
    key_phrases: List[str] = []
    question_bank: List[str] = []
    anti_patterns: List[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class TabScriptResponse(BaseModel):
    id: str
    playbook_id: str
    tab: TabType
    explain_template: str
    clarifying_questions: List[str] = []
    common_confusions: List[str] = []
    short_analogies: List[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class ComplianceLibraryResponse(BaseModel):
    id: str
    playbook_id: str
    must_say: List[str] = []
    must_not_say: List[str] = []
    required_disclosures: List[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# AI EVENT LOG MODELS
# =============================================================================

class AIEventLogCreate(BaseModel):
    call_session_id: str
    event_type: AIEventType
    speaker: Optional[str] = None  # "lo" | "borrower" | "ai"
    transcript_text: Optional[str] = None
    ai_utterance: Optional[str] = None
    tts_audio_id: Optional[str] = None
    training_chunks_used: Optional[List[str]] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Dict[str, Any]] = None
    action_proposed: Optional[Dict[str, Any]] = None
    action_approved: Optional[bool] = None
    approved_by_user_id: Optional[str] = None


class AIEventLogResponse(AIEventLogCreate):
    id: str
    timestamp: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class PendingActionCreate(BaseModel):
    call_session_id: str
    action_type: PendingActionType
    proposed_by: str  # "ai" | user_id
    payload: Dict[str, Any]


class PendingActionUpdate(BaseModel):
    status: PendingActionStatus
    reviewed_by_user_id: str


class PendingActionResponse(BaseModel):
    id: str
    call_session_id: str
    action_type: PendingActionType
    proposed_by: str
    proposed_at: datetime
    status: PendingActionStatus
    reviewed_by_user_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    payload: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# AI VOICE COMMAND MODELS
# =============================================================================

class AIExplainTabRequest(BaseModel):
    call_session_id: str


class AIAskQuestionRequest(BaseModel):
    call_session_id: str
    question_type: Optional[str] = None  # "clarifying" | "discovery" | "confirmation"


class AISummarizeRequest(BaseModel):
    call_session_id: str
    include_recommendations: bool = True


class AIResponse(BaseModel):
    status: str  # "speaking" | "complete" | "error"
    text: Optional[str] = None
    audio_url: Optional[str] = None
    error: Optional[str] = None


class AIProposedAction(BaseModel):
    action_id: str
    action_type: PendingActionType
    description: str
    payload: Dict[str, Any]


# =============================================================================
# WEBSOCKET MESSAGE MODELS
# =============================================================================

class WSTabChangedMessage(BaseModel):
    type: str = "TAB_CHANGED"
    active_tab: TabType


class WSTabStateUpdatedMessage(BaseModel):
    type: str = "TAB_STATE_UPDATED"
    tab_state: Dict[str, Any]


class WSAISpeakingMessage(BaseModel):
    type: str = "AI_SPEAKING"
    text: str
    audio_url: Optional[str] = None


class WSAIStoppedMessage(BaseModel):
    type: str = "AI_STOPPED"


class WSActionProposedMessage(BaseModel):
    type: str = "ACTION_PROPOSED"
    action: AIProposedAction


class WSActionApprovedMessage(BaseModel):
    type: str = "ACTION_APPROVED"
    action_id: str


class WSActionRejectedMessage(BaseModel):
    type: str = "ACTION_REJECTED"
    action_id: str


# =============================================================================
# PROCESS TAB MODELS
# =============================================================================

class ProcessMilestone(BaseModel):
    id: str
    name: str
    status: str  # "complete" | "in_progress" | "pending" | "blocked"
    owner: str
    estimated_completion: Optional[str] = None


class ProcessTask(BaseModel):
    id: str
    description: str
    status: str
    assigned_to: str


class ProcessTabResponse(BaseModel):
    milestones: List[ProcessMilestone]
    current_stage: str
    estimated_close_date: Optional[str] = None
    days_in_current_stage: int
    tasks: List[ProcessTask] = []


# =============================================================================
# PROGRAMS TAB MODELS
# =============================================================================

class LoanProgramSummary(BaseModel):
    id: str
    family: LoanProductFamily
    name: str
    term: str
    min_credit_score: int
    min_down_payment_pct: float
    max_dti: float
    allows_gift_funds: bool
    requires_pmi: bool
    badges: List[str] = []  # ["Best for First-Time", "Lowest Payment"]


class ProgramsTabResponse(BaseModel):
    eligible_programs: List[LoanProgramSummary]
    recommended_program_id: Optional[str] = None
    client_profile: Dict[str, Any] = {}  # credit score, down payment, etc.


# =============================================================================
# CLOSING COSTS TAB MODELS
# =============================================================================

class ClosingCostItem(BaseModel):
    name: str
    category: str  # "origination" | "title" | "government" | "prepaid" | "escrow"
    amount: float
    is_shoppable: bool = False
    paid_by: str = "borrower"  # "borrower" | "seller" | "lender"


class ClosingCostsTabResponse(BaseModel):
    scenario_id: str
    loan_amount: float
    lender_credit_available: float
    lender_credit_applied: float
    total_closing_costs: float
    cash_to_close: float
    items: List[ClosingCostItem]
    credits_waterfall: List[Dict[str, Any]] = []  # Shows how credits are applied
