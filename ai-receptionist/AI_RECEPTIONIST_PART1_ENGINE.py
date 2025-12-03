"""
================================================================================
PERENNIA AI - CONVERSATION ENGINE
================================================================================
Part 1: Core Engine

Intelligent, empathetic AI receptionist that handles inbound calls with
natural conversation flow, emotional intelligence, and seamless tool integration.

Components:
- ConversationState: Tracks call context and history
- PersonalityEngine: Manages empathy and tone
- IntentClassifier: Understands caller needs
- ConversationEngine: Orchestrates the full experience

================================================================================
"""

import os
import json
import asyncio
import logging
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import re

# Optional imports - graceful fallback
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class CallIntent(str, Enum):
    """Primary caller intents"""
    SCHEDULE_APPOINTMENT = "schedule_appointment"
    SPEAK_TO_AGENT = "speak_to_agent"
    LOAN_STATUS = "loan_status"
    RATE_INQUIRY = "rate_inquiry"
    MAKE_PAYMENT = "make_payment"
    LEAVE_MESSAGE = "leave_message"
    GENERAL_QUESTION = "general_question"
    COMPLAINT = "complaint"
    CALLBACK_REQUEST = "callback_request"
    UNKNOWN = "unknown"


class EmotionalState(str, Enum):
    """Detected caller emotional state"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    FRUSTRATED = "frustrated"
    ANXIOUS = "anxious"
    CONFUSED = "confused"
    ANGRY = "angry"
    URGENT = "urgent"
    SAD = "sad"


class ConversationPhase(str, Enum):
    """Current phase of the conversation"""
    GREETING = "greeting"
    IDENTIFICATION = "identification"
    INTENT_DISCOVERY = "intent_discovery"
    INFORMATION_GATHERING = "information_gathering"
    ACTION_EXECUTION = "action_execution"
    CONFIRMATION = "confirmation"
    CLOSING = "closing"
    TRANSFER = "transfer"
    ON_HOLD = "on_hold"


class TransferType(str, Enum):
    """Types of call transfers"""
    WARM = "warm"  # Stay on line, introduce caller
    COLD = "cold"  # Direct transfer
    BLIND = "blind"  # Transfer without announcement


# =============================================================================
# PERSONALITY CONFIGURATION
# =============================================================================

@dataclass
class ReceptionistPersonality:
    """Configurable personality traits for the AI receptionist"""

    name: str = "Sarah"
    company_name: str = "Perennia Mortgage"

    # Core traits (0-10 scale)
    warmth: int = 8
    professionalism: int = 9
    patience: int = 9
    empathy: int = 9
    enthusiasm: int = 7

    # Communication style
    speaking_pace: str = "moderate"  # slow, moderate, fast
    formality: str = "professional_friendly"  # formal, professional_friendly, casual
    use_caller_name: bool = True
    use_filler_words: bool = True  # "um", "let me see" - sounds more human

    # Empathy responses by emotional state
    empathy_responses: Dict[str, List[str]] = field(default_factory=lambda: {
        "frustrated": [
            "I completely understand how frustrating this must be for you.",
            "I hear you, and I want to help make this right.",
            "I can tell this has been difficult, and I appreciate your patience.",
            "That does sound frustrating. Let me see what I can do to help.",
        ],
        "anxious": [
            "I understand this can feel overwhelming. Let's take it one step at a time.",
            "Don't worry, we'll figure this out together.",
            "I can hear this is weighing on you. I'm here to help.",
            "It's completely normal to have questions. That's what I'm here for.",
        ],
        "confused": [
            "No problem at all - let me explain that more clearly.",
            "That's a great question. Let me break it down for you.",
            "I understand it can be confusing. Here's what you need to know.",
            "Let me make sure I explain this in a way that makes sense.",
        ],
        "angry": [
            "I'm truly sorry you're dealing with this. Let me help.",
            "I understand why you're upset, and I want to resolve this for you.",
            "Your frustration is completely valid. Let's work on fixing this.",
            "I hear you, and I'm going to do everything I can to help.",
        ],
        "urgent": [
            "I understand this is time-sensitive. Let me prioritize this for you.",
            "I can tell this is urgent. Let me help you right away.",
            "I hear the urgency. Let's get this handled immediately.",
            "I understand you need this resolved quickly. I'm on it.",
        ],
        "sad": [
            "I'm sorry to hear that. I'm here to help however I can.",
            "That sounds really difficult. Let me see what we can do.",
            "I appreciate you sharing that with me. How can I help?",
            "I understand. Let's see how we can make this easier for you.",
        ],
    })

    # Filler phrases for natural speech
    thinking_fillers: List[str] = field(default_factory=lambda: [
        "Let me check on that for you...",
        "One moment while I look that up...",
        "Let me see here...",
        "Give me just a second...",
        "Alright, let me pull that up...",
    ])

    # Acknowledgment phrases
    acknowledgments: List[str] = field(default_factory=lambda: [
        "Absolutely.",
        "Of course.",
        "Sure thing.",
        "I'd be happy to help with that.",
        "Certainly.",
        "No problem at all.",
    ])

    def get_greeting(self, time_of_day: str = None) -> str:
        """Generate appropriate greeting based on time of day"""
        if time_of_day is None:
            hour = datetime.now().hour
            if hour < 12:
                time_of_day = "morning"
            elif hour < 17:
                time_of_day = "afternoon"
            else:
                time_of_day = "evening"

        greetings = {
            "morning": f"Good morning! Thank you for calling {self.company_name}. This is {self.name}, how may I help you today?",
            "afternoon": f"Good afternoon! Thank you for calling {self.company_name}. This is {self.name}, how can I assist you?",
            "evening": f"Good evening! Thank you for calling {self.company_name}. This is {self.name}, how may I help you?",
        }
        return greetings.get(time_of_day, greetings["afternoon"])

    def get_empathy_response(self, emotional_state: EmotionalState) -> str:
        """Get appropriate empathy response for emotional state"""
        import random
        responses = self.empathy_responses.get(emotional_state.value, [])
        if responses:
            return random.choice(responses)
        return "I understand. How can I help you?"

    def get_thinking_filler(self) -> str:
        """Get a natural thinking filler phrase"""
        import random
        return random.choice(self.thinking_fillers)

    def get_acknowledgment(self) -> str:
        """Get a natural acknowledgment phrase"""
        import random
        return random.choice(self.acknowledgments)


# =============================================================================
# CONVERSATION STATE
# =============================================================================

@dataclass
class CallerInfo:
    """Information about the caller"""
    phone_number: str
    caller_id_name: Optional[str] = None

    # Identified information
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None

    # CRM lookup results
    contact_id: Optional[str] = None
    is_existing_customer: bool = False
    loan_ids: List[str] = field(default_factory=list)
    assigned_lo_id: Optional[str] = None
    assigned_lo_name: Optional[str] = None

    # Preferences
    preferred_contact_method: Optional[str] = None
    timezone: str = "America/New_York"

    @property
    def display_name(self) -> str:
        if self.first_name:
            return self.first_name
        if self.caller_id_name:
            return self.caller_id_name.split()[0]
        return "there"

    @property
    def full_name(self) -> Optional[str]:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.caller_id_name


@dataclass
class ConversationTurn:
    """Single turn in the conversation"""
    role: str  # "caller" or "receptionist"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    intent: Optional[CallIntent] = None
    emotion: Optional[EmotionalState] = None
    action_taken: Optional[str] = None
    tool_calls: List[Dict] = field(default_factory=list)


@dataclass
class ConversationState:
    """Complete state of an ongoing conversation"""

    # Call identification
    call_sid: str
    started_at: datetime = field(default_factory=datetime.now)

    # Caller info
    caller: CallerInfo = None

    # Conversation tracking
    phase: ConversationPhase = ConversationPhase.GREETING
    turns: List[ConversationTurn] = field(default_factory=list)

    # Intent and context
    primary_intent: Optional[CallIntent] = None
    secondary_intents: List[CallIntent] = field(default_factory=list)
    current_emotion: EmotionalState = EmotionalState.NEUTRAL

    # Gathered information
    gathered_info: Dict[str, Any] = field(default_factory=dict)
    pending_questions: List[str] = field(default_factory=list)

    # Action tracking
    actions_taken: List[Dict] = field(default_factory=list)
    pending_actions: List[Dict] = field(default_factory=list)

    # Transfer state
    transfer_target: Optional[str] = None
    transfer_type: Optional[TransferType] = None
    hold_started_at: Optional[datetime] = None

    # Flags
    needs_supervisor: bool = False
    is_callback_scheduled: bool = False
    message_left: bool = False
    appointment_scheduled: bool = False

    # Metrics
    interruption_count: int = 0
    silence_count: int = 0

    def add_turn(self, role: str, content: str, **kwargs) -> ConversationTurn:
        """Add a conversation turn"""
        turn = ConversationTurn(role=role, content=content, **kwargs)
        self.turns.append(turn)
        return turn

    def get_conversation_history(self, max_turns: int = 20) -> List[Dict]:
        """Get recent conversation history for LLM context"""
        recent = self.turns[-max_turns:] if len(self.turns) > max_turns else self.turns
        return [
            {"role": "user" if t.role == "caller" else "assistant", "content": t.content}
            for t in recent
        ]

    def get_context_summary(self) -> str:
        """Get a summary of current conversation context"""
        parts = []

        if self.caller and self.caller.first_name:
            parts.append(f"Caller: {self.caller.full_name or self.caller.first_name}")
        if self.caller and self.caller.is_existing_customer:
            parts.append("Existing customer")
        if self.primary_intent:
            parts.append(f"Intent: {self.primary_intent.value}")
        if self.current_emotion != EmotionalState.NEUTRAL:
            parts.append(f"Emotion: {self.current_emotion.value}")
        if self.gathered_info:
            parts.append(f"Info gathered: {', '.join(self.gathered_info.keys())}")

        return " | ".join(parts) if parts else "New call"

    @property
    def duration_seconds(self) -> int:
        """Get call duration in seconds"""
        return int((datetime.now() - self.started_at).total_seconds())

    @property
    def turn_count(self) -> int:
        """Get number of conversation turns"""
        return len(self.turns)


# =============================================================================
# INTENT CLASSIFIER
# =============================================================================

class IntentClassifier:
    """Classifies caller intent from speech"""

    # Keywords mapped to intents
    INTENT_KEYWORDS = {
        CallIntent.SCHEDULE_APPOINTMENT: [
            "appointment", "schedule", "meet", "meeting", "book", "available",
            "calendar", "time slot", "consultation", "come in", "visit"
        ],
        CallIntent.SPEAK_TO_AGENT: [
            "speak to", "talk to", "transfer", "connect me", "loan officer",
            "representative", "agent", "person", "human", "someone"
        ],
        CallIntent.LOAN_STATUS: [
            "loan status", "application status", "where is my", "update on",
            "progress", "approved", "closing", "underwriting", "how long"
        ],
        CallIntent.RATE_INQUIRY: [
            "rate", "rates", "interest", "apr", "percentage", "points",
            "current rate", "today's rate", "lock", "quote"
        ],
        CallIntent.MAKE_PAYMENT: [
            "payment", "pay", "pay my", "bill", "due", "amount owed",
            "balance", "pay off"
        ],
        CallIntent.LEAVE_MESSAGE: [
            "message", "leave a message", "voicemail", "call me back",
            "have them call", "return my call"
        ],
        CallIntent.COMPLAINT: [
            "complaint", "problem", "issue", "wrong", "mistake", "error",
            "unhappy", "frustrated", "upset", "manager", "supervisor"
        ],
        CallIntent.CALLBACK_REQUEST: [
            "call back", "callback", "call me", "return call", "reach me",
            "get back to me", "when available"
        ],
    }

    # Emotional indicators
    EMOTION_KEYWORDS = {
        EmotionalState.FRUSTRATED: [
            "frustrated", "annoying", "annoyed", "ridiculous", "unbelievable",
            "how many times", "again", "still", "waiting", "forever"
        ],
        EmotionalState.ANXIOUS: [
            "worried", "nervous", "anxious", "concerned", "scared",
            "what if", "afraid", "stress", "overwhelming"
        ],
        EmotionalState.CONFUSED: [
            "confused", "don't understand", "what do you mean", "unclear",
            "lost", "huh", "what", "explain"
        ],
        EmotionalState.ANGRY: [
            "angry", "furious", "unacceptable", "demand", "terrible",
            "worst", "never again", "lawsuit", "lawyer", "sue"
        ],
        EmotionalState.URGENT: [
            "urgent", "emergency", "asap", "immediately", "right now",
            "today", "can't wait", "deadline", "closing tomorrow"
        ],
        EmotionalState.HAPPY: [
            "thank you", "great", "wonderful", "excellent", "happy",
            "appreciate", "perfect", "awesome"
        ],
    }

    def classify_intent(self, text: str) -> Tuple[CallIntent, float]:
        """Classify intent from text with confidence score"""
        text_lower = text.lower()
        scores = {}

        for intent, keywords in self.INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[intent] = score

        if scores:
            best_intent = max(scores, key=scores.get)
            confidence = min(scores[best_intent] / 3, 1.0)  # Normalize
            return best_intent, confidence

        return CallIntent.UNKNOWN, 0.0

    def detect_emotion(self, text: str) -> Tuple[EmotionalState, float]:
        """Detect emotional state from text"""
        text_lower = text.lower()
        scores = {}

        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[emotion] = score

        if scores:
            best_emotion = max(scores, key=scores.get)
            confidence = min(scores[best_emotion] / 2, 1.0)
            return best_emotion, confidence

        return EmotionalState.NEUTRAL, 1.0

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Extract named entities from text"""
        entities = {}

        # Phone number
        phone_match = re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', text)
        if phone_match:
            entities["phone"] = phone_match.group()

        # Email
        email_match = re.search(r'\b[\w.-]+@[\w.-]+\.\w+\b', text)
        if email_match:
            entities["email"] = email_match.group()

        # Loan number (common format)
        loan_match = re.search(r'\b[A-Z]{2,3}[-]?\d{6,10}\b', text, re.IGNORECASE)
        if loan_match:
            entities["loan_number"] = loan_match.group().upper()

        # Date/time mentions
        date_patterns = [
            r'\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday)\b',
            r'\b(\d{1,2}[:/]\d{2}\s*(?:am|pm)?)\b',
            r'\b(morning|afternoon|evening)\b',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                entities.setdefault("time_mentions", []).append(match.group())

        # Dollar amounts
        amount_match = re.search(r'\$[\d,]+(?:\.\d{2})?', text)
        if amount_match:
            entities["amount"] = amount_match.group()

        return entities


# =============================================================================
# LLM CONVERSATION HANDLER
# =============================================================================

class LLMHandler(ABC):
    """Abstract base for LLM providers"""

    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict],
        tools: List[Dict] = None,
    ) -> Tuple[str, List[Dict]]:
        """Generate response from LLM"""
        pass


