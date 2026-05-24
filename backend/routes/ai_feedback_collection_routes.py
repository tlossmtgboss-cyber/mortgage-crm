"""
AI Feedback Collection Routes

Lightweight inline feedback collection for thumbs-up/thumbs-down on individual
AI responses. Separate from the existing ai_feedback_routes.py which handles
detailed "report wrong answer" feedback.

This module:
- POST /api/v1/ai/feedback      - Submit rating on an AI response (positive/negative)
- GET  /api/v1/ai/feedback/stats - Aggregated feedback stats for current user's org
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai")


# =============================================================================
# Rate limiter — per-user sliding window (30 req/min for feedback)
# =============================================================================

_feedback_rate_store: Dict[str, list] = defaultdict(list)
FEEDBACK_RATE_LIMIT = 30
FEEDBACK_RATE_WINDOW = 60  # seconds


def _check_feedback_rate_limit(user_id: str) -> None:
    """Check per-user feedback rate limit. Raises 429 if exceeded."""
    now = time.time()
    window_start = now - FEEDBACK_RATE_WINDOW

    timestamps = _feedback_rate_store[user_id]
    _feedback_rate_store[user_id] = [t for t in timestamps if t > window_start]

    if len(_feedback_rate_store[user_id]) >= FEEDBACK_RATE_LIMIT:
        retry_after = int(FEEDBACK_RATE_WINDOW - (now - _feedback_rate_store[user_id][0]))
        raise HTTPException(
            status_code=429,
            detail=f"Feedback rate limit exceeded. Max {FEEDBACK_RATE_LIMIT} per {FEEDBACK_RATE_WINDOW}s.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )

    _feedback_rate_store[user_id].append(now)


# =============================================================================
# Constants
# =============================================================================

ALLOWED_RATINGS = {"positive", "negative"}
ALLOWED_FEEDBACK_TYPES = {
    "wrong_answer",
    "incomplete",
    "outdated",
    "irrelevant",
    "hallucination",
    "helpful",
    "accurate",
    "other",
}


# =============================================================================
# Pydantic Models
# =============================================================================

class FeedbackSubmit(BaseModel):
    """Request body for submitting feedback on an AI response."""
    session_id: str = Field(..., min_length=1, max_length=255, description="Chat session ID")
    message_id: Optional[str] = Field(None, max_length=255, description="Specific message ID")
    rating: str = Field(..., description="positive or negative")
    feedback_type: Optional[str] = Field(None, description="Category of feedback")
    feedback_text: Optional[str] = Field(None, max_length=2000, description="Optional free-text feedback")
    user_question: Optional[str] = Field(None, max_length=5000, description="The user's original question")
    ai_response: Optional[str] = Field(None, max_length=10000, description="The AI's response text")

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALLOWED_RATINGS:
            raise ValueError(f"rating must be one of: {', '.join(sorted(ALLOWED_RATINGS))}")
        return v

    @field_validator("feedback_type")
    @classmethod
    def validate_feedback_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in ALLOWED_FEEDBACK_TYPES:
            raise ValueError(f"feedback_type must be one of: {', '.join(sorted(ALLOWED_FEEDBACK_TYPES))}")
        return v


class FeedbackStatsResponse(BaseModel):
    """Response body for feedback statistics."""
    total: int
    positive: int
    negative: int
    positive_rate: float
    top_issues: List[Dict]
    by_category: Dict[str, int]
    period_days: int


# =============================================================================
# Routes
# =============================================================================

def _get_db():
    """Lazy DB session dependency."""
    from db import get_db
    yield from get_db()


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackSubmit,
    db: Session = Depends(_get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """
    Submit feedback (thumbs-up / thumbs-down) on an AI response.

    Creates an AIFeedbackLog entry with the rating mapped to feedback_type.
    Rate limited to 30 requests per minute per user.
    """
    user_id_str = str(getattr(current_user, "id", "unknown"))
    _check_feedback_rate_limit(user_id_str)

    try:
        from database.models.ai import AIFeedbackLog
    except ImportError:
        # Fallback: import through main
        try:
            import main
            AIFeedbackLog = main.AIFeedbackLog
        except Exception as e:
            logger.error(f"Cannot import AIFeedbackLog: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # Map rating to a feedback_type if none provided
    feedback_type = body.feedback_type
    if not feedback_type:
        feedback_type = "helpful" if body.rating == "positive" else "other"

    # Auto-detect category from the question text
    category = _auto_detect_category(body.user_question) if body.user_question else "general"

    try:
        entry = AIFeedbackLog(
            user_id=current_user.id,
            organization_id=getattr(current_user, "organization_id", None),
            user_question=body.user_question or "(no question provided)",
            ai_response=body.ai_response or "(no response provided)",
            feedback_type=feedback_type,
            user_feedback=body.feedback_text,
            category=category,
            session_id=body.session_id,
            request_id=body.message_id,
            status="pending" if body.rating == "negative" else "reviewed",
        )

        db.add(entry)
        db.commit()
        db.refresh(entry)

        logger.info(
            f"AI feedback collected: id={entry.id}, rating={body.rating}, "
            f"type={feedback_type}, session={body.session_id}"
        )

        # If negative feedback, save as memory and trigger learning synchronously.
        # Failures here are logged but do not block the feedback response (it was already saved).
        if body.rating == "negative" and body.user_question and body.ai_response:
            try:
                _save_feedback_as_memory(
                    db=db,
                    feedback_log=entry,
                    current_user=current_user,
                    feedback_text=body.feedback_text,
                    category=category,
                )
            except Exception as mem_err:
                logger.warning(
                    f"Failed to save feedback as memory for feedback_id={entry.id}: {mem_err}"
                )

            try:
                _trigger_learning_from_feedback(
                    session_id=body.session_id,
                    question=body.user_question,
                    response=body.ai_response,
                    feedback_text=body.feedback_text,
                    feedback_type=feedback_type,
                )
            except Exception as learn_err:
                logger.warning(
                    f"Failed to trigger learning from feedback for session={body.session_id}: {learn_err}"
                )

        return {
            "success": True,
            "feedback_id": entry.id,
            "message": "Feedback recorded. Thank you!",
        }

    except SQLAlchemyError as e:
        logger.error(f"Error saving feedback: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(_get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """
    Get feedback statistics for the current user's organization.

    Returns total counts, positive rate, and top issues.
    """
    try:
        from database.models.ai import AIFeedbackLog
    except ImportError:
        try:
            import main
            AIFeedbackLog = main.AIFeedbackLog
        except Exception as e:
            logger.error(f"Cannot import AIFeedbackLog: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    org_id = getattr(current_user, "organization_id", None)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Base query scoped to organization and time window
        base_q = db.query(AIFeedbackLog).filter(AIFeedbackLog.created_at >= cutoff)
        if org_id:
            base_q = base_q.filter(AIFeedbackLog.organization_id == org_id)

        total = base_q.count()

        # Positive = feedback_type in helpful/accurate OR status reviewed (from positive rating)
        # Negative = everything else
        positive_types = {"helpful", "accurate"}
        positive = base_q.filter(AIFeedbackLog.feedback_type.in_(positive_types)).count()
        negative = total - positive

        positive_rate = round((positive / total * 100) if total > 0 else 0.0, 1)

        # Top issues: group negative feedback by feedback_type
        negative_types_q = (
            db.query(
                AIFeedbackLog.feedback_type,
                func.count(AIFeedbackLog.id).label("count"),
            )
            .filter(
                AIFeedbackLog.created_at >= cutoff,
                AIFeedbackLog.feedback_type.notin_(positive_types),
            )
        )
        if org_id:
            negative_types_q = negative_types_q.filter(AIFeedbackLog.organization_id == org_id)

        negative_types_q = (
            negative_types_q
            .group_by(AIFeedbackLog.feedback_type)
            .order_by(func.count(AIFeedbackLog.id).desc())
            .limit(10)
            .all()
        )

        top_issues = [
            {"feedback_type": row[0], "count": row[1]}
            for row in negative_types_q
        ]

        # By category
        category_q = (
            db.query(
                AIFeedbackLog.category,
                func.count(AIFeedbackLog.id).label("count"),
            )
            .filter(AIFeedbackLog.created_at >= cutoff)
        )
        if org_id:
            category_q = category_q.filter(AIFeedbackLog.organization_id == org_id)

        category_q = category_q.group_by(AIFeedbackLog.category).all()

        by_category = {(row[0] or "uncategorized"): row[1] for row in category_q}

        return FeedbackStatsResponse(
            total=total,
            positive=positive,
            negative=negative,
            positive_rate=positive_rate,
            top_issues=top_issues,
            by_category=by_category,
            period_days=days,
        )

    except SQLAlchemyError as e:
        logger.error(f"Error fetching feedback stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Helpers
# =============================================================================

def _auto_detect_category(question: Optional[str]) -> str:
    """Auto-detect feedback category from the user's question text."""
    if not question:
        return "general"

    q = question.lower()
    if any(w in q for w in ("sla", "turnaround", "turn time", "deadline")):
        return "sla"
    if any(w in q for w in ("pipeline", "bottleneck", "stage", "funnel")):
        return "pipeline"
    if any(w in q for w in ("task", "todo", "priority", "action item")):
        return "tasks"
    if any(w in q for w in ("loan", "mortgage", "rate", "closing", "underwriting")):
        return "loans"
    if any(w in q for w in ("lead", "prospect", "client", "borrower")):
        return "leads"
    if any(w in q for w in ("document", "doc", "upload", "missing")):
        return "documents"
    if any(w in q for w in ("compliance", "trid", "respa", "disclosure")):
        return "compliance"
    return "general"


