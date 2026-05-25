"""
Live Call Whisper Service

Real-time AI-powered suggestions during phone calls.
Part of the Conversation Intelligence module.

Features:
- Real-time transcription analysis
- Context-aware suggestions
- Objection handling tips
- Product recommendations
- Compliance reminders
- Next best action prompts
"""

import os
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque

from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Whisper delivery SLA targets
WHISPER_LATENCY_TARGET_MS = 2000  # Max acceptable latency: trigger to delivery
WHISPER_LATENCY_WARNING_MS = 1500  # Warn if latency exceeds this threshold
WHISPER_PROCESSING_BUDGET_MS = 500  # Max time for local processing before LLM call
LATENCY_WINDOW_SIZE = 200  # Rolling window size for latency tracking


class WhisperType(str, Enum):
    """Types of whisper suggestions."""
    TALKING_POINT = "talking_point"
    OBJECTION_HANDLER = "objection_handler"
    PRODUCT_RECOMMENDATION = "product_recommendation"
    COMPLIANCE_REMINDER = "compliance_reminder"
    NEXT_ACTION = "next_action"
    RATE_INFO = "rate_info"
    QUESTION_PROMPT = "question_prompt"
    CLOSING_TECHNIQUE = "closing_technique"
    RAPPORT_BUILDER = "rapport_builder"
    WARNING = "warning"
    CALCULATOR_SUGGESTION = "calculator_suggestion"