class ClaudeHandler(LLMHandler):
    """Claude API handler"""

    def __init__(self, api_key: str = None):
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package not installed")
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-20250514"

    async def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict],
        tools: List[Dict] = None,
    ) -> Tuple[str, List[Dict]]:
        """Generate response using Claude"""

        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools

        response = self.client.messages.create(**kwargs)

        text_response = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_response = block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        return text_response, tool_calls


class OpenAIHandler(LLMHandler):
    """OpenAI API handler (GPT-4)"""

    def __init__(self, api_key: str = None):
        if not HAS_OPENAI:
            raise ImportError("openai package not installed")
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4-turbo-preview"

    async def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict],
        tools: List[Dict] = None,
    ) -> Tuple[str, List[Dict]]:
        """Generate response using OpenAI"""

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs = {
            "model": self.model,
            "messages": full_messages,
        }

        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        response = self.client.chat.completions.create(**kwargs)

        message = response.choices[0].message
        text_response = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })

        return text_response, tool_calls


# =============================================================================
# MAIN CONVERSATION ENGINE
# =============================================================================

class ConversationEngine:
    """
    Main conversation engine that orchestrates the AI receptionist.

    Handles:
    - Natural conversation flow with empathy
    - Intent recognition and routing
    - Tool execution for actions
    - State management across turns
    - Warm/cold transfers
    """

    def __init__(
        self,
        personality: ReceptionistPersonality = None,
        llm_provider: str = "claude",  # "claude" or "openai"
        tool_executor: Callable = None,
    ):
        self.personality = personality or ReceptionistPersonality()
        self.intent_classifier = IntentClassifier()
        self.tool_executor = tool_executor

        # Initialize LLM handler
        if llm_provider == "claude" and HAS_ANTHROPIC:
            self.llm = ClaudeHandler()
        elif llm_provider == "openai" and HAS_OPENAI:
            self.llm = OpenAIHandler()
        else:
            self.llm = None
            logger.warning("No LLM provider available - using rule-based responses")

        # Active conversations
        self.conversations: Dict[str, ConversationState] = {}

    def _build_system_prompt(self, state: ConversationState) -> str:
        """Build the system prompt for the LLM"""
        p = self.personality

        return f"""You are {p.name}, a warm and professional AI receptionist for {p.company_name}, a mortgage company.

PERSONALITY TRAITS:
- Warmth: {p.warmth}/10 - You genuinely care about callers
- Professionalism: {p.professionalism}/10 - You maintain appropriate boundaries
- Patience: {p.patience}/10 - You never rush callers or show frustration
- Empathy: {p.empathy}/10 - You acknowledge and validate feelings
- Enthusiasm: {p.enthusiasm}/10 - You're positive without being over the top

COMMUNICATION STYLE:
- Speak at a {p.speaking_pace} pace
- Use {p.formality} tone
- {"Use the caller's name naturally" if p.use_caller_name else "Don't overuse names"}
- {"Include natural filler words occasionally" if p.use_filler_words else "Speak directly"}

CURRENT CONTEXT:
{state.get_context_summary()}

CALLER EMOTIONAL STATE: {state.current_emotion.value}
{f"Empathy guidance: {p.get_empathy_response(state.current_emotion)}" if state.current_emotion != EmotionalState.NEUTRAL else ""}

YOUR CAPABILITIES:
1. Schedule appointments with loan officers
2. Check loan officer availability
3. Look up loan status (with verification)
4. Take messages for loan officers
5. Transfer calls (warm or cold)
6. Schedule callbacks
7. Answer general mortgage questions
8. Create callback requests

IMPORTANT GUIDELINES:
1. Always verify caller identity before sharing loan details
2. If unsure, offer to take a message or schedule a callback
3. Never share specific financial details without verification
4. Show empathy when callers are frustrated or anxious
5. Offer alternatives if the first option doesn't work
6. Confirm actions before taking them
7. Keep responses conversational - this is a phone call, not a chat
8. Responses should be brief (1-3 sentences) unless explaining something complex

RESPONSE FORMAT:
- Speak naturally as if on a phone call
- Don't use markdown, bullet points, or formatting
- Don't narrate actions (don't say "I'm checking..." say "Let me check...")
- End with a question or clear next step when appropriate"""

    def _get_available_tools(self) -> List[Dict]:
        """Get tools available for the conversation"""
        return [
            {
                "name": "get_lo_availability",
                "description": "Check a loan officer's availability for appointments",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lo_id": {"type": "string", "description": "Loan officer ID"},
                        "date": {"type": "string", "description": "Date to check (YYYY-MM-DD)"},
                    },
                    "required": ["lo_id"],
                },
            },
            {
                "name": "book_appointment",
                "description": "Schedule an appointment with a loan officer",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lo_id": {"type": "string", "description": "Loan officer ID"},
                        "caller_name": {"type": "string", "description": "Caller's name"},
                        "caller_phone": {"type": "string", "description": "Caller's phone"},
                        "datetime": {"type": "string", "description": "Appointment datetime"},
                        "purpose": {"type": "string", "description": "Purpose of appointment"},
                    },
                    "required": ["lo_id", "caller_name", "caller_phone", "datetime"],
                },
            },
            {
                "name": "create_callback_request",
                "description": "Create a request for someone to call the caller back",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "caller_name": {"type": "string"},
                        "caller_phone": {"type": "string"},
                        "lo_id": {"type": "string", "description": "Specific LO to call back"},
                        "reason": {"type": "string"},
                        "urgency": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                        "best_time": {"type": "string", "description": "Best time to reach caller"},
                    },
                    "required": ["caller_name", "caller_phone"],
                },
            },
            {
                "name": "get_loan_status",
                "description": "Get status of a loan (requires verification)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "loan_number": {"type": "string"},
                        "borrower_last_name": {"type": "string"},
                        "ssn_last_four": {"type": "string", "description": "Last 4 of SSN for verification"},
                    },
                    "required": ["loan_number", "borrower_last_name"],
                },
            },
            {
                "name": "transfer_call",
                "description": "Transfer the call to a loan officer or department",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string", "description": "LO ID or department"},
                        "transfer_type": {"type": "string", "enum": ["warm", "cold"]},
                        "context": {"type": "string", "description": "Context to provide to recipient"},
                    },
                    "required": ["target_id", "transfer_type"],
                },
            },
            {
                "name": "leave_message",
                "description": "Take a message for a loan officer",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lo_id": {"type": "string"},
                        "caller_name": {"type": "string"},
                        "caller_phone": {"type": "string"},
                        "message": {"type": "string"},
                        "urgent": {"type": "boolean"},
                    },
                    "required": ["lo_id", "caller_name", "message"],
                },
            },
            {
                "name": "lookup_caller",
                "description": "Look up caller information in CRM by phone number",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string"},
                    },
                    "required": ["phone_number"],
                },
            },
        ]

    async def start_conversation(
        self,
        call_sid: str,
        caller_phone: str,
        caller_id_name: str = None,
    ) -> Tuple[ConversationState, str]:
        """
        Start a new conversation when a call comes in.

        Returns:
            Tuple of (ConversationState, initial_greeting)
        """
        # Create conversation state
        caller = CallerInfo(
            phone_number=caller_phone,
            caller_id_name=caller_id_name,
        )

        state = ConversationState(
            call_sid=call_sid,
            caller=caller,
            phase=ConversationPhase.GREETING,
        )

        self.conversations[call_sid] = state

        # Look up caller in CRM
        if self.tool_executor:
            try:
                result = await self._execute_tool("lookup_caller", {"phone_number": caller_phone})
                if result and result.get("found"):
                    caller.contact_id = result.get("contact_id")
                    caller.first_name = result.get("first_name")
                    caller.last_name = result.get("last_name")
                    caller.is_existing_customer = result.get("is_customer", False)
                    caller.loan_ids = result.get("loan_ids", [])
                    caller.assigned_lo_id = result.get("assigned_lo_id")
                    caller.assigned_lo_name = result.get("assigned_lo_name")
            except Exception as e:
                logger.warning(f"CRM lookup failed: {e}")

        # Generate greeting
        greeting = self.personality.get_greeting()

        # Personalize if we know them
        if caller.first_name:
            greeting = f"Good {'morning' if datetime.now().hour < 12 else 'afternoon'}, {caller.first_name}! " \
                       f"Thank you for calling {self.personality.company_name}. This is {self.personality.name}. " \
                       f"How can I help you today?"

        # Record the greeting
        state.add_turn("receptionist", greeting)

        return state, greeting

    async def process_input(
        self,
        call_sid: str,
        caller_input: str,
    ) -> str:
        """
        Process caller input and generate response.

        Args:
            call_sid: The call identifier
            caller_input: What the caller said (from STT)

        Returns:
            The receptionist's response (for TTS)
        """
        state = self.conversations.get(call_sid)
        if not state:
            logger.error(f"No conversation found for call {call_sid}")
            return "I'm sorry, I seem to have lost our connection. Let me transfer you to someone who can help."

        # Detect intent and emotion
        intent, intent_confidence = self.intent_classifier.classify_intent(caller_input)
        emotion, emotion_confidence = self.intent_classifier.detect_emotion(caller_input)

        # Update state
        if emotion_confidence > 0.5:
            state.current_emotion = emotion

        if intent != CallIntent.UNKNOWN and intent_confidence > 0.3:
            if not state.primary_intent:
                state.primary_intent = intent
            elif intent != state.primary_intent:
                state.secondary_intents.append(intent)

        # Extract entities
        entities = self.intent_classifier.extract_entities(caller_input)
        state.gathered_info.update(entities)

        # Record caller turn
        state.add_turn("caller", caller_input, intent=intent, emotion=emotion)

        # Generate response
        if self.llm:
            response = await self._generate_llm_response(state, caller_input)
        else:
            response = self._generate_rule_based_response(state, caller_input, intent)

        # Record response
        state.add_turn("receptionist", response)

        # Update conversation phase
        self._update_phase(state)

        return response

    async def _generate_llm_response(
        self,
        state: ConversationState,
        caller_input: str,
    ) -> str:
        """Generate response using LLM"""
        system_prompt = self._build_system_prompt(state)
        messages = state.get_conversation_history()
        tools = self._get_available_tools()

        response_text, tool_calls = await self.llm.generate_response(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
        )

        # Execute any tool calls
        if tool_calls:
            tool_results = []
            for tc in tool_calls:
                result = await self._execute_tool(tc["name"], tc["arguments"])
                tool_results.append({
                    "tool": tc["name"],
                    "result": result,
                })
                state.actions_taken.append({
                    "tool": tc["name"],
                    "arguments": tc["arguments"],
                    "result": result,
                })

            # Get follow-up response with tool results
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": f"Tool results: {json.dumps(tool_results)}\n\nPlease respond to the caller based on these results."
            })

            response_text, _ = await self.llm.generate_response(
                system_prompt=system_prompt,
                messages=messages,
            )

        return response_text

    def _generate_rule_based_response(
        self,
        state: ConversationState,
        caller_input: str,
        intent: CallIntent,
    ) -> str:
        """Generate response using rules (fallback when no LLM)"""
        p = self.personality
        caller_name = state.caller.display_name

        # Handle emotional state first
        if state.current_emotion in [EmotionalState.FRUSTRATED, EmotionalState.ANGRY]:
            empathy = p.get_empathy_response(state.current_emotion)
            prefix = f"{empathy} "
        else:
            prefix = ""

        # Generate response based on intent
        if intent == CallIntent.SCHEDULE_APPOINTMENT:
            return f"{prefix}{p.get_acknowledgment()} I'd be happy to help you schedule an appointment. " \
                   f"Do you have a particular loan officer you'd like to meet with, or would you like me to find someone available?"

        elif intent == CallIntent.SPEAK_TO_AGENT:
            if state.caller.assigned_lo_name:
                return f"{prefix}Sure! I can connect you with {state.caller.assigned_lo_name}. " \
                       f"Let me check if they're available. One moment please."
            return f"{prefix}Of course! Do you have a specific person you'd like to speak with, " \
                   f"or can I help direct you to the right department?"

        elif intent == CallIntent.LOAN_STATUS:
            return f"{prefix}I'd be happy to help you check on your loan status. " \
                   f"For security purposes, can you please verify your loan number and the last four digits of your social security number?"

        elif intent == CallIntent.RATE_INQUIRY:
            return f"{prefix}Great question! Rates can vary based on several factors. " \
                   f"Would you like me to schedule a quick consultation with a loan officer who can give you personalized rate information?"

        elif intent == CallIntent.LEAVE_MESSAGE:
            return f"{prefix}{p.get_acknowledgment()} Who would you like me to take a message for?"

        elif intent == CallIntent.CALLBACK_REQUEST:
            return f"{prefix}No problem! I can have someone call you back. " \
                   f"Can you confirm the best number to reach you at, and what time works best?"

        elif intent == CallIntent.COMPLAINT:
            return f"{prefix}I'm sorry to hear you're having an issue. I want to make sure we get this resolved for you. " \
                   f"Would you like me to connect you with a supervisor, or can you tell me more about what happened?"

        else:
            # General/unknown
            if state.turn_count <= 2:
                return f"{p.get_acknowledgment()} How can I help you today?"
            return f"I want to make sure I help you with the right thing. " \
                   f"Are you looking to schedule an appointment, check on a loan, or something else?"

    async def _execute_tool(self, tool_name: str, arguments: Dict) -> Any:
        """Execute a tool and return results"""
        if self.tool_executor:
            try:
                return await self.tool_executor(tool_name, **arguments)
            except Exception as e:
                logger.error(f"Tool execution failed: {tool_name} - {e}")
                return {"error": str(e)}
        return {"error": "No tool executor configured"}

    def _update_phase(self, state: ConversationState):
        """Update conversation phase based on state"""
        if state.phase == ConversationPhase.GREETING and state.turn_count > 1:
            if state.primary_intent:
                state.phase = ConversationPhase.INTENT_DISCOVERY
            else:
                state.phase = ConversationPhase.IDENTIFICATION

        elif state.phase == ConversationPhase.INTENT_DISCOVERY:
            if state.primary_intent in [CallIntent.SCHEDULE_APPOINTMENT, CallIntent.LOAN_STATUS]:
                state.phase = ConversationPhase.INFORMATION_GATHERING
            elif state.primary_intent == CallIntent.SPEAK_TO_AGENT:
                state.phase = ConversationPhase.TRANSFER

        elif state.phase == ConversationPhase.INFORMATION_GATHERING:
            # Check if we have enough info to take action
            if state.primary_intent == CallIntent.SCHEDULE_APPOINTMENT:
                if all(k in state.gathered_info for k in ["time_mentions"]):
                    state.phase = ConversationPhase.ACTION_EXECUTION

    async def handle_transfer(
        self,
        call_sid: str,
        target_id: str,
        transfer_type: TransferType = TransferType.WARM,
    ) -> str:
        """Handle call transfer"""
        state = self.conversations.get(call_sid)
        if not state:
            return "I apologize, but I'm having trouble with the transfer. Please hold."

        state.transfer_target = target_id
        state.transfer_type = transfer_type
        state.phase = ConversationPhase.TRANSFER

        if transfer_type == TransferType.WARM:
            return f"I'm going to connect you now. I'll stay on the line to introduce you. One moment please."
        else:
            return f"I'm transferring you now. Thank you for calling {self.personality.company_name}!"

    async def handle_hold(self, call_sid: str) -> str:
        """Put caller on hold"""
        state = self.conversations.get(call_sid)
        if state:
            state.phase = ConversationPhase.ON_HOLD
            state.hold_started_at = datetime.now()

        return "I'm going to put you on a brief hold while I look into this. I'll be right back with you."

    async def return_from_hold(self, call_sid: str, update: str = None) -> str:
        """Return from hold with optional update"""
        state = self.conversations.get(call_sid)
        if not state:
            return "Thank you for holding. How can I help you?"

        hold_duration = 0
        if state.hold_started_at:
            hold_duration = (datetime.now() - state.hold_started_at).seconds

        state.hold_started_at = None
        caller_name = state.caller.display_name

        if hold_duration > 60:
            prefix = f"Thank you so much for your patience, {caller_name}. I appreciate you holding."
        else:
            prefix = f"Thanks for holding, {caller_name}."

        if update:
            return f"{prefix} {update}"
        return f"{prefix} I have that information for you now."

    async def end_conversation(
        self,
        call_sid: str,
        reason: str = "caller_hangup",
    ) -> Dict:
        """End conversation and return summary"""
        state = self.conversations.pop(call_sid, None)
        if not state:
            return {"error": "Conversation not found"}

        return {
            "call_sid": call_sid,
            "duration_seconds": state.duration_seconds,
            "turn_count": state.turn_count,
            "primary_intent": state.primary_intent.value if state.primary_intent else None,
            "caller_name": state.caller.full_name,
            "caller_phone": state.caller.phone_number,
            "is_existing_customer": state.caller.is_existing_customer,
            "actions_taken": state.actions_taken,
            "appointment_scheduled": state.appointment_scheduled,
            "callback_scheduled": state.is_callback_scheduled,
            "message_left": state.message_left,
            "transferred": state.transfer_target is not None,
            "end_reason": reason,
        }

    def get_conversation_state(self, call_sid: str) -> Optional[ConversationState]:
        """Get current conversation state"""
        return self.conversations.get(call_sid)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_receptionist(
    company_name: str = "Perennia Mortgage",
    receptionist_name: str = "Sarah",
    llm_provider: str = "claude",
    tool_executor: Callable = None,
    **personality_kwargs,
) -> ConversationEngine:
    """
    Factory function to create a configured AI receptionist.

    Args:
        company_name: Your company name
        receptionist_name: Name for the AI receptionist
        llm_provider: "claude" or "openai"
        tool_executor: Async function to execute tools
        **personality_kwargs: Additional personality configuration

    Returns:
        Configured ConversationEngine
    """
    personality = ReceptionistPersonality(
        name=receptionist_name,
        company_name=company_name,
        **personality_kwargs,
    )

    return ConversationEngine(
        personality=personality,
        llm_provider=llm_provider,
        tool_executor=tool_executor,
    )


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def demo():
        # Create receptionist
        receptionist = create_receptionist(
            company_name="Perennia Mortgage",
            receptionist_name="Sarah",
        )

        # Simulate a call
        call_sid = "CA123456"
        caller_phone = "+15551234567"

        # Start call
        state, greeting = await receptionist.start_conversation(
            call_sid=call_sid,
            caller_phone=caller_phone,
            caller_id_name="John Smith",
        )
        print(f"Sarah: {greeting}\n")

        # Simulate conversation
        test_inputs = [
            "Hi, I'd like to schedule an appointment with a loan officer",
            "I'm looking to refinance my home",
            "How about tomorrow afternoon?",
        ]

        for caller_input in test_inputs:
            print(f"Caller: {caller_input}")
            response = await receptionist.process_input(call_sid, caller_input)
            print(f"Sarah: {response}\n")

        # End call
        summary = await receptionist.end_conversation(call_sid)
        print(f"\nCall Summary: {json.dumps(summary, indent=2)}")

    asyncio.run(demo())