def _trigger_learning_from_feedback(
    session_id: str,
    question: str,
    response: str,
    feedback_text: Optional[str],
    feedback_type: str,
) -> None:
    """
    Feed negative feedback into ConversationAILearningService as a correction.
    Runs synchronously within the request. Raises on failure so the caller can log it.
    """
    try:
        from services.conversation_ai_learning_service import conversation_ai_learning_service
    except ImportError as e:
        logger.error(f"Cannot import conversation_ai_learning_service: {e}")
        return

    conversation_ai_learning_service.add_correction(
        original_query=question,
        incorrect_response=response,
        correct_response=feedback_text or "(user indicated this was wrong)",
        explanation=f"User feedback type: {feedback_type}",
        source_conversation_id=session_id,
    )
    logger.info(f"Learning correction added from feedback for session {session_id}")


def _save_feedback_as_memory(
    db: Session,
    feedback_log,
    current_user,
    feedback_text: Optional[str],
    category: str,
) -> None:
    """
    Save negative feedback as a DIRECTIVE-type AgentMemory so the analyze node
    can retrieve it in future conversations and avoid repeating the same mistake.

    Raises on DB errors so the caller can handle and log the failure.
    """
    from database.models.agent_memory import AgentMemory, MemoryType

    memory_key = f"feedback_correction_{feedback_log.id}"

    memory = AgentMemory(
        user_id=current_user.id,
        organization_id=getattr(current_user, "organization_id", None),
        memory_type=MemoryType.DIRECTIVE,
        key=memory_key,
        value=(
            f"User reported issue with AI response: "
            f"{feedback_text or 'negative feedback'}. "
            f"Category: {category}. Avoid similar responses."
        ),
        confidence=0.8,
        agent_role="user_feedback",
    )
    db.add(memory)
    db.commit()
    logger.info(
        f"Feedback memory saved: memory_type=DIRECTIVE, key={memory_key}"
    )
