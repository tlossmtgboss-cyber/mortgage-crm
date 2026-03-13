"""
eClosing Session Model

Tracks closing sessions with external eClosing providers (Snapdocs, Pavaso,
NotaryCam) or the internal closing workflow.  Each session ties an organization
and loan to a provider-side session, tracking document status, notary scheduling,
eNote MERS registration, and overall closing lifecycle.

This model bridges the gap between the platform's built-in e-signature system
(which handles standard disclosures and authorizations) and specialized eClosing
platforms that handle the regulated closing ceremony -- wet-ink requirements,
RON/IPEN notarization, MISMO-compliant eNotes, and eVault storage.

Usage:
    from database.models.eclosing import EClosingSession, EClosingSessionStatus

    session = db.query(EClosingSession).filter(
        EClosingSession.organization_id == org_id,
        EClosingSession.loan_id == loan_id,
    ).first()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from db import Base


# ============================================================================
# ENUMS
# ============================================================================

class EClosingSessionStatus(str, enum.Enum):
    """Lifecycle status of an eClosing session."""
    CREATED = "created"
    DOCUMENTS_UPLOADED = "documents_uploaded"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ClosingType(str, enum.Enum):
    """Type of closing ceremony."""
    FULL_ECLOSING = "full_eclosing"   # All documents signed electronically
    HYBRID = "hybrid"                  # Mix of electronic and wet-ink
    INK = "ink"                        # Traditional with eNotarization


class NotaryType(str, enum.Enum):
    """Type of notarization."""
    RON = "ron"           # Remote Online Notarization
    IPEN = "ipen"         # In-Person Electronic Notarization
    TRADITIONAL = "traditional"


class EClosingProvider(str, enum.Enum):
    """Supported eClosing providers."""
    SNAPDOCS = "snapdocs"
    PAVASO = "pavaso"
    NOTARYCAM = "notarycam"
    INTERNAL = "internal"


# ============================================================================
# ECLOSING SESSION MODEL
# ============================================================================

class EClosingSession(Base):
    """eClosing session linking a loan to an external closing provider.

    Lifecycle:
        CREATED -> DOCUMENTS_UPLOADED -> READY -> IN_PROGRESS -> COMPLETED
                                                              |
                                                              +-> CANCELLED

    The documents_package JSON column stores the closing package manifest:
        [{
            "doc_type": "promissory_note",
            "filename": "note.pdf",
            "requires_notarization": true,
            "requires_wet_ink": false,
            "signing_order": 1,
            "status": "pending",
            "signed_at": null
        }, ...]

    The enote_status JSON column tracks eNote lifecycle:
        {
            "mers_registered": false,
            "evault_stored": false,
            "evault_id": null,
            "tamper_seal_valid": true
        }
    """
    __tablename__ = "eclosing_sessions"
    __table_args__ = (
        Index("ix_eclosing_sessions_org_loan", "organization_id", "loan_id"),
        Index("ix_eclosing_sessions_session_id", "session_id"),
        Index("ix_eclosing_sessions_status", "status"),
        Index("ix_eclosing_sessions_provider", "provider"),
        Index("ix_eclosing_sessions_closing_date", "closing_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, comment="references organizations.id")
    loan_id = Column(Integer, nullable=False, comment="references loans.id")

    # Provider details
    provider = Column(String(20), nullable=False, default=EClosingProvider.INTERNAL.value)
    session_id = Column(String(100), nullable=True, index=True, comment="Provider's external session ID")

    # Closing configuration
    closing_type = Column(String(20), nullable=False, default=ClosingType.HYBRID.value)
    closing_date = Column(Date, nullable=True)

    # Status
    status = Column(String(20), nullable=False, default=EClosingSessionStatus.CREATED.value)

    # Signing URL from provider
    signing_url = Column(Text, nullable=True)

    # Notary scheduling
    notary_type = Column(String(20), nullable=True)
    notary_scheduled_at = Column(DateTime, nullable=True)
    notary_name = Column(String(255), nullable=True)
    notary_commission_id = Column(String(100), nullable=True)

    # Closing package manifest (JSON array of document statuses)
    documents_package = Column(JSON, nullable=True, comment="Array of closing documents and their status")

    # eNote tracking
    enote_mers_min = Column(String(18), nullable=True, comment="MERS Mortgage Identification Number for eNote")
    enote_status = Column(JSON, nullable=True, comment="eNote lifecycle status: MERS registration, eVault storage")

    # Completion
    completed_at = Column(DateTime, nullable=True)
    completion_notes = Column(Text, nullable=True)

    # Post-closing
    recording_number = Column(String(100), nullable=True, comment="County recording number")
    recording_date = Column(Date, nullable=True)
    signed_documents_key = Column(String(1024), nullable=True, comment="S3 key for signed closing package")

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "EClosingSessionStatus",
    "ClosingType",
    "NotaryType",
    "EClosingProvider",
    # Models
    "EClosingSession",
]
