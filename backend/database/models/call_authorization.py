"""
TCPA Call Authorization audit trail.
Every outbound call — manual, LO-approved, or autonomous — gets a record.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Index
import uuid

from db import Base


class CallAuthorization(Base):
    __tablename__ = "call_authorizations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    call_id = Column(PG_UUID(as_uuid=True), nullable=True)
    authorization_type = Column(String, nullable=False)  # lo_manual, lo_approval, auto_rule
    authorized_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rule_id = Column(String, nullable=True)
    borrower_consent_source = Column(String, nullable=True)  # web_form, verbal, signed_disclosure
    borrower_consent_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_call_auth_lead_created", "lead_id", "created_at"),
    )
