"""
===============================================================================
PERENNIA AI RECEPTIONIST - PART 1: CONVERSATION ENGINE
===============================================================================
Core AI conversation engine using Claude/GPT for intelligent call handling.

Features:
- Multi-turn conversation management
- Intent detection and entity extraction
- Context-aware responses
- Mortgage domain expertise
===============================================================================
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND TYPES
# =============================================================================

class CallIntent(str, Enum):
    """Detected caller intents."""
    RATE_INQUIRY = "rate_inquiry"
    NEW_APPLICATION = "new_application"
    EXISTING_LOAN_STATUS = "existing_loan_status"
    REFINANCE = "refinance"
    PREAPPROVAL = "preapproval"
    DOCUMENT_QUESTION = "document_question"
    SPEAK_TO_LO = "speak_to_lo"
    SCHEDULE_APPOINTMENT = "schedule_appointment"
    GENERAL_QUESTION = "general_question"
    COMPLAINT = "complaint"
    UNKNOWN = "unknown"


class CallOutcome(str, Enum):
    """Possible call outcomes."""
    APPOINTMENT_SCHEDULED = "appointment_scheduled"
    CALLBACK_REQUESTED = "callback_requested"
    TRANSFERRED_TO_LO = "transferred_to_lo"
    INFORMATION_PROVIDED = "information_provided"
    LEAD_CAPTURED = "lead_captured"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"
    COMPLETED = "completed"


class SentimentLevel(str, Enum):
    """Caller sentiment levels."""
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CallerInfo:
    """Information about the caller."""
    phone: str
    name: Optional[str] = None
    email: Optional[str] = None
    is_existing_customer: bool = False
    lead_id: Optional[str] = None
    loan_id: Optional[str] = None
    previous_interactions: int = 0


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    role: str  # "caller" or "ai"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    intent: Optional[CallIntent] = None
    confidence: float = 0.0
    entities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationState:
    """Current state of the conversation."""
    call_sid: str
    caller_info: CallerInfo
    turns: List[ConversationTurn] = field(default_factory=list)
    detected_intent: CallIntent = CallIntent.UNKNOWN
    sentiment: SentimentLevel = SentimentLevel.NEUTRAL
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    needs_transfer: bool = False
    transfer_reason: Optional[str] = None
    outcome: Optional[CallOutcome] = None
    started_at: datetime = field(default_factory=datetime.now)

    def add_turn(self, role: str, content: str, **kwargs) -> ConversationTurn:
        """Add a conversation turn."""
        turn = ConversationTurn(role=role, content=content, **kwargs)
        self.turns.append(turn)
        return turn

    def get_context(self, max_turns: int = 10) -> str:
        """Get conversation context for AI."""
        recent_turns = self.turns[-max_turns:]
        context_lines = []
        for turn in recent_turns:
            prefix = "Caller:" if turn.role == "caller" else "AI:"
            context_lines.append(f"{prefix} {turn.content}")
        return "\n".join(context_lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "call_sid": self.call_sid,
            "caller_phone": self.caller_info.phone,
            "caller_name": self.caller_info.name,
            "intent": self.detected_intent.value,
            "sentiment": self.sentiment.value,
            "entities": self.extracted_entities,
            "turn_count": len(self.turns),
            "duration_seconds": (datetime.now() - self.started_at).total_seconds(),
            "outcome": self.outcome.value if self.outcome else None,
        }


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

RECEPTIONIST_SYSTEM_PROMPT = """You are the AI receptionist for {company_name}, a mortgage company. Your role is to:

1. Greet callers warmly and professionally
2. Understand their needs (rate inquiries, application status, new applications, etc.)
3. Collect necessary information (name, phone, loan purpose, timeline)
4. Schedule appointments or callbacks with loan officers when appropriate
5. Answer common mortgage questions
6. Transfer to a human when needed

IMPORTANT GUIDELINES:
- Be concise - phone conversations should be brief
- Ask one question at a time
- Confirm information back to the caller
- If you don't know something, offer to connect them with a loan officer
- Be empathetic, especially with stressed callers
- Never discuss specific rates without qualifying the caller first
- Collect: name, phone, email, loan purpose, property type, timeline, credit range

CURRENT RATES (general guidance only):
- 30-year fixed: Around 6.5-7.5%
- 15-year fixed: Around 5.5-6.5%
- FHA loans: Around 6.0-7.0%
- VA loans: Around 6.0-7.0%
Always clarify that actual rates depend on credit score, loan amount, and other factors.

TRANSFER TRIGGERS (immediately offer to transfer):
- Caller asks to speak to a specific person
- Caller is upset or frustrated
- Complex loan scenarios
- Legal or compliance questions
- Caller has been waiting or calling back multiple times

