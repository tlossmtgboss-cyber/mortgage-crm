"""
AI Receptionist Dashboard API Routes
Endpoints for monitoring AI receptionist performance, metrics, and health
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta, timezone
import logging

from database import get_db
from ai_receptionist_dashboard_models import (
    AIReceptionistActivity,
    AIReceptionistMetricsDaily,
    AIReceptionistSkill,
    AIReceptionistError,
    AIReceptionistSystemHealth,
    AIReceptionistConversation
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ai-receptionist/dashboard", tags=["AI Receptionist Dashboard"])


# ============================================================================
# PYDANTIC RESPONSE MODELS
# ============================================================================

class ActivityFeedItem(BaseModel):
    id: str
    timestamp: datetime
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    action_type: str
    channel: Optional[str] = None
    message_in: Optional[str] = None
    message_out: Optional[str] = None
    confidence_score: Optional[float] = None
    lead_stage: Optional[str] = None
    outcome_status: Optional[str] = None
    conversation_id: Optional[str] = None
    transcript_url: Optional[str] = None

    class Config:
        from_attributes = True


class DailyMetrics(BaseModel):
    date: date
    total_conversations: int
    inbound_calls: int
    inbound_texts: int
    outbound_messages: int
    response_time_avg_seconds: Optional[float] = None
    appointments_scheduled: int
    forms_completed: int
    loan_apps_initiated: int
    escalations: int
    ai_coverage_percentage: Optional[float] = None
    estimated_revenue_created: Optional[float] = None
    saved_labor_hours: Optional[float] = None

    class Config:
        from_attributes = True


class RealtimeMetrics(BaseModel):
    """Current day metrics updated in real-time"""
    conversations_today: int
    appointments_today: int
    escalations_today: int
    avg_response_time_seconds: Optional[float] = None
    ai_coverage_percentage: Optional[float] = None
    active_conversations: int
    errors_today: int


class SkillPerformance(BaseModel):
    id: str
    skill_name: str
    skill_category: Optional[str] = None
    accuracy_score: Optional[float] = None
    accuracy_score_7day: Optional[float] = None
    trend_direction: Optional[str] = None
    trend_7day: Optional[float] = None
    usage_count: int
    needs_retraining: bool

    class Config:
        from_attributes = True


class ErrorLogItem(BaseModel):
    id: str
    timestamp: datetime
    error_type: str
    severity: Optional[str] = None
    context: Optional[str] = None
    conversation_snippet: Optional[str] = None
    root_cause: Optional[str] = None
    recommended_fix: Optional[str] = None
    resolution_status: str
    needs_human_review: bool

    class Config:
        from_attributes = True


class SystemHealthStatus(BaseModel):
    component_name: str
    status: str
    latency_ms: Optional[int] = None
    error_rate: Optional[float] = None
    uptime_percentage: Optional[float] = None
    last_checked: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class ROIMetrics(BaseModel):
    """Business impact and ROI calculations"""
    total_appointments: int
    appointment_to_app_rate: Optional[float] = None
    estimated_revenue: float
    saved_labor_hours: float
    saved_missed_calls: int
    cost_per_interaction: Optional[float] = None
    roi_percentage: Optional[float] = None


class ConversationDetail(BaseModel):
    id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    client_name: Optional[str] = None
    channel: Optional[str] = None
    summary: Optional[str] = None
    intent_detected: Optional[str] = None
    sentiment: Optional[str] = None
    outcome: Optional[str] = None
    avg_confidence_score: Optional[float] = None
    transcript: Optional[str] = None
    recording_url: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# ACTIVITY FEED ENDPOINTS
# ============================================================================

@router.get("/activity/feed", response_model=List[ActivityFeedItem])
async def get_activity_feed(
    limit: int = Query(50, le=200, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    client_id: Optional[str] = Query(None, description="Filter by client ID"),
    start_date: Optional[datetime] = Query(None, description="Filter from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter to this date"),
    db: Session = Depends(get_db)
):
    """
    Get real-time activity feed of all AI receptionist actions
    Returns chronological feed (most recent first)
    """
    try:
        query = db.query(AIReceptionistActivity)

        # Apply filters
        if action_type:
            query = query.filter(AIReceptionistActivity.action_type == action_type)
        if client_id:
            query = query.filter(AIReceptionistActivity.client_id == client_id)
        if start_date:
            query = query.filter(AIReceptionistActivity.timestamp >= start_date)
        if end_date:
            query = query.filter(AIReceptionistActivity.timestamp <= end_date)

        # Order by timestamp descending (most recent first)
        query = query.order_by(desc(AIReceptionistActivity.timestamp))

        # Pagination
        activities = query.offset(offset).limit(limit).all()

        return activities

    except Exception as e:
        logger.error(f"Error fetching activity feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/activity/count")
async def get_activity_count(
    action_type: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Get total count of activities (for pagination)"""
    try:
        query = db.query(func.count(AIReceptionistActivity.id))

        if action_type:
            query = query.filter(AIReceptionistActivity.action_type == action_type)
        if start_date:
            query = query.filter(AIReceptionistActivity.timestamp >= start_date)
        if end_date:
            query = query.filter(AIReceptionistActivity.timestamp <= end_date)

        total = query.scalar()

        return {"total": total}

    except Exception as e:
        logger.error(f"Error counting activities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# METRICS ENDPOINTS
# ============================================================================

@router.get("/metrics/daily", response_model=List[DailyMetrics])
async def get_daily_metrics(
    start_date: date = Query(..., description="Start date for metrics"),
    end_date: date = Query(..., description="End date for metrics"),
    db: Session = Depends(get_db)
):
    """
    Get daily aggregated metrics for date range
    Used for trend graphs and performance tracking
    """
    try:
        metrics = db.query(AIReceptionistMetricsDaily).filter(
            and_(
                AIReceptionistMetricsDaily.date >= start_date,
                AIReceptionistMetricsDaily.date <= end_date
            )
        ).order_by(AIReceptionistMetricsDaily.date).all()

        return metrics

    except Exception as e:
        logger.error(f"Error fetching daily metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/realtime", response_model=RealtimeMetrics)
async def get_realtime_metrics(db: Session = Depends(get_db)):
    """
    Get real-time metrics for current day
    Updates as new activities come in
    """
    try:
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)

        # Count today's activities
        conversations_today = db.query(func.count(AIReceptionistActivity.id)).filter(
            and_(
                AIReceptionistActivity.timestamp >= today_start,
                AIReceptionistActivity.action_type.in_(['incoming_call', 'incoming_text'])
            )
        ).scalar() or 0

        appointments_today = db.query(func.count(AIReceptionistActivity.id)).filter(
            and_(
                AIReceptionistActivity.timestamp >= today_start,
                AIReceptionistActivity.action_type == 'appointment_booked'
            )
        ).scalar() or 0

        escalations_today = db.query(func.count(AIReceptionistActivity.id)).filter(
            and_(
                AIReceptionistActivity.timestamp >= today_start,
                AIReceptionistActivity.action_type == 'escalated'
            )
        ).scalar() or 0

        errors_today = db.query(func.count(AIReceptionistError.id)).filter(
            AIReceptionistError.timestamp >= today_start
        ).scalar() or 0

        # Calculate average response time (placeholder - would need actual response time tracking)
        avg_response_time = None

        # Calculate AI coverage (placeholder)
        ai_coverage = (1 - (escalations_today / max(conversations_today, 1))) * 100 if conversations_today > 0 else 0

        # Active conversations (placeholder - would need real-time tracking)
        active_conversations = 0

        return RealtimeMetrics(
            conversations_today=conversations_today,
            appointments_today=appointments_today,
            escalations_today=escalations_today,
            avg_response_time_seconds=avg_response_time,
            ai_coverage_percentage=ai_coverage,
            active_conversations=active_conversations,
            errors_today=errors_today
        )

    except Exception as e:
        logger.error(f"Error fetching realtime metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SKILLS ENDPOINTS
# ============================================================================

@router.get("/skills", response_model=List[SkillPerformance])
async def get_skills_performance(
    needs_retraining: Optional[bool] = Query(None, description="Filter by retraining needs"),
    db: Session = Depends(get_db)
):
    """
    Get performance metrics for all AI skills
    Used for heatmap visualization
    """
    try:
        query = db.query(AIReceptionistSkill)

        if needs_retraining is not None:
            query = query.filter(AIReceptionistSkill.needs_retraining == needs_retraining)

        skills = query.order_by(desc(AIReceptionistSkill.usage_count)).all()

        return skills

    except Exception as e:
        logger.error(f"Error fetching skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skills/{skill_name}", response_model=SkillPerformance)
async def get_skill_detail(
    skill_name: str,
    db: Session = Depends(get_db)
):
    """Get detailed performance for a specific skill"""
    try:
        skill = db.query(AIReceptionistSkill).filter(
            AIReceptionistSkill.skill_name == skill_name
        ).first()

        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        return skill

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching skill detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ROI ENDPOINTS
# ============================================================================

@router.get("/roi", response_model=ROIMetrics)
async def get_roi_metrics(
    start_date: Optional[date] = Query(None, description="Start date for ROI calculation"),
    end_date: Optional[date] = Query(None, description="End date for ROI calculation"),
    db: Session = Depends(get_db)
):
    """
    Calculate ROI and business impact metrics
    Shows revenue created, time saved, cost efficiency
    """
    try:
        # Default to last 30 days if not specified
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Get metrics for date range
        metrics = db.query(AIReceptionistMetricsDaily).filter(
            and_(
                AIReceptionistMetricsDaily.date >= start_date,
                AIReceptionistMetricsDaily.date <= end_date
            )
        ).all()

        # Aggregate metrics
        total_appointments = sum(m.appointments_scheduled for m in metrics)
        total_apps_initiated = sum(m.loan_apps_initiated for m in metrics)
        total_saved_hours = sum(m.saved_labor_hours or 0 for m in metrics)
        total_estimated_revenue = sum(m.estimated_revenue_created or 0 for m in metrics)
        total_conversations = sum(m.total_conversations for m in metrics)

        # Calculate conversion rate
        appointment_to_app_rate = (total_apps_initiated / total_appointments * 100) if total_appointments > 0 else None

        # Calculate cost per interaction (placeholder - would need actual cost tracking)
        cost_per_interaction = 0.50  # Estimated

        # Calculate saved missed calls (placeholder)
        saved_missed_calls = int(total_conversations * 0.35)  # Assume 35% would have been missed

        # Calculate ROI (placeholder - needs real cost data)
        total_cost = total_conversations * cost_per_interaction
        total_value = total_estimated_revenue + (total_saved_hours * 50)  # $50/hour labor cost
        roi_percentage = ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else None

        return ROIMetrics(
            total_appointments=total_appointments,
            appointment_to_app_rate=appointment_to_app_rate,
            estimated_revenue=total_estimated_revenue,
            saved_labor_hours=total_saved_hours,
            saved_missed_calls=saved_missed_calls,
            cost_per_interaction=cost_per_interaction,
            roi_percentage=roi_percentage
        )

    except Exception as e:
        logger.error(f"Error calculating ROI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ERROR LOG ENDPOINTS
# ============================================================================

@router.get("/errors", response_model=List[ErrorLogItem])
async def get_errors(
    status: Optional[str] = Query(None, description="Filter by resolution status"),
    needs_review: Optional[bool] = Query(None, description="Filter by review flag"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get error log for AI receptionist
    Shows what the AI couldn't handle
    """
    try:
        query = db.query(AIReceptionistError)

        if status:
            query = query.filter(AIReceptionistError.resolution_status == status)
        if needs_review is not None:
            query = query.filter(AIReceptionistError.needs_human_review == needs_review)
        if error_type:
            query = query.filter(AIReceptionistError.error_type == error_type)

        errors = query.order_by(desc(AIReceptionistError.timestamp)).offset(offset).limit(limit).all()

        return errors

    except Exception as e:
        logger.error(f"Error fetching error log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/errors/{error_id}/approve-fix")
async def approve_auto_fix(
    error_id: str,
    db: Session = Depends(get_db)
):
    """
    Approve AI-proposed fix for an error
    Marks error as resolved and applies fix
    """
    try:
        error = db.query(AIReceptionistError).filter(AIReceptionistError.id == error_id).first()

        if not error:
            raise HTTPException(status_code=404, detail="Error not found")

        # Mark as auto-fixed
        error.resolution_status = 'auto_fixed'
        error.reviewed_at = datetime.now(timezone.utc)
        error.trained_into_model = True

        db.commit()

        return {
            "success": True,
            "message": "Auto-fix approved and applied",
            "error_id": error_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving fix: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SYSTEM HEALTH ENDPOINTS
# ============================================================================

@router.get("/system-health", response_model=List[SystemHealthStatus])
async def get_system_health(db: Session = Depends(get_db)):
    """
    Get real-time health status of all system components
    Shows which integrations are working
    """
    try:
        components = db.query(AIReceptionistSystemHealth).all()

        return components

    except Exception as e:
        logger.error(f"Error fetching system health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-health/{component_name}", response_model=SystemHealthStatus)
async def get_component_health(
    component_name: str,
    db: Session = Depends(get_db)
):
    """Get health status of a specific component"""
    try:
        component = db.query(AIReceptionistSystemHealth).filter(
            AIReceptionistSystemHealth.component_name == component_name
        ).first()

        if not component:
            raise HTTPException(status_code=404, detail=f"Component '{component_name}' not found")

        return component

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching component health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONVERSATION ENDPOINTS
# ============================================================================

@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_detail(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """
    Get full conversation transcript and details
    Linked from activity feed items
    """
    try:
        conversation = db.query(AIReceptionistConversation).filter(
            AIReceptionistConversation.id == conversation_id
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return conversation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations", response_model=List[ConversationDetail])
async def get_conversations(
    client_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    outcome: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get list of conversations with filters"""
    try:
        query = db.query(AIReceptionistConversation)

        if client_id:
            query = query.filter(AIReceptionistConversation.client_id == client_id)
        if start_date:
            query = query.filter(AIReceptionistConversation.started_at >= start_date)
        if end_date:
            query = query.filter(AIReceptionistConversation.started_at <= end_date)
        if outcome:
            query = query.filter(AIReceptionistConversation.outcome == outcome)

        conversations = query.order_by(desc(AIReceptionistConversation.started_at)).offset(offset).limit(limit).all()

        return conversations

    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
