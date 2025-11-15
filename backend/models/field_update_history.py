"""
Field Update History Model
Tracks all field-level changes for audit trail and conflict resolution
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from database import Base


class FieldUpdateHistory(Base):
    """
    Field Update History - Audit trail for all profile field changes
    Enables rollback and conflict resolution
    """
    __tablename__ = "field_update_history"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Profile reference (polymorphic - can point to any profile type)
    profile_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    profile_type = Column(String(50), index=True)  # 'lead', 'active_loan', 'mum_client', 'team_member'

    # Field details
    field_name = Column(String(100), index=True, nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)

    # Source of update
    update_source = Column(String(50))  # 'manual_entry', 'parsed_email', 'import', 'api', 'calculated'
    email_interaction_id = Column(UUID(as_uuid=True), ForeignKey('email_interactions.id'), index=True)

    # Confidence and validation
    confidence = Column(Integer)  # 0-100 if from AI parsing
    was_validated = Column(String(20))  # 'auto', 'manual', 'none'

    # User who made the change (if manual)
    user_id = Column(Integer, index=True)

    # Timestamp
    updated_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<FieldUpdateHistory {self.profile_type}.{self.field_name}: {self.old_value} → {self.new_value}>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'profile_id': str(self.profile_id),
            'profile_type': self.profile_type,
            'field_name': self.field_name,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'update_source': self.update_source,
            'email_interaction_id': str(self.email_interaction_id) if self.email_interaction_id else None,
            'confidence': self.confidence,
            'was_validated': self.was_validated,
            'user_id': self.user_id,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
