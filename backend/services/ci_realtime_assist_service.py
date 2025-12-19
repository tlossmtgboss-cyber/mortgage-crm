"""
Conversation Intelligence - Real-Time Assist Service

Provides live coaching suggestions during calls via WebSocket:
- Objection response suggestions
- Compliance alerts
- Script prompts
- Customer sentiment indicators

Features:
- Real-time transcription processing
- Context-aware suggestions
- Low-latency response
- Agent feedback collection
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid
import re

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class SuggestionType(str, Enum):
    TIP = "tip"
    WARNING = "warning"
    SCRIPT = "script"
    OBJECTION_RESPONSE = "objection_response"
    COMPLIANCE_ALERT = "compliance_alert"
    SENTIMENT_ALERT = "sentiment_alert"
    DISCOVERY_PROMPT = "discovery_prompt"


class SuggestionPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RealtimeSuggestion:
    """A real-time coaching suggestion."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    suggestion_type: SuggestionType = SuggestionType.TIP
    priority: SuggestionPriority = SuggestionPriority.NORMAL
    title: str = ""
    content: str = ""
    triggered_by: str = ""
    trigger_timestamp_ms: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    was_displayed: bool = False
    was_helpful: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "suggestion_type": self.suggestion_type.value,
            "priority": self.priority.value,
            "title": self.title,
            "content": self.content,
            "triggered_by": self.triggered_by,
            "trigger_timestamp_ms": self.trigger_timestamp_ms,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SessionState:
    """State for a real-time assist session."""
    session_id: str
    agent_user_id: str
    call_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)

    # Transcription buffer
    transcript_buffer: List[Dict] = field(default_factory=list)

    # Detected items
    objections_detected: List[str] = field(default_factory=list)
    compliance_issues: List[str] = field(default_factory=list)
    questions_asked: List[str] = field(default_factory=list)

    # Suggestions sent
    suggestions_sent: List[RealtimeSuggestion] = field(default_factory=list)
    suggestions_sent_ids: Set[str] = field(default_factory=set)

    # Context
    loan_purpose: Optional[str] = None
    customer_sentiment: str = "neutral"
    call_stage: str = "greeting"  # greeting, discovery, presentation, objection, closing

    def add_transcript(self, speaker: str, text: str, timestamp_ms: int):
        self.transcript_buffer.append({
            "speaker": speaker,
            "text": text,
            "timestamp_ms": timestamp_ms
        })
        # Keep buffer reasonable size
        if len(self.transcript_buffer) > 100:
            self.transcript_buffer = self.transcript_buffer[-50:]


# =============================================================================
# TRIGGER PATTERNS
# =============================================================================

OBJECTION_PATTERNS = {
    "rate_too_high": {
        "triggers": ["rate is too high", "rates are high", "better rate", "lower rate", "seen lower"],
        "response": {
            "title": "Rate Objection Detected",
            "content": "Consider: 'I understand rate is important. Let me show you the total cost comparison - sometimes a slightly higher rate with lower fees actually saves you money. What's most important to you - the lowest monthly payment or the lowest total cost?'"
        }
    },
    "not_ready": {
        "triggers": ["not ready", "just looking", "think about it", "not sure", "maybe later"],
        "response": {
            "title": "Timing Objection",
            "content": "Try: 'I completely understand. Many of my clients felt the same way initially. Would it help if I sent you some information to review at your own pace? That way when you're ready, you'll have everything you need.'"
        }
    },
    "using_another": {
        "triggers": ["already have", "working with someone", "my bank", "another lender", "got pre-approved"],
        "response": {
            "title": "Competition Objection",
            "content": "Ask: 'That's great you're already working on this! Have they provided a Loan Estimate yet? I'd be happy to give you a second opinion - no obligation. Often we can find savings others miss.'"
        }
    },
    "too_expensive": {
        "triggers": ["can't afford", "too expensive", "too much", "costs", "fees are high"],
        "response": {
            "title": "Cost Objection",
            "content": "Respond: 'I hear you - costs are definitely something we take seriously. Let me break down exactly what you're looking at and see if there are any programs or options that could help reduce your out-of-pocket.'"
        }
    },
    "bad_credit": {
        "triggers": ["bad credit", "low credit", "credit isn't great", "credit issues", "bankruptcy"],
        "response": {
            "title": "Credit Concern",
            "content": "Reassure: 'Thanks for sharing that. We work with all kinds of credit situations. There may be programs specifically designed for your situation. Would you be open to letting me pull your credit so I can see exactly what options are available?'"
        }
    }
}

