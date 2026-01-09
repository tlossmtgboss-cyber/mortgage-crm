"""
Widget Session Model
Tracks conversational sessions from site widget for lead qualification
"""

from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from database import Base


class WidgetSession(Base):
    """
    Widget Session - Tracks site widget conversations for lead qualification.
    Sessions can convert to LeadProfiles upon successful qualification.
    """
    __tablename__ = "widget_sessions"

    # Primary Key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Session State
    status = Column(String(20), default='active', index=True)
    # Statuses: active, qualified, converted, abandoned, expired

    current_intent = Column(String(100))  # Current position in flow
    qualification_progress = Column(String(10), default='0')  # Percentage complete

    # Conversation Data
    conversation_json = Column(JSONB, default=list)
    # Array of {role: 'user'|'assistant', content: str, timestamp: str}

    # Extracted Qualification Data
    extracted_data = Column(JSONB, default=dict)
    # {
    #   loan_purpose: str,
    #   first_time_buyer: bool,
    #   target_location: str,
    #   target_state: str,
    #   timeline: str,
    #   estimated_amount: int,
    #   credit_tier: str,
    #   estimated_credit_score: int,
    #   first_name: str,
    #   last_name: str,
    #   email: str,
    #   phone: str,
    #   preferred_contact: str,
    #   lead_temperature: str
    # }

    # Attribution
    page_url = Column(Text)  # Which page they started on
    utm_source = Column(String(100))
    utm_campaign = Column(String(100))
    utm_medium = Column(String(100))
    utm_term = Column(String(255))
    utm_content = Column(String(255))
    referrer = Column(Text)

    # Device/Browser Info
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(Text)
    device_type = Column(String(20))  # desktop, mobile, tablet
    browser = Column(String(50))
    os = Column(String(50))

    # Dialogflow Session Reference
    dialogflow_session_id = Column(String(255))

    # Conversion Tracking
    lead_id = Column(UUID(as_uuid=True), ForeignKey("lead_profiles.id"), nullable=True)
    converted_at = Column(DateTime)

    # LO Assignment (for routing before conversion)
    assigned_lo_id = Column(String(36))

    # Analytics
    message_count = Column(String(10), default='0')
    fallback_count = Column(String(10), default='0')
    total_duration_seconds = Column(String(10))  # Time from start to end
    avg_response_time_ms = Column(String(10))  # Average AI response time

    # Flags
    offered_human_handoff = Column(Boolean, default=False)
    human_handoff_requested = Column(Boolean, default=False)
    is_test = Column(Boolean, default=False)  # For internal testing

    def __repr__(self):
        return f"<WidgetSession {self.id} status={self.status}>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'status': self.status,
            'current_intent': self.current_intent,
            'qualification_progress': self.qualification_progress,
            'conversation_json': self.conversation_json,
            'extracted_data': self.extracted_data,
            'page_url': self.page_url,
            'utm_source': self.utm_source,
            'utm_campaign': self.utm_campaign,
            'lead_id': str(self.lead_id) if self.lead_id else None,
            'converted_at': self.converted_at.isoformat() if self.converted_at else None,
            'message_count': self.message_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def get_extracted_field(self, field: str, default=None):
        """Safely get a field from extracted_data"""
        if self.extracted_data and isinstance(self.extracted_data, dict):
            return self.extracted_data.get(field, default)
        return default

    def is_qualification_complete(self) -> bool:
        """Check if minimum required fields are captured"""
        required = ['loan_purpose', 'first_name', 'email', 'phone']
        if not self.extracted_data:
            return False
        return all(self.extracted_data.get(f) for f in required)

    def calculate_lead_score(self) -> int:
        """Calculate preliminary lead score from extracted data"""
        score = 50  # Base score

        if not self.extracted_data:
            return score

        # Timeline scoring
        timeline = self.extracted_data.get('timeline')
        timeline_scores = {
            'immediate': 25,
            '1_3_months': 20,
            '3_6_months': 15,
            '6_plus_months': 5,
            'exploring': 5
        }
        score += timeline_scores.get(timeline, 0)

        # Credit scoring
        credit_score = self.extracted_data.get('estimated_credit_score', 0)
        if credit_score >= 740:
            score += 15
        elif credit_score >= 700:
            score += 10
        elif credit_score >= 660:
            score += 5

        # Loan amount scoring
        amount = self.extracted_data.get('estimated_amount', 0)
        if amount >= 500000:
            score += 10
        elif amount >= 300000:
            score += 7
        elif amount >= 200000:
            score += 5

        return min(score, 100)  # Cap at 100
