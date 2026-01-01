"""
Recruiting Workflow CRM Models

Pydantic models for:
- Person (LO/Realtor) management
- Relationship intelligence and scoring
- Signal detection and timing
- Objection tracking
- Cadence and playbook systems
- Contact preferences
- Tasks, notes, meetings
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, time
from decimal import Decimal
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class PersonType(str, Enum):
    LOAN_OFFICER = "LOAN_OFFICER"
    REALTOR = "REALTOR"


class RelationshipStage(str, Enum):
    DISCOVERED = "DISCOVERED"
    CONNECTED = "CONNECTED"
    NURTURING = "NURTURING"
    WARMING = "WARMING"
    ACTIVE_CONVERSATION = "ACTIVE_CONVERSATION"
    EVALUATING_SWITCH = "EVALUATING_SWITCH"
    COMMITTED = "COMMITTED"
    ONBOARDING = "ONBOARDING"
    ACTIVE_PARTNER = "ACTIVE_PARTNER"
    DORMANT = "DORMANT"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"


class CommChannel(str, Enum):
    SMS = "SMS"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    LINKEDIN = "LINKEDIN"
    INSTAGRAM = "INSTAGRAM"
    FACEBOOK = "FACEBOOK"
    IN_PERSON = "IN_PERSON"
    DIRECT_MAIL = "DIRECT_MAIL"


class EventType(str, Enum):
    PERSON_CREATED = "PERSON_CREATED"
    PERSON_UPDATED = "PERSON_UPDATED"
    OUTBOUND_SENT = "OUTBOUND_SENT"
    INBOUND_RECEIVED = "INBOUND_RECEIVED"
    MEETING_SCHEDULED = "MEETING_SCHEDULED"
    MEETING_COMPLETED = "MEETING_COMPLETED"
    NOTE_ADDED = "NOTE_ADDED"
    TASK_COMPLETED = "TASK_COMPLETED"
    REFERRAL_GIVEN = "REFERRAL_GIVEN"
    DEAL_CLOSED = "DEAL_CLOSED"
    OBJECTION_LOGGED = "OBJECTION_LOGGED"
    SIGNAL_DETECTED = "SIGNAL_DETECTED"
    PLAYBOOK_TRIGGERED = "PLAYBOOK_TRIGGERED"
    CADENCE_STEP_DUE = "CADENCE_STEP_DUE"
    PREFERENCE_UPDATED = "PREFERENCE_UPDATED"
    CONSENT_UPDATED = "CONSENT_UPDATED"
    STAGE_CHANGED = "STAGE_CHANGED"
    SCORE_UPDATED = "SCORE_UPDATED"


class ObjectionCategory(str, Enum):
    COMPENSATION = "COMPENSATION"
    TECH_STACK = "TECH_STACK"
    SUPPORT_STAFF = "SUPPORT_STAFF"
    OPERATIONS = "OPERATIONS"
    PROCESSING = "PROCESSING"
    UNDERWRITING = "UNDERWRITING"
    BRAND_REPUTATION = "BRAND_REPUTATION"
    LEAD_FLOW = "LEAD_FLOW"
    MARKETING = "MARKETING"
    CULTURE = "CULTURE"
    MANAGEMENT = "MANAGEMENT"
    TRAINING = "TRAINING"
    COMPLIANCE_RISK = "COMPLIANCE_RISK"
    NON_COMPETE = "NON_COMPETE"
    TIMING = "TIMING"
    INERTIA = "INERTIA"
    LOYALTY = "LOYALTY"
    GEOGRAPHY = "GEOGRAPHY"
    PRODUCT_LIMITATION = "PRODUCT_LIMITATION"
    PRICING_RATES = "PRICING_RATES"
    OTHER = "OTHER"


class SignalType(str, Enum):
    JOB_CHANGE = "JOB_CHANGE"
    TEAM_CHANGE = "TEAM_CHANGE"
    PRODUCTION_SPIKE = "PRODUCTION_SPIKE"
    PRODUCTION_DROP = "PRODUCTION_DROP"
    COMMISSION_CHANGE = "COMMISSION_CHANGE"
    TECH_PAIN = "TECH_PAIN"
    OPS_PAIN = "OPS_PAIN"
    BRANCH_INSTABILITY = "BRANCH_INSTABILITY"
    MANAGEMENT_CONFLICT = "MANAGEMENT_CONFLICT"
    MARKET_SHIFT = "MARKET_SHIFT"
    NEW_MARKET_ENTRY = "NEW_MARKET_ENTRY"
    LIFE_EVENT = "LIFE_EVENT"
    REFERRAL_ACTIVITY = "REFERRAL_ACTIVITY"
    ENGAGEMENT_SPIKE = "ENGAGEMENT_SPIKE"
    MEETING_INTENT = "MEETING_INTENT"
    OBJECTION_SOFTENED = "OBJECTION_SOFTENED"
    TIME_WINDOW = "TIME_WINDOW"
    LENDER_DISSATISFACTION = "LENDER_DISSATISFACTION"
    TEAM_GROWTH = "TEAM_GROWTH"
    SEASONAL_SURGE = "SEASONAL_SURGE"


class EdgeType(str, Enum):
    PAST_DEAL = "PAST_DEAL"
    REFERRAL_SENT = "REFERRAL_SENT"
    REFERRAL_RECEIVED = "REFERRAL_RECEIVED"
    CO_WORKED_WITH = "CO_WORKED_WITH"
    SAME_ORG = "SAME_ORG"
    INTRO_REQUESTED = "INTRO_REQUESTED"
    INTRO_MADE = "INTRO_MADE"
    SOCIAL_MUTUAL = "SOCIAL_MUTUAL"
    EVENT_MET = "EVENT_MET"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    SNOOZED = "SNOOZED"


# =============================================================================
# ORGANIZATION MODELS
# =============================================================================

class OrgBase(BaseModel):
    """Base organization model."""
    name: str
    org_type: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    nmls_id: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class OrgCreate(OrgBase):
    """Model for creating an organization."""
    pass


class OrgUpdate(BaseModel):
    """Model for updating an organization."""
    name: Optional[str] = None
    org_type: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    nmls_id: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class Org(OrgBase):
    """Organization with ID and timestamps."""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# PERSON MODELS
# =============================================================================

class PersonBase(BaseModel):
    """Base person model."""
    person_type: PersonType
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    primary_email: Optional[str] = None
    secondary_email: Optional[str] = None
    primary_phone: Optional[str] = None
    secondary_phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_handle: Optional[str] = None
    facebook_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_zip: Optional[str] = None
    timezone: Optional[str] = "America/New_York"
    current_org_id: Optional[str] = None
    title: Optional[str] = None
    nmls_id: Optional[str] = None
    license_state: Optional[str] = None
    years_experience: Optional[int] = None
    annual_volume: Optional[float] = None
    annual_units: Optional[int] = None
    avg_loan_size: Optional[float] = None
    source: Optional[str] = None
    source_campaign: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None


class PersonCreate(PersonBase):
    """Model for creating a person."""
    organization_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    referrer_person_id: Optional[str] = None


class PersonUpdate(BaseModel):
    """Model for updating a person."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    primary_email: Optional[str] = None
    secondary_email: Optional[str] = None
    primary_phone: Optional[str] = None
    secondary_phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_handle: Optional[str] = None
    facebook_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_zip: Optional[str] = None
    timezone: Optional[str] = None
    current_org_id: Optional[str] = None
    title: Optional[str] = None
    nmls_id: Optional[str] = None
    license_state: Optional[str] = None
    years_experience: Optional[int] = None
    annual_volume: Optional[float] = None
    annual_units: Optional[int] = None
    avg_loan_size: Optional[float] = None
    relationship_stage: Optional[RelationshipStage] = None
    owner_user_id: Optional[int] = None
    consent_sms: Optional[bool] = None
    consent_email: Optional[bool] = None
    consent_phone: Optional[bool] = None
    do_not_contact: Optional[bool] = None
    source: Optional[str] = None
    source_campaign: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None


