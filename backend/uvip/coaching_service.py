"""
UVIP - Coaching Service
Generates personalized coaching recommendations based on analytics.
"""

from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class CoachingService:
    """Generate personalized coaching recommendations"""

    async def generate_coaching(
        self,
        analytics: Dict,
        transcript_segments: List[Dict],
        db: Session,
        models: Dict
    ) -> List[Dict]:
        """Generate coaching recommendations based on analytics"""

        CoachingRecommendation = models.get('CoachingRecommendation')
        recommendations = []

        # 1. Talk-Listen Ratio Coaching
        talk_ratio = analytics.get("talk_listen_ratio", 0.5)
        if talk_ratio > 0.7:
            recommendations.append({
                "category": "listening",
                "recommendation": "You talked 70%+ of the time. In discovery calls, aim for 40-50% to better understand borrower needs. Try asking more open-ended questions.",
                "priority": "high",
                "evidence": {
                    "current_ratio": f"{talk_ratio:.0%}",
                    "target_ratio": "40-50%",
                    "action": "Ask 3-5 more questions next time"
                }
            })
        elif talk_ratio < 0.3:
            recommendations.append({
                "category": "engagement",
                "recommendation": "You only spoke 30% of the time. Make sure you're guiding the conversation and explaining key mortgage concepts clearly.",
                "priority": "medium",
                "evidence": {
                    "current_ratio": f"{talk_ratio:.0%}",
                    "target_ratio": "40-50%"
                }
            })

        # 2. Monologue Coaching
        longest_monologue = analytics.get("longest_monologue_seconds", 0)
        if longest_monologue > 180:
            minutes = longest_monologue // 60
            recommendations.append({
                "category": "pacing",
                "recommendation": f"Your longest explanation was {minutes} minutes. Break complex topics into chunks and check for understanding every 60-90 seconds.",
                "priority": "high",
                "evidence": {
                    "longest_monologue": f"{longest_monologue}s",
                    "threshold": "180s (3 minutes)"
                }
            })

        # 3. Interruption Coaching
        interruption_count = analytics.get("interruption_count", 0)
        if interruption_count > 3:
            recommendations.append({
                "category": "listening",
                "recommendation": f"You interrupted {interruption_count} times. Practice the '2-second pause' - count to 2 before responding to ensure the borrower is finished speaking.",
                "priority": "high",
                "evidence": {
                    "interruption_count": interruption_count,
                    "threshold": "3 interruptions per call"
                }
            })

        # 4. Question Coaching
        question_count = analytics.get("question_count", 0)
        if question_count < 3:
            recommendations.append({
                "category": "questioning",
                "recommendation": f"You only asked {question_count} questions. Use open-ended questions to uncover borrower concerns: 'What's most important to you in this purchase?' 'What questions do you have?'",
                "priority": "high",
                "evidence": {
                    "question_count": question_count,
                    "recommended_minimum": "5-8 questions per discovery call"
                }
            })

        # 5. Filler Word Coaching
        filler_count = analytics.get("filler_word_count", 0)
        if filler_count > 20:
            recommendations.append({
                "category": "clarity",
                "recommendation": f"You used {filler_count} filler words (um, uh, like). Practice pausing instead. Silence is more professional than fillers.",
                "priority": "low",
                "evidence": {
                    "filler_count": filler_count,
                    "threshold": "20 per call"
                }
            })

        # 6. Speaking Pace Coaching
        speaking_pace = analytics.get("speaking_pace_wpm", 0)
        if speaking_pace > 180:
            recommendations.append({
                "category": "pacing",
                "recommendation": f"Your speaking pace ({speaking_pace} WPM) is fast. Slow down to 140-160 WPM to ensure borrowers can follow complex mortgage information.",
                "priority": "medium",
                "evidence": {
                    "current_pace": f"{speaking_pace} WPM",
                    "target_pace": "140-160 WPM"
                }
            })
        elif speaking_pace > 0 and speaking_pace < 100:
            recommendations.append({
                "category": "pacing",
                "recommendation": f"Your speaking pace ({speaking_pace} WPM) is slow. Try to maintain 140-160 WPM to keep the conversation engaging.",
                "priority": "low",
                "evidence": {
                    "current_pace": f"{speaking_pace} WPM",
                    "target_pace": "140-160 WPM"
                }
            })

        # 7. Sentiment Coaching
        negative_pct = analytics.get("sentiment_negative_pct", 0)
        if negative_pct > 30:
            recommendations.append({
                "category": "positivity",
                "recommendation": "Your language had 30%+ negative words (problem, issue, concern). Reframe challenges positively: 'Here's how we'll solve that' vs 'That's a problem.'",
                "priority": "medium",
                "evidence": {
                    "negative_sentiment": f"{negative_pct:.1f}%",
                    "target": "<20%"
                }
            })

        # 8. Mortgage-Specific Coaching
        mortgage_coaching = await self._generate_mortgage_coaching(transcript_segments)
        recommendations.extend(mortgage_coaching)

        # Save to database if analytics_id is available
        analytics_id = analytics.get("id")
        if analytics_id and CoachingRecommendation:
            for rec in recommendations:
                coaching_rec = CoachingRecommendation(
                    analytics_id=analytics_id,
                    category=rec["category"],
                    recommendation=rec["recommendation"],
                    priority=rec["priority"],
                    evidence=rec.get("evidence")
                )
                db.add(coaching_rec)
            db.commit()

        return recommendations

    async def _generate_mortgage_coaching(
        self,
        transcript_segments: List[Dict]
    ) -> List[Dict]:
        """Generate mortgage-specific coaching recommendations"""

        recommendations = []

        if not transcript_segments:
            return recommendations

        full_text = " ".join(
            seg.get('text', '') for seg in transcript_segments
        ).lower()

        # Check for rate explanation
        if "rate" in full_text:
            if "lock" not in full_text:
                recommendations.append({
                    "category": "mortgage_knowledge",
                    "recommendation": "You discussed rates but didn't mention rate locks. Always explain: 'We can lock your rate for 30-60 days to protect against increases.'",
                    "priority": "medium",
                    "evidence": {"mentioned": "rate", "missing": "rate lock explanation"}
                })

        # Check for timeline discussion
        timeline_keywords = ["timeline", "close", "closing", "days", "weeks"]
        if not any(kw in full_text for kw in timeline_keywords):
            recommendations.append({
                "category": "process_clarity",
                "recommendation": "Set clear timeline expectations. Borrowers appreciate knowing: 'Pre-approval takes 24 hours, full approval 5-7 days, closing in 30 days.'",
                "priority": "high",
                "evidence": {"missing": "timeline/closing date discussion"}
            })

        # Check for costs discussion
        cost_keywords = ["closing costs", "fees", "down payment", "cash to close"]
        if not any(kw in full_text for kw in cost_keywords):
            recommendations.append({
                "category": "mortgage_knowledge",
                "recommendation": "Consider discussing costs upfront. Borrowers want to know: 'Typical closing costs are 2-5% of loan amount.'",
                "priority": "medium",
                "evidence": {"missing": "closing costs discussion"}
            })

        # Check for document discussion
        doc_keywords = ["documents", "paperwork", "w2", "tax returns", "pay stubs", "bank statements"]
        if not any(kw in full_text for kw in doc_keywords):
            recommendations.append({
                "category": "process_clarity",
                "recommendation": "Prepare borrowers for documentation needs. Set expectations: 'You'll need last 2 years of tax returns, recent pay stubs, and bank statements.'",
                "priority": "medium",
                "evidence": {"missing": "document requirements discussion"}
            })

        # Check for objection handling opportunities
        objection_words = ["but", "concerned", "worried", "expensive", "afford", "not sure"]
        if any(word in full_text for word in objection_words):
            # Check if they used good objection handling
            handling_phrases = ["understand", "that's common", "let me explain", "good question"]
            if not any(phrase in full_text for phrase in handling_phrases):
                recommendations.append({
                    "category": "objection_handling",
                    "recommendation": "When addressing concerns, try the 'Feel, Felt, Found' technique: 'I understand how you feel. Others felt that way too. Here's what they found...'",
                    "priority": "medium",
                    "evidence": {"objections_detected": True, "suggestion": "Use empathetic response techniques"}
                })

        # Check for next steps
        next_step_keywords = ["next step", "what's next", "from here", "follow up", "i'll send", "i'll call"]
        if not any(kw in full_text for kw in next_step_keywords):
            recommendations.append({
                "category": "process_clarity",
                "recommendation": "Always end with clear next steps. Tell the borrower: 'Here's exactly what happens next...' to keep them engaged.",
                "priority": "high",
                "evidence": {"missing": "clear next steps"}
            })

        return recommendations

    async def get_user_coaching_summary(
        self,
        user_id: int,
        db: Session,
        models: Dict,
        days: int = 30
    ) -> Dict:
        """Get coaching summary for a user over a time period"""

        from datetime import timedelta

        ParticipantAnalytics = models.get('ParticipantAnalytics')
        CoachingRecommendation = models.get('CoachingRecommendation')
        MeetingParticipant = models.get('MeetingParticipant')

        if not all([ParticipantAnalytics, CoachingRecommendation, MeetingParticipant]):
            return {"error": "Required models not available"}

        # Get analytics for this user's meetings
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        analytics_records = db.query(ParticipantAnalytics).join(
            MeetingParticipant,
            ParticipantAnalytics.participant_id == MeetingParticipant.id
        ).filter(
            MeetingParticipant.user_id == user_id,
            ParticipantAnalytics.created_at >= cutoff_date
        ).all()

        if not analytics_records:
            return {
                "user_id": user_id,
                "meetings_analyzed": 0,
                "message": "No analytics found for this period"
            }

        # Calculate averages
        avg_talk_ratio = sum(a.talk_listen_ratio or 0 for a in analytics_records) / len(analytics_records)
        avg_question_count = sum(a.question_count or 0 for a in analytics_records) / len(analytics_records)
        avg_interruptions = sum(a.interruption_count or 0 for a in analytics_records) / len(analytics_records)
        avg_engagement = sum(a.engagement_score or 0 for a in analytics_records) / len(analytics_records)
        total_filler_words = sum(a.filler_word_count or 0 for a in analytics_records)

        # Get all coaching recommendations
        analytics_ids = [a.id for a in analytics_records]
        all_recommendations = db.query(CoachingRecommendation).filter(
            CoachingRecommendation.analytics_id.in_(analytics_ids)
        ).all()

        # Group by category
        recommendations_by_category = {}
        for rec in all_recommendations:
            if rec.category not in recommendations_by_category:
                recommendations_by_category[rec.category] = []
            recommendations_by_category[rec.category].append(rec)

        # Find top priorities
        top_priorities = sorted(
            [
                {
                    "category": category,
                    "frequency": len(recs),
                    "latest_recommendation": recs[-1].recommendation if recs else None
                }
                for category, recs in recommendations_by_category.items()
            ],
            key=lambda x: x["frequency"],
            reverse=True
        )[:5]

        return {
            "user_id": user_id,
            "meetings_analyzed": len(analytics_records),
            "period_days": days,
            "averages": {
                "talk_listen_ratio": round(avg_talk_ratio, 2),
                "question_count_per_call": round(avg_question_count, 1),
                "interruption_count_per_call": round(avg_interruptions, 1),
                "engagement_score": round(avg_engagement, 2)
            },
            "totals": {
                "total_filler_words": total_filler_words,
                "total_recommendations": len(all_recommendations)
            },
            "top_coaching_priorities": top_priorities,
            "recommendations_by_category": {
                category: len(recs)
                for category, recs in recommendations_by_category.items()
            }
        }


# Service singleton
_coaching_service: Optional[CoachingService] = None


def get_coaching_service() -> CoachingService:
    """Get or create the coaching service singleton"""
    global _coaching_service
    if _coaching_service is None:
        _coaching_service = CoachingService()
    return _coaching_service
