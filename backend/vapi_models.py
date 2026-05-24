"""
Vapi AI Receptionist - Database Models
Handles call records, transcriptions, and lead capture
"""
import logging
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float, Boolean, ForeignKey, text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base

logger = logging.getLogger(__name__)


class VapiCall(Base):
    """Store Vapi call records"""
    __tablename__ = "vapi_calls"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    stereo_recording_url = Column(String(512), nullable=True)
    recording_status = Column(String(50), default='none')  # none, available, downloaded, transcribed
    transcript_status = Column(String(50), default='none')  # none, pending, completed, failed

    # Analysis
    sentiment = Column(String(50))  # positive, neutral, negative
    intent = Column(String(100))  # appointment, inquiry, complaint, etc.
    language = Column(String(10), default="en")

    # Metadata
    call_metadata = Column(JSON)
    vapi_raw_data = Column(JSON)  # Store complete Vapi response

    # CRM Integration
    lead_id = Column(Integer, ForeignKey('leads.id'), nullable=True)
    loan_officer_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)

    # Recording persistence
    recording_local_path = Column(String(512), nullable=True)
    recording_downloaded_at = Column(DateTime(timezone=True), nullable=True)

    # Call Intelligence
    ci_processed = Column(Boolean, default=False)
    ci_extractions_count = Column(Integer, default=0)
    ci_tasks_created = Column(Integer, default=0)

    # Relationships
    notes = relationship("VapiCallNote", back_populates="call", cascade="all, delete-orphan")

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class VapiCallNote(Base):
    """Action items and notes extracted from calls"""
    __tablename__ = "vapi_call_notes"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    call_id = Column(Integer, ForeignKey('vapi_calls.id'), nullable=False)

    note_type = Column(String(50))  # action_item, follow_up, information, etc.
    content = Column(Text, nullable=False)
    priority = Column(String(20))  # high, medium, low
    completed = Column(Boolean, default=False)

    assigned_to = Column(Integer, ForeignKey('users.id'), nullable=True)
    due_date = Column(DateTime, nullable=True)

    call = relationship("VapiCall", back_populates="notes")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class VapiAssistant(Base):
    """Vapi Assistant Configurations"""
    __tablename__ = "vapi_assistants"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class VapiPhoneNumber(Base):
    """Vapi Phone Numbers"""
    __tablename__ = "vapi_phone_numbers"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    vapi_number_id = Column(String(255), unique=True, index=True)

    phone_number = Column(String(20), unique=True, nullable=False)
    name = Column(String(255))

    # Assignment
    assistant_id = Column(Integer, ForeignKey('vapi_assistants.id'))
    department = Column(String(100))  # sales, support, scheduling, etc.

    # Settings
    is_active = Column(Boolean, default=True)
    config = Column(JSON)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CallRoutingLog(Base):
    """Track call routing decisions and transfers"""
    __tablename__ = "call_routing_log"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    call_id = Column(Integer, ForeignKey('vapi_calls.id'), nullable=True)
    vapi_call_id = Column(String(255), index=True)

    # Routing Decision
    routing_decision = Column(String(100))  # transfer_to_pa, transfer_to_lo, etc.
    caller_type = Column(String(50))  # new_lead, active_loan, existing_client

    # Transfer Details
    routed_to_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    routed_to_role = Column(String(50))  # production_assistant, loan_officer, processor
    routed_to_phone = Column(String(20))

    # Whisper Message
    whisper_message = Column(Text)

    # Transfer Status
    transfer_successful = Column(Boolean, default=False)
    transfer_error = Column(Text)

    # Context
    caller_phone = Column(String(20))
    caller_name = Column(String(255))
    call_reason = Column(Text)
    urgency_level = Column(String(20))  # low, medium, high, urgent

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class StaffAvailability(Base):
    """Track staff availability for call routing"""
    __tablename__ = "staff_availability"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)

    # Availability Status
    status = Column(String(50), default='available')  # available, busy, offline, dnd
    available_for_calls = Column(Boolean, default=True)

    # Phone Numbers
    primary_phone = Column(String(20))
    backup_phone = Column(String(20))

    # Role Information
    role = Column(String(50))  # production_assistant, loan_officer, processor
    department = Column(String(100))

    # Working Hours
    working_hours = Column(JSON)  # {monday: {start: '09:00', end: '17:00'}, ...}

    # Current Status
    current_call_count = Column(Integer, default=0)
    max_concurrent_calls = Column(Integer, default=3)

    # Metadata
    out_of_office = Column(Boolean, default=False)
    out_of_office_message = Column(Text)
    auto_response_enabled = Column(Boolean, default=False)

    # Timestamps
    last_call_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


def ensure_vapi_ci_columns(db) -> None:
    """Add Call Intelligence and LO tracking columns to vapi_calls if they don't exist.

    Safe to call on every startup — uses IF NOT EXISTS.
    """
    _cols = [
        ("ci_processed", "BOOLEAN DEFAULT FALSE"),
        ("ci_extractions_count", "INTEGER DEFAULT 0"),
        ("ci_tasks_created", "INTEGER DEFAULT 0"),
        ("loan_officer_id", "INTEGER REFERENCES users(id)"),
        ("recording_local_path", "VARCHAR(512)"),
        ("recording_downloaded_at", "TIMESTAMPTZ"),
    ]
    for col_name, col_def in _cols:
        try:
            db.execute(text(
                f"ALTER TABLE vapi_calls ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
            ))
        except Exception as e:
            logger.warning("Could not add vapi_calls.%s: %s", col_name, e)
    try:
        db.commit()
    except Exception:
        db.rollback()


class CallTransferConfig(Base):
    """Configuration for call routing rules"""
    __tablename__ = "call_transfer_config"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Transfer Rules
    caller_type = Column(String(50))  # new_lead, active_loan, etc.
    default_route_to_role = Column(String(50))  # production_assistant, loan_officer

    # Conditions
    routing_conditions = Column(JSON)  # Additional routing logic

    # Priority
    priority_order = Column(Integer, default=0)

    # Active Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
