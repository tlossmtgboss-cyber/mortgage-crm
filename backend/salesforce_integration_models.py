"""
Salesforce Integration - Database Models
Per-user Salesforce integration with OAuth, schema discovery, field mappings, and sync
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class IntegrationProfile(Base):
    """Per-user integration connection to Salesforce"""
    __tablename__ = "integration_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)  # FK to users.id exists in DB
    provider = Column(String(50), nullable=False, default='salesforce')
    status = Column(String(50), nullable=False, default='disconnected')
    # Status values: disconnected, connected, mapping_required, active, error, suspended

    # OAuth Credentials (encrypted)
    access_token_encrypted = Column(Text)
    refresh_token_encrypted = Column(Text)
    instance_url = Column(Text)

    # Salesforce Specifics
    sf_org_id = Column(String(100))
    sf_user_id = Column(String(100))
    sf_username = Column(String(255))

    # Metadata
    connected_at = Column(DateTime)
    last_sync_at = Column(DateTime)
    last_error = Column(Text)
    field_map_version = Column(Integer, default=1)

    # Settings
    sync_enabled = Column(Boolean, default=True)
    sync_interval_minutes = Column(Integer, default=15)
    sync_direction = Column(String(20), default='bidirectional')  # inbound, outbound, bidirectional

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    schemas = relationship("SfUserSchema", back_populates="profile", cascade="all, delete-orphan")
    field_mappings = relationship("FieldMapping", back_populates="profile", cascade="all, delete-orphan")
    events = relationship("IntegrationEvent", back_populates="profile", cascade="all, delete-orphan")
    sync_queue_items = relationship("SyncQueueItem", back_populates="profile", cascade="all, delete-orphan")
    record_tracking = relationship("IntegrationRecordTracking", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('user_id', 'provider', name='uq_user_provider'),
        {'extend_existing': True}
    )


class SfUserSchema(Base):
    """Discovered Salesforce schema for a user's org"""
    __tablename__ = "sf_user_schemas"

    id = Column(Integer, primary_key=True, index=True)
    integration_profile_id = Column(Integer, ForeignKey('integration_profiles.id'), nullable=False)
    object_name = Column(String(100), nullable=False)  # Lead, Contact, Opportunity, etc.

    # Raw schema from Salesforce
    fields = Column(JSON, nullable=False)  # Array of field metadata
    record_types = Column(JSON)  # Available record types
    picklist_values = Column(JSON)  # Picklist options

    # Object-level enable/disable (controls visibility in Field Mappings)
    enabled = Column(Boolean, default=True)

    # Metadata
    discovered_at = Column(DateTime, default=datetime.utcnow)
    last_validated_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    profile = relationship("IntegrationProfile", back_populates="schemas")

    __table_args__ = (
        UniqueConstraint('integration_profile_id', 'object_name', name='uq_profile_object'),
        {'extend_existing': True}
    )


class FieldMapping(Base):
    """User's field transformation rules from Salesforce to CRM"""
    __tablename__ = "field_mappings"

    id = Column(Integer, primary_key=True, index=True)
    integration_profile_id = Column(Integer, ForeignKey('integration_profiles.id'), nullable=False)

    # Source (Salesforce side)
    source_object = Column(String(100), nullable=False)  # Lead, Contact, etc.
    source_field = Column(String(255), nullable=False)  # Salesforce API name

    # Target (CRM side)
    target_entity = Column(String(100), nullable=False)  # borrower, loan, application, etc.
    target_field = Column(String(255), nullable=False)  # Canonical field name

    # Transformation Rules
    transform_type = Column(String(50))  # direct, picklist_map, stage_map, date_format, currency_convert, phone_format
    transform_config = Column(JSON)  # Configuration for the transform

    # Mapping categorization (field mapper v2)
    mapping_category = Column(String(50))  # sla_milestone, crm_field

    # Validation
    data_type = Column(String(50))  # string, number, date, boolean, picklist, etc.
    required = Column(Boolean, default=False)
    default_value = Column(Text)

    # Sync Direction
    sync_direction = Column(String(20), default='bidirectional')  # inbound, outbound, bidirectional

    # Status
    enabled = Column(Boolean, default=True)
    validation_status = Column(String(50), default='pending')  # pending, valid, invalid, warning
    validation_message = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    profile = relationship("IntegrationProfile", back_populates="field_mappings")

    __table_args__ = (
        UniqueConstraint('integration_profile_id', 'source_object', 'source_field', name='uq_profile_source'),
        {'extend_existing': True}
    )


