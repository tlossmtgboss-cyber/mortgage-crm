"""Borrower prep sequence models for pre-appointment preparation."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Index
from db import Base


def _uuid():
    return str(uuid.uuid4())


class BorrowerPrepSequence(Base):
    __tablename__ = "borrower_prep_sequences"

    id = Column(String, primary_key=True, default=_uuid)
    appointment_id = Column(String, nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True)
    organization_id = Column(String, nullable=False, index=True)
    appointment_type = Column(String, nullable=False)  # pre_approval_consult, rate_lock_call, closing_prep
    status = Column(String, default="active")  # active, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)


class BorrowerPrepStep(Base):
    __tablename__ = "borrower_prep_steps"

    id = Column(String, primary_key=True, default=_uuid)
    sequence_id = Column(String, ForeignKey("borrower_prep_sequences.id"), nullable=False, index=True)
    trigger_offset = Column(String, nullable=False)  # T-48h, T-24h, T-2h, T-30m
    trigger_time = Column(DateTime, nullable=True)
    channel = Column(String, nullable=False)  # sms, email
    template_key = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    status = Column(String, default="scheduled")  # scheduled, sent, failed, cancelled
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
