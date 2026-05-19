"""
SMS AI Auto-Response Task Models

Models for AI-assisted SMS response with confidence scoring,
feedback learning, and auto-response capability.

Usage:
    from database.models.sms_task import SMSTask, SMSResponsePattern, SMSAIConfidence, SMSAIAuditLog
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, JSON, Index, UniqueConstraint, text, Numeric
)

from db import Base


class SMSTask(Base):
    __tablename__ = "sms_tasks"
    __table_args__ = (
        Index('ix_sms_tasks_org_status', 'organization_id', 'status'),
        Index('ix_sms_tasks_org_assigned_user', 'organization_id', 'assigned_user_id'),
        Index('ix_sms_tasks_assigned_user_status', 'assigned_user_id', 'status'),
        Index('ix_sms_tasks_phone_number', 'phone_number'),
        Index('ix_sms_tasks_lead_id', 'lead_id'),
        Index(
            'ix_sms_tasks_pending',
            'organization_id', 'created_at',
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    assigned_user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    phone_number = Column(String, nullable=False)
    contact_name = Column(String, nullable=True)
    inbound_message = Column(Text, nullable=False)
    inbound_message_id = Column(String, nullable=True)
    inbound_received_at = Column(DateTime(timezone=True), nullable=False)

    status = Column(String, default="pending")
    priority = Column(String, default="normal")
    category = Column(String, nullable=True)

    ai_recommendation = Column(Text, nullable=True)
    ai_confidence = Column(Float, default=0)
    ai_model_version = Column(String, nullable=True)
    ai_reasoning = Column(Text, nullable=True)
    ai_generated_at = Column(DateTime(timezone=True), nullable=True)

    response_text = Column(Text, nullable=True)
    response_source = Column(String, nullable=True)
    response_sent_at = Column(DateTime(timezone=True), nullable=True)
    responded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user_feedback = Column(String, nullable=True)
    edit_distance = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SMSResponsePattern(Base):
    __tablename__ = "sms_response_patterns"
    __table_args__ = (
        Index('ix_sms_response_patterns_org_category', 'organization_id', 'category'),
        Index('ix_sms_response_patterns_success_rate', 'organization_id', 'success_rate'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    category = Column(String, nullable=False)
    message_keywords = Column(JSON)
    response_template = Column(Text, nullable=False)
    times_used = Column(Integer, default=1)
    times_accepted = Column(Integer, default=0)
    times_edited = Column(Integer, default=0)
    times_rejected = Column(Integer, default=0)
    success_rate = Column(Numeric(8, 5), default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SMSAIConfidence(Base):
    __tablename__ = "sms_ai_confidence"
    __table_args__ = (
        UniqueConstraint('organization_id', 'user_id', 'category', name='uq_sms_ai_confidence_org_user_cat'),
        Index('ix_sms_ai_confidence_org_id', 'organization_id'),
        Index('ix_sms_ai_confidence_user_id', 'user_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    category = Column(String, nullable=False)
    total_recommendations = Column(Integer, default=0)
    accepted_count = Column(Integer, default=0)
    edited_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=20.0)
    auto_respond_enabled = Column(Boolean, default=False)
    auto_respond_threshold = Column(Float, default=80.0)
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SMSAIAuditLog(Base):
    __tablename__ = "sms_ai_audit_log"
    __table_args__ = (
        Index('ix_sms_ai_audit_org_id', 'organization_id'),
        Index('ix_sms_ai_audit_task_id', 'task_id'),
        Index('ix_sms_ai_audit_action', 'organization_id', 'action'),
        Index('ix_sms_ai_audit_created', 'organization_id', 'created_at'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("sms_tasks.id"), nullable=True)
    action = Column(String, nullable=False)
    details = Column(JSON, default=dict)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


__all__ = [
    "SMSTask",
    "SMSResponsePattern",
    "SMSAIConfidence",
    "SMSAIAuditLog",
]