class Person(PersonBase):
    """Person with full details."""
    id: str
    organization_id: Optional[int] = None
    display_name: Optional[str] = None
    relationship_stage: RelationshipStage
    owner_user_id: Optional[int] = None
    consent_sms: bool = False
    consent_email: bool = True
    consent_phone: bool = True
    do_not_contact: bool = False
    referrer_person_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# RELATIONSHIP INTELLIGENCE MODELS
# =============================================================================

class RelationshipIntelBase(BaseModel):
    """Base relationship intelligence model."""
    timing_score: int = 0
    trust_score: int = 0
    reciprocity_score: int = 0
    risk_score: int = 0
    engagement_score: int = 0
    why_they_might_switch: Optional[str] = None
    what_they_care_about: Optional[str] = None
    what_they_hate: Optional[str] = None
    ideal_offer: Optional[str] = None
    predicted_timeline: Optional[str] = None
    next_best_action: Optional[str] = None
    next_best_action_reason: Optional[str] = None


class RelationshipIntelUpdate(BaseModel):
    """Model for updating relationship intelligence."""
    timing_score: Optional[int] = None
    trust_score: Optional[int] = None
    reciprocity_score: Optional[int] = None
    risk_score: Optional[int] = None
    engagement_score: Optional[int] = None
    why_they_might_switch: Optional[str] = None
    what_they_care_about: Optional[str] = None
    what_they_hate: Optional[str] = None
    ideal_offer: Optional[str] = None
    predicted_timeline: Optional[str] = None
    next_best_action: Optional[str] = None
    next_best_action_reason: Optional[str] = None


