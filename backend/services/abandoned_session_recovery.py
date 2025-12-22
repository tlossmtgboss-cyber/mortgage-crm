"""
Abandoned Session Recovery - Revenue Recovery Workflows

This service identifies and recovers abandoned high-intent sessions:
- Find sessions that went silent at high engagement points
- Generate context summaries for LO follow-up
- Trigger notifications to recovery workflows
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text

from chat_state_machine_models import (
    ChatSession, ChatMessage, CallRequest,
    ChatPhase, UrgencyLevel, CTAType
)

logger = logging.getLogger(__name__)


class AbandonedSessionRecovery:
    """Identify and recover abandoned high-intent sessions"""

    def __init__(self, db: Session):
        self.db = db

    async def find_abandoned_sessions(
        self,
        hours_inactive: int = 2,
        max_hours_old: int = 168,  # 7 days
        min_intent_score: int = 60,
        min_phase: int = 3,
        microsite_id: Optional[int] = None,
        loan_officer_id: Optional[int] = None,
    ) -> List[ChatSession]:
        """
        Find high-intent sessions that went silent.

        Criteria:
        - Phase 3 or 4 (personalization started)
        - Intent score >= min_intent_score
        - No messages in last X hours
        - Not older than max_hours_old
        - No CTA accepted

        Args:
            hours_inactive: Hours without activity to consider abandoned
            max_hours_old: Maximum age of session to consider
            min_intent_score: Minimum intent score threshold
            min_phase: Minimum phase reached
            microsite_id: Optional filter by microsite
            loan_officer_id: Optional filter by LO

        Returns:
            List of abandoned high-intent sessions
        """
        now = datetime.now(timezone.utc)
        inactive_cutoff = now - timedelta(hours=hours_inactive)
        age_cutoff = now - timedelta(hours=max_hours_old)

        filters = [
            ChatSession.last_message_at < inactive_cutoff,
            ChatSession.last_message_at > age_cutoff,
            ChatSession.current_phase >= min_phase,
            ChatSession.intent_score >= min_intent_score,
            ChatSession.cta_accepted == False,
            ChatSession.is_active == True,
        ]

        if microsite_id:
            filters.append(ChatSession.microsite_id == microsite_id)
        if loan_officer_id:
            filters.append(ChatSession.loan_officer_id == loan_officer_id)

        abandoned = self.db.query(ChatSession).filter(
            and_(*filters)
        ).order_by(
            ChatSession.intent_score.desc(),
            ChatSession.last_message_at.desc()
        ).all()

        logger.info(f"Found {len(abandoned)} abandoned high-intent sessions")
        return abandoned

    def get_recovery_priority(self, session: ChatSession) -> str:
        """
        Determine recovery priority based on session characteristics.

        Returns: 'critical', 'high', 'medium', 'low'
        """
        score = 0

        # Intent score contribution
        if session.intent_score >= 80:
            score += 40
        elif session.intent_score >= 70:
            score += 30
        elif session.intent_score >= 60:
            score += 20

        # Phase contribution
        if session.current_phase >= 4:
            score += 30
        elif session.current_phase >= 3:
            score += 20

        # Urgency contribution
        if session.urgency == UrgencyLevel.HIGH.value:
            score += 20
        elif session.urgency == UrgencyLevel.MEDIUM.value:
            score += 10

        # Contact info bonus
        if session.contact_phone or session.contact_email:
            score += 15

        # Timeline signal bonus
        signals = session.intent_signals or []
        if any(s.get('signal') == 'timeline' for s in signals):
            score += 10

        # Determine priority level
        if score >= 80:
            return 'critical'
        elif score >= 60:
            return 'high'
        elif score >= 40:
            return 'medium'
        return 'low'

    def generate_recovery_context(self, session: ChatSession) -> Dict[str, Any]:
        """
        Generate detailed context for LO follow-up.

        This provides everything the LO needs to make an effective
        recovery call without reading the full transcript.
        """
        signals = session.intent_signals or []
        signal_map = {s.get('signal'): s.get('value') for s in signals}

        # Get last few messages for context
        last_messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.desc()).limit(4).all()

        last_messages.reverse()  # Chronological order

        # Calculate time since last activity
        now = datetime.now(timezone.utc)
        hours_since_activity = 0
        if session.last_message_at:
            hours_since_activity = (now - session.last_message_at).total_seconds() / 3600

        return {
            'session_id': str(session.id),
            'visitor_id': session.visitor_id,
            'priority': self.get_recovery_priority(session),

            # Timing
            'created_at': session.created_at.isoformat() if session.created_at else None,
            'last_activity': session.last_message_at.isoformat() if session.last_message_at else None,
            'hours_since_activity': round(hours_since_activity, 1),

            # Engagement metrics
            'intent_score': session.intent_score,
            'phase_reached': session.current_phase,
            'turn_count': session.turn_count,
            'urgency': session.urgency,

            # Contact info
            'contact': {
                'name': session.contact_name,
                'phone': session.contact_phone,
                'email': session.contact_email,
                'has_contact_info': bool(session.contact_phone or session.contact_email)
            },

            # What we learned
            'signals': {
                'goal': signal_map.get('goal'),
                'timeline': signal_map.get('timeline'),
                'price_range': signal_map.get('price'),
                'loan_type': signal_map.get('loan_type'),
                'down_payment': signal_map.get('down_payment'),
                'credit_range': signal_map.get('credit_band'),
            },

            # Conversation summary
            'conversation_summary': self._generate_summary(session, signals),

            # Last messages for quick context
            'last_messages': [
                {
                    'role': msg.role,
                    'content': msg.content[:200] + '...' if len(msg.content) > 200 else msg.content,
                    'timestamp': msg.created_at.isoformat() if msg.created_at else None
                }
                for msg in last_messages
            ],

            # CTA history
            'cta_history': {
                'offered': session.cta_offered,
                'declined_count': session.cta_declined_count,
                'was_offered_call': session.cta_offered == CTAType.CALL_NOW.value,
            },

            # Suggested approach
            'recovery_approach': self._suggest_recovery_approach(session, signals),
        }

    def _generate_summary(self, session: ChatSession, signals: List[Dict]) -> str:
        """Generate human-readable summary for LO"""
        signal_types = [s.get('signal') for s in signals]

        summary_parts = []

        # Intent level
        if session.intent_score >= 80:
            summary_parts.append("Very high intent buyer")
        elif session.intent_score >= 70:
            summary_parts.append("High intent")
        elif session.intent_score >= 60:
            summary_parts.append("Moderate-high intent")
        else:
            summary_parts.append("Moderate intent")

        # Key signals
        if 'timeline' in signal_types:
            timeline_val = next((s.get('value') for s in signals if s.get('signal') == 'timeline'), None)
            if timeline_val:
                summary_parts.append(f"timeline: {timeline_val}")

        if 'price' in signal_types:
            price_val = next((s.get('value') for s in signals if s.get('signal') == 'price'), None)
            if price_val:
                summary_parts.append(f"budget: {price_val}")

        if 'goal' in signal_types:
            goal_val = next((s.get('value') for s in signals if s.get('signal') == 'goal'), None)
            if goal_val:
                summary_parts.append(f"looking to {goal_val}")

        # Contact status
        if session.contact_phone:
            summary_parts.append("phone number collected")
        elif session.contact_email:
            summary_parts.append("email collected")

        return " | ".join(summary_parts) if summary_parts else "Engaged prospect, needs follow-up"

    def _suggest_recovery_approach(self, session: ChatSession, signals: List[Dict]) -> Dict[str, Any]:
        """Suggest best recovery approach based on session context"""
        signal_types = [s.get('signal') for s in signals]

        # Determine best channel
        if session.contact_phone:
            preferred_channel = 'phone'
            channel_reason = 'Phone number available - direct call recommended'
        elif session.contact_email:
            preferred_channel = 'email'
            channel_reason = 'Email available - personalized follow-up recommended'
        else:
            preferred_channel = 'chat_follow_up'
            channel_reason = 'No contact info - wait for return visit or retarget'

        # Determine talking points
        talking_points = []

        if 'timeline' in signal_types:
            timeline_val = next((s.get('value') for s in signals if s.get('signal') == 'timeline'), '')
            talking_points.append(f"Reference their timeline: {timeline_val}")

        if 'price' in signal_types:
            price_val = next((s.get('value') for s in signals if s.get('signal') == 'price'), '')
            talking_points.append(f"Mention you looked at options in their {price_val} range")

        if session.urgency == UrgencyLevel.HIGH.value:
            talking_points.append("Acknowledge their urgency and readiness to move quickly")

        if session.cta_declined_count > 0:
            talking_points.append("Don't push too hard - they declined before. Be helpful, not salesy")

        if not talking_points:
            talking_points.append("Ask what held them back and how you can help")

        return {
            'preferred_channel': preferred_channel,
            'channel_reason': channel_reason,
            'talking_points': talking_points,
            'tone': 'helpful and curious' if session.cta_declined_count > 0 else 'warm and direct',
            'urgency_of_follow_up': self.get_recovery_priority(session),
        }

    async def get_recovery_queue(
        self,
        loan_officer_id: Optional[int] = None,
        microsite_id: Optional[int] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get prioritized queue of sessions needing recovery.

        Returns list of recovery contexts sorted by priority.
        """
        abandoned = await self.find_abandoned_sessions(
            loan_officer_id=loan_officer_id,
            microsite_id=microsite_id,
        )

        # Generate context and sort by priority
        recovery_items = []
        for session in abandoned[:limit]:
            context = self.generate_recovery_context(session)
            recovery_items.append(context)

        # Sort by priority (critical > high > medium > low)
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        recovery_items.sort(key=lambda x: (
            priority_order.get(x['priority'], 4),
            -x['intent_score']  # Higher score first within priority
        ))

        return recovery_items

    async def mark_session_recovered(
        self,
        session_id: UUID,
        recovery_outcome: str,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Mark a session as recovered/followed-up.

        Args:
            session_id: The session that was recovered
            recovery_outcome: 'converted', 'scheduled_callback', 'not_interested', 'no_answer'
            notes: Optional notes about the recovery attempt
        """
        session = self.db.query(ChatSession).filter(
            ChatSession.id == session_id
        ).first()

        if not session:
            return False

        # For now, we'll end the session to prevent it appearing in recovery queue again
        # In a full implementation, you'd have a separate recovery_attempts table
        session.is_active = False
        session.ended_at = datetime.now(timezone.utc)

        self.db.commit()
        logger.info(f"Session {session_id} marked as recovered: {recovery_outcome}")

        return True

    def get_abandonment_stats(
        self,
        days: int = 30,
        microsite_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get statistics about session abandonment patterns."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        filters = [ChatSession.created_at > cutoff]
        if microsite_id:
            filters.append(ChatSession.microsite_id == microsite_id)

        # Total sessions
        total = self.db.query(func.count(ChatSession.id)).filter(
            and_(*filters)
        ).scalar() or 0

        # Abandoned high-intent (phase 3+, score 60+, no CTA accepted)
        abandoned_high_intent = self.db.query(func.count(ChatSession.id)).filter(
            and_(
                *filters,
                ChatSession.current_phase >= 3,
                ChatSession.intent_score >= 60,
                ChatSession.cta_accepted == False,
            )
        ).scalar() or 0

        # Abandoned by phase
        by_phase = self.db.query(
            ChatSession.current_phase,
            func.count(ChatSession.id)
        ).filter(
            and_(
                *filters,
                ChatSession.cta_accepted == False,
            )
        ).group_by(ChatSession.current_phase).all()

        # Average intent score at abandonment
        avg_score = self.db.query(
            func.avg(ChatSession.intent_score)
        ).filter(
            and_(
                *filters,
                ChatSession.cta_accepted == False,
            )
        ).scalar() or 0

        return {
            'period_days': days,
            'total_sessions': total,
            'abandoned_high_intent': abandoned_high_intent,
            'abandonment_rate': round((abandoned_high_intent / total * 100), 2) if total > 0 else 0,
            'by_phase': {str(phase): count for phase, count in by_phase},
            'avg_intent_score_at_abandon': round(float(avg_score), 1),
            'potential_revenue_at_risk': abandoned_high_intent,  # Each is a potential deal
        }
