"""SMS intent detection — keyword matching with LLM fallback for ambiguous messages."""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    intent: str  # scheduling, qualifying, objection, positive, question, document, greeting, unknown
    confidence: float  # 0.0 - 1.0
    suggested_stage: Optional[str] = None
    entities: Dict = field(default_factory=dict)
    method: str = "keyword"  # keyword or llm


INTENT_PATTERNS = {
    "scheduling": {
        "patterns": [
            r"\b(schedule|appointment|meet|call me|available|when can|set up a time|book|free time|calendar)\b",
        ],
        "suggested_stage": "scheduling",
        "confidence": 0.85,
    },
    "qualifying": {
        "patterns": [
            r"\b(how much|rate|rates|qualify|credit score|down payment|pre-?approv|afford|monthly payment|loan amount|what do i need)\b",
        ],
        "suggested_stage": "qualifying",
        "confidence": 0.8,
    },
    "objection": {
        "patterns": [
            r"\b(not interested|too expensive|bad timing|already working with|stop calling|go away|leave me alone|no thanks|don'?t contact)\b",
        ],
        "suggested_stage": "objection_handling",
        "confidence": 0.9,
    },
    "positive": {
        "patterns": [
            r"\b(yes|interested|tell me more|sounds good|let'?s do it|ready|sign me up|apply|i'?m in|absolutely|perfect)\b",
        ],
        "suggested_stage": "qualifying",
        "confidence": 0.8,
    },
    "question": {
        "patterns": [
            r"^(what|how|why|when|where|can you|do you|is there|are there|will)\b",
            r"\?\s*$",
        ],
        "suggested_stage": "qualifying",
        "confidence": 0.6,
    },
    "document": {
        "patterns": [
            r"\b(upload|document|paystub|pay stub|w-?2|bank statement|tax return|send you|attached|paperwork)\b",
        ],
        "suggested_stage": "qualifying",
        "confidence": 0.8,
    },
    "greeting": {
        "patterns": [
            r"^(hi|hello|hey|good morning|good afternoon|good evening|howdy)\b",
        ],
        "suggested_stage": "greeting",
        "confidence": 0.7,
    },
}

# Pre-compile patterns
_compiled = {}
for intent_name, config in INTENT_PATTERNS.items():
    _compiled[intent_name] = {
        "regexes": [re.compile(p, re.IGNORECASE) for p in config["patterns"]],
        "suggested_stage": config["suggested_stage"],
        "confidence": config["confidence"],
    }


ENTITY_PATTERNS = {
    "dollar_amount": re.compile(r"\$[\d,]+(?:\.\d{2})?|\b\d{3,7}\s*(?:k|thousand|dollars)\b", re.IGNORECASE),
    "credit_score": re.compile(r"\b(?:credit\s+(?:score\s+)?(?:is\s+)?)?([5-8]\d{2})\b"),
    "timeline": re.compile(r"\b(\d+)\s*(month|week|year|day)s?\b", re.IGNORECASE),
    "phone_number": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
}


class SMSIntentDetector:
    """Detects borrower intent from SMS messages."""

    def detect_intent(self, message: str, conversation_context: dict = None) -> IntentResult:
        """Detect intent using keyword matching."""
        if not message or not message.strip():
            return IntentResult(intent="unknown", confidence=0.0)

        message_clean = message.strip()
        best_match = None
        best_confidence = 0.0

        for intent_name, config in _compiled.items():
            for regex in config["regexes"]:
                if regex.search(message_clean):
                    if config["confidence"] > best_confidence:
                        best_confidence = config["confidence"]
                        best_match = intent_name

        # Boost confidence if context aligns
        if best_match and conversation_context:
            current_stage = conversation_context.get("current_stage")
            suggested = _compiled[best_match]["suggested_stage"]
            if current_stage == suggested:
                best_confidence = min(1.0, best_confidence + 0.1)

        if not best_match:
            return IntentResult(intent="unknown", confidence=0.3, method="keyword")

        entities = self._extract_entities(message_clean)

        return IntentResult(
            intent=best_match,
            confidence=best_confidence,
            suggested_stage=_compiled[best_match]["suggested_stage"],
            entities=entities,
            method="keyword",
        )

    async def detect_intent_llm(self, message: str, history: list = None) -> IntentResult:
        """LLM-based intent detection for ambiguous messages."""
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic()

            history_context = ""
            if history:
                recent = history[-5:]
                history_context = "\n".join(
                    f"{'Borrower' if m.get('direction') == 'inbound' else 'AI'}: {m.get('content', '')}"
                    for m in recent
                )

            from agents.anthropic_client import cached_system_block
            model = os.getenv("SMS_AI_MODEL_VERSION", "claude-sonnet-4-6")
            response = await client.messages.create(
                model=model,
                max_tokens=200,
                system=cached_system_block(
                    "Classify this SMS message from a mortgage lead into exactly one category: "
                    "scheduling, qualifying, objection, positive, question, document, greeting, unknown. "
                    "Respond with JSON: {\"intent\": \"...\", \"confidence\": 0.0-1.0, \"stage\": \"...\"}"
                ),
                messages=[
                    {"role": "user", "content": f"Conversation history:\n{history_context}\n\nNew message: {message}"},
                ],
            )

            import json
            result = json.loads(response.content[0].text)
            return IntentResult(
                intent=result.get("intent", "unknown"),
                confidence=result.get("confidence", 0.5),
                suggested_stage=result.get("stage"),
                entities=self._extract_entities(message),
                method="llm",
            )
        except Exception:
            logger.debug("LLM intent detection failed, falling back to keyword", exc_info=True)
            return self.detect_intent(message)

    def needs_llm_classification(self, keyword_result: IntentResult) -> bool:
        """Determine if we should escalate to LLM for better classification."""
        return keyword_result.confidence < 0.6 or keyword_result.intent == "unknown"

    def _extract_entities(self, message: str) -> Dict:
        """Extract structured entities from message text."""
        entities = {}
        for entity_name, pattern in ENTITY_PATTERNS.items():
            matches = pattern.findall(message)
            if matches:
                entities[entity_name] = matches[0] if len(matches) == 1 else matches
        return entities