COMPLIANCE_TRIGGERS = {
    "nmls_request": {
        "triggers": ["nmls", "license number", "credentials", "are you licensed"],
        "response": {
            "title": "⚠️ NMLS Disclosure Required",
            "content": "Customer asked about licensing. Provide your NMLS ID now.",
            "priority": SuggestionPriority.CRITICAL
        }
    },
    "rate_guarantee_risk": {
        "triggers": ["guaranteed", "promise", "lock it in", "won't change"],
        "response": {
            "title": "⚠️ Rate Guarantee Risk",
            "content": "Avoid guaranteeing rates without a formal lock. Say: 'I can provide you with today's rates, but please note they can change daily until we lock.'",
            "priority": SuggestionPriority.HIGH
        }
    }
}

DISCOVERY_PROMPTS = {
    "purchase_vs_refi": {
        "condition": lambda state: state.loan_purpose is None,
        "stage": "discovery",
        "content": "Ask: 'Are you looking to purchase a new home or refinance an existing mortgage?'"
    },
    "timeline": {
        "condition": lambda state: state.loan_purpose is not None and "timeline" not in str(state.transcript_buffer),
        "stage": "discovery",
        "content": "Ask about timeline: 'When are you hoping to close? Do you have a specific date in mind?'"
    },
    "pre_approval": {
        "condition": lambda state: state.loan_purpose == "purchase",
        "stage": "discovery",
        "content": "Ask: 'Have you been pre-approved by another lender, or would this be your first?'"
    }
}

SENTIMENT_INDICATORS = {
    "frustrated": ["frustrated", "annoyed", "this is ridiculous", "waste of time", "sick of"],
    "confused": ["confused", "don't understand", "what do you mean", "lost", "unclear"],
    "excited": ["excited", "can't wait", "perfect", "great news", "finally"],
    "anxious": ["worried", "nervous", "scared", "what if", "concerned"]
}


# =============================================================================
# REAL-TIME ASSIST SERVICE
# =============================================================================

