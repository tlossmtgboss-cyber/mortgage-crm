"""
Sentiment Analysis Agent

Scores borrower sentiment every 30 seconds during live mortgage calls using
Claude for nuanced, mortgage-context-aware sentiment analysis. Tracks a
full sentiment timeline so the LO and coaching agents can detect trends
(e.g., borrower becoming anxious about closing costs).

This is NOT generic sentiment analysis — prompts are calibrated for mortgage
conversations where "anxious" and "frustrated" are distinct, actionable states
beyond simple positive/negative.

Runs in parallel with other live call agents during every active call session.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

SENTIMENT_LABELS = ("positive", "neutral", "negative", "anxious", "frustrated")


@dataclass
class SentimentReading:
    """A single sentiment measurement at a point in the call."""
    timestamp: float  # seconds from call start
    score: float  # -1.0 (very negative) to 1.0 (very positive)
    label: str  # one of SENTIMENT_LABELS
    confidence: float  # 0.0 to 1.0
    rationale: str = ""
    transcript_window: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANALYSIS_INTERVAL_SECONDS = 30.0
# Minimum transcript length (chars) before running analysis
MIN_WINDOW_LENGTH = 40
# Maximum transcript window sent to LLM (chars) — keeps cost and latency down
MAX_WINDOW_LENGTH = 3000
# Default label when analysis cannot run
DEFAULT_LABEL = "neutral"
DEFAULT_SCORE = 0.0

SENTIMENT_SYSTEM_PROMPT = """\
You are a mortgage call sentiment analyst. Analyze the borrower's emotional \
state in the transcript excerpt below. Focus on mortgage-specific nuances:
- "anxious": borrower worried about approval odds, timelines, or unknowns
- "frustrated": borrower annoyed by process, paperwork, or delays
- "positive": borrower enthusiastic, engaged, or optimistic
- "neutral": borrower calm, informational tone
- "negative": borrower unhappy, resistant, or disengaged (but NOT anxious/frustrated)

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "score": <float from -1.0 to 1.0>,
  "label": "<positive|neutral|negative|anxious|frustrated>",
  "confidence": <float from 0.0 to 1.0>,
  "rationale": "<one sentence explaining your assessment>"
}
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SentimentAnalysisAgent:
    """Mortgage-context sentiment scorer for live calls.

    Evaluates borrower sentiment every 30 seconds using Claude, returning a
    score (-1.0 to 1.0), a mortgage-specific label, and a confidence value.
    Maintains a timeline of readings for trend detection.

    Usage:
        agent = SentimentAnalysisAgent(db=session)
        result = await agent.process(transcript_chunk, call_context)
    """

    def __init__(self, db: Session = None):
        self.db = db
        self._timeline: List[SentimentReading] = []
        self._transcript_buffer: str = ""
        self._last_analysis_time: float = 0.0
        self._call_id: Optional[str] = None
        self._anthropic_client: Optional[Any] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, transcript_chunk: str, call_context: dict) -> dict:
        """Accumulate transcript and periodically score sentiment.

        Args:
            transcript_chunk: Latest text from the transcription agent.
            call_context: Dict with call_id, elapsed_seconds, speaker, etc.

        Returns:
            Dict with latest sentiment reading (if scored this cycle) or
            the most recent historical reading.
        """
        try:
            self._call_id = call_context.get("call_id", self._call_id)
            elapsed = call_context.get("elapsed_seconds", 0.0)

            # Only accumulate borrower speech for sentiment
            speaker = call_context.get("speaker", "unknown")
            if speaker in ("borrower", "customer", "client", "lead", "unknown"):
                self._transcript_buffer += f" {transcript_chunk.strip()}"

            # Trim buffer to max window
            if len(self._transcript_buffer) > MAX_WINDOW_LENGTH:
                self._transcript_buffer = self._transcript_buffer[-MAX_WINDOW_LENGTH:]

            # Check if it is time to analyse
            time_since_last = elapsed - self._last_analysis_time
            should_analyse = (
                time_since_last >= ANALYSIS_INTERVAL_SECONDS
                and len(self._transcript_buffer.strip()) >= MIN_WINDOW_LENGTH
            )

            if should_analyse:
                reading = await self._analyse_sentiment(
                    self._transcript_buffer.strip(), elapsed
                )
                self._timeline.append(reading)
                self._last_analysis_time = elapsed
                return self._reading_to_dict(reading, is_new=True)

            # Return most recent reading if available
            if self._timeline:
                return self._reading_to_dict(self._timeline[-1], is_new=False)

            return {
                "agent": "sentiment_analysis",
                "call_id": self._call_id,
                "score": DEFAULT_SCORE,
                "label": DEFAULT_LABEL,
                "confidence": 0.0,
                "is_new_reading": False,
                "readings_count": 0,
                "trend": "insufficient_data",
            }

        except Exception as e:
            logger.error(
                "SentimentAnalysisAgent.process failed: %s", e, exc_info=True
            )
            return {
                "agent": "sentiment_analysis",
                "error": str(e),
                "call_id": self._call_id,
                "score": DEFAULT_SCORE,
                "label": DEFAULT_LABEL,
                "confidence": 0.0,
                "is_new_reading": False,
            }

    def get_timeline(self) -> List[dict]:
        """Return the full sentiment timeline as a list of dicts."""
        return [
            {
                "timestamp": r.timestamp,
                "score": r.score,
                "label": r.label,
                "confidence": r.confidence,
                "rationale": r.rationale,
            }
            for r in self._timeline
        ]

    def get_trend(self) -> str:
        """Compute overall sentiment trend across the call."""
        if len(self._timeline) < 2:
            return "insufficient_data"
        recent = self._timeline[-1].score
        earlier = self._timeline[0].score
        delta = recent - earlier
        if delta > 0.2:
            return "improving"
        if delta < -0.2:
            return "declining"
        return "stable"

    # ------------------------------------------------------------------
    # LLM analysis
    # ------------------------------------------------------------------

    async def _analyse_sentiment(
        self, text: str, elapsed: float
    ) -> SentimentReading:
        """Call Claude to score borrower sentiment."""
        try:
            client = self._get_anthropic_client()
            if client is None:
                return self._fallback_reading(text, elapsed)

            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-6",
                max_tokens=256,
                system=SENTIMENT_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Borrower transcript excerpt (last ~30s of a mortgage call):\n\n"
                            f"{text[-MAX_WINDOW_LENGTH:]}"
                        ),
                    }
                ],
            )

            import json

            raw = response.content[0].text.strip()
            # Handle possible markdown fences
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(raw)

            score = max(-1.0, min(1.0, float(data.get("score", 0.0))))
            label = data.get("label", DEFAULT_LABEL)
            if label not in SENTIMENT_LABELS:
                label = DEFAULT_LABEL
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
            rationale = str(data.get("rationale", ""))

            return SentimentReading(
                timestamp=elapsed,
                score=score,
                label=label,
                confidence=confidence,
                rationale=rationale,
                transcript_window=text[-500:],
            )

        except Exception as e:
            logger.warning(
                "LLM sentiment analysis failed, using fallback: %s", e
            )
            return self._fallback_reading(text, elapsed)

    def _fallback_reading(self, text: str, elapsed: float) -> SentimentReading:
        """Keyword-based fallback when LLM is unavailable."""
        lower = text.lower()

        negative_signals = [
            "too expensive", "can't afford", "frustrat", "confus",
            "too long", "don't understand", "give up", "not worth",
            "ridiculous", "waste of time",
        ]
        anxious_signals = [
            "worried", "nervous", "concern", "not sure",
            "what if", "scary", "overwhelm", "uncertain",
        ]
        positive_signals = [
            "great", "perfect", "excited", "love", "wonderful",
            "sounds good", "let's do it", "looking forward", "thank you",
        ]

        neg_count = sum(1 for s in negative_signals if s in lower)
        anx_count = sum(1 for s in anxious_signals if s in lower)
        pos_count = sum(1 for s in positive_signals if s in lower)

        if anx_count > neg_count and anx_count > pos_count:
            return SentimentReading(
                timestamp=elapsed, score=-0.3, label="anxious",
                confidence=0.4, rationale="Keyword fallback: anxiety signals detected",
                transcript_window=text[-500:],
            )
        if neg_count > pos_count:
            return SentimentReading(
                timestamp=elapsed, score=-0.5, label="negative",
                confidence=0.4, rationale="Keyword fallback: negative signals detected",
                transcript_window=text[-500:],
            )
        if pos_count > 0:
            return SentimentReading(
                timestamp=elapsed, score=0.5, label="positive",
                confidence=0.4, rationale="Keyword fallback: positive signals detected",
                transcript_window=text[-500:],
            )

        return SentimentReading(
            timestamp=elapsed, score=0.0, label="neutral",
            confidence=0.3, rationale="Keyword fallback: no strong signals",
            transcript_window=text[-500:],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_anthropic_client(self):
        """Lazy-init Anthropic client."""
        if self._anthropic_client is not None:
            return self._anthropic_client
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                logger.debug("ANTHROPIC_API_KEY not set — LLM sentiment unavailable")
                return None
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=api_key)
            return self._anthropic_client
        except ImportError:
            logger.warning("anthropic package not installed")
            return None
        except Exception as e:
            logger.warning("Failed to create Anthropic client: %s", e)
            return None

    def _reading_to_dict(self, reading: SentimentReading, is_new: bool) -> dict:
        """Convert a SentimentReading to a serialisable dict."""
        return {
            "agent": "sentiment_analysis",
            "call_id": self._call_id,
            "score": reading.score,
            "label": reading.label,
            "confidence": reading.confidence,
            "rationale": reading.rationale,
            "is_new_reading": is_new,
            "readings_count": len(self._timeline),
            "trend": self.get_trend(),
            "timestamp": reading.timestamp,
        }
