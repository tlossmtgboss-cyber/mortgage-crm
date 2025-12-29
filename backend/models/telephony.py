"""
Telephony Database Models

Active models for telephony/dialer functionality including:
- Agent telephony settings
- Dialer sessions and tasks
- Call logs
- Active call locks
- Verified caller IDs
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from database import Base


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


class AgentTelephonySettings(Base):
    """Per-agent telephony configuration"""
    __tablename__ = "agent_telephony_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    cell_phone = Column(String(20), nullable=False)
    business_caller_id = Column(String(20), nullable=False)
    dialer_enabled = Column(Boolean, default=True)
    max_calls_per_day = Column(Integer, default=200)
    max_concurrent_sessions = Column(Integer, default=1)
    preferred_pause_timeout = Column(Integer, default=90)  # seconds
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'cell_phone': self.cell_phone,
            'business_caller_id': self.business_caller_id,
            'dialer_enabled': self.dialer_enabled,
            'max_calls_per_day': self.max_calls_per_day,
            'max_concurrent_sessions': self.max_concurrent_sessions,
            'preferred_pause_timeout': self.preferred_pause_timeout,
        }


class DialerSession(Base):
    """A power dialer session with multiple tasks"""
    __tablename__ = "dialer_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.ACTIVE)
    current_task_id = Column(Integer, nullable=True)
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    failed_tasks = Column(Integer, default=0)
    skipped_tasks = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    tasks = relationship("DialerSessionTask", back_populates="session")

    __table_args__ = (
        Index('idx_dialer_sessions_agent_status', 'agent_id', 'status'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'status': self.status.value if self.status else None,
            'current_task_id': self.current_task_id,
            'total_tasks': self.total_tasks,
            'completed_tasks': self.completed_tasks,
            'failed_tasks': self.failed_tasks,
            'skipped_tasks': self.skipped_tasks,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class DialerSessionTask(Base):
    """Individual task within a dialer session"""
    __tablename__ = "dialer_session_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("dialer_sessions.id"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    contact_name = Column(String(255))
    phone = Column(String(20), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    referring_partner_id = Column(Integer, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    call_sid = Column(String(100), nullable=True)
    disposition = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    ai_note_summary = Column(Text, nullable=True)
    follow_up_date = Column(DateTime, nullable=True)
    task_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    session = relationship("DialerSession", back_populates="tasks")

    __table_args__ = (
        Index('idx_session_tasks_session_order', 'session_id', 'task_order'),
        Index('idx_session_tasks_status', 'status'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'contact_id': self.contact_id,
            'contact_name': self.contact_name,
            'phone': self.phone,
            'lead_id': self.lead_id,
            'loan_id': self.loan_id,
            'status': self.status.value if self.status else None,
            'call_sid': self.call_sid,
            'disposition': self.disposition,
            'notes': self.notes,
            'ai_note_summary': self.ai_note_summary,
            'follow_up_date': self.follow_up_date.isoformat() if self.follow_up_date else None,
            'task_order': self.task_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class CallLog(Base):
    """Record of all calls made through the system"""
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    referring_partner_id = Column(Integer, nullable=True)
    session_id = Column(Integer, ForeignKey("dialer_sessions.id"), nullable=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    call_sid = Column(String(100), nullable=False, unique=True, index=True)
    outcome = Column(Enum(CallOutcome), nullable=True)
    failure_reason = Column(String(100), nullable=True)
    disposition = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    ai_note_summary = Column(Text, nullable=True)
    caller_id_used = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_call_logs_agent_date', 'agent_id', 'start_time'),
        Index('idx_call_logs_contact', 'contact_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'contact_id': self.contact_id,
            'lead_id': self.lead_id,
            'loan_id': self.loan_id,
            'session_id': self.session_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.duration_seconds,
            'call_sid': self.call_sid,
            'outcome': self.outcome.value if self.outcome else None,
            'disposition': self.disposition,
            'notes': self.notes,
            'ai_note_summary': self.ai_note_summary,
            'caller_id_used': self.caller_id_used,
        }


class ActiveCall(Base):
    """Soft lock to prevent multiple agents calling same contact"""
    __tablename__ = "active_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    call_sid = Column(String(100), nullable=False)
    locked_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('idx_active_calls_expires', 'expires_at'),
    )


class VerifiedCallerId(Base):
    """Twilio-verified outbound caller IDs"""
    __tablename__ = "verified_caller_ids"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, nullable=False)
    friendly_name = Column(String(100), nullable=False)
    verification_status = Column(Enum(VerificationStatus), default=VerificationStatus.PENDING)
    twilio_sid = Column(String(100), nullable=True)
    organization_id = Column(Integer, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_caller_ids_org', 'organization_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'phone_number': self.phone_number,
            'friendly_name': self.friendly_name,
            'verification_status': self.verification_status.value if self.verification_status else None,
            'twilio_sid': self.twilio_sid,
            'organization_id': self.organization_id,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
        }


class DialerQueueRule(Base):
    """Rules for dialer queue management per campaign"""
    __tablename__ = "dialer_queue_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_instance_id = Column(String(100), unique=True, nullable=False, index=True)
    priority = Column(String(20), default="NORMAL")  # URGENT, HIGH, NORMAL, LOW
    max_attempts = Column(Integer, default=3)
    retry_interval_minutes = Column(Integer, default=30)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'campaign_instance_id': self.campaign_instance_id,
            'priority': self.priority,
            'max_attempts': self.max_attempts,
            'retry_interval_minutes': self.retry_interval_minutes,
            'active': self.active,
        }
