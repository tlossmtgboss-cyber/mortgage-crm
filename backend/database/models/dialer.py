"""
Power Dialer / Telephony Models

Models for the power dialer system including sessions, tasks, call logs, and DNC.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.dialer import DialerSession, CallLog, AgentTelephonySettings
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, ForeignKey, Enum as SQLEnum, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship

from db import Base
from database.enums import DialerSessionStatus, DialerTaskStatus, CallOutcome


class AgentTelephonySettings(Base):
    """Telephony settings for each agent/user"""
    __tablename__ = "agent_telephony_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    cell_phone = Column(String, nullable=True)
    business_caller_id = Column(String, nullable=True)
    dialer_enabled = Column(Boolean, default=True)
    max_calls_per_day = Column(Integer, default=200)
    max_concurrent_sessions = Column(Integer, default=1)
    auto_advance = Column(Boolean, default=True)
    pause_between_calls = Column(Integer, default=3)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    user = relationship("User", backref="telephony_settings")


class VerifiedCallerId(Base):
    """Verified caller IDs for the organization"""
    __tablename__ = "verified_caller_ids"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, nullable=False)
    friendly_name = Column(String)
    verification_status = Column(String, default="pending")  # pending, verified, failed
    provider_sid = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))  # Owner
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class DialerSession(Base):
    """Power dialer session tracking"""
    __tablename__ = "dialer_sessions"
    __table_args__ = (
        Index('ix_dialer_sessions_agent_status', 'agent_id', 'status'),
    )
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(SQLEnum(DialerSessionStatus), default=DialerSessionStatus.ACTIVE)
    current_task_id = Column(Integer, nullable=True)
    caller_id_used = Column(String)
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    failed_tasks = Column(Integer, default=0)
    skipped_tasks = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)
    agent = relationship("User", backref="dialer_sessions")
    tasks = relationship("DialerSessionTask", back_populates="session", order_by="DialerSessionTask.task_order")


class DialerSessionTask(Base):
    """Individual task/contact in a dialer session queue"""
    __tablename__ = "dialer_session_tasks"
    __table_args__ = (
        Index('ix_dialer_session_tasks_session', 'session_id', 'status'),
        Index('ix_dialer_session_tasks_order', 'session_id', 'task_order'),
    )
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("dialer_sessions.id"), nullable=False)
    contact_phone = Column(String, nullable=False)
    contact_name = Column(String)
    contact_context = Column(String)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    referral_partner_id = Column(Integer, ForeignKey("referral_partners.id"), nullable=True)
    mum_client_id = Column(Integer, ForeignKey("mum_clients.id"), nullable=True)
    original_task_id = Column(Integer, ForeignKey("ai_tasks.id"), nullable=True)
    status = Column(SQLEnum(DialerTaskStatus), default=DialerTaskStatus.PENDING)
    call_sid = Column(String)
    disposition = Column(String)
    notes = Column(Text)
    ai_note_summary = Column(Text)
    follow_up_date = Column(DateTime)
    task_order = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)
    session = relationship("DialerSession", back_populates="tasks")


class CallLog(Base):
    """Log of all calls made through the system"""
    __tablename__ = "call_logs"
    __table_args__ = (
        Index('ix_call_logs_agent', 'agent_id', 'created_at'),
        Index('ix_call_logs_call_sid', 'call_sid'),
    )
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    contact_phone = Column(String, nullable=False)
    contact_name = Column(String)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    referral_partner_id = Column(Integer, ForeignKey("referral_partners.id"), nullable=True)
    mum_client_id = Column(Integer, ForeignKey("mum_clients.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("dialer_sessions.id"), nullable=True)
    session_task_id = Column(Integer, ForeignKey("dialer_session_tasks.id"), nullable=True)
    call_sid = Column(String, index=True)
    caller_id_used = Column(String)
    start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime)
    duration_seconds = Column(Integer)
    outcome = Column(SQLEnum(CallOutcome))
    failure_reason = Column(String)
    disposition = Column(String)
    notes = Column(Text)
    ai_note_summary = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    agent = relationship("User", backref="call_logs")


class ActiveCall(Base):
    """Soft lock for preventing multi-agent collision on same contact"""
    __tablename__ = "active_calls"
    __table_args__ = (
        Index('ix_active_calls_contact', 'contact_phone', 'expires_at'),
    )
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    contact_phone = Column(String, nullable=False)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    call_sid = Column(String)
    locked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)


class ContactDNCStatus(Base):
    """Do Not Call list for contacts"""
    __tablename__ = "contact_dnc_status"
    __table_args__ = (
        UniqueConstraint('phone_number', 'organization_id', name='uq_dnc_phone_org'),
    )
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    phone_number = Column(String, nullable=False, index=True)
    reason = Column(String)
    added_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


__all__ = [
    "AgentTelephonySettings",
    "VerifiedCallerId",
    "DialerSession",
    "DialerSessionTask",
    "CallLog",
    "ActiveCall",
    "ContactDNCStatus",
]
