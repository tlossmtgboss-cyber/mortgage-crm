"""
Follow Up Boss Integration Models
Perennia AI - Mortgage CRM

Database models for Follow Up Boss CRM integration:
- FUBUserConnection: Per-user API connection
- FUBLeadMapping: Maps FUB people to CRM leads
- FUBSyncEvent: Audit log for sync operations
- FUBStageMapping: Stage name mapping between systems
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, JSON, Enum as SQLEnum, Index, func
)
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

from database import Base


# =============================================================================
# ENUMS
# =============================================================================

class FUBSyncDirection(str, Enum):
    """Direction of sync operation."""
    INBOUND = "inbound"      # FUB → CRM
    OUTBOUND = "outbound"    # CRM → FUB
    BIDIRECTIONAL = "bidirectional"


class FUBSyncStatus(str, Enum):
    """Status of sync operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FUBEventType(str, Enum):
    """Types of FUB webhook events."""
    PEOPLE_CREATED = "people.created"
    PEOPLE_UPDATED = "people.updated"
    PEOPLE_STAGE_CHANGED = "people.stage_changed"
    PEOPLE_ASSIGNED = "people.assigned"
    NOTES_CREATED = "notes.created"
    NOTES_UPDATED = "notes.updated"
    MANUAL_SYNC = "manual_sync"
    SCHEDULED_SYNC = "scheduled_sync"


# =============================================================================
# SQLALCHEMY MODELS
# =============================================================================

class FUBUserConnection(Base):
    """
    Per-user Follow Up Boss API connection.
    Each user can connect their own FUB account.
    """
    __tablename__ = "fub_user_connections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # API credentials (encrypted)
    api_key_encrypted = Column(Text, nullable=False)

    # FUB user info (fetched on connect)
    fub_user_id = Column(Integer, nullable=True)
    fub_user_email = Column(String(255), nullable=True)
    fub_user_name = Column(String(255), nullable=True)

    # Webhook configuration
    webhook_secret = Column(String(64), nullable=True)  # For validating incoming webhooks
    webhook_url = Column(String(500), nullable=True)    # Generated URL to configure in FUB

    # Sync settings
    sync_enabled = Column(Boolean, default=True)
    sync_notes = Column(Boolean, default=True)
    sync_stages = Column(Boolean, default=True)
    sync_lead_updates = Column(Boolean, default=True)

    # Sync tracking
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    lead_mappings = relationship("FUBLeadMapping", back_populates="connection", cascade="all, delete-orphan")
    sync_events = relationship("FUBSyncEvent", back_populates="connection", cascade="all, delete-orphan")
    stage_mappings = relationship("FUBStageMapping", back_populates="connection", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_fub_connections_user_id", "user_id"),
    )


class FUBLeadMapping(Base):
    """
    Maps FUB person IDs to CRM lead IDs.
    Tracks sync state and change detection.
    """
    __tablename__ = "fub_lead_mappings"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("fub_user_connections.id", ondelete="CASCADE"), nullable=False)

    # ID mapping
    fub_person_id = Column(Integer, nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)

    # Sync tracking
    sync_hash = Column(String(64), nullable=True)  # MD5 hash of last synced data
    last_synced_at = Column(DateTime, nullable=True)
    sync_direction = Column(String(20), default="bidirectional")  # Last sync direction

    # FUB metadata cache
    fub_stage = Column(String(100), nullable=True)
    fub_assigned_to = Column(String(255), nullable=True)
    fub_updated_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("FUBUserConnection", back_populates="lead_mappings")

    __table_args__ = (
        Index("uq_fub_mappings_connection_person", "connection_id", "fub_person_id", unique=True),
        Index("ix_fub_mappings_lead", "lead_id"),
    )


class FUBSyncEvent(Base):
    """
    Audit log for all sync operations.
    Tracks both inbound (webhook) and outbound (push) events.
    """
    __tablename__ = "fub_sync_events"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("fub_user_connections.id", ondelete="CASCADE"), nullable=False)

    # Event details
    event_type = Column(String(50), nullable=False)  # FUBEventType value
    direction = Column(String(20), nullable=False)   # inbound/outbound

    # Entity references
    fub_entity_type = Column(String(50), nullable=True)  # people, notes, events
    fub_entity_id = Column(Integer, nullable=True)
    crm_entity_type = Column(String(50), nullable=True)  # lead, activity
    crm_entity_id = Column(Integer, nullable=True)

    # Result
    status = Column(String(20), nullable=False, default="pending")  # FUBSyncStatus value
    error_message = Column(Text, nullable=True)

    # Payload (for debugging)
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    connection = relationship("FUBUserConnection", back_populates="sync_events")

    __table_args__ = (
        Index("ix_fub_events_connection_created", "connection_id", "created_at"),
        Index("ix_fub_events_status", "status"),
    )


