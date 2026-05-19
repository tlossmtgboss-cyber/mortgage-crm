"""
AI Feedback Log Routes

Provides endpoints to track and manage user feedback on AI responses
that were incorrect or unsatisfactory.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import logging
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================

class AIFeedbackCreate(BaseModel):
    """Request model for creating AI feedback"""
    user_question: str
    ai_response: str
    feedback_type: str  # 'wrong_answer', 'incomplete', 'outdated', 'irrelevant', 'other'
    user_feedback: Optional[str] = None
    category: Optional[str] = None
    session_id: Optional[str] = None
    tools_used: Optional[List[str]] = None
    request_id: Optional[str] = None


class AIFeedbackUpdate(BaseModel):
    """Request model for updating AI feedback status"""
    status: Optional[str] = None
    resolution_notes: Optional[str] = None


class AIFeedbackResponse(BaseModel):
    """Response model for AI feedback"""
    id: int
    user_id: int
    user_email: Optional[str] = None
    user_question: str
    ai_response: str
    feedback_type: str
    user_feedback: Optional[str] = None
    category: Optional[str] = None
    status: str
    resolution_notes: Optional[str] = None
    resolved_by: Optional[int] = None
    resolver_email: Optional[str] = None
    resolved_at: Optional[datetime] = None
    session_id: Optional[str] = None
    tools_used: Optional[List[str]] = None
    request_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AIFeedbackStats(BaseModel):
    """Statistics about AI feedback"""
    total_feedback: int
    pending_count: int
    reviewed_count: int
    fixed_count: int
    dismissed_count: int
    by_category: dict
    by_feedback_type: dict
    recent_trend: List[dict]


# =============================================================================
# Dependencies - Import from shared modules
# =============================================================================

from database import get_db

# For user authentication, we import from main at runtime to avoid circular imports
def get_current_user_dep():
    """Get current user - imports from main at runtime"""
    import main
    return main.get_current_user


def set_dependencies(db_dependency, user_dependency):
    """Legacy function for backwards compatibility - no longer needed"""
    pass  # Dependencies are now imported directly


# =============================================================================
# Routes
# =============================================================================

@router.post("/", response_model=dict)
def create_feedback(
    feedback: AIFeedbackCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Submit feedback about an unsatisfactory AI response.

    This allows users to report when the AI:
    - Gave a wrong answer
    - Provided incomplete information
    - Used outdated data
    - Gave an irrelevant response
    """
    try:
        # Import here to avoid circular imports
        import main
        AIFeedbackLog = main.AIFeedbackLog

        # Auto-detect category from question if not provided
        category = feedback.category
        if not category:
            question_lower = feedback.user_question.lower()
            if any(word in question_lower for word in ['sla', 'turnaround', 'turn time']):
                category = 'sla'
            elif any(word in question_lower for word in ['pipeline', 'bottleneck', 'stage']):
                category = 'pipeline'
            elif any(word in question_lower for word in ['task', 'todo', 'priority']):
                category = 'tasks'
            elif any(word in question_lower for word in ['loan', 'mortgage', 'rate']):
                category = 'loans'
            elif any(word in question_lower for word in ['lead', 'prospect', 'client']):
                category = 'leads'
            else:
                category = 'general'

        new_feedback = AIFeedbackLog(
            user_id=current_user.id,
            user_question=feedback.user_question,
            ai_response=feedback.ai_response,
            feedback_type=feedback.feedback_type,
            user_feedback=feedback.user_feedback,
            category=category,
            session_id=feedback.session_id,
            tools_used=feedback.tools_used,
            request_id=feedback.request_id,
            status='pending'
        )

        db.add(new_feedback)
        db.commit()
        db.refresh(new_feedback)

        logger.info(f"AI feedback logged: id={new_feedback.id}, type={feedback.feedback_type}, category={category}")

        return {
            "success": True,
            "message": "Thank you for your feedback! We'll use this to improve the AI.",
            "feedback_id": new_feedback.id
        }

    except SQLAlchemyError as e:
        logger.error(f"Error creating AI feedback: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/", response_model=List[AIFeedbackResponse])
