"""
Telephony Database Models

NOTE: This file shows the ideal model structure with UUIDs and proper relationships.
The actual models are currently defined in main.py with integer IDs to match
the existing database schema.

To migrate to this structure in the future:
1. Set up Alembic migrations
2. Create migration to add UUID columns
3. Migrate data
4. Update foreign key references
5. Switch to this models file
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

# For future use with UUID-based architecture:
# from sqlalchemy.dialects.postgresql import UUID
# import uuid
# from app.database import Base

# Current implementation uses main.py Base
# from backend.main import Base

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================


class SessionStatus(str, enum.Enum):
    """Dialer session states"""
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class TaskStatus(str, enum.Enum):
    """Individual task states within a session"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    SKIPPED = "skipped"


class CallOutcome(str, enum.Enum):
    """Possible outcomes for a call attempt"""
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    CANCELED = "canceled"


class VerificationStatus(str, enum.Enum):
    """Caller ID verification states"""
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


# =============================================================================
# FUTURE UUID-BASED MODELS (Reference Implementation)
# =============================================================================
#
# class AgentTelephonySettings(Base):
#     """Per-agent telephony configuration"""
#     __tablename__ = "agent_telephony_settings"
#
#     agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), primary_key=True)
#     cell_phone = Column(String(20), nullable=False)
#     business_caller_id = Column(String(20), nullable=False)
#     dialer_enabled = Column(Boolean, default=True)
#     max_calls_per_day = Column(Integer, default=200)
#     max_concurrent_sessions = Column(Integer, default=1)
#     preferred_pause_timeout = Column(Integer, default=90)
#     created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
#     updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
#
#     # Relationships
#     agent = relationship("Agent", back_populates="telephony_settings")
#
#
# class DialerSession(Base):
#     """A power dialer session with multiple tasks"""
#     __tablename__ = "dialer_sessions"
#
#     session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
#     status = Column(Enum(SessionStatus), default=SessionStatus.ACTIVE)
#     current_task_id = Column(UUID(as_uuid=True), nullable=True)
#     total_tasks = Column(Integer, default=0)
#     completed_tasks = Column(Integer, default=0)
#     failed_tasks = Column(Integer, default=0)
#     skipped_tasks = Column(Integer, default=0)
#     created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
#     updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
#     completed_at = Column(DateTime, nullable=True)
#
#     # Relationships
#     agent = relationship("Agent", back_populates="dialer_sessions")
#     tasks = relationship("DialerSessionTask", back_populates="session")
#
#     __table_args__ = (
#         Index('idx_dialer_sessions_agent_status', 'agent_id', 'status'),
#     )
#
#
# class DialerSessionTask(Base):
#     """Individual task within a dialer session"""
#     __tablename__ = "dialer_session_tasks"
#
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     session_id = Column(UUID(as_uuid=True), ForeignKey("dialer_sessions.session_id"), nullable=False)
#     contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False)
#     phone = Column(String(20), nullable=False)
#     loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=True)
#     referring_partner_id = Column(UUID(as_uuid=True), ForeignKey("referring_partners.id"), nullable=True)
#     status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
#     call_sid = Column(String(100), nullable=True)
#     disposition = Column(String(100), nullable=True)
#     notes = Column(Text, nullable=True)
#     ai_note_summary = Column(Text, nullable=True)
#     follow_up_date = Column(DateTime, nullable=True)
#     task_order = Column(Integer, nullable=False)
#     created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
#     updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
#     completed_at = Column(DateTime, nullable=True)
#
#     # Relationships
#     session = relationship("DialerSession", back_populates="tasks")
#     contact = relationship("Contact")
#
#     __table_args__ = (
#         Index('idx_session_tasks_session_order', 'session_id', 'task_order'),
#         Index('idx_session_tasks_status', 'status'),
#     )
#
#
# class CallLog(Base):
#     """Record of all calls made through the system"""
#     __tablename__ = "call_logs"
#
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
#     contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False)
#     loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=True)
#     referring_partner_id = Column(UUID(as_uuid=True), ForeignKey("referring_partners.id"), nullable=True)
#     session_id = Column(UUID(as_uuid=True), ForeignKey("dialer_sessions.session_id"), nullable=True)
#     start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
#     end_time = Column(DateTime, nullable=True)
#     duration_seconds = Column(Integer, nullable=True)
#     call_sid = Column(String(100), nullable=False, unique=True)
#     outcome = Column(Enum(CallOutcome), nullable=True)
#     failure_reason = Column(String(100), nullable=True)
#     disposition = Column(String(100), nullable=True)
#     notes = Column(Text, nullable=True)
#     ai_note_summary = Column(Text, nullable=True)
#     caller_id_used = Column(String(20), nullable=False)
#     created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
#     updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
#
#     # Relationships
#     agent = relationship("Agent")
#     contact = relationship("Contact")
#     session = relationship("DialerSession")
#
#     __table_args__ = (
#         Index('idx_call_logs_agent_date', 'agent_id', 'start_time'),
#         Index('idx_call_logs_call_sid', 'call_sid'),
#         Index('idx_call_logs_contact', 'contact_id'),
#     )
#
#
# class ActiveCall(Base):
#     """Soft lock to prevent multiple agents calling same contact"""
#     __tablename__ = "active_calls"
#
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False)
#     agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
#     call_sid = Column(String(100), nullable=False)
#     locked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
#     expires_at = Column(DateTime, nullable=False)
#
#     __table_args__ = (
#         Index('idx_active_calls_contact', 'contact_id'),
#         Index('idx_active_calls_expires', 'expires_at'),
#     )
#
#
# class VerifiedCallerId(Base):
#     """Telnyx-verified outbound caller IDs"""
#     __tablename__ = "verified_caller_ids"
#
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     phone_number = Column(String(20), unique=True, nullable=False)
#     friendly_name = Column(String(100), nullable=False)
#     verification_status = Column(Enum(VerificationStatus), default=VerificationStatus.PENDING)
#     provider_sid = Column(String(100), nullable=True)
#     organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
#     verified_at = Column(DateTime, nullable=True)
#     created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
#     updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
#
#     __table_args__ = (
#         Index('idx_caller_ids_org', 'organization_id'),
#     )
