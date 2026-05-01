"""
TCPA Voice Consent Tracking Models

Tracks prior express consent and prior express written consent for AI-generated
voice calls (Vapi/Telnyx).  FCC ruled (Nov 2023, eff. Feb 2024) that AI-generated
voices are "artificial or prerecorded voice" under TCPA 47 U.S.C. 227.  The
Mortgage One class action (Feb 2026) set damages at $500-$1,500 per AI voice call
placed without proper consent.

Models:
    VoiceConsent        — Per-phone consent record with full provenance.
    VoiceConsentAudit   — Immutable append-only audit trail for every consent
                          lifecycle event (creation, verification, revocation,
                          expiration).

Consent records MUST be retained for a minimum of 5 years from the consent date
(retention_expires_at).  The VoiceConsentAudit table is APPEND-ONLY; no UPDATE
or DELETE operations should ever be performed on it.

Usage:
    from database.models.voice_consent import VoiceConsent, VoiceConsentAudit

    consent = VoiceConsent(
        organization_id=org_id,
        lead_id=lead_id,
        phone_number="+18431234567",
        consent_type="PRIOR_EXPRESS_WRITTEN",
        consent_channel="WEBFORM",
        consent_language_version="v2.1",
        consent_text="I agree to receive AI-generated voice calls...",
        ip_address="192.168.1.1",
        consented_at=datetime.now(timezone.utc),
    )
    db.add(consent)
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from db import Base


# ============================================================================
# Consent type and channel constants (stored as VARCHAR, not DB enums,
# to avoid PostgreSQL ENUM migration pain -- see Lead.stage precedent)
# ============================================================================

# consent_type values
CONSENT_TYPE_PRIOR_EXPRESS = "PRIOR_EXPRESS"
CONSENT_TYPE_PRIOR_EXPRESS_WRITTEN = "PRIOR_EXPRESS_WRITTEN"
CONSENT_TYPE_VERBAL = "VERBAL"
CONSENT_TYPE_REVOKED = "REVOKED"

VALID_CONSENT_TYPES = {
    CONSENT_TYPE_PRIOR_EXPRESS,
    CONSENT_TYPE_PRIOR_EXPRESS_WRITTEN,
    CONSENT_TYPE_VERBAL,
    CONSENT_TYPE_REVOKED,
}

# consent_channel values
CONSENT_CHANNEL_WEBFORM = "WEBFORM"
CONSENT_CHANNEL_VOICE_RECORDING = "VOICE_RECORDING"
CONSENT_CHANNEL_ESIGN = "ESIGN"
CONSENT_CHANNEL_SMS_OPT_IN = "SMS_OPT_IN"
CONSENT_CHANNEL_MANUAL = "MANUAL"

VALID_CONSENT_CHANNELS = {
    CONSENT_CHANNEL_WEBFORM,
    CONSENT_CHANNEL_VOICE_RECORDING,
    CONSENT_CHANNEL_ESIGN,
    CONSENT_CHANNEL_SMS_OPT_IN,
    CONSENT_CHANNEL_MANUAL,
}

# audit action values
AUDIT_ACTION_CREATED = "CREATED"
AUDIT_ACTION_VERIFIED = "VERIFIED"
AUDIT_ACTION_REVOKED = "REVOKED"
AUDIT_ACTION_EXPIRED = "EXPIRED"

VALID_AUDIT_ACTIONS = {
    AUDIT_ACTION_CREATED,
    AUDIT_ACTION_VERIFIED,
    AUDIT_ACTION_REVOKED,
    AUDIT_ACTION_EXPIRED,
}

# Default retention period: 5 years from consent date
DEFAULT_RETENTION_YEARS = 5


class VoiceConsent(Base):
    """
    Per-phone voice consent record for AI-generated calls.

    TCPA requires "prior express consent" for informational autodialed calls
    and "prior express written consent" for telemarketing/advertising calls.
    AI-generated voices (Vapi, ElevenLabs, Deepgram TTS) are classified as
    "artificial or prerecorded voice" per FCC ruling.

    consent_type values:
        PRIOR_EXPRESS           — Oral or implied consent for informational calls
        PRIOR_EXPRESS_WRITTEN   — Signed/e-signed consent for marketing calls
        VERBAL                  — Recorded verbal consent during a live call
        REVOKED                 — Consumer revoked previously granted consent

    consent_channel values:
        WEBFORM          — Web form submission (POS portal, landing page)
        VOICE_RECORDING  — Verbal consent captured via call recording
        ESIGN            — Electronic signature (DocuSign, e-sign flow)
        SMS_OPT_IN       — Consumer replied YES/SUBSCRIBE to opt-in SMS
        MANUAL           — LO manually recorded consent (paper form, in-person)
    """

    __tablename__ = "voice_consents"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    lead_id = Column(
        Integer,
        ForeignKey("leads.id"),
        nullable=True,
        index=True,
    )
    borrower_id = Column(
        Integer,
        ForeignKey("leads.id"),
        nullable=True,
        index=True,
    )

    # Contact info
    phone_number = Column(String(20), nullable=False, index=True)

    # Consent classification
    consent_type = Column(String(30), nullable=False)  # PRIOR_EXPRESS, PRIOR_EXPRESS_WRITTEN, VERBAL, REVOKED
    consent_channel = Column(String(20), nullable=False)  # WEBFORM, VOICE_RECORDING, ESIGN, SMS_OPT_IN, MANUAL

    # Disclosure provenance
    consent_language_version = Column(String(20), nullable=True)  # e.g. "v2.1"
    consent_text = Column(Text, nullable=True)  # Exact disclosure text consumer agreed to

    # Evidence
    recording_url = Column(String(500), nullable=True)  # URL to recording of verbal consent
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6, for web-based consent
    user_agent = Column(String(500), nullable=True)  # Browser user-agent string

    # Lifecycle
    consented_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    revocation_reason = Column(String(500), nullable=True)

    # Retention: 5 years from consent date (TCPA best practice)
    retention_expires_at = Column(DateTime, nullable=True)

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

    __table_args__ = (
        Index("ix_vc_org_phone", "organization_id", "phone_number"),
        Index("ix_vc_phone_type", "phone_number", "consent_type"),
    )

    def __repr__(self) -> str:
        revoked = f" revoked={self.revoked_at}" if self.revoked_at else ""
        return (
            f"<VoiceConsent id={self.id} phone={self.phone_number} "
            f"type={self.consent_type} channel={self.consent_channel}{revoked}>"
        )

    @property
    def is_active(self) -> bool:
        """True if consent has not been revoked and has not expired."""
        if self.consent_type == CONSENT_TYPE_REVOKED:
            return False
        if self.revoked_at is not None:
            return False
        if self.retention_expires_at and datetime.now(timezone.utc) > self.retention_expires_at:
            return False
        return True


class VoiceConsentAudit(Base):
    """
    Immutable append-only audit trail for voice consent lifecycle events.

    This table is APPEND-ONLY. No UPDATE or DELETE operations should ever
    be performed on it. Each row represents a single event in the consent
    lifecycle.

    action values:
        CREATED   — Consent record was created
        VERIFIED  — Consent was checked before placing an AI voice call
        REVOKED   — Consumer revoked consent
        EXPIRED   — Consent record passed retention_expires_at
    """

    __tablename__ = "voice_consent_audit"

    id = Column(Integer, primary_key=True, index=True)
    voice_consent_id = Column(
        Integer,
        ForeignKey("voice_consents.id"),
        nullable=False,
        index=True,
    )

    action = Column(String(20), nullable=False)  # CREATED, VERIFIED, REVOKED, EXPIRED
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )
    actor_ip = Column(String(45), nullable=True)

    details = Column(JSON, nullable=True)  # Additional structured context

    # Immutable timestamp -- no updated_at by design
    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_vca_consent_action", "voice_consent_id", "action"),
        Index("ix_vca_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<VoiceConsentAudit id={self.id} consent_id={self.voice_consent_id} "
            f"action={self.action} at={self.timestamp}>"
        )


__all__ = [
    "VoiceConsent",
    "VoiceConsentAudit",
    # Constants
    "CONSENT_TYPE_PRIOR_EXPRESS",
    "CONSENT_TYPE_PRIOR_EXPRESS_WRITTEN",
    "CONSENT_TYPE_VERBAL",
    "CONSENT_TYPE_REVOKED",
    "VALID_CONSENT_TYPES",
    "CONSENT_CHANNEL_WEBFORM",
    "CONSENT_CHANNEL_VOICE_RECORDING",
    "CONSENT_CHANNEL_ESIGN",
    "CONSENT_CHANNEL_SMS_OPT_IN",
    "CONSENT_CHANNEL_MANUAL",
    "VALID_CONSENT_CHANNELS",
    "AUDIT_ACTION_CREATED",
    "AUDIT_ACTION_VERIFIED",
    "AUDIT_ACTION_REVOKED",
    "AUDIT_ACTION_EXPIRED",
    "VALID_AUDIT_ACTIONS",
    "DEFAULT_RETENTION_YEARS",
]
