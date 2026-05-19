"""
Unified Timeline Routes (Domain 2 — Unified Communications)

Provides a single chronological timeline view of all communications
(SMS, email, calls, notes, system events) for a loan file.

Endpoints:
    GET  /api/v1/files/{file_id}/timeline          — Paginated, filterable timeline
    POST /api/v1/files/{file_id}/timeline/mark-read — Mark all messages read for current user
    GET  /api/v1/files/{file_id}/timeline/unread-count — Unread count for current user
    POST /api/v1/files/{file_id}/timeline/draft     — Trigger AI draft for inbound message

Usage:
    from routes.unified_timeline_routes import register_unified_timeline_routes
    register_unified_timeline_routes(app)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging

from db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)
security = HTTPBearer()


# ---------------------------------------------------------------------------
# Lazy auth import (avoids circular imports)
# ---------------------------------------------------------------------------

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TimelineEntry(BaseModel):
    """Single entry in the unified timeline."""
    id: int
    file_id: int
    direction: str
    channel: str
    body: str
    html_body: Optional[str] = None
    subject: Optional[str] = None
    from_party: str
    to_party: str
    sender_user_id: Optional[int] = None
    ai_summary: Optional[str] = None
    ai_draft_response: Optional[str] = None
    ai_draft_status: Optional[str] = None
    source_id: Optional[str] = None
    source_table: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    read_by: Optional[List[int]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TimelinePage(BaseModel):
    """Paginated timeline response."""
    items: List[TimelineEntry]
    total: int
    page: int
    page_size: int
    has_more: bool


class UnreadCountResponse(BaseModel):
    """Unread message count."""
    file_id: int
    unread_count: int


class MarkReadResponse(BaseModel):
    """Result of marking messages read."""
    file_id: int
    marked_count: int


class DraftRequest(BaseModel):
    """Request body for triggering an AI draft."""
    message_id: int = Field(..., description="ID of the inbound FileCommunication to draft a reply for")


class DraftResponse(BaseModel):
    """AI-generated draft result."""
    message_id: int
    suggested_reply: str
    confidence_score: float
    tone_analysis: str
    ai_draft_status: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/v1/files",
    tags=["unified-timeline"],
    dependencies=[Depends(_get_current_user())],
)


# ---------------------------------------------------------------------------
# GET /api/v1/files/{file_id}/timeline
# ---------------------------------------------------------------------------

@router.get("/{file_id}/timeline", response_model=TimelinePage)
async def get_file_timeline(
    file_id: int,
    channel: Optional[str] = Query(None, description="Filter by channel: sms, email, call, note, system"),
    direction: Optional[str] = Query(None, description="Filter by direction: inbound, outbound"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_get_current_user()),
):
    """Return all communications for a loan file in reverse-chronological order.

    Merges SMS, email, calls, notes, and system events from the
    ``file_communications`` table. Supports channel and direction filters.
    """
    from database.models.file_communication import FileCommunication

    # Base query — tenant isolation enforced by RLS in get_db
    query = db.query(FileCommunication).filter(
        FileCommunication.file_id == file_id,
        FileCommunication.organization_id == current_user.organization_id,
    )

    # Optional filters
    if channel:
        query = query.filter(FileCommunication.channel == channel.lower())
    if direction:
        query = query.filter(FileCommunication.direction == direction.lower())

    # Total before pagination
    total = query.count()

    # Paginate (newest first)
    offset = (page - 1) * page_size
    items = (
        query
        .order_by(desc(FileCommunication.created_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return TimelinePage(
        items=[TimelineEntry.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/files/{file_id}/timeline/mark-read
# ---------------------------------------------------------------------------

@router.post("/{file_id}/timeline/mark-read", response_model=MarkReadResponse)
async def mark_timeline_read(
    file_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_get_current_user()),
):
    """Mark every unread message in this file as read by the current user.

    Appends ``current_user.id`` to the ``read_by`` JSON array on each
    ``FileCommunication`` row that the user has not yet read.
    """
    from database.models.file_communication import FileCommunication

    user_id = current_user.id

    unread = (
        db.query(FileCommunication)
        .filter(
            FileCommunication.file_id == file_id,
            FileCommunication.organization_id == current_user.organization_id,
        )
        .all()
    )

    marked = 0
    for comm in unread:
        readers = comm.read_by or []
        if user_id not in readers:
            readers.append(user_id)
            comm.read_by = readers
            marked += 1

    if marked:
        # Also update the participant's last_read_at
        from database.models.file_communication import CommunicationParticipant

        participant = (
            db.query(CommunicationParticipant)
            .filter(
                CommunicationParticipant.file_id == file_id,
                CommunicationParticipant.user_id == user_id,
                CommunicationParticipant.organization_id == current_user.organization_id,
            )
            .first()
        )
        if participant:
            participant.last_read_at = datetime.now(timezone.utc)

        await db.commit()

    return MarkReadResponse(file_id=file_id, marked_count=marked)


# ---------------------------------------------------------------------------
# GET /api/v1/files/{file_id}/timeline/unread-count
# ---------------------------------------------------------------------------

@router.get("/{file_id}/timeline/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    file_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_get_current_user()),
):
    """Return the number of messages in this file not yet read by the current user."""
    from database.models.file_communication import FileCommunication

    user_id = current_user.id

    # Count rows where the user_id is NOT in the read_by JSON array.
    # PostgreSQL JSON containment is used when available; fallback to
    # loading all rows for SQLite / simple engines.
    all_comms = (
        db.query(FileCommunication)
        .filter(
            FileCommunication.file_id == file_id,
            FileCommunication.organization_id == current_user.organization_id,
        )
        .all()
    )

    unread = sum(1 for c in all_comms if user_id not in (c.read_by or []))

    return UnreadCountResponse(file_id=file_id, unread_count=unread)


# ---------------------------------------------------------------------------
# POST /api/v1/files/{file_id}/timeline/draft
# ---------------------------------------------------------------------------

@router.post("/{file_id}/timeline/draft", response_model=DraftResponse)
async def trigger_ai_draft(
    file_id: int,
    body: DraftRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_get_current_user()),
):
    """Trigger an AI draft reply for a specific inbound message.

    Returns the generated draft synchronously.  For automatic background
    drafting on inbound arrival, use the ``CommunicationDraftAgent`` service
    directly.
    """
    from database.models.file_communication import FileCommunication

    # Validate the message exists and belongs to this file/org
    comm = (
        db.query(FileCommunication)
        .filter(
            FileCommunication.id == body.message_id,
            FileCommunication.file_id == file_id,
            FileCommunication.organization_id == current_user.organization_id,
        )
        .first()
    )

    if not comm:
        raise HTTPException(status_code=404, detail="Message not found in this file")

    if comm.direction != "inbound":
        raise HTTPException(status_code=400, detail="AI drafts can only be generated for inbound messages")

    # Generate the draft via the CommunicationDraftAgent
    from services.communication_draft_agent import CommunicationDraftAgent

    agent = CommunicationDraftAgent()
    try:
        result = await agent.generate_draft(
            file_id=file_id,
            message_id=body.message_id,
            db=db,
        )
    except Exception as e:
        logger.exception("AI draft generation failed for message %s", body.message_id)
        raise HTTPException(status_code=500, detail="Draft generation failed") from e

    return DraftResponse(
        message_id=body.message_id,
        suggested_reply=result["suggested_reply"],
        confidence_score=result["confidence_score"],
        tone_analysis=result["tone_analysis"],
        ai_draft_status=result.get("ai_draft_status", "pending"),
    )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_unified_timeline_routes(app):
    """Register the unified timeline router on the FastAPI app."""
    app.include_router(router)
    logger.info("Registered unified timeline routes")
