"""
Document Security & Audit Models

Comprehensive security layer for document management: access logging,
encryption tracking, integrity verification, retention policies, and
watermark auditing. Designed for mortgage compliance (TRID document
retention, SOC 2 audit trails, tamper detection).

Models:
    - DocumentAccessLog: Every document access attempt (granted or denied)
    - DocumentEncryptionRecord: Per-document encryption status and key metadata
    - DocumentIntegrityCheck: Tamper detection hash verification records
    - DocumentRetentionPolicy: Configurable retention rules per doc type
    - DocumentWatermarkLog: Watermark application audit trail

Usage:
    from database.models.document_security import (
        DocumentAccessLog,
        DocumentEncryptionRecord,
        DocumentIntegrityCheck,
        DocumentRetentionPolicy,
        DocumentWatermarkLog,
    )

    # Query access logs for a document
    logs = db.query(DocumentAccessLog).filter(
        DocumentAccessLog.document_id == doc_id,
        DocumentAccessLog.access_type == AccessType.DOWNLOAD,
    ).order_by(DocumentAccessLog.created_at.desc()).all()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    JSON,
    Enum as SQLEnum,
    Index,
)

from db import Base


# =============================================================================
# ENUMS
# =============================================================================

class AccessType(str, enum.Enum):
    """Type of document access performed or attempted."""
    VIEW = "view"
    DOWNLOAD = "download"
    PRINT = "print"
    PREVIEW = "preview"
    SHARE = "share"
    EDIT = "edit"
    DELETE = "delete"
    SIGN = "sign"
    VERIFY = "verify"
    EXPORT = "export"
    EMAIL_FORWARD = "email_forward"


class EncryptionStatus(str, enum.Enum):
    """Current encryption state of a document."""
    PENDING = "pending"
    ENCRYPTED = "encrypted"
    DECRYPTION_REQUESTED = "decryption_requested"
    FAILED = "failed"


class IntegrityCheckType(str, enum.Enum):
    """What triggered the integrity check."""
    SCHEDULED = "scheduled"
    ON_ACCESS = "on_access"
    ON_DOWNLOAD = "on_download"
    MANUAL = "manual"
    POST_SIGN = "post_sign"


class RetentionAction(str, enum.Enum):
    """Action to take when retention period expires."""
    DELETE = "delete"
    ARCHIVE = "archive"
    ANONYMIZE = "anonymize"
    NOTIFY_ADMIN = "notify_admin"


class WatermarkType(str, enum.Enum):
    """Context in which watermark was applied."""
    VIEWING = "viewing"
    DOWNLOAD = "download"
    PRINT = "print"
    COPY = "copy"


# =============================================================================
# DOCUMENT ACCESS LOG
# =============================================================================

class DocumentAccessLog(Base):
    """Comprehensive audit trail for every document access attempt.

    Records both granted and denied access. Immutable append-only table
    for SOC 2 and regulatory audit compliance. Each row captures the
    full context of the access: who, what, when, where, how long, and
    which pages were viewed.

    Denial records (access_granted=False) are critical for security
    incident investigation and demonstrating access controls are enforced.
    """
    __tablename__ = "document_access_logs"
    __table_args__ = (
        Index("ix_document_access_logs_document_id", "document_id"),
        Index("ix_document_access_logs_document_type", "document_type"),
        Index("ix_document_access_logs_user_id", "user_id"),
        Index("ix_document_access_logs_access_type", "access_type"),
        Index("ix_document_access_logs_organization_id", "organization_id"),
        Index("ix_document_access_logs_created_at", "created_at"),
        Index("ix_document_access_logs_access_granted", "access_granted"),
        Index("ix_document_access_logs_session_id", "session_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)  # ref organizations.id

    # Document reference (no FK — document may live in smart_documents, esignature, etc.)
    document_id = Column(Integer, nullable=False)  # ref smart_documents.id or other doc table
    document_type = Column(String(64), nullable=False)  # smart_document, esignature_envelope, etc.

    # Who accessed
    user_id = Column(Integer, nullable=True)  # ref users.id — null for system/anonymous access

    # Access details
    access_type = Column(
        SQLEnum(AccessType, name="doc_access_type_enum"),
        nullable=False,
    )
    access_granted = Column(Boolean, nullable=False, default=True)
    denial_reason = Column(Text, nullable=True)  # Populated when access_granted=False

    # Request context
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(512), nullable=True)
    geo_location = Column(String(255), nullable=True)  # e.g. "Charleston, SC, US"
    session_id = Column(String(128), nullable=True)
    referrer_url = Column(String(1024), nullable=True)

    # Engagement metrics
    duration_seconds = Column(Integer, nullable=True)  # How long document was viewed
    pages_viewed = Column(JSON, nullable=True)  # e.g. [1, 2, 5] — which pages were viewed

    # Extensible metadata
    extra_metadata = Column("metadata", JSON, nullable=True)

    # Timestamp (immutable — no updated_at)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


# =============================================================================
# DOCUMENT ENCRYPTION RECORD
# =============================================================================

class DocumentEncryptionRecord(Base):
    """Tracks encryption status and key management metadata per document.

    Stores references to encryption keys (never the keys themselves),
    initialization vectors, and content hashes for verifying encryption
    integrity. Supports key rotation via key_version tracking.

    The content_hash_before and content_hash_after fields enable
    round-trip verification: decrypt, hash plaintext, compare to
    content_hash_before to confirm no corruption.
    """
    __tablename__ = "document_encryption_records"
    __table_args__ = (
        Index("ix_document_encryption_records_document_id", "document_id"),
        Index("ix_document_encryption_records_document_type", "document_type"),
        Index("ix_document_encryption_records_organization_id", "organization_id"),
        Index("ix_document_encryption_records_key_id", "key_id"),
        Index("ix_document_encryption_records_encryption_status", "encryption_status"),
        Index("ix_document_encryption_records_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)  # ref organizations.id

    # Document reference
    document_id = Column(Integer, nullable=False)  # ref smart_documents.id or other doc table
    document_type = Column(String(64), nullable=False)

    # Encryption parameters
    encryption_algorithm = Column(String(64), nullable=False, default="AES-256-GCM")
    key_id = Column(String(128), nullable=False)  # Reference to encryption key (NOT the key itself)
    key_version = Column(Integer, nullable=False, default=1)
    encrypted_at = Column(DateTime, nullable=True)
    encryption_status = Column(
        SQLEnum(EncryptionStatus, name="doc_encryption_status_enum"),
        nullable=False,
        default=EncryptionStatus.PENDING,
    )

    # Cryptographic metadata
    iv_nonce = Column(String(64), nullable=True)  # Initialization vector (hex-encoded)
    content_hash_before = Column(String(64), nullable=True)  # SHA-256 of plaintext
    content_hash_after = Column(String(64), nullable=True)  # SHA-256 of ciphertext

    # Size tracking
    file_size_before = Column(Integer, nullable=True)  # Bytes before encryption
    file_size_after = Column(Integer, nullable=True)  # Bytes after encryption

    # Access tracking
    last_accessed_at = Column(DateTime, nullable=True)
    access_count = Column(Integer, nullable=False, default=0)

    # Timestamp
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# =============================================================================
# DOCUMENT INTEGRITY CHECK
# =============================================================================

class DocumentIntegrityCheck(Base):
    """Tamper detection verification records.

    Each row represents a single integrity check: comparing the expected
    hash (recorded at upload/encryption time) against the actual hash
    computed from the current file on storage. Mismatches set
    tamper_detected=True and populate tamper_details for investigation.

    Checks can be triggered on schedule (CRON), on access, on download,
    manually by an admin, or automatically after e-signature completion.
    """
    __tablename__ = "document_integrity_checks"
    __table_args__ = (
        Index("ix_document_integrity_checks_document_id", "document_id"),
        Index("ix_document_integrity_checks_document_type", "document_type"),
        Index("ix_document_integrity_checks_check_type", "check_type"),
        Index("ix_document_integrity_checks_is_valid", "is_valid"),
        Index("ix_document_integrity_checks_tamper_detected", "tamper_detected"),
        Index("ix_document_integrity_checks_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Document reference
    document_id = Column(Integer, nullable=False)  # ref smart_documents.id or other doc table
    document_type = Column(String(64), nullable=False)

    # Check context
    check_type = Column(
        SQLEnum(IntegrityCheckType, name="doc_integrity_check_type_enum"),
        nullable=False,
    )

    # Hash comparison
    expected_hash = Column(String(64), nullable=False)  # SHA-256 recorded at creation/encryption
    actual_hash = Column(String(64), nullable=False)  # SHA-256 computed during this check
    is_valid = Column(Boolean, nullable=False)  # expected_hash == actual_hash

    # Tamper detection
    tamper_detected = Column(Boolean, nullable=False, default=False)
    tamper_details = Column(Text, nullable=True)  # Description of detected tampering

    # Who/what performed the check
    checked_by = Column(String(100), nullable=False)  # "SYSTEM", "CRON", or user_id as string

    # Performance
    check_duration_ms = Column(Integer, nullable=True)  # How long the check took

    # Storage context
    storage_key_checked = Column(String(1024), nullable=True)  # S3 key or file path checked

    # File size verification
    file_size_expected = Column(Integer, nullable=True)
    file_size_actual = Column(Integer, nullable=True)

    # Extensible metadata
    extra_metadata = Column("metadata", JSON, nullable=True)

    # Timestamp
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


# =============================================================================
# DOCUMENT RETENTION POLICY
# =============================================================================

class DocumentRetentionPolicy(Base):
    """Configurable retention rules per document type per organization.

    Defines how long documents must be retained after a triggering event
    (e.g., loan funded, denied, cancelled) and what action to take when
    the retention period expires. Supports state-specific regulatory
    requirements (e.g., TRID 36-month retention rule).

    Multiple policies can exist for the same doc_type if different
    organizations or states have different requirements; the most
    restrictive policy should be applied.
    """
    __tablename__ = "document_retention_policies"
    __table_args__ = (
        Index("ix_document_retention_policies_organization_id", "organization_id"),
        Index("ix_document_retention_policies_doc_type", "doc_type"),
        Index("ix_document_retention_policies_is_active", "is_active"),
        Index("ix_document_retention_policies_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)  # ref organizations.id

    # What this policy applies to
    doc_type = Column(String(64), nullable=False)  # DocType value this policy governs
    policy_name = Column(String(255), nullable=False)

    # Retention rules
    retention_days = Column(Integer, nullable=False)  # Days to keep after triggering event
    retention_after_event = Column(String(64), nullable=False)  # FUNDED, DENIED, CANCELLED, etc.
    action_on_expiry = Column(
        SQLEnum(RetentionAction, name="doc_retention_action_enum"),
        nullable=False,
        default=RetentionAction.NOTIFY_ADMIN,
    )
    notify_days_before = Column(Integer, nullable=False, default=30)  # Days before expiry to notify

    # Policy status
    is_active = Column(Boolean, nullable=False, default=True)

    # Regulatory context
    regulatory_reference = Column(Text, nullable=True)  # e.g. "TRID 36-month retention requirement"

    # State-specific overrides
    applies_to_states = Column(JSON, nullable=True)  # e.g. ["CA", "TX"] or null for all states

    # Timestamps
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


# =============================================================================
# DOCUMENT WATERMARK LOG
# =============================================================================

class DocumentWatermarkLog(Base):
    """Audit trail for watermarks applied to documents.

    Records every watermark application with the exact text used,
    the user it was applied for, and a reference to the watermarked
    output file. Supports forensic tracing of leaked documents back
    to the specific user and timestamp.
    """
    __tablename__ = "document_watermark_logs"
    __table_args__ = (
        Index("ix_document_watermark_logs_document_id", "document_id"),
        Index("ix_document_watermark_logs_watermark_type", "watermark_type"),
        Index("ix_document_watermark_logs_applied_to_user_id", "applied_to_user_id"),
        Index("ix_document_watermark_logs_applied_at", "applied_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Document reference
    document_id = Column(Integer, nullable=False)  # ref smart_documents.id or other doc table

    # Watermark details
    watermark_type = Column(
        SQLEnum(WatermarkType, name="doc_watermark_type_enum"),
        nullable=False,
    )
    watermark_text = Column(String(500), nullable=False)  # e.g. "COPY - John Smith - 2026-03-10 14:30:00"

    # Who received the watermarked copy
    applied_to_user_id = Column(Integer, nullable=False)  # ref users.id

    # When watermark was applied
    applied_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Output reference
    output_storage_key = Column(String(1024), nullable=True)  # S3 key or file path of watermarked copy

    # Extensible metadata
    extra_metadata = Column("metadata", JSON, nullable=True)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "AccessType",
    "EncryptionStatus",
    "IntegrityCheckType",
    "RetentionAction",
    "WatermarkType",
    # Models
    "DocumentAccessLog",
    "DocumentEncryptionRecord",
    "DocumentIntegrityCheck",
    "DocumentRetentionPolicy",
    "DocumentWatermarkLog",
]
