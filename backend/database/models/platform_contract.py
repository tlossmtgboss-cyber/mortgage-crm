"""
Platform Contract Models

Tracks licensing agreements, contracts, and e-signed documents between
the Perennia AI platform and its CRM licensees (organizations).

Usage:
    from database.models.platform_contract import PlatformContract
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, JSON, Date, Numeric
)
from sqlalchemy.orm import relationship

from db import Base


class PlatformContract(Base):
    __tablename__ = "platform_contracts"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    client_profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=True, index=True)

    # Contract details
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    contract_type = Column(String(50), nullable=False, default="license_agreement")  # license_agreement, addendum, nda, service_agreement
    status = Column(String(20), nullable=False, default="draft", index=True)  # draft, sent, viewed, signed, expired, voided

    # PDF storage
    pdf_storage_key = Column(String(500), nullable=True)
    pdf_file_name = Column(String(255), nullable=True)

    # Signed copy
    signed_pdf_storage_key = Column(String(500), nullable=True)
    signed_at = Column(DateTime, nullable=True)

    # E-sign integration (links to existing esign system, no FK constraint)
    esign_envelope_id = Column(Integer, nullable=True, index=True)

    # Contract terms
    effective_date = Column(Date, nullable=True)
    expiration_date = Column(Date, nullable=True)
    auto_renew = Column(Boolean, default=False)
    renewal_term_months = Column(Integer, nullable=True)

    # Financial
    contract_value = Column(Numeric(14, 2), nullable=True)
    billing_frequency = Column(String(20), nullable=True)  # monthly, quarterly, annually

    # Signer info (denormalized for display)
    signer_name = Column(String(255), nullable=True)
    signer_email = Column(String(255), nullable=True)
    signer_title = Column(String(255), nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)
    contract_metadata = Column("metadata", JSON, nullable=True)

    # Audit
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    organization = relationship("Organization", backref="platform_contracts")
    client_profile = relationship("ClientProfile", backref="platform_contracts")
    created_by = relationship("User", backref="created_contracts", foreign_keys=[created_by_user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "client_profile_id": self.client_profile_id,
            "title": self.title,
            "description": self.description,
            "contract_type": self.contract_type,
            "status": self.status,
            "pdf_file_name": self.pdf_file_name,
            "has_pdf": bool(self.pdf_storage_key),
            "has_signed_pdf": bool(self.signed_pdf_storage_key),
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "esign_envelope_id": self.esign_envelope_id,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "auto_renew": self.auto_renew,
            "renewal_term_months": self.renewal_term_months,
            "contract_value": self.contract_value,
            "billing_frequency": self.billing_frequency,
            "signer_name": self.signer_name,
            "signer_email": self.signer_email,
            "signer_title": self.signer_title,
            "notes": self.notes,
            "tags": self.tags,
            "metadata": self.contract_metadata,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
