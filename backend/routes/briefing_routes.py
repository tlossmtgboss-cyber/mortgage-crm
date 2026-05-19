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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/briefing", tags=["Morning Briefing"])


def _get_auth():
    """Lazy import auth dependency to avoid circular imports at module load."""
    from auth.dependencies import get_current_user
    return get_current_user


def _get_deps():
    """Lazy import to avoid circular imports."""
    from database.models.morning_briefing import MorningBriefing
    from database.models import User
    return MorningBriefing, User


# --- Schemas ---

class BriefingSections(BaseModel):
    pipeline: bool = True
    at_risk: bool = True
    stale_leads: bool = True
    appointments: bool = True
    conditions: bool = True
    yesterday: bool = True


class BriefingThresholds(BaseModel):
    at_risk_days: int = Field(default=10, ge=1, le=30)
    stale_lead_days: int = Field(default=7, ge=1, le=30)
    stale_lead_high_score_days: int = Field(default=3, ge=1, le=14)
    lock_expiring_days: int = Field(default=3, ge=1, le=14)
    max_at_risk_items: int = Field(default=10, ge=1, le=20)
    max_stale_lead_items: int = Field(default=10, ge=1, le=20)


class BriefingPreferencesSchema(BaseModel):
    briefing_enabled: bool = True
    briefing_hour: int = Field(ge=0, le=23, default=7)
    sections: BriefingSections = BriefingSections()
    thresholds: BriefingThresholds = BriefingThresholds()
    ai_tone: Literal["concise", "balanced", "detailed"] = "balanced"


class BriefingResponse(BaseModel):
    class Config:
        from_attributes = True


# --- Dependencies ---

_get_db = None


def set_dependencies(get_db_func, get_current_user_func=None):
    """Register DB dependency. Auth is imported from auth.dependencies."""
    global _get_db
    _get_db = get_db_func


def get_db():
    if _get_db is None:
        raise RuntimeError("briefing_routes: dependencies not initialized")
    yield from _get_db()


# Use canonical auth (deduped from local wrapper)
from auth.dependencies import get_current_user  # noqa: E402


# --- Routes ---

