"""
Perennia AI — URLA Call Intelligence Routes
============================================
API endpoints for URLA voice agent call intelligence:
  - Trigger analysis on a completed application
  - Retrieve call scores, briefings, tasks
  - Get aggregate analytics
  - List recent URLA sessions
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger("urla.routes.intelligence")

# ---------------------------------------------------------------------------
# Auth & DB dependencies — match existing codebase patterns
# ---------------------------------------------------------------------------

from auth.dependencies import get_current_user

try:
    from db import get_db
except ImportError:
    from database import get_db

# ---------------------------------------------------------------------------
# URLA module imports — graceful fallback when modules are not yet available
# ---------------------------------------------------------------------------

_URLA_AVAILABLE = True

try:
    from agents.urla.state import URLAStateManager
    from agents.urla.call_intelligence import (
        analyze_call,
        URLACallIntelligenceResult,
    )
except ImportError as e:
    _URLA_AVAILABLE = False
    logger.warning(f"URLA modules not fully available: {e}")

# Optional sub-modules — some may not exist yet
_HAS_SCORING = False
_HAS_BRIEFING = False
_HAS_BRIEFING_HTML = False
_HAS_TASK_GENERATOR = False
_HAS_ANALYTICS = False

try:
    from agents.urla.call_scoring import score_urla_call, URLACallScore
    _HAS_SCORING = True
except ImportError:
    pass

try:
    from agents.urla.lo_briefing import generate_lo_briefing, LOBriefing
    _HAS_BRIEFING = True
except ImportError:
    pass

try:
    from agents.urla.lo_briefing import format_briefing_as_html
    _HAS_BRIEFING_HTML = True
except ImportError:
    pass

try:
    from agents.urla.task_generator import generate_urla_tasks, URLATask
    _HAS_TASK_GENERATOR = True
except ImportError:
    pass

try:
    from agents.urla.call_analytics import compute_analytics
    _HAS_ANALYTICS = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/urla", tags=["URLA Call Intelligence"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    loan_id: str
    tenant_id: str
    analyzed_at: str
    score: dict
    briefing: dict
    tasks: list
    call_notes: dict


class ScoreResponse(BaseModel):
    loan_id: str
    score: dict


class BriefingResponse(BaseModel):
    loan_id: str
    briefing: dict


class TaskItem(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    due_in_hours: Optional[int] = None
    category: str = "general"


class TasksResponse(BaseModel):
    loan_id: str
    tasks: List[TaskItem]


class PushTasksResponse(BaseModel):
    loan_id: str
    tasks_created: int
    task_ids: List[int]


class TranscriptEntry(BaseModel):
    speaker: str
    text: str
    timestamp: Optional[str] = None


class TranscriptResponse(BaseModel):
    loan_id: str
    transcript: List[TranscriptEntry]
    entry_count: int


class SessionSummary(BaseModel):
    loan_id: str
    current_section: str
    completed_sections: List[str]
    is_finalized: bool
    created_at: str
    updated_at: str
    percent_complete: int
    borrower_name: Optional[str] = None


class SessionsResponse(BaseModel):
    sessions: List[SessionSummary]
    total: int


class AnalyticsResponse(BaseModel):
    tenant_id: str
    period_start: str
    period_end: str
    analytics: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_tenant_id(current_user) -> str:
    """Extract tenant identifier from the authenticated user.

    The CRM user model uses ``organization_id`` (int). The URLA state
    manager uses a string tenant key, so we convert.
    """
    org_id = getattr(current_user, "organization_id", None)
    if org_id is None:
        org_id = getattr(current_user, "org_id", None)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Unable to determine tenant from authenticated user")
    return str(org_id)


async def _get_state_manager() -> URLAStateManager:
    """Create and connect a URLAStateManager instance."""
    if not _URLA_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="URLA modules are not available on this deployment",
        )
    state = URLAStateManager()
    await state.connect()
    return state


async def _load_app(state: URLAStateManager, tenant_id: str, loan_id: str):
    """Load a URLA application from Redis, raising 404 if not found."""
    from agents.urla.models import URLAApplication

    app = await state.load_application(tenant_id, loan_id)
    if app is None:
        raise HTTPException(
            status_code=404,
            detail=f"URLA application '{loan_id}' not found for this tenant",
        )
    return app


# ---------------------------------------------------------------------------
# 1. POST /calls/{loan_id}/analyze
# ---------------------------------------------------------------------------

@router.post("/calls/{loan_id}/analyze", response_model=AnalyzeResponse)
async def analyze_urla_call(
    loan_id: str,
    current_user=Depends(get_current_user),
):
    """Trigger call intelligence analysis on a completed URLA application.

    The application must be finalized before analysis can run.
    """
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        app = await _load_app(state, tenant_id, loan_id)

        if not app.is_finalized:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"URLA application '{loan_id}' has not been finalized. "
                    "Complete the application before running analysis."
                ),
            )

        result = await analyze_call(app, tenant_id)

        # Persist call notes back onto the application record
        app.call_notes = result.call_notes
        await state.save_application(app)

        return AnalyzeResponse(
            loan_id=result.loan_id,
            tenant_id=result.tenant_id,
            analyzed_at=result.analyzed_at.isoformat(),
            score=result.score.model_dump(),
            briefing=result.briefing.model_dump(),
            tasks=[t.model_dump() for t in result.tasks],
            call_notes=result.call_notes.model_dump(mode="json"),
        )
    finally:
        await state.close()


# ---------------------------------------------------------------------------
# 2. GET /calls/{loan_id}/intelligence
# ---------------------------------------------------------------------------

@router.get("/calls/{loan_id}/intelligence")
async def get_call_intelligence(
    loan_id: str,
    current_user=Depends(get_current_user),
):
    """Return the full call intelligence result (score + briefing + tasks).

    If analysis has not yet been run, returns a 404 hint.
    """
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        app = await _load_app(state, tenant_id, loan_id)

        if not app.call_notes:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No call intelligence data found for '{loan_id}'. "
                    "Run POST /api/v1/urla/calls/{loan_id}/analyze first."
                ),
            )

        # Re-derive score and briefing from stored call notes + application
        # This is lightweight since call_notes already exist.
        result = await analyze_call(app, tenant_id)

        return {
            "loan_id": result.loan_id,
            "tenant_id": result.tenant_id,
            "analyzed_at": result.analyzed_at.isoformat(),
            "score": result.score.model_dump(),
            "briefing": result.briefing.model_dump(),
            "tasks": [t.model_dump() for t in result.tasks],
            "call_notes": result.call_notes.model_dump(mode="json"),
        }
    finally:
        await state.close()


# ---------------------------------------------------------------------------
# 3. GET /calls/{loan_id}/briefing
# ---------------------------------------------------------------------------

@router.get("/calls/{loan_id}/briefing", response_model=BriefingResponse)
async def get_lo_briefing(
    loan_id: str,
    current_user=Depends(get_current_user),
):
    """Return the LO briefing for a URLA application."""
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        app = await _load_app(state, tenant_id, loan_id)

        if _HAS_BRIEFING:
            briefing = await generate_lo_briefing(app, app.call_notes)
            return BriefingResponse(
                loan_id=loan_id,
                briefing=briefing.model_dump(),
            )

        # Fallback: use call_notes if available
        if app.call_notes:
            return BriefingResponse(
                loan_id=loan_id,
                briefing={
                    "headline": app.call_notes.executive_summary,
                    "key_facts": [app.call_notes.loan_snapshot],
                    "risk_factors": app.call_notes.red_flags,
                    "recommended_actions": app.call_notes.recommended_talking_points,
                    "borrower_sentiment": "unknown",
                },
            )

        raise HTTPException(
            status_code=404,
            detail=(
                f"No briefing data available for '{loan_id}'. "
                "Run POST /api/v1/urla/calls/{loan_id}/analyze first."
            ),
        )
    finally:
        await state.close()


# ---------------------------------------------------------------------------
# 4. GET /calls/{loan_id}/briefing/html
# ---------------------------------------------------------------------------

@router.get("/calls/{loan_id}/briefing/html", response_class=HTMLResponse)
async def get_lo_briefing_html(
    loan_id: str,
    current_user=Depends(get_current_user),
):
    """Return the LO briefing as styled HTML (for email or printing)."""
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        app = await _load_app(state, tenant_id, loan_id)

        if _HAS_BRIEFING_HTML and _HAS_BRIEFING:
            briefing = await generate_lo_briefing(app, app.call_notes)
            html_content = format_briefing_as_html(briefing, app)
            return HTMLResponse(content=html_content)

        # Fallback: generate basic HTML from call notes
        if not app.call_notes:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No briefing data available for '{loan_id}'. "
                    "Run POST /api/v1/urla/calls/{loan_id}/analyze first."
                ),
            )

        html = _build_fallback_briefing_html(app)
        return HTMLResponse(content=html)
    finally:
        await state.close()


def _build_fallback_briefing_html(app) -> str:
    """Generate minimal styled HTML from CallNotes when lo_briefing module is unavailable."""
    cn = app.call_notes
    primary = app.primary_borrower()
    name = "Unknown"
    if primary and primary.section_1a:
        first = primary.section_1a.first_name or ""
        last = primary.section_1a.last_name or ""
        name = f"{first} {last}".strip() or "Unknown"

    red_flags_html = ""
    if cn.red_flags:
        items = "".join(f"<li>{rf}</li>" for rf in cn.red_flags)
        red_flags_html = f"""
        <div class="section risk">
            <h3>Risk Factors</h3>
            <ul>{items}</ul>
        </div>"""

    concerns_html = ""
    if cn.stated_concerns:
        items = "".join(f"<li>{c}</li>" for c in cn.stated_concerns)
        concerns_html = f"""
        <div class="section">
            <h3>Borrower Concerns</h3>
            <ul>{items}</ul>
        </div>"""

    actions_html = ""
    if cn.recommended_talking_points:
        items = "".join(f"<li>{tp}</li>" for tp in cn.recommended_talking_points)
        actions_html = f"""
        <div class="section">
            <h3>Recommended Talking Points</h3>
            <ul>{items}</ul>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>URLA Briefing — {name}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 680px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; border-bottom: 2px solid #2563eb; padding-bottom: 0.5rem; }}
  h3 {{ font-size: 1rem; margin-top: 1.5rem; color: #374151; }}
  .section {{ margin-bottom: 1rem; }}
  .section.risk h3 {{ color: #dc2626; }}
  .section.risk ul {{ border-left: 3px solid #dc2626; padding-left: 1rem; }}
  p {{ line-height: 1.6; }}
  ul {{ line-height: 1.8; }}
  .meta {{ font-size: 0.85rem; color: #6b7280; }}
</style>
</head>
<body>
<h1>URLA Briefing: {name}</h1>
<p class="meta">Loan ID: {app.loan_id} &bull; Generated: {cn.generated_at.strftime('%Y-%m-%d %H:%M UTC') if cn.generated_at else 'N/A'}</p>

<div class="section">
    <h3>Executive Summary</h3>
    <p>{cn.executive_summary}</p>
</div>

<div class="section">
    <h3>Borrower Profile</h3>
    <p>{cn.borrower_profile}</p>
</div>

<div class="section">
    <h3>Loan Snapshot</h3>
    <p>{cn.loan_snapshot}</p>
</div>

{red_flags_html}
{concerns_html}
{actions_html}

<hr>
<p class="meta">Perennia AI &mdash; URLA Call Intelligence</p>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 5. GET /calls/{loan_id}/score
# ---------------------------------------------------------------------------

@router.get("/calls/{loan_id}/score", response_model=ScoreResponse)
async def get_call_score(
    loan_id: str,
    current_user=Depends(get_current_user),
):
    """Return the call quality/compliance score for a URLA application."""
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        app = await _load_app(state, tenant_id, loan_id)

        if not app.is_finalized:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"URLA application '{loan_id}' has not been finalized. "
                    "Scoring requires a finalized application."
                ),
            )

        # Use the dedicated scoring module if available, otherwise fall
        # back to the stub bundled in call_intelligence.py
        if _HAS_SCORING:
            score = await score_urla_call(app)
        else:
            # Import the stub from call_intelligence (always available)
            from agents.urla.call_intelligence import score_urla_call as _score
            score = await _score(app)

        return ScoreResponse(
            loan_id=loan_id,
            score=score.model_dump(),
        )
    finally:
        await state.close()


# ---------------------------------------------------------------------------
# 6. GET /calls/{loan_id}/tasks
# ---------------------------------------------------------------------------

@router.get("/calls/{loan_id}/tasks", response_model=TasksResponse)
async def get_call_tasks(
    loan_id: str,
    current_user=Depends(get_current_user),
):
    """Return auto-generated tasks for a URLA call."""
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        app = await _load_app(state, tenant_id, loan_id)

        if _HAS_TASK_GENERATOR:
            tasks = await generate_urla_tasks(app, app.call_notes)
        else:
            from agents.urla.call_intelligence import generate_urla_tasks as _gen
            tasks = await _gen(app, app.call_notes)

        return TasksResponse(
            loan_id=loan_id,
            tasks=[
                TaskItem(
                    title=t.title,
                    description=t.description,
                    priority=t.priority,
                    due_in_hours=t.due_in_hours,
                    category=t.category,
                )
                for t in tasks
            ],
        )
    finally:
        await state.close()


# ---------------------------------------------------------------------------
# 7. POST /calls/{loan_id}/tasks/push-to-crm
# ---------------------------------------------------------------------------

@router.post("/calls/{loan_id}/tasks/push-to-crm", response_model=PushTasksResponse)
async def push_tasks_to_crm(
    loan_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Push the auto-generated URLA tasks to the CRM task system.

    Creates actual Task records in PostgreSQL, assigned to the current user.
    """
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        app = await _load_app(state, tenant_id, loan_id)

        # Generate tasks
        if _HAS_TASK_GENERATOR:
            tasks = await generate_urla_tasks(app, app.call_notes)
        else:
            from agents.urla.call_intelligence import generate_urla_tasks as _gen
            tasks = await _gen(app, app.call_notes)

        if not tasks:
            return PushTasksResponse(loan_id=loan_id, tasks_created=0, task_ids=[])

        # Import Task model
        try:
            from database.models import Task as CRMTask
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="CRM database models not available",
            )

        created_ids: List[int] = []
        org_id = int(tenant_id) if tenant_id.isdigit() else None

        for task in tasks:
            due_date = None
            if task.due_in_hours:
                due_date = datetime.now(timezone.utc) + timedelta(hours=task.due_in_hours)

            crm_task = CRMTask(
                organization_id=org_id,
                title=task.title,
                description=task.description,
                priority=task.priority,
                status="pending",
                due_date=due_date,
                owner_id=current_user.id,
                related_type="urla_call_intelligence",
                related_contact_name=_get_borrower_name(app),
            )
            db.add(crm_task)
            db.flush()
            created_ids.append(crm_task.id)

        db.commit()

        logger.info(
            "Pushed %d URLA tasks to CRM",
            len(created_ids),
            extra={"loan_id": loan_id, "user_id": current_user.id},
        )

        return PushTasksResponse(
            loan_id=loan_id,
            tasks_created=len(created_ids),
            task_ids=created_ids,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(
            "Failed to push URLA tasks to CRM",
            extra={"loan_id": loan_id},
        )
        raise HTTPException(status_code=500, detail="Failed to create CRM tasks")
    finally:
        await state.close()


def _get_borrower_name(app) -> Optional[str]:
    """Extract the primary borrower's name from a URLAApplication."""
    primary = app.primary_borrower()
    if primary and primary.section_1a:
        first = primary.section_1a.first_name or ""
        last = primary.section_1a.last_name or ""
        name = f"{first} {last}".strip()
        return name or None
    return None


# ---------------------------------------------------------------------------
# 8. GET /analytics
# ---------------------------------------------------------------------------

@router.get("/analytics", response_model=AnalyticsResponse)
async def get_urla_analytics(
    start_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD)"),
    current_user=Depends(get_current_user),
):
    """Return aggregate URLA analytics for the tenant.

    Defaults to the last 30 days if no date range is provided.
    """
    tenant_id = _get_tenant_id(current_user)

    now = datetime.now(timezone.utc)
    try:
        period_end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) if end_date else now
        period_start = (
            datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            if start_date
            else period_end - timedelta(days=30)
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use ISO 8601 (YYYY-MM-DD).",
        )

    if _HAS_ANALYTICS:
        analytics_data = await compute_analytics(
            tenant_id=tenant_id,
            start_date=period_start,
            end_date=period_end,
        )
        return AnalyticsResponse(
            tenant_id=tenant_id,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            analytics=analytics_data,
        )

    # Fallback: scan Redis for basic stats when the analytics module is
    # not available.  This is intentionally lightweight.
    state = await _get_state_manager()
    try:
        analytics = await _compute_basic_analytics(state, tenant_id, period_start, period_end)
        return AnalyticsResponse(
            tenant_id=tenant_id,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            analytics=analytics,
        )
    finally:
        await state.close()


async def _compute_basic_analytics(
    state: URLAStateManager,
    tenant_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """Compute basic analytics by scanning URLA keys in Redis.

    This is a best-effort fallback. The dedicated call_analytics module
    should be used for production analytics once available.
    """
    cursor = "0"
    pattern = f"urla:{tenant_id}:loan:*"
    total = 0
    finalized = 0
    in_progress = 0
    avg_completion = 0.0

    try:
        while True:
            cursor, keys = await state.redis.scan(
                cursor=int(cursor), match=pattern, count=100
            )
            for key in keys:
                raw = await state.redis.get(key)
                if raw is None:
                    continue
                try:
                    # Try to decrypt (handles both encrypted and plaintext)
                    cipher = state._get_cipher()
                    if cipher and raw:
                        try:
                            raw = cipher.decrypt(raw.encode()).decode()
                        except Exception:
                            pass
                    from agents.urla.models import URLAApplication
                    app = URLAApplication.model_validate_json(raw)

                    # Filter by date range
                    if app.created_at < start_date or app.created_at > end_date:
                        continue

                    total += 1
                    completed_pct = (len(app.completed_sections) / 9) * 100
                    avg_completion += completed_pct

                    if app.is_finalized:
                        finalized += 1
                    elif app.current_section not in ("COMPLETE",):
                        in_progress += 1
                except Exception as e:
                    logger.debug("Skipping unparseable URLA record: %s", e)
                    continue

            if cursor == 0:
                break
    except Exception as e:
        logger.warning("Error scanning Redis for URLA analytics: %s", e)

    return {
        "total_applications": total,
        "finalized": finalized,
        "in_progress": in_progress,
        "abandoned": total - finalized - in_progress,
        "average_completion_percent": round(avg_completion / total, 1) if total else 0.0,
        "finalization_rate_percent": round((finalized / total) * 100, 1) if total else 0.0,
        "note": "Basic analytics (call_analytics module not installed)",
    }


# ---------------------------------------------------------------------------
# 9. GET /sessions
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=SessionsResponse)
async def list_urla_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(
        None,
        description="Filter by status: all, completed, in_progress, abandoned, finalized",
    ),
    current_user=Depends(get_current_user),
):
    """List recent URLA sessions for the tenant."""
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        cursor_pos = "0"
        pattern = f"urla:{tenant_id}:loan:*"
        all_sessions: List[SessionSummary] = []

        while True:
            cursor_pos, keys = await state.redis.scan(
                cursor=int(cursor_pos), match=pattern, count=200
            )
            for key in keys:
                raw = await state.redis.get(key)
                if raw is None:
                    continue
                try:
                    cipher = state._get_cipher()
                    if cipher and raw:
                        try:
                            raw = cipher.decrypt(raw.encode()).decode()
                        except Exception:
                            pass

                    from agents.urla.models import URLAApplication
                    app = URLAApplication.model_validate_json(raw)

                    # Apply status filter
                    if status and status != "all":
                        if status == "completed" and app.current_section != "COMPLETE":
                            continue
                        elif status == "finalized" and not app.is_finalized:
                            continue
                        elif status == "in_progress" and (
                            app.is_finalized or app.current_section == "COMPLETE"
                        ):
                            continue
                        elif status == "abandoned" and (
                            app.is_finalized
                            or app.current_section == "COMPLETE"
                            or not app.current_section.startswith("PAUSED:")
                        ):
                            # Heuristic: abandoned = paused and not finalized
                            # This is imperfect; the analytics module can
                            # use timeout-based detection.
                            continue

                    progress = app.progress_summary()
                    all_sessions.append(
                        SessionSummary(
                            loan_id=app.loan_id,
                            current_section=app.current_section,
                            completed_sections=app.completed_sections,
                            is_finalized=app.is_finalized,
                            created_at=app.created_at.isoformat(),
                            updated_at=app.updated_at.isoformat(),
                            percent_complete=progress["percent_complete"],
                            borrower_name=progress.get("borrower_name"),
                        )
                    )
                except Exception as e:
                    logger.debug("Skipping unparseable URLA record: %s", e)
                    continue

            if cursor_pos == 0:
                break

        # Sort by created_at descending (most recent first)
        all_sessions.sort(key=lambda s: s.created_at, reverse=True)
        total = len(all_sessions)
        paginated = all_sessions[offset : offset + limit]

        return SessionsResponse(sessions=paginated, total=total)
    finally:
        await state.close()


# ---------------------------------------------------------------------------
# 10. GET /calls/{loan_id}/transcript
# ---------------------------------------------------------------------------

@router.get("/calls/{loan_id}/transcript", response_model=TranscriptResponse)
async def get_call_transcript(
    loan_id: str,
    current_user=Depends(get_current_user),
):
    """Return the call transcript for a URLA application."""
    tenant_id = _get_tenant_id(current_user)
    state = await _get_state_manager()
    try:
        app = await _load_app(state, tenant_id, loan_id)

        entries = [
            TranscriptEntry(
                speaker=entry.speaker,
                text=entry.text,
                timestamp=entry.timestamp.isoformat() if entry.timestamp else None,
            )
            for entry in (app.transcript or [])
        ]

        return TranscriptResponse(
            loan_id=loan_id,
            transcript=entries,
            entry_count=len(entries),
        )
    finally:
        await state.close()
