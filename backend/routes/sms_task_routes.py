import json
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, validator
from database import get_db

logger = logging.getLogger(__name__)


def _get_current_user():
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible


router = APIRouter(prefix="/api/v1/sms-tasks", tags=["SMS Tasks"])


class RespondRequest(BaseModel):
    response_text: str
    response_source: str = "human"

    @validator("response_text")
    def validate_response_text(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("response_text cannot be empty")
        if len(v) > 1600:
            raise ValueError("response_text must be 1600 characters or fewer")
        return v

    @validator("response_source")
    def validate_response_source(cls, v):
        allowed = {"ai_accepted", "ai_edited", "human", "ai", "manual"}
        if v not in allowed:
            raise ValueError(f"response_source must be one of {allowed}")
        return v


class FeedbackRequest(BaseModel):
    rating: str

    @validator("rating")
    def validate_rating(cls, v):
        allowed = {"good", "acceptable", "poor", "positive", "negative"}
        if v not in allowed:
            raise ValueError(f"rating must be one of {allowed}")
        return v


class RegenerateRequest(BaseModel):
    feedback: str = ""

    @validator("feedback")
    def validate_feedback(cls, v):
        if len(v) > 2000:
            raise ValueError("feedback must be 2000 characters or fewer")
        return v


class SettingsUpdate(BaseModel):
    category: str
    auto_respond_enabled: Optional[bool] = None
    auto_respond_threshold: Optional[float] = None

    @validator("auto_respond_threshold")
    def validate_threshold(cls, v):
        if v is not None and not (50 <= v <= 99):
            raise ValueError("auto_respond_threshold must be between 50 and 99")
        return v


def _require_org(current_user) -> int:
    org_id = getattr(current_user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    return org_id


@router.get("")
async def list_sms_tasks(
    status: str = Query("pending"),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    mine: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_task_service import get_sms_tasks

        user_id = current_user.id if mine else None
        tasks, total = get_sms_tasks(
            db,
            organization_id=org_id,
            user_id=user_id,
            status=status,
            category=category,
            limit=limit,
            offset=offset,
        )
        return {
            "tasks": tasks,
            "total": total,
            "page_info": {"limit": limit, "offset": offset},
        }
    except Exception as e:
        logger.exception("Failed to list SMS tasks org=%s: %s", org_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_task_statistics(
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_task_service import get_task_stats
        from services.sms_confidence_engine import get_all_confidence

        counts = get_task_stats(db, organization_id=org_id)
        confidence = get_all_confidence(db, organization_id=org_id)
        return {"counts": counts, "confidence": confidence}
    except Exception as e:
        logger.exception("Failed to get SMS task stats org=%s: %s", org_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/settings")
async def get_auto_respond_settings(
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_confidence_engine import get_all_confidence

        settings = get_all_confidence(db, organization_id=org_id)
        return {"settings": settings}
    except Exception as e:
        logger.exception("Failed to get SMS settings org=%s: %s", org_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/settings")
async def update_auto_respond_settings(
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_confidence_engine import update_settings

        threshold = int(body.auto_respond_threshold) if body.auto_respond_threshold is not None else None
        updated = update_settings(
            db,
            organization_id=org_id,
            category=body.category,
            auto_respond_enabled=body.auto_respond_enabled,
            auto_respond_threshold=threshold,
        )
        db.commit()
        return {"settings": updated}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update SMS settings org=%s: %s", org_id, e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/confidence/trend")
async def get_confidence_trend(
    category: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_confidence_engine import get_confidence_trend as _get_trend

        trend = _get_trend(db, organization_id=org_id, category=category, days=days)
        return {"trend": trend, "days": days, "category": category}
    except Exception as e:
        logger.exception("Failed to get confidence trend org=%s: %s", org_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{task_id}")
async def get_sms_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_task_service import get_sms_task as _get_task

        task = _get_task(db, task_id=task_id, organization_id=org_id)
        if not task:
            raise HTTPException(status_code=404, detail="SMS task not found")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get SMS task %s org=%s: %s", task_id, org_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{task_id}/respond")
async def respond_to_task(
    task_id: int,
    body: RespondRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_auto_responder import process_user_response

        result = process_user_response(
            db,
            task_id=task_id,
            organization_id=org_id,
            user_id=current_user.id,
            response_text=body.response_text,
            response_source=body.response_source,
        )
        db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to respond to SMS task %s org=%s: %s", task_id, org_id, e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{task_id}/dismiss")
async def dismiss_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_task_service import dismiss_task as _dismiss

        task = _dismiss(
            db,
            task_id=task_id,
            organization_id=org_id,
            user_id=current_user.id,
        )
        db.commit()
        return {"status": "dismissed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to dismiss SMS task %s org=%s: %s", task_id, org_id, e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{task_id}/regenerate")
async def regenerate_recommendation(
    task_id: int,
    body: RegenerateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_ai_responder import regenerate_recommendation as _regenerate

        result = _regenerate(
            db,
            task_id=task_id,
            organization_id=org_id,
            feedback=body.feedback,
        )
        if result.get("recommendation") is None:
            raise HTTPException(status_code=404, detail="SMS task not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Failed to regenerate recommendation for task %s org=%s: %s", task_id, org_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{task_id}/feedback")
async def post_feedback(
    task_id: int,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    org_id = _require_org(current_user)
    try:
        from services.sms_task_service import get_sms_task as _get_task
        from datetime import datetime, timezone

        task = _get_task(db, task_id=task_id, organization_id=org_id)
        if not task:
            raise HTTPException(status_code=404, detail="SMS task not found")

        now = datetime.now(timezone.utc)
        db.execute(
            text("""
                UPDATE sms_tasks
                SET user_feedback = :feedback,
                    updated_at = :now
                WHERE id = :task_id
                  AND organization_id = :org_id
            """),
            {
                "feedback": body.rating,
                "now": now,
                "task_id": task_id,
                "org_id": org_id,
            },
        )

        db.execute(
            text("""
                INSERT INTO sms_ai_audit_log
                    (organization_id, task_id, action, details, user_id, created_at)
                VALUES
                    (:org_id, :task_id, 'feedback', :details, :user_id, :now)
            """),
            {
                "org_id": org_id,
                "task_id": task_id,
                "details": json.dumps({"rating": body.rating}),
                "user_id": current_user.id,
                "now": now,
            },
        )
        db.commit()
        return {"status": "recorded", "task_id": task_id, "rating": body.rating}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to record feedback for task %s org=%s: %s", task_id, org_id, e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