class FUBStageMapping(Base):
    """
    Maps FUB stage names to CRM LeadStage values.
    Auto-populated on connect, user can override.
    """
    __tablename__ = "fub_stage_mappings"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("fub_user_connections.id", ondelete="CASCADE"), nullable=False)

    # Stage mapping
    fub_stage_name = Column(String(100), nullable=False)
    fub_stage_id = Column(Integer, nullable=True)  # FUB internal stage ID if available
    crm_stage = Column(String(50), nullable=False)  # LeadStage enum value

    # Mapping metadata
    is_auto_mapped = Column(Boolean, default=True)  # False if user manually set
    confidence_score = Column(Integer, default=100)  # Auto-mapping confidence 0-100

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("FUBUserConnection", back_populates="stage_mappings")

    __table_args__ = (
        Index("ix_fub_stages_connection_fub", "connection_id", "fub_stage_name"),
    )


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class FUBConnectRequest(BaseModel):
    """Request to connect FUB account."""
    api_key: str = Field(..., min_length=10, description="Follow Up Boss API key")


class FUBConnectionStatus(BaseModel):
    """FUB connection status response."""
    connected: bool
    fub_user_email: Optional[str] = None
    fub_user_name: Optional[str] = None
    sync_enabled: bool = True
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    webhook_url: Optional[str] = None
    total_synced_leads: int = 0


class FUBStageMappingItem(BaseModel):
    """Single stage mapping item."""
    fub_stage_name: str
    fub_stage_id: Optional[int] = None
    crm_stage: str
    is_auto_mapped: bool = True


class FUBStageMappingResponse(BaseModel):
    """Stage mapping list response."""
    mappings: List[FUBStageMappingItem]


class FUBStageMappingUpdate(BaseModel):
    """Request to update stage mappings."""
    mappings: List[FUBStageMappingItem]


class FUBSyncEventResponse(BaseModel):
    """Sync event for history display."""
    id: int
    event_type: str
    direction: str
    status: str
    fub_entity_type: Optional[str] = None
    crm_entity_type: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime


class FUBSyncHistoryResponse(BaseModel):
    """Sync history response."""
    events: List[FUBSyncEventResponse]
    total: int


class FUBWebhookPayload(BaseModel):
    """FUB webhook event payload."""
    event: str
    data: dict
    timestamp: Optional[str] = None


# =============================================================================
# FIELD MAPPING CONFIGURATION
# =============================================================================

# FUB person fields → CRM lead fields
FUB_TO_CRM_FIELD_MAP = {
    "firstName": "first_name",
    "lastName": "last_name",
    "name": "name",  # Full name fallback
    "emails": "email",  # Will extract first email
    "phones": "phone",  # Will extract first phone
    "stage": "stage",  # Requires stage mapping
    "source": "source",
    "assignedTo": None,  # Handled specially - lookup user
    "price": "loan_amount",
    "propertyStreet": "address",
    "propertyCity": "city",
    "propertyState": "state",
    "propertyZip": "zip_code",
    "tags": None,  # Store in metadata
    "created": "lead_received_date",
    "updated": None,  # Track separately
}

# CRM lead fields → FUB person fields (for outbound sync)
CRM_TO_FUB_FIELD_MAP = {
    "first_name": "firstName",
    "last_name": "lastName",
    "email": "emails",  # Will format as array
    "phone": "phones",  # Will format as array
    "stage": "stage",  # Requires reverse stage mapping
    "source": "source",
    "loan_amount": "price",
    "address": "propertyStreet",
    "city": "propertyCity",
    "state": "propertyState",
    "zip_code": "propertyZip",
}

# Default stage mapping (FUB stage → CRM LeadStage)
DEFAULT_STAGE_MAPPINGS = {
    "New Lead": "NEW",
    "Attempted Contact": "ATTEMPTED_CONTACT",
    "Made Contact": "PROSPECT",
    "Qualified": "PRE_QUALIFIED",
    "Appointment Set": "PROSPECT",
    "Met In Person": "PROSPECT",
    "Showed Property": "PROSPECT",
    "Submitted Offer": "APPLICATION",
    "Under Contract": "UNDER_CONTRACT",
    "Closed": "CLOSED",
    "On Hold": "LONG_TERM_NURTURE",
    "Trash": "WITHDRAWN",
    "Unqualified": "DOES_NOT_QUALIFY",
    # Add more as needed
}
