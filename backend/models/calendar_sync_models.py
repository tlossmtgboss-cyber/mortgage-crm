"""
Calendar Sync Models
Database models for CRM ↔ Salesforce ↔ Outlook calendar synchronization
"""
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, JSON, Boolean,
    ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from enum import Enum

from database import Base


class EventStatus(str, Enum):
    """Event status enumeration"""
    SCHEDULED = "scheduled"
    CANCELED = "canceled"
    COMPLETED = "completed"


class SyncStatus(str, Enum):
    """Sync status enumeration"""
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class SourceSystem(str, Enum):
    """Source system enumeration"""
    CRM = "crm"
    SALESFORCE = "salesforce"
    OUTLOOK = "outlook"


class ConflictPolicy(str, Enum):
    """Conflict resolution policy"""
    LAST_WRITE_WINS = "last_write_wins"
    CRM_WINS = "crm_wins"
    OUTLOOK_WINS = "outlook_wins"
    SALESFORCE_WINS = "salesforce_wins"


class DeletePolicy(str, Enum):
    """Delete policy enumeration"""
    SOFT_CANCEL = "soft_cancel"
    HARD_DELETE = "hard_delete"
    IGNORE = "ignore"


class CRMCalendarEvent(Base):
    """
    CRM Calendar Event
    Stores all calendar events in the CRM that sync with Salesforce/Outlook
    """
    __tablename__ = "crm_calendar_events"
    __table_args__ = (
        Index('idx_calendar_owner_start', 'owner_user_id', 'start_at'),
        Index('idx_calendar_sync_status', 'sync_status'),
        Index('idx_calendar_fingerprint', 'fingerprint_hash'),
        {'extend_existing': True}
    )

    # Primary key - using string UUID for compatibility
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Event details
    title = Column(String(255), nullable=False)
    start_at = Column(DateTime, nullable=False, index=True)
    end_at = Column(DateTime, nullable=False)
    timezone = Column(String(50), default="America/New_York")
    all_day = Column(Boolean, default=False)
    location = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    # Ownership
    owner_user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Attendees as JSON array: [{"email": "...", "name": "...", "status": "..."}]
    attendees = Column(JSON, default=list)

    # Related entity linking
    related_entity_type = Column(String(50), nullable=True)  # lead, contact, opportunity, loan
    related_entity_id = Column(Integer, nullable=True)

    # Status
    status = Column(String(20), default=EventStatus.SCHEDULED.value)

    # Source tracking
    source_system = Column(String(20), default=SourceSystem.CRM.value)
    last_modified_by_system = Column(String(20), default=SourceSystem.CRM.value)
    last_modified_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Sync tracking
    last_synced_at = Column(DateTime, nullable=True)
    sync_status = Column(String(20), default=SyncStatus.PENDING.value)
    sync_error = Column(Text, nullable=True)

    # Fingerprint for change detection and loop prevention
    fingerprint_hash = Column(String(64), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship to sync mapping
    sync_mapping = relationship("CalendarEventSyncMap", back_populates="crm_event", uselist=False, cascade="all, delete-orphan")

    def compute_fingerprint(self) -> str:
        """
        Compute SHA256 fingerprint for change detection.
        Used to prevent sync loops and detect meaningful changes.
        """
        # Normalize values
        title_normalized = (self.title or "").strip().lower()
        start_str = self.start_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.start_at else ""
        end_str = self.end_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.end_at else ""
        all_day_str = "true" if self.all_day else "false"
        location_normalized = (self.location or "").strip().lower()
        notes_normalized = (self.notes or "").strip()

        # Concatenate with delimiter
        concatenated = f"{title_normalized}|{start_str}|{end_str}|{all_day_str}|{location_normalized}|{notes_normalized}"

        # Compute hash
        return hashlib.sha256(concatenated.encode('utf-8')).hexdigest()

    def update_fingerprint(self):
        """Update the fingerprint hash"""
        self.fingerprint_hash = self.compute_fingerprint()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "timezone": self.timezone,
            "all_day": self.all_day,
            "location": self.location,
            "notes": self.notes,
            "owner_user_id": self.owner_user_id,
            "attendees": self.attendees or [],
            "related_entity_type": self.related_entity_type,
            "related_entity_id": self.related_entity_id,
            "status": self.status,
            "source_system": self.source_system,
            "last_modified_by_system": self.last_modified_by_system,
            "last_modified_at": self.last_modified_at.isoformat() if self.last_modified_at else None,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
            "fingerprint_hash": self.fingerprint_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "salesforce_event_id": self.sync_mapping.salesforce_event_id if self.sync_mapping else None,
        }

    def to_salesforce_event(self, sf_owner_id: str = None) -> Dict[str, Any]:
        """
        Convert to Salesforce Event object format.

        Args:
            sf_owner_id: Salesforce User ID for event owner
        """
        event_data = {
            "Subject": self.title,
            "StartDateTime": self.start_at.strftime("%Y-%m-%dT%H:%M:%S.000+0000") if self.start_at else None,
            "EndDateTime": self.end_at.strftime("%Y-%m-%dT%H:%M:%S.000+0000") if self.end_at else None,
            "IsAllDayEvent": self.all_day,
            "Location": self.location,
            "Description": self.notes,
            "CRM_Event_ID__c": self.id,
            "CRM_Last_Pushed_At__c": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
            "CRM_Fingerprint__c": self.fingerprint_hash,
            "CRM_Source__c": "crm",
            "CRM_Sync_Version__c": 1,
        }

        if sf_owner_id:
            event_data["OwnerId"] = sf_owner_id

        return event_data


