"""
Voice Call Session Model

Persists Aria in-app voice conversations — transcript, duration, AI-generated
summary, sentiment, outcome, and tool calls executed during the session.

Supports the voice call history UI, analytics dashboard, and compliance audit.

Usage:
    from database.models.voice_call_session import VoiceCallSession, VoiceCallMessage

    session = VoiceCallSession(
        organization_id=org_id,
        user_id=user_id,
        direction="inbound",
        status="completed",
        duration_seconds=45,
        summary="Discussed pipeline status, sent follow-up SMS to John Smith.",
        sentiment="positive",
        outcome="action_taken",
    )
    db.add(session)
    db.commit()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db import Base


class VoiceCallSession(Base):
    """A single Aria in-app voice conversation session.

    Created when a user opens a voice session (WebSocket or SSE).
    Updated with transcript/summary/outcome when the session ends.
    """

    __tablename__ = "voice_call_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_uuid = Column(String(100), unique=True, nullable=False, index=True)

    # Ownership
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=True, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )

    # Session metadata
    direction = Column(String(20), default="inbound")  # inbound (user initiated), outbound (proactive)
    status = Column(
        String(30), nullable=False, default="active"
    )  # active, completed, failed, abandoned
    voice_mode = Column(String(20), default="websocket")  # websocket, sse, browser_rtc

    # Timing
    started_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # AI-generated post-call data
    summary = Column(Text, nullable=True)
    sentiment = Column(String(20), nullable=True)  # positive, neutral, negative, mixed
    outcome = Column(
        String(50), nullable=True
    )  # action_taken, info_provided, escalated, abandoned, error

    # Tool usage during session
    tools_executed = Column(JSONB, nullable=True)  # [{tool: "send_sms", args: {...}, result: {...}}]
    tool_count = Column(Integer, default=0)

    # Transcript stored as array of turn objects
    transcript = Column(JSONB, nullable=True)  # [{role, content, timestamp}]
    message_count = Column(Integer, default=0)

    # Voice provider info
    stt_provider = Column(String(30), nullable=True)  # deepgram, web_speech_api
    tts_provider = Column(String(30), nullable=True)  # elevenlabs, google, openai
    tts_voice_id = Column(String(100), nullable=True)

    # CRM context (if conversation was about a specific lead/loan)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_voice_call_sessions_user_started", "user_id", "started_at"),
        Index("ix_voice_call_sessions_org_started", "organization_id", "started_at"),
        Index("ix_voice_call_sessions_status", "status"),
    )
