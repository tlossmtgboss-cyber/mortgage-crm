"""
Chat State Machine - Database Models

This module defines SQLAlchemy models for the phase-based chat state machine system:
- ChatSession: Session tracking with phase state, intent scoring, and CTA management
- ChatMessage: Individual messages within a session
- CallRequest: Click-to-call and callback request tracking

The state machine progresses through 4 phases:
1. Reassure & Orient - Create emotional safety
2. Educate with Tradeoffs - Demonstrate expertise
3. Personalize via Micro-Commitments - Earn permission
4. Earned Next Step - Present ONE logical CTA
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, ForeignKey,
    DateTime, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime, timezone
import uuid
import enum

from database import Base


# =============================================================================
# ENUMS
# =============================================================================

class ChatPhase(int, enum.Enum):
    """Chat conversation phases - state machine states"""
    REASSURE_ORIENT = 1      # Phase 1: Create emotional safety
    EDUCATE_TRADEOFFS = 2    # Phase 2: Demonstrate expertise
    MICRO_COMMITMENTS = 3    # Phase 3: Earn permission
    EARNED_NEXT_STEP = 4     # Phase 4: Present ONE logical CTA


class UrgencyLevel(str, enum.Enum):
    """Borrower urgency classification"""
    LOW = "low"       # No specific timeline
    MEDIUM = "medium" # Exploring options, 3-6 months
    HIGH = "high"     # Ready to act, within 30 days


class CTAType(str, enum.Enum):
    """Call-to-action types"""
    NONE = "none"
    CALL_NOW = "call_now"
    SCHEDULE = "schedule"
    APPLICATION = "application"


class MessageRole(str, enum.Enum):
    """Message sender role"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class CallStatus(str, enum.Enum):
    """Call request status"""
    PENDING = "pending"
    CONNECTING = "connecting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NO_ANSWER = "no_answer"


class CallDirection(str, enum.Enum):
    """Call direction"""
    INBOUND = "inbound"     # User initiated click-to-call
    OUTBOUND = "outbound"   # Scheduled callback
    TRANSFER = "transfer"   # AI-to-human handoff


# =============================================================================
# INTENT SIGNAL TYPES
# =============================================================================

# These are the intent signals we detect from user messages
INTENT_SIGNALS = [
    "property",           # Property type interest (single family, condo, etc.)
    "price",              # Price range mentioned
    "timeline",           # When they want to buy/refinance
    "down_payment",       # Down payment amount/percentage
    "loan_type",          # Loan program interest (FHA, VA, conventional)
    "credit_band",        # Credit score range
    "goal",               # Primary goal (lower payment, cash out, etc.)
    "urgency",            # Explicit urgency indicators
    "recommendation_request",  # Asking for advice
]

# Weights for intent score calculation
INTENT_WEIGHTS = {
    "property": 10,
    "price": 15,
    "timeline": 20,
    "down_payment": 15,
    "loan_type": 10,
    "credit_band": 10,
    "goal": 10,
    "urgency": 5,
    "recommendation_request": 5,
}


# =============================================================================
# MODELS
# =============================================================================

