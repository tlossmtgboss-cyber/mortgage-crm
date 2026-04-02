"""
Conversational Insights Service
===============================
NLP-powered analysis of AI Receptionist conversations to identify:
- Trending questions and topics
- Common objections and concerns
- Customer intent patterns
- Emotional sentiment journey
- Successful conversation patterns

Uses Claude AI for intelligent analysis with caching for cost efficiency.
"""

import os
import re
import json
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Try to import Claude client
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False

# Try to import LLM cache
try:
    from services.llm_cache_service import llm_cache, LLMCacheService
    CACHE_AVAILABLE = True
except ImportError:
    llm_cache = None
    LLMCacheService = None
    CACHE_AVAILABLE = False


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class IntentCategory(str, Enum):
    RATE_INQUIRY = "rate_inquiry"
    PREQUALIFICATION = "prequalification"
    REFINANCE = "refinance"
    PURCHASE = "purchase"
    DOCUMENT_QUESTION = "document_question"
    STATUS_CHECK = "status_check"
    PAYMENT_QUESTION = "payment_question"
    COMPLAINT = "complaint"
    GENERAL_INFO = "general_info"
    APPOINTMENT_REQUEST = "appointment_request"
    TRANSFER_REQUEST = "transfer_request"
    OTHER = "other"


class SentimentLevel(str, Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class ObjectionType(str, Enum):
    RATE_TOO_HIGH = "rate_too_high"
    FEES_CONCERN = "fees_concern"
    TIMING = "timing"
    CREDIT_CONCERN = "credit_concern"
    DOCUMENTATION = "documentation"
    TRUST = "trust"
    COMPARISON_SHOPPING = "comparison_shopping"
    NOT_READY = "not_ready"
    OTHER = "other"


# Keywords for pattern matching (fallback when AI not available)
INTENT_KEYWORDS = {
    IntentCategory.RATE_INQUIRY: ["rate", "rates", "interest", "apr", "percentage"],
    IntentCategory.PREQUALIFICATION: ["prequalify", "prequalification", "pre-qualify", "qualify", "how much can i"],
    IntentCategory.REFINANCE: ["refinance", "refi", "lower payment", "cash out", "heloc"],
    IntentCategory.PURCHASE: ["buy", "buying", "purchase", "first time", "new home"],
    IntentCategory.DOCUMENT_QUESTION: ["document", "paperwork", "need to provide", "upload", "send"],
    IntentCategory.STATUS_CHECK: ["status", "where are we", "update", "timeline", "how long"],
    IntentCategory.PAYMENT_QUESTION: ["payment", "monthly", "afford", "escrow"],
    IntentCategory.COMPLAINT: ["complaint", "unhappy", "frustrated", "problem", "issue", "wrong"],
    IntentCategory.APPOINTMENT_REQUEST: ["appointment", "schedule", "meet", "call back", "available"],
    IntentCategory.TRANSFER_REQUEST: ["speak to", "talk to", "transfer", "manager", "supervisor"],
}

OBJECTION_KEYWORDS = {
    ObjectionType.RATE_TOO_HIGH: ["rate is high", "too high", "better rate", "lower rate"],
    ObjectionType.FEES_CONCERN: ["fees", "costs", "closing costs", "expensive"],
    ObjectionType.TIMING: ["not ready", "later", "few months", "next year", "thinking about"],
    ObjectionType.CREDIT_CONCERN: ["credit score", "bad credit", "improve credit"],
    ObjectionType.DOCUMENTATION: ["too much paperwork", "complicated", "difficult"],
    ObjectionType.COMPARISON_SHOPPING: ["shopping around", "other lenders", "comparing"],
    ObjectionType.NOT_READY: ["just looking", "browsing", "not sure", "thinking"],
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ConversationInsight:
    """Insight extracted from a single conversation."""
    conversation_id: str
    timestamp: datetime
    intent: IntentCategory
    sentiment: SentimentLevel
    objections: List[ObjectionType] = field(default_factory=list)
    key_questions: List[str] = field(default_factory=list)
    topics_discussed: List[str] = field(default_factory=list)
    resolution_status: str = "unknown"
    call_duration_seconds: int = 0

    def to_dict(self) -> Dict:
        return {
            "conversation_id": self.conversation_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "intent": self.intent.value if self.intent else None,
            "sentiment": self.sentiment.value if self.sentiment else None,
            "objections": [o.value for o in self.objections],
            "key_questions": self.key_questions,
            "topics_discussed": self.topics_discussed,
            "resolution_status": self.resolution_status,
            "call_duration_seconds": self.call_duration_seconds
        }


@dataclass
class TrendingTopic:
    """A trending topic or question."""
    topic: str
    count: int
    percentage: float
    trend: str = "stable"  # up, down, stable
    example_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "topic": self.topic,
            "count": self.count,
            "percentage": round(self.percentage, 2),
            "trend": self.trend,
            "examples": self.example_questions[:3]
        }


@dataclass
class InsightsSummary:
    """Aggregated insights summary."""
    period_start: date
    period_end: date
    total_conversations: int = 0
    intent_distribution: Dict[str, int] = field(default_factory=dict)
    sentiment_distribution: Dict[str, int] = field(default_factory=dict)
    objection_frequency: Dict[str, int] = field(default_factory=dict)
    trending_topics: List[TrendingTopic] = field(default_factory=list)
    top_questions: List[str] = field(default_factory=list)
    avg_sentiment_score: float = 0.0
    resolution_rate: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat()
            },
            "total_conversations": self.total_conversations,
            "intent_distribution": self.intent_distribution,
            "sentiment_distribution": self.sentiment_distribution,
            "objection_frequency": self.objection_frequency,
            "trending_topics": [t.to_dict() for t in self.trending_topics],
            "top_questions": self.top_questions[:10],
            "avg_sentiment_score": round(self.avg_sentiment_score, 2),
            "resolution_rate": round(self.resolution_rate, 2)
        }