class RelationshipIntel(RelationshipIntelBase):
    """Relationship intelligence with computed fields."""
    person_id: str
    overall_score: Optional[int] = None
    last_signal_at: Optional[datetime] = None
    last_signal_type: Optional[SignalType] = None
    last_meaningful_touch_at: Optional[datetime] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class PersonSummary(Person):
    """Person with relationship intelligence summary."""
    timing_score: Optional[int] = 0
    trust_score: Optional[int] = 0
    engagement_score: Optional[int] = 0
    overall_score: Optional[int] = 0
    last_signal_at: Optional[datetime] = None
    last_signal_type: Optional[str] = None
    next_best_action: Optional[str] = None
    org_name: Optional[str] = None
    open_objections: int = 0
    pending_tasks: int = 0
    last_outreach_at: Optional[datetime] = None


# =============================================================================
# SIGNAL MODELS
# =============================================================================

class SignalBase(BaseModel):
    """Base signal model."""
    signal_type: SignalType
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: Optional[str] = None
    source: Optional[str] = None
    source_reference: Optional[str] = None


class SignalCreate(SignalBase):
    """Model for creating a signal."""
    person_id: str
    weight: Optional[int] = None  # Override default weight
    detected_by: Optional[int] = None
    ai_detected: bool = False
    expires_at: Optional[datetime] = None


class Signal(SignalBase):
    """Signal with full details."""
    id: str
    person_id: str
    weight: int
    processed: bool = False
    processed_at: Optional[datetime] = None
    score_delta: Optional[int] = None
    detected_by: Optional[int] = None
    ai_detected: bool = False
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SignalExtraction(BaseModel):
    """AI-extracted signals from text."""
    signals: List[Dict[str, Any]] = []
    objections: List[Dict[str, Any]] = []
    recommend_next_action: Optional[str] = None


# =============================================================================
# OBJECTION MODELS
# =============================================================================

class ObjectionBase(BaseModel):
    """Base objection model."""
    category: ObjectionCategory
    subcategory: Optional[str] = None
    severity: int = Field(default=3, ge=1, le=5)
    statement: Optional[str] = None
    context: Optional[str] = None
    our_response: Optional[str] = None


class ObjectionCreate(ObjectionBase):
    """Model for creating an objection."""
    person_id: str
    captured_via: Optional[str] = None


