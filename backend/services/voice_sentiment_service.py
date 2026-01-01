"""
Voice Sentiment Analysis Service
Analyzes voice conversation transcripts to determine sentiment and emotional tone.
"""
import os
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

import openai

logger = logging.getLogger(__name__)


class SentimentCategory(str, Enum):
    """Sentiment categories for voice conversations."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    ANXIOUS = "anxious"
    FRUSTRATED = "frustrated"
    EXCITED = "excited"
    CONFUSED = "confused"


@dataclass
class SentimentResult:
    """Structured result from sentiment analysis."""
    overall_sentiment: str
    confidence: float
    sentiment_scores: Dict[str, float]
    key_moments: List[Dict[str, Any]]
    summary: str
    caller_emotional_journey: str

    def to_dict(self) -> Dict:
        return {
            "overall_sentiment": self.overall_sentiment,
            "confidence": self.confidence,
            "sentiment_scores": self.sentiment_scores,
            "key_moments": self.key_moments,
            "summary": self.summary,
            "caller_emotional_journey": self.caller_emotional_journey
        }


class VoiceSentimentService:
    """
    Analyzes voice conversation transcripts for sentiment.

    Uses OpenAI for accurate analysis with fallback to keyword-based analysis.
    """

    # Keyword mappings for fallback analysis
    SENTIMENT_KEYWORDS = {
        "positive": [
            "great", "thanks", "thank you", "helpful", "good", "excellent",
            "perfect", "awesome", "wonderful", "appreciate", "amazing",
            "happy", "pleased", "excited", "love", "fantastic"
        ],
        "negative": [
            "bad", "terrible", "awful", "horrible", "disappointed", "upset",
            "angry", "hate", "worst", "unacceptable", "ridiculous", "stupid"
        ],
        "anxious": [
            "worried", "nervous", "scared", "anxious", "stress", "concern",
            "afraid", "overwhelm", "panic", "uncertain", "unsure", "confused"
        ],
        "frustrated": [
            "frustrated", "annoyed", "irritated", "fed up", "sick of",
            "tired of", "enough", "ridiculous", "unbelievable", "seriously"
        ],
        "excited": [
            "excited", "can't wait", "thrilled", "eager", "looking forward",
            "amazing", "incredible", "wow", "fantastic"
        ]
    }

    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o-mini"  # Fast and cost-effective for analysis

    async def analyze_conversation(
        self,
        conversation_history: List[Dict[str, str]],
        use_ai: bool = True
    ) -> SentimentResult:
        """
        Analyze a voice conversation for sentiment.

        Args:
            conversation_history: List of conversation turns with 'role' and 'content'/'text'
            use_ai: Whether to use AI analysis (falls back to keywords if False or on error)

        Returns:
            SentimentResult with detailed sentiment analysis
        """
        if not conversation_history:
            return self._empty_result()

        # Format conversation for analysis
        formatted_transcript = self._format_transcript(conversation_history)

        if use_ai and os.getenv("OPENAI_API_KEY"):
            try:
                return await self._analyze_with_ai(formatted_transcript, conversation_history)
            except Exception as e:
                logger.warning(f"AI sentiment analysis failed, falling back to keywords: {e}")

        # Fallback to keyword-based analysis
        return self._analyze_with_keywords(formatted_transcript, conversation_history)

    def analyze_conversation_sync(
        self,
        conversation_history: List[Dict[str, str]],
        use_ai: bool = True
    ) -> SentimentResult:
        """
        Synchronous version of analyze_conversation for non-async contexts.
        """
        if not conversation_history:
            return self._empty_result()

        formatted_transcript = self._format_transcript(conversation_history)

        if use_ai and os.getenv("OPENAI_API_KEY"):
            try:
                return self._analyze_with_ai_sync(formatted_transcript, conversation_history)
            except Exception as e:
                logger.warning(f"AI sentiment analysis failed, falling back to keywords: {e}")

        return self._analyze_with_keywords(formatted_transcript, conversation_history)

    def _format_transcript(self, conversation_history: List[Dict]) -> str:
        """Format conversation history into a readable transcript."""
        lines = []
        for turn in conversation_history:
            role = turn.get("role", "unknown").capitalize()
            # Handle different content key names
            content = turn.get("content") or turn.get("text") or turn.get("message", "")
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _analyze_with_ai(
        self,
        transcript: str,
        conversation_history: List[Dict]
    ) -> SentimentResult:
        """Use OpenAI to analyze sentiment."""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self._analyze_with_ai_sync,
            transcript,
            conversation_history
        )

    def _analyze_with_ai_sync(
        self,
        transcript: str,
        conversation_history: List[Dict]
    ) -> SentimentResult:
        """Synchronous AI analysis."""
        system_prompt = """You are a sentiment analysis expert for mortgage industry voice calls.
Analyze the following call transcript and provide a detailed sentiment analysis.

