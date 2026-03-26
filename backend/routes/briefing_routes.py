"""
Morning Briefing API Routes

GET  /api/v1/briefing/today         — Today's briefing for current user
GET  /api/v1/briefing/history       — Paginated briefing history
POST /api/v1/briefing/generate-now  — Manually trigger a briefing
POST /api/v1/briefing/{id}/viewed   — Mark briefing as viewed in-app
GET  /api/v1/briefing/preferences   — Get briefing preferences
PUT  /api/v1/briefing/preferences   — Update briefing preferences
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from typing import Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/briefing", tags=["Morning Briefing"])


def _get_deps():
    """Lazy import to avoid circular imports."""
    from database.models.morning_briefing import MorningBriefing
    from database.models import User
    return MorningBriefing, User


# --- Schemas ---

class BriefingSections(BaseModel):
    pipeline_health: bool = True
    sla_alerts: bool = True
    tasks: bool = True
    lead_activity: bool = True
    rate_watch: bool = True
    team_performance: bool = True


class BriefingThresholds(BaseModel):
    sla_warning_days: int = Field(default=3, ge=1, le=30)
    stale_lead_days: int = Field(default=7, ge=1, le=30)
    rate_change_threshold: float = Field(default=0.125, ge=0.01, le=1.0)


VALID_DELIVERY_TIMES = [f"{h:02d}:00" for h in range(5, 12)]  # 05:00 - 11:00


class BriefingPreferencesSchema(BaseModel):
    briefing_enabled: bool = True
    delivery_time: str = Field(default="07:00")
    sections: BriefingSections = BriefingSections()
    thresholds: BriefingThresholds = BriefingThresholds()
    ai_tone: Literal["concise", "detailed", "coaching"] = "concise"


class BriefingResponse(BaseModel):
    class Config:
        from_attributes = True


# --- Dependency stubs (replaced at registration) ---

_get_db = None
_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    if _get_db is None:
        raise RuntimeError("briefing_routes: dependencies not initialized")
    return _get_db()


def get_current_user():
    if _get_current_user is None:
        raise RuntimeError("briefing_routes: dependencies not initialized")
    return _get_current_user()


# --- Routes ---

@router.get("/today")
async def get_today_briefing(db: Session = Depends(get_db),
                              current_user=Depends(get_current_user)):
    """Get current user's briefing for today."""
    MorningBriefing, _ = _get_deps()

    user_tz = getattr(current_user, "timezone", None) or "America/Chicago"
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("America/Chicago")

    today = datetime.now(tz).date()

    briefing = db.query(MorningBriefing).filter(
        MorningBriefing.user_id == current_user.id,
        MorningBriefing.briefing_date == today,
    ).first()

    if not briefing:
        return Response(status_code=204)  # No briefing yet today

    data = briefing.briefing_data or {}
    team = briefing.team_data

    return {
        "id": briefing.id,
        "briefing_date": briefing.briefing_date.isoformat(),
        "briefing_level": briefing.briefing_level,
        "status": briefing.status,
        "ai_narrative": briefing.ai_narrative,
        "pipeline": data.get("pipeline", {}),
        "at_risk": data.get("at_risk", []),
        "stale_leads": data.get("stale_leads", []),
        "appointments": data.get("appointments", []),
        "conditions": data.get("conditions", []),
        "yesterday": data.get("yesterday", {}),
        "team": team,
        "viewed_in_app": briefing.viewed_in_app_at is not None,
        "created_at": briefing.created_at.isoformat() if briefing.created_at else None,
    }