class ObjectionUpdate(BaseModel):
    """Model for updating an objection."""
    subcategory: Optional[str] = None
    severity: Optional[int] = Field(default=None, ge=1, le=5)
    statement: Optional[str] = None
    context: Optional[str] = None
    our_response: Optional[str] = None
    status: Optional[str] = None
    resolution_notes: Optional[str] = None
    next_revisit_at: Optional[datetime] = None


class Objection(ObjectionBase):
    """Objection with full details."""
    id: str
    person_id: str
    status: str = "OPEN"
    addressed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    next_revisit_at: Optional[datetime] = None
    revisit_count: int = 0
    captured_by_user_id: Optional[int] = None
    captured_via: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# PERSON EDGE (CONNECTIONS) MODELS
# =============================================================================

class PersonEdgeBase(BaseModel):
    """Base person edge model."""
    edge_type: EdgeType
    strength: int = Field(default=1, ge=1, le=10)
    evidence: Optional[str] = None
    occurred_at: Optional[datetime] = None
    notes: Optional[str] = None


class PersonEdgeCreate(PersonEdgeBase):
    """Model for creating a person edge."""
    from_person_id: str
    to_person_id: str
    deal_id: Optional[int] = None


class PersonEdge(PersonEdgeBase):
    """Person edge with full details."""
    id: str
    from_person_id: str
    to_person_id: str
    deal_id: Optional[int] = None
    verified: bool = False
    verified_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MutualConnection(BaseModel):
    """Mutual connection between two people."""
    person_id: str
    display_name: Optional[str] = None
    total_strength: int
    edge_types: List[str]


class TopConnection(BaseModel):
    """Top connection for a person."""
    connected_person_id: str
    display_name: Optional[str] = None
    relationship_stage: Optional[RelationshipStage] = None
    total_strength: int
    edge_count: int
    strongest_edge_type: Optional[EdgeType] = None


# =============================================================================
# CONTACT PREFERENCE MODELS
# =============================================================================

class ContactPreferenceBase(BaseModel):
    """Base contact preference model."""
    preferred_channels: Optional[List[CommChannel]] = None
    do_not_use_channels: Optional[List[CommChannel]] = None
    preferred_days: Optional[List[int]] = None  # 0-6
    preferred_time_start: Optional[str] = None  # HH:MM format
    preferred_time_end: Optional[str] = None  # HH:MM format


class ContactPreferenceUpdate(ContactPreferenceBase):
    """Model for updating contact preferences."""
    pass


class ContactPreference(ContactPreferenceBase):
    """Contact preference with learned data."""
    person_id: str
    sms_response_rate: float = 0
    email_open_rate: float = 0
    email_reply_rate: float = 0
    phone_answer_rate: float = 0
    best_contact_minute: Optional[int] = None
    best_contact_day: Optional[int] = None
    best_channel: Optional[CommChannel] = None
    total_outreach_count: int = 0
    total_response_count: int = 0
    last_response_at: Optional[datetime] = None
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# COMM OUTCOME MODELS
# =============================================================================

class CommOutcomeCreate(BaseModel):
    """Model for creating a communication outcome."""
    person_id: str
    channel: CommChannel
    direction: str = "outbound"
    sent_at: datetime
    template_key: Optional[str] = None
    campaign_id: Optional[str] = None
    message_preview: Optional[str] = None


class CommOutcomeUpdate(BaseModel):
    """Model for updating a communication outcome."""
    delivered: Optional[bool] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    booked_meeting_at: Optional[datetime] = None


class CommOutcome(BaseModel):
    """Communication outcome with full details."""
    id: str
    person_id: str
    channel: CommChannel
    direction: str
    sent_at: datetime
    sent_day_of_week: Optional[int] = None
    sent_minute_of_day: Optional[int] = None
    delivered: bool = True
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    booked_meeting_at: Optional[datetime] = None
    outcome_score: int = 0
    template_key: Optional[str] = None
    campaign_id: Optional[str] = None
    message_preview: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# CADENCE MODELS
# =============================================================================

class CadenceStepBase(BaseModel):
    """Base cadence step model."""
    step_order: int
    step_name: Optional[str] = None
    min_days_after_prev: int
    max_days_after_prev: Optional[int] = None
    channel: CommChannel
    template_key: str
    goal: Optional[str] = None
    skip_if_conditions: Optional[Dict[str, Any]] = None
    is_required: bool = True


