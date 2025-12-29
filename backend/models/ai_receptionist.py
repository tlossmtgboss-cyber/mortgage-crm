"""
AI Receptionist Models
Database models for AI-powered voice receptionist call logs and analytics.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from database import Base


class AIReceptionistCallLog(Base):
    """
    Stores call logs for AI Receptionist interactions.
    """
    __tablename__ = "ai_receptionist_call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Call identification
    call_sid = Column(String(100), unique=True, nullable=False, index=True)

    # Call details
    status = Column(String(50))  # initiated, ringing, in-progress, completed, failed, busy, no-answer
    from_number = Column(String(20))
    to_number = Column(String(20))
    direction = Column(String(20))  # inbound, outbound
    duration_seconds = Column(Integer)

    # Conversation content
    transcript = Column(Text)
    summary = Column(Text)

    # AI analysis
    intent_detected = Column(String(100))  # e.g., "loan_inquiry", "rate_check", "callback_request"
    sentiment = Column(String(20))  # positive, neutral, negative

    # Callback handling
    callback_requested = Column(Boolean, default=False)
    callback_reason = Column(String(255))
    callback_completed = Column(Boolean, default=False)
    callback_completed_at = Column(DateTime)

    # Assignment
    assigned_lo_id = Column(Integer)  # Loan officer ID if assigned

    # Metadata
    metadata = Column(JSONB, default={})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_ai_calls_status', 'status'),
        Index('idx_ai_calls_callback', 'callback_requested'),
        Index('idx_ai_calls_created', 'created_at'),
    )

    def __repr__(self):
        return f"<AIReceptionistCallLog {self.call_sid} - {self.status}>"

    def to_dict(self):
        return {
            'id': self.id,
            'call_sid': self.call_sid,
            'status': self.status,
            'from_number': self.from_number,
            'to_number': self.to_number,
            'direction': self.direction,
            'duration_seconds': self.duration_seconds,
            'transcript': self.transcript,
            'summary': self.summary,
            'intent_detected': self.intent_detected,
            'sentiment': self.sentiment,
            'callback_requested': self.callback_requested,
            'callback_reason': self.callback_reason,
            'callback_completed': self.callback_completed,
            'assigned_lo_id': self.assigned_lo_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
