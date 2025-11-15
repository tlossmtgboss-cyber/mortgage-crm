"""
Vapi AI Receptionist - Database Models
Handles call records, transcriptions, and lead capture
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class VapiCall(Base):
    """Store Vapi call records"""
    __tablename__ = "vapi_calls"

    id = Column(Integer, primary_key=True, index=True)
    vapi_call_id = Column(String(255), unique=True, index=True, nullable=False)

    # Call Details
    phone_number = Column(String(20))
    caller_name = Column(String(255))
    direction = Column(String(20))  # inbound/outbound
    status = Column(String(50))  # ringing, in-progress, completed, failed, etc.

    # Timing
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    duration = Column(Integer)  # seconds

    # Call Data
    transcript = Column(Text)
    summary = Column(Text)
    recording_url = Column(String(512))

    # Analysis
    sentiment = Column(String(50))  # positive, neutral, negative
    intent = Column(String(100))  # appointment, inquiry, complaint, etc.
    language = Column(String(10), default="en")

    # Metadata
    call_metadata = Column(JSON)
    vapi_raw_data = Column(JSON)  # Store complete Vapi response

    # CRM Integration
    lead_id = Column(Integer, ForeignKey('leads.id'), nullable=True)

    # Relationships
    notes = relationship("VapiCallNote", back_populates="call", cascade="all, delete-orphan")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VapiCallNote(Base):
    """Action items and notes extracted from calls"""
    __tablename__ = "vapi_call_notes"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey('vapi_calls.id'), nullable=False)

    note_type = Column(String(50))  # action_item, follow_up, information, etc.
    content = Column(Text, nullable=False)
    priority = Column(String(20))  # high, medium, low
    completed = Column(Boolean, default=False)

    assigned_to = Column(Integer, ForeignKey('users.id'), nullable=True)
    due_date = Column(DateTime, nullable=True)

    call = relationship("VapiCall", back_populates="notes")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VapiAssistant(Base):
    """Vapi Assistant Configurations"""
    __tablename__ = "vapi_assistants"

    id = Column(Integer, primary_key=True, index=True)
    vapi_assistant_id = Column(String(255), unique=True, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Configuration
    voice_id = Column(String(100))
    language = Column(String(10), default="en")
    first_message = Column(Text)
    system_prompt = Column(Text)

    # Settings
    is_active = Column(Boolean, default=True)
    config = Column(JSON)  # Full Vapi assistant config

    # Usage tracking
    total_calls = Column(Integer, default=0)
    total_minutes = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VapiPhoneNumber(Base):
    """Vapi Phone Numbers"""
    __tablename__ = "vapi_phone_numbers"

    id = Column(Integer, primary_key=True, index=True)
    vapi_number_id = Column(String(255), unique=True, index=True)

    phone_number = Column(String(20), unique=True, nullable=False)
    name = Column(String(255))

    # Assignment
    assistant_id = Column(Integer, ForeignKey('vapi_assistants.id'))
    department = Column(String(100))  # sales, support, scheduling, etc.

    # Settings
    is_active = Column(Boolean, default=True)
    config = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
