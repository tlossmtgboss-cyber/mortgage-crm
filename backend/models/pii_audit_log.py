"""
PII Audit Log Model

Stores audit trail for all access to Personally Identifiable Information (PII)
and other sensitive data for compliance with GLBA, GDPR, CCPA.
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from datetime import datetime, timezone
import uuid

from database import Base


class PIIAuditLog(Base):
    """
    Audit log for PII access.

    This table should be:
    - Append-only (no updates or deletes)
    - Retained for minimum 7 years (GLBA requirement)
    - Regularly backed up
    - Access-controlled (only compliance/security team)
    """
    __tablename__ = "pii_audit_logs"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Timestamp (immutable)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Who accessed
    user_id = Column(Integer, index=True)
    user_email = Column(String(255))
    ip_address = Column(String(45))  # IPv6 compatible
    session_id = Column(String(255))

    # What was accessed
    entity_type = Column(String(50), nullable=False, index=True)  # lead, loan, contact, etc.
    entity_id = Column(String(255), nullable=False, index=True)
    access_type = Column(String(20), nullable=False)  # read, write, update, delete, export, search
    fields_accessed = Column(ARRAY(String), nullable=False)  # List of PII field names

    # Context
    reason = Column(Text)  # Business justification for access
    request_id = Column(String(255))  # For tracing
    organization_id = Column(String(255), index=True)

    # Result
    success = Column(Boolean, default=True)

    # Additional metadata (Python attr 'meta_data' avoids conflict with SQLAlchemy's reserved .metadata)
    meta_data = Column('metadata', JSONB)

    # Indexes for compliance queries
    __table_args__ = (
        # Query: "Who accessed this borrower's data?"
        Index('ix_pii_audit_entity', 'entity_type', 'entity_id'),
        # Query: "What did this user access?"
        Index('ix_pii_audit_user', 'user_id', 'timestamp'),
        # Query: "Show all SSN accesses in date range"
        Index('ix_pii_audit_time', 'timestamp', 'access_type'),
        # Query: "All accesses for this organization"
        Index('ix_pii_audit_org_time', 'organization_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<PIIAuditLog {self.access_type} {self.entity_type}/{self.entity_id} by user {self.user_id}>"