class WhisperPriority(str, Enum):
    """Priority levels for whispers."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Whisper:
    """A single whisper suggestion."""
    id: str
    type: WhisperType
    priority: WhisperPriority
    title: str
    content: str
    context: str  # What triggered this whisper
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    dismissed: bool = False
    used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "priority": self.priority.value,
            "title": self.title,
            "content": self.content,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "dismissed": self.dismissed,
            "used": self.used,
        }


@dataclass
class CallContext:
    """Context about the current call."""
    call_id: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    caller_name: str = ""
    caller_type: str = "prospect"  # prospect, client, partner
    loan_purpose: Optional[str] = None
    loan_type: Optional[str] = None
    loan_amount: Optional[float] = None
    credit_score: Optional[int] = None
    property_type: Optional[str] = None
    call_stage: str = "opening"  # opening, discovery, presentation, objection, closing
    topics_discussed: List[str] = field(default_factory=list)
    objections_raised: List[str] = field(default_factory=list)
    questions_asked: List[str] = field(default_factory=list)
    sentiment: str = "neutral"  # positive, neutral, negative, frustrated
    duration_seconds: int = 0


@dataclass
class TranscriptSegment:
    """A segment of call transcript."""
    speaker: str  # "agent" or "caller"
    text: str
    timestamp: datetime
    confidence: float = 1.0


@dataclass
class LatencyRecord:
    """Single latency measurement for a whisper generation cycle."""
    call_id: str
    trigger_to_generated_ms: float
    generated_to_delivered_ms: float
    total_ms: float
    whisper_count: int
    recorded_at: float  # time.monotonic() value


class WhisperLatencyTracker:
    """Tracks whisper delivery latency with rolling statistics."""

    def __init__(self, window_size: int = LATENCY_WINDOW_SIZE):
        self._records: deque = deque(maxlen=window_size)
        self._sla_violations: int = 0
        self._sla_warnings: int = 0
        self._total_measurements: int = 0

    def record(self, record: LatencyRecord) -> None:
        """Record a latency measurement, logging warnings/errors against SLA."""
        self._records.append(record)
        self._total_measurements += 1

        if record.total_ms > WHISPER_LATENCY_TARGET_MS:
            self._sla_violations += 1
            logger.error(
                "Whisper latency SLA VIOLATION: %.1fms (target %dms) "
                "call=%s trigger_to_gen=%.1fms gen_to_deliver=%.1fms whispers=%d",
                record.total_ms, WHISPER_LATENCY_TARGET_MS, record.call_id,
                record.trigger_to_generated_ms, record.generated_to_delivered_ms,
                record.whisper_count,
            )
        elif record.total_ms > WHISPER_LATENCY_WARNING_MS:
            self._sla_warnings += 1
            logger.warning(
                "Whisper latency WARNING: %.1fms (warning %dms) "
                "call=%s trigger_to_gen=%.1fms gen_to_deliver=%.1fms whispers=%d",
                record.total_ms, WHISPER_LATENCY_WARNING_MS, record.call_id,
                record.trigger_to_generated_ms, record.generated_to_delivered_ms,
                record.whisper_count,
            )

    @property
    def avg_total_ms(self) -> float:
        """Running average total latency across the window."""
        if not self._records:
            return 0.0
        return sum(r.total_ms for r in self._records) / len(self._records)

    @property
    def avg_generation_ms(self) -> float:
        """Running average trigger-to-generated latency."""
        if not self._records:
            return 0.0
        return sum(r.trigger_to_generated_ms for r in self._records) / len(self._records)

    @property
    def avg_delivery_ms(self) -> float:
        """Running average generated-to-delivered latency."""
        if not self._records:
            return 0.0
        return sum(r.generated_to_delivered_ms for r in self._records) / len(self._records)

    @property
    def p95_total_ms(self) -> float:
        """95th percentile total latency."""
        if not self._records:
            return 0.0
        sorted_vals = sorted(r.total_ms for r in self._records)
        idx = int(len(sorted_vals) * 0.95)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    @property
    def sla_compliance_pct(self) -> float:
        """Percentage of measurements within SLA target."""
        if self._total_measurements == 0:
            return 100.0
        return ((self._total_measurements - self._sla_violations) / self._total_measurements) * 100.0

    def get_stats(self) -> Dict[str, Any]:
        """Return full latency statistics snapshot."""
        return {
            "total_measurements": self._total_measurements,
            "window_size": len(self._records),
            "avg_total_ms": round(self.avg_total_ms, 1),
            "avg_generation_ms": round(self.avg_generation_ms, 1),
            "avg_delivery_ms": round(self.avg_delivery_ms, 1),
            "p95_total_ms": round(self.p95_total_ms, 1),
            "sla_target_ms": WHISPER_LATENCY_TARGET_MS,
            "sla_warning_ms": WHISPER_LATENCY_WARNING_MS,
            "sla_violations": self._sla_violations,
            "sla_warnings": self._sla_warnings,
            "sla_compliance_pct": round(self.sla_compliance_pct, 1),
        }


class LiveCallWhisperService:
    """Service for providing real-time AI whispers during calls."""

    def __init__(self, db=None):
        self.db = db
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.active_calls: Dict[str, CallContext] = {}
        self.call_transcripts: Dict[str, List[TranscriptSegment]] = {}
        self.call_whispers: Dict[str, List[Whisper]] = {}
        self.latency_tracker = WhisperLatencyTracker()

        # Rate and product info for quick reference
        self.current_rates = {
            "conventional_30": 6.875,
            "conventional_15": 6.125,
            "fha_30": 6.625,
            "va_30": 6.375,
            "jumbo_30": 7.125,
        }

        # Common objection patterns
        self.objection_patterns = [
            ("rate", ["rate is too high", "better rate", "lower rate", "rate shopping"]),
            ("timing", ["not ready", "waiting", "bad time", "think about it"]),
            ("fees", ["too expensive", "closing costs", "fees are high"]),
            ("competition", ["other lender", "another quote", "shopping around"]),
            ("credit", ["credit score", "credit issues", "improve credit"]),
            ("down_payment", ["down payment", "not enough saved", "cash"]),
        ]

    async def start_call(
        self,
        call_id: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        caller_info: Optional[Dict] = None,
    ) -> CallContext:
        """Initialize a new call session."""
        context = CallContext(
            call_id=call_id,
            lead_id=lead_id,
            loan_id=loan_id,
            caller_name=caller_info.get("name", "") if caller_info else "",
            caller_type=caller_info.get("type", "prospect") if caller_info else "prospect",
            loan_purpose=caller_info.get("loan_purpose") if caller_info else None,
            loan_type=caller_info.get("loan_type") if caller_info else None,
            loan_amount=caller_info.get("loan_amount") if caller_info else None,
            credit_score=caller_info.get("credit_score") if caller_info else None,
        )

        self.active_calls[call_id] = context
        self.call_transcripts[call_id] = []
        self.call_whispers[call_id] = []

        # Generate opening whispers
        opening_whispers = await self._generate_opening_whispers(context)
        self.call_whispers[call_id].extend(opening_whispers)

        return context

    async def process_transcript(
        self,
        call_id: str,
        speaker: str,
        text: str,
        confidence: float = 1.0,
    ) -> List[Whisper]:
        """Process a new transcript segment and generate whispers.

        Instruments the full trigger-to-generation latency and returns
        a `_generation_ended_at` attribute on the returned list so the
        caller (route/WebSocket) can measure delivery time separately.
        """
        t_trigger = time.monotonic()

        if call_id not in self.active_calls:
            logger.warning(f"Call {call_id} not found")
            return []

        context = self.active_calls[call_id]

        # Add to transcript history
        segment = TranscriptSegment(
            speaker=speaker,
            text=text,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence,
        )
        self.call_transcripts[call_id].append(segment)

        # Update call duration
        if len(self.call_transcripts[call_id]) > 1:
            first_segment = self.call_transcripts[call_id][0]
            context.duration_seconds = int((segment.timestamp - first_segment.timestamp).total_seconds())

        # Analyze the transcript segment
        new_whispers = []

        # Check for objections (caller speech)
        if speaker == "caller":
            objection_whispers = await self._detect_objections(context, text)
            new_whispers.extend(objection_whispers)

            # Detect sentiment changes
            sentiment_whisper = await self._detect_sentiment(context, text)
            if sentiment_whisper:
                new_whispers.append(sentiment_whisper)

            # Detect questions from caller
            question_whispers = await self._detect_questions(context, text)
            new_whispers.extend(question_whispers)

            # Detect calculator opportunities
            calculator_whisper = self._detect_calculator_opportunities(context, text)
            if calculator_whisper:
                new_whispers.append(calculator_whisper)

        # Check for opportunities and suggestions
        if speaker == "agent":
            # Check if agent is missing opportunities
            opportunity_whispers = await self._detect_opportunities(context, text)
            new_whispers.extend(opportunity_whispers)

        # Update call stage based on conversation flow
        self._update_call_stage(context, speaker, text)

        # Generate stage-specific whispers
        stage_whispers = await self._generate_stage_whispers(context)
        new_whispers.extend(stage_whispers)

        # Store whispers
        self.call_whispers[call_id].extend(new_whispers)

        # Record generation latency — delivery timing is completed by the caller
        t_generated = time.monotonic()
        generation_ms = (t_generated - t_trigger) * 1000

        if generation_ms > WHISPER_PROCESSING_BUDGET_MS and new_whispers:
            logger.warning(
                "Whisper generation exceeded processing budget: %.1fms (budget %dms) call=%s whispers=%d",
                generation_ms, WHISPER_PROCESSING_BUDGET_MS, call_id, len(new_whispers),
            )

        # Attach timing metadata so the route layer can finalize the measurement
        result = list(new_whispers)
        result._trigger_monotonic = t_trigger  # type: ignore[attr-defined]
        result._generated_monotonic = t_generated  # type: ignore[attr-defined]
        return result

    def record_delivery_latency(self, call_id: str, trigger_mono: float, generated_mono: float, whisper_count: int) -> None:
        """Record final delivery latency after whispers have been sent to the client.

        Called by route/WebSocket handlers after broadcasting whispers.
        """
        t_delivered = time.monotonic()
        trigger_to_gen_ms = (generated_mono - trigger_mono) * 1000
        gen_to_deliver_ms = (t_delivered - generated_mono) * 1000
        total_ms = (t_delivered - trigger_mono) * 1000

        record = LatencyRecord(
            call_id=call_id,
            trigger_to_generated_ms=trigger_to_gen_ms,
            generated_to_delivered_ms=gen_to_deliver_ms,
            total_ms=total_ms,
            whisper_count=whisper_count,
            recorded_at=t_delivered,
        )
        self.latency_tracker.record(record)

    async def get_ai_whisper(
        self,
        call_id: str,
        prompt: str,
    ) -> Optional[Whisper]:
        """Get an AI-generated whisper based on a specific prompt."""
        t_trigger = time.monotonic()

        if call_id not in self.active_calls:
            return None

        context = self.active_calls[call_id]
        recent_transcript = self._get_recent_transcript(call_id, segments=10)

        try:
            from services.llm_gateway import llm_gateway
            llm_result = llm_gateway.complete_sync(
                intent="coaching",
                system_prompt="You are a real-time sales coach for mortgage loan officers. Provide brief, actionable suggestions that can be used immediately during a call. Keep responses under 50 words. Be direct and practical.",
                messages=[
                    {
                        "role": "user",
                        "content": f"""Call context:
