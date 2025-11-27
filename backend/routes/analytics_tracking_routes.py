"""
Analytics Tracking API Routes
Tracks user behavior and feature usage for beta metrics
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging

from database import get_db, Base

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics-tracking"])


# ============================================================================
# Models
# ============================================================================

class AnalyticsEvent(Base):
    """Analytics event model for tracking user behavior"""
    __tablename__ = "analytics_events"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    user_email = Column(String(255))
    event_name = Column(String(100), nullable=False, index=True)
    properties = Column(JSON)
    url = Column(String(500))
    user_agent = Column(String(500))
    screen_width = Column(Integer)
    screen_height = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ============================================================================
# Schemas
# ============================================================================

class EventTrackRequest(BaseModel):
    """Schema for tracking an event"""
    event: str
    properties: Optional[Dict[str, Any]] = None


class EventStats(BaseModel):
    """Schema for event statistics"""
    event_name: str
    count: int
    unique_users: int


# ============================================================================
# Routes
# ============================================================================

@router.post("/track")
async def track_event(
    event_data: EventTrackRequest,
    db: Session = Depends(get_db),
    # Note: Remove auth requirement for tracking to work without login
):
    """
    Track a user event.
    Used for analytics and beta program metrics.
    """
    try:
        properties = event_data.properties or {}

        # Extract standard properties
        url = properties.pop('url', None)
        user_agent = properties.pop('userAgent', None)
        screen_width = properties.pop('screenWidth', None)
        screen_height = properties.pop('screenHeight', None)
        properties.pop('timestamp', None)  # We use server timestamp

        # Create event record
        db_event = AnalyticsEvent(
            user_id=None,  # Will be populated if authenticated
            event_name=event_data.event,
            properties=properties,
            url=url,
            user_agent=user_agent,
            screen_width=screen_width,
            screen_height=screen_height,
        )

        db.add(db_event)
        db.commit()

        return {"success": True}

    except Exception as e:
        logger.error(f"Error tracking event: {str(e)}")
        # Don't fail the request - analytics should be non-blocking
        return {"success": False, "error": "Failed to track event"}


@router.get("/events/summary")
async def get_events_summary(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """
    Get summary of events for the last N days.
    Used for beta metrics dashboard.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Get event counts
    event_counts = db.query(
        AnalyticsEvent.event_name,
        func.count(AnalyticsEvent.id).label('count'),
        func.count(func.distinct(AnalyticsEvent.user_id)).label('unique_users')
    ).filter(
        AnalyticsEvent.created_at >= since
    ).group_by(
        AnalyticsEvent.event_name
    ).all()

    # Get daily active users
    daily_users = db.query(
        func.date(AnalyticsEvent.created_at).label('date'),
        func.count(func.distinct(AnalyticsEvent.user_id)).label('users')
    ).filter(
        AnalyticsEvent.created_at >= since
    ).group_by(
        func.date(AnalyticsEvent.created_at)
    ).all()

    # Get feature usage breakdown
    feature_usage = db.query(
        AnalyticsEvent.properties['feature'].astext.label('feature'),
        AnalyticsEvent.properties['action'].astext.label('action'),
        func.count(AnalyticsEvent.id).label('count')
    ).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.created_at >= since
    ).group_by(
        AnalyticsEvent.properties['feature'].astext,
        AnalyticsEvent.properties['action'].astext
    ).all()

    return {
        "period_days": days,
        "events": [
            {"event": e[0], "count": e[1], "unique_users": e[2]}
            for e in event_counts
        ],
        "daily_active_users": [
            {"date": str(d[0]), "users": d[1]}
            for d in daily_users
        ],
        "feature_usage": [
            {"feature": f[0], "action": f[1], "count": f[2]}
            for f in feature_usage if f[0]
        ],
        "generated_at": datetime.utcnow().isoformat()
    }


@router.get("/events/feature/{feature_name}")
async def get_feature_stats(
    feature_name: str,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get detailed stats for a specific feature.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Get actions for this feature
    actions = db.query(
        AnalyticsEvent.properties['action'].astext.label('action'),
        func.count(AnalyticsEvent.id).label('count'),
        func.count(func.distinct(AnalyticsEvent.user_id)).label('unique_users')
    ).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == feature_name,
        AnalyticsEvent.created_at >= since
    ).group_by(
        AnalyticsEvent.properties['action'].astext
    ).all()

    # Get daily trend
    daily_trend = db.query(
        func.date(AnalyticsEvent.created_at).label('date'),
        func.count(AnalyticsEvent.id).label('count')
    ).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == feature_name,
        AnalyticsEvent.created_at >= since
    ).group_by(
        func.date(AnalyticsEvent.created_at)
    ).all()

    return {
        "feature": feature_name,
        "period_days": days,
        "actions": [
            {"action": a[0], "count": a[1], "unique_users": a[2]}
            for a in actions if a[0]
        ],
        "daily_trend": [
            {"date": str(d[0]), "count": d[1]}
            for d in daily_trend
        ]
    }


@router.get("/beta/metrics")
async def get_beta_metrics(
    db: Session = Depends(get_db)
):
    """
    Get key metrics for beta program monitoring.
    """
    now = datetime.utcnow()
    last_7_days = now - timedelta(days=7)
    last_30_days = now - timedelta(days=30)

    # Total events
    total_events = db.query(func.count(AnalyticsEvent.id)).scalar()

    # Events last 7 days
    events_7d = db.query(func.count(AnalyticsEvent.id)).filter(
        AnalyticsEvent.created_at >= last_7_days
    ).scalar()

    # Unique users last 7 days
    users_7d = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
        AnalyticsEvent.created_at >= last_7_days
    ).scalar()

    # Feature adoption rates
    clip_users = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'video_clip',
        AnalyticsEvent.created_at >= last_30_days
    ).scalar()

    meeting_users = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'meeting',
        AnalyticsEvent.created_at >= last_30_days
    ).scalar()

    ai_users = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'ai_assistant',
        AnalyticsEvent.created_at >= last_30_days
    ).scalar()

    # Onboarding completion
    onboarding_started = db.query(func.count(AnalyticsEvent.id)).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'onboarding',
        AnalyticsEvent.properties['action'].astext == 'started'
    ).scalar()

    onboarding_completed = db.query(func.count(AnalyticsEvent.id)).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'onboarding',
        AnalyticsEvent.properties['action'].astext == 'completed'
    ).scalar()

    return {
        "total_events": total_events,
        "events_last_7_days": events_7d,
        "unique_users_last_7_days": users_7d,
        "feature_adoption_30d": {
            "video_clips": clip_users,
            "meetings": meeting_users,
            "ai_assistant": ai_users
        },
        "onboarding": {
            "started": onboarding_started,
            "completed": onboarding_completed,
            "completion_rate": (onboarding_completed / onboarding_started * 100) if onboarding_started > 0 else 0
        },
        "generated_at": now.isoformat()
    }
