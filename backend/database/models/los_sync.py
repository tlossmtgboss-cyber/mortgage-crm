"""
LOS Integration & Sync Models

Models for field-level mapping configuration and per-loan sync state tracking.
Addresses Module 12 gap: LosFieldMapping, LosSyncLog.

Usage:
    from database.models.los_sync import LosFieldMapping, LosSyncLog
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Index, Numeric
)
from sqlalchemy.orm import relationship

from db import Base

import enum


class SyncDirection(str, enum.Enum):
    """Direction of LOS sync"""
    PUSH = "push"         # CRM -> LOS
    PULL = "pull"         # LOS -> CRM
    BIDIRECTIONAL = "bidirectional"


class ConflictStrategy(str, enum.Enum):
    """How to resolve sync conflicts"""
    CRM_WINS = "crm_wins"
    LOS_WINS = "los_wins"
    MOST_RECENT = "most_recent"
    MANUAL = "manual"


class SyncStatus(str, enum.Enum):
    """Status of a sync operation"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CONFLICT = "conflict"
    PENDING_REVIEW = "pending_review"


# ============================================================================
# LOS FIELD MAPPING
# ============================================================================

class LosFieldMapping(Base):
    """Field-level mapping between CRM and LOS systems.

    Enables configurable, auditable field mapping with transformation support.
    Follows Module 12.1 spec: push/pull with conflict resolution.
    """
    __tablename__ = "los_field_mappings"
    __table_args__ = (
        Index('ix_los_mapping_org_id', 'organization_id'),
        Index('ix_los_mapping_system', 'los_system'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)

    los_system = Column(String, nullable=False)  # encompass, salesforce, calyx, blend
    entity_type = Column(String, nullable=False)  # loan, lead, contact, document

    # Field mapping
    crm_field_name = Column(String, nullable=False)   # e.g., "loan_amount"
    los_field_name = Column(String, nullable=False)    # e.g., "Fields.352"
    crm_field_path = Column(String)  # Dot-notation path: "loan.borrower.income"
    los_field_path = Column(String)  # LOS-specific path

    # Data handling
    data_type = Column(String, default="string")  # string, number, date, boolean, enum
    transform_function = Column(String)  # Python function name for value transformation
    default_value = Column(String)  # Default if source is null

    # Sync config
    sync_direction = Column(String, default="bidirectional")  # push, pull, bidirectional
    conflict_strategy = Column(String, default="most_recent")
    is_required = Column(Boolean, default=False)  # Required for sync to succeed
    is_read_only = Column(Boolean, default=False)  # Can only pull, never push

    # Validation
    validation_regex = Column(String)  # Optional validation pattern
    min_value = Column(String)
    max_value = Column(String)

    # Metadata
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# LOS SYNC LOG
# ============================================================================

class LosSyncLog(Base):
    """Per-loan sync state and history.

    Provides detailed audit trail of every sync operation per loan,
    including which fields changed, conflicts detected, and resolution.
    """
    __tablename__ = "los_sync_logs"
    __table_args__ = (
        Index('ix_los_sync_loan_id', 'loan_id'),
        Index('ix_los_sync_org_id', 'organization_id'),
        Index('ix_los_sync_status', 'sync_status'),
        Index('ix_los_sync_timestamp', 'sync_timestamp'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    los_system = Column(String, nullable=False)  # encompass, salesforce
    sync_direction = Column(String, nullable=False)  # push, pull, bidirectional
    sync_trigger = Column(String)  # webhook, scheduled, manual, status_change

    # Results
    sync_status = Column(String, nullable=False)  # success, partial, failed, conflict
    fields_synced = Column(JSON)  # ["loan_amount", "rate", "status"]
    fields_failed = Column(JSON)  # [{"field": "income", "reason": "validation_failed"}]
    fields_conflicted = Column(JSON)  # [{"field": "status", "crm_value": "X", "los_value": "Y"}]

    # Change tracking (Module 12.1: old -> new values)
    changes = Column(JSON)  # [{"field": "rate", "old": "6.5", "new": "6.25", "source": "los"}]

    # Conflict resolution
    conflicts_auto_resolved = Column(Integer, default=0)
    conflicts_manual_pending = Column(Integer, default=0)
    resolution_notes = Column(Text)

    # Error handling (Module 12.1: retry logic)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    error_payload = Column(JSON)  # Full request/response for debugging

    # Performance
    sync_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    duration_ms = Column(Integer)

    # Audit
    triggered_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "SyncDirection",
    "ConflictStrategy",
    "SyncStatus",
    "LosFieldMapping",
    "LosSyncLog",
]
