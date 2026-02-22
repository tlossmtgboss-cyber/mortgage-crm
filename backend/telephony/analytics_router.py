"""Analytics and reporting endpoints for dialer calls"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, date, timedelta
from typing import Optional
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================


# Import dependencies directly from main
from auth.dependencies import get_current_user
from database import get_db


# Keep set_dependencies for backwards compatibility (no-op now)
def set_dependencies(db_dependency, user_dependency):
    """Legacy function - dependencies now imported directly from main"""
    pass


# =============================================================================
# Daily Summary
# =============================================================================

@router.get("/analytics/daily-summary")
def get_daily_summary(
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get daily call summary for the current agent

    Returns:
    - Total calls made
    - Total talk time (minutes)
    - Connect rate (calls > 10 seconds / total)
    - Average call duration
    - Disposition breakdown
    """
    try:
        from database.models import CallLog

        # Use today if not specified
        if not target_date:
            target_date = date.today()

        # Convert to datetime range
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = datetime.combine(target_date, datetime.max.time())

        # Query calls for this date
        calls = db.query(CallLog).filter(
            and_(
                CallLog.agent_id == current_user.id,
                CallLog.start_time >= start_time,
                CallLog.start_time <= end_time
            )
        ).all()

        total_calls = len(calls)
        total_duration = sum(call.duration_seconds or 0 for call in calls)
        total_talk_time_minutes = total_duration // 60

        # Calculate connect rate (calls > 10 seconds / total calls)
        connected_calls = sum(1 for call in calls if (call.duration_seconds or 0) > 10)
        connect_rate = connected_calls / total_calls if total_calls > 0 else 0.0

        # Average call duration
        avg_duration = total_duration // total_calls if total_calls > 0 else 0

        # Disposition breakdown
        disposition_counts = {}
        for call in calls:
            if call.disposition:
                disposition_counts[call.disposition] = disposition_counts.get(call.disposition, 0) + 1

        return {
            "date": target_date.isoformat(),
            "total_calls": total_calls,
            "total_talk_time_minutes": total_talk_time_minutes,
            "connect_rate": round(connect_rate, 2),
            "average_call_duration_seconds": avg_duration,
            "connected_calls": connected_calls,
            "dispositions": disposition_counts
        }
    except Exception as e:
        logger.exception(f"Error in get_daily_summary: {e}")
        raise


# =============================================================================
# Disposition Breakdown
# =============================================================================

