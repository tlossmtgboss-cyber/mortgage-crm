"""
Chat Session Manager - State Machine Service

This service manages the phase-based chat state machine:
- Session lifecycle (create, update, end)
- Intent detection and scoring
- Phase transitions
- CTA recommendations
- Conversation context building
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_

from sqlalchemy.exc import SQLAlchemyError
from chat_state_machine_models import (
    ChatSession, ChatMessage, CallRequest,
    ChatPhase, UrgencyLevel, CTAType, MessageRole, CallStatus,
    INTENT_SIGNALS, INTENT_WEIGHTS, get_phase_description
)

logger = logging.getLogger(__name__)


# =============================================================================
# INTENT DETECTION PATTERNS
# =============================================================================

INTENT_PATTERNS = {
    "property": {
        "patterns": [
            r"single\s*family",
            r"condo(?:minium)?",
            r"townhouse|town\s*home",
            r"multi\s*family|duplex|triplex|fourplex",
            r"investment\s*property",
            r"(?:first|1st|starter)\s*home",
            r"vacation\s*home|second\s*home",
        ],
        "extract": lambda m: m.group(0).strip()
    },
    "price": {
        "patterns": [
            r"\$\s*([\d,]+)\s*(?:k|K|thousand)?",
            r"([\d,]+)\s*(?:k|K)\s*(?:range|budget|price)?",
            r"around\s*\$?\s*([\d,]+)",
            r"budget\s*(?:of|is|around)?\s*\$?\s*([\d,]+)",
            r"(?:under|below|less\s*than)\s*\$?\s*([\d,]+)",
            r"(?:up\s*to|max(?:imum)?)\s*\$?\s*([\d,]+)",
        ],
        "extract": lambda m: f"${m.group(1).replace(',', '')}"
    },
    "timeline": {
        "patterns": [
            r"(?:within|in|next)\s*(\d+)\s*(?:months?|weeks?|days?)",
            r"(?:asap|as\s*soon\s*as\s*possible|right\s*away|immediately)",
            r"(?:this|next)\s*(?:month|week|year)",
            r"(?:spring|summer|fall|winter|autumn)",
            r"(?:just\s*)?looking|exploring|researching",
            r"ready\s*(?:to\s*(?:buy|move|close))?",
            r"(?:not\s*)?(?:in\s*a\s*)?(?:rush|hurry)",
        ],
        "extract": lambda m: m.group(0).strip()
    },
    "down_payment": {
        "patterns": [
            r"(\d+)\s*%?\s*down",
            r"down\s*payment\s*(?:of|is|around)?\s*\$?\s*([\d,]+)",
            r"\$\s*([\d,]+)\s*(?:saved|available|for\s*down)",
            r"(?:zero|no|0)\s*down",
            r"(?:20|10|5|3\.?5?)\s*percent",
        ],
        "extract": lambda m: m.group(0).strip()
    },
    "loan_type": {
        "patterns": [
            r"\b(?:fha|va|usda|conventional|jumbo|conforming)\b",
            r"(?:government|govt)\s*(?:backed|loan)",
            r"(?:fixed|adjustable|arm)\s*(?:rate)?",
            r"(?:15|20|30)\s*year",
            r"(?:first\s*time\s*(?:home\s*)?buyer|fthb)",
        ],
        "extract": lambda m: m.group(0).strip().upper() if m.group(0).lower() in ['fha', 'va', 'usda'] else m.group(0).strip()
    },
    "credit_band": {
        "patterns": [
            r"credit\s*(?:score|rating)?\s*(?:is|of|around)?\s*(\d{3})",
            r"(\d{3})\s*credit",
            r"(?:excellent|good|fair|poor|bad)\s*credit",
            r"(?:700s?|600s?|800s?|mid|high|low)\s*(?:\d{2}0s?)?",
        ],
        "extract": lambda m: m.group(0).strip()
    },
    "goal": {
        "patterns": [
            r"(?:buy(?:ing)?|purchase|purchas(?:e|ing))\s*(?:a\s*)?(?:home|house|property)",
            r"refinanc(?:e|ing)",
            r"(?:lower|reduce)\s*(?:my\s*)?(?:payment|rate|interest)",
            r"cash\s*out",
            r"(?:pay\s*off|consolidate)\s*debt",
            r"(?:home\s*)?equity",
            r"(?:sell|selling)\s*(?:and\s*)?(?:buy|buying)",
        ],
        "extract": lambda m: m.group(0).strip()
    },
    "urgency": {
        "patterns": [
            r"(?:asap|urgent|quickly|soon|immediately)",
            r"(?:contract|offer)\s*(?:pending|accepted|submitted)",
            r"(?:closing|close)\s*(?:in|on|by)",
            r"(?:rate\s*)?lock(?:ed|ing)?",
            r"(?:pre\s*)?approv(?:ed|al)",
        ],
        "extract": lambda m: m.group(0).strip()
    },
    "recommendation_request": {
        "patterns": [
            r"(?:what|which)\s*(?:do\s*you|would\s*you)\s*(?:recommend|suggest)",
            r"(?:should|would)\s*(?:I|we)",
            r"(?:what'?s?\s*)?(?:best|better)\s*(?:option|choice|for\s*me)?",
            r"(?:your|any)\s*(?:advice|recommendation|suggestion|thoughts)",
            r"(?:help\s*me)\s*(?:decide|choose|understand)",
        ],
        "extract": lambda m: "advice_requested"
    },
}


class ChatSessionManager:
    """
    Manages chat sessions with phase-based state machine.

    This service handles:
    - Session creation and retrieval
    - Message processing with intent detection
    - Phase transitions based on conversation progress
    - CTA timing and recommendations
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================

    def get_or_create_session(
        self,
        visitor_id: str,
        microsite_id: Optional[int] = None,
        loan_officer_id: Optional[int] = None,
        source_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> ChatSession:
        """Get existing active session or create new one for visitor"""

        # Look for existing active session for this visitor
        existing = self.db.query(ChatSession).filter(
            and_(
                ChatSession.visitor_id == visitor_id,
                ChatSession.is_active == True,
                ChatSession.microsite_id == microsite_id
            )
        ).first()

        if existing:
            return existing

        # Create new session
        session = ChatSession(
            visitor_id=visitor_id,
            microsite_id=microsite_id,
            loan_officer_id=loan_officer_id,
            source_url=source_url,
            user_agent=user_agent,
            ip_address=ip_address,
            current_phase=1,
            turn_count=0,
            intent_score=0,
            urgency=UrgencyLevel.LOW.value,
            intent_signals=[],
        )

        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        logger.info(f"Created new chat session: {session.id} for visitor: {visitor_id}")
        return session

    def get_session(self, session_id: UUID) -> Optional[ChatSession]:
        """Get session by ID"""
        return self.db.query(ChatSession).filter(ChatSession.id == session_id).first()

    def get_session_with_messages(self, session_id: UUID) -> Optional[ChatSession]:
        """Get session with all messages loaded"""
        session = self.get_session(session_id)
        if session:
            # Trigger lazy load of messages
            _ = session.messages
        return session

    def end_session(self, session_id: UUID) -> Optional[ChatSession]:
        """Mark session as ended"""
        session = self.get_session(session_id)
        if session:
            session.is_active = False
            session.ended_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.info(f"Ended chat session: {session_id}")
        return session

    # =========================================================================
    # MESSAGE PROCESSING
    # =========================================================================

    def process_user_message(
        self,
        session_id: UUID,
        content: str,
        additional_signals: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[ChatMessage, ChatSession]:
        """
        Process a user message:
        1. Save the message
        2. Detect intents (both built-in and additional from enhanced detector)
        3. Update session state
        4. Check for phase advancement

        Args:
            session_id: Chat session ID
            content: User message content
            additional_signals: Additional signals from enhanced intent detector
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Increment turn count
        session.turn_count += 1

        # Detect intents in message (built-in detection)
        detected_intents = self.detect_intents(content)

        # Merge additional signals from enhanced detector
        if additional_signals:
            existing_types = {i['signal'] for i in detected_intents}
            for signal in additional_signals:
                # Only add if not already detected (enhanced detector may have higher precision)
                if signal.get('signal') not in existing_types:
                    detected_intents.append({
                        'signal': signal.get('signal'),
                        'value': signal.get('value', signal.get('signal')),
                        'confidence': signal.get('confidence', 0.75),
                        'source': 'enhanced_detector',
                    })

        # Determine sentiment
        sentiment = self.analyze_sentiment(content)

        # Create message record
        message = ChatMessage(
            session_id=session_id,
            role=MessageRole.USER.value,
            content=content,
            turn_number=session.turn_count,
            phase_at_message=session.current_phase,
            detected_intents=detected_intents if detected_intents else None,
            sentiment=sentiment,
        )

        self.db.add(message)

        # Update session with detected intents
        for intent in detected_intents:
            session.add_intent_signal(
                signal=intent['signal'],
                value=intent['value'],
                confidence=intent.get('confidence', 0.8)
            )

        # Check if we should advance phase (basic check - route may override with validator)
        if session.should_advance_phase():
            old_phase = session.current_phase
            session.advance_phase()
            logger.info(f"Session {session_id} advanced from phase {old_phase} to {session.current_phase}")

        # Update last message timestamp
        session.last_message_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(message)
        self.db.refresh(session)

        return message, session

    def save_assistant_message(
        self,
        session_id: UUID,
        content: str,
        cta_presented: Optional[str] = None,
        model_used: Optional[str] = None,
        tokens_used: Optional[int] = None,
        response_time_ms: Optional[int] = None,
    ) -> ChatMessage:
        """Save assistant response message"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        message = ChatMessage(
            session_id=session_id,
            role=MessageRole.ASSISTANT.value,
            content=content,
            turn_number=session.turn_count,
            phase_at_message=session.current_phase,
            cta_presented=cta_presented,
            model_used=model_used,
            tokens_used=tokens_used,
            response_time_ms=response_time_ms,
        )

        self.db.add(message)

        # Update CTA tracking if one was presented
        if cta_presented and cta_presented != CTAType.NONE.value:
            session.cta_offered = cta_presented

        session.last_message_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(message)

        return message

    def record_cta_response(
        self,
        session_id: UUID,
        message_id: UUID,
        response: str  # "accepted" or "declined"
    ) -> ChatSession:
        """Record user's response to a CTA"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        message = self.db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if message:
            message.cta_response = response

        if response == "accepted":
            session.cta_accepted = True
            session.cta_accepted_at = datetime.now(timezone.utc)
        elif response == "declined":
            session.cta_declined_count += 1

        self.db.commit()
        self.db.refresh(session)

        return session

    # =========================================================================
    # INTENT DETECTION
    # =========================================================================

    def detect_intents(self, text: str) -> List[Dict[str, Any]]:
        """Detect intent signals from user message"""
        text_lower = text.lower()
        detected = []

        for signal_type, config in INTENT_PATTERNS.items():
            for pattern in config['patterns']:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    try:
                        value = config['extract'](match)
                    except Exception as e:
                        logger.warning(f"Error extracting intent signal value: {e}")
                        value = match.group(0)

                    detected.append({
                        'signal': signal_type,
                        'value': value,
                        'confidence': self._calculate_confidence(signal_type, match, text),
                        'pattern_matched': pattern,
                    })
                    break  # Only one match per signal type

        return detected

    def _calculate_confidence(self, signal_type: str, match, full_text: str) -> float:
        """Calculate confidence score for detected intent"""
        base_confidence = 0.7

        # Boost for explicit mentions
        if signal_type in ['loan_type', 'timeline', 'price']:
            base_confidence = 0.85

        # Boost for recommendation requests (high signal value)
        if signal_type == 'recommendation_request':
            base_confidence = 0.95

        # Boost if the message is focused (short and specific)
        if len(full_text) < 100:
            base_confidence += 0.1

        return min(1.0, base_confidence)

    def analyze_sentiment(self, text: str) -> str:
        """Simple sentiment analysis of user message"""
        text_lower = text.lower()

        # Anxiety/worry indicators
        anxiety_words = ['worried', 'nervous', 'scared', 'anxious', 'stress', 'concern', 'afraid', 'overwhelm']
        if any(word in text_lower for word in anxiety_words):
            return 'anxious'

        # Negative indicators
        negative_words = ['no', 'not', 'cant', "can't", 'wont', "won't", 'problem', 'issue', 'bad', 'terrible']
        negative_count = sum(1 for word in negative_words if word in text_lower)

        # Positive indicators
        positive_words = ['great', 'thanks', 'thank', 'helpful', 'good', 'excellent', 'perfect', 'awesome', 'yes']
        positive_count = sum(1 for word in positive_words if word in text_lower)

        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        return 'neutral'

    # =========================================================================
    # CONTEXT BUILDING
    # =========================================================================

    def build_conversation_context(self, session: ChatSession, max_messages: int = 10) -> Dict[str, Any]:
        """Build context object for AI prompt construction"""
        messages = session.messages[-max_messages:] if session.messages else []

        # Summarize detected intents
        intent_summary = {}
        for signal in (session.intent_signals or []):
            intent_summary[signal['signal']] = signal['value']

        # Get phase info
        phase_info = get_phase_description(session.current_phase)

        # Determine CTA recommendation
        cta_recommendation = session.get_cta_recommendation()

        return {
            "session_id": str(session.id),
            "current_phase": session.current_phase,
            "phase_name": phase_info['name'],
            "phase_goal": phase_info['goal'],
            "turn_count": session.turn_count,
            "intent_score": session.intent_score,
            "urgency": session.urgency,
            "intent_summary": intent_summary,
            "collected_signals": list(intent_summary.keys()),
            "missing_signals": [s for s in ['timeline', 'price', 'loan_type'] if s not in intent_summary],
            "cta_recommendation": cta_recommendation,
            "cta_declined_count": session.cta_declined_count,
            "conversation_history": [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ],
            "contact_info": {
                "name": session.contact_name,
                "email": session.contact_email,
                "phone": session.contact_phone,
            },
            "microsite_id": session.microsite_id,
            "loan_officer_id": session.loan_officer_id,
        }

    def get_next_question_suggestion(self, session: ChatSession) -> Optional[str]:
        """Suggest next question to ask based on missing intent signals"""
        collected = [s['signal'] for s in (session.intent_signals or [])]

        # Priority order of questions to ask
        question_priorities = [
            ('timeline', "What's your timeline for buying/refinancing?"),
            ('price', "What price range are you considering?"),
            ('loan_type', "Are you interested in any specific loan programs?"),
            ('down_payment', "Do you have a sense of your down payment?"),
            ('credit_band', "What's your approximate credit score range?"),
        ]

        for signal, question in question_priorities:
            if signal not in collected:
                return question

        return None

    # =========================================================================
    # CONTACT INFO
    # =========================================================================

    def update_contact_info(
        self,
        session_id: UUID,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> ChatSession:
        """Update session with collected contact information"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if name:
            session.contact_name = name
        if email:
            session.contact_email = email
        if phone:
            session.contact_phone = phone

        self.db.commit()
        self.db.refresh(session)

        return session

    # =========================================================================
    # CALL REQUEST MANAGEMENT
    # =========================================================================

    def create_call_request(
        self,
        session_id: UUID,
        caller_phone: str,
        caller_name: Optional[str] = None,
        is_immediate: bool = True,
        scheduled_at: Optional[datetime] = None,
        preferred_time_slot: Optional[str] = None,
    ) -> CallRequest:
        """Create a call request for click-to-call or scheduled callback"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Update session contact info if provided
        if caller_phone:
            session.contact_phone = caller_phone
        if caller_name:
            session.contact_name = caller_name

        # Build intent summary for whisper message
        intent_summary = self._build_intent_summary(session)

        call_request = CallRequest(
            session_id=session_id,
            loan_officer_id=session.loan_officer_id,
            direction='inbound' if is_immediate else 'outbound',
            caller_phone=caller_phone,
            caller_name=caller_name or session.contact_name,
            is_immediate=is_immediate,
            scheduled_at=scheduled_at,
            preferred_time_slot=preferred_time_slot,
            status=CallStatus.PENDING.value,
            intent_summary=intent_summary,
            intent_signals_snapshot=session.intent_signals,
        )

        # Generate whisper message
        self.db.add(call_request)
        self.db.flush()  # Get ID without committing
        call_request.whisper_message = call_request.generate_whisper_message()

        # Record CTA acceptance
        session.cta_accepted = True
        session.cta_accepted_at = datetime.now(timezone.utc)
        session.cta_offered = CTAType.CALL_NOW.value if is_immediate else CTAType.SCHEDULE.value

        self.db.commit()
        self.db.refresh(call_request)

        logger.info(f"Created call request: {call_request.id} for session: {session_id}")
        return call_request

    def _build_intent_summary(self, session: ChatSession) -> str:
        """Build human-readable summary of detected intents"""
        parts = []

        signals = session.intent_signals or []
        signal_map = {s['signal']: s['value'] for s in signals}

        if 'goal' in signal_map:
            parts.append(f"Goal: {signal_map['goal']}")
        if 'price' in signal_map:
            parts.append(f"Budget: {signal_map['price']}")
        if 'timeline' in signal_map:
            parts.append(f"Timeline: {signal_map['timeline']}")
        if 'loan_type' in signal_map:
            parts.append(f"Interest: {signal_map['loan_type']}")
        if 'down_payment' in signal_map:
            parts.append(f"Down payment: {signal_map['down_payment']}")
        if 'credit_band' in signal_map:
            parts.append(f"Credit: {signal_map['credit_band']}")

        parts.append(f"Intent score: {session.intent_score}/100")
        parts.append(f"Urgency: {session.urgency}")

        return " | ".join(parts) if parts else "No specific details collected"

    def update_call_status(
        self,
        call_id: UUID,
        status: str,
        telephony_call_sid: Optional[str] = None,
        telephony_conference_sid: Optional[str] = None,
    ) -> Optional[CallRequest]:
        """Update call request status"""
        call = self.db.query(CallRequest).filter(CallRequest.id == call_id).first()
        if not call:
            return None

        call.status = status
        if telephony_call_sid:
            call.twilio_call_sid = telephony_call_sid  # legacy column name
        if telephony_conference_sid:
            call.twilio_conference_sid = telephony_conference_sid  # legacy column name

        # Update timestamps based on status
        now = datetime.now(timezone.utc)
        if status == CallStatus.CONNECTING.value:
            call.initiated_at = now
        elif status == CallStatus.IN_PROGRESS.value:
            call.connected_at = now
        elif status in [CallStatus.COMPLETED.value, CallStatus.FAILED.value,
                        CallStatus.CANCELLED.value, CallStatus.NO_ANSWER.value]:
            call.ended_at = now
            if call.connected_at:
                call.call_duration_seconds = int((now - call.connected_at).total_seconds())

        self.db.commit()
        self.db.refresh(call)

        return call

    def complete_call(
        self,
        call_id: UUID,
        outcome: Optional[str] = None,
        outcome_notes: Optional[str] = None,
        recording_url: Optional[str] = None,
        recording_sid: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        converted_to_lead: bool = False,
        lead_id: Optional[int] = None,
    ) -> Optional[CallRequest]:
        """Complete a call with outcome tracking"""
        call = self.update_call_status(call_id, CallStatus.COMPLETED.value)
        if not call:
            return None

        if outcome:
            call.outcome = outcome
        if outcome_notes:
            call.outcome_notes = outcome_notes
        if recording_url:
            call.recording_url = recording_url
        if recording_sid:
            call.recording_sid = recording_sid
        if duration_seconds:
            call.call_duration_seconds = duration_seconds
        if converted_to_lead:
            call.converted_to_lead = True
            call.lead_id = lead_id

            # Also update the session
            session = call.session
            if session:
                session.converted_to_lead = True
                session.lead_id = lead_id

        self.db.commit()
        self.db.refresh(call)

        return call

    # =========================================================================
    # ANALYTICS
    # =========================================================================

    def get_session_stats(self, session_id: UUID) -> Dict[str, Any]:
        """Get statistics for a session"""
        session = self.get_session_with_messages(session_id)
        if not session:
            return {}

        user_messages = [m for m in session.messages if m.role == MessageRole.USER.value]
        assistant_messages = [m for m in session.messages if m.role == MessageRole.ASSISTANT.value]

        return {
            "session_id": str(session_id),
            "duration_seconds": (session.ended_at - session.created_at).total_seconds() if session.ended_at else None,
            "total_messages": len(session.messages),
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages),
            "turns": session.turn_count,
            "final_phase": session.current_phase,
            "final_intent_score": session.intent_score,
            "final_urgency": session.urgency,
            "signals_collected": len(session.intent_signals or []),
            "cta_offered": session.cta_offered,
            "cta_accepted": session.cta_accepted,
            "cta_declined_count": session.cta_declined_count,
            "converted_to_lead": session.converted_to_lead,
        }