@router.get("/today")
async def get_today_briefing(db: AsyncSession = Depends(get_async_db),
                              current_user=Depends(get_current_user)):
    """Get current user's briefing for today."""
    MorningBriefing, _ = _get_deps()

    user_tz = getattr(current_user, "timezone", None) or "America/Chicago"
    try:
        tz = ZoneInfo(user_tz)
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        tz = ZoneInfo("America/Chicago")

    today = datetime.now(tz).date()

    try:
        briefing = (await db.execute(select(MorningBriefing).where(
            MorningBriefing.user_id == current_user.id,
            MorningBriefing.briefing_date == today,
        ))).scalars().first()
    except Exception as e:
        logger.error("Briefing query failed for user %s: %s", current_user.id, e)
        await db.rollback()
        return Response(status_code=204)

    if not briefing:
        return Response(status_code=204)

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
    db: AsyncSession = Depends(get_async_db),
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
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Manually trigger a briefing for current user."""
    MorningBriefing, _ = _get_deps()
    from services.morning_briefing_service import MorningBriefingService

    user_tz = getattr(current_user, "timezone", None) or "America/Chicago"
    try:
        tz = ZoneInfo(user_tz)
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        tz = ZoneInfo("America/Chicago")

    today = datetime.now(tz).date()
    level = MorningBriefingService.determine_level(current_user)

    try:
        existing = (await db.execute(select(MorningBriefing).where(
            MorningBriefing.user_id == current_user.id,
            MorningBriefing.briefing_date == today,
        ))).scalars().first()
    except Exception as e:
        logger.error("Briefing existence check failed: %s", e)
        await db.rollback()
        existing = None

    if existing and not force:
        raise HTTPException(status_code=409, detail="Briefing already exists for today. Use force=true to regenerate.")

    if existing and force:
        try:
            await db.delete(existing)
            await db.commit()
        except Exception as e:
            logger.error("Failed to delete existing briefing: %s", e)
            await db.rollback()

    # Try Celery first, fall back to synchronous generation
    try:
        from tasks.morning_briefing_tasks import generate_user_briefing
        generate_user_briefing.apply_async(args=[current_user.id, today.isoformat(), level])
        return JSONResponse(status_code=202, content={"status": "accepted", "message": "Briefing generation started"})
    except Exception as celery_err:
        logger.warning("Celery unavailable (%s), generating briefing synchronously", celery_err)

    # Synchronous fallback — generate inline when Celery/Redis isn't running
    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    try:
        service = MorningBriefingService()
        prefs = service.load_preferences(current_user)
        ctx = service.build_context(db, current_user, today, prefs)

        narrative = service.generate_narrative(ctx, prefs.ai_tone, prefs)

        briefing = MorningBriefing(
            organization_id=org_id,
            user_id=current_user.id,
            briefing_date=today,
            briefing_level=level,
            status="delivered",
            ai_narrative=narrative,
            briefing_data={
                "pipeline": ctx.pipeline,
                "at_risk": ctx.at_risk,
                "stale_leads": ctx.stale_leads,
                "appointments": ctx.appointments,
                "conditions": ctx.conditions,
                "yesterday": ctx.yesterday,
            },
            team_data=ctx.team if ctx.team else None,
        )
        db.add(briefing)
        await db.commit()
        return JSONResponse(status_code=201, content={"status": "generated", "message": "Briefing generated"})
    except HTTPException:
        raise
    except Exception as sync_err:
        await db.rollback()
        from sqlalchemy.exc import IntegrityError
        if isinstance(sync_err, IntegrityError):
            raise HTTPException(status_code=409, detail="Briefing already exists for today")
        logger.exception("Synchronous briefing generation failed: %s", sync_err)
        raise HTTPException(status_code=500, detail="Briefing generation failed")


@router.post("/{briefing_id}/viewed")
async def mark_viewed(
    briefing_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Mark a briefing as viewed in-app."""
    MorningBriefing, _ = _get_deps()

    briefing = (await db.execute(select(MorningBriefing).where(
        MorningBriefing.id == briefing_id,
        MorningBriefing.user_id == current_user.id,
    ))).scalars().first()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    if not briefing.viewed_in_app_at:
        briefing.viewed_in_app_at = datetime.now(timezone.utc)
        briefing.updated_at = datetime.now(timezone.utc)
        await db.commit()

    return {"status": "ok"}


@router.get("/preferences")
async def get_preferences(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Get briefing preferences (merged with defaults)."""
    from services.morning_briefing_service import MorningBriefingService
    prefs = MorningBriefingService.load_preferences(current_user)
    enabled = getattr(current_user, "briefing_enabled", True)
    return {
        "briefing_enabled": enabled if enabled is not None else True,
        "briefing_hour": getattr(current_user, "briefing_hour", 7) or 7,
        "timezone": getattr(current_user, "timezone", "America/New_York"),
        "sections": prefs.sections,
        "thresholds": prefs.thresholds,
        "ai_tone": prefs.ai_tone,
    }


@router.put("/preferences")
async def update_preferences(
    prefs: BriefingPreferencesSchema,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Update briefing preferences.

    Split-write: briefing_enabled and briefing_hour go to dedicated User columns
    (used by Celery dispatch for fast SQL filtering). sections, thresholds, and
    ai_tone go to user.briefing_preferences JSONB.
    """
    # Dedicated columns (fast SQL filtering by Celery dispatch)
    current_user.briefing_enabled = prefs.briefing_enabled
    current_user.briefing_hour = prefs.briefing_hour

    # JSONB column (customization preferences)
    current_user.briefing_preferences = {
        "sections": prefs.sections.model_dump(),
        "thresholds": prefs.thresholds.model_dump(),
        "ai_tone": prefs.ai_tone,
    }
    await db.commit()

    from services.morning_briefing_service import MorningBriefingService
    loaded = MorningBriefingService.load_preferences(current_user)
    return {
        "briefing_enabled": current_user.briefing_enabled,
        "briefing_hour": current_user.briefing_hour,
        "timezone": getattr(current_user, "timezone", "America/New_York"),
        "sections": loaded.sections,
        "thresholds": loaded.thresholds,
        "ai_tone": loaded.ai_tone,
    }
