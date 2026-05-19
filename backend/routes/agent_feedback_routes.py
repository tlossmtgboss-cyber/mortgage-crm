"""
Agent Feedback Routes

REST API for submitting and analyzing user feedback on AI agent responses.
Powers the feedback loop that drives agent quality improvements.

Endpoints:
    POST /api/v1/agent/feedback                Submit feedback on an AI response
    GET  /api/v1/agent/feedback/stats           Feedback statistics (admin)
    GET  /api/v1/agent/feedback/recent          Recent feedback entries
    GET  /api/v1/agent/feedback/trends          Daily satisfaction trends (admin)
    POST /api/v1/agent/feedback/summary/generate  Generate a period summary (admin)
    GET  /api/v1/agent/feedback/improvements    Improvement suggestions from negative feedback (admin)
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, cast, String
from sqlalchemy.orm import Session
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class FeedbackSubmitRequest(BaseModel):
    conversation_id: str = Field(..., max_length=100)
    message_index: Optional[int] = None
    rating: str = Field(..., pattern="^(positive|negative|neutral)$")
    feedback_text: Optional[str] = None
    agent_role: Optional[str] = None
    intent: Optional[str] = None
    query_text: Optional[str] = None
    response_text: Optional[str] = None
    tools_used: Optional[list] = None
    response_time_ms: Optional[int] = None


class FeedbackSubmitResponse(BaseModel):
    id: int
    status: str = "recorded"


class SummaryGenerateRequest(BaseModel):
    agent_role: str
    period_start: datetime
    period_end: datetime


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_agent_feedback_routes(app, get_db, get_current_user, **kwargs):
    """
    Register agent feedback routes.

    Args:
        app: FastAPI application instance.
        get_db: Database session dependency.
        get_current_user: Auth dependency returning current User.
    """

    # Lazy imports to avoid circular deps
    from database.models.agent_feedback import AgentFeedback, AgentFeedbackSummary
    from database.models.learning_example import LearningExample

    def _require_admin(current_user):
        """Raise 403 if the user is not a platform or site admin."""
        role = getattr(current_user, "role", None)
        if role not in ("Platform Admin", "Site Admin", "platform_admin", "site_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

    # -------------------------------------------------------------------
    # POST /api/v1/agent/feedback - Submit feedback
    # -------------------------------------------------------------------
    @app.post("/api/v1/agent/feedback", tags=["Agent Feedback"])
    async def submit_agent_feedback(
        body: FeedbackSubmitRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """
        Record user feedback on an AI agent response.

        If the rating is negative, a LearningExample is also created so the
        training pipeline can incorporate the failure case.
        """
        try:
            fb = AgentFeedback(
                organization_id=current_user.organization_id,
                user_id=current_user.id,
                conversation_id=body.conversation_id,
                message_index=body.message_index,
                rating=body.rating,
                feedback_text=body.feedback_text,
                agent_role=body.agent_role,
                intent=body.intent,
                query_text=body.query_text,
                response_text=body.response_text,
                tools_used=body.tools_used,
                response_time_ms=body.response_time_ms,
            )
            db.add(fb)
            await db.flush()  # get fb.id before commit

            # Negative feedback -> create a learning example for training
            if body.rating == "negative" and body.query_text:
                example = LearningExample(
                    organization_id=current_user.organization_id,
                    example_type="negative",
                    intent=body.intent,
                    agent_role=body.agent_role,
                    query_text=body.query_text,
                    actual_response=body.response_text,
                    tools_used=body.tools_used,
                    correction_notes=body.feedback_text,
                    feedback_id=fb.id,
                    quality_score=0,
                )
                db.add(example)

            await db.commit()
            return FeedbackSubmitResponse(id=fb.id)

        except Exception as e:
            await db.rollback()
            logger.exception(f"Failed to record agent feedback: {e}")
            raise HTTPException(status_code=500, detail="Failed to record feedback")

    # -------------------------------------------------------------------
    # GET /api/v1/agent/feedback/stats - Feedback statistics (admin)
    # -------------------------------------------------------------------
    @app.get("/api/v1/agent/feedback/stats", tags=["Agent Feedback"])
    async def get_feedback_stats(
        agent_role: Optional[str] = Query(default=None),
        days: int = Query(default=30, ge=1, le=365),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Aggregate feedback statistics, optionally filtered by agent role."""
        _require_admin(current_user)

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            base_q = db.query(AgentFeedback).filter(
                AgentFeedback.organization_id == current_user.organization_id,
                AgentFeedback.created_at >= cutoff,
            )
            if agent_role:
                base_q = base_q.filter(AgentFeedback.agent_role == agent_role)

            total = base_q.count()
            positive = base_q.filter(AgentFeedback.rating == "positive").count()
            negative = base_q.filter(AgentFeedback.rating == "negative").count()
            neutral = base_q.filter(AgentFeedback.rating == "neutral").count()
            satisfaction_rate = round(positive / total * 100, 1) if total > 0 else 0.0

            # Breakdown by role
            by_role_rows = (
                db.query(
                    AgentFeedback.agent_role,
                    AgentFeedback.rating,
                    func.count().label("cnt"),
                )
                .filter(
                    AgentFeedback.organization_id == current_user.organization_id,
                    AgentFeedback.created_at >= cutoff,
                    AgentFeedback.agent_role.isnot(None),
                )
                .group_by(AgentFeedback.agent_role, AgentFeedback.rating)
                .all()
            )
            by_role: dict = {}
            for role, rating, cnt in by_role_rows:
                by_role.setdefault(role, {"positive": 0, "negative": 0, "neutral": 0, "total": 0})
                by_role[role][rating] = cnt
                by_role[role]["total"] += cnt

            # Breakdown by intent
            by_intent_rows = (
                db.query(
                    AgentFeedback.intent,
                    AgentFeedback.rating,
                    func.count().label("cnt"),
                )
                .filter(
                    AgentFeedback.organization_id == current_user.organization_id,
                    AgentFeedback.created_at >= cutoff,
                    AgentFeedback.intent.isnot(None),
                )
                .group_by(AgentFeedback.intent, AgentFeedback.rating)
                .all()
            )
            by_intent: dict = {}
            for intent, rating, cnt in by_intent_rows:
                by_intent.setdefault(intent, {"positive": 0, "negative": 0, "neutral": 0, "total": 0})
                by_intent[intent][rating] = cnt
                by_intent[intent]["total"] += cnt

            return {
                "total": total,
                "positive": positive,
                "negative": negative,
                "neutral": neutral,
                "satisfaction_rate": satisfaction_rate,
                "by_role": by_role,
                "by_intent": by_intent,
            }

        except Exception as e:
            logger.exception(f"Failed to compute feedback stats: {e}")
            raise HTTPException(status_code=500, detail="Failed to compute feedback stats")

    # -------------------------------------------------------------------
    # GET /api/v1/agent/feedback/recent - Recent feedback entries
    # -------------------------------------------------------------------
    @app.get("/api/v1/agent/feedback/recent", tags=["Agent Feedback"])
    async def get_recent_feedback(
        agent_role: Optional[str] = Query(default=None),
        rating: Optional[str] = Query(default=None, pattern="^(positive|negative|neutral)$"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Return recent feedback entries with optional filters."""
        try:
            q = db.query(AgentFeedback).filter(
                AgentFeedback.organization_id == current_user.organization_id,
            )
            if agent_role:
                q = q.filter(AgentFeedback.agent_role == agent_role)
            if rating:
                q = q.filter(AgentFeedback.rating == rating)

            total = q.count()
            rows = (
                q.order_by(AgentFeedback.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            items = [
                {
                    "id": r.id,
                    "conversation_id": r.conversation_id,
                    "message_index": r.message_index,
                    "rating": r.rating,
                    "feedback_text": r.feedback_text,
                    "agent_role": r.agent_role,
                    "intent": r.intent,
                    "query_text": r.query_text,
                    "response_time_ms": r.response_time_ms,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

            return {"total": total, "limit": limit, "offset": offset, "items": items}

        except Exception as e:
            logger.exception(f"Failed to fetch recent feedback: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch recent feedback")

    # -------------------------------------------------------------------
    # GET /api/v1/agent/feedback/trends - Daily satisfaction trends (admin)
    # -------------------------------------------------------------------
    @app.get("/api/v1/agent/feedback/trends", tags=["Agent Feedback"])
    async def get_feedback_trends(
        days: int = Query(default=30, ge=1, le=365),
        agent_role: Optional[str] = Query(default=None),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Return daily satisfaction scores over the given window."""
        _require_admin(current_user)

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            date_expr = func.date(AgentFeedback.created_at)

            q = (
                db.query(
                    date_expr.label("day"),
                    AgentFeedback.rating,
                    func.count().label("cnt"),
                )
                .filter(
                    AgentFeedback.organization_id == current_user.organization_id,
                    AgentFeedback.created_at >= cutoff,
                )
            )
            if agent_role:
                q = q.filter(AgentFeedback.agent_role == agent_role)

            rows = q.group_by(date_expr, AgentFeedback.rating).all()

            daily: dict = {}
            for day, rating_val, cnt in rows:
                day_str = str(day)
                daily.setdefault(day_str, {"positive": 0, "negative": 0, "neutral": 0, "total": 0})
                daily[day_str][rating_val] = cnt
                daily[day_str]["total"] += cnt

            trends = []
            for day_str in sorted(daily.keys()):
                d = daily[day_str]
                sat = round(d["positive"] / d["total"] * 100, 1) if d["total"] > 0 else 0.0
                trends.append({"date": day_str, "satisfaction_rate": sat, **d})

            return {"days": days, "trends": trends}

        except Exception as e:
            logger.exception(f"Failed to compute feedback trends: {e}")
            raise HTTPException(status_code=500, detail="Failed to compute feedback trends")

    # -------------------------------------------------------------------
    # POST /api/v1/agent/feedback/summary/generate - Generate summary (admin)
    # -------------------------------------------------------------------
    @app.post("/api/v1/agent/feedback/summary/generate", tags=["Agent Feedback"])
    async def generate_feedback_summary(
        body: SummaryGenerateRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """
        Aggregate feedback for a specific agent role and period into a summary record.
        """
        _require_admin(current_user)

        try:
            org_id = current_user.organization_id
            base_q = db.query(AgentFeedback).filter(
                AgentFeedback.organization_id == org_id,
                AgentFeedback.agent_role == body.agent_role,
                AgentFeedback.created_at >= body.period_start,
                AgentFeedback.created_at <= body.period_end,
            )

            total = base_q.count()
            if total == 0:
                raise HTTPException(status_code=404, detail="No feedback found for the given period and role")

            positive = base_q.filter(AgentFeedback.rating == "positive").count()
            negative = base_q.filter(AgentFeedback.rating == "negative").count()

            avg_rt = db.query(func.avg(AgentFeedback.response_time_ms)).filter(
                AgentFeedback.organization_id == org_id,
                AgentFeedback.agent_role == body.agent_role,
                AgentFeedback.created_at >= body.period_start,
                AgentFeedback.created_at <= body.period_end,
                AgentFeedback.response_time_ms.isnot(None),
            ).scalar()

            avg_tok = db.query(func.avg(AgentFeedback.token_count)).filter(
                AgentFeedback.organization_id == org_id,
                AgentFeedback.agent_role == body.agent_role,
                AgentFeedback.created_at >= body.period_start,
                AgentFeedback.created_at <= body.period_end,
                AgentFeedback.token_count.isnot(None),
            ).scalar()

            # Top intents
            intent_rows = (
                db.query(AgentFeedback.intent, func.count().label("cnt"))
                .filter(
                    AgentFeedback.organization_id == org_id,
                    AgentFeedback.agent_role == body.agent_role,
                    AgentFeedback.created_at >= body.period_start,
                    AgentFeedback.created_at <= body.period_end,
                    AgentFeedback.intent.isnot(None),
                )
                .group_by(AgentFeedback.intent)
                .order_by(func.count().desc())
                .limit(10)
                .all()
            )
            top_intents = [{"intent": i, "count": c} for i, c in intent_rows]

            # Common complaints from negative feedback
            neg_rows = (
                base_q.filter(
                    AgentFeedback.rating == "negative",
                    AgentFeedback.feedback_text.isnot(None),
                )
                .order_by(AgentFeedback.created_at.desc())
                .limit(20)
                .all()
            )
            common_complaints = [r.feedback_text for r in neg_rows if r.feedback_text]

            summary = AgentFeedbackSummary(
                organization_id=org_id,
                agent_role=body.agent_role,
                period_start=body.period_start,
                period_end=body.period_end,
                total_interactions=total,
                positive_count=positive,
                negative_count=negative,
                avg_response_time_ms=int(avg_rt) if avg_rt else None,
                avg_token_count=int(avg_tok) if avg_tok else None,
                top_intents=top_intents,
                common_complaints=common_complaints,
            )
            db.add(summary)
            await db.commit()
            await db.refresh(summary)

            return {
                "id": summary.id,
                "agent_role": summary.agent_role,
                "period_start": summary.period_start.isoformat(),
                "period_end": summary.period_end.isoformat(),
                "total_interactions": summary.total_interactions,
                "positive_count": summary.positive_count,
                "negative_count": summary.negative_count,
                "satisfaction_rate": round(positive / total * 100, 1) if total > 0 else 0.0,
                "avg_response_time_ms": summary.avg_response_time_ms,
                "avg_token_count": summary.avg_token_count,
                "top_intents": summary.top_intents,
                "common_complaints": summary.common_complaints,
            }

        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.exception(f"Failed to generate feedback summary: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate feedback summary")

    # -------------------------------------------------------------------
    # GET /api/v1/agent/feedback/improvements - Improvement suggestions (admin)
    # -------------------------------------------------------------------
    @app.get("/api/v1/agent/feedback/improvements", tags=["Agent Feedback"])
    async def get_improvement_suggestions(
        agent_role: Optional[str] = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """
        Analyze negative feedback patterns and return actionable suggestions.

        Groups negative feedback by agent role and intent, counts occurrences,
        and returns the most frequent problem areas.
        """
        _require_admin(current_user)

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            q = (
                db.query(
                    AgentFeedback.agent_role,
                    AgentFeedback.intent,
                    func.count().label("cnt"),
                )
                .filter(
                    AgentFeedback.organization_id == current_user.organization_id,
                    AgentFeedback.rating == "negative",
                    AgentFeedback.created_at >= cutoff,
                )
            )
            if agent_role:
                q = q.filter(AgentFeedback.agent_role == agent_role)

            rows = (
                q.group_by(AgentFeedback.agent_role, AgentFeedback.intent)
                .order_by(func.count().desc())
                .limit(limit)
                .all()
            )

            suggestions = []
            for role, intent, cnt in rows:
                # Grab sample feedback texts for context
                samples = (
                    db.query(AgentFeedback.feedback_text)
                    .filter(
                        AgentFeedback.organization_id == current_user.organization_id,
                        AgentFeedback.rating == "negative",
                        AgentFeedback.agent_role == role,
                        AgentFeedback.intent == intent,
                        AgentFeedback.feedback_text.isnot(None),
                    )
                    .order_by(AgentFeedback.created_at.desc())
                    .limit(3)
                    .all()
                )
                suggestions.append({
                    "agent_role": role,
                    "intent": intent,
                    "negative_count": cnt,
                    "sample_feedback": [s[0] for s in samples],
                })

            return {"suggestions": suggestions}

        except Exception as e:
            logger.exception(f"Failed to compute improvement suggestions: {e}")
            raise HTTPException(status_code=500, detail="Failed to compute improvement suggestions")
