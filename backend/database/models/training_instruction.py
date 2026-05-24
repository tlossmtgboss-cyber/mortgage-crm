"""
AI Training Instruction Model

Stores user-submitted training instructions that teach AI agents how to handle
specific scenarios. Each instruction has a scope (task_type, global, borrower)
and tracks how many times it has influenced agent output.

Usage:
    from database.models.training_instruction import AITrainingInstruction
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, ForeignKey, JSON, Boolean, Index,
)
from sqlalchemy.dialects.postgresql import UUID

from db import Base


class AITrainingInstruction(Base):
    """
    A training instruction submitted by a user to influence AI behavior.

    Scopes:
        - task_type: applies to all tasks of the same type (e.g. "workflow_day1_text")
        - global: applies to all AI interactions for this user/org
        - borrower: applies only to a specific borrower context
    """
    __tablename__ = 'ai_training_instructions'
    __table_args__ = (
        Index("ix_training_instr_user_org", "user_id", "organization_id"),
        Index("ix_training_instr_task_type", "task_type"),
        Index("ix_training_instr_scope", "scope"),
        Index("ix_training_instr_active", "is_active"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    organization_id = Column(Integer, index=True)
    instruction_text = Column(Text, nullable=False)
    task_type = Column(String(100), index=True)  # e.g. "workflow_day1_text", "sms_rate_inquiry"
    task_context = Column(JSON)  # borrower_name, stage, etc.
    scope = Column(String(50), default='task_type')  # 'task_type', 'global', 'borrower'
    is_active = Column(Boolean, default=True)
    applied_count = Column(Integer, default=0)  # how many times this instruction influenced output
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