@router.get("/analytics/disposition-breakdown")
def get_disposition_breakdown(
    start_date: date = Query(..., description="Start date for range"),
    end_date: date = Query(..., description="End date for range"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get disposition breakdown for a date range

    Returns disposition counts with percentages
    """
    from database.models import CallLog

    start_time = datetime.combine(start_date, datetime.min.time())
    end_time = datetime.combine(end_date, datetime.max.time())

    # Query disposition counts
    results = db.query(
        CallLog.disposition,
        func.count(CallLog.id).label('count')
    ).filter(
        and_(
            CallLog.agent_id == current_user.id,
            CallLog.start_time >= start_time,
            CallLog.start_time <= end_time,
            CallLog.disposition.isnot(None)
        )
    ).group_by(CallLog.disposition).all()

    total = sum(r.count for r in results)

    breakdown = [
        {
            'disposition': r.disposition,
            'count': r.count,
            'percentage': round((r.count / total * 100), 1) if total > 0 else 0
        }
        for r in results
    ]

    # Sort by count descending
    breakdown.sort(key=lambda x: x['count'], reverse=True)

    return {
        'breakdown': breakdown,
        'total': total,
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        }
    }


# =============================================================================
# Connect Rate by Hour
# =============================================================================

@router.get("/analytics/connect-rate-by-hour")
def get_connect_rate_by_hour(
    start_date: date = Query(..., description="Start date for range"),
    end_date: date = Query(..., description="End date for range"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get connect rate by hour of day

    Useful for optimizing call timing - find the best hours to make calls
    """
    from database.models import CallLog

    start_time = datetime.combine(start_date, datetime.min.time())
    end_time = datetime.combine(end_date, datetime.max.time())

    calls = db.query(CallLog).filter(
        and_(
            CallLog.agent_id == current_user.id,
            CallLog.start_time >= start_time,
            CallLog.start_time <= end_time
        )
    ).all()

    # Group by hour
    hourly_stats = {}
    for hour in range(24):
        hourly_stats[hour] = {'total': 0, 'connected': 0}

    for call in calls:
        if call.start_time:
            hour = call.start_time.hour
            hourly_stats[hour]['total'] += 1
            if (call.duration_seconds or 0) > 10:
                hourly_stats[hour]['connected'] += 1

    # Calculate rates
    results = []
    for hour, stats in hourly_stats.items():
        rate = stats['connected'] / stats['total'] if stats['total'] > 0 else 0
        results.append({
            'hour': hour,
            'hour_label': f"{hour:02d}:00",
            'total_calls': stats['total'],
            'connected_calls': stats['connected'],
            'connect_rate': round(rate, 2)
        })

    # Find best hours (top 3 with at least 5 calls)
    valid_hours = [h for h in results if h['total_calls'] >= 5]
    best_hours = sorted(valid_hours, key=lambda x: x['connect_rate'], reverse=True)[:3]

    return {
        'hourly_stats': results,
        'best_hours': best_hours,
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        }
    }


# =============================================================================
# Agent Performance
# =============================================================================

@router.get("/analytics/performance")
def get_agent_performance(
    date_range: str = Query('last_7_days', description="Preset date range"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get comprehensive agent performance metrics

    Preset ranges: today, last_7_days, last_30_days, this_month
    """
    from database.models import CallLog

    # Calculate date range
    today = date.today()
    if date_range == 'today':
        start_date = today
        end_date = today
    elif date_range == 'last_7_days':
        start_date = today - timedelta(days=7)
        end_date = today
    elif date_range == 'last_30_days':
        start_date = today - timedelta(days=30)
        end_date = today
    elif date_range == 'this_month':
        start_date = today.replace(day=1)
        end_date = today
    else:
        # Default to last 7 days
        start_date = today - timedelta(days=7)
        end_date = today

    start_time = datetime.combine(start_date, datetime.min.time())
    end_time = datetime.combine(end_date, datetime.max.time())

    calls = db.query(CallLog).filter(
        and_(
            CallLog.agent_id == current_user.id,
            CallLog.start_time >= start_time,
            CallLog.start_time <= end_time
        )
    ).all()

    # Calculate metrics
    total_calls = len(calls)
    total_duration = sum(call.duration_seconds or 0 for call in calls)
    connected_calls = sum(1 for call in calls if (call.duration_seconds or 0) > 10)

    # Outcome breakdown
    outcome_counts = {}
    for call in calls:
        if call.outcome:
            outcome = call.outcome.value if hasattr(call.outcome, 'value') else str(call.outcome)
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    # Disposition breakdown
    disposition_counts = {}
    for call in calls:
        if call.disposition:
            disposition_counts[call.disposition] = disposition_counts.get(call.disposition, 0) + 1

    # Average calls per day
    days_in_range = (end_date - start_date).days + 1
    avg_calls_per_day = total_calls / days_in_range if days_in_range > 0 else 0

    # Daily trend
    daily_counts = {}
    for call in calls:
        if call.start_time:
            day = call.start_time.date().isoformat()
            daily_counts[day] = daily_counts.get(day, 0) + 1

    daily_trend = [
        {'date': day, 'calls': count}
        for day, count in sorted(daily_counts.items())
    ]

    return {
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
            'preset': date_range
        },
        'summary': {
            'total_calls': total_calls,
            'connected_calls': connected_calls,
            'connect_rate': round(connected_calls / total_calls, 2) if total_calls > 0 else 0,
            'total_talk_time_minutes': total_duration // 60,
            'average_call_duration_seconds': total_duration // total_calls if total_calls > 0 else 0,
            'average_calls_per_day': round(avg_calls_per_day, 1)
        },
        'outcome_breakdown': outcome_counts,
        'disposition_breakdown': disposition_counts,
        'daily_trend': daily_trend
    }


# =============================================================================
# Session Analytics
# =============================================================================

@router.get("/analytics/sessions")
def get_session_analytics(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get analytics for dialer sessions

    Returns session-level metrics including completion rates
    """
    from database.models import DialerSession, DialerSessionTask

    # Default to last 30 days
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    start_time = datetime.combine(start_date, datetime.min.time())
    end_time = datetime.combine(end_date, datetime.max.time())

    sessions = db.query(DialerSession).filter(
        and_(
            DialerSession.agent_id == current_user.id,
            DialerSession.started_at >= start_time,
            DialerSession.started_at <= end_time
        )
    ).all()

    session_stats = []
    total_tasks = 0
    total_completed = 0
    total_duration_minutes = 0

    for session in sessions:
        tasks = db.query(DialerSessionTask).filter(
            DialerSessionTask.session_id == session.id
        ).all()

        task_count = len(tasks)
        completed_count = sum(1 for t in tasks if t.status == 'completed')

        # Calculate session duration
        duration_minutes = 0
        if session.created_at and session.completed_at:
            duration_minutes = int((session.completed_at - session.created_at).total_seconds() / 60)

        session_stats.append({
            'session_id': session.id,
            'started_at': session.created_at.isoformat() if session.created_at else None,
            'ended_at': session.completed_at.isoformat() if session.completed_at else None,
            'status': session.status.value if hasattr(session.status, 'value') else str(session.status),
            'total_tasks': task_count,
            'completed_tasks': completed_count,
            'completion_rate': round(completed_count / task_count, 2) if task_count > 0 else 0,
            'duration_minutes': duration_minutes
        })

        total_tasks += task_count
        total_completed += completed_count
        total_duration_minutes += duration_minutes

    return {
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'summary': {
            'total_sessions': len(sessions),
            'total_tasks': total_tasks,
            'total_completed': total_completed,
            'overall_completion_rate': round(total_completed / total_tasks, 2) if total_tasks > 0 else 0,
            'total_duration_minutes': total_duration_minutes,
            'avg_session_duration_minutes': round(total_duration_minutes / len(sessions), 1) if sessions else 0
        },
        'sessions': session_stats
    }
