"""
Chat Analytics - Performance Metrics & Insights

Provides analytics for:
- Conversion funnel tracking
- Phase progression analysis
- Intent signal distribution
- CTA effectiveness
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text, func

logger = logging.getLogger(__name__)


class ChatAnalytics:
    """Analytics for chat performance"""

    def __init__(self, db: Session):
        self.db = db

    def get_conversion_funnel(
        self,
        days: int = 30,
        microsite_id: Optional[int] = None,
        loan_officer_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get phase progression funnel.

        Returns metrics on how users progress through phases.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Build filter conditions
        filters = ["created_at >= :since"]
        params = {"since": since}

        if microsite_id:
            filters.append("microsite_id = :microsite_id")
            params["microsite_id"] = microsite_id

        if loan_officer_id:
            filters.append("loan_officer_id = :loan_officer_id")
            params["loan_officer_id"] = loan_officer_id

        where_clause = " AND ".join(filters)

        sql = """
            SELECT
                COUNT(*) as total_sessions,
                COUNT(CASE WHEN current_phase >= 2 THEN 1 END) as reached_phase_2,
                COUNT(CASE WHEN current_phase >= 3 THEN 1 END) as reached_phase_3,
                COUNT(CASE WHEN current_phase >= 4 THEN 1 END) as reached_phase_4,
                COUNT(CASE WHEN cta_offered IS NOT NULL AND cta_offered != 'none' THEN 1 END) as cta_offered,
                COUNT(CASE WHEN cta_accepted = true THEN 1 END) as cta_accepted,
                COUNT(CASE WHEN converted_to_lead = true THEN 1 END) as converted_to_lead,
                AVG(turn_count) as avg_turns,
                AVG(intent_score) as avg_intent_score
            FROM chat_sessions
            WHERE """ + where_clause + """
        """
        result = self.db.execute(text(sql), params).first()

        total = result.total_sessions or 0

        def safe_rate(numerator, denominator):
            if denominator and denominator > 0:
                return round((numerator or 0) / denominator * 100, 1)
            return 0.0

        funnel = {
            'period_days': days,
            'total_sessions': total,
            'funnel': {
                'phase_1': total,
                'phase_2': result.reached_phase_2 or 0,
                'phase_3': result.reached_phase_3 or 0,
                'phase_4': result.reached_phase_4 or 0,
            },
            'conversion_rates': {
                'phase_1_to_2': safe_rate(result.reached_phase_2, total),
                'phase_2_to_3': safe_rate(result.reached_phase_3, result.reached_phase_2),
                'phase_3_to_4': safe_rate(result.reached_phase_4, result.reached_phase_3),
                'overall_to_cta': safe_rate(result.cta_offered, total),
            },
            'cta_metrics': {
                'offered': result.cta_offered or 0,
                'accepted': result.cta_accepted or 0,
                'acceptance_rate': safe_rate(result.cta_accepted, result.cta_offered),
            },
            'lead_conversion': {
                'converted': result.converted_to_lead or 0,
                'conversion_rate': safe_rate(result.converted_to_lead, total),
            },
            'engagement': {
                'avg_turns': round(float(result.avg_turns or 0), 1),
                'avg_intent_score': round(float(result.avg_intent_score or 0), 1),
            }
        }

        return funnel

    def get_intent_distribution(
        self,
        days: int = 30,
        microsite_id: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Get distribution of intent signals.

        Returns count of each signal type detected.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        filters = ["created_at >= :since"]
        params = {"since": since}

        if microsite_id:
            filters.append("microsite_id = :microsite_id")
            params["microsite_id"] = microsite_id

        where_clause = " AND ".join(filters)

        # Get all sessions with intent signals
        intent_sql = """
            SELECT intent_signals
            FROM chat_sessions
            WHERE """ + where_clause + """
            AND intent_signals IS NOT NULL
            AND jsonb_array_length(intent_signals) > 0
        """
        result = self.db.execute(text(intent_sql), params).fetchall()

        signal_counts = {}
        for row in result:
            signals = row.intent_signals or []
            for signal in signals:
                signal_type = signal.get('signal') or signal.get('type')
                if signal_type:
                    signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1

        # Sort by count descending
        return dict(sorted(signal_counts.items(), key=lambda x: x[1], reverse=True))

    def get_avg_messages_to_cta(
        self,
        days: int = 30,
        microsite_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get average messages before CTA offered/accepted.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        filters = ["created_at >= :since", "cta_offered IS NOT NULL", "cta_offered != 'none'"]
        params = {"since": since}

        if microsite_id:
            filters.append("microsite_id = :microsite_id")
            params["microsite_id"] = microsite_id

        where_clause = " AND ".join(filters)

        cta_sql = """
            SELECT
                AVG(turn_count) as avg_turns_to_cta,
                MIN(turn_count) as min_turns,
                MAX(turn_count) as max_turns,
                COUNT(*) as sample_size
            FROM chat_sessions
            WHERE """ + where_clause + """
        """
        result = self.db.execute(text(cta_sql), params).first()

        return {
            'avg_turns_to_cta': round(float(result.avg_turns_to_cta or 0), 1),
            'min_turns': result.min_turns or 0,
            'max_turns': result.max_turns or 0,
            'sample_size': result.sample_size or 0
        }

    def get_cta_effectiveness_by_type(
        self,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get CTA effectiveness broken down by type.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = self.db.execute(text("""
            SELECT
                cta_offered,
                COUNT(*) as offered_count,
                SUM(CASE WHEN cta_accepted = true THEN 1 ELSE 0 END) as accepted_count,
                AVG(intent_score) as avg_intent_score
            FROM chat_sessions
            WHERE created_at >= :since
            AND cta_offered IS NOT NULL
            AND cta_offered != 'none'
            GROUP BY cta_offered
            ORDER BY offered_count DESC
        """), {"since": since}).fetchall()

        return [
            {
                'cta_type': row.cta_offered,
                'offered': row.offered_count,
                'accepted': row.accepted_count,
                'acceptance_rate': round((row.accepted_count / row.offered_count * 100), 1) if row.offered_count > 0 else 0,
                'avg_intent_score': round(float(row.avg_intent_score or 0), 1)
            }
            for row in result
        ]

    def get_phase_drop_off_analysis(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze where users drop off in the funnel.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = self.db.execute(text("""
            SELECT
                current_phase,
                COUNT(*) as count,
                AVG(turn_count) as avg_turns,
                AVG(intent_score) as avg_intent
            FROM chat_sessions
            WHERE created_at >= :since
            AND is_active = false
            GROUP BY current_phase
            ORDER BY current_phase
        """), {"since": since}).fetchall()

        return {
            'drop_off_by_phase': [
                {
                    'phase': row.current_phase,
                    'count': row.count,
                    'avg_turns': round(float(row.avg_turns or 0), 1),
                    'avg_intent': round(float(row.avg_intent or 0), 1)
                }
                for row in result
            ]
        }

    def get_session_duration_analysis(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze session durations.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = self.db.execute(text("""
            SELECT
                EXTRACT(EPOCH FROM (COALESCE(ended_at, last_message_at) - created_at)) / 60 as duration_minutes
            FROM chat_sessions
            WHERE created_at >= :since
            AND (ended_at IS NOT NULL OR last_message_at IS NOT NULL)
        """), {"since": since}).fetchall()

        durations = [row.duration_minutes for row in result if row.duration_minutes]

        if not durations:
            return {
                'avg_duration_minutes': 0,
                'median_duration_minutes': 0,
                'min_duration_minutes': 0,
                'max_duration_minutes': 0
            }

        durations_sorted = sorted(durations)
        median_idx = len(durations_sorted) // 2

        return {
            'avg_duration_minutes': round(sum(durations) / len(durations), 1),
            'median_duration_minutes': round(durations_sorted[median_idx], 1),
            'min_duration_minutes': round(min(durations), 1),
            'max_duration_minutes': round(max(durations), 1),
            'sample_size': len(durations)
        }

    def get_urgency_distribution(
        self,
        days: int = 30
    ) -> Dict[str, int]:
        """
        Get distribution of urgency levels.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = self.db.execute(text("""
            SELECT
                urgency,
                COUNT(*) as count
            FROM chat_sessions
            WHERE created_at >= :since
            GROUP BY urgency
        """), {"since": since}).fetchall()

        return {row.urgency: row.count for row in result}

    def get_top_performing_signals(
        self,
        days: int = 30,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get signals most correlated with CTA acceptance.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Get sessions with CTA accepted
        accepted_result = self.db.execute(text("""
            SELECT intent_signals
            FROM chat_sessions
            WHERE created_at >= :since
            AND cta_accepted = true
            AND intent_signals IS NOT NULL
        """), {"since": since}).fetchall()

        # Count signals in accepted sessions
        signal_counts = {}
        for row in accepted_result:
            signals = row.intent_signals or []
            for signal in signals:
                signal_type = signal.get('signal') or signal.get('type')
                if signal_type:
                    signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1

        # Sort and return top N
        sorted_signals = sorted(signal_counts.items(), key=lambda x: x[1], reverse=True)

        return [
            {'signal': sig, 'count': count}
            for sig, count in sorted_signals[:limit]
        ]

    def get_daily_session_trend(
        self,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get daily session counts.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = self.db.execute(text("""
            SELECT
                DATE(created_at) as date,
                COUNT(*) as sessions,
                SUM(CASE WHEN cta_accepted = true THEN 1 ELSE 0 END) as conversions
            FROM chat_sessions
            WHERE created_at >= :since
            GROUP BY DATE(created_at)
            ORDER BY date
        """), {"since": since}).fetchall()

        return [
            {
                'date': row.date.isoformat(),
                'sessions': row.sessions,
                'conversions': row.conversions
            }
            for row in result
        ]


def get_analytics_summary(
    db: Session,
    days: int = 30,
    microsite_id: Optional[int] = None,
    loan_officer_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get comprehensive analytics summary.

    Convenience function for API endpoints.
    """
    analytics = ChatAnalytics(db)

    return {
        'funnel': analytics.get_conversion_funnel(days, microsite_id, loan_officer_id),
        'intent_distribution': analytics.get_intent_distribution(days, microsite_id),
        'cta_metrics': analytics.get_avg_messages_to_cta(days, microsite_id),
        'cta_by_type': analytics.get_cta_effectiveness_by_type(days),
        'urgency_distribution': analytics.get_urgency_distribution(days),
        'session_duration': analytics.get_session_duration_analysis(days),
        'top_signals': analytics.get_top_performing_signals(days),
    }
