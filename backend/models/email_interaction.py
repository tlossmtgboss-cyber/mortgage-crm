"""
Email Interaction Model
Comprehensive email tracking with parsed data and AI analysis
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, ARRAY, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from database import Base


class EmailInteraction(Base):
    """
    Email Interaction - Stores complete email data with AI parsing results
    Links emails to any of the 4 profile types (polymorphic relationship)
    """
    __tablename__ = "email_interactions"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # ==================== POLYMORPHIC PROFILE REFERENCES ====================
    # An email can relate to one of these profile types
    lead_profile_id = Column(UUID(as_uuid=True), ForeignKey('lead_profiles.id'), index=True)
    active_loan_id = Column(UUID(as_uuid=True), ForeignKey('active_loan_profiles.id'), index=True)
    mum_client_id = Column(UUID(as_uuid=True), ForeignKey('mum_client_profiles.id'), index=True)
    team_member_id = Column(UUID(as_uuid=True), ForeignKey('team_member_profiles.id'), index=True)

    profile_type = Column(String(50))  # 'lead', 'active_loan', 'mum_client', 'team_member'

    # ==================== EMAIL IDENTIFIERS ====================
    email_id = Column(String(255), unique=True, index=True)  # Microsoft Graph message ID
    thread_id = Column(String(255), index=True)
    conversation_id = Column(String(255), index=True)

    # ==================== EMAIL DETAILS ====================
    subject = Column(Text)
    from_email = Column(String(255), index=True)
    to_emails = Column(ARRAY(String))
    cc_emails = Column(ARRAY(String))
    bcc_emails = Column(ARRAY(String))
    sent_date = Column(DateTime)
    received_date = Column(DateTime, index=True)

    # ==================== EMAIL CONTENT ====================
    body_text = Column(Text)  # Plain text version
    body_html = Column(Text)  # HTML version
    attachments = Column(JSONB)  # Array of attachment metadata

    # ==================== PARSED DATA (from Claude) ====================
    parsed_data = Column(JSONB)  # Complete Claude response
    extracted_fields = Column(JSONB)  # Flat dict of extracted fields
    confidence_scores = Column(JSONB)  # Confidence for each field
    milestone_triggers = Column(JSONB)  # Array of detected milestones
    field_updates = Column(JSONB)  # Array of field update recommendations
    conflicts = Column(JSONB)  # Array of conflicts needing review

    # ==================== AI ANALYSIS ====================
    email_summary = Column(Text)  # Brief summary of email
    sentiment = Column(String(20))  # 'positive', 'neutral', 'negative', 'urgent'
    urgency_score = Column(Integer)  # 0-100
    suggested_actions = Column(ARRAY(String))  # Recommended actions
    next_best_action = Column(Text)  # Primary recommendation

    # ==================== PROCESSING METADATA ====================
    processed_at = Column(DateTime, default=datetime.utcnow, index=True)
    parser_version = Column(String(20))  # Claude parser version
    parser_model = Column(String(50))  # Model used (e.g., "claude-sonnet-4-20250514")
    sync_status = Column(String(50), default='pending')  # 'pending', 'processed', 'applied', 'conflict', 'error'
    processing_time_ms = Column(Integer)  # Time to parse
    overall_confidence = Column(Integer)  # Average confidence across all fields
    field_count = Column(Integer)  # Number of fields extracted

    # User who owns this email
    user_id = Column(Integer, index=True)  # FK to users table in main.py

    # ==================== METADATA ====================
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Error tracking
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # ==================== RELATIONSHIPS ====================
    lead_profile = relationship("LeadProfile", back_populates="email_interactions")
    active_loan = relationship("ActiveLoanProfile", back_populates="email_interactions")
    mum_client = relationship("MUMClientProfile", back_populates="email_interactions")
    team_member = relationship("TeamMemberProfile", back_populates="email_interactions")

    def __repr__(self):
        return f"<EmailInteraction {self.subject[:50]} from {self.from_email}>"

    def get_profile_id(self):
        """Get the associated profile ID regardless of type"""
        if self.lead_profile_id:
            return self.lead_profile_id
        elif self.active_loan_id:
            return self.active_loan_id
        elif self.mum_client_id:
            return self.mum_client_id
        elif self.team_member_id:
            return self.team_member_id
        return None

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'profile_type': self.profile_type,
            'profile_id': str(self.get_profile_id()) if self.get_profile_id() else None,
            'email_id': self.email_id,
            'subject': self.subject,
            'from_email': self.from_email,
            'to_emails': self.to_emails,
            'sent_date': self.sent_date.isoformat() if self.sent_date else None,
            'received_date': self.received_date.isoformat() if self.received_date else None,
            'email_summary': self.email_summary,
            'sentiment': self.sentiment,
            'urgency_score': self.urgency_score,
            'suggested_actions': self.suggested_actions,
            'next_best_action': self.next_best_action,
            'extracted_fields': self.extracted_fields,
            'confidence_scores': self.confidence_scores,
            'milestone_triggers': self.milestone_triggers,
            'conflicts': self.conflicts,
            'sync_status': self.sync_status,
            'processing_time_ms': self.processing_time_ms,
            'overall_confidence': self.overall_confidence,
            'field_count': self.field_count,
            'parser_model': self.parser_model,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
