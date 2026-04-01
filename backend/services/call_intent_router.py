"""Call intent router — detects caller intent and routes to appropriate handler."""
import logging
import re
from dataclasses import dataclass
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class CallIntent:
    intent: str
    confidence: float
    route: str
    priority: str
    matched_keywords: List[str]


CALL_INTENTS = {
    "purchase_inquiry": {
        "keywords": [r"\b(buy|purchase|new home|first[- ]time|house hunting|pre[- ]approv|looking for a home)\b"],
        "route": "qualification_agent",
        "priority": "high",
    },
    "refinance_inquiry": {
        "keywords": [r"\b(refinanc|refi|lower.{0,10}rate|cash[- ]out|equity|lower.{0,10}payment)\b"],
        "route": "qualification_agent",
        "priority": "high",
    },
    "rate_check": {
        "keywords": [r"\b(rate|rates|interest rate|what are rates|today'?s rate|current rate)\b"],
        "route": "rate_info_response",
        "priority": "medium",
    },
    "loan_status": {
        "keywords": [r"\b(status|my loan|update|where is my|application status|closing date|when will)\b"],
        "route": "lo_transfer",
        "priority": "medium",
    },
    "appointment": {
        "keywords": [r"\b(appointment|schedule|meet|consultation|call.{0,5}back|set up.{0,5}time|book.{0,5}time)\b"],
        "route": "scheduling_agent",
        "priority": "medium",
    },
    "documents": {
        "keywords": [r"\b(document|upload|send.{0,10}(paystub|w2|bank|tax)|paperwork|fax|email.{0,10}docs)\b"],
        "route": "document_portal",
        "priority": "medium",
    },
    "payment": {
        "keywords": [r"\b(payment|pay.{0,5}(my|the).{0,5}(mortgage|loan)|autopay|escrow)\b"],
        "route": "servicing_transfer",
        "priority": "medium",
    },
    "complaint": {
        "keywords": [r"\b(complaint|problem|unhappy|manager|supervisor|escalat|dissatisfied|terrible)\b"],
        "route": "escalation",
        "priority": "urgent",
    },
    "closing": {
        "keywords": [r"\b(closing|close.{0,5}(date|tomorrow|next week)|settlement|sign.{0,10}(papers|docs))\b"],
        "route": "lo_transfer",
        "priority": "high",
    },
    "dnc_request": {
        "keywords": [r"\b(stop call|don'?t call|remove.{0,10}(list|number)|do not call|take me off)\b"],
        "route": "dnc_handler",
        "priority": "urgent",
    },
}

# Pre-compile all regex patterns
_compiled_intents = {}
for intent_name, config in CALL_INTENTS.items():
    _compiled_intents[intent_name] = {
        "regexes": [re.compile(p, re.IGNORECASE) for p in config["keywords"]],
        "route": config["route"],
        "priority": config["priority"],
    }


class CallIntentRouter:
    """Routes inbound calls based on detected caller intent."""

    def detect_intent(self, transcript: str) -> Optional[CallIntent]:
        """Detect caller intent from transcript segment."""
        if not transcript:
            return None

        best_intent = None
        best_confidence = 0.0
        best_keywords = []

        for intent_name, config in _compiled_intents.items():
            matched = []
            for regex in config["regexes"]:
                matches = regex.findall(transcript)
                if matches:
                    matched.extend(matches if isinstance(matches[0], str) else [m[0] for m in matches])

            if matched:
                # Confidence based on number of keyword matches
                confidence = min(1.0, 0.6 + (len(matched) * 0.15))

                # Priority boost
                if config["priority"] == "urgent":
                    confidence = min(1.0, confidence + 0.2)
                elif config["priority"] == "high":
                    confidence = min(1.0, confidence + 0.1)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_intent = intent_name
                    best_keywords = matched[:5]

        if not best_intent:
            return None

        config = _compiled_intents[best_intent]
        return CallIntent(
            intent=best_intent,
            confidence=best_confidence,
            route=config["route"],
            priority=config["priority"],
            matched_keywords=best_keywords,
        )

    def get_routing(self, intent: str) -> Dict:
        """Get routing destination for an intent."""
        config = _compiled_intents.get(intent)
        if not config:
            return {"route": "general_queue", "priority": "low"}
        return {"route": config["route"], "priority": config["priority"]}

    def detect_multiple_intents(self, transcript: str) -> List[CallIntent]:
        """Detect all intents present in transcript, ranked by confidence."""
        if not transcript:
            return []

        results = []
        for intent_name, config in _compiled_intents.items():
            matched = []
            for regex in config["regexes"]:
                matches = regex.findall(transcript)
                if matches:
                    matched.extend(matches if isinstance(matches[0], str) else [m[0] for m in matches])

            if matched:
                confidence = min(1.0, 0.6 + (len(matched) * 0.15))
                results.append(CallIntent(
                    intent=intent_name,
                    confidence=confidence,
                    route=config["route"],
                    priority=config["priority"],
                    matched_keywords=matched[:3],
                ))

        return sorted(results, key=lambda x: x.confidence, reverse=True)