- Caller: {context.caller_name} ({context.caller_type})
- Loan Purpose: {context.loan_purpose or 'Unknown'}
- Loan Amount: ${context.loan_amount:,.0f} if context.loan_amount else 'Unknown'
- Credit Score: {context.credit_score or 'Unknown'}
- Call Stage: {context.call_stage}
- Sentiment: {context.sentiment}

Recent conversation:
{recent_transcript}

Request: {prompt}

Provide a brief, actionable suggestion:"""
                    }
                ],
                max_tokens_override=300,
            )
            response_text = llm_result.text

            import uuid
            whisper = Whisper(
                id=str(uuid.uuid4())[:8],
                type=WhisperType.TALKING_POINT,
                priority=WhisperPriority.MEDIUM,
                title="AI Suggestion",
                content=response_text,
                context=prompt,
            )

            self.call_whispers[call_id].append(whisper)

            t_generated = time.monotonic()
            generation_ms = (t_generated - t_trigger) * 1000
            if generation_ms > WHISPER_LATENCY_TARGET_MS:
                logger.error(
                    "AI whisper generation alone exceeded SLA: %.1fms call=%s",
                    generation_ms, call_id,
                )
            elif generation_ms > WHISPER_LATENCY_WARNING_MS:
                logger.warning(
                    "AI whisper generation approaching SLA limit: %.1fms call=%s",
                    generation_ms, call_id,
                )

            # Attach timing metadata for delivery-layer measurement
            whisper._trigger_monotonic = t_trigger  # type: ignore[attr-defined]
            whisper._generated_monotonic = t_generated  # type: ignore[attr-defined]
            return whisper

        except Exception as e:
            logger.error(f"Failed to generate AI whisper: {e}")
            return None

    async def end_call(self, call_id: str) -> Dict[str, Any]:
        """End a call session and return summary."""
        if call_id not in self.active_calls:
            return {"error": "Call not found"}

        context = self.active_calls[call_id]
        whispers = self.call_whispers.get(call_id, [])
        transcript = self.call_transcripts.get(call_id, [])

        summary = {
            "call_id": call_id,
            "duration_seconds": context.duration_seconds,
            "call_stage_reached": context.call_stage,
            "sentiment": context.sentiment,
            "topics_discussed": context.topics_discussed,
            "objections_raised": context.objections_raised,
            "whispers_generated": len(whispers),
            "whispers_used": len([w for w in whispers if w.used]),
            "transcript_segments": len(transcript),
            "latency": self.latency_tracker.get_stats(),
        }

        # Cleanup
        del self.active_calls[call_id]
        del self.call_transcripts[call_id]
        del self.call_whispers[call_id]

        return summary

    def get_active_whispers(self, call_id: str) -> List[Whisper]:
        """Get all active (non-dismissed) whispers for a call."""
        whispers = self.call_whispers.get(call_id, [])
        return [w for w in whispers if not w.dismissed]

    def dismiss_whisper(self, call_id: str, whisper_id: str) -> bool:
        """Dismiss a whisper."""
        whispers = self.call_whispers.get(call_id, [])
        for whisper in whispers:
            if whisper.id == whisper_id:
                whisper.dismissed = True
                return True
        return False

    def mark_whisper_used(self, call_id: str, whisper_id: str) -> bool:
        """Mark a whisper as used by the agent."""
        whispers = self.call_whispers.get(call_id, [])
        for whisper in whispers:
            if whisper.id == whisper_id:
                whisper.used = True
                return True
        return False

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _generate_opening_whispers(self, context: CallContext) -> List[Whisper]:
        """Generate whispers for call opening."""
        import uuid
        whispers = []

        # Personalized greeting if we have caller info
        if context.caller_name:
            whispers.append(Whisper(
                id=str(uuid.uuid4())[:8],
                type=WhisperType.RAPPORT_BUILDER,
                priority=WhisperPriority.HIGH,
                title="Personalized Opening",
                content=f"Use their name: 'Hi {context.caller_name}, thank you for calling...'",
                context="Call started",
            ))

        # Loan context whisper
        if context.loan_purpose:
            purpose_tips = {
                "purchase": "Ask about their timeline and if they've found a property yet.",
                "refinance": "Ask what they're hoping to achieve - lower payment, cash out, or shorter term?",
                "cash_out": "Understand how they plan to use the funds - home improvement, debt consolidation, etc.",
            }
            tip = purpose_tips.get(context.loan_purpose, "Confirm their loan goals early in the call.")
            whispers.append(Whisper(
                id=str(uuid.uuid4())[:8],
                type=WhisperType.QUESTION_PROMPT,
                priority=WhisperPriority.MEDIUM,
                title=f"{context.loan_purpose.title()} Discovery",
                content=tip,
                context="Loan purpose context",
            ))

        # Credit score context
        if context.credit_score:
            if context.credit_score >= 740:
                whispers.append(Whisper(
                    id=str(uuid.uuid4())[:8],
                    type=WhisperType.TALKING_POINT,
                    priority=WhisperPriority.LOW,
                    title="Excellent Credit",
                    content="Great credit score! Mention they qualify for the best rates available.",
                    context="Credit score analysis",
                ))
            elif context.credit_score < 620:
                whispers.append(Whisper(
                    id=str(uuid.uuid4())[:8],
                    type=WhisperType.PRODUCT_RECOMMENDATION,
                    priority=WhisperPriority.HIGH,
                    title="FHA May Be Best Fit",
                    content="Consider FHA loan - more flexible credit requirements. Minimum 580 for 3.5% down.",
                    context="Credit score analysis",
                ))

        return whispers

    async def _detect_objections(self, context: CallContext, text: str) -> List[Whisper]:
        """Detect objections in caller speech and generate handling tips."""
        import uuid
        whispers = []
        text_lower = text.lower()

        objection_handlers = {
            "rate": {
                "title": "Rate Objection Detected",
                "content": """Handle rate objection:
