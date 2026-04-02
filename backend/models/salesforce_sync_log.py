"""
Salesforce Sync Log Model

Tracks all Salesforce sync operations for auditing and troubleshooting.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base


class SalesforceSyncLog(Base):
    """Model for tracking Salesforce sync operations."""

    __tablename__ = "salesforce_sync_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Sync details
    sync_type = Column(String(20), nullable=False)  # email, calendar, loan, lead, contact
    sync_direction = Column(String(20), default="inbound")  # inbound, outbound, bidirectional

    # Salesforce reference
    salesforce_id = Column(String(18), nullable=True, index=True)

    # CRM references
    loan_id = Column(Integer, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True, index=True)
    integration_profile_id = Column(Integer, ForeignKey("integration_profiles.id", ondelete="CASCADE"), nullable=True)

    # Status tracking
    status = Column(String(20), nullable=False)  # success, error, partial, in_progress

    # Record counts
    records_processed = Column(Integer, default=0)
    records_success = Column(Integer, default=0)  # Alias for records_created + records_updated
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Additional data
    payload_summary = Column(JSON, nullable=True)

    # Timing
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # User context
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(Integer, nullable=True)

    # Relationships
    loan = relationship("Loan", foreign_keys=[loan_id], lazy="select")
    user = relationship("User", foreign_keys=[user_id], lazy="select")

    def __repr__(self):
        return f"<SalesforceSyncLog {self.id}: {self.sync_type} - {self.status}>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "sync_type": self.sync_type,
            "sync_direction": self.sync_direction,
            "salesforce_id": self.salesforce_id,
            "loan_id": self.loan_id,
            "status": self.status,
            "records_processed": self.records_processed,
            "records_success": self.records_success,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
        }

    def mark_completed(self, status: str = "success", error_message: Optional[str] = None):
        """Mark the sync as completed."""
        self.status = status
        self.completed_at = datetime.now(timezone.utc)
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        if error_message:
            self.error_message = error_message
        # Calculate records_success
        self.records_success = (self.records_created or 0) + (self.records_updated or 0)


class SalesforceFieldMapping(Base):
    """Model for customizable field mappings between CRM and Salesforce."""

    __tablename__ = "salesforce_field_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)

    # Salesforce side
    salesforce_object = Column(String(100), nullable=False)
    salesforce_field = Column(String(100), nullable=False)

    # CRM side
    crm_entity = Column(String(50), nullable=False)
    crm_field = Column(String(100), nullable=False)

    # Transformation rules
    transform_type = Column(String(50), nullable=True)  # decimal, date, stage_mapping, etc.
    sync_direction = Column(String(20), default="bidirectional")  # inbound, outbound, bidirectional

    # Status
    is_active = Column(Integer, default=1)  # Using Integer for SQLite compatibility

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<SalesforceFieldMapping {self.crm_entity}.{self.crm_field} -> {self.salesforce_object}.{self.salesforce_field}>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "salesforce_object": self.salesforce_object,
            "salesforce_field": self.salesforce_field,
            "crm_entity": self.crm_entity,
            "crm_field": self.crm_field,
            "transform_type": self.transform_type,
            "sync_direction": self.sync_direction,
            "is_active": bool(self.is_active),
        }
