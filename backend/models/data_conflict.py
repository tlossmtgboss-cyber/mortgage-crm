"""
Data Conflict Model
Stores conflicts that require manual review
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

from database import Base


class DataConflict(Base):
    """
    Data Conflict - Stores field conflicts that need manual resolution
    Appears in Reconciliation Center for user review
    """
    __tablename__ = "data_conflicts"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Profile reference
    profile_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    profile_type = Column(String(50), index=True)  # 'lead', 'active_loan', 'mum_client', 'team_member'

    # Email that triggered the conflict
    email_interaction_id = Column(UUID(as_uuid=True), ForeignKey('email_interactions.id'), index=True)

    # Conflict details
    field_name = Column(String(100), index=True)
    current_value = Column(Text)
    proposed_value = Column(Text)
    conflict_reason = Column(Text)  # Why this is a conflict

    # AI analysis
    confidence = Column(Integer)  # Confidence in proposed value
    suggested_resolution = Column(String(50))  # 'use_new', 'keep_old', 'merge', 'manual_review'
    ai_reasoning = Column(Text)  # Claude's reasoning

    # Resolution
    status = Column(String(50), default='pending', index=True)  # 'pending', 'resolved', 'ignored'
    resolution = Column(String(50))  # 'accepted_new', 'kept_old', 'merged', 'manual_entry'
    resolved_value = Column(Text)
    resolved_by_user_id = Column(Integer)
    resolved_at = Column(DateTime)

    # Additional context
    additional_context = Column(JSONB)  # Any extra info to help with resolution

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<DataConflict {self.profile_type}.{self.field_name}: {self.current_value} vs {self.proposed_value}>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'profile_id': str(self.profile_id),
            'profile_type': self.profile_type,
            'email_interaction_id': str(self.email_interaction_id) if self.email_interaction_id else None,
            'field_name': self.field_name,
            'current_value': self.current_value,
            'proposed_value': self.proposed_value,
            'conflict_reason': self.conflict_reason,
            'confidence': self.confidence,
            'suggested_resolution': self.suggested_resolution,
            'ai_reasoning': self.ai_reasoning,
            'status': self.status,
            'resolution': self.resolution,
            'resolved_value': self.resolved_value,
            'resolved_by_user_id': self.resolved_by_user_id,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'additional_context': self.additional_context,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
