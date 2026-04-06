"""
Objection Detection Agent

Flags borrower objections and hesitations in real time during live mortgage
calls. Recognises common mortgage-specific objection categories and returns
structured data including the objection type, severity, a suggested LO
response, and the transcript excerpt that triggered the detection.

Objection Categories:
    - rate_concern: "Your rate seems high", "I saw lower rates online"
    - closing_cost_shock: "That's a lot in fees", "Why are closing costs so high"
    - timeline_anxiety: "How long will this take", "I need to close by X"
    - document_fatigue: "You need MORE documents?", "I already sent that"
    - competing_offer: "Another lender offered me...", "I'm shopping around"
    - affordability_doubt: "I'm not sure I can afford", "Monthly payment is high"
    - trust_hesitation: "How do I know...", "Is this a scam", "Why do you need my SSN"
    - process_confusion: "I don't understand why", "This is so complicated"

Runs in parallel with other live call agents during every active call session.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

SEVERITY_LEVELS = ("low", "medium", "high")


@dataclass
class Objection:
    """A detected objection or hesitation."""
    objection_id: str
    objection_type: str
    severity: str  # low / medium / high
    suggested_response: str
    transcript_excerpt: str
    timestamp: float  # seconds from call start
    confidence: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Objection pattern registry
# ---------------------------------------------------------------------------

# Each entry: (regex_pattern, objection_type, default_severity, suggested_response)
_OBJECTION_PATTERNS: List[Tuple[re.Pattern, str, str, str]] = [
    # Rate concerns
    (
        re.compile(
            r"(rate\s+(seems?|is|looks?)\s+(high|too high|expensive))|"
            r"(saw\s+(lower|better)\s+rate)|"
            r"(rate\s+(lock|guarantee))|"
            r"(why\s+is\s+(the\s+)?rate\s+so\s+high)",
            re.IGNORECASE,
        ),
        "rate_concern",
        "medium",
        "Acknowledge their concern and explain rate factors: credit score, "
        "loan type, lock period. Offer to show a rate comparison breakdown.",
    ),
    # Closing cost shock
    (
        re.compile(
            r"(closing\s+costs?\s+(are\s+)?(so\s+)?(high|a\s+lot|too\s+much|expensive))|"
            r"(fees?\s+(are\s+)?(so\s+)?(high|a\s+lot|too\s+much))|"
            r"(why\s+(do\s+I|am\s+I)\s+(have\s+to\s+)?pay\s+(so\s+much|all\s+th))|"
            r"(that'?s\s+a\s+lot\s+(of\s+)?(money|fees|in\s+fees))",
            re.IGNORECASE,
        ),
        "closing_cost_shock",
        "high",
        "Walk through the Loan Estimate line by line. Highlight lender credits, "
        "seller concessions, or alternative structures that reduce out-of-pocket.",
    ),
    # Timeline anxiety
    (
        re.compile(
            r"(how\s+long\s+(will|does|is)\s+(this|it|the\s+process))|"
            r"(need\s+to\s+close\s+by)|"
            r"(taking\s+(too\s+long|forever))|"
            r"(when\s+(will|can)\s+(we|I)\s+(close|finish|be\s+done))|"
            r"(running\s+out\s+of\s+time)",
            re.IGNORECASE,
        ),
        "timeline_anxiety",
        "medium",
        "Provide a clear timeline with milestones. Identify the critical path "
        "and any items the borrower can help expedite.",
    ),
    # Document fatigue
    (
        re.compile(
            r"(more\s+documents?|another\s+document)|"
            r"(already\s+sent\s+(that|those|it|everything))|"
            r"(why\s+do\s+you\s+need\s+(more|all\s+th|so\s+many))|"
            r"(so\s+much\s+paperwork)|"
            r"(tired\s+of\s+(sending|uploading|providing))",
            re.IGNORECASE,
        ),
        "document_fatigue",
        "low",
        "Empathise with the burden. Explain why the specific document is required "
        "(investor/regulatory) and offer to walk them through upload.",
    ),
    # Competing offers
    (
        re.compile(
            r"(another\s+(lender|company|bank)\s+(offered|quoted|gave))|"
            r"(shopping\s+around)|"
            r"(better\s+(deal|offer|rate)\s+(somewhere|from|at))|"
            r"(compare\s+(to\s+)?other\s+(lenders?|offers?))|"
            r"(thinking\s+(about|of)\s+going\s+with\s+(someone|another))",
            re.IGNORECASE,
        ),
        "competing_offer",
        "high",
        "Ask for the competing Loan Estimate to do a side-by-side comparison. "
        "Highlight your advantages: service, speed, local presence, total cost.",
    ),
    # Affordability doubt
    (
        re.compile(
            r"(can'?t\s+afford)|"
            r"(too\s+(much|expensive)\s+(per\s+month|monthly|a\s+month))|"
            r"(monthly\s+payment\s+(is\s+)?(too\s+)?(high|a\s+lot))|"
            r"(not\s+sure\s+(I|we)\s+can\s+(afford|swing|manage))|"
            r"(stretch(ing)?\s+(my|our)\s+budget)",
            re.IGNORECASE,
        ),
        "affordability_doubt",
        "high",
        "Explore alternative loan structures: longer term, different program, "
        "reduced down payment. Show total housing expense vs current rent.",
    ),
    # Trust / hesitation
    (
        re.compile(
            r"(is\s+this\s+(a\s+)?scam)|"
            r"(how\s+do\s+I\s+know)|"
            r"(why\s+do\s+you\s+need\s+(my\s+)?ssn)|"
            r"(don'?t\s+feel\s+comfortable)|"
            r"(not\s+sure\s+I\s+trust)|"
            r"(sounds?\s+too\s+good\s+to\s+be\s+true)",
            re.IGNORECASE,
        ),
        "trust_hesitation",
        "medium",
        "Share your NMLS number, company credentials, and consumer protection "
        "rights. Offer to send written disclosures before proceeding.",
    ),
    # Process confusion
    (
        re.compile(
            r"(don'?t\s+understand\s+(why|what|how))|"
            r"(this\s+is\s+(so\s+)?(confus|complicat))|"
            r"(what\s+does\s+that\s+(mean|stand\s+for))|"
            r"(can\s+you\s+explain\s+(that|this)\s+again)",
            re.IGNORECASE,
        ),
        "process_confusion",
        "low",
        "Simplify the explanation using everyday language. Offer an analogy "
        "or visual aid. Confirm understanding before moving on.",
    ),
]

# Quick-fire hesitation phrases (not full regex, just substring matching)
_HESITATION_PHRASES = [
    "i'm not sure",
    "let me think",
    "i need to talk to",
    "i'll get back to you",
    "maybe later",
    "i don't know",
    "that's a lot to think about",
]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ObjectionDetectionAgent:
    """Real-time objection and hesitation detector for live mortgage calls.

    Scans each transcript chunk for mortgage-specific objection patterns,
    categorises them, assigns a severity, and suggests an LO response.

    Usage:
        agent = ObjectionDetectionAgent(db=session)
        result = await agent.process(transcript_chunk, call_context)
    """

    def __init__(self, db: Session = None):
        self.db = db
        self._objections: List[Objection] = []
        self._call_id: Optional[str] = None
        self._objection_counter: int = 0
        # Cooldown: don't re-flag the same type within this window (seconds)
        self._cooldown_seconds: float = 45.0
        self._last_detection_by_type: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, transcript_chunk: str, call_context: dict) -> dict:
        """Scan a transcript chunk for objections.

        Args:
            transcript_chunk: Latest text from the transcription agent.
            call_context: Dict with call_id, elapsed_seconds, speaker, etc.

        Returns:
            Dict with any newly detected objections and historical summary.
        """
        try:
            self._call_id = call_context.get("call_id", self._call_id)
            elapsed = call_context.get("elapsed_seconds", 0.0)
            speaker = call_context.get("speaker", "unknown")

            # Only analyse borrower speech for objections
            if speaker in ("lo", "loan_officer", "agent"):
                return self._summary_response(new_objections=[])

            text = transcript_chunk.strip()
            if not text:
                return self._summary_response(new_objections=[])

            new_objections: List[Objection] = []

            # Pattern-based detection
            for pattern, obj_type, severity, suggestion in _OBJECTION_PATTERNS:
                if pattern.search(text):
                    # Cooldown check
                    last_time = self._last_detection_by_type.get(obj_type, -999)
                    if elapsed - last_time < self._cooldown_seconds:
                        continue

                    self._objection_counter += 1
                    objection = Objection(
                        objection_id=f"{self._call_id}_obj_{self._objection_counter}",
                        objection_type=obj_type,
                        severity=severity,
                        suggested_response=suggestion,
                        transcript_excerpt=text[:300],
                        timestamp=elapsed,
                        confidence=0.75,
                    )
                    new_objections.append(objection)
                    self._objections.append(objection)
                    self._last_detection_by_type[obj_type] = elapsed

                    logger.info(
                        "Objection detected [%s/%s] at %.1fs in call %s",
                        obj_type,
                        severity,
                        elapsed,
                        self._call_id,
                    )

            # Hesitation phrase detection
            lower = text.lower()
            for phrase in _HESITATION_PHRASES:
                if phrase in lower:
                    last_time = self._last_detection_by_type.get("hesitation", -999)
                    if elapsed - last_time < self._cooldown_seconds:
                        break

                    self._objection_counter += 1
                    objection = Objection(
                        objection_id=f"{self._call_id}_obj_{self._objection_counter}",
                        objection_type="hesitation",
                        severity="low",
                        suggested_response=(
                            "The borrower is hesitating. Pause, acknowledge their "
                            "concern, and ask an open-ended question to understand "
                            "what's holding them back."
                        ),
                        transcript_excerpt=text[:300],
                        timestamp=elapsed,
                        confidence=0.6,
                    )
                    new_objections.append(objection)
                    self._objections.append(objection)
                    self._last_detection_by_type["hesitation"] = elapsed
                    break  # One hesitation detection per chunk

            return self._summary_response(new_objections=new_objections)

        except Exception as e:
            logger.error(
                "ObjectionDetectionAgent.process failed: %s", e, exc_info=True
            )
            return {
                "agent": "objection_detection",
                "error": str(e),
                "call_id": self._call_id,
                "new_objections": [],
                "total_objections": len(self._objections),
            }

    def get_all_objections(self) -> List[dict]:
        """Return all detected objections as dicts."""
        return [self._objection_to_dict(o) for o in self._objections]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _summary_response(self, new_objections: List[Objection]) -> dict:
        severity_counts = {"low": 0, "medium": 0, "high": 0}
        for o in self._objections:
            if o.severity in severity_counts:
                severity_counts[o.severity] += 1

        return {
            "agent": "objection_detection",
            "call_id": self._call_id,
            "new_objections": [self._objection_to_dict(o) for o in new_objections],
            "total_objections": len(self._objections),
            "severity_breakdown": severity_counts,
            "objection_types_seen": list(
                {o.objection_type for o in self._objections}
            ),
        }

    @staticmethod
    def _objection_to_dict(obj: Objection) -> dict:
        return {
            "objection_id": obj.objection_id,
            "objection_type": obj.objection_type,
            "severity": obj.severity,
            "suggested_response": obj.suggested_response,
            "transcript_excerpt": obj.transcript_excerpt,
            "timestamp": obj.timestamp,
            "confidence": obj.confidence,
        }
