"""
Calendar Sync Models - CRM Calendar ↔ Salesforce Events Sync

Database models for bi-directional calendar synchronization between
CRM Calendar and Salesforce Events (which syncs to Outlook).

Tables:
- CalendarEvent: CRM Calendar events (internal system)
- CalendarEventSyncMap: Mapping between CRM and Salesforce events
- SyncWatermark: Track last sync times for polling loops
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, JSON, Boolean,
    ForeignKey, UniqueConstraint, Index, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from database import Base


# ============================================================================
# ENUMS
# ============================================================================

class CalendarEventStatus(str, enum.Enum):
    """Status of a calendar event"""
    SCHEDULED = "scheduled"
    CANCELED = "canceled"


class CalendarEventVisibility(str, enum.Enum):
    """Visibility level of a calendar event"""
    PRIVATE = "private"
    PUBLIC = "public"
    INTERNAL = "internal"


class CalendarEventSourceSystem(str, enum.Enum):
    """Source system where the event originated"""
    CRM = "crm"
    SALESFORCE = "salesforce"
    OUTLOOK = "outlook"


class CalendarSyncStatus(str, enum.Enum):
    """Sync status of a calendar event"""
    PENDING = "pending"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"


class ConflictResolutionPolicy(str, enum.Enum):
    """Conflict resolution policy for sync conflicts"""
    LAST_WRITE_WINS = "last_write_wins"
    CRM_WINS = "crm_wins"
    OUTLOOK_WINS = "outlook_wins"
    SALESFORCE_WINS = "salesforce_wins"


# ============================================================================
# CALENDAR EVENT MODEL
# ============================================================================

class CalendarEvent(Base):
    """
    CRM Calendar events - internal system events that sync with Salesforce.

    This is the primary calendar event table for the CRM. Events here are
    synchronized bi-directionally with Salesforce Event objects, which in
    turn sync with Outlook calendars.
    """
    __tablename__ = "calendar_events"
    __table_args__ = (
        Index('ix_calendar_events_owner', 'owner_user_id'),
        Index('ix_calendar_events_start', 'start_at'),
        Index('ix_calendar_events_sync_status', 'sync_status'),
        Index('ix_calendar_events_pending_sync', 'last_modified_at',
              postgresql_where="sync_status = 'pending'"),
        {'extend_existing': True}
    )

    id = Column(String(36), primary_key=True)  # ULID/UUID format

    # Core event fields
    title = Column(String(255), nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=False)
    timezone = Column(String(50), default="America/New_York")
    all_day = Column(Boolean, default=False)
    location = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    # Ownership
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Attendees (stored as JSON array of emails or CRM contact IDs)
    attendees = Column(JSON, default=list)

    # Related entity (lead/contact/opportunity/deal)
    related_entity_type = Column(String(50), nullable=True)  # lead, contact, opportunity, deal
    related_entity_id = Column(String(50), nullable=True)  # ID of the related entity

    # Event status and visibility
    status = Column(SQLEnum(CalendarEventStatus), default=CalendarEventStatus.SCHEDULED)
    visibility = Column(SQLEnum(CalendarEventVisibility), default=CalendarEventVisibility.INTERNAL)

    # Sync metadata - critical for bi-directional sync
    source_system = Column(SQLEnum(CalendarEventSourceSystem), default=CalendarEventSourceSystem.CRM)
    last_modified_by_system = Column(SQLEnum(CalendarEventSourceSystem), default=CalendarEventSourceSystem.CRM)
    last_modified_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(SQLEnum(CalendarSyncStatus), default=CalendarSyncStatus.PENDING)
    sync_error = Column(Text, nullable=True)

    # Fingerprint hash for change detection (SHA-256 of normalized content)
    fingerprint_hash = Column(String(64), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", backref="calendar_events", foreign_keys=[owner_user_id])
    sync_map = relationship("CalendarEventSyncMap", back_populates="crm_event",
                           uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CalendarEvent(id={self.id}, title={self.title[:30] if self.title else ''}, status={self.status})>"


# ============================================================================
# SYNC MAP MODEL
# ============================================================================

class CalendarEventSyncMap(Base):
    """
    Mapping table between CRM Calendar events and Salesforce Event objects.

    This table tracks the relationship between internal CRM events and their
    corresponding Salesforce Event records. It also stores sync metadata
    used for loop prevention and change detection.
    """
    __tablename__ = "calendar_event_sync_map"
    __table_args__ = (
        Index('ix_sync_map_sf_event', 'salesforce_event_id'),
        Index('ix_sync_map_last_pulled', 'last_pulled_at'),
        Index('ix_sync_map_pending_push', 'last_pushed_at'),
        {'extend_existing': True}
    )

    # Primary key is the CRM event ID
    crm_event_id = Column(String(36), ForeignKey('calendar_events.id', ondelete='CASCADE'),
                          primary_key=True)

    # Salesforce Event ID (18-character Salesforce ID)
    salesforce_event_id = Column(String(18), unique=True, nullable=True, index=True)

    # Salesforce owner (user who owns the event in Salesforce)
    salesforce_owner_id = Column(String(18), nullable=True)

    # External calendar ID (Outlook calendar event ID if available)
    external_calendar_id = Column(String(255), nullable=True)

    # Fingerprint for echo/loop prevention
    fingerprint_hash = Column(String(64), nullable=False)

    # Push/Pull tracking
    last_pushed_at = Column(DateTime(timezone=True), nullable=True)
    last_pulled_at = Column(DateTime(timezone=True), nullable=True)

    # Last known Salesforce modification time (for conflict detection)
    last_seen_salesforce_modified_at = Column(DateTime(timezone=True), nullable=True)

    # Version for optimistic locking
    sync_version = Column(Integer, default=1)

    # Lock token for deduplication during concurrent sync operations
    lock_token = Column(String(64), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship back to CRM event
    crm_event = relationship("CalendarEvent", back_populates="sync_map")

    def __repr__(self):
        return f"<CalendarEventSyncMap(crm={self.crm_event_id}, sf={self.salesforce_event_id})>"


# ============================================================================
# SYNC WATERMARK MODEL
# ============================================================================

class SyncWatermark(Base):
    """
    Tracks sync watermarks for polling-based synchronization.

    Watermarks record the last successful sync timestamp for each sync type,
    enabling incremental polling that only fetches records modified since
    the last successful poll.
    """
    __tablename__ = "sync_watermarks"
    __table_args__ = {'extend_existing': True}

    # Sync type identifier (e.g., 'salesforce_calendar_pull', 'salesforce_calendar_push')
    sync_type = Column(String(100), primary_key=True)

    # Last successful sync timestamp
    last_synced_at = Column(DateTime(timezone=True), nullable=False)

    # Additional metadata about the sync
    records_processed = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SyncWatermark(type={self.sync_type}, last_synced={self.last_synced_at})>"


# ============================================================================
# CALENDAR SYNC SETTINGS MODEL
# ============================================================================

class CalendarSyncSettings(Base):
    """
    Per-user calendar sync settings and configuration.

    Allows users to customize their calendar sync behavior, including
    conflict resolution policies and sync direction preferences.
    """
    __tablename__ = "calendar_sync_settings"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Integration profile link (for Salesforce OAuth credentials)
    integration_profile_id = Column(Integer, ForeignKey("integration_profiles.id"), nullable=True)

    # Sync mode
    sync_mode = Column(String(50), default="crm_only")  # crm_only | all_salesforce_events

    # Conflict resolution policy
    conflict_policy = Column(
        SQLEnum(ConflictResolutionPolicy),
        default=ConflictResolutionPolicy.LAST_WRITE_WINS
    )

    # Echo prevention window (in seconds)
    echo_ignore_window_seconds = Column(Integer, default=90)

    # Sync intervals (in seconds)
    push_interval_seconds = Column(Integer, default=60)
    pull_interval_seconds = Column(Integer, default=60)

    # Batch size for sync operations
    batch_size = Column(Integer, default=100)

    # Maximum retry attempts
    max_retries = Column(Integer, default=5)

    # Delete policy
    delete_policy = Column(String(50), default="soft_cancel")  # soft_cancel | hard_delete

    # Enable immediate push on event creation (don't wait for cycle)
    enable_immediate_push = Column(Boolean, default=True)

    # Salesforce API version
    salesforce_api_version = Column(String(10), default="v60.0")

    # Sync enabled flag
    sync_enabled = Column(Boolean, default=True)

    # Last sync status
    last_push_at = Column(DateTime(timezone=True), nullable=True)
    last_pull_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="calendar_sync_settings")
    integration_profile = relationship("IntegrationProfile", backref="calendar_sync_settings")

    def __repr__(self):
        return f"<CalendarSyncSettings(user_id={self.user_id}, enabled={self.sync_enabled})>"


# ============================================================================
# CALENDAR SYNC EVENT LOG
# ============================================================================

class CalendarSyncEventLog(Base):
    """
    Audit log for calendar sync operations.

    Tracks all sync events for debugging, monitoring, and audit purposes.
    """
    __tablename__ = "calendar_sync_event_logs"
    __table_args__ = (
        Index('ix_sync_log_timestamp', 'created_at'),
        Index('ix_sync_log_crm_event', 'crm_event_id'),
        Index('ix_sync_log_direction', 'direction'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Event references
    crm_event_id = Column(String(36), nullable=True)
    salesforce_event_id = Column(String(18), nullable=True)

    # Sync details
    direction = Column(String(10), nullable=False)  # push | pull
    operation = Column(String(20), nullable=False)  # create | update | delete

    # Content hashes for debugging
    fingerprint_before = Column(String(64), nullable=True)
    fingerprint_after = Column(String(64), nullable=True)

    # Result
    result = Column(String(20), nullable=False)  # success | failed | skipped | echo
    error_message = Column(Text, nullable=True)

    # Performance tracking
    duration_ms = Column(Integer, nullable=True)

    # Source system that triggered this sync
    source_system = Column(String(20), nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __repr__(self):
        return f"<CalendarSyncEventLog(direction={self.direction}, result={self.result})>"


# ============================================================================
# SALESFORCE USER MAPPING
# ============================================================================

class SalesforceUserMapping(Base):
    """
    Mapping between CRM user IDs and Salesforce user IDs.

    Required for proper event ownership assignment during sync.
    """
    __tablename__ = "salesforce_user_mappings"
    __table_args__ = (
        UniqueConstraint('crm_user_id', 'salesforce_user_id', name='uq_user_mapping'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    crm_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    salesforce_user_id = Column(String(18), nullable=False, unique=True, index=True)

    # User email for fallback matching
    email = Column(String(255), nullable=True)

    # Sync preferences
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = relationship("User", backref="salesforce_mapping")

    def __repr__(self):
        return f"<SalesforceUserMapping(crm={self.crm_user_id}, sf={self.salesforce_user_id})>"
