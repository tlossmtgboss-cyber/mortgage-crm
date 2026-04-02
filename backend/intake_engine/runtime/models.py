"""
Intake Engine Data Models
Party-aware session state with Redis/Postgres storage support
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from uuid import uuid4


class PartyType(str, Enum):
    PRIMARY = "PRIMARY"
    CO_BORROWER = "CO_BORROWER"
    NON_BORROWING_SPOUSE = "NON_BORROWING_SPOUSE"


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"
    ABANDONED = "ABANDONED"
    EXPIRED = "EXPIRED"


class FlagCategory(str, Enum):
    TRUTH = "truth"
    READINESS = "readiness"
    PRODUCT = "product"
    COMPLIANCE = "compliance"
    FLOW = "flow"
    SLA = "sla"


class FlagSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    HIGH = "high"
    CRITICAL = "critical"


class HesitationBand(str, Enum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    HIGH = "high"


class TruthBand(str, Enum):
    RED = "RED"
    ORANGE = "ORANGE"
    YELLOW = "YELLOW"
    LIGHT_GREEN = "LIGHT_GREEN"
    GREEN = "GREEN"


class DataClass(str, Enum):
    PUBLIC = "PUBLIC"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"


class EventType(str, Enum):
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_RESUMED = "SESSION_RESUMED"
    SESSION_COMPLETED = "SESSION_COMPLETED"
    SESSION_ABANDONED = "SESSION_ABANDONED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    QUESTION_SHOWN = "QUESTION_SHOWN"
    ANSWER_SUBMITTED = "ANSWER_SUBMITTED"
    ANSWER_EDITED = "ANSWER_EDITED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    FLAG_ADDED = "FLAG_ADDED"
    FLAG_REMOVED = "FLAG_REMOVED"
    SCORE_UPDATED = "SCORE_UPDATED"
    CONSENT_CAPTURED = "CONSENT_CAPTURED"
    CONSENT_DECLINED = "CONSENT_DECLINED"
    SLA_TASK_CREATED = "SLA_TASK_CREATED"
    OVERLAY_TRIGGERED = "OVERLAY_TRIGGERED"
    SECTION_CHANGED = "SECTION_CHANGED"
    PARTY_ADDED = "PARTY_ADDED"
    URLA_GENERATED = "URLA_GENERATED"


# ============================================================================
# Core Models
# ============================================================================

class Party(BaseModel):
    """Represents a borrower, co-borrower, or non-borrowing spouse"""
    party_id: str = Field(default_factory=lambda: f"P_{uuid4().hex[:10]}")
    party_type: PartyType
    display_name: Optional[str] = None
    is_complete: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnswerMeta(BaseModel):
    """Metadata for an individual answer"""
    party_id: Optional[str] = None
    confidence: float = 0.9
    evidence_source: str = "memory"
    answered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    response_time_ms: int = 0
    edits_count: int = 0
    hedges_detected: List[str] = Field(default_factory=list)
    uncertainty_expressed: bool = False


class Flag(BaseModel):
    """A flag indicating something notable about the session/answers"""
    code: str
    category: FlagCategory
    severity: FlagSeverity
    message: Optional[str] = None
    triggered_by: Optional[str] = None
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    party_id: Optional[str] = None


class ConsentRecord(BaseModel):
    """Record of a consent capture"""
    consent_key: str
    accepted: bool
    version_hash: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class Signals(BaseModel):
    """Behavioral signals collected during intake"""
    response_time_ms: int = 0
    avg_response_time_ms: float = 0.0
    edits_count: int = 0
    hedges: List[str] = Field(default_factory=list)
    uncertainty_count: int = 0
    device_rtt_ms: int = 0
    session_duration_ms: int = 0
    questions_answered: int = 0
    questions_skipped: int = 0
    back_navigation_count: int = 0


class ScoreBreakdown(BaseModel):
    """Detailed breakdown of truth score components"""
    completeness: float = 0.0
    internal_consistency: float = 0.0
    evidence_alignment: float = 0.0
    behavioral_confidence: float = 0.0


class Scores(BaseModel):
    """Session scores: hesitation, truth, and readiness"""
    hesitation_score: float = 0.0
    hesitation_band: HesitationBand = HesitationBand.NONE
    underwriting_truth_score: float = 0.0
    truth_band: TruthBand = TruthBand.GREEN
    lo_readiness_score: float = 0.0
    readiness_cap: Optional[float] = None
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)


class EditHistory(BaseModel):
    """Record of an answer edit"""
    question_id: str
    party_id: Optional[str] = None
    old_value: Any = None
    new_value: Any = None
    edited_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Session(BaseModel):
    """Complete session state for intake engine"""
    session_id: str = Field(default_factory=lambda: f"S_{uuid4().hex[:10]}")
    loan_id: Optional[str] = None
    borrower_id: Optional[str] = None
    app_version: str = "1.0.0"
    locale: str = "en-US"
    mode: str = "intake_prequal"
    status: SessionStatus = SessionStatus.ACTIVE

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    current_section: str = "LANGUAGE"
    last_question_id: Optional[str] = None

    # Parties (borrower, co-borrower, NBS)
    parties: List[Party] = Field(default_factory=list)

    # Answers - global (non-party-specific)
    answers: Dict[str, Any] = Field(default_factory=dict)

    # Party-specific answers: { party_id: { question_id: answer } }
    party_answers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Metadata for each answer
    answer_meta: Dict[str, AnswerMeta] = Field(default_factory=dict)

    # Active flags
    flags: List[Flag] = Field(default_factory=list)

    # Behavioral signals
    signals: Signals = Field(default_factory=Signals)

    # Scores
    scores: Scores = Field(default_factory=Scores)

    # Active coaching overlay
    active_overlay: Optional[str] = None

    # Dynamically required/skipped questions
    required_questions: List[str] = Field(default_factory=list)
    skipped_questions: List[str] = Field(default_factory=list)

    # Edit history
    edits_history: List[EditHistory] = Field(default_factory=list)

    # Consents
    consents: Dict[str, ConsentRecord] = Field(default_factory=dict)

    def get_answer(self, question_id: str, party_id: Optional[str] = None) -> Any:
        """Get answer for a question, optionally for a specific party"""
        if party_id and party_id in self.party_answers:
            return self.party_answers[party_id].get(question_id)
        return self.answers.get(question_id)

    def set_answer(
        self,
        question_id: str,
        value: Any,
        party_id: Optional[str] = None,
        meta: Optional[AnswerMeta] = None
    ):
        """Set answer for a question"""
        # Check if this is an edit
        old_value = self.get_answer(question_id, party_id)
        if old_value is not None and old_value != value:
            self.edits_history.append(EditHistory(
                question_id=question_id,
                party_id=party_id,
                old_value=old_value,
                new_value=value
            ))

        if party_id:
            if party_id not in self.party_answers:
                self.party_answers[party_id] = {}
            self.party_answers[party_id][question_id] = value
        else:
            self.answers[question_id] = value

        if meta:
            key = f"{party_id or 'global'}:{question_id}"
            self.answer_meta[key] = meta

        self.updated_at = datetime.now(timezone.utc)

    def add_flag(self, flag: Flag):
        """Add a flag if not already present"""
        if not any(f.code == flag.code for f in self.flags):
            self.flags.append(flag)

    def remove_flag(self, code: str):
        """Remove a flag by code"""
        self.flags = [f for f in self.flags if f.code != code]

    def has_flag(self, code: str) -> bool:
        """Check if a flag is present"""
        return any(f.code == code for f in self.flags)

    def add_party(self, party_type: PartyType, display_name: Optional[str] = None) -> Party:
        """Add a new party to the session"""
        party = Party(party_type=party_type, display_name=display_name)
        self.parties.append(party)
        self.party_answers[party.party_id] = {}
        return party

    def get_primary_party(self) -> Optional[Party]:
        """Get the primary borrower party"""
        for party in self.parties:
            if party.party_type == PartyType.PRIMARY:
                return party
        return None

    class Config:
        use_enum_values = True


# ============================================================================
# Audit Event Model
# ============================================================================

class AuditEvent(BaseModel):
    """Immutable audit event with hash chain"""
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    party_id: Optional[str] = None
    event_type: EventType
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
    hash_prev: Optional[str] = None
    hash_self: str = ""
    pii_redacted: bool = False

    class Config:
        use_enum_values = True


# ============================================================================
# Question Model (from question bank)
# ============================================================================

class Question(BaseModel):
    """Question definition from question bank"""
    question_id: str
    prompt_key: str
    urla_section: str
    urla_payload_path: Optional[str] = None
    answer_types: List[str]
    required: bool
    party_aware: bool = False
    category: str = "identity"
    options: Optional[List[Dict[str, Any]]] = None
    ui: Dict[str, Any] = Field(default_factory=dict)
    data_class: DataClass = DataClass.SENSITIVE
    validations: List[Dict[str, Any]] = Field(default_factory=list)
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
    micro_why_key: Optional[str] = None
    help_text_key: Optional[str] = None
    evidence_types: List[str] = Field(default_factory=list)
    hmda_segregated: bool = False


# ============================================================================
# Response Models
# ============================================================================

class NextQuestion(BaseModel):
    """Response model for next question endpoint"""
    question_id: str
    prompt: str
    answer_types: List[str]
    ui: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[List[Dict[str, Any]]] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class AnswerResponse(BaseModel):
    """Response model for answer submission"""
    accepted: bool
    validation_errors: List[Dict[str, Any]] = Field(default_factory=list)
    flags_added: List[str] = Field(default_factory=list)
    scores: Dict[str, Any] = Field(default_factory=dict)
    next: Optional[NextQuestion] = None
    overlay: Optional[Dict[str, Any]] = None


class SessionCompleteResponse(BaseModel):
    """Response model for session completion"""
    status: str
    urla_payload: Dict[str, Any]
    scores: Dict[str, Any]
    flags: List[Dict[str, Any]]
    sla_tasks_created: List[Dict[str, Any]]
    redirect: Optional[str] = None


class SLATask(BaseModel):
    """SLA task created from hooks"""
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    code: str
    title: str
    description: Optional[str] = None
    priority: str = "P2"
    status: str = "OPEN"
    assignee_role: Optional[str] = None
    due_hours: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