class CadenceStepCreate(CadenceStepBase):
    """Model for creating a cadence step."""
    pass


class CadenceStep(CadenceStepBase):
    """Cadence step with full details."""
    id: str
    cadence_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class CadenceBase(BaseModel):
    """Base cadence model."""
    name: str
    key: str
    description: Optional[str] = None
    person_type: PersonType
    target_stages: Optional[List[RelationshipStage]] = None
    is_active: bool = True
    is_default: bool = False
    pause_on_reply: bool = True
    pause_on_meeting: bool = True
    exit_on_stage_change: bool = False


class CadenceCreate(CadenceBase):
    """Model for creating a cadence."""
    organization_id: Optional[int] = None
    steps: Optional[List[CadenceStepCreate]] = None


class CadenceUpdate(BaseModel):
    """Model for updating a cadence."""
    name: Optional[str] = None
    description: Optional[str] = None
    target_stages: Optional[List[RelationshipStage]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    pause_on_reply: Optional[bool] = None
    pause_on_meeting: Optional[bool] = None
    exit_on_stage_change: Optional[bool] = None


class Cadence(CadenceBase):
    """Cadence with full details."""
    id: str
    organization_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    steps: Optional[List[CadenceStep]] = None

    class Config:
        from_attributes = True


class CadenceEnrollmentCreate(BaseModel):
    """Model for enrolling a person in a cadence."""
    person_id: str
    cadence_id: str
    enrolled_by: Optional[int] = None
    start_at: Optional[datetime] = None  # When to start (default: now)


class CadenceEnrollmentUpdate(BaseModel):
    """Model for updating a cadence enrollment."""
    status: Optional[str] = None
    pause_reason: Optional[str] = None
    paused_until: Optional[datetime] = None


class CadenceEnrollment(BaseModel):
    """Cadence enrollment with full details."""
    id: str
    person_id: str
    cadence_id: str
    status: str = "ACTIVE"
    current_step: int = 1
    completed_steps: List[int] = []
    enrolled_at: datetime
    next_step_due_at: datetime
    last_step_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    paused_until: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    enrolled_by: Optional[int] = None
    pause_reason: Optional[str] = None
    steps_executed: int = 0
    responses_received: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CadenceDueItem(BaseModel):
    """Item from cadence due view."""
    enrollment_id: str
    cadence_name: str
    cadence_key: str
    current_step: int
    next_channel: CommChannel
    next_template: str
    next_goal: Optional[str] = None
    person_id: str
    person_name: Optional[str] = None
    person_type: PersonType
    primary_email: Optional[str] = None
    primary_phone: Optional[str] = None


# =============================================================================
# PLAYBOOK MODELS
# =============================================================================

class PlaybookAction(BaseModel):
    """A single action in a playbook."""
    type: str  # SMS, EMAIL, PHONE, TASK, PAUSE_CADENCE, INTRO_REQUEST, ASSET
    timing: Optional[str] = None  # immediate, within_15_min, within_1_hour, etc.
    template_key: Optional[str] = None
    message: Optional[str] = None
    title: Optional[str] = None
    priority: Optional[str] = None
    condition: Optional[str] = None
    days: Optional[int] = None
    asset_key: Optional[str] = None


class PlaybookTrigger(BaseModel):
    """Playbook trigger configuration."""
    timing_score_min: Optional[int] = None
    timing_score_max: Optional[int] = None
    signal_types: Optional[List[SignalType]] = None
    stage_in: Optional[List[RelationshipStage]] = None
    stage_not_in: Optional[List[RelationshipStage]] = None
    operator: str = "OR"  # AND/OR for signal matching


class PlaybookBase(BaseModel):
    """Base playbook model."""
    key: str
    name: str
    description: Optional[str] = None
    person_type: PersonType
    trigger_config: PlaybookTrigger
    actions: List[PlaybookAction]
    is_active: bool = True
    priority: int = 50
    cooldown_days: int = 30


class PlaybookCreate(PlaybookBase):
    """Model for creating a playbook."""
    organization_id: Optional[int] = None


class PlaybookUpdate(BaseModel):
    """Model for updating a playbook."""
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_config: Optional[PlaybookTrigger] = None
    actions: Optional[List[PlaybookAction]] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    cooldown_days: Optional[int] = None


class Playbook(PlaybookBase):
    """Playbook with full details."""
    id: str
    organization_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlaybookRunCreate(BaseModel):
    """Model for creating a playbook run."""
    playbook_id: str
    person_id: str
    triggered_by_signal_id: Optional[str] = None
    triggered_by_event_id: Optional[str] = None
    trigger_context: Optional[Dict[str, Any]] = None


class PlaybookRun(BaseModel):
    """Playbook run with full details."""
    id: str
    playbook_id: str
    person_id: str
    triggered_by_signal_id: Optional[str] = None
    triggered_by_event_id: Optional[str] = None
    trigger_context: Dict[str, Any] = {}
    status: str = "STARTED"
    actions_total: int = 0
    actions_completed: int = 0
    actions_log: List[Dict[str, Any]] = []
    outcome: Optional[str] = None
    outcome_notes: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# TASK MODELS
# =============================================================================

class TaskBase(BaseModel):
    """Base task model."""
    title: str
    description: Optional[str] = None
    task_type: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: Optional[datetime] = None
    reminder_at: Optional[datetime] = None


class TaskCreate(TaskBase):
    """Model for creating a task."""
    organization_id: Optional[int] = None
    person_id: Optional[str] = None
    assigned_to: Optional[int] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None


class TaskUpdate(BaseModel):
    """Model for updating a task."""
    title: Optional[str] = None
    description: Optional[str] = None
    task_type: Optional[str] = None
    priority: Optional[TaskPriority] = None
    due_at: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    assigned_to: Optional[int] = None
    status: Optional[TaskStatus] = None
    outcome: Optional[str] = None
    outcome_notes: Optional[str] = None


class Task(TaskBase):
    """Task with full details."""
    id: str
    organization_id: Optional[int] = None
    person_id: Optional[str] = None
    assigned_to: Optional[int] = None
    status: TaskStatus = TaskStatus.PENDING
    completed_at: Optional[datetime] = None
    completed_by: Optional[int] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    outcome: Optional[str] = None
    outcome_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# NOTE MODELS
# =============================================================================

class NoteBase(BaseModel):
    """Base note model."""
    content: str
    note_type: Optional[str] = None
    is_private: bool = False
    pinned: bool = False


class NoteCreate(NoteBase):
    """Model for creating a note."""
    person_id: str


class NoteUpdate(BaseModel):
    """Model for updating a note."""
    content: Optional[str] = None
    note_type: Optional[str] = None
    is_private: Optional[bool] = None
    pinned: Optional[bool] = None


class Note(NoteBase):
    """Note with full details."""
    id: str
    person_id: str
    created_by: Optional[int] = None
    ai_processed: bool = False
    ai_extracted_signals: Optional[Dict[str, Any]] = None
    ai_extracted_objections: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# MEETING MODELS
# =============================================================================

class MeetingBase(BaseModel):
    """Base meeting model."""
    title: str
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    scheduled_at: datetime
    duration_minutes: int = 30
    location: Optional[str] = None


class MeetingCreate(MeetingBase):
    """Model for creating a meeting."""
    person_id: str
    organizer_user_id: Optional[int] = None
    attendee_emails: Optional[List[str]] = None


class MeetingUpdate(BaseModel):
    """Model for updating a meeting."""
    title: Optional[str] = None
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    status: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    next_steps: Optional[str] = None


class Meeting(MeetingBase):
    """Meeting with full details."""
    id: str
    person_id: str
    status: str = "SCHEDULED"
    organizer_user_id: Optional[int] = None
    attendee_emails: Optional[List[str]] = None
    completed_at: Optional[datetime] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    next_steps: Optional[str] = None
    external_calendar_id: Optional[str] = None
    external_event_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# MESSAGE TEMPLATE MODELS
# =============================================================================

class MessageTemplateBase(BaseModel):
    """Base message template model."""
    key: str
    name: str
    channel: CommChannel
    person_type: Optional[PersonType] = None
    subject: Optional[str] = None
    body: str
    merge_fields: Optional[List[str]] = None
    category: Optional[str] = None
    purpose: Optional[str] = None


class MessageTemplateCreate(MessageTemplateBase):
    """Model for creating a message template."""
    organization_id: Optional[int] = None


class MessageTemplateUpdate(BaseModel):
    """Model for updating a message template."""
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    merge_fields: Optional[List[str]] = None
    category: Optional[str] = None
    purpose: Optional[str] = None
    is_active: Optional[bool] = None


class MessageTemplate(MessageTemplateBase):
    """Message template with full details."""
    id: str
    organization_id: Optional[int] = None
    times_used: int = 0
    avg_response_rate: Optional[float] = None
    is_active: bool = True
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# INTRO REQUEST MODELS
# =============================================================================

class IntroRequestCreate(BaseModel):
    """Model for creating an intro request."""
    target_person_id: str
    connector_person_id: str
    edge_id: Optional[str] = None
    reason: Optional[str] = None
    suggested_message: Optional[str] = None


class IntroRequestUpdate(BaseModel):
    """Model for updating an intro request."""
    status: Optional[str] = None
    response_notes: Optional[str] = None


class IntroRequest(BaseModel):
    """Intro request with full details."""
    id: str
    target_person_id: str
    connector_person_id: str
    edge_id: Optional[str] = None
    status: str = "PENDING"
    reason: Optional[str] = None
    suggested_message: Optional[str] = None
    requested_by: Optional[int] = None
    sent_at: Optional[datetime] = None
    response_at: Optional[datetime] = None
    response_notes: Optional[str] = None
    intro_made_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# CRM EVENT MODELS
# =============================================================================

class CRMEventCreate(BaseModel):
    """Model for creating a CRM event."""
    event_type: EventType
    person_id: Optional[str] = None
    organization_id: Optional[int] = None
    user_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None


class CRMEvent(BaseModel):
    """CRM event with full details."""
    id: str
    organization_id: Optional[int] = None
    event_type: EventType
    person_id: Optional[str] = None
    user_id: Optional[int] = None
    payload: Dict[str, Any] = {}
    processed: bool = False
    processed_at: Optional[datetime] = None
    occurred_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# NEXT BEST ACTION MODELS
# =============================================================================

class NextBestActionRequest(BaseModel):
    """Request for AI-powered next best action."""
    person_id: str


class NextBestActionResponse(BaseModel):
    """AI-generated next best action recommendation."""
    recommended_channel: CommChannel
    recommended_send_time_local: Optional[str] = None
    message_goal: str  # micro_yes, value, book_meeting, intro_request, send_asset
    draft_message: Optional[str] = None
    draft_subject: Optional[str] = None  # for email
    playbook_to_trigger: Optional[str] = None
    reasoning_bullets: List[str] = []
    confidence: float = 0.5


# =============================================================================
# TIMING INTELLIGENCE MODELS
# =============================================================================

class TimingIntelligence(BaseModel):
    """Timing intelligence summary for a person."""
    person_id: str
    timing_score: int
    timing_grade: str  # HOT, WARM, COOL, COLD
    last_signal_at: Optional[datetime] = None
    last_signal_type: Optional[SignalType] = None
    why_now: Optional[str] = None
    recent_signals: List[Signal] = []
    recommended_action: Optional[str] = None


# =============================================================================
# DASHBOARD / AGGREGATE MODELS
# =============================================================================

class WorkflowStats(BaseModel):
    """Aggregate statistics for recruiting workflow."""
    total_people: int = 0
    by_type: Dict[str, int] = {}
    by_stage: Dict[str, int] = {}
    hot_leads: int = 0
    warm_leads: int = 0
    cadences_active: int = 0
    tasks_pending: int = 0
    tasks_overdue: int = 0
    meetings_upcoming: int = 0
    objections_open: int = 0
    playbook_runs_active: int = 0


class PersonPipeline(BaseModel):
    """Pipeline view of people by stage."""
    stage: RelationshipStage
    count: int
    people: List[PersonSummary] = []


# =============================================================================
# CONSTANTS
# =============================================================================

# Signal weights by person type
SIGNAL_WEIGHTS = {
    PersonType.LOAN_OFFICER: {
        SignalType.MEETING_INTENT: 35,
        SignalType.BRANCH_INSTABILITY: 25,
        SignalType.OPS_PAIN: 20,
        SignalType.TECH_PAIN: 15,
        SignalType.ENGAGEMENT_SPIKE: 18,
        SignalType.JOB_CHANGE: 30,
        SignalType.PRODUCTION_DROP: 20,
        SignalType.COMMISSION_CHANGE: 22,
        SignalType.MANAGEMENT_CONFLICT: 25,
        SignalType.OBJECTION_SOFTENED: 15,
        SignalType.TIME_WINDOW: 10,
    },
    PersonType.REALTOR: {
        SignalType.LENDER_DISSATISFACTION: 25,
        SignalType.REFERRAL_ACTIVITY: 20,
        SignalType.ENGAGEMENT_SPIKE: 18,
        SignalType.TEAM_GROWTH: 15,
        SignalType.MEETING_INTENT: 30,
        SignalType.SEASONAL_SURGE: 12,
        SignalType.OBJECTION_SOFTENED: 15,
        SignalType.TIME_WINDOW: 10,
    },
}

# Default weight for signals not in the map
DEFAULT_SIGNAL_WEIGHT = 10

# Timing thresholds
TIMING_THRESHOLD_HOT = 70
TIMING_THRESHOLD_WARM = 50
TIMING_THRESHOLD_COOL = 30

# Objection revisit intervals (days)
OBJECTION_REVISIT_DAYS = {
    ObjectionCategory.TIMING: 45,
    ObjectionCategory.INERTIA: 60,
    ObjectionCategory.COMPENSATION: 90,
    ObjectionCategory.OPERATIONS: 21,
    ObjectionCategory.PROCESSING: 30,
    ObjectionCategory.TECH_STACK: 30,
    ObjectionCategory.SUPPORT_STAFF: 30,
    ObjectionCategory.UNDERWRITING: 30,
    ObjectionCategory.BRAND_REPUTATION: 60,
    ObjectionCategory.LEAD_FLOW: 45,
    ObjectionCategory.MARKETING: 45,
    ObjectionCategory.CULTURE: 60,
    ObjectionCategory.MANAGEMENT: 45,
    ObjectionCategory.TRAINING: 45,
    ObjectionCategory.COMPLIANCE_RISK: 60,
    ObjectionCategory.NON_COMPETE: 90,
    ObjectionCategory.LOYALTY: 60,
    ObjectionCategory.GEOGRAPHY: 90,
    ObjectionCategory.PRODUCT_LIMITATION: 45,
    ObjectionCategory.PRICING_RATES: 30,
    ObjectionCategory.OTHER: 45,
}

# Relationship stage labels
STAGE_LABELS = {
    RelationshipStage.DISCOVERED: "Discovered",
    RelationshipStage.CONNECTED: "Connected",
    RelationshipStage.NURTURING: "Nurturing",
    RelationshipStage.WARMING: "Warming",
    RelationshipStage.ACTIVE_CONVERSATION: "Active Conversation",
    RelationshipStage.EVALUATING_SWITCH: "Evaluating Switch",
    RelationshipStage.COMMITTED: "Committed",
    RelationshipStage.ONBOARDING: "Onboarding",
    RelationshipStage.ACTIVE_PARTNER: "Active Partner",
    RelationshipStage.DORMANT: "Dormant",
    RelationshipStage.DO_NOT_CONTACT: "Do Not Contact",
}

# Person type labels
PERSON_TYPE_LABELS = {
    PersonType.LOAN_OFFICER: "Loan Officer",
    PersonType.REALTOR: "Realtor",
}