class CalendarEventSyncMap(Base):
    """
    Calendar Event Sync Mapping
    Tracks the relationship between CRM events and Salesforce events
    """
    __tablename__ = "calendar_event_sync_map"
    __table_args__ = (
        Index('idx_sync_map_sf_event', 'salesforce_event_id'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)

    # CRM event reference (unique)
    crm_event_id = Column(String(36), ForeignKey('crm_calendar_events.id'), unique=True, nullable=False)

    # Salesforce event reference (unique when not null)
    salesforce_event_id = Column(String(18), unique=True, nullable=True, index=True)

    # Sync tracking
    fingerprint_hash = Column(String(64), nullable=True)  # Last synced fingerprint
    last_pushed_at = Column(DateTime, nullable=True)
    last_pulled_at = Column(DateTime, nullable=True)
    last_seen_sf_modified_at = Column(DateTime, nullable=True)

    # Version tracking
    sync_version = Column(Integer, default=1)

    # Optimistic locking
    lock_token = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    crm_event = relationship("CRMCalendarEvent", back_populates="sync_mapping")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "crm_event_id": self.crm_event_id,
            "salesforce_event_id": self.salesforce_event_id,
            "fingerprint_hash": self.fingerprint_hash,
            "last_pushed_at": self.last_pushed_at.isoformat() if self.last_pushed_at else None,
            "last_pulled_at": self.last_pulled_at.isoformat() if self.last_pulled_at else None,
            "last_seen_sf_modified_at": self.last_seen_sf_modified_at.isoformat() if self.last_seen_sf_modified_at else None,
            "sync_version": self.sync_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CalendarSyncLog(Base):
    """
    Calendar Sync Log
    Audit trail for all sync operations
    """
    __tablename__ = "calendar_sync_log"
    __table_args__ = (
        Index('idx_sync_log_user', 'user_id'),
        Index('idx_sync_log_created', 'created_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)

    # Event references
    crm_event_id = Column(String(36), nullable=True)
    salesforce_event_id = Column(String(18), nullable=True)
    user_id = Column(Integer, nullable=True)

    # Operation details
    direction = Column(String(10), nullable=False)  # push, pull
    operation = Column(String(20), nullable=False)  # create, update, cancel, delete

    # Fingerprint tracking
    fingerprint_before = Column(String(64), nullable=True)
    fingerprint_after = Column(String(64), nullable=True)

    # Result
    result = Column(String(20), nullable=False)  # success, failed, skipped
    error_message = Column(Text, nullable=True)

    # Performance
    duration_ms = Column(Integer, nullable=True)

    # Timestamp
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "crm_event_id": self.crm_event_id,
            "salesforce_event_id": self.salesforce_event_id,
            "user_id": self.user_id,
            "direction": self.direction,
            "operation": self.operation,
            "fingerprint_before": self.fingerprint_before,
            "fingerprint_after": self.fingerprint_after,
            "result": self.result,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CalendarSyncSettings(Base):
    """
    Calendar Sync Settings
    Configuration for calendar synchronization behavior
    """
    __tablename__ = "calendar_sync_settings"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)

    # Scope: null = global, user_id = per-user settings
    user_id = Column(Integer, nullable=True, unique=True, index=True)

    # Sync mode
    calendar_sync_mode = Column(String(30), default="crm_only")  # crm_only, all_salesforce

    # Conflict resolution
    conflict_policy = Column(String(30), default=ConflictPolicy.LAST_WRITE_WINS.value)

    # Loop prevention
    echo_ignore_window_seconds = Column(Integer, default=60)

    # SLA
    sync_sla_seconds = Column(Integer, default=60)

    # Delete behavior
    delete_policy = Column(String(20), default=DeletePolicy.SOFT_CANCEL.value)

    # Polling configuration
    polling_enabled = Column(Boolean, default=False)
    polling_interval_seconds = Column(Integer, default=300)

    # CDC configuration
    cdc_enabled = Column(Boolean, default=True)

    # Batch size
    batch_size = Column(Integer, default=200)

    # Per-user settings
    sync_enabled = Column(Boolean, default=True)
    sync_direction = Column(String(20), default="bidirectional")  # inbound, outbound, bidirectional
    default_event_duration_minutes = Column(Integer, default=30)

    # Watermark for polling
    last_poll_watermark = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "calendar_sync_mode": self.calendar_sync_mode,
            "conflict_policy": self.conflict_policy,
            "echo_ignore_window_seconds": self.echo_ignore_window_seconds,
            "sync_sla_seconds": self.sync_sla_seconds,
            "delete_policy": self.delete_policy,
            "polling_enabled": self.polling_enabled,
            "polling_interval_seconds": self.polling_interval_seconds,
            "cdc_enabled": self.cdc_enabled,
            "batch_size": self.batch_size,
            "sync_enabled": self.sync_enabled,
            "sync_direction": self.sync_direction,
            "default_event_duration_minutes": self.default_event_duration_minutes,
        }
