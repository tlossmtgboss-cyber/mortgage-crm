"""
Partner Portal Models

Models for partner portal authentication and pre-approval letter tracking.
Extends the existing ReferralPartner model with portal-specific concerns.

The ReferralPartner model (in referral.py) is the canonical partner identity.
These models add portal session management and letter-request tracking on top.

Usage:
    from database.models.partner import PartnerSession, PreApprovalLetterRequest
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship

from db import Base


# ============================================================================
# PARTNER SESSION (portal authentication)
# ============================================================================

class PartnerSession(Base):
    """
    Session tokens for partner portal access.
    Partners authenticate separately from LO users — they are NOT in the users table.
    Mirrors the BorrowerMagicLink / ApplicationSession pattern.
    """
    __tablename__ = "partner_sessions"
    __table_args__ = (
        Index("ix_partner_session_token", "token"),
        Index("ix_partner_session_partner_id", "partner_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    partner_id = Column(Integer, ForeignKey("referral_partners.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship
    partner = relationship("ReferralPartner")


# ============================================================================
# PRE-APPROVAL LETTER REQUEST
# ============================================================================

class PreApprovalLetterRequest(Base):
    """
    Tracks partner requests for pre-approval letters.
    The LO reviews and generates (or auto-generates) the letter; the partner
    can then download the PDF from the portal.
    """
    __tablename__ = "pre_approval_letter_requests"
    __table_args__ = (
        Index("ix_prequal_req_partner_id", "partner_id"),
        Index("ix_prequal_req_loan_id", "loan_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("referral_partners.id", ondelete="CASCADE"), nullable=False)
    loan_id = Column(Integer, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Buyer details (snapshot at time of request)
    buyer_name = Column(String, nullable=False)
    buyer_email = Column(String)
    property_address = Column(String)
    requested_amount = Column(String)  # String to avoid exposing exact financials

    # Status tracking
    status = Column(String, default="pending")  # pending, approved, denied, generated
    letter_url = Column(String)  # S3/storage URL to generated PDF
    notes = Column(Text)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    partner = relationship("ReferralPartner")
    loan = relationship("Loan")
    lead = relationship("Lead")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "PartnerSession",
    "PreApprovalLetterRequest",
]
