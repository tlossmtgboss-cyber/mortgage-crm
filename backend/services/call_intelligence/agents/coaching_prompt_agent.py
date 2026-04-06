"""
Coaching Prompt Agent

Pushes real-time coaching cards to the LO's screen during live mortgage
calls. Cards are triggered by actionable events from peer agents:
    - Objection detected (from ObjectionDetectionAgent)
    - Sentiment drop (from SentimentAnalysisAgent)
    - Compliance gap (from ComplianceMonitorCallAgent)
    - Opportunity identified (e.g., cross-sell, upsell, referral moment)

Enforces a maximum of 1 card per 60 seconds to prevent overwhelming the LO
during a live conversation. Cards are prioritised by urgency so the most
critical coaching insight wins when multiple triggers fire simultaneously.

Card priorities (highest first):
    1. compliance_gap — regulatory risk, must address immediately
    2. objection_high — high-severity objection needs response now
    3. sentiment_drop — borrower disengaging, intervene
    4. objection_medium — moderate objection, coach through it
    5. opportunity — cross-sell or upsell moment
    6. general_tip — best-practice suggestion

Runs in parallel with other live call agents during every active call session.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

CARD_PRIORITIES = {
    "compliance_gap": 1,
    "objection_high": 2,
    "sentiment_drop": 3,
    "objection_medium": 4,
    "opportunity": 5,
    "general_tip": 6,
}


@dataclass
class CoachingCard:
    """A coaching card displayed to the LO during a live call."""
    card_id: str
    trigger: str  # what event triggered this card
    priority: int  # 1 = highest
    title: str
    body: str
    action_suggestion: str
    timestamp: float  # seconds from call start
    dismissed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CARD_COOLDOWN_SECONDS = 60.0  # Max 1 card per this interval
SENTIMENT_DROP_THRESHOLD = -0.3  # Score delta that triggers a coaching card
MAX_CARDS_PER_CALL = 30  # Safety cap


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class CoachingPromptAgent:
    """Real-time coaching card engine for live mortgage calls.

    Consumes signals from peer agents (objection, sentiment, compliance)
    and produces prioritised coaching cards for the LO's UI. Enforces a
    cooldown of 60 seconds between cards to avoid cognitive overload.

    Usage:
        agent = CoachingPromptAgent(db=session)
        result = await agent.process(transcript_chunk, call_context)

    The call_context dict should include outputs from peer agents:
        - objections: list of new objection dicts (from ObjectionDetectionAgent)
        - sentiment: dict with score, label, trend, is_new_reading
        - compliance: dict with compliance_score, required_missed, new_violations
    """

    def __init__(self, db: Session = None):
        self.db = db
        self._cards: List[CoachingCard] = []
        self._call_id: Optional[str] = None
        self._card_counter: int = 0
        self._last_card_time: float = -CARD_COOLDOWN_SECONDS  # Allow first card immediately
        self._previous_sentiment_score: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, transcript_chunk: str, call_context: dict) -> dict:
        """Evaluate signals from peer agents and emit coaching cards.

        Args:
            transcript_chunk: Latest text (used for context, not primary trigger).
            call_context: Dict with call_id, elapsed_seconds, and peer-agent
                          outputs (objections, sentiment, compliance).

        Returns:
            Dict with the new coaching card (if any) and historical cards.
        """
        try:
            self._call_id = call_context.get("call_id", self._call_id)
            elapsed = call_context.get("elapsed_seconds", 0.0)

            # Collect candidate cards from all signal sources
            candidates: List[CoachingCard] = []

            # --- Compliance gaps ---
            compliance = call_context.get("compliance", {})
            candidates.extend(
                self._evaluate_compliance(compliance, elapsed)
            )

            # --- Objections ---
            objections = call_context.get("objections", [])
            candidates.extend(
                self._evaluate_objections(objections, elapsed)
            )

            # --- Sentiment ---
            sentiment = call_context.get("sentiment", {})
            candidates.extend(
                self._evaluate_sentiment(sentiment, elapsed)
            )

            # --- Opportunity detection from transcript ---
            candidates.extend(
                self._evaluate_opportunities(transcript_chunk, elapsed)
            )

            # Pick the highest-priority candidate
            if candidates:
                candidates.sort(key=lambda c: c.priority)
                best = candidates[0]

                # Cooldown check
                time_since_last = elapsed - self._last_card_time
                if (
                    time_since_last >= CARD_COOLDOWN_SECONDS
                    and len(self._cards) < MAX_CARDS_PER_CALL
                ):
                    self._cards.append(best)
                    self._last_card_time = elapsed
                    logger.info(
                        "Coaching card [%s] emitted at %.1fs for call %s",
                        best.trigger,
                        elapsed,
                        self._call_id,
                    )
                    return self._build_response(new_card=best)

            return self._build_response(new_card=None)

        except Exception as e:
            logger.error(
                "CoachingPromptAgent.process failed: %s", e, exc_info=True
            )
            return {
                "agent": "coaching_prompt",
                "error": str(e),
                "call_id": self._call_id,
                "new_card": None,
                "total_cards": len(self._cards),
            }

    def get_all_cards(self) -> List[dict]:
        """Return all coaching cards emitted during this call."""
        return [self._card_to_dict(c) for c in self._cards]

    def dismiss_card(self, card_id: str) -> bool:
        """Mark a card as dismissed by the LO."""
        for card in self._cards:
            if card.card_id == card_id:
                card.dismissed = True
                return True
        return False

    # ------------------------------------------------------------------
    # Signal evaluators
    # ------------------------------------------------------------------

    def _evaluate_compliance(
        self, compliance: dict, elapsed: float
    ) -> List[CoachingCard]:
        """Generate coaching cards from compliance gaps."""
        cards: List[CoachingCard] = []

        # New violations
        for violation in compliance.get("new_violations", []):
            self._card_counter += 1
            cards.append(
                CoachingCard(
                    card_id=f"{self._call_id}_card_{self._card_counter}",
                    trigger="compliance_gap",
                    priority=CARD_PRIORITIES["compliance_gap"],
                    title="Compliance Alert",
                    body=violation.get("description", "Compliance issue detected"),
                    action_suggestion=(
                        "Address this disclosure requirement now. "
                        "Failure to comply may result in regulatory action."
                    ),
                    timestamp=elapsed,
                )
            )

        # Missing required disclosures (after 2 minutes into call)
        if elapsed > 120:
            missed = compliance.get("required_missed", [])
            for item_name in missed:
                # Only card once per missed item
                already_carded = any(
                    c.trigger == "compliance_gap" and item_name in c.body
                    for c in self._cards
                )
                if not already_carded:
                    self._card_counter += 1
                    cards.append(
                        CoachingCard(
                            card_id=f"{self._call_id}_card_{self._card_counter}",
                            trigger="compliance_gap",
                            priority=CARD_PRIORITIES["compliance_gap"],
                            title=f"Missing: {item_name}",
                            body=f"Required disclosure '{item_name}' has not been made yet.",
                            action_suggestion=f"Make the {item_name} disclosure before continuing.",
                            timestamp=elapsed,
                        )
                    )

        return cards

    def _evaluate_objections(
        self, objections: list, elapsed: float
    ) -> List[CoachingCard]:
        """Generate coaching cards from detected objections."""
        cards: List[CoachingCard] = []

        for obj in objections:
            severity = obj.get("severity", "low")
            obj_type = obj.get("objection_type", "unknown")
            suggested = obj.get("suggested_response", "Address the borrower's concern.")

            if severity == "high":
                trigger = "objection_high"
            elif severity == "medium":
                trigger = "objection_medium"
            else:
                continue  # Low-severity objections don't generate cards

            self._card_counter += 1
            cards.append(
                CoachingCard(
                    card_id=f"{self._call_id}_card_{self._card_counter}",
                    trigger=trigger,
                    priority=CARD_PRIORITIES[trigger],
                    title=f"Objection: {obj_type.replace('_', ' ').title()}",
                    body=f"Borrower raised a {severity}-severity {obj_type.replace('_', ' ')} objection.",
                    action_suggestion=suggested,
                    timestamp=elapsed,
                )
            )

        return cards

    def _evaluate_sentiment(
        self, sentiment: dict, elapsed: float
    ) -> List[CoachingCard]:
        """Generate coaching cards from sentiment drops."""
        cards: List[CoachingCard] = []

        if not sentiment.get("is_new_reading"):
            return cards

        current_score = sentiment.get("score", 0.0)
        label = sentiment.get("label", "neutral")

        # Detect significant drop from previous reading
        if self._previous_sentiment_score is not None:
            delta = current_score - self._previous_sentiment_score
            if delta <= SENTIMENT_DROP_THRESHOLD:
                self._card_counter += 1
                cards.append(
                    CoachingCard(
                        card_id=f"{self._call_id}_card_{self._card_counter}",
                        trigger="sentiment_drop",
                        priority=CARD_PRIORITIES["sentiment_drop"],
                        title="Borrower Sentiment Dropping",
                        body=(
                            f"Sentiment dropped from {self._previous_sentiment_score:.1f} "
                            f"to {current_score:.1f} ({label}). "
                            f"{sentiment.get('rationale', '')}"
                        ),
                        action_suggestion=(
                            "Pause and check in with the borrower. Ask an open-ended "
                            "question like 'How are you feeling about everything so far?' "
                            "to re-engage and address underlying concerns."
                        ),
                        timestamp=elapsed,
                    )
                )

        # Persistent negative/anxious state
        if label in ("frustrated", "anxious") and current_score < -0.4:
            # Only if we haven't already carded for this state recently
            recent_sentiment_cards = [
                c for c in self._cards
                if c.trigger == "sentiment_drop"
                and elapsed - c.timestamp < 120
            ]
            if not recent_sentiment_cards:
                self._card_counter += 1
                suggestion_map = {
                    "frustrated": (
                        "Acknowledge the frustration directly: 'I understand this "
                        "process can feel tedious. Let me simplify what's left.'"
                    ),
                    "anxious": (
                        "Provide reassurance: 'This is completely normal at this "
                        "stage. Here's exactly what to expect next...'"
                    ),
                }
                cards.append(
                    CoachingCard(
                        card_id=f"{self._call_id}_card_{self._card_counter}",
                        trigger="sentiment_drop",
                        priority=CARD_PRIORITIES["sentiment_drop"],
                        title=f"Borrower Appears {label.title()}",
                        body=f"Borrower sentiment is {label} (score: {current_score:.1f}).",
                        action_suggestion=suggestion_map.get(
                            label,
                            "Check in with the borrower and address their concerns."
                        ),
                        timestamp=elapsed,
                    )
                )

        self._previous_sentiment_score = current_score
        return cards

    def _evaluate_opportunities(
        self, transcript_chunk: str, elapsed: float
    ) -> List[CoachingCard]:
        """Detect cross-sell / upsell / referral opportunities in transcript."""
        cards: List[CoachingCard] = []
        lower = transcript_chunk.lower()

        opportunity_triggers = [
            {
                "patterns": ["refinance", "refi", "lower my rate", "rate drop"],
                "title": "Refinance Opportunity",
                "body": "Borrower mentioned refinance interest. Discuss rate monitoring and refi options.",
                "action": "Offer to set up rate alerts and explain the break-even point for refinancing.",
            },
            {
                "patterns": ["investment property", "rental", "second home", "vacation home"],
                "title": "Investment Property Interest",
                "body": "Borrower expressed interest in additional property. Explore loan options.",
                "action": "Discuss investment property loan programs, down payment requirements, and rate differences.",
            },
            {
                "patterns": ["home insurance", "homeowner's insurance", "need insurance"],
                "title": "Insurance Referral Moment",
                "body": "Borrower asking about insurance. Opportunity for trusted partner referral.",
                "action": "Offer to connect the borrower with a trusted insurance partner.",
            },
            {
                "patterns": ["financial advisor", "financial planner", "wealth", "estate planning"],
                "title": "Financial Planning Referral",
                "body": "Borrower mentioned financial planning. Referral partner opportunity.",
                "action": "Offer to introduce a trusted financial planning partner.",
            },
        ]

        for opp in opportunity_triggers:
            if any(p in lower for p in opp["patterns"]):
                # Don't duplicate if already carded for this opportunity type
                already_carded = any(
                    c.title == opp["title"] for c in self._cards
                )
                if not already_carded:
                    self._card_counter += 1
                    cards.append(
                        CoachingCard(
                            card_id=f"{self._call_id}_card_{self._card_counter}",
                            trigger="opportunity",
                            priority=CARD_PRIORITIES["opportunity"],
                            title=opp["title"],
                            body=opp["body"],
                            action_suggestion=opp["action"],
                            timestamp=elapsed,
                        )
                    )

        return cards

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_response(self, new_card: Optional[CoachingCard]) -> dict:
        return {
            "agent": "coaching_prompt",
            "call_id": self._call_id,
            "new_card": self._card_to_dict(new_card) if new_card else None,
            "total_cards": len(self._cards),
            "active_cards": [
                self._card_to_dict(c) for c in self._cards if not c.dismissed
            ],
        }

    @staticmethod
    def _card_to_dict(card: CoachingCard) -> dict:
        return {
            "card_id": card.card_id,
            "trigger": card.trigger,
            "priority": card.priority,
            "title": card.title,
            "body": card.body,
            "action_suggestion": card.action_suggestion,
            "timestamp": card.timestamp,
            "dismissed": card.dismissed,
        }
