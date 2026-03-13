"""
Document Archive Models

Archive management for post-closing loan documents. Handles long-term
retention with tiered S3 storage, legal holds, retention policy enforcement,
and regulatory compliance tracking.

Key table:
    smart_docs_archives  -- one archive per funded loan, tracks bundled
                           documents through their retention lifecycle

Usage:
    from database.models.document_archive import (
        DocumentArchive,
        ArchiveType,
        ArchiveStatus,
        RetentionPolicy,
        StorageClass,
    )

    archives = db.query(DocumentArchive).filter(
        DocumentArchive.organization_id == org_id,
        DocumentArchive.archive_status == ArchiveStatus.ACTIVE,
    ).all()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    ForeignKey,
    Index,
    JSON,
)

from db import Base


# =============================================================================
# ENUMS
# =============================================================================

class ArchiveType(str, enum.Enum):
    """Reason the archive was created."""
    POST_CLOSING = "POST_CLOSING"
    AUDIT_HOLD = "AUDIT_HOLD"
    REGULATORY = "REGULATORY"
    MANUAL = "MANUAL"


class ArchiveStatus(str, enum.Enum):
    """Lifecycle status of an archive."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    PURGED = "PURGED"
    LEGAL_HOLD = "LEGAL_HOLD"


class RetentionPolicy(str, enum.Enum):
    """Retention period for the archive."""
    THREE_YEAR = "3_YEAR"
    SEVEN_YEAR = "7_YEAR"
    TEN_YEAR = "10_YEAR"
    PERMANENT = "PERMANENT"


class StorageClass(str, enum.Enum):
    """S3 storage class the archive currently resides in."""
    STANDARD = "STANDARD"
    STANDARD_IA = "STANDARD_IA"
    GLACIER = "GLACIER"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"


# =============================================================================
# MODEL
# =============================================================================

class DocumentArchive(Base):
    """Post-closing document archive with tiered storage and legal-hold support.

    Each archive bundles all documents for a single funded loan. The storage
    class is tiered based on age:
      - 0-90 days:    S3 Standard
      - 90d - 1 year: S3 Standard-IA
      - 1-3 years:    S3 Glacier
      - 3+ years:     S3 Glacier Deep Archive

    Legal holds prevent purging regardless of retention expiry. Purge
    operations require explicit approval and record the purge timestamp.
    """

    __tablename__ = "smart_docs_archives"

    __table_args__ = (
        Index("ix_archives_org_status", "organization_id", "archive_status"),
        Index("ix_archives_retention", "retention_expires_at"),
        Index("ix_archives_org_loan", "organization_id", "loan_id"),
        Index("ix_archives_legal_hold", "legal_hold"),
        Index("ix_archives_storage_class", "storage_class"),
        Index("ix_archives_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    loan_id = Column(
        Integer,
        ForeignKey("loans.id"),
        nullable=False,
        index=True,
    )

    # Archive classification
    archive_type = Column(String(30), nullable=False)  # ArchiveType value
    archive_status = Column(String(20), nullable=False, default="ACTIVE")  # ArchiveStatus value
    archive_label = Column(String(255), nullable=True)  # Human-readable label

    # Content metrics
    document_count = Column(Integer, nullable=False, default=0)
    total_size_bytes = Column(BigInteger, nullable=False, default=0)
    document_manifest = Column(JSON, nullable=True)  # List of {doc_id, doc_type, filename, sha256}

    # Storage
    storage_location = Column(String, nullable=True)  # S3 archive path
    storage_class = Column(String(30), nullable=False, default="STANDARD")  # StorageClass value

    # Retention
    retention_policy = Column(String(30), nullable=False)  # RetentionPolicy value
    retention_expires_at = Column(DateTime, nullable=True)

    # Legal hold
    legal_hold = Column(Boolean, nullable=False, default=False)
    legal_hold_reason = Column(Text, nullable=True)
    legal_hold_placed_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )
    legal_hold_placed_at = Column(DateTime, nullable=True)
    legal_hold_released_at = Column(DateTime, nullable=True)

    # Integrity
    archive_checksum = Column(String(64), nullable=True)  # SHA-256 of the archive bundle
    last_integrity_check_at = Column(DateTime, nullable=True)
    integrity_verified = Column(Boolean, nullable=True)

    # Retrieval tracking
    last_retrieval_at = Column(DateTime, nullable=True)
    retrieval_count = Column(Integer, nullable=False, default=0)
    restore_in_progress = Column(Boolean, nullable=False, default=False)
    restore_eta = Column(DateTime, nullable=True)

    # Audit
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    purged_at = Column(DateTime, nullable=True)
    purged_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    # Cost tracking
    monthly_storage_cost_cents = Column(Integer, nullable=True)  # In cents for precision


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "DocumentArchive",
    "ArchiveType",
    "ArchiveStatus",
    "RetentionPolicy",
    "StorageClass",
]
