"""
Immutable TCPA Consent Audit Trail

Append-only audit log for every consent grant, revocation, and verification
event across ALL consent sources (ChannelPreference, TCPAConsent, VoiceConsent).

This table is APPEND-ONLY. No UPDATE or DELETE operations should ever be
performed on this table. Each row represents a single consent lifecycle event.

Regulatory context:
    - TCPA (47 U.S.C. 227): Requires provable record of consent before
      autodialed/prerecorded calls.
    - FCC 1:1 consent rule (eff. April 2026): Must prove consent was granted
      by THIS consumer for THIS company.
    - FCC revocation rule: Opt-outs must be honoured within 10 business days.
    - Recommended retention: 7 years (matches IRS guidance for mortgage lenders).

Usage:
    from database.models.consent_audit import ConsentAuditLog

    log = ConsentAuditLog(
        organization_id=org_id,
        contact_id=lead_id,
        consent_type="call",
        action="granted",
        method="web_form",
        ip_address="192.168.1.1",
        source_table="channel_preferences",
        source_record_id=pref_id,
        actor_user_id=user_id,
        details={"disclosure_version": "v2.1"},
    )
    db.add(log)
"""

from datetime import datetime, timezone

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


class ConsentAuditLog(Base):
    """
    Immutable append-only audit trail for consent lifecycle events.

    This table is APPEND-ONLY. No UPDATE or DELETE operations should ever
    be performed on it.

    consent_type values:
        - call: Voice/telephone consent
        - sms: SMS/text message consent
        - email: Email marketing consent
        - voice_ai: AI-generated voice call consent (TCPA specific)
        - both: Covers call + sms (from TCPAConsent)

    action values:
        - granted: Consent was recorded/granted
        - revoked: Consent was revoked/withdrawn
        - verified: Consent was checked before an outbound contact attempt
        - expired: Consent record reached its expiration date
        - updated: Consent preference was modified (e.g. call_consent toggled)

    method values (for grant/revoke):
        - web_form: Online form submission
        - verbal: Verbal consent during a call
        - text_reply: SMS opt-in/opt-out reply (STOP, YES, etc.)
        - paper_form: Physical signed document
        - portal: Borrower/partner portal action
        - api: Programmatic via API
        - manual: LO manually recorded
        - app_signup: Mobile app signup flow
        - esign: Electronic signature (DocuSign, etc.)
        - system: System-initiated (expiration, migration)
    """

    __tablename__ = "consent_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )

    # Who the consent applies to (lead_id, borrower_id, etc.)
    # Stored as Integer to match Lead.id / ChannelPreference.lead_id
    contact_id = Column(Integer, nullable=True, index=True)
    # Also support UUID-based contacts (TCPAConsent uses UUID contact_id)
    contact_uuid = Column(String(36), nullable=True, index=True)
    contact_type = Column(String(30), nullable=True)  # lead, borrower, referral_partner

    # What type of consent
    consent_type = Column(
        String(20),
        nullable=False,
        index=True,
    )  # call, sms, email, voice_ai, both

    # What happened
    action = Column(
        String(20),
        nullable=False,
        index=True,
    )  # granted, revoked, verified, expired, updated

    # How consent was captured/revoked
    method = Column(String(30), nullable=True)  # web_form, verbal, text_reply, etc.

    # Evidence / provenance
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)  # Browser UA string

    # Which consent source triggered this event
    source_table = Column(
        String(50),
        nullable=True,
    )  # channel_preferences, tcpa_consents, voice_consents, sms_consent
    source_record_id = Column(String(50), nullable=True)  # ID in the source table

    # Who performed the action
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    # Verification result (for action=verified)
    verification_result = Column(
        String(20),
        nullable=True,
    )  # passed, failed, not_found

    # Freeform context
    reason = Column(Text, nullable=True)  # Human-readable reason
    details = Column(JSON, nullable=True)  # Structured metadata

    # Masked phone (last 4 digits only for PII compliance)
    phone_masked = Column(String(10), nullable=True)

    # Immutable timestamp -- no updated_at by design
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # Primary query pattern: all consent events for a contact
        Index("ix_consent_audit_contact", "contact_id", "created_at"),
        Index("ix_consent_audit_contact_uuid", "contact_uuid", "created_at"),
        # Org-scoped queries
        Index("ix_consent_audit_org_created", "organization_id", "created_at"),
        # Filter by type + action
        Index("ix_consent_audit_type_action", "consent_type", "action", "created_at"),
        # Org + contact for tenant-isolated lookups
        Index("ix_consent_audit_org_contact", "organization_id", "contact_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ConsentAuditLog id={self.id} contact={self.contact_id} "
            f"type={self.consent_type} action={self.action} at={self.created_at}>"
        )


__all__ = [
    "ConsentAuditLog",
]