# ============================================================================
# CONVERSATIONAL INSIGHTS SERVICE
# ============================================================================

class ConversationalInsightsService:
    """
    Analyzes AI Receptionist conversations to extract actionable insights.

    Features:
    - Intent classification
    - Sentiment analysis
    - Objection detection
    - Trending topic identification
    - Question extraction
    """

    def __init__(self, db: Session, organization_id: int = None):
        self.db = db
        self.organization_id = organization_id
        self.client = None

        if ANTHROPIC_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)

    # ========================================================================
    # SINGLE CONVERSATION ANALYSIS
    # ========================================================================

    def analyze_conversation(
        self,
        transcript: str,
        conversation_id: str = None,
        timestamp: datetime = None
    ) -> ConversationInsight:
        """
        Analyze a single conversation transcript.

        Uses AI for deep analysis, falls back to keyword matching if unavailable.
        """
        if self.client:
            return self._analyze_with_ai(transcript, conversation_id, timestamp)
        else:
            return self._analyze_with_keywords(transcript, conversation_id, timestamp)

    def _analyze_with_ai(
        self,
        transcript: str,
        conversation_id: str,
        timestamp: datetime
    ) -> ConversationInsight:
        """Use Claude for intelligent conversation analysis."""
        prompt = f"""Analyze this mortgage-related phone conversation transcript and extract the following:

1. PRIMARY INTENT: What is the caller's main purpose? Choose from:
   - rate_inquiry, prequalification, refinance, purchase, document_question,
   - status_check, payment_question, complaint, general_info, appointment_request,
   - transfer_request, other

2. SENTIMENT: Overall emotional tone. Choose from:
   - very_positive, positive, neutral, negative, very_negative

3. OBJECTIONS: Any concerns or objections raised. Choose applicable from:
   - rate_too_high, fees_concern, timing, credit_concern, documentation,
   - trust, comparison_shopping, not_ready, other

4. KEY QUESTIONS: List the 3 most important questions asked by the caller.

5. TOPICS: Main topics discussed (max 5).

6. RESOLUTION: Was the caller's need resolved? (resolved, escalated, callback_scheduled, unresolved)

TRANSCRIPT:
{transcript[:3000]}

Respond in JSON format:
{{
  "intent": "...",
  "sentiment": "...",
  "objections": ["..."],
  "key_questions": ["..."],
  "topics": ["..."],
  "resolution": "..."
}}"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse JSON response
            response_text = response.content[0].text
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                return ConversationInsight(
                    conversation_id=conversation_id or "unknown",
                    timestamp=timestamp or datetime.now(timezone.utc),
                    intent=IntentCategory(data.get("intent", "other")),
                    sentiment=SentimentLevel(data.get("sentiment", "neutral")),
                    objections=[ObjectionType(o) for o in data.get("objections", []) if o in [e.value for e in ObjectionType]],
                    key_questions=data.get("key_questions", []),
                    topics_discussed=data.get("topics", []),
                    resolution_status=data.get("resolution", "unknown")
                )
        except Exception as e:
            logger.warning(f"AI analysis failed, falling back to keywords: {e}")

        return self._analyze_with_keywords(transcript, conversation_id, timestamp)

    def _analyze_with_keywords(
        self,
        transcript: str,
        conversation_id: str,
        timestamp: datetime
    ) -> ConversationInsight:
        """Fallback keyword-based analysis."""
        transcript_lower = transcript.lower()

        # Detect intent
        intent = IntentCategory.OTHER
        max_matches = 0
        for cat, keywords in INTENT_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in transcript_lower)
            if matches > max_matches:
                max_matches = matches
                intent = cat

        # Detect sentiment (simple)
        positive_words = ["great", "thank", "perfect", "excellent", "happy", "appreciate"]
        negative_words = ["frustrated", "angry", "disappointed", "problem", "issue", "wrong"]

        pos_count = sum(1 for w in positive_words if w in transcript_lower)
        neg_count = sum(1 for w in negative_words if w in transcript_lower)

        if pos_count > neg_count + 1:
            sentiment = SentimentLevel.POSITIVE
        elif neg_count > pos_count + 1:
            sentiment = SentimentLevel.NEGATIVE
        else:
            sentiment = SentimentLevel.NEUTRAL

        # Detect objections
        objections = []
        for obj, keywords in OBJECTION_KEYWORDS.items():
            if any(kw in transcript_lower for kw in keywords):
                objections.append(obj)

        # Extract questions (simple pattern)
        questions = re.findall(r'[^.!?]*\?', transcript)
        questions = [q.strip() for q in questions if len(q.strip()) > 10][:5]

        return ConversationInsight(
            conversation_id=conversation_id or "unknown",
            timestamp=timestamp or datetime.now(timezone.utc),
            intent=intent,
            sentiment=sentiment,
            objections=objections,
            key_questions=questions,
            topics_discussed=[intent.value],
            resolution_status="unknown"
        )

    # ========================================================================
    # BATCH ANALYSIS
    # ========================================================================

    def get_insights_summary(
        self,
        start_date: date = None,
        end_date: date = None,
        limit: int = 100
    ) -> InsightsSummary:
        """
        Get aggregated insights from recent conversations.
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        summary = InsightsSummary(period_start=start_date, period_end=end_date)

        # Fetch conversations
        conversations = self._fetch_conversations(start_date, end_date, limit)
        summary.total_conversations = len(conversations)

        if not conversations:
            return summary

        # Analyze each conversation
        insights = []
        for conv in conversations:
            transcript = conv.get("transcript") or conv.get("message_content", "")
            if transcript:
                insight = self.analyze_conversation(
                    transcript=transcript,
                    conversation_id=str(conv.get("id", "")),
                    timestamp=conv.get("timestamp") or conv.get("created_at")
                )
                insights.append(insight)

        # Aggregate results
        intent_counts = Counter(i.intent.value for i in insights)
        sentiment_counts = Counter(i.sentiment.value for i in insights)
        objection_counts = Counter(o.value for i in insights for o in i.objections)

        summary.intent_distribution = dict(intent_counts)
        summary.sentiment_distribution = dict(sentiment_counts)
        summary.objection_frequency = dict(objection_counts)

        # Calculate sentiment score (1-5 scale)
        sentiment_scores = {
            "very_negative": 1, "negative": 2, "neutral": 3,
            "positive": 4, "very_positive": 5
        }
        if insights:
            scores = [sentiment_scores.get(i.sentiment.value, 3) for i in insights]
            summary.avg_sentiment_score = sum(scores) / len(scores)

        # Resolution rate
        resolved = sum(1 for i in insights if i.resolution_status in ["resolved", "callback_scheduled"])
        summary.resolution_rate = (resolved / len(insights)) * 100 if insights else 0

        # Extract trending topics
        all_questions = []
        topic_counts = Counter()
        for insight in insights:
            all_questions.extend(insight.key_questions)
            for topic in insight.topics_discussed:
                topic_counts[topic] += 1

        # Top questions
        summary.top_questions = list(set(all_questions))[:10]

        # Trending topics
        for topic, count in topic_counts.most_common(10):
            summary.trending_topics.append(TrendingTopic(
                topic=topic,
                count=count,
                percentage=(count / len(insights)) * 100 if insights else 0,
                example_questions=[q for q in all_questions if topic.lower() in q.lower()][:3]
            ))

        return summary

    def _fetch_conversations(
        self,
        start_date: date,
        end_date: date,
        limit: int
    ) -> List[Dict]:
        """Fetch conversation records from database."""
        conversations = []

        # Try AI receptionist conversations table
        try:
            result = self.db.execute(text("""
                SELECT id, started_at as timestamp, transcript, outcome
                FROM ai_receptionist_conversations
                WHERE DATE(started_at) BETWEEN :start_date AND :end_date
                ORDER BY started_at DESC
                LIMIT :limit
            """), {"start_date": start_date, "end_date": end_date, "limit": limit})

            for row in result:
                conversations.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "transcript": row[2],
                    "outcome": row[3]
                })

            if conversations:
                return conversations
        except Exception as e:
            logger.debug(f"Could not fetch from ai_receptionist_conversations: {e}")

        # Try AI receptionist activity table
        try:
            result = self.db.execute(text("""
                SELECT id, timestamp, message_in, message_out, action_type
                FROM ai_receptionist_activity
                WHERE DATE(timestamp) BETWEEN :start_date AND :end_date
                ORDER BY timestamp DESC
                LIMIT :limit
            """), {"start_date": start_date, "end_date": end_date, "limit": limit})

            for row in result:
                conversations.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "transcript": f"Customer: {row[2] or ''}\nAI: {row[3] or ''}",
                    "action_type": row[4]
                })
        except SQLAlchemyError as e:
            logger.debug(f"Could not fetch from ai_receptionist_activity: {e}")

        return conversations

    # ========================================================================
    # SPECIFIC ANALYSIS ENDPOINTS
    # ========================================================================

    def get_trending_questions(
        self,
        days: int = 7,
        limit: int = 20
    ) -> List[Dict]:
        """Get most frequently asked questions."""
        summary = self.get_insights_summary(
            start_date=date.today() - timedelta(days=days),
            end_date=date.today()
        )
        return summary.top_questions[:limit]

    def get_objection_analysis(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get detailed objection analysis with handling recommendations."""
        summary = self.get_insights_summary(
            start_date=date.today() - timedelta(days=days),
            end_date=date.today()
        )

        # Add handling recommendations
        objection_recommendations = {
            "rate_too_high": "Emphasize total cost of ownership, not just rate. Highlight other benefits like service quality and closing speed.",
            "fees_concern": "Break down fees transparently. Offer to compare total costs with competitors.",
            "timing": "Ask about their timeline and what would make them ready. Offer to stay in touch.",
            "credit_concern": "Explain credit improvement strategies. Mention FHA and other flexible programs.",
            "documentation": "Simplify the process explanation. Offer document collection assistance.",
            "comparison_shopping": "Provide a clear comparison worksheet. Emphasize unique value propositions.",
            "not_ready": "Nurture with educational content. Set follow-up reminders.",
        }

        analysis = {
            "total_conversations": summary.total_conversations,
            "objections": []
        }

        for objection, count in sorted(summary.objection_frequency.items(), key=lambda x: -x[1]):
            analysis["objections"].append({
                "type": objection,
                "count": count,
                "percentage": round((count / summary.total_conversations) * 100, 1) if summary.total_conversations > 0 else 0,
                "recommendation": objection_recommendations.get(objection, "Review and develop handling strategy.")
            })

        return analysis

    def get_sentiment_trend(
        self,
        days: int = 30
    ) -> List[Dict]:
        """Get daily sentiment trend."""
        trends = []
        end_date = date.today()

        for i in range(days):
            day = end_date - timedelta(days=i)
            summary = self.get_insights_summary(start_date=day, end_date=day, limit=50)

            trends.append({
                "date": day.isoformat(),
                "avg_sentiment_score": summary.avg_sentiment_score,
                "total_conversations": summary.total_conversations,
                "sentiment_distribution": summary.sentiment_distribution
            })

        return list(reversed(trends))