You are speaking on the PHONE - keep responses SHORT (1-2 sentences max).
"""

INTENT_DETECTION_PROMPT = """Analyze this caller statement and determine their intent.

Caller said: "{text}"

Previous context:
{context}

Classify the intent as one of:
- rate_inquiry: Asking about current mortgage rates
- new_application: Wants to apply for a new mortgage
- existing_loan_status: Checking on an existing loan application
- refinance: Interested in refinancing
- preapproval: Wants to get pre-approved
- document_question: Questions about required documents
- speak_to_lo: Wants to speak to a loan officer directly
- schedule_appointment: Wants to schedule a meeting/call
- general_question: General mortgage questions
- complaint: Has a complaint or issue
- unknown: Cannot determine intent

Also extract any entities mentioned:
- name: Caller's name
- phone: Phone number
- email: Email address
- loan_purpose: purchase, refinance, cash_out, etc.
- property_type: single_family, condo, multi_family, etc.
- loan_amount: Approximate loan amount
- credit_score: Credit score or range
- timeline: When they need the loan

Respond in JSON format:
{{
    "intent": "intent_name",
    "confidence": 0.0-1.0,
    "entities": {{}},
    "sentiment": "positive/neutral/negative",
    "needs_transfer": true/false,
    "transfer_reason": "reason if needs_transfer is true"
}}
"""


# =============================================================================
# CONVERSATION ENGINE
# =============================================================================

class ConversationEngine:
    """
    AI-powered conversation engine for handling phone calls.

    Uses Claude (preferred) or GPT for natural language understanding
    and response generation.
    """

    def __init__(
        self,
        company_name: str = "Perennia Mortgage",
        llm_provider: str = "anthropic",  # or "openai"
    ):
        self.company_name = company_name
        self.llm_provider = llm_provider
        self.conversations: Dict[str, ConversationState] = {}

        # Initialize LLM client
        self._init_llm_client()

        logger.info(f"ConversationEngine initialized with {llm_provider}")

    def _init_llm_client(self):
        """Initialize the LLM client."""
        if self.llm_provider == "anthropic":
            try:
                import anthropic
                self.client = anthropic.Anthropic(
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
                self.model = "claude-sonnet-4-20250514"
                logger.info("Using Anthropic Claude")
            except Exception as e:
                logger.warning(f"Failed to init Anthropic: {e}, falling back to OpenAI")
                self.llm_provider = "openai"
                self._init_llm_client()
        else:
            import openai
            self.client = openai.OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )
            self.model = "gpt-4o"
            logger.info("Using OpenAI GPT-4")

    def start_conversation(
        self,
        call_sid: str,
        caller_phone: str,
        caller_info: Optional[Dict[str, Any]] = None,
    ) -> ConversationState:
        """Start a new conversation."""
        info = CallerInfo(
            phone=caller_phone,
            name=caller_info.get("name") if caller_info else None,
            is_existing_customer=caller_info.get("is_existing") if caller_info else False,
            lead_id=caller_info.get("lead_id") if caller_info else None,
        )

        state = ConversationState(
            call_sid=call_sid,
            caller_info=info,
        )

        self.conversations[call_sid] = state
        logger.info(f"Started conversation {call_sid} for {caller_phone}")

        return state

    def get_conversation(self, call_sid: str) -> Optional[ConversationState]:
        """Get an existing conversation."""
        return self.conversations.get(call_sid)

    def generate_greeting(self, state: ConversationState) -> str:
        """Generate initial greeting."""
        if state.caller_info.is_existing_customer and state.caller_info.name:
            greeting = f"Hello {state.caller_info.name}! Thank you for calling {self.company_name}. How can I help you today?"
        else:
            greeting = f"Thank you for calling {self.company_name}. My name is Alex, your AI assistant. How can I help you today?"

        state.add_turn("ai", greeting)
        return greeting

    async def process_speech(
        self,
        call_sid: str,
        text: str,
    ) -> Dict[str, Any]:
        """
        Process caller speech and generate response.

        Returns:
            {
                "response": "AI response text",
                "intent": "detected intent",
                "confidence": 0.0-1.0,
                "needs_transfer": bool,
                "entities": {...}
            }
        """
        state = self.conversations.get(call_sid)
        if not state:
            logger.error(f"No conversation found for {call_sid}")
            return {
                "response": "I'm sorry, there was an error. Let me transfer you to a representative.",
                "needs_transfer": True,
            }

        # Add caller turn
        state.add_turn("caller", text)

        # Detect intent and extract entities
        analysis = await self._analyze_speech(text, state)

        # Update state
        if analysis.get("intent"):
            state.detected_intent = CallIntent(analysis["intent"])
        if analysis.get("entities"):
            state.extracted_entities.update(analysis["entities"])
        if analysis.get("sentiment"):
            state.sentiment = SentimentLevel(analysis["sentiment"])
        if analysis.get("needs_transfer"):
            state.needs_transfer = True
            state.transfer_reason = analysis.get("transfer_reason")

        # Generate response
        response = await self._generate_response(state, analysis)

        # Add AI turn
        state.add_turn("ai", response, intent=state.detected_intent)

        return {
            "response": response,
            "intent": state.detected_intent.value,
            "confidence": analysis.get("confidence", 0.0),
            "needs_transfer": state.needs_transfer,
            "transfer_reason": state.transfer_reason,
            "entities": state.extracted_entities,
            "sentiment": state.sentiment.value,
        }

    async def _analyze_speech(
        self,
        text: str,
        state: ConversationState,
    ) -> Dict[str, Any]:
        """Analyze speech for intent and entities."""
        prompt = INTENT_DETECTION_PROMPT.format(
            text=text,
            context=state.get_context(max_turns=5),
        )

        try:
            if self.llm_provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                )
                result_text = response.content[0].text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                )
                result_text = response.choices[0].message.content

            # Parse JSON response
            # Find JSON in response
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(result_text[start:end])
            return {"intent": "unknown", "confidence": 0.5}

        except Exception as e:
            logger.error(f"Error analyzing speech: {e}")
            return {"intent": "unknown", "confidence": 0.0}

    async def _generate_response(
        self,
        state: ConversationState,
        analysis: Dict[str, Any],
    ) -> str:
        """Generate AI response based on conversation state."""
        # Check if transfer needed
        if state.needs_transfer:
            return f"I'd be happy to connect you with one of our loan officers. {state.transfer_reason or 'They can better assist you with this.'} Please hold while I transfer your call."

        # Build prompt
        system_prompt = RECEPTIONIST_SYSTEM_PROMPT.format(
            company_name=self.company_name
        )

        # Add context about caller
        context = f"""