1. Acknowledge their concern
2. Ask what rate they're comparing to
3. Explain total cost of loan vs just rate
4. Mention our rate lock options
5. Highlight service and closing speed value""",
                "priority": WhisperPriority.HIGH,
            },
            "timing": {
                "title": "Timing Objection",
                "content": """They're not ready yet:
1. Ask what would need to change
2. Offer to stay in touch with rate alerts
3. Discuss pre-approval benefits (no commitment)
4. Mention how market timing rarely works out""",
                "priority": WhisperPriority.MEDIUM,
            },
            "fees": {
                "title": "Fee Objection",
                "content": """Address fee concerns:
1. Break down what each fee covers
2. Compare to industry averages
3. Discuss lender credit options
4. Show total cost over loan life
5. Mention no-cost refinance options if applicable""",
                "priority": WhisperPriority.HIGH,
            },
            "competition": {
                "title": "Competitive Situation",
                "content": """They're shopping around:
1. Ask what's important beyond rate
2. Highlight our unique value (speed, service, tech)
3. Offer to review their other quote
4. Discuss our rate match policy if applicable
5. Create urgency around lock timing""",
                "priority": WhisperPriority.URGENT,
            },
            "credit": {
                "title": "Credit Concerns",
                "content": """Credit score discussion:
1. Explain how scores are used in pricing
2. Discuss rapid rescore options
3. Mention credit improvement strategies
4. Consider FHA or alternative programs
5. Offer credit counseling resources""",
                "priority": WhisperPriority.MEDIUM,
            },
            "down_payment": {
                "title": "Down Payment Concerns",
                "content": """Down payment options:
