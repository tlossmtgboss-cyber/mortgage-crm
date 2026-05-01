"""
SMS Compliance Models — opt-outs, consent, and compliance audit log.

These three tables back the SMS compliance gate (sms_compliance_gate.py) and
opt-out manager (sms_opt_out_manager.py).  All outbound SMS is checked against
sms_opt_outs and sms_consent before sending; every check is logged to
sms_compliance_log for TCPA audit purposes.

Usage:
    from database.models.sms_compliance import SMSOptOut, SMSConsent, SMSComplianceLog
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from db import Base


class SMSOptOut(Base):
    """Opt-out records for TCPA compliance. Checked before every outbound SMS.

    A row with ``active=True`` means the phone is opted out.  When the
    contact replies START/UNSTOP, ``active`` is set to ``False`` and
    ``opted_in_at`` is populated — the row is kept for audit trail.
    """

    __tablename__ = "sms_opt_outs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), nullable=False, index=True)
    opt_out_keyword = Column(String(20), default="STOP")
    lead_id = Column(
        Integer,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    active = Column(Boolean, default=True, nullable=False)
    opted_out_at = Column(DateTime, server_default=func.now())
    opted_in_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_sms_opt_outs_org_phone", "organization_id", "phone_number"),
        UniqueConstraint("organization_id", "phone_number", name="uq_sms_opt_out_org_phone"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<SMSOptOut id={self.id} phone={self.phone_number} "
            f"active={self.active}>"
        )


class SMSConsent(Base):
    """Written consent records for outbound SMS (TCPA).

    NOTE: This is ONE of 6+ consent sources. For authoritative SMS consent
    decisions, use ``services.sms_consent_resolver.resolve_consent()`` which
    checks this table along with tcpa_consents, sms_opt_outs,
    smart_docs_consent_records, channel_preferences, and borrower_profiles.
    Do NOT query this table alone for send/block decisions.

    The ``(organization_id, phone_number)`` composite unique constraint
    supports upsert via ``ON CONFLICT ... DO UPDATE`` in
    ``record_consent()`` and ``record_opt_in()`` in the compliance gate.
    """

    __tablename__ = "sms_consent"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), nullable=False, index=True)
    lead_id = Column(
        Integer,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    consent_given = Column(Boolean, default=False, nullable=False)
    consent_source = Column(String(50))  # "web_form", "sms_keyword", etc.
    consented_at = Column(DateTime, server_default=func.now())
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6

    __table_args__ = (
        UniqueConstraint("organization_id", "phone_number", name="uq_sms_consent_org_phone"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<SMSConsent id={self.id} phone={self.phone_number} "
            f"given={self.consent_given}>"
        )


class SMSComplianceLog(Base):
    """Immutable audit trail for pre-send compliance checks.

    One row is written per ``sms_compliance_gate.check_sms_compliance()``
    invocation, regardless of pass/fail.  ``check_result`` contains the
    gate verdict (e.g. "allowed", "blocked_opt_out", "blocked_quiet_hours").
    """

    __tablename__ = "sms_compliance_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), nullable=False, index=True)
    lead_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    check_result = Column(String(50), nullable=False)
    # TCPA consent proof — which consent record was active at time of check
    consent_record_id = Column(Integer, nullable=True)
    consent_method = Column(String(50), nullable=True)
    checked_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_sms_compliance_log_phone_checked", "phone_number", "checked_at"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<SMSComplianceLog id={self.id} phone={self.phone_number} "
            f"result={self.check_result}>"
        )
