"""
Unified Communication Threading Models (Domain 2)

Unified file-level communication timeline that aggregates SMS, email, call,
note, and system events into a single chronological thread per loan file.

Usage:
    from database.models.file_communication import FileCommunication, CommunicationParticipant

    # Query all comms for a loan file
    comms = db.query(FileCommunication).filter(
        FileCommunication.file_id == loan_id,
        FileCommunication.organization_id == org_id,
    ).order_by(FileCommunication.created_at.desc()).all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index,
    UniqueConstraint,
)

from db import Base


class FileCommunication(Base):
    """Unified communication record for a loan file (SMS, email, call, note, system)."""
    __tablename__ = "file_communications"
    __table_args__ = (
        Index("ix_file_comms_org_file_created", "organization_id", "file_id", "created_at"),
        Index("ix_file_comms_file_id", "file_id"),
        Index("ix_file_comms_source", "source_table", "source_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)

    # Message direction and channel
    direction = Column(String, nullable=False)  # 'inbound' | 'outbound'
    channel = Column(String, nullable=False)  # 'sms' | 'email' | 'call' | 'note' | 'system'

    # Content
    body = Column(Text, nullable=False)
    html_body = Column(Text, nullable=True)  # For emails
    subject = Column(String, nullable=True)  # For emails

    # Participants
    from_party = Column(String, nullable=False)  # Sender identifier (phone, email, user name)
    to_party = Column(String, nullable=False)  # Recipient identifier
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Internal sender

    # AI enrichment
    ai_summary = Column(Text, nullable=True)
    ai_draft_response = Column(Text, nullable=True)
    ai_draft_status = Column(String, nullable=True)  # 'pending' | 'approved' | 'rejected' | 'sent'

    # Source system linkage
    source_id = Column(String, nullable=True)  # Original message ID (telnyx_id, graph_id, etc.)
    source_table = Column(String, nullable=True)  # 'sms_messages' | 'email_messages' | 'call_logs' | 'activities'

    # Structured data
    attachments = Column(JSON, nullable=True)
    extra_metadata = Column("metadata", JSON, nullable=True)
    read_by = Column(JSON, default=list)  # Array of user_ids who have read this

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class CommunicationParticipant(Base):
    """Tracks which users are participants in a loan file's communication thread."""
    __tablename__ = "communication_participants"
    __table_args__ = (
        UniqueConstraint("file_id", "user_id", name="uq_comm_participant_file_user"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    notify = Column(Boolean, default=True, nullable=False)
    last_read_at = Column(DateTime, nullable=True)
