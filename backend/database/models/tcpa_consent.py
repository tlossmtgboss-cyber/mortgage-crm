"""
TCPA Consent Certificate Storage - FCC 1:1 Consent Rules (April 2026)

Stores per-contact consent certificates required under the FCC's one-to-one
consent rule effective April 11, 2026.  Each row represents a single consent
grant for a single phone number.  Revocations are recorded in-place (the row
is not deleted) so the full audit trail is always preserved.

Key compliance requirements modelled here:
  - Consent must be captured before ANY autodialed/prerecorded call or text.
  - FCC 1:1 rule: consent must name this company specifically (no lead-
    generator blanket consent).
  - Revocation must be honoured within 10 business days (FCC standard).
  - Evidence of consent (IP, user-agent, recording URL, document URL) must be
    retained for the duration of business operations plus any applicable statute
    of limitations.

Usage:
    from database.models.tcpa_consent import TCPAConsent

    record = db.query(TCPAConsent).filter(
        TCPAConsent.phone_number == phone,
        TCPAConsent.organization_id == org_id,
        TCPAConsent.is_active == True,
        TCPAConsent.consent_channel.in_(["call", "both"]),
    ).order_by(TCPAConsent.granted_at.desc()).first()
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from db import Base


class TCPAConsent(Base):
    __tablename__ = "tcpa_consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    # Lead ID, borrower profile ID, or referral partner ID — kept as UUID
    # without a hard FK so consent records survive contact record deletion.
    contact_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contact_type = Column(
        String(20),
        nullable=False,
    )  # "lead", "borrower", "referral_partner"
    phone_number = Column(String(20), nullable=False, index=True)

    # ------------------------------------------------------------------
    # Consent details
    # ------------------------------------------------------------------
    consent_type = Column(
        String(30),
        nullable=False,
    )  # "express_written", "express_oral", "implied"
    consent_channel = Column(
        String(20),
        nullable=False,
    )  # "call", "sms", "both"
    consent_source = Column(
        String(100),
    )  # "web_form", "paper_form", "verbal_recording", "app_signup"
    # Exact disclosure language presented to the contact at time of consent.
    # Storing the verbatim text satisfies FCC requirements to prove the
    # consumer consented to contact from THIS company specifically.
    consent_text = Column(Text)
    consent_ip_address = Column(String(45))   # IPv4 or IPv6
    consent_user_agent = Column(Text)          # Browser / app UA string

    # ------------------------------------------------------------------
    # Status & lifecycle
    # ------------------------------------------------------------------
    is_active = Column(Boolean, default=True, nullable=False)
    granted_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime)              # NULL = no expiration
    revoked_at = Column(DateTime)
    # How the revocation was received: "text_reply", "phone_request",
    # "email", "portal", "manual"
    revocation_method = Column(String(50))
    # Timestamp when revocation was processed into this system.
    # FCC requires opt-outs to be honoured within 10 business days.
    revocation_processed_at = Column(DateTime)

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ------------------------------------------------------------------
    # Evidence storage
    # ------------------------------------------------------------------
    # URL to a call recording capturing the verbal consent grant.
    recording_url = Column(String(500))
    # URL to a signed consent form (PDF, e-sign document, etc.).
    document_url = Column(String(500))

    # ------------------------------------------------------------------
    # Composite indexes for common query patterns
    # ------------------------------------------------------------------
    __table_args__ = (
        # Lookup active consent by org + phone (pre-call check)
        Index("ix_tcpa_consent_org_phone", "organization_id", "phone_number"),
        # Lookup active consent across all orgs for a given phone
        Index("ix_tcpa_consent_active", "phone_number", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<TCPAConsent id={self.id} phone={self.phone_number} "
            f"type={self.consent_type} active={self.is_active}>"
        )
