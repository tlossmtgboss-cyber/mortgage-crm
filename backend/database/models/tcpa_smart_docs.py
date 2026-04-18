"""
TCPA Consent & DNC Models for Smart Docs Follow-Up System

Supplements the existing TCPAConsent model (tcpa_consent.py) with models
specifically tailored for the document follow-up automation pipeline:

- SmartDocsConsentRecord: Per-phone consent records with full audit trail,
  used by the TCPAComplianceService to gate every SMS and call action.

- InternalDNCEntry: Organization-scoped Do Not Call entries with optional
  expiration. Checked before any outbound SMS or call.

- OutreachLog: Frequency-limiting journal. Every outbound touch (SMS, call)
  is logged so the service can enforce per-day-per-channel caps.

TCPA penalty: $500-$1,500 per unconsented message. These models exist to
ensure the follow-up automation system NEVER sends without consent.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from db import Base


class SmartDocsConsentRecord(Base):
    """
    Per-phone, per-channel consent record for the Smart Docs follow-up system.

    DEPRECATION NOTE: This is ONE of 6+ overlapping consent sources. For
    authoritative SMS consent decisions, use:
        from services.sms_consent_resolver import resolve_consent
    The resolver checks this table along with sms_consent, tcpa_consents,
    sms_opt_outs, channel_preferences, and borrower_profiles.

    Every SMS or call sent by followup_automation_service MUST have a
    corresponding active consent record.  Revocations take effect immediately
    (revoked_at IS NOT NULL => consent no longer valid).

    consent_source values:
        web_form     - borrower checked consent box on portal / landing page
        verbal       - LO recorded verbal consent during a call
        text_reply   - borrower replied YES / SUBSCRIBE to an opt-in SMS
        portal       - borrower toggled consent in the client portal
        paper        - signed paper consent form uploaded
    """

    __tablename__ = "smart_docs_consent_records"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    borrower_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    phone = Column(String(20), nullable=False, index=True)

    channel = Column(String(10), nullable=False)  # "sms", "call", "both"
    consent_given = Column(Boolean, nullable=False, default=True)

    consent_source = Column(String(50), nullable=False)
    consent_ip_address = Column(String(45), nullable=True)
    consent_user_agent = Column(Text, nullable=True)

    consented_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    revoked_at = Column(DateTime, nullable=True)
    revocation_source = Column(String(50), nullable=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_sdcr_org_phone", "organization_id", "phone"),
        Index("ix_sdcr_phone_channel", "phone", "channel"),
    )

    def __repr__(self) -> str:
        revoked = f" revoked={self.revoked_at}" if self.revoked_at else ""
        return (
            f"<SmartDocsConsentRecord id={self.id} phone={self.phone} "
            f"channel={self.channel} source={self.consent_source}{revoked}>"
        )


class InternalDNCEntry(Base):
    """
    Organization-scoped Do Not Call / Do Not Text entry.

    Checked before any outbound SMS or call from the Smart Docs follow-up
    system. Entries with expires_at=NULL are permanent.
    """

    __tablename__ = "internal_dnc_entries"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    phone = Column(String(20), nullable=False, index=True)

    reason = Column(String(200), nullable=True)

    added_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    added_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at = Column(DateTime, nullable=True)  # NULL = permanent

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_idnc_org_phone", "organization_id", "phone"),
    )

    def __repr__(self) -> str:
        return (
            f"<InternalDNCEntry id={self.id} phone={self.phone} "
            f"reason={self.reason}>"
        )


class OutreachLog(Base):
    """
    Per-phone outreach frequency log for TCPA rate limiting.

    Every SMS sent or call placed by the follow-up system is recorded here
    so that check_frequency_limit() can enforce daily caps per channel.
    """

    __tablename__ = "smart_docs_outreach_log"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    phone = Column(String(20), nullable=False, index=True)

    channel = Column(String(10), nullable=False)  # "sms", "call"
    campaign_id = Column(Integer, nullable=True)

    sent_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_sol_org_phone_channel_sent", "organization_id", "phone", "channel", "sent_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<OutreachLog id={self.id} phone={self.phone} "
            f"channel={self.channel} sent_at={self.sent_at}>"
        )


__all__ = [
    "SmartDocsConsentRecord",
    "InternalDNCEntry",
    "OutreachLog",
]
