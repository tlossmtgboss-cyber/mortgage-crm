"""
Conversation Quality Analyzer

Analyzes conversation quality to identify:
- Poor AI responses that need review
- Confused borrowers needing human intervention
- Missed opportunities for improvement
- Training examples from successful conversations

Quality Dimensions:
- Clarity: Are responses clear and jargon-free?
- Engagement: Is the borrower actively participating?
- Progression: Is the conversation advancing appropriately?
- Outcome: Did we achieve a positive result?
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class QualityFlag(str, Enum):
    """Quality issues that can be flagged"""
    STUCK_PHASE_1 = "stuck_phase_1"
    LOW_ENGAGEMENT = "low_engagement"
    REPETITIVE_QUESTIONS = "repetitive_questions"
    MISSED_CTA_OPPORTUNITY = "missed_cta_opportunity"
    BORROWER_CONFUSED = "borrower_confused"
    EXCESSIVE_JARGON = "excessive_jargon"
    RESPONSE_TOO_LONG = "response_too_long"
    NO_QUESTIONS_ASKED = "no_questions_asked"
    RAPID_ABANDONMENT = "rapid_abandonment"


@dataclass
class QualityMetrics:
    """Quality metrics for a conversation"""
    overall_score: float          # 0-100
    clarity_score: float          # 0-100
    engagement_score: float       # 0-100
    progression_score: float      # 0-100
    outcome_score: float          # 0-100
    flags: List[QualityFlag] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'overall_score': round(self.overall_score, 2),
            'clarity_score': round(self.clarity_score, 2),
            'engagement_score': round(self.engagement_score, 2),
            'progression_score': round(self.progression_score, 2),
            'outcome_score': round(self.outcome_score, 2),
            'flags': [f.value for f in self.flags],
            'recommendations': self.recommendations,
            'grade': self._get_grade(),
        }

    def _get_grade(self) -> str:
        """Get letter grade based on overall score"""
        if self.overall_score >= 90:
            return 'A'
        elif self.overall_score >= 80:
            return 'B'
        elif self.overall_score >= 70:
            return 'C'
        elif self.overall_score >= 60:
            return 'D'
        return 'F'


class ConversationQualityAnalyzer:
    """
    Analyze conversation quality for improvement opportunities.

    Usage:
        analyzer = ConversationQualityAnalyzer()
        metrics = analyzer.analyze_conversation(messages, session)
    """

    # Jargon words that should be explained if used
    JARGON_WORDS = [
        'amortization', 'escrow', 'origination', 'underwriting',
        'apr', 'pmi', 'dti', 'ltv', 'piti', 'fico',
        'conforming', 'non-conforming', 'jumbo', 'arm',
        'basis points', 'lock', 'float', 'buydown',
        'points', 'seasoning', 'impound', 'subordinate'
    ]

    # Confusion indicators in user messages
    CONFUSION_PHRASES = [
        'confused', "don't understand", "don't get it",
        'what do you mean', 'huh', 'what?', 'i dont know',
        "that doesn't make sense", 'can you explain',
        "i'm lost", 'too complicated', 'over my head'
    ]

    # Disengagement indicators
    DISENGAGEMENT_PHRASES = [
        'never mind', 'not interested', 'no thanks',
        'goodbye', 'bye', 'forget it', "i'll pass",
        'maybe later', 'not now', "i'm good"
    ]

    def analyze_conversation(
        self,
        messages: List[Dict[str, str]],
        session: Any  # ChatSession model
    ) -> QualityMetrics:
        """
        Comprehensive quality analysis of a conversation.

        Args:
            messages: List of message dicts with 'role' and 'content'
            session: ChatSession model instance

        Returns:
            QualityMetrics with scores and flags
        """
        user_messages = [m for m in messages if m.get('role') == 'user']
        assistant_messages = [m for m in messages if m.get('role') == 'assistant']

        # Calculate individual scores
        clarity = self._analyze_clarity(assistant_messages)
        engagement = self._analyze_engagement(user_messages, session)
        progression = self._analyze_progression(session)
        outcome = self._analyze_outcome(session)

        # Weighted average
        overall = (
            clarity * 0.25 +
            engagement * 0.30 +
            progression * 0.25 +
            outcome * 0.20
        )

        # Identify issues
        flags = self._identify_flags(messages, session)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            flags, clarity, engagement, progression, outcome
        )

        return QualityMetrics(
            overall_score=overall,
            clarity_score=clarity,
            engagement_score=engagement,
            progression_score=progression,
            outcome_score=outcome,
            flags=flags,
            recommendations=recommendations
        )

    def _analyze_clarity(self, assistant_messages: List[Dict]) -> float:
        """Analyze if AI responses are clear and helpful"""
        if not assistant_messages:
            return 50.0

        score = 100.0
        issues_found = 0

        for msg in assistant_messages:
            content = msg.get('content', '')
            content_lower = content.lower()

            # Penalty for overly long responses (>400 words)
            word_count = len(content.split())
            if word_count > 400:
                score -= 5
                issues_found += 1

            # Penalty for jargon without explanation
            for jargon in self.JARGON_WORDS:
                if jargon in content_lower:
                    # Check if explanation follows
                    explain_indicators = ['means', 'which is', 'this is', 'basically', 'in other words']
                    has_explanation = any(ind in content_lower for ind in explain_indicators)
                    if not has_explanation:
                        score -= 3
                        issues_found += 1

            # Penalty for not answering (apologizing without helping)
            if 'sorry' in content_lower and "can't" in content_lower:
                if 'but' not in content_lower and 'however' not in content_lower:
                    score -= 10
                    issues_found += 1

            # Bonus for using formatting (lists, structure)
            if '•' in content or '1.' in content or '\n-' in content:
                score += 2

        return max(0, min(100, score))

    def _analyze_engagement(
        self,
        user_messages: List[Dict],
        session: Any
    ) -> float:
        """Analyze borrower engagement level"""
        if not user_messages:
            return 0.0

        score = 50.0  # Start neutral

        # Positive: Message length indicates engagement
        total_words = sum(len(m.get('content', '').split()) for m in user_messages)
        avg_words = total_words / len(user_messages)

        if avg_words > 15:
            score += 25  # Detailed responses
        elif avg_words > 8:
            score += 15  # Moderate detail
        elif avg_words < 3:
            score -= 15  # Very short responses

        # Positive: Questions indicate interest
        questions = sum(1 for m in user_messages if '?' in m.get('content', ''))
        score += min(20, questions * 7)

        # Positive: Multiple messages
        if len(user_messages) >= 5:
            score += 15
        elif len(user_messages) >= 3:
            score += 10
        elif len(user_messages) == 1:
            score -= 20

        # Negative: Disengagement phrases
        for msg in user_messages:
            content_lower = msg.get('content', '').lower()
            if any(phrase in content_lower for phrase in self.DISENGAGEMENT_PHRASES):
                score -= 25

        # Negative: Confusion phrases
        confusion_count = sum(
            1 for msg in user_messages
            if any(phrase in msg.get('content', '').lower() for phrase in self.CONFUSION_PHRASES)
        )
        score -= confusion_count * 10

        return max(0, min(100, score))

    def _analyze_progression(self, session: Any) -> float:
        """Analyze if conversation is progressing appropriately"""
        score = 100.0

        current_phase = getattr(session, 'current_phase', 1)
        turn_count = getattr(session, 'turn_count', 0)

        # Expected phase by turn count
        expected_progressions = [
            (3, 2),   # By turn 3, should be in phase 2
            (5, 2),   # By turn 5, should still be at least phase 2
            (7, 3),   # By turn 7, should be in phase 3
            (10, 4),  # By turn 10, should be in phase 4
        ]

        for turns, expected_phase in expected_progressions:
            if turn_count >= turns and current_phase < expected_phase:
                score -= 15

        # Heavy penalty for stuck in phase 1 after many turns
        if turn_count > 5 and current_phase == 1:
            score -= 30

        # Bonus for rapid progression
        if turn_count <= 5 and current_phase >= 3:
            score += 15

        return max(0, min(100, score))

    def _analyze_outcome(self, session: Any) -> float:
        """Analyze conversation outcome"""
        cta_accepted = getattr(session, 'cta_accepted', False)
        cta_offered = getattr(session, 'cta_offered', None)
        current_phase = getattr(session, 'current_phase', 1)
        intent_score = getattr(session, 'intent_score', 0)

        if cta_accepted:
            return 100.0

        if cta_offered and cta_offered != 'none':
            # CTA offered but not accepted
            return 40.0

        if current_phase >= 4:
            # Ready for CTA but not offered
            return 25.0

        # Based on intent score and phase
        if intent_score >= 70:
            return 50.0
        elif intent_score >= 50:
            return 35.0
        elif intent_score >= 30:
            return 20.0

        return 10.0

    def _identify_flags(
        self,
        messages: List[Dict],
        session: Any
    ) -> List[QualityFlag]:
        """Identify specific quality issues"""
        flags = []
        user_messages = [m for m in messages if m.get('role') == 'user']
        assistant_messages = [m for m in messages if m.get('role') == 'assistant']

        turn_count = getattr(session, 'turn_count', 0)
        current_phase = getattr(session, 'current_phase', 1)
        intent_score = getattr(session, 'intent_score', 0)
        cta_offered = getattr(session, 'cta_offered', None)

        # Stuck in early phase
        if turn_count > 5 and current_phase == 1:
            flags.append(QualityFlag.STUCK_PHASE_1)

        # Low engagement
        if len(user_messages) > 3:
            avg_length = sum(len(m.get('content', '')) for m in user_messages) / len(user_messages)
            if avg_length < 20:
                flags.append(QualityFlag.LOW_ENGAGEMENT)

        # Repetitive questions
        user_contents = [m.get('content', '').lower().strip() for m in user_messages]
        if len(user_contents) != len(set(user_contents)):
            flags.append(QualityFlag.REPETITIVE_QUESTIONS)

        # High intent but no CTA
        if intent_score >= 70 and (not cta_offered or cta_offered == 'none'):
            flags.append(QualityFlag.MISSED_CTA_OPPORTUNITY)

        # Borrower confusion
        for msg in user_messages:
            content_lower = msg.get('content', '').lower()
            if any(phrase in content_lower for phrase in self.CONFUSION_PHRASES):
                flags.append(QualityFlag.BORROWER_CONFUSED)
                break

        # Excessive jargon in responses
        jargon_count = 0
        for msg in assistant_messages:
            content_lower = msg.get('content', '').lower()
            jargon_count += sum(1 for j in self.JARGON_WORDS if j in content_lower)
        if jargon_count > 5:
            flags.append(QualityFlag.EXCESSIVE_JARGON)

        # Response too long
        for msg in assistant_messages:
            if len(msg.get('content', '').split()) > 500:
                flags.append(QualityFlag.RESPONSE_TOO_LONG)
                break

        # No questions asked by AI
        ai_questions = sum(1 for m in assistant_messages if '?' in m.get('content', ''))
        if len(assistant_messages) >= 3 and ai_questions == 0:
            flags.append(QualityFlag.NO_QUESTIONS_ASKED)

        # Rapid abandonment (few turns, left quickly)
        if turn_count <= 2 and not getattr(session, 'is_active', True):
            flags.append(QualityFlag.RAPID_ABANDONMENT)

        return list(set(flags))  # Dedupe

    def _generate_recommendations(
        self,
        flags: List[QualityFlag],
        clarity: float,
        engagement: float,
        progression: float,
        outcome: float
    ) -> List[str]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []

        # Flag-based recommendations
        flag_recommendations = {
            QualityFlag.STUCK_PHASE_1: "Review phase transition logic - conversation not advancing",
            QualityFlag.LOW_ENGAGEMENT: "Consider more engaging questions or simpler language",
            QualityFlag.REPETITIVE_QUESTIONS: "AI may not be understanding user intent - review NLU",
            QualityFlag.MISSED_CTA_OPPORTUNITY: "CTA should have been offered - check phase 4 triggers",
            QualityFlag.BORROWER_CONFUSED: "User showed confusion - review response clarity",
            QualityFlag.EXCESSIVE_JARGON: "Too much industry jargon - simplify language",
            QualityFlag.RESPONSE_TOO_LONG: "Responses too verbose - aim for conciseness",
            QualityFlag.NO_QUESTIONS_ASKED: "AI should ask more questions to gather information",
            QualityFlag.RAPID_ABANDONMENT: "User left quickly - review initial greeting/engagement",
        }

        for flag in flags:
            if flag in flag_recommendations:
                recommendations.append(flag_recommendations[flag])

        # Score-based recommendations
        if clarity < 60:
            recommendations.append("Focus on clearer, simpler explanations")

        if engagement < 50:
            recommendations.append("Improve engagement through personalization and questions")

        if progression < 60:
            recommendations.append("Review phase advancement criteria")

        if outcome == 100:
            recommendations.append("Use as training example for successful conversion")

        return recommendations[:5]  # Max 5 recommendations


def get_quality_summary(metrics: QualityMetrics) -> str:
    """Generate human-readable quality summary"""
    grade = metrics._get_grade()

    if grade == 'A':
        return f"Excellent conversation (Score: {metrics.overall_score:.0f}). Use as training example."
    elif grade == 'B':
        return f"Good conversation (Score: {metrics.overall_score:.0f}). Minor improvements possible."
    elif grade == 'C':
        return f"Average conversation (Score: {metrics.overall_score:.0f}). Review for improvement opportunities."
    elif grade == 'D':
        return f"Below average (Score: {metrics.overall_score:.0f}). Needs review: {', '.join(f.value for f in metrics.flags[:3])}"
    else:
        return f"Poor conversation (Score: {metrics.overall_score:.0f}). Manual review recommended."
