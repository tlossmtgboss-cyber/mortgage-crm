"""Call disposition model — structured disposition logging with reporting support."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON, ForeignKey, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID
from db import Base


def _uuid():
    return str(uuid.uuid4())


class CallDisposition(Base):
    __tablename__ = "call_dispositions"

    id = Column(String, primary_key=True, default=_uuid)
    canonical_call_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    call_log_id = Column(String, nullable=True, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True, index=True)
    loan_id = Column(String, nullable=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)

    # Disposition outcome
    disposition = Column(String, nullable=False)  # answered, voicemail, no_answer, busy, wrong_number, dnc, callback, transferred
    sub_disposition = Column(String, nullable=True)  # qualified, not_interested, needs_followup, appointment_set, etc.

    # Call metadata
    call_direction = Column(String, default="outbound")  # inbound, outbound
    call_duration_seconds = Column(Integer, nullable=True)
    caller_phone = Column(String, nullable=True)

    # AI analysis
    ai_summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)  # positive, neutral, negative
    intent_detected = Column(String, nullable=True)
    qualification_score = Column(Float, nullable=True)

    # Follow-up
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(DateTime, nullable=True)
    follow_up_notes = Column(Text, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)
    voice_note_url = Column(String, nullable=True)
    transcript_url = Column(String, nullable=True)

    # Source context
    source = Column(String, default="dialer")  # dialer, ai_call, manual, receptionist
    session_id = Column(String, nullable=True)  # dialer session if applicable

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_disposition_org_date", "organization_id", "created_at"),
        Index("ix_disposition_user_date", "user_id", "created_at"),
        Index("ix_disposition_canonical", "canonical_call_id"),
    )
