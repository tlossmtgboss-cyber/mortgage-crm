"""
POS Consent Models — Credit Authorization & E-Consent Agreement
================================================================
Legally significant consent records for the POS voice-complete flow.

When a URLA voice agent completes an application, the borrower receives
an SMS with a magic link to review, authorize credit, agree to
e-disclosures, and submit. These tables capture the consent events
with the specificity regulators expect: exact text shown, typed name,
IP, user agent, and content hash for tamper detection.

Models:
    - CreditAuthorization: FCRA Section 604(a)(3)(A) credit pull consent
    - EConsentAgreement: E-SIGN Act electronic disclosure consent

Both integrate with ESignatureAuditEvent for the unified event stream.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from db import Base
from encryption_utils import EncryptedString


class CreditAuthorization(Base):
    """FCRA credit pull authorization captured via POS consent flow.

    Records the borrower's explicit consent to pull credit, including
    the exact disclosure language shown (hashed for integrity) and the
    borrower's typed full name as their electronic signature.
    """
    __tablename__ = "credit_authorizations"
    __table_args__ = (
        Index("ix_credit_auth_application_id", "application_id"),
        Index("ix_credit_auth_organization_id", "organization_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    application_id = Column(Integer, ForeignKey("borrower_applications.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)

    authorized = Column(Boolean, nullable=False, default=False)
    consent_text_version = Column(String(50), nullable=False)
    consent_text_hash = Column(String(64), nullable=False)

    typed_full_name = Column(String(255), nullable=False)

    ip_address = Column(EncryptedString, nullable=False)
    user_agent = Column(String(512), nullable=False)

    authorized_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EConsentAgreement(Base):
    """E-SIGN Act electronic disclosure consent.

    Records the borrower's agreement to receive disclosures electronically,
    including the specific hardware/software requirements disclosed and
    their right to withdraw consent or request paper copies.
    """
    __tablename__ = "econsent_agreements"
    __table_args__ = (
        Index("ix_econsent_application_id", "application_id"),
        Index("ix_econsent_organization_id", "organization_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    application_id = Column(Integer, ForeignKey("borrower_applications.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)

    consented = Column(Boolean, nullable=False, default=False)
    consent_text_version = Column(String(50), nullable=False)
    consent_text_hash = Column(String(64), nullable=False)

    typed_full_name = Column(String(255), nullable=False)

    hardware_software_requirements_shown = Column(Text, nullable=False)
    right_to_withdraw_shown = Column(Text, nullable=False)
    paper_copy_info_shown = Column(Text, nullable=False)

    ip_address = Column(EncryptedString, nullable=False)
    user_agent = Column(String(512), nullable=False)

    consented_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