1. Discuss 3% conventional options
2. Explain FHA 3.5% down
3. Mention VA 0% for veterans
4. Discuss down payment assistance programs
5. Gift fund options from family""",
                "priority": WhisperPriority.MEDIUM,
            },
        }

        for objection_type, patterns in self.objection_patterns:
            for pattern in patterns:
                if pattern in text_lower:
                    handler = objection_handlers.get(objection_type)
                    if handler:
                        # Track objection
                        if objection_type not in context.objections_raised:
                            context.objections_raised.append(objection_type)

                        whispers.append(Whisper(
                            id=str(uuid.uuid4())[:8],
                            type=WhisperType.OBJECTION_HANDLER,
                            priority=handler["priority"],
                            title=handler["title"],
                            content=handler["content"],
                            context=f"Detected: '{pattern}' in caller speech",
                        ))
                    break

        return whispers

    async def _detect_sentiment(self, context: CallContext, text: str) -> Optional[Whisper]:
        """Detect sentiment changes in caller speech."""
        import uuid
        text_lower = text.lower()

        # Frustration indicators
        frustration_words = ["frustrated", "annoyed", "ridiculous", "waste of time", "forget it"]
        for word in frustration_words:
            if word in text_lower:
                context.sentiment = "frustrated"
                return Whisper(
                    id=str(uuid.uuid4())[:8],
                    type=WhisperType.WARNING,
                    priority=WhisperPriority.URGENT,
                    title="Frustration Detected",
                    content="Slow down, acknowledge their frustration, and ask what would help resolve their concern.",
                    context=f"Detected frustration indicator: '{word}'",
                )

        # Positive indicators
        positive_words = ["great", "perfect", "sounds good", "let's do it", "ready to move forward"]
        for word in positive_words:
            if word in text_lower:
                context.sentiment = "positive"
                return Whisper(
                    id=str(uuid.uuid4())[:8],
                    type=WhisperType.CLOSING_TECHNIQUE,
                    priority=WhisperPriority.HIGH,
                    title="Positive Signal!",
                    content="They're ready! Move to next steps: 'Great! Let me get your application started...'",
                    context=f"Positive signal: '{word}'",
                )

        return None

    async def _detect_questions(self, context: CallContext, text: str) -> List[Whisper]:
        """Detect questions from caller and provide answer guidance."""
        import uuid
        whispers = []
        text_lower = text.lower()

        question_answers = {
            "what is your rate": {
                "title": "Rate Question",
                "content": f"Current rates: Conv 30yr {self.current_rates['conventional_30']}%, 15yr {self.current_rates['conventional_15']}%, FHA {self.current_rates['fha_30']}%. Rates depend on credit, LTV, and loan type.",
                "type": WhisperType.RATE_INFO,
            },
            "how long does it take": {
                "title": "Timeline Question",
                "content": "Typical timeline: 21-30 days from application to closing. Pre-approval in 24-48 hours. Emphasize our track record of on-time closings.",
                "type": WhisperType.TALKING_POINT,
            },
            "what do i need": {
                "title": "Documentation Question",
                "content": "Standard docs: 2 years tax returns, 2 months bank statements, recent pay stubs, ID. For self-employed: P&L and business returns.",
                "type": WhisperType.TALKING_POINT,
            },
            "how much can i afford": {
                "title": "Affordability Question",
                "content": "Discuss DTI limits (43% typically). Monthly payment = principal, interest, taxes, insurance. Offer to run quick scenarios.",
                "type": WhisperType.TALKING_POINT,
            },
            "what are the fees": {
                "title": "Fees Question",
                "content": "Typical closing costs 2-5% of loan. Break down: origination, appraisal, title, prepaid taxes/insurance. Offer to provide Loan Estimate.",
                "type": WhisperType.TALKING_POINT,
            },
            "can i lock": {
                "title": "Rate Lock Question",
                "content": "Lock options: 30, 45, 60 days typical. Longer locks cost more. Explain float-down options if available. Lock after full application.",
                "type": WhisperType.RATE_INFO,
            },
        }

        for question_pattern, answer in question_answers.items():
            if question_pattern in text_lower or text.strip().endswith("?"):
                if any(word in text_lower for word in question_pattern.split()):
                    context.questions_asked.append(question_pattern)
                    whispers.append(Whisper(
                        id=str(uuid.uuid4())[:8],
                        type=answer["type"],
                        priority=WhisperPriority.HIGH,
                        title=answer["title"],
                        content=answer["content"],
                        context=f"Question detected: {question_pattern}",
                    ))
                    break

        return whispers

    def _detect_calculator_opportunities(self, context: CallContext, text: str) -> Optional[Whisper]:
        """Detect calculator opportunities and return pre-calculated whisper."""
        try:
            from .live_call_whisper_calculator import calculator_whisper_detector
            return calculator_whisper_detector.detect_calculator_opportunity(text, context)
        except Exception as e:
            logger.warning(f"Calculator whisper detection error: {e}")
            return None

    async def _detect_opportunities(self, context: CallContext, text: str) -> List[Whisper]:
        """Detect opportunities the agent might be missing."""
        import uuid
        whispers = []

        # Check if agent has been talking too long without asking questions
        recent = self.call_transcripts.get(context.call_id, [])[-5:]
        agent_segments = [s for s in recent if s.speaker == "agent"]

        if len(agent_segments) >= 4:
            whispers.append(Whisper(
                id=str(uuid.uuid4())[:8],
                type=WhisperType.QUESTION_PROMPT,
                priority=WhisperPriority.MEDIUM,
                title="Ask a Question",
                content="You've been talking a lot. Ask an open-ended question to engage them: 'What's most important to you in this process?'",
                context="Agent talking ratio high",
            ))

        return whispers

    def _update_call_stage(self, context: CallContext, speaker: str, text: str) -> None:
        """Update the call stage based on conversation content."""
        text_lower = text.lower()

        # Detect stage transitions
        discovery_signals = ["tell me about", "what are you looking", "how can i help"]
        presentation_signals = ["rate would be", "payment would be", "options available"]
        objection_signals = ["but", "however", "concern", "worried about"]
        closing_signals = ["ready to", "next steps", "get started", "application"]

        if context.call_stage == "opening":
            if any(signal in text_lower for signal in discovery_signals):
                context.call_stage = "discovery"
        elif context.call_stage == "discovery":
            if any(signal in text_lower for signal in presentation_signals):
                context.call_stage = "presentation"
        elif context.call_stage == "presentation":
            if speaker == "caller" and any(signal in text_lower for signal in objection_signals):
                context.call_stage = "objection"
        if any(signal in text_lower for signal in closing_signals):
            context.call_stage = "closing"

    async def _generate_stage_whispers(self, context: CallContext) -> List[Whisper]:
        """Generate stage-specific coaching whispers."""
        import uuid
        whispers = []

        # Only generate periodically (every 60 seconds roughly)
        if context.duration_seconds % 60 != 0 or context.duration_seconds == 0:
            return []

        stage_tips = {
            "opening": "Build rapport before diving into business. Ask about their day or reference something personal.",
            "discovery": "Ask about their timeline, motivation, and concerns. Listen more than you talk.",
            "presentation": "Tie features to their specific needs. Use their words when presenting solutions.",
            "objection": "Acknowledge, isolate, and address objections. Don't be defensive.",
            "closing": "Summarize benefits, confirm next steps, and set clear expectations.",
        }

        tip = stage_tips.get(context.call_stage)
        if tip:
            whispers.append(Whisper(
                id=str(uuid.uuid4())[:8],
                type=WhisperType.TALKING_POINT,
                priority=WhisperPriority.LOW,
                title=f"{context.call_stage.title()} Stage Tip",
                content=tip,
                context=f"Call duration: {context.duration_seconds}s",
            ))

        return whispers

    def _get_recent_transcript(self, call_id: str, segments: int = 5) -> str:
        """Get recent transcript as formatted string."""
        transcript = self.call_transcripts.get(call_id, [])
        recent = transcript[-segments:] if len(transcript) > segments else transcript

        lines = []
        for segment in recent:
            speaker_label = "Agent" if segment.speaker == "agent" else "Caller"
            lines.append(f"{speaker_label}: {segment.text}")

        return "\n".join(lines)

    async def get_compliance_reminders(self, context: CallContext) -> List[Whisper]:
        """Get compliance reminders based on call context."""
        import uuid
        whispers = []

        # RESPA reminder if discussing fees
        if "fees" in context.topics_discussed:
            whispers.append(Whisper(
                id=str(uuid.uuid4())[:8],
                type=WhisperType.COMPLIANCE_REMINDER,
                priority=WhisperPriority.HIGH,
                title="RESPA Reminder",
                content="Don't quote exact closing costs without providing Loan Estimate. Say 'approximately' or 'in the range of'.",
                context="Fee discussion detected",
            ))

        # Fair lending reminder
        if context.duration_seconds > 300:  # 5 minutes
            whispers.append(Whisper(
                id=str(uuid.uuid4())[:8],
                type=WhisperType.COMPLIANCE_REMINDER,
                priority=WhisperPriority.MEDIUM,
                title="Fair Lending",
                content="Ensure consistent treatment. Don't make assumptions based on protected characteristics.",
                context="Long call compliance check",
            ))

        return whispers
