"""
Email Training Routes

Provides a training interface for reviewing AI email responses and providing
corrections to improve the qualification agent.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import logging
from routes.auth_deps import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)

# =============================================================================
# Database Model
# =============================================================================

from database import get_db, Base, engine
from sqlalchemy.exc import SQLAlchemyError

class EmailTrainingLog(Base):
    """Stores email conversations for training review"""
    __tablename__ = "email_training_logs"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)

    # Conversation info
    conversation_id = Column(String(255), index=True)
    from_email = Column(String(255), index=True)
    to_email = Column(String(255))
    subject = Column(String(500))

    # Message content
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)

    # Training feedback
    is_correct = Column(Boolean, default=None)  # None = not reviewed, True = correct, False = incorrect
    feedback_type = Column(String(50))  # 'wrong_answer', 'incomplete', 'tone_issue', 'missed_question', 'other'
    correct_response = Column(Text)  # What the AI should have said
    feedback_notes = Column(Text)  # Additional notes

    # Review metadata
    reviewed_by = Column(Integer)  # User ID who reviewed
    reviewed_at = Column(DateTime(timezone=True))

    # Context
    detected_topics = Column(JSON)  # Topics detected in user message
    conversation_stage = Column(String(50))
    qualification_data = Column(JSON)  # Current qualification state

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# Create table
try:
    EmailTrainingLog.__table__.create(engine, checkfirst=True)
    logger.info("EmailTrainingLog table created/verified")
except Exception as e:
    logger.warning(f"Could not create EmailTrainingLog table: {e}")


# =============================================================================
# Pydantic Models
# =============================================================================

class EmailTrainingCreate(BaseModel):
    """Request model for logging an email exchange for training"""
    conversation_id: str
    from_email: str
    to_email: Optional[str] = None
    subject: Optional[str] = None
    user_message: str
    ai_response: str
    detected_topics: Optional[List[str]] = None
    conversation_stage: Optional[str] = None
    qualification_data: Optional[dict] = None


class EmailTrainingReview(BaseModel):
    """Request model for submitting a training review"""
    is_correct: bool
    feedback_type: Optional[str] = None  # 'wrong_answer', 'incomplete', 'tone_issue', 'missed_question', 'other'
    correct_response: Optional[str] = None
    feedback_notes: Optional[str] = None


class EmailTrainingResponse(BaseModel):
    """Response model for email training log"""
    id: int
    conversation_id: str
    from_email: str
    to_email: Optional[str]
    subject: Optional[str]
    user_message: str
    ai_response: str
    is_correct: Optional[bool]
    feedback_type: Optional[str]
    correct_response: Optional[str]
    feedback_notes: Optional[str]
    reviewed_by: Optional[int]
    reviewed_at: Optional[datetime]
    detected_topics: Optional[List[str]]
    conversation_stage: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class EmailTrainingStats(BaseModel):
    """Statistics about email training"""
    total_emails: int
    reviewed_count: int
    pending_review: int
    correct_count: int
    incorrect_count: int
    accuracy_rate: float
    by_feedback_type: dict
    by_topic: dict
    recent_trend: List[dict]


# =============================================================================
# Routes
# =============================================================================

@router.post("/log", response_model=dict)
def log_email_for_training(
    data: EmailTrainingCreate,
    db: Session = Depends(get_db)
):
    """
    Log an email exchange for training review.
    Called automatically when AI responds to an email.
    """
    try:
        log = EmailTrainingLog(
            conversation_id=data.conversation_id,
            from_email=data.from_email,
            to_email=data.to_email,
            subject=data.subject,
            user_message=data.user_message,
            ai_response=data.ai_response,
            detected_topics=data.detected_topics,
            conversation_stage=data.conversation_stage,
            qualification_data=data.qualification_data
        )

        db.add(log)
        db.commit()
        db.refresh(log)

        logger.info(f"Email logged for training: id={log.id}, conv={data.conversation_id}")

        return {
            "success": True,
            "training_log_id": log.id
        }
    except SQLAlchemyError as e:
        logger.error(f"Error logging email for training: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/emails", response_model=List[EmailTrainingResponse])
def get_training_emails(
    status: Optional[str] = Query(None, description="Filter: 'pending', 'reviewed', 'correct', 'incorrect'"),
    from_email: Optional[str] = Query(None, description="Filter by sender email"),
    topic: Optional[str] = Query(None, description="Filter by detected topic"),
    source: Optional[str] = Query("all", description="Source: 'all', 'ai_conversations', 'inbox'"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get email exchanges for training review.
    Combines AI conversation logs with real inbox emails.
    """
    from sqlalchemy import text
    try:
        results = []

        # Get AI conversation logs (existing behavior)
        if source in ["all", "ai_conversations"]:
            query = db.query(EmailTrainingLog)

            # Apply filters
            if status == "pending":
                query = query.filter(EmailTrainingLog.is_correct == None)
            elif status == "reviewed":
                query = query.filter(EmailTrainingLog.is_correct != None)
            elif status == "correct":
                query = query.filter(EmailTrainingLog.is_correct == True)
            elif status == "incorrect":
                query = query.filter(EmailTrainingLog.is_correct == False)

            if from_email:
                query = query.filter(EmailTrainingLog.from_email.ilike(f"%{from_email}%"))

            # Order by newest first, prioritizing unreviewed
            query = query.order_by(
                EmailTrainingLog.is_correct.is_(None).desc(),
                desc(EmailTrainingLog.created_at)
            )

            logs = query.offset(offset).limit(limit).all()

            for log in logs:
                results.append(EmailTrainingResponse(
                    id=log.id,
                    conversation_id=log.conversation_id,
                    from_email=log.from_email,
                    to_email=log.to_email,
                    subject=log.subject,
                    user_message=log.user_message,
                    ai_response=log.ai_response,
                    is_correct=log.is_correct,
                    feedback_type=log.feedback_type,
                    correct_response=log.correct_response,
                    feedback_notes=log.feedback_notes,
                    reviewed_by=log.reviewed_by,
                    reviewed_at=log.reviewed_at,
                    detected_topics=log.detected_topics,
                    conversation_stage=log.conversation_stage,
                    created_at=log.created_at
                ))

        # Also get real inbox emails (processed by AI)
        if source in ["all", "inbox"]:
            try:
                # Query real emails from the emails table that have AI processing
                inbox_emails = db.execute(text("""
                    SELECT
                        e.id,
                        e.message_id as conversation_id,
                        e.sender_email as from_email,
                        e.sender_name,
                        e.recipient_emails,
                        e.subject,
                        e.body_text as user_message,
                        e.received_date as created_at,
                        e.ai_extracted_data,
                        e.processed,
                        e.folder_name
                    FROM emails e
                    WHERE e.processed = true
                    AND e.folder_name = 'Inbox'
                    ORDER BY e.received_date DESC
                    LIMIT :limit OFFSET :offset
                """), {"limit": limit, "offset": offset}).fetchall()

                for email in inbox_emails:
                    ai_data = email.ai_extracted_data or {}
                    ai_response = ai_data.get('ai_response', ai_data.get('summary', 'No AI response recorded'))

                    # Check if this email already exists in training logs (by message_id)
                    existing = any(r.conversation_id == email.conversation_id for r in results)
                    if not existing:
                        results.append(EmailTrainingResponse(
                            id=email.id + 100000,  # Offset to avoid ID conflicts
                            conversation_id=email.conversation_id or f"inbox_{email.id}",
                            from_email=email.from_email,
                            to_email=str(email.recipient_emails[0]) if email.recipient_emails else None,
                            subject=email.subject,
                            user_message=email.user_message or "(No body)",
                            ai_response=ai_response if isinstance(ai_response, str) else str(ai_response),
                            is_correct=None,  # Not yet reviewed
                            feedback_type=None,
                            correct_response=None,
                            feedback_notes=None,
                            reviewed_by=None,
                            reviewed_at=None,
                            detected_topics=ai_data.get('topics', []),
                            conversation_stage=ai_data.get('stage', 'inbox'),
                            created_at=email.created_at
                        ))
            except Exception as inbox_err:
                logger.warning(f"Could not fetch inbox emails: {inbox_err}")

        # Sort combined results by date
        results.sort(key=lambda x: x.created_at if x.created_at else datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        return results[:limit]

    except Exception as e:
        logger.error(f"Error fetching training emails: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/emails/{log_id}", response_model=EmailTrainingResponse)
def get_training_email(
    log_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific email training log."""
    log = db.query(EmailTrainingLog).filter(EmailTrainingLog.id == log_id).first()

    if not log:
        raise HTTPException(status_code=404, detail="Training log not found")

    return EmailTrainingResponse(
        id=log.id,
        conversation_id=log.conversation_id,
        from_email=log.from_email,
        to_email=log.to_email,
        subject=log.subject,
        user_message=log.user_message,
        ai_response=log.ai_response,
        is_correct=log.is_correct,
        feedback_type=log.feedback_type,
        correct_response=log.correct_response,
        feedback_notes=log.feedback_notes,
        reviewed_by=log.reviewed_by,
        reviewed_at=log.reviewed_at,
        detected_topics=log.detected_topics,
        conversation_stage=log.conversation_stage,
        created_at=log.created_at
    )


@router.post("/emails/{log_id}/review", response_model=dict)
def review_training_email(
    log_id: int,
    review: EmailTrainingReview,
    db: Session = Depends(get_db)
):
    """
    Submit a review for an email AI response.
    Mark as correct or incorrect and optionally provide the correct response.
    """
    try:
        log = db.query(EmailTrainingLog).filter(EmailTrainingLog.id == log_id).first()

        if not log:
            raise HTTPException(status_code=404, detail="Training log not found")

        log.is_correct = review.is_correct
        log.feedback_type = review.feedback_type
        log.correct_response = review.correct_response
        log.feedback_notes = review.feedback_notes
        log.reviewed_at = datetime.now(timezone.utc)
        # log.reviewed_by = current_user.id  # Add when auth is integrated

        db.commit()

        logger.info(f"Training review submitted: id={log_id}, correct={review.is_correct}")

        return {
            "success": True,
            "message": "Review submitted successfully",
            "is_correct": review.is_correct
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error submitting review: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats", response_model=EmailTrainingStats)
def get_training_stats(
    days: int = Query(30, description="Number of days to include"),
    db: Session = Depends(get_db)
):
    """Get training statistics."""
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Base query for the time period
        base_query = db.query(EmailTrainingLog).filter(
            EmailTrainingLog.created_at >= start_date
        )

        total = base_query.count()
        reviewed = base_query.filter(EmailTrainingLog.is_correct != None).count()
        pending = base_query.filter(EmailTrainingLog.is_correct == None).count()
        correct = base_query.filter(EmailTrainingLog.is_correct == True).count()
        incorrect = base_query.filter(EmailTrainingLog.is_correct == False).count()

        accuracy = (correct / reviewed * 100) if reviewed > 0 else 0.0

        # By feedback type
        feedback_counts = {}
        feedback_results = db.query(
            EmailTrainingLog.feedback_type,
            func.count(EmailTrainingLog.id)
        ).filter(
            EmailTrainingLog.created_at >= start_date,
            EmailTrainingLog.feedback_type != None
        ).group_by(EmailTrainingLog.feedback_type).all()

        for ftype, count in feedback_results:
            feedback_counts[ftype or 'unspecified'] = count

        # By topic (approximate from detected_topics)
        topic_counts = {}
        logs_with_topics = db.query(EmailTrainingLog).filter(
            EmailTrainingLog.created_at >= start_date,
            EmailTrainingLog.detected_topics != None
        ).all()

        for log in logs_with_topics:
            if log.detected_topics:
                for topic in log.detected_topics:
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1

        # Recent trend (daily counts)
        from sqlalchemy import text
        trend_results = db.execute(text("""
            SELECT DATE(created_at) as date,
                   COUNT(*) as total,
                   SUM(CASE WHEN is_correct = true THEN 1 ELSE 0 END) as correct,
                   SUM(CASE WHEN is_correct = false THEN 1 ELSE 0 END) as incorrect
            FROM email_training_logs
            WHERE created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 14
        """), {"start_date": start_date}).fetchall()

        recent_trend = [
            {
                "date": str(row.date),
                "total": row.total,
                "correct": row.correct or 0,
                "incorrect": row.incorrect or 0
            }
            for row in trend_results
        ]

        return EmailTrainingStats(
            total_emails=total,
            reviewed_count=reviewed,
            pending_review=pending,
            correct_count=correct,
            incorrect_count=incorrect,
            accuracy_rate=round(accuracy, 1),
            by_feedback_type=feedback_counts,
            by_topic=topic_counts,
            recent_trend=recent_trend
        )

    except Exception as e:
        logger.error(f"Error fetching training stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/export", response_model=List[dict])
def export_training_data(
    include_correct: bool = Query(True, description="Include correct responses"),
    include_incorrect: bool = Query(True, description="Include incorrect responses with corrections"),
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db)
):
    """
    Export training data for fine-tuning.
    Returns a list of message/response pairs suitable for training.
    """
    try:
        query = db.query(EmailTrainingLog).filter(EmailTrainingLog.is_correct != None)

        if not include_correct:
            query = query.filter(EmailTrainingLog.is_correct == False)
        if not include_incorrect:
            query = query.filter(EmailTrainingLog.is_correct == True)

        # Only include incorrect ones that have corrections
        logs = query.order_by(desc(EmailTrainingLog.created_at)).limit(limit).all()

        training_data = []
        for log in logs:
            if log.is_correct:
                # Use the original AI response as the target
                training_data.append({
                    "user_message": log.user_message,
                    "ideal_response": log.ai_response,
                    "source": "verified_correct",
                    "topics": log.detected_topics
                })
            elif log.correct_response:
                # Use the human-provided correction as the target
                training_data.append({
                    "user_message": log.user_message,
                    "ideal_response": log.correct_response,
                    "original_response": log.ai_response,
                    "feedback_type": log.feedback_type,
                    "source": "human_corrected",
                    "topics": log.detected_topics
                })

        return training_data

    except Exception as e:
        logger.error(f"Error exporting training data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/emails/{log_id}")
def delete_training_log(
    log_id: int,
    db: Session = Depends(get_db)
):
    """Delete a training log entry."""
    try:
        log = db.query(EmailTrainingLog).filter(EmailTrainingLog.id == log_id).first()

        if not log:
            raise HTTPException(status_code=404, detail="Training log not found")

        db.delete(log)
        db.commit()

        return {"success": True, "message": "Training log deleted"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error deleting training log: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
