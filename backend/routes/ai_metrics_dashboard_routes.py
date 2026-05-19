"""
AI Metrics Dashboard Routes

Endpoints for AI performance metrics, business analytics, quality metrics,
and user feedback collection.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import logging

from db import get_async_db

router = APIRouter(prefix="/api/v1/ai/metrics", tags=["AI Metrics Dashboard"])
logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================

class UserFeedbackRequest(BaseModel):
    """Schema for submitting user feedback"""
    session_id: str
    feedback_type: str  # 'thumbs_up', 'thumbs_down', 'helpful', 'not_helpful', 'accurate', 'inaccurate'
    message_id: Optional[str] = None
    rating: Optional[int] = None  # 1-5
    comment: Optional[str] = None
    query_type: Optional[str] = None


# =============================================================================
# Dependencies - Import from main at runtime to avoid circular imports
# =============================================================================

def get_current_user_flexible_dep():
    """Get current user flexible - imports from main at runtime"""
    import main
    return main.get_current_user_flexible


# =============================================================================
# AI METRICS DASHBOARD ENDPOINTS
# =============================================================================

@router.get("/dashboard")
async def get_ai_metrics_dashboard(
    days: int = 7,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get comprehensive AI metrics dashboard.
    Returns agent performance, business metrics, and AI quality metrics.
    """
    try:
        from agents.metrics import AIMetricsService

        # Ensure metrics table exists
        await AIMetricsService.ensure_table_exists(db)

        dashboard = await AIMetricsService.get_dashboard_summary(db, days)

        return {
            "success": True,
            "dashboard": dashboard
        }

    except Exception as e:
        logger.error(f"Error getting AI metrics dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/performance")
async def get_ai_performance_metrics(
    days: int = 7,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get agent performance metrics: response times, error rates, user satisfaction.
    """
    try:
        from agents.metrics import AIMetricsService

        await AIMetricsService.ensure_table_exists(db)
        metrics = await AIMetricsService.get_agent_performance(db, days)

        return {
            "success": True,
            "metrics": metrics.model_dump()
        }

    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/business")
async def get_ai_business_metrics(
    days: int = 7,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get business metrics: query patterns, tool usage, actions executed.
    """
    try:
        from agents.metrics import AIMetricsService

        await AIMetricsService.ensure_table_exists(db)
        metrics = await AIMetricsService.get_business_metrics(db, days)

        return {
            "success": True,
            "metrics": metrics.model_dump()
        }

    except Exception as e:
        logger.error(f"Error getting business metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/quality")
async def get_ai_quality_metrics(
    days: int = 7,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get AI quality metrics: intent accuracy, tool selection, response quality.
    """
    try:
        from agents.metrics import AIMetricsService

        await AIMetricsService.ensure_table_exists(db)
        metrics = await AIMetricsService.get_ai_quality_metrics(db, days)

        return {
            "success": True,
            "metrics": metrics.model_dump()
        }

    except Exception as e:
        logger.error(f"Error getting quality metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/response-times")
async def get_ai_response_time_breakdown(
    days: int = 7,
    query_type: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get detailed response time breakdown by query type.
    """
    try:
        from agents.metrics import AIMetricsService

        await AIMetricsService.ensure_table_exists(db)
        breakdown = await AIMetricsService.get_response_time_breakdown(db, days, query_type)

        return {
            "success": True,
            "breakdown": breakdown
        }

    except Exception as e:
        logger.error(f"Error getting response time breakdown: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/feedback")
async def submit_ai_feedback(
    feedback: UserFeedbackRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Submit user feedback on AI response (thumbs up/down, rating, comment).
    """
    try:
        from agents.metrics import AIMetricsService
        from agents.metrics.models import UserFeedbackMetric, FeedbackType

        await AIMetricsService.ensure_table_exists(db)

        # Map feedback type string to enum
        feedback_type_map = {
            'thumbs_up': FeedbackType.THUMBS_UP,
            'thumbs_down': FeedbackType.THUMBS_DOWN,
            'helpful': FeedbackType.HELPFUL,
            'not_helpful': FeedbackType.NOT_HELPFUL,
            'accurate': FeedbackType.ACCURATE,
            'inaccurate': FeedbackType.INACCURATE
        }

        fb_type = feedback_type_map.get(feedback.feedback_type.lower())
        if not fb_type:
            raise HTTPException(status_code=400, detail=f"Invalid feedback type: {feedback.feedback_type}")

        success = await AIMetricsService.record_user_feedback(
            db=db,
            user_id=current_user.id,
            feedback=UserFeedbackMetric(
                session_id=feedback.session_id,
                message_id=feedback.message_id,
                feedback_type=fb_type,
                rating=feedback.rating,
                comment=feedback.comment,
                query_type=feedback.query_type
            )
        )

        return {
            "success": success,
            "message": "Feedback recorded" if success else "Failed to record feedback"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/followup-click")
async def record_followup_click(
    session_id: str,
    suggestion_text: str,
    suggestion_index: int = 0,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Record when user clicks a follow-up suggestion.
    """
    try:
        from agents.metrics import AIMetricsService

        await AIMetricsService.ensure_table_exists(db)
        success = await AIMetricsService.record_followup_click(
            db=db,
            user_id=current_user.id,
            session_id=session_id,
            suggestion_text=suggestion_text,
            suggestion_index=suggestion_index
        )

        return {
            "success": success
        }

    except Exception as e:
        logger.error(f"Error recording followup click: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