@router.get("/history")
async def get_briefing_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get paginated briefing history."""
    MorningBriefing, _ = _get_deps()

    offset = (page - 1) * per_page
    briefings = (
        db.query(MorningBriefing)
        .filter(MorningBriefing.user_id == current_user.id)
        .order_by(MorningBriefing.briefing_date.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    return {
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": b.id,
                "briefing_date": b.briefing_date.isoformat(),
                "briefing_level": b.briefing_level,
                "status": b.status,
                "ai_narrative": (b.ai_narrative or "")[:200],
                "viewed_in_app": b.viewed_in_app_at is not None,
            }
            for b in briefings
        ],
    }


@router.post("/generate-now")
async def generate_now(
    force: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually trigger a briefing for current user."""
    MorningBriefing, _ = _get_deps()
    from services.morning_briefing_service import MorningBriefingService

    user_tz = getattr(current_user, "timezone", None) or "America/Chicago"
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("America/Chicago")

    today = datetime.now(tz).date()
    level = MorningBriefingService.determine_level(current_user)

    existing = db.query(MorningBriefing).filter(
        MorningBriefing.user_id == current_user.id,
        MorningBriefing.briefing_date == today,
    ).first()

    if existing and not force:
        raise HTTPException(status_code=409, detail="Briefing already exists for today. Use force=true to regenerate.")

    if existing and force:
        db.delete(existing)
        db.commit()

    from tasks.morning_briefing_tasks import generate_user_briefing
    generate_user_briefing.apply_async(args=[current_user.id, today.isoformat(), level])

    return JSONResponse(status_code=202, content={"status": "accepted", "message": "Briefing generation started"})


@router.post("/{briefing_id}/viewed")
async def mark_viewed(
    briefing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark a briefing as viewed in-app."""
    MorningBriefing, _ = _get_deps()

    briefing = db.query(MorningBriefing).filter(
        MorningBriefing.id == briefing_id,
        MorningBriefing.user_id == current_user.id,
    ).first()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    if not briefing.viewed_in_app_at:
        briefing.viewed_in_app_at = datetime.now(timezone.utc)
        briefing.updated_at = datetime.now(timezone.utc)
        db.commit()

    return {"status": "ok"}


@router.get("/preferences")
async def get_preferences(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get briefing preferences (merged with defaults)."""
    from services.morning_briefing_service import MorningBriefingService
    prefs = MorningBriefingService.load_preferences(current_user)
    # Convert briefing_hour int to delivery_time string for the frontend
    briefing_hour = getattr(current_user, "briefing_hour", 7) or 7
    delivery_time = f"{briefing_hour:02d}:00"
    return {
        "briefing_enabled": getattr(current_user, "briefing_enabled", True) if current_user.briefing_enabled is not None else True,
        "delivery_time": delivery_time,
        "timezone": getattr(current_user, "timezone", "America/New_York"),
        "sections": prefs.sections,
        "thresholds": prefs.thresholds,
        "ai_tone": prefs.ai_tone,
    }


@router.put("/preferences")
async def update_preferences(
    prefs: BriefingPreferencesSchema,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update briefing preferences.

    Split-write: briefing_enabled and briefing_hour go to dedicated User columns
    (used by Celery dispatch for fast SQL filtering). sections, thresholds, and
    ai_tone go to user.briefing_preferences JSONB.
    delivery_time string ("07:00") is converted to briefing_hour int for the DB.
    """
    # Convert delivery_time string to briefing_hour int
    try:
        hour = int(prefs.delivery_time.split(":")[0])
    except (ValueError, IndexError):
        hour = 7

    # Dedicated columns (fast SQL filtering by Celery dispatch)
    current_user.briefing_enabled = prefs.briefing_enabled
    current_user.briefing_hour = hour

    # JSONB column (customization preferences)
    current_user.briefing_preferences = {
        "sections": prefs.sections.model_dump(),
        "thresholds": prefs.thresholds.model_dump(),
        "ai_tone": prefs.ai_tone,
    }
    db.commit()

    from services.morning_briefing_service import MorningBriefingService
    loaded = MorningBriefingService.load_preferences(current_user)
    delivery_time = f"{current_user.briefing_hour:02d}:00"
    return {
        "briefing_enabled": current_user.briefing_enabled,
        "delivery_time": delivery_time,
        "timezone": getattr(current_user, "timezone", "America/New_York"),
        "sections": loaded.sections,
        "thresholds": loaded.thresholds,
        "ai_tone": loaded.ai_tone,
    }