class RealtimeAssistService:
    """
    Service for providing real-time coaching during calls.

    Usage:
        service = RealtimeAssistService()
        session = service.create_session(agent_id)

        # As transcription comes in:
        suggestions = service.process_transcript_update(
            session.session_id,
            speaker="customer",
            text="Your rates are too high",
            timestamp_ms=15000
        )
    """

    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}
        self.suggestion_callbacks: Dict[str, Callable] = {}

    def create_session(
        self,
        agent_user_id: str,
        call_id: Optional[str] = None
    ) -> SessionState:
        """Create a new real-time assist session."""
        session_id = str(uuid.uuid4())
        session = SessionState(
            session_id=session_id,
            agent_user_id=agent_user_id,
            call_id=call_id
        )
        self.sessions[session_id] = session
        logger.info(f"Created real-time session {session_id} for agent {agent_user_id}")
        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get an existing session."""
        return self.sessions.get(session_id)

    def end_session(self, session_id: str) -> Optional[SessionState]:
        """End a session and return final state."""
        return self.sessions.pop(session_id, None)

    def register_callback(
        self,
        session_id: str,
        callback: Callable[[RealtimeSuggestion], None]
    ):
        """Register callback for when suggestions are generated."""
        self.suggestion_callbacks[session_id] = callback

    def process_transcript_update(
        self,
        session_id: str,
        speaker: str,
        text: str,
        timestamp_ms: int
    ) -> List[RealtimeSuggestion]:
        """
        Process new transcript text and generate suggestions.

        Args:
            session_id: Session ID
            speaker: 'agent' or 'customer'
            text: New transcript text
            timestamp_ms: Timestamp in milliseconds

        Returns:
            List of suggestions to show agent
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found")
            return []

        # Add to buffer
        session.add_transcript(speaker, text, timestamp_ms)

        suggestions = []
        text_lower = text.lower()

        # Only analyze customer speech for triggers
        if speaker == "customer":
            # Check for objections
            objection_suggestions = self._check_objections(session, text_lower, timestamp_ms)
            suggestions.extend(objection_suggestions)

            # Check sentiment
            sentiment_suggestion = self._check_sentiment(session, text_lower, timestamp_ms)
            if sentiment_suggestion:
                suggestions.append(sentiment_suggestion)

            # Check for questions
            if "?" in text:
                session.questions_asked.append(text)

            # Update context from customer speech
            self._update_context(session, text_lower)

        # Check compliance (both speakers)
        compliance_suggestions = self._check_compliance(session, text_lower, timestamp_ms, speaker)
        suggestions.extend(compliance_suggestions)

        # Generate discovery prompts if in discovery stage
        if session.call_stage == "discovery" and speaker == "agent":
            discovery_suggestion = self._check_discovery_prompts(session, timestamp_ms)
            if discovery_suggestion:
                suggestions.append(discovery_suggestion)

        # Deduplicate and filter
        suggestions = self._filter_suggestions(session, suggestions)

        # Track suggestions sent
        for s in suggestions:
            session.suggestions_sent.append(s)
            session.suggestions_sent_ids.add(s.id)

        # Trigger callback if registered
        callback = self.suggestion_callbacks.get(session_id)
        if callback and suggestions:
            for s in suggestions:
                callback(s)

        return suggestions

    def _check_objections(
        self,
        session: SessionState,
        text: str,
        timestamp_ms: int
    ) -> List[RealtimeSuggestion]:
        """Check for objection patterns."""
        suggestions = []

        for objection_type, config in OBJECTION_PATTERNS.items():
            # Skip if we already sent this objection type recently
            if objection_type in session.objections_detected:
                continue

            for trigger in config["triggers"]:
                if trigger in text:
                    session.objections_detected.append(objection_type)

                    suggestion = RealtimeSuggestion(
                        suggestion_type=SuggestionType.OBJECTION_RESPONSE,
                        priority=SuggestionPriority.HIGH,
                        title=config["response"]["title"],
                        content=config["response"]["content"],
                        triggered_by=f"Customer said: '{text[:50]}...'",
                        trigger_timestamp_ms=timestamp_ms
                    )
                    suggestions.append(suggestion)
                    break

        return suggestions

    def _check_compliance(
        self,
        session: SessionState,
        text: str,
        timestamp_ms: int,
        speaker: str
    ) -> List[RealtimeSuggestion]:
        """Check for compliance triggers."""
        suggestions = []

        for rule_type, config in COMPLIANCE_TRIGGERS.items():
            # Skip if already flagged
            if rule_type in session.compliance_issues:
                continue

            for trigger in config["triggers"]:
                if trigger in text:
                    # For NMLS, only trigger on customer speech
                    if rule_type == "nmls_request" and speaker != "customer":
                        continue

                    # For rate guarantee risk, only trigger on agent speech
                    if rule_type == "rate_guarantee_risk" and speaker != "agent":
                        continue

                    session.compliance_issues.append(rule_type)

                    suggestion = RealtimeSuggestion(
                        suggestion_type=SuggestionType.COMPLIANCE_ALERT,
                        priority=config["response"].get("priority", SuggestionPriority.HIGH),
                        title=config["response"]["title"],
                        content=config["response"]["content"],
                        triggered_by=f"Detected: '{trigger}'",
                        trigger_timestamp_ms=timestamp_ms
                    )
                    suggestions.append(suggestion)
                    break

        return suggestions

    def _check_sentiment(
        self,
        session: SessionState,
        text: str,
        timestamp_ms: int
    ) -> Optional[RealtimeSuggestion]:
        """Check for sentiment indicators."""
        for sentiment, indicators in SENTIMENT_INDICATORS.items():
            for indicator in indicators:
                if indicator in text:
                    # Update session sentiment
                    old_sentiment = session.customer_sentiment
                    session.customer_sentiment = sentiment

                    # Only alert on negative sentiments
                    if sentiment in ["frustrated", "confused", "anxious"]:
                        return RealtimeSuggestion(
                            suggestion_type=SuggestionType.SENTIMENT_ALERT,
                            priority=SuggestionPriority.NORMAL,
                            title=f"Customer Sentiment: {sentiment.title()}",
                            content=self._get_sentiment_guidance(sentiment),
                            triggered_by=f"Customer said: '{text[:50]}...'",
                            trigger_timestamp_ms=timestamp_ms
                        )

        return None

    def _get_sentiment_guidance(self, sentiment: str) -> str:
        """Get guidance for handling different sentiments."""
        guidance = {
            "frustrated": "Customer seems frustrated. Acknowledge their feelings: 'I can hear this has been frustrating. Let me see what I can do to help.'",
            "confused": "Customer seems confused. Slow down and clarify: 'Let me explain that more clearly...'",
            "anxious": "Customer seems anxious. Provide reassurance: 'I understand this is a big decision. Let me walk you through this step by step.'",
            "excited": "Customer is excited! Maintain their enthusiasm while ensuring they have all the information they need."
        }
        return guidance.get(sentiment, "Monitor customer sentiment and respond appropriately.")

    def _check_discovery_prompts(
        self,
        session: SessionState,
        timestamp_ms: int
    ) -> Optional[RealtimeSuggestion]:
        """Check if any discovery prompts should be shown."""
        for prompt_id, config in DISCOVERY_PROMPTS.items():
            # Check if condition is met
            if config["condition"](session):
                # Check if we haven't sent this prompt
                prompt_key = f"discovery_{prompt_id}"
                if prompt_key not in session.suggestions_sent_ids:
                    return RealtimeSuggestion(
                        id=prompt_key,
                        suggestion_type=SuggestionType.DISCOVERY_PROMPT,
                        priority=SuggestionPriority.NORMAL,
                        title="Discovery Prompt",
                        content=config["content"],
                        triggered_by="Needs assessment",
                        trigger_timestamp_ms=timestamp_ms
                    )

        return None

    def _update_context(self, session: SessionState, text: str):
        """Update session context based on customer speech."""
        # Detect loan purpose
        if session.loan_purpose is None:
            if any(word in text for word in ["purchase", "buy", "buying", "new home"]):
                session.loan_purpose = "purchase"
            elif any(word in text for word in ["refinance", "refi", "lower rate"]):
                session.loan_purpose = "refinance"
            elif any(word in text for word in ["cash out", "cash-out", "equity"]):
                session.loan_purpose = "cash_out"

        # Detect call stage progression
        if len(session.transcript_buffer) > 3:
            if any("rate" in str(t) for t in session.transcript_buffer[-5:]):
                session.call_stage = "presentation"
            elif session.objections_detected:
                session.call_stage = "objection"

    def _filter_suggestions(
        self,
        session: SessionState,
        suggestions: List[RealtimeSuggestion]
    ) -> List[RealtimeSuggestion]:
        """Filter and deduplicate suggestions."""
        filtered = []
        seen_types = set()

        for s in suggestions:
            # Skip if we already sent this suggestion ID
            if s.id in session.suggestions_sent_ids:
                continue

            # Limit same type suggestions (except critical)
            type_key = f"{s.suggestion_type}_{s.title}"
            if s.priority != SuggestionPriority.CRITICAL and type_key in seen_types:
                continue

            seen_types.add(type_key)
            filtered.append(s)

        # Limit total suggestions per update
        return sorted(filtered, key=lambda x: x.priority.value, reverse=True)[:3]

    def record_feedback(
        self,
        session_id: str,
        suggestion_id: str,
        was_helpful: bool
    ):
        """Record agent feedback on a suggestion."""
        session = self.sessions.get(session_id)
        if session:
            for s in session.suggestions_sent:
                if s.id == suggestion_id:
                    s.was_helpful = was_helpful
                    break

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Get summary of a session."""
        session = self.sessions.get(session_id)
        if not session:
            return {}

        return {
            "session_id": session.session_id,
            "agent_user_id": session.agent_user_id,
            "started_at": session.started_at.isoformat(),
            "transcript_length": len(session.transcript_buffer),
            "objections_detected": session.objections_detected,
            "compliance_issues": session.compliance_issues,
            "suggestions_sent": len(session.suggestions_sent),
            "suggestions_helpful": sum(1 for s in session.suggestions_sent if s.was_helpful),
            "customer_sentiment": session.customer_sentiment,
            "call_stage": session.call_stage,
            "loan_purpose": session.loan_purpose
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_realtime_assist_service() -> RealtimeAssistService:
    """Get singleton real-time assist service."""
    return RealtimeAssistService()
