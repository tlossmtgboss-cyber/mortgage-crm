"""
Listing Agent Portal Models
Pydantic models for the transaction-scoped listing agent portal.
"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class TransactionStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    CLOSING = "closing"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class PartyRole(str, Enum):
    LISTING_AGENT = "listing_agent"
    SELLING_AGENT = "selling_agent"
    ESCROW_OFFICER = "escrow_officer"
    TITLE_OFFICER = "title_officer"
    ATTORNEY = "attorney"
    OTHER = "other"


class MilestoneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class DeliveryType(str, Enum):
    WEEKLY_UPDATE = "weekly_update"
    MILESTONE_CHANGE = "milestone_change"
    MESSAGE_NOTIFICATION = "message_notification"
    INVITE = "invite"
    REMINDER = "reminder"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"


class UnsubscribeType(str, Enum):
    ALL = "all"
    WEEKLY_UPDATES = "weekly_updates"
    MILESTONES = "milestones"
    MESSAGES = "messages"


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CreateTransactionRequest(BaseModel):
    """Request to create a new listing transaction"""
    loan_id: int
    property_address: str
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    purchase_price: Optional[float] = None
    contract_date: Optional[date] = None
    target_close_date: Optional[date] = None


class AddPartyRequest(BaseModel):
    """Request to add a party to a transaction"""
    role: PartyRole
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    company_name: Optional[str] = None
    license_number: Optional[str] = None
    notify_weekly_updates: bool = True
    notify_milestone_changes: bool = True
    notify_messages: bool = True


class UpdatePartyRequest(BaseModel):
    """Request to update party information"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    notify_weekly_updates: Optional[bool] = None
    notify_milestone_changes: Optional[bool] = None
    notify_messages: Optional[bool] = None


class UpdateMilestoneRequest(BaseModel):
    """Request to update a milestone status"""
    status: MilestoneStatus
    completed_at: Optional[datetime] = None
    target_date: Optional[date] = None


class SendMessageRequest(BaseModel):
    """Request to send a message"""
    content: str = Field(..., min_length=1, max_length=5000)
    attachments: Optional[List[Dict[str, str]]] = None


class MagicLinkAuthRequest(BaseModel):
    """Request to authenticate via magic link token"""
    token: str


class RefreshSessionRequest(BaseModel):
    """Request to refresh a session"""
    session_token: str


class UnsubscribeRequest(BaseModel):
    """Request to unsubscribe from notifications"""
    token: str
    unsubscribe_type: Optional[UnsubscribeType] = UnsubscribeType.ALL


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class PartyResponse(BaseModel):
    """Party information response"""
    id: int
    role: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    company_name: Optional[str] = None
    notify_weekly_updates: bool = True
    notify_milestone_changes: bool = True
    notify_messages: bool = True
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class MilestoneResponse(BaseModel):
    """Milestone information response"""
    id: int
    milestone_key: str
    milestone_name: str
    description: Optional[str] = None
    status: str
    completed_at: Optional[datetime] = None
    target_date: Optional[date] = None
    display_order: int

    model_config = {"from_attributes": True}


class TransactionResponse(BaseModel):
    """Transaction information response"""
    id: int
    loan_id: int
    property_address: str
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    purchase_price: Optional[float] = None
    contract_date: Optional[date] = None
    target_close_date: Optional[date] = None
    actual_close_date: Optional[date] = None
    current_status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TransactionDetailResponse(BaseModel):
    """Detailed transaction with parties and milestones"""
    transaction: TransactionResponse
    parties: List[PartyResponse] = []
    milestones: List[MilestoneResponse] = []
    unread_messages: int = 0


class MessageResponse(BaseModel):
    """Message response"""
    id: int
    transaction_id: int
    sender_name: str
    sender_type: str  # "party" or "lo"
    content: str
    attachments: List[Dict[str, str]] = []
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    """Conversation thread response"""
    transaction_id: int
    messages: List[MessageResponse] = []
    total_count: int = 0


class InviteResponse(BaseModel):
    """Portal invite response"""
    id: int
    party_id: int
    party_name: str
    party_email: str
    portal_url: str
    expires_at: datetime
    sent_via: str
    created_at: datetime


class SessionResponse(BaseModel):
    """Session authentication response"""
    session_token: str
    expires_at: datetime
    party: PartyResponse
    transaction: TransactionResponse


class DeliveryResponse(BaseModel):
    """Update delivery status response"""
    id: int
    party_id: int
    transaction_id: int
    delivery_type: str
    status: str
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    created_at: datetime


# =============================================================================
# PORTAL VIEW MODELS (for listing agents)
# =============================================================================

class PortalTransactionView(BaseModel):
    """Transaction view for listing agent portal (PII-safe)"""
    id: int
    property_address: str
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    purchase_price: Optional[float] = None
    target_close_date: Optional[date] = None
    current_status: str
    days_until_close: Optional[int] = None
    milestones: List[MilestoneResponse] = []
    unread_messages: int = 0
    last_update: Optional[datetime] = None


class PortalDashboardView(BaseModel):
    """Dashboard view for listing agent portal"""
    active_transactions: List[PortalTransactionView] = []
    recent_messages: List[MessageResponse] = []
    upcoming_closings: List[PortalTransactionView] = []


# =============================================================================
# SNAPSHOT MODELS (for weekly updates)
# =============================================================================

# PII-forbidden keys that must never be included in snapshots
FORBIDDEN_PII_KEYS = frozenset([
    "ssn", "social_security", "dob", "date_of_birth", "birth_date",
    "income", "salary", "assets", "debt", "credit_score", "fico",
    "bank_account", "account_number", "routing_number",
    "borrower_name", "borrower_email", "borrower_phone", "borrower_address",
    "co_borrower", "coborrower", "spouse",
    "employer", "employment", "w2", "tax_return",
    "password", "secret", "token", "api_key",
])


class TransactionSnapshot(BaseModel):
    """PII-safe snapshot of transaction status"""
    transaction_id: int
    property_address: str
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    purchase_price: Optional[float] = None
    target_close_date: Optional[date] = None
    current_status: str
    days_until_close: Optional[int] = None
    milestones: List[Dict[str, Any]] = []
    milestone_progress: Dict[str, int] = {}  # {"completed": 5, "total": 9}
    recent_activity: List[Dict[str, Any]] = []
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_safe_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with extra PII validation"""
        data = self.model_dump()
        # Double-check all keys
        for key in list(data.keys()):
            if key.lower() in FORBIDDEN_PII_KEYS:
                del data[key]
        return data


class WeeklyUpdateData(BaseModel):
    """Data structure for weekly update emails"""
    party_name: str
    party_email: str
    transaction_count: int
    transactions: List[TransactionSnapshot]
    unsubscribe_token: str
    unsubscribe_url: str
    portal_url: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def validate_no_pii(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and strip any PII from a dictionary.
    Returns cleaned data.
    """
    if not isinstance(data, dict):
        return data

    cleaned = {}
    for key, value in data.items():
        # Skip forbidden keys
        if key.lower() in FORBIDDEN_PII_KEYS:
            continue

        # Recursively clean nested dicts
        if isinstance(value, dict):
            cleaned[key] = validate_no_pii(value)
        elif isinstance(value, list):
            cleaned[key] = [
                validate_no_pii(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value

    return cleaned
