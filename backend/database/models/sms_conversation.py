"""SMS conversation threading models."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON, ForeignKey, Index, Boolean
from db import Base


def _uuid():
    return str(uuid.uuid4())


class SMSAIConversation(Base):
    __tablename__ = "sms_ai_conversations"
    __table_args__ = (
        Index("ix_sms_ai_conv_phone_org", "phone_number", "organization_id"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, default=_uuid)
    phone_number = Column(String, nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    status = Column(String, default="active")  # active, paused, closed, converted
    current_stage = Column(String, default="greeting")  # greeting, qualifying, scheduling, nurture, objection_handling
    context_data = Column(JSON, default=dict)  # accumulated qualification data
    close_reason = Column(String, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    message_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SMSAIConversationMessage(Base):
    __tablename__ = "sms_ai_conversation_messages"

    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("sms_ai_conversations.id"), nullable=False, index=True)
    direction = Column(String, nullable=False)  # inbound, outbound
    content = Column(Text, nullable=False)
    intent = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    intent_method = Column(String, nullable=True)  # keyword, llm
    entities = Column(JSON, default=dict)
    ai_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
