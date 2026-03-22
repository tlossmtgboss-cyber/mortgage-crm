"""Database models for persistent SMS campaign and scheduled job state.

These models back the in-memory dicts in sms_campaign_manager.py and
sms_scheduler.py so that campaign/job state survives process restarts.

The in-memory dicts remain as a hot cache; the DB is the source of truth.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.sql import func

from db import Base


class SMSCampaignRecord(Base):
    __tablename__ = "sms_campaign_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(100), unique=True, nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=True)
    status = Column(String(50), default="active", index=True)  # active, paused, completed, cancelled
    campaign_config = Column(JSON, nullable=True)  # Store full campaign config as JSON
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ScheduledSMSJobRecord(Base):
    __tablename__ = "scheduled_sms_job_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), unique=True, nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    phone_number = Column(String(20), nullable=True)
    message = Column(Text, nullable=True)
    status = Column(String(50), default="pending", index=True)  # pending, sent, failed, cancelled
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    job_config = Column(JSON, nullable=True)  # Store full job config as JSON
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    executed_at = Column(DateTime(timezone=True), nullable=True)
