"""
Chat Real-Time Monitoring - Operational Dashboard Queries

This service provides real-time operational monitoring for the chat system:
- Live activity metrics
- System health indicators
- Operational alerts
- Performance tracking
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, case

from chat_state_machine_models import (
    ChatSession, ChatMessage, CallRequest,
    ChatPhase, CTAType, CallStatus
)

logger = logging.getLogger(__name__)


class ChatRealtimeMonitoring:
    """Real-time operational monitoring for chat system"""

    def __init__(self, db: Session):
        self.db = db

    def get_live_metrics(self) -> Dict[str, Any]:
        """Get current system health metrics"""
        now = datetime.now(timezone.utc)
        last_hour = now - timedelta(hours=1)
        last_5min = now - timedelta(minutes=5)
        last_24h = now - timedelta(hours=24)

        # Activity metrics
        active_sessions_5min = self.db.query(func.count(ChatSession.id)).filter(
            ChatSession.last_message_at >= last_5min
        ).scalar() or 0

        new_sessions_hour = self.db.query(func.count(ChatSession.id)).filter(
            ChatSession.created_at >= last_hour
        ).scalar() or 0

        messages_hour = self.db.query(func.count(ChatMessage.id)).filter(
            ChatMessage.created_at >= last_hour
        ).scalar() or 0

        # Conversion metrics
        ctas_offered_hour = self.db.query(func.count(ChatSession.id)).filter(
            and_(
                ChatSession.updated_at >= last_hour,
                ChatSession.cta_offered.isnot(None),
                ChatSession.cta_offered != CTAType.NONE.value
            )
        ).scalar() or 0

        ctas_accepted_hour = self.db.query(func.count(ChatSession.id)).filter(
            and_(
                ChatSession.cta_accepted_at >= last_hour,
                ChatSession.cta_accepted == True
            )
        ).scalar() or 0

        # Call metrics
        calls_initiated_hour = self.db.query(func.count(CallRequest.id)).filter(
            CallRequest.created_at >= last_hour
        ).scalar() or 0

        calls_connected_hour = self.db.query(func.count(CallRequest.id)).filter(
            and_(
                CallRequest.connected_at >= last_hour,
                CallRequest.status == CallStatus.COMPLETED.value
            )
        ).scalar() or 0

        calls_failed_hour = self.db.query(func.count(CallRequest.id)).filter(
            and_(
                CallRequest.created_at >= last_hour,
                CallRequest.status == CallStatus.FAILED.value
            )
        ).scalar() or 0

        # Quality metrics
        avg_intent_score = self.db.query(
            func.avg(ChatSession.intent_score)
        ).filter(
            ChatSession.created_at >= last_hour
        ).scalar() or 0

        # Phase progression rates
        phase_4_rate = self._calculate_phase_rate(last_hour, 4)
        phase_3_rate = self._calculate_phase_rate(last_hour, 3)

        # Abandoned high-intent (for alerts)
        high_intent_abandoned = self.db.query(func.count(ChatSession.id)).filter(
            and_(
                ChatSession.intent_score >= 70,
                ChatSession.current_phase >= 3,
                ChatSession.last_message_at < now - timedelta(hours=1),
                ChatSession.last_message_at > last_24h,
                ChatSession.cta_accepted == False,
                ChatSession.is_active == True
            )
        ).scalar() or 0

        return {
            'timestamp': now.isoformat(),

            # Activity
            'activity': {
                'active_sessions_5min': active_sessions_5min,
                'new_sessions_hour': new_sessions_hour,
                'messages_hour': messages_hour,
                'avg_messages_per_session': round(messages_hour / max(new_sessions_hour, 1), 1),
            },

            # Conversions
            'conversions': {
                'ctas_offered_hour': ctas_offered_hour,
                'ctas_accepted_hour': ctas_accepted_hour,
                'cta_acceptance_rate': round(ctas_accepted_hour / max(ctas_offered_hour, 1) * 100, 1),
            },

            # Calls
            'calls': {
                'initiated_hour': calls_initiated_hour,
                'connected_hour': calls_connected_hour,
                'failed_hour': calls_failed_hour,
                'connection_rate': round(calls_connected_hour / max(calls_initiated_hour, 1) * 100, 1),
            },

            # Quality
            'quality': {
                'avg_intent_score': round(float(avg_intent_score), 1),
                'phase_3_rate': phase_3_rate,
                'phase_4_rate': phase_4_rate,
            },

            # Alerts
            'alert_indicators': {
                'high_intent_abandoned': high_intent_abandoned,
                'failed_calls_hour': calls_failed_hour,
                'low_cta_acceptance': ctas_accepted_hour < 1 and ctas_offered_hour >= 5,
            }
        }

    def _calculate_phase_rate(self, since: datetime, phase: int) -> float:
        """Calculate rate of sessions reaching a phase"""
        total = self.db.query(func.count(ChatSession.id)).filter(
            ChatSession.created_at >= since
        ).scalar() or 0

        if total == 0:
            return 0.0

        reached = self.db.query(func.count(ChatSession.id)).filter(
            and_(
                ChatSession.created_at >= since,
                ChatSession.current_phase >= phase
            )
        ).scalar() or 0

        return round(reached / total * 100, 2)

    def get_alerts(self) -> List[Dict[str, Any]]:
        """Get operational alerts that need attention"""
        alerts = []
        now = datetime.now(timezone.utc)
        last_hour = now - timedelta(hours=1)

        # Alert: High call failure rate
        last_hour_calls = self.db.query(func.count(CallRequest.id)).filter(
            CallRequest.created_at >= last_hour
        ).scalar() or 0

        if last_hour_calls >= 5:
            failed_calls = self.db.query(func.count(CallRequest.id)).filter(
                and_(
                    CallRequest.created_at >= last_hour,
                    CallRequest.status == CallStatus.FAILED.value
                )
            ).scalar() or 0

            failure_rate = failed_calls / last_hour_calls
            if failure_rate > 0.3:  # 30% failure rate
                alerts.append({
                    'id': 'call_failure_rate',
                    'severity': 'high',
                    'type': 'call_failure_rate',
                    'title': 'High Call Failure Rate',
                    'message': f'High call failure rate: {failure_rate*100:.0f}% ({failed_calls}/{last_hour_calls})',
                    'action': 'Check Telnyx status and LO phone availability',
                    'timestamp': now.isoformat(),
                    'metric_value': failure_rate,
                })

        # Alert: Abandoned high-intent sessions
        abandoned = self.db.query(func.count(ChatSession.id)).filter(
            and_(
                ChatSession.intent_score >= 70,
                ChatSession.current_phase >= 3,
                ChatSession.last_message_at < now - timedelta(hours=2),
                ChatSession.last_message_at > now - timedelta(hours=24),
                ChatSession.cta_accepted == False,
                ChatSession.is_active == True
            )
        ).scalar() or 0

        if abandoned > 0:
            alerts.append({
                'id': 'abandoned_high_intent',
                'severity': 'medium',
                'type': 'abandoned_high_intent',
                'title': 'Abandoned High-Intent Sessions',
                'message': f'{abandoned} high-intent sessions went silent in last 24h',
                'action': 'Review for LO follow-up - potential lost deals',
                'timestamp': now.isoformat(),
                'metric_value': abandoned,
            })

        # Alert: Low Phase 4 conversion rate
        metrics = self.get_live_metrics()
        if metrics['activity']['new_sessions_hour'] >= 10:
            if metrics['quality']['phase_4_rate'] < 20:
                alerts.append({
                    'id': 'low_phase_4_rate',
                    'severity': 'low',
                    'type': 'low_phase_4_rate',
                    'title': 'Low CTA Phase Rate',
                    'message': f'Only {metrics["quality"]["phase_4_rate"]:.0f}% of sessions reaching Phase 4',
                    'action': 'Review conversation patterns and intent detection',
                    'timestamp': now.isoformat(),
                    'metric_value': metrics['quality']['phase_4_rate'],
                })

        # Alert: Low CTA acceptance
        if metrics['conversions']['ctas_offered_hour'] >= 10:
            if metrics['conversions']['cta_acceptance_rate'] < 10:
                alerts.append({
                    'id': 'low_cta_acceptance',
                    'severity': 'medium',
                    'type': 'low_cta_acceptance',
                    'title': 'Low CTA Acceptance Rate',
                    'message': f'CTA acceptance at {metrics["conversions"]["cta_acceptance_rate"]:.0f}%',
                    'action': 'Review CTA timing and messaging',
                    'timestamp': now.isoformat(),
                    'metric_value': metrics['conversions']['cta_acceptance_rate'],
                })

        # Alert: No recent activity (system health check)
        if metrics['activity']['active_sessions_5min'] == 0 and metrics['activity']['new_sessions_hour'] == 0:
            # This might be normal during off-hours, check if it's business hours
            if self._is_business_hours():
                alerts.append({
                    'id': 'no_activity',
                    'severity': 'low',
                    'type': 'no_activity',
                    'title': 'No Chat Activity',
                    'message': 'No chat sessions in the last hour during business hours',
                    'action': 'Verify chat widget is working and traffic is flowing',
                    'timestamp': now.isoformat(),
                    'metric_value': 0,
                })

        return alerts

    def _is_business_hours(self) -> bool:
        """Check if current time is during typical business hours (9am-6pm EST)"""
        # Simple check - in production, use proper timezone handling
        now = datetime.now(timezone.utc)
        hour_utc = now.hour
        # EST is UTC-5, so 9am EST = 14:00 UTC, 6pm EST = 23:00 UTC
        return 14 <= hour_utc <= 23

    def get_phase_distribution(self, hours: int = 24) -> Dict[str, Any]:
        """Get distribution of sessions across phases"""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        distribution = self.db.query(
            ChatSession.current_phase,
            func.count(ChatSession.id).label('count')
        ).filter(
            ChatSession.created_at >= since
        ).group_by(ChatSession.current_phase).all()

        total = sum(d.count for d in distribution)

        return {
            'period_hours': hours,
            'total_sessions': total,
            'distribution': {
                f'phase_{d.current_phase}': {
                    'count': d.count,
                    'percentage': round(d.count / max(total, 1) * 100, 1)
                }
                for d in distribution
            }
        }

    def get_intent_signal_distribution(self, hours: int = 24) -> Dict[str, Any]:
        """Get distribution of detected intent signals"""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        sessions = self.db.query(ChatSession).filter(
            and_(
                ChatSession.created_at >= since,
                ChatSession.intent_signals.isnot(None)
            )
        ).all()

        signal_counts = {}
        for session in sessions:
            for signal in (session.intent_signals or []):
                signal_type = signal.get('signal')
                if signal_type:
                    signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1

        total = len(sessions)

        return {
            'period_hours': hours,
            'sessions_analyzed': total,
            'signals': {
                signal: {
                    'count': count,
                    'percentage': round(count / max(total, 1) * 100, 1)
                }
                for signal, count in sorted(signal_counts.items(), key=lambda x: -x[1])
            }
        }

    def get_hourly_trend(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get hourly trend of sessions and conversions"""
        now = datetime.now(timezone.utc)
        trends = []

        for i in range(hours, 0, -1):
            hour_start = now - timedelta(hours=i)
            hour_end = now - timedelta(hours=i-1)

            sessions = self.db.query(func.count(ChatSession.id)).filter(
                and_(
                    ChatSession.created_at >= hour_start,
                    ChatSession.created_at < hour_end
                )
            ).scalar() or 0

            ctas_accepted = self.db.query(func.count(ChatSession.id)).filter(
                and_(
                    ChatSession.cta_accepted_at >= hour_start,
                    ChatSession.cta_accepted_at < hour_end,
                    ChatSession.cta_accepted == True
                )
            ).scalar() or 0

            calls = self.db.query(func.count(CallRequest.id)).filter(
                and_(
                    CallRequest.created_at >= hour_start,
                    CallRequest.created_at < hour_end
                )
            ).scalar() or 0

            trends.append({
                'hour': hour_start.isoformat(),
                'sessions': sessions,
                'ctas_accepted': ctas_accepted,
                'calls': calls,
            })

        return trends

    def get_lo_performance(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get per-LO performance metrics"""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        # This query assumes loan_officer_id links to a users table
        results = self.db.query(
            ChatSession.loan_officer_id,
            func.count(ChatSession.id).label('total_sessions'),
            func.sum(case((ChatSession.cta_accepted == True, 1), else_=0)).label('conversions'),
            func.avg(ChatSession.intent_score).label('avg_intent'),
        ).filter(
            and_(
                ChatSession.created_at >= since,
                ChatSession.loan_officer_id.isnot(None)
            )
        ).group_by(ChatSession.loan_officer_id).all()

        return [
            {
                'loan_officer_id': r.loan_officer_id,
                'total_sessions': r.total_sessions,
                'conversions': int(r.conversions or 0),
                'conversion_rate': round(int(r.conversions or 0) / max(r.total_sessions, 1) * 100, 1),
                'avg_intent_score': round(float(r.avg_intent or 0), 1),
            }
            for r in results
        ]

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get complete dashboard summary for operations view"""
        return {
            'live_metrics': self.get_live_metrics(),
            'alerts': self.get_alerts(),
            'phase_distribution': self.get_phase_distribution(24),
            'hourly_trend': self.get_hourly_trend(12),  # Last 12 hours for dashboard
        }
