"""
Document Visibility Models

SQLAlchemy models for controlling document visibility to borrowers and partners,
with milestone-based auto-release and comprehensive audit logging.

Tables:
- DocumentVisibility: Per-document visibility settings
- DocumentVisibilityAudit: Audit trail for all visibility changes
"""

from datetime import datetime, timezone
from typing import Optional
import enum

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Index, UniqueConstraint
)
from sqlalchemy.orm import relationship

from database import Base


class ReleaseMode(str, enum.Enum):
    """How the document becomes visible"""
    MANUAL = "manual"           # Manually released by staff
    MILESTONE = "milestone"     # Auto-released on loan milestone
    DATETIME = "datetime"       # Auto-released at specific date/time


class ChangeSource(str, enum.Enum):
    """Source of visibility change"""
    MANUAL = "manual"           # Staff manually changed
    AUTO_RELEASE = "auto_release"  # Triggered by milestone
    SYSTEM = "system"           # System/default behavior
    UPLOAD = "upload"           # Set during document upload


class DocumentVisibility(Base):
    """
    Per-document visibility control.

    Supports multiple document tables (perennia_documents, portal_documents, etc.)
    via polymorphic document_table + document_id reference.
    """
    __tablename__ = "document_visibility"

    id = Column(Integer, primary_key=True, index=True)

    # Polymorphic document reference
    document_table = Column(String(50), nullable=False)
    document_id = Column(Integer, nullable=False)
    loan_id = Column(Integer, nullable=False)

    # Visibility flags
    visible_to_borrower = Column(Boolean, nullable=False, default=True)
    visible_to_partner = Column(Boolean, nullable=False, default=True)
    visible_to_internal = Column(Boolean, nullable=False, default=True)

    # Release configuration
    release_mode = Column(String(20), default=ReleaseMode.MANUAL.value)
    release_milestone = Column(String(50), nullable=True)  # e.g., 'funded', 'clear_to_close'
    release_at = Column(DateTime(timezone=True), nullable=True)

    # Lock and reason
    visibility_locked = Column(Boolean, default=False)
    hidden_reason = Column(Text, nullable=True)

    # Change tracking
    last_changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    # Note: User relationship removed to avoid circular import issues
    # Use last_changed_by ID to look up user separately if needed
    audit_entries = relationship("DocumentVisibilityAudit", back_populates="visibility", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('document_table', 'document_id', name='uq_doc_visibility_document'),
        Index('idx_doc_visibility_loan', 'loan_id'),
        Index('idx_doc_visibility_borrower_hidden', 'visible_to_borrower', postgresql_where=Column('visible_to_borrower') == False),
        Index('idx_doc_visibility_release', 'release_mode', 'release_milestone', postgresql_where=Column('release_mode') == 'milestone'),
    )

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "document_table": self.document_table,
            "document_id": self.document_id,
            "loan_id": self.loan_id,
            "visible_to_borrower": self.visible_to_borrower,
            "visible_to_partner": self.visible_to_partner,
            "visible_to_internal": self.visible_to_internal,
            "release_mode": self.release_mode,
            "release_milestone": self.release_milestone,
            "release_at": self.release_at.isoformat() if self.release_at else None,
            "visibility_locked": self.visibility_locked,
            "hidden_reason": self.hidden_reason,
            "last_changed_by": self.last_changed_by,
            "last_changed_at": self.last_changed_at.isoformat() if self.last_changed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DocumentVisibilityAudit(Base):
    """
    Audit trail for document visibility changes.
    Records every change to visibility settings with before/after state.
    """
    __tablename__ = "document_visibility_audit"

    id = Column(Integer, primary_key=True, index=True)

    # Reference to visibility record
    document_visibility_id = Column(Integer, ForeignKey("document_visibility.id", ondelete="CASCADE"), nullable=False)
    loan_id = Column(Integer, nullable=False)

    # Change details
    field_changed = Column(String(50), nullable=False)  # e.g., 'visible_to_borrower'
    old_value = Column(Boolean, nullable=True)
    new_value = Column(Boolean, nullable=True)

    # Actor info
    change_source = Column(String(50), nullable=False)  # manual, auto_release, system
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    change_reason = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    visibility = relationship("DocumentVisibility", back_populates="audit_entries")
    # Note: User relationship removed to avoid circular import issues

    __table_args__ = (
        Index('idx_doc_visibility_audit_doc', 'document_visibility_id', 'created_at'),
        Index('idx_doc_visibility_audit_loan', 'loan_id', 'created_at'),
    )

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "document_visibility_id": self.document_visibility_id,
            "loan_id": self.loan_id,
            "field_changed": self.field_changed,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "change_source": self.change_source,
            "changed_by": self.changed_by,
            "change_reason": self.change_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