Current caller information:
- Phone: {state.caller_info.phone}
- Name: {state.caller_info.name or 'Not provided yet'}
- Existing customer: {'Yes' if state.caller_info.is_existing_customer else 'No'}
- Detected intent: {state.detected_intent.value}
- Sentiment: {state.sentiment.value}
- Information collected: {json.dumps(state.extracted_entities)}

Conversation so far:
{state.get_context()}

Generate your next response (keep it brief - 1-2 sentences):
"""

        try:
            if self.llm_provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=200,
                    system=system_prompt,
                    messages=[{"role": "user", "content": context}],
                )
                return response.content[0].text.strip()
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=200,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": context},
                    ],
                )
                return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I apologize, I'm having trouble understanding. Could you repeat that?"

    def end_conversation(
        self,
        call_sid: str,
        outcome: CallOutcome,
    ) -> Optional[Dict[str, Any]]:
        """End a conversation and return summary."""
        state = self.conversations.get(call_sid)
        if not state:
            return None

        state.outcome = outcome

        summary = {
            "call_sid": call_sid,
            "caller_phone": state.caller_info.phone,
            "caller_name": state.caller_info.name,
            "duration_seconds": (datetime.now() - state.started_at).total_seconds(),
            "turn_count": len(state.turns),
            "intent": state.detected_intent.value,
            "sentiment": state.sentiment.value,
            "outcome": outcome.value,
            "entities": state.extracted_entities,
            "transferred": state.needs_transfer,
            "transcript": [
                {"role": t.role, "content": t.content}
                for t in state.turns
            ],
        }

        # Clean up
        del self.conversations[call_sid]

        logger.info(f"Ended conversation {call_sid}: {outcome.value}")
        return summary


# =============================================================================
# FACTORY
# =============================================================================

def create_engine(
    company_name: str = "Perennia Mortgage",
    llm_provider: Optional[str] = None,
) -> ConversationEngine:
    """
    Create a conversation engine instance.

    Args:
        company_name: Company name for greetings
        llm_provider: "anthropic" or "openai" (auto-detects if None)
    """
    if llm_provider is None:
        # Auto-detect based on available API keys
        if os.getenv("ANTHROPIC_API_KEY"):
            llm_provider = "anthropic"
        elif os.getenv("OPENAI_API_KEY"):
            llm_provider = "openai"
        else:
            raise ValueError("No LLM API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")

    return ConversationEngine(
        company_name=company_name,
        llm_provider=llm_provider,
    )
