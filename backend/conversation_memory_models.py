"""
AI Conversation Memory Models
Stores permanent conversation history for AI assistant
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import text
from database import Base


class AIConversationMemory(Base):
    """Store every message forever"""
    __tablename__ = 'ai_conversation_memory'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    message_index = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    action_id = Column(UUID(as_uuid=True), nullable=True)
    action_data = Column(JSONB, nullable=True)
    is_ai_generated = Column(Boolean, default=False, nullable=False, server_default=text('false'))  # AI-005: Content attribution
    ai_model = Column(String(50), nullable=True)  # AI-005: Which model generated this (claude-opus-4-5, gpt-4o, etc.)
    ai_confidence = Column(Integer, nullable=True)  # AI-005: Confidence score 0-100 if applicable
    created_at = Column(DateTime, nullable=False, server_default=text('NOW()'))

    __table_args__ = (
        Index('idx_conv_user_date', 'user_id', 'created_at'),
        Index('idx_conv_session', 'session_id', 'message_index'),
        Index('ix_ai_conversation_memory_organization_id', 'organization_id'),
    )


class AIActionHistory(Base):
    """Store action history"""
    __tablename__ = 'ai_action_history'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)
    action_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    action_type = Column(String(50), nullable=False)
    preview_data = Column(JSONB, nullable=False)
    execution_data = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False)  # 'previewed', 'executed', 'failed'
    created_at = Column(DateTime, nullable=False, server_default=text('NOW()'))
    executed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_action_user_date', 'user_id', 'created_at'),
        Index('ix_ai_action_history_organization_id', 'organization_id'),
    )