class ChatSession(Base):
    """
    Chat session with state machine tracking.

    Tracks the borrower's journey through the 4-phase conversation model,
    including intent signals, scoring, and CTA interactions.
    """
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index('ix_chat_sessions_visitor_id', 'visitor_id'),
        Index('ix_chat_sessions_user_id', 'user_id'),
        Index('ix_chat_sessions_microsite_id', 'microsite_id'),
        Index('ix_chat_sessions_active', 'is_active'),
        CheckConstraint('current_phase BETWEEN 1 AND 4', name='ck_chat_sessions_phase'),
        CheckConstraint('intent_score BETWEEN 0 AND 100', name='ck_chat_sessions_intent_score'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Visitor/User identification
    visitor_id = Column(String(255), nullable=False, index=True)  # Browser fingerprint or cookie ID
    user_id = Column(UUID(as_uuid=True), nullable=True)  # Authenticated user if logged in

    # Microsite context
    microsite_id = Column(Integer, nullable=True, index=True)  # Which LO's site
    loan_officer_id = Column(Integer, nullable=True)  # Assigned LO for this session

    # State machine tracking
    current_phase = Column(Integer, nullable=False, default=1)  # 1-4
    turn_count = Column(Integer, nullable=False, default=0)  # Conversation turns

    # Intent scoring
    intent_score = Column(Integer, nullable=False, default=0)  # 0-100
    urgency = Column(String(10), nullable=False, default='low')  # low/medium/high

    # Intent signals (JSONB array of detected signals)
    # Format: [{"signal": "timeline", "value": "3 months", "confidence": 0.9, "turn": 3}, ...]
    intent_signals = Column(JSONB, nullable=False, default=list)

    # CTA tracking
    cta_offered = Column(String(20), nullable=True)  # none/call_now/schedule/application
    cta_declined_count = Column(Integer, nullable=False, default=0)
    cta_accepted = Column(Boolean, default=False)
    cta_accepted_at = Column(DateTime(timezone=True), nullable=True)

    # Session metadata
    is_active = Column(Boolean, nullable=False, default=True)
    source_url = Column(String(500), nullable=True)  # Page where chat started
    referrer = Column(String(500), nullable=True)
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length

    # Contact info collected during chat
    contact_name = Column(String(200), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(20), nullable=True)

    # Lead conversion tracking
    converted_to_lead = Column(Boolean, default=False)
    lead_id = Column(Integer, nullable=True)  # Link to leads table if converted

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")
    call_requests = relationship("CallRequest", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ChatSession {self.id} phase={self.current_phase} score={self.intent_score}>"

    def add_intent_signal(self, signal: str, value: str, confidence: float = 1.0):
        """Add a detected intent signal and recalculate score"""
        if self.intent_signals is None:
            self.intent_signals = []

        # Check if signal already exists
        existing = next((s for s in self.intent_signals if s.get('signal') == signal), None)

        new_signal = {
            "signal": signal,
            "value": value,
            "confidence": confidence,
            "turn": self.turn_count,
            "detected_at": datetime.now(timezone.utc).isoformat()
        }

        if existing:
            # Update existing signal if new confidence is higher
            if confidence > existing.get('confidence', 0):
                self.intent_signals = [s if s.get('signal') != signal else new_signal for s in self.intent_signals]
        else:
            self.intent_signals = self.intent_signals + [new_signal]

        # Recalculate intent score
        self._calculate_intent_score()

    def _calculate_intent_score(self):
        """Calculate intent score based on detected signals"""
        if not self.intent_signals:
            self.intent_score = 0
            return

        total_score = 0
        for signal in self.intent_signals:
            signal_type = signal.get('signal', '')
            confidence = signal.get('confidence', 1.0)
            weight = INTENT_WEIGHTS.get(signal_type, 0)
            total_score += int(weight * confidence)

        self.intent_score = min(100, total_score)

        # Update urgency based on score
        if self.intent_score >= 70:
            self.urgency = UrgencyLevel.HIGH.value
        elif self.intent_score >= 40:
            self.urgency = UrgencyLevel.MEDIUM.value
        else:
            self.urgency = UrgencyLevel.LOW.value

    def should_advance_phase(self) -> bool:
        """Determine if session should advance to next phase"""
        if self.current_phase >= 4:
            return False

        # Phase 1 -> 2: After 2+ turns and user has engaged
        if self.current_phase == 1:
            return self.turn_count >= 2

        # Phase 2 -> 3: After demonstrating value (4+ turns or intent signal detected)
        if self.current_phase == 2:
            return self.turn_count >= 4 or len(self.intent_signals or []) >= 2

        # Phase 3 -> 4: After collecting info (6+ turns or high intent score)
        if self.current_phase == 3:
            return self.turn_count >= 6 or self.intent_score >= 50

        return False

    def advance_phase(self):
        """Advance to next phase if conditions met"""
        if self.should_advance_phase():
            self.current_phase = min(4, self.current_phase + 1)

    def get_cta_recommendation(self) -> str:
        """Get recommended CTA based on current state"""
        # Don't offer CTA if not in phase 4
        if self.current_phase < 4:
            return CTAType.NONE.value

        # Don't re-offer declined CTA too quickly
        if self.cta_declined_count >= 2:
            return CTAType.NONE.value

        # High urgency -> call now
        if self.urgency == UrgencyLevel.HIGH.value:
            return CTAType.CALL_NOW.value

        # Medium urgency with good intent -> schedule
        if self.urgency == UrgencyLevel.MEDIUM.value and self.intent_score >= 40:
            return CTAType.SCHEDULE.value

        # Has contact info -> application
        if self.contact_email or self.contact_phone:
            return CTAType.APPLICATION.value

        return CTAType.SCHEDULE.value

    def to_dict(self, include_messages=False, include_calls=False):
        """Convert to dictionary for API responses"""
        result = {
            "id": str(self.id),
            "visitorId": self.visitor_id,
            "userId": str(self.user_id) if self.user_id else None,
            "micrositeId": self.microsite_id,
            "loanOfficerId": self.loan_officer_id,
            "currentPhase": self.current_phase,
            "turnCount": self.turn_count,
            "intentScore": self.intent_score,
            "urgency": self.urgency,
            "intentSignals": self.intent_signals or [],
            "ctaOffered": self.cta_offered,
            "ctaDeclinedCount": self.cta_declined_count,
            "ctaAccepted": self.cta_accepted,
            "ctaAcceptedAt": self.cta_accepted_at.isoformat() if self.cta_accepted_at else None,
            "isActive": self.is_active,
            "sourceUrl": self.source_url,
            "contactName": self.contact_name,
            "contactEmail": self.contact_email,
            "contactPhone": self.contact_phone,
            "convertedToLead": self.converted_to_lead,
            "leadId": self.lead_id,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "lastMessageAt": self.last_message_at.isoformat() if self.last_message_at else None,
            "endedAt": self.ended_at.isoformat() if self.ended_at else None,
        }

        if include_messages and self.messages:
            result["messages"] = [msg.to_dict() for msg in self.messages]

        if include_calls and self.call_requests:
            result["callRequests"] = [call.to_dict() for call in self.call_requests]

        return result


class ChatMessage(Base):
    """
    Individual chat message within a session.

    Stores both user and assistant messages with metadata for
    intent analysis and conversation flow tracking.
    """
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index('ix_chat_messages_session_id', 'session_id'),
        Index('ix_chat_messages_created_at', 'created_at'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session link
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)

    # Message content
    role = Column(String(20), nullable=False)  # user/assistant/system
    content = Column(Text, nullable=False)

    # Turn tracking
    turn_number = Column(Integer, nullable=False, default=0)

    # Phase at time of message
    phase_at_message = Column(Integer, nullable=True)

    # Intent analysis results (for user messages)
    detected_intents = Column(JSONB, nullable=True)  # Signals detected in this message
    sentiment = Column(String(20), nullable=True)  # positive/neutral/negative/anxious

    # CTA interaction (for assistant messages)
    cta_presented = Column(String(20), nullable=True)  # Which CTA was shown
    cta_response = Column(String(20), nullable=True)   # accepted/declined/ignored

    # AI model info (for assistant messages)
    model_used = Column(String(50), nullable=True)  # e.g., "claude-3-sonnet"
    tokens_used = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage {self.id} role={self.role} turn={self.turn_number}>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "sessionId": str(self.session_id),
            "role": self.role,
            "content": self.content,
            "turnNumber": self.turn_number,
            "phaseAtMessage": self.phase_at_message,
            "detectedIntents": self.detected_intents,
            "sentiment": self.sentiment,
            "ctaPresented": self.cta_presented,
            "ctaResponse": self.cta_response,
            "modelUsed": self.model_used,
            "tokensUsed": self.tokens_used,
            "responseTimeMs": self.response_time_ms,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class CallRequest(Base):
    """
    Call request tracking for click-to-call and callbacks.

    Integrates with Telnyx for:
    - Click-to-call: Immediate connection with whisper + bridge
    - Scheduled callbacks: LO calls borrower at requested time
    - AI handoff: Transfer from chat to live call
    """
    __tablename__ = "call_requests"
    __table_args__ = (
        Index('ix_call_requests_session_id', 'session_id'),
        Index('ix_call_requests_status', 'status'),
        Index('ix_call_requests_loan_officer_id', 'loan_officer_id'),
        Index('ix_call_requests_scheduled_at', 'scheduled_at'),
        {'extend_existing': True}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session link
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)

    # Loan officer assignment
    loan_officer_id = Column(Integer, nullable=True)  # Links to users table

    # Call type and direction
    direction = Column(String(20), nullable=False, default='inbound')  # inbound/outbound/transfer

    # Contact info
    caller_phone = Column(String(20), nullable=False)  # Borrower's phone
    caller_name = Column(String(200), nullable=True)
    destination_phone = Column(String(20), nullable=True)  # LO's phone (for outbound)

    # Scheduling
    is_immediate = Column(Boolean, nullable=False, default=True)  # Click-to-call vs scheduled
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    preferred_time_slot = Column(String(50), nullable=True)  # "morning", "afternoon", etc.

    # Call status tracking
    status = Column(String(20), nullable=False, default='pending')

    # Telephony provider integration
    twilio_call_sid = Column(String(50), nullable=True)  # Legacy column name, stores Telnyx call control ID
    twilio_conference_sid = Column(String(50), nullable=True)  # Legacy column name, stores Telnyx conference ID

    # Call metadata
    whisper_message = Column(Text, nullable=True)  # Context spoken to LO before connecting
    call_duration_seconds = Column(Integer, nullable=True)
    recording_url = Column(String(500), nullable=True)
    recording_sid = Column(String(50), nullable=True)

    # Intent context passed to LO
    intent_summary = Column(Text, nullable=True)  # Summary of chat conversation
    intent_signals_snapshot = Column(JSONB, nullable=True)  # Signals at time of call

    # Outcome tracking
    outcome = Column(String(50), nullable=True)  # "scheduled_appointment", "requested_callback", etc.
    outcome_notes = Column(Text, nullable=True)

    # Lead conversion
    converted_to_lead = Column(Boolean, default=False)
    lead_id = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    initiated_at = Column(DateTime(timezone=True), nullable=True)  # When call actually started
    connected_at = Column(DateTime(timezone=True), nullable=True)  # When parties connected
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    session = relationship("ChatSession", back_populates="call_requests")

    def __repr__(self):
        return f"<CallRequest {self.id} status={self.status} direction={self.direction}>"

    def generate_whisper_message(self) -> str:
        """Generate whisper message for LO based on session context"""
        session = self.session
        if not session:
            return "Incoming call from website visitor."

        parts = ["Incoming lead from chat."]

        # Add intent score
        if session.intent_score >= 70:
            parts.append("High intent buyer.")
        elif session.intent_score >= 40:
            parts.append("Moderate interest.")

        # Add key signals
        signals = session.intent_signals or []
        timeline_signal = next((s for s in signals if s.get('signal') == 'timeline'), None)
        if timeline_signal:
            parts.append(f"Timeline: {timeline_signal.get('value')}.")

        price_signal = next((s for s in signals if s.get('signal') == 'price'), None)
        if price_signal:
            parts.append(f"Price range: {price_signal.get('value')}.")

        loan_type_signal = next((s for s in signals if s.get('signal') == 'loan_type'), None)
        if loan_type_signal:
            parts.append(f"Interested in {loan_type_signal.get('value')}.")

        # Add name if known
        if session.contact_name:
            parts.append(f"Name: {session.contact_name}.")

        return " ".join(parts)

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "sessionId": str(self.session_id),
            "loanOfficerId": self.loan_officer_id,
            "direction": self.direction,
            "callerPhone": self.caller_phone,
            "callerName": self.caller_name,
            "destinationPhone": self.destination_phone,
            "isImmediate": self.is_immediate,
            "scheduledAt": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "preferredTimeSlot": self.preferred_time_slot,
            "status": self.status,
            "callSid": self.twilio_call_sid,
            "callDurationSeconds": self.call_duration_seconds,
            "recordingUrl": self.recording_url,
            "intentSummary": self.intent_summary,
            "outcome": self.outcome,
            "outcomeNotes": self.outcome_notes,
            "convertedToLead": self.converted_to_lead,
            "leadId": self.lead_id,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "initiatedAt": self.initiated_at.isoformat() if self.initiated_at else None,
            "connectedAt": self.connected_at.isoformat() if self.connected_at else None,
            "endedAt": self.ended_at.isoformat() if self.ended_at else None,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_phase_description(phase: int) -> dict:
    """Get description and goals for a phase"""
    phases = {
        1: {
            "name": "Reassure & Orient",
            "goal": "Create emotional safety",
            "description": "Welcome the visitor, acknowledge their situation, and establish trust.",
            "example_responses": [
                "I understand navigating mortgage options can feel overwhelming...",
                "You're asking the right questions - let me help clarify...",
            ]
        },
        2: {
            "name": "Educate with Tradeoffs",
            "goal": "Demonstrate expertise",
            "description": "Provide valuable information showing understanding of their situation.",
            "example_responses": [
                "Here's how FHA vs conventional typically works for your situation...",
                "There are a few factors to consider here...",
            ]
        },
        3: {
            "name": "Personalize via Micro-Commitments",
            "goal": "Earn permission",
            "description": "Gather specific details through natural conversation flow.",
            "example_responses": [
                "To give you a more accurate picture, what's your approximate credit range?",
                "What's your target price range for the home?",
            ]
        },
        4: {
            "name": "Earned Next Step",
            "goal": "Present ONE logical CTA",
            "description": "Based on trust earned, present the single most appropriate next step.",
            "example_responses": [
                "Based on what you've shared, I think a quick call would help clarify your options...",
                "Would you like to schedule a time to discuss your specific numbers?",
            ]
        }
    }
    return phases.get(phase, phases[1])
