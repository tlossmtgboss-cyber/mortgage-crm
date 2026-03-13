"""
Document Version Control Model

Tracks version history for Smart Docs V2 documents. Each document replacement,
correction, or addendum creates a new version with:
  - Frozen extracted data snapshot (historical accuracy)
  - Full audit trail (who, when, why)
  - SHA-256 file hash for integrity verification
  - Linked list via previous_version_id for traversal

Table: smart_docs_document_versions

Usage:
    from database.models.document_version import DocumentVersion, ChangeType

    # Get current version
    current = db.query(DocumentVersion).filter(
        DocumentVersion.document_id == doc_id,
        DocumentVersion.is_current == True,
        DocumentVersion.organization_id == org_id,
    ).first()

    # Get full history
    history = db.query(DocumentVersion).filter(
        DocumentVersion.document_id == doc_id,
        DocumentVersion.organization_id == org_id,
    ).order_by(DocumentVersion.version_number.asc()).all()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from db import Base


# =============================================================================
# ENUMS
# =============================================================================

class ChangeType(str, enum.Enum):
    """Type of change that created this version."""
    INITIAL = "INITIAL"             # First upload
    REPLACEMENT = "REPLACEMENT"     # Full document replacement
    CORRECTION = "CORRECTION"       # Minor fix (e.g., wrong page, re-scan)
    ADDENDUM = "ADDENDUM"           # Supplementary material added
    REPROCESSED = "REPROCESSED"     # Same file re-extracted (AI model change)


# =============================================================================
# MODEL
# =============================================================================

class DocumentVersion(Base):
    """
    Version history record for a Smart Document.

    Each row represents a single version of a document. Only one version
    per document has ``is_current = True`` at any time. Version numbers
    are monotonically increasing per document (enforced by unique constraint).

    The ``extracted_data_snapshot`` column stores a frozen copy of the AI
    extraction results at the time this version was created, so historical
    queries always see the data as it was -- even after the document is
    replaced and re-extracted.
    """
    __tablename__ = "smart_docs_document_versions"

    id = Column(Integer, primary_key=True, index=True)

    # Tenant isolation
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    # Document this version belongs to
    document_id = Column(
        Integer,
        ForeignKey("smart_documents.id"),
        nullable=False,
        index=True,
    )

    # Monotonically increasing version number per document
    version_number = Column(Integer, nullable=False)

    # File integrity
    file_hash = Column(String(64), nullable=False)  # SHA-256 hex digest
    file_location = Column(String, nullable=False)   # S3 key or storage path
    file_size = Column(Integer)                       # Bytes

    # Change metadata
    change_type = Column(String(50), nullable=False, default=ChangeType.INITIAL.value)
    change_reason = Column(Text, nullable=True)

    # Who made this change
    changed_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,  # System-initiated changes may not have a user
    )

    # Linked list for version traversal
    previous_version_id = Column(
        Integer,
        ForeignKey("smart_docs_document_versions.id"),
        nullable=True,  # NULL for version 1
    )

    # Frozen extraction data at this version
    extracted_data_snapshot = Column(JSON, nullable=True)

    # Only one version per document is current
    is_current = Column(Boolean, default=True, nullable=False)

    # File metadata captured at version time
    original_filename = Column(String(512), nullable=True)
    mime_type = Column(String(128), nullable=True)

    # Archival support
    is_archived = Column(Boolean, default=False, nullable=False)
    archived_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        # A document can only have one row per version number
        UniqueConstraint(
            "document_id", "version_number",
            name="uq_doc_version_number",
        ),
        # Fast lookup: "get current version of document X"
        Index(
            "ix_doc_versions_doc_current",
            "document_id", "is_current",
        ),
        # Fast lookup: versions by org (tenant queries)
        Index(
            "ix_doc_versions_org_doc",
            "organization_id", "document_id",
        ),
        # Archive cleanup queries
        Index(
            "ix_doc_versions_archived",
            "is_archived", "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentVersion id={self.id} doc={self.document_id} "
            f"v{self.version_number} current={self.is_current}>"
        )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "DocumentVersion",
    "ChangeType",
]