Return a JSON object with these fields:
- overall_sentiment: One of "positive", "negative", "neutral", "anxious", "frustrated", "excited", "confused"
- confidence: Float 0-1 indicating confidence in the analysis
- sentiment_scores: Object with scores (0-1) for each sentiment category
- key_moments: Array of {turn_index, sentiment, text_snippet, significance} for notable emotional moments
- summary: Brief 1-2 sentence summary of the caller's emotional state
- caller_emotional_journey: Brief description of how caller's emotions changed during the call

Focus on the CALLER's sentiment, not the assistant/agent. Consider:
- Tone indicators in the text
- Questions asked (uncertainty vs. confidence)
- Response to information provided
- Signs of stress about financial decisions
- Satisfaction or frustration with service"""

        user_prompt = f"""Analyze this mortgage-related voice call transcript:

{transcript}

Provide sentiment analysis in JSON format."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            return SentimentResult(
                overall_sentiment=result.get("overall_sentiment", "neutral"),
                confidence=float(result.get("confidence", 0.7)),
                sentiment_scores=result.get("sentiment_scores", {}),
                key_moments=result.get("key_moments", []),
                summary=result.get("summary", ""),
                caller_emotional_journey=result.get("caller_emotional_journey", "")
            )

        except Exception as e:
            logger.error(f"OpenAI sentiment analysis error: {e}")
            raise

    def _analyze_with_keywords(
        self,
        transcript: str,
        conversation_history: List[Dict]
    ) -> SentimentResult:
        """Fallback keyword-based sentiment analysis."""
        transcript_lower = transcript.lower()

        # Count keyword matches for each sentiment
        scores = {}
        for sentiment, keywords in self.SENTIMENT_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in transcript_lower)
            scores[sentiment] = min(1.0, count * 0.15)  # Cap at 1.0

        # Add neutral as inverse of other sentiments
        total_sentiment = sum(scores.values())
        scores["neutral"] = max(0, 1.0 - total_sentiment) if total_sentiment < 1 else 0

        # Determine overall sentiment
        if scores.get("anxious", 0) > 0.3:
            overall = "anxious"
        elif scores.get("frustrated", 0) > 0.3:
            overall = "frustrated"
        elif scores.get("negative", 0) > scores.get("positive", 0):
            overall = "negative"
        elif scores.get("positive", 0) > scores.get("negative", 0):
            overall = "positive"
        elif scores.get("excited", 0) > 0.2:
            overall = "excited"
        else:
            overall = "neutral"

        # Find key moments (simple version)
        key_moments = []
        for i, turn in enumerate(conversation_history):
            content = (turn.get("content") or turn.get("text") or "").lower()
            if turn.get("role", "").lower() in ("user", "caller", "customer"):
                for sentiment, keywords in self.SENTIMENT_KEYWORDS.items():
                    if any(kw in content for kw in keywords):
                        key_moments.append({
                            "turn_index": i,
                            "sentiment": sentiment,
                            "text_snippet": content[:100],
                            "significance": "keyword_match"
                        })
                        break

        return SentimentResult(
            overall_sentiment=overall,
            confidence=0.6,  # Lower confidence for keyword analysis
            sentiment_scores=scores,
            key_moments=key_moments[:5],  # Limit to 5 key moments
            summary=f"Caller displayed primarily {overall} sentiment during the call.",
            caller_emotional_journey="Analyzed using keyword matching (AI unavailable)."
        )

    def _empty_result(self) -> SentimentResult:
        """Return empty result for empty conversations."""
        return SentimentResult(
            overall_sentiment="neutral",
            confidence=0.0,
            sentiment_scores={"neutral": 1.0},
            key_moments=[],
            summary="No conversation to analyze.",
            caller_emotional_journey="N/A"
        )

    def get_simple_sentiment(self, conversation_history: List[Dict]) -> str:
        """
        Quick sentiment analysis returning just the sentiment string.
        Useful for simple use cases where full analysis isn't needed.
        """
        if not conversation_history:
            return "neutral"

        transcript = self._format_transcript(conversation_history)
        result = self._analyze_with_keywords(transcript, conversation_history)
        return result.overall_sentiment


# Singleton instance for easy import
_sentiment_service = None


def get_sentiment_service() -> VoiceSentimentService:
    """Get or create the singleton sentiment service instance."""
    global _sentiment_service
    if _sentiment_service is None:
        _sentiment_service = VoiceSentimentService()
    return _sentiment_service


def analyze_voice_sentiment(conversation_history: List[Dict], use_ai: bool = True) -> str:
    """
    Convenience function to analyze voice sentiment.

    Args:
        conversation_history: List of conversation turns
        use_ai: Whether to use AI (True) or keyword fallback (False)

    Returns:
        Sentiment string: "positive", "negative", "neutral", "anxious", etc.
    """
    service = get_sentiment_service()

    if use_ai and os.getenv("OPENAI_API_KEY"):
        try:
            result = service._analyze_with_ai_sync(
                service._format_transcript(conversation_history),
                conversation_history
            )
            return result.overall_sentiment
        except Exception as e:
            logger.warning(f"AI sentiment failed, using keywords: {e}")

    return service.get_simple_sentiment(conversation_history)