def get_feedback_logs(
    status: Optional[str] = Query(None, description="Filter by status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    feedback_type: Optional[str] = Query(None, description="Filter by feedback type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Get AI feedback logs with optional filters.

    Admin users can see all feedback, regular users see only their own.
    """
    try:
        import main
        AIFeedbackLog = main.AIFeedbackLog
        User = main.User

        query = db.query(AIFeedbackLog)

        # Apply filters
        if status:
            query = query.filter(AIFeedbackLog.status == status)
        if category:
            query = query.filter(AIFeedbackLog.category == category)
        if feedback_type:
            query = query.filter(AIFeedbackLog.feedback_type == feedback_type)

        # Order by created_at descending (newest first)
        query = query.order_by(desc(AIFeedbackLog.created_at))

        # Apply pagination
        total = query.count()
        logs = query.offset(offset).limit(limit).all()

        # Build response with user emails
        results = []
        for log in logs:
            user = db.query(User).filter(User.id == log.user_id).first()
            resolver = db.query(User).filter(User.id == log.resolved_by).first() if log.resolved_by else None

            results.append(AIFeedbackResponse(
                id=log.id,
                user_id=log.user_id,
                user_email=user.email if user else None,
                user_question=log.user_question,
                ai_response=log.ai_response,
                feedback_type=log.feedback_type,
                user_feedback=log.user_feedback,
                category=log.category,
                status=log.status,
                resolution_notes=log.resolution_notes,
                resolved_by=log.resolved_by,
                resolver_email=resolver.email if resolver else None,
                resolved_at=log.resolved_at,
                session_id=log.session_id,
                tools_used=log.tools_used,
                request_id=log.request_id,
                created_at=log.created_at,
                updated_at=log.updated_at
            ))

        return results

    except Exception as e:
        logger.error(f"Error fetching AI feedback logs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats", response_model=AIFeedbackStats)
def get_feedback_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Get statistics about AI feedback for the dashboard.
    """
    try:
        import main
        AIFeedbackLog = main.AIFeedbackLog
        from sqlalchemy import text

        # Total feedback count
        total = db.query(AIFeedbackLog).count()

        # Counts by status
        pending = db.query(AIFeedbackLog).filter(AIFeedbackLog.status == 'pending').count()
        reviewed = db.query(AIFeedbackLog).filter(AIFeedbackLog.status == 'reviewed').count()
        fixed = db.query(AIFeedbackLog).filter(AIFeedbackLog.status == 'fixed').count()
        dismissed = db.query(AIFeedbackLog).filter(AIFeedbackLog.status == 'dismissed').count()

        # Counts by category
        category_counts = {}
        category_results = db.query(
            AIFeedbackLog.category,
            func.count(AIFeedbackLog.id)
        ).group_by(AIFeedbackLog.category).all()
        for cat, count in category_results:
            category_counts[cat or 'uncategorized'] = count

        # Counts by feedback type
        type_counts = {}
        type_results = db.query(
            AIFeedbackLog.feedback_type,
            func.count(AIFeedbackLog.id)
        ).group_by(AIFeedbackLog.feedback_type).all()
        for ftype, count in type_results:
            type_counts[ftype] = count

        # Recent trend (last 7 days)
        from datetime import timedelta
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_results = db.execute(text("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM ai_feedback_logs
            WHERE created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date
        """), {"start_date": seven_days_ago}).fetchall()
        recent_trend = [{"date": str(row.date), "count": row.count} for row in recent_results]

        return AIFeedbackStats(
            total_feedback=total,
            pending_count=pending,
            reviewed_count=reviewed,
            fixed_count=fixed,
            dismissed_count=dismissed,
            by_category=category_counts,
            by_feedback_type=type_counts,
            recent_trend=recent_trend
        )

    except Exception as e:
        logger.error(f"Error fetching AI feedback stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{feedback_id}", response_model=dict)
def update_feedback_status(
    feedback_id: int,
    update: AIFeedbackUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Update the status of a feedback log (for admins to mark as reviewed/fixed).
    """
    try:
        import main
        AIFeedbackLog = main.AIFeedbackLog

        feedback = db.query(AIFeedbackLog).filter(AIFeedbackLog.id == feedback_id).first()

        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")

        if update.status:
            feedback.status = update.status
            if update.status in ['reviewed', 'fixed', 'dismissed']:
                feedback.resolved_by = current_user.id
                feedback.resolved_at = datetime.now(timezone.utc)

        if update.resolution_notes is not None:
            feedback.resolution_notes = update.resolution_notes

        db.commit()

        logger.info(f"AI feedback {feedback_id} updated: status={update.status}")

        return {
            "success": True,
            "message": f"Feedback status updated to '{update.status}'"
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error updating AI feedback: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{feedback_id}")
def delete_feedback(
    feedback_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Delete a feedback log entry.
    """
    try:
        import main
        AIFeedbackLog = main.AIFeedbackLog

        feedback = db.query(AIFeedbackLog).filter(AIFeedbackLog.id == feedback_id).first()

        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")

        db.delete(feedback)
        db.commit()

        logger.info(f"AI feedback {feedback_id} deleted")

        return {"success": True, "message": "Feedback deleted"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error deleting AI feedback: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Ensure tables exist
# =============================================================================

def ensure_tables_exist(engine):
    """Create the ai_feedback_logs table if it doesn't exist"""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_feedback_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    user_question TEXT NOT NULL,
                    ai_response TEXT NOT NULL,
                    feedback_type VARCHAR(50) NOT NULL,
                    user_feedback TEXT,
                    category VARCHAR(50),
                    status VARCHAR(20) DEFAULT 'pending',
                    resolution_notes TEXT,
                    resolved_by INTEGER REFERENCES users(id),
                    resolved_at TIMESTAMP,
                    session_id VARCHAR(255),
                    tools_used JSONB,
                    request_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS ix_ai_feedback_user_id ON ai_feedback_logs(user_id);
                CREATE INDEX IF NOT EXISTS ix_ai_feedback_created_at ON ai_feedback_logs(created_at);
                CREATE INDEX IF NOT EXISTS ix_ai_feedback_status ON ai_feedback_logs(status);
                CREATE INDEX IF NOT EXISTS ix_ai_feedback_category ON ai_feedback_logs(category);
            """))
            conn.commit()
            logger.info("AI feedback logs table ensured to exist")
    except SQLAlchemyError as e:
        logger.warning(f"Note: AI feedback table check: {e}")