class IntegrationEvent(Base):
    """Audit trail of all integration operations"""
    __tablename__ = "integration_events"

    id = Column(Integer, primary_key=True, index=True)
    integration_profile_id = Column(Integer, ForeignKey('integration_profiles.id'), nullable=False)

    event_type = Column(String(100), nullable=False)  # sync_started, sync_completed, sync_failed, etc.
    direction = Column(String(20))  # inbound, outbound

    # Context
    source_object = Column(String(100))
    source_record_id = Column(String(100))
    target_entity = Column(String(100))
    target_record_id = Column(Integer)

    # Details
    records_processed = Column(Integer)
    records_succeeded = Column(Integer)
    records_failed = Column(Integer)

    # Error Tracking
    status = Column(String(50), nullable=False, default='pending')  # success, warning, error, pending
    error_message = Column(Text)
    error_details = Column(JSON)

    # Performance
    duration_ms = Column(Integer)

    # Full Event Data
    event_data = Column(JSON)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    profile = relationship("IntegrationProfile", back_populates="events")

    __table_args__ = {'extend_existing': True}


class SyncQueueItem(Base):
    """Queue for managing async sync operations"""
    __tablename__ = "sync_queue"

    id = Column(Integer, primary_key=True, index=True)
    integration_profile_id = Column(Integer, ForeignKey('integration_profiles.id'), nullable=False)

    operation = Column(String(50), nullable=False)  # full_sync, incremental_sync, single_record, schema_refresh
    direction = Column(String(20), nullable=False)  # inbound, outbound

    # Payload
    source_object = Column(String(100))
    source_record_id = Column(String(100))
    priority = Column(Integer, default=5)  # 1-10, higher = more urgent

    # Status
    status = Column(String(50), default='pending')  # pending, processing, completed, failed, retry
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)

    # Timing
    scheduled_for = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Results
    result = Column(JSON)
    error_message = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    profile = relationship("IntegrationProfile", back_populates="sync_queue_items")

    __table_args__ = {'extend_existing': True}


class OAuthState(Base):
    """Temporary storage for OAuth CSRF protection"""
    __tablename__ = "oauth_states"

    id = Column(Integer, primary_key=True, index=True)
    state_token = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    provider = Column(String(50), nullable=False)

    # Security
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

    # Context
    return_url = Column(Text)
    state_metadata = Column(JSON)


class IntegrationRecordTracking(Base):
    """Track synced records for change detection"""
    __tablename__ = "integration_record_tracking"

    id = Column(Integer, primary_key=True, index=True)
    integration_profile_id = Column(Integer, ForeignKey('integration_profiles.id'), nullable=False)

    # Source (Salesforce)
    source_object = Column(String(100), nullable=False)
    source_record_id = Column(String(100), nullable=False)

    # Target (CRM)
    target_entity = Column(String(100), nullable=False)
    target_record_id = Column(Integer)

    # Sync Metadata
    last_synced_at = Column(DateTime, nullable=False)
    sync_hash = Column(String(64))  # MD5 hash for change detection
    sync_status = Column(String(50), default='synced')  # synced, pending, conflict, error

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    profile = relationship("IntegrationProfile", back_populates="record_tracking")

    __table_args__ = (
        UniqueConstraint('integration_profile_id', 'source_object', 'source_record_id', name='uq_profile_source_record'),
        {'extend_existing': True}
    )
