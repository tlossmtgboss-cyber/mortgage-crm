"""
Analytics Tracking API Routes
Perennia AI - IBMA

Tracks user behavior and feature usage for beta metrics.
Provides insights into feature adoption, user engagement,
and onboarding completion rates.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, JSON, func, text
from sqlalchemy.orm import Session

from database import get_db, Base, engine
from sqlalchemy.exc import SQLAlchemyError
from routes.auth_deps import require_auth
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics Tracking"], dependencies=[Depends(require_auth)])


# ============================================================================
# Database Initialization
# ============================================================================

def ensure_analytics_tables_exist():
    """Create analytics tables if they don't exist."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    user_email VARCHAR(255),
                    event_name VARCHAR(100) NOT NULL,
                    properties JSONB DEFAULT '{}',
                    url VARCHAR(500),
                    user_agent VARCHAR(500),
                    screen_width INTEGER,
                    screen_height INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_analytics_event_name ON analytics_events(event_name);
                CREATE INDEX IF NOT EXISTS idx_analytics_user_id ON analytics_events(user_id);
                CREATE INDEX IF NOT EXISTS idx_analytics_created_at ON analytics_events(created_at DESC);
            """))
            conn.commit()
            logger.info("Analytics tables ensured to exist")
    except SQLAlchemyError as e:
        logger.warning(f"Analytics tables check warning: {e}")


# Auto-create tables on module load
try:
    ensure_analytics_tables_exist()
except SQLAlchemyError as e:
    logger.warning(f"Could not auto-create analytics tables: {e}")


# ============================================================================
# SQLAlchemy Model
# ============================================================================

class AnalyticsEvent(Base):
    """Analytics event model for tracking user behavior."""
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


# ============================================================================
# Pydantic Schemas - Requests
# ============================================================================

class EventTrackRequest(BaseModel):
    """Request schema for tracking an event."""
    event: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Event name (e.g., 'page_view', 'feature_usage')"
    )
    properties: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional event properties"
    )


# ============================================================================
# Pydantic Schemas - Responses
# ============================================================================

class EventCountResponse(BaseModel):
    """Response for event counts."""
    event: str = Field(..., description="Event name")
    count: int = Field(..., description="Total event count")
    unique_users: int = Field(..., description="Unique users who triggered this event")


class DailyUsersResponse(BaseModel):
    """Response for daily active users."""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    users: int = Field(..., description="Number of unique users")


class FeatureUsageResponse(BaseModel):
    """Response for feature usage breakdown."""
    feature: str = Field(..., description="Feature name")
    action: str = Field(..., description="Action performed")
    count: int = Field(..., description="Number of times performed")


class EventsSummaryResponse(BaseModel):
    """Response for events summary."""
    period_days: int = Field(..., description="Number of days in the period")
    events: List[EventCountResponse] = Field(default=[], description="Event counts")
    daily_active_users: List[DailyUsersResponse] = Field(default=[], description="Daily user counts")
    feature_usage: List[FeatureUsageResponse] = Field(default=[], description="Feature usage breakdown")
    generated_at: str = Field(..., description="Report generation timestamp")


class FeatureStatsResponse(BaseModel):
    """Response for feature-specific stats."""
    feature: str = Field(..., description="Feature name")
    period_days: int = Field(..., description="Number of days in the period")
    actions: List[dict] = Field(default=[], description="Actions performed on this feature")
    daily_trend: List[dict] = Field(default=[], description="Daily usage trend")


class BetaMetricsResponse(BaseModel):
    """Response for beta program metrics."""
    total_events: int = Field(..., description="Total events tracked")
    events_last_7_days: int = Field(..., description="Events in last 7 days")
    unique_users_last_7_days: int = Field(..., description="Unique users in last 7 days")
    feature_adoption_30d: Dict[str, int] = Field(..., description="Feature adoption counts")
    onboarding: Dict[str, Any] = Field(..., description="Onboarding metrics")
    generated_at: str = Field(..., description="Report generation timestamp")


# ============================================================================
# API Routes
# ============================================================================

@router.post("/track")
async def track_event(
    event_data: EventTrackRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Track a user event.

    Used for analytics and beta program metrics.
    This endpoint does not require authentication to support
    tracking before/during login flows.

    **Common Events:**
    - `page_view`: User viewed a page
    - `feature_usage`: User interacted with a feature
    - `button_click`: User clicked a button
    - `form_submit`: User submitted a form
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
        await db.commit()

        return {"success": True}

    except SQLAlchemyError as e:
        logger.error(f"Error tracking event: {str(e)}")
        # Don't fail the request - analytics should be non-blocking
        return {"success": False, "error": "Failed to track event"}


@router.get("/events/summary", response_model=EventsSummaryResponse)
async def get_events_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get summary of events for the last N days.

    Used for beta metrics dashboard and overall analytics.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

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

    return EventsSummaryResponse(
        period_days=days,
        events=[
            EventCountResponse(event=e[0], count=e[1], unique_users=e[2])
            for e in event_counts
        ],
        daily_active_users=[
            DailyUsersResponse(date=str(d[0]), users=d[1])
            for d in daily_users
        ],
        feature_usage=[
            FeatureUsageResponse(feature=f[0], action=f[1], count=f[2])
            for f in feature_usage if f[0]
        ],
        generated_at=datetime.now(timezone.utc).isoformat()
    )


@router.get("/events/feature/{feature_name}", response_model=FeatureStatsResponse)
async def get_feature_stats(
    feature_name: str,
    days: int = Query(30, ge=1, le=90, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get detailed stats for a specific feature.

    Useful for understanding feature adoption and usage patterns.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

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

    return FeatureStatsResponse(
        feature=feature_name,
        period_days=days,
        actions=[
            {"action": a[0], "count": a[1], "unique_users": a[2]}
            for a in actions if a[0]
        ],
        daily_trend=[
            {"date": str(d[0]), "count": d[1]}
            for d in daily_trend
        ]
    )


@router.get("/beta/metrics", response_model=BetaMetricsResponse)
async def get_beta_metrics(db: AsyncSession = Depends(get_async_db)):
    """
    Get key metrics for beta program monitoring.

    Returns comprehensive metrics including:
    - Total event counts
    - Feature adoption rates
    - Onboarding completion rates
    """
    now = datetime.now(timezone.utc)
    last_7_days = now - timedelta(days=7)
    last_30_days = now - timedelta(days=30)

    # Total events
    total_events = db.query(func.count(AnalyticsEvent.id)).scalar() or 0

    # Events last 7 days
    events_7d = db.query(func.count(AnalyticsEvent.id)).filter(
        AnalyticsEvent.created_at >= last_7_days
    ).scalar() or 0

    # Unique users last 7 days
    users_7d = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
        AnalyticsEvent.created_at >= last_7_days
    ).scalar() or 0

    # Feature adoption rates
    clip_users = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'video_clip',
        AnalyticsEvent.created_at >= last_30_days
    ).scalar() or 0

    meeting_users = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'meeting',
        AnalyticsEvent.created_at >= last_30_days
    ).scalar() or 0

    ai_users = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'ai_assistant',
        AnalyticsEvent.created_at >= last_30_days
    ).scalar() or 0

    # Onboarding completion
    onboarding_started = db.query(func.count(AnalyticsEvent.id)).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'onboarding',
        AnalyticsEvent.properties['action'].astext == 'started'
    ).scalar() or 0

    onboarding_completed = db.query(func.count(AnalyticsEvent.id)).filter(
        AnalyticsEvent.event_name == 'feature_usage',
        AnalyticsEvent.properties['feature'].astext == 'onboarding',
        AnalyticsEvent.properties['action'].astext == 'completed'
    ).scalar() or 0

    completion_rate = (onboarding_completed / onboarding_started * 100) if onboarding_started > 0 else 0

    return BetaMetricsResponse(
        total_events=total_events,
        events_last_7_days=events_7d,
        unique_users_last_7_days=users_7d,
        feature_adoption_30d={
            "video_clips": clip_users,
            "meetings": meeting_users,
            "ai_assistant": ai_users
        },
        onboarding={
            "started": onboarding_started,
            "completed": onboarding_completed,
            "completion_rate": round(completion_rate, 1)
        },
        generated_at=now.isoformat()
    )


@router.get("/health")
async def health_check():
    """Health check endpoint for analytics service."""
    return {
        "status": "healthy",
        "service": "analytics-tracking",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
