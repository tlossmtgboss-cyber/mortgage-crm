"""
Data Reconciliation Engine (DRE) Models

Models for incoming data processing, extraction, duplicate detection, and AI training.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.data_reconciliation import IncomingDataEvent, ExtractedData, BlockedSender
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship

from db import Base


class IncomingDataEvent(Base):
    __tablename__ = "incoming_data_events"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False)  # 'outlook', 'calendar', 'dropbox', etc.
    external_message_id = Column(String, index=True)  # Microsoft message ID, Gmail message ID, etc.
    raw_text = Column(Text)
    raw_html = Column(Text)
    subject = Column(String)
    sender = Column(String)
    recipients = Column(JSON)
    attachments = Column(JSON)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ExtractedData(Base):
    __tablename__ = "extracted_data"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("incoming_data_events.id"))
    category = Column(String)  # 'lead_update', 'loan_update', 'portfolio_update', etc.
    subcategory = Column(String)  # 'rate_lock', 'appraisal', 'title_clear', etc.
    fields = Column(JSON)  # {field_name: {value, confidence}}
    match_entity_type = Column(String)  # 'lead', 'loan', 'partner', etc.
    match_entity_id = Column(Integer)  # ID of matched entity
    match_confidence = Column(Float)
    ai_confidence = Column(Float)
    status = Column(String, default='pending_review')  # 'auto_applied', 'pending_review', 'rejected', 'error'
    applied_at = Column(DateTime)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship to incoming event
    incoming_event = relationship("IncomingDataEvent", foreign_keys=[event_id])


class BlockedSender(Base):
    __tablename__ = "blocked_senders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sender_email = Column(String, nullable=False)
    reason = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_blocked_senders_user_email', 'user_id', 'sender_email', unique=True),
    )


class DuplicatePair(Base):
    __tablename__ = "duplicate_pairs"
    id = Column(Integer, primary_key=True, index=True)
    lead_id_1 = Column(Integer, ForeignKey("leads.id"))
    lead_id_2 = Column(Integer, ForeignKey("leads.id"))
    similarity_score = Column(Float)  # 0.0 to 1.0
    status = Column(String, default='pending')  # 'pending', 'merged', 'dismissed', 'auto_merged'
    ai_suggestion = Column(JSON)  # AI's suggested merge choices
    user_decision = Column(JSON)  # User's actual choices
    principal_record_id = Column(Integer, ForeignKey("leads.id"))  # Which record was kept
    merged_at = Column(DateTime)
    merged_by = Column(Integer, ForeignKey("users.id"))
    user_id = Column(Integer, ForeignKey("users.id"))  # Owner
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MergeTrainingEvent(Base):
    __tablename__ = "merge_training_events"
    id = Column(Integer, primary_key=True, index=True)
    duplicate_pair_id = Column(Integer, ForeignKey("duplicate_pairs.id"))
    field_name = Column(String)
    ai_suggested_value = Column(String)  # Which value AI suggested
    ai_suggested_record = Column(Integer)  # 1 or 2 (which record AI chose)
    user_chosen_value = Column(String)  # What user actually chose
    user_chosen_record = Column(Integer)  # 1 or 2 (which record user chose)
    was_correct = Column(Boolean)  # Did AI guess correctly?
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MergeAIModel(Base):
    __tablename__ = "merge_ai_models"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    total_predictions = Column(Integer, default=0)
    correct_predictions = Column(Integer, default=0)
    consecutive_correct = Column(Integer, default=0)  # Track streak for auto-pilot
    accuracy = Column(Float, default=0.0)  # Overall accuracy
    autopilot_enabled = Column(Boolean, default=False)  # Enabled after 100 consecutive correct
    last_prediction_at = Column(DateTime)
    autopilot_enabled_at = Column(DateTime)  # When it reached 100 streak
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


__all__ = [
    "IncomingDataEvent",
    "ExtractedData",
    "BlockedSender",
    "DuplicatePair",
    "MergeTrainingEvent",
    "MergeAIModel",
]
