"""
FastAPI routers for the iMessage system.

Two routers:
  api_router      — authenticated user-facing endpoints  (mount at /api/imessage)
  webhook_router  — public BlueBubbles webhook receiver   (mount at /webhooks/imessage)
"""
from __future__ import annotations

import hmac
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

# === Perennia auth + DB wiring ========================================
from database import get_db as get_db_session
from auth.dependencies import get_current_user_flexible as get_current_user

# Perennia's auth returns a user object (dict-like); alias for clarity.
CurrentUser = Any


def require_role(*_roles: str):
    """No-op dependency stub. Perennia RBAC is enforced at the middleware /
    permission layer, not via per-route DI. Kept so existing
    ``dependencies=[Depends(require_role(...))]`` decorators don't break."""
    async def _noop():
        pass
    return _noop
# =====================================================================

from .config import get_imessage_settings
from .factory import build_imessage_service, get_line_for_webhook
from .models import IMessageLine
from .schemas import (
    BBWebhookEvent,
    ConversationThread,
    IMessageDetectionResult,
    SendMessageRequest,
    SendMessageResponse,
    TapbackRequest,
    ConversationMessage,
)
from .service import IMessageService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DI helpers
# ---------------------------------------------------------------------------
def get_service() -> IMessageService:
    return build_imessage_service()


SvcDep = Annotated[IMessageService, Depends(get_service)]
DbDep = Annotated[Session, Depends(get_db_session)]
UserDep = Annotated[CurrentUser, Depends(get_current_user)]


# ===========================================================================
# Authenticated API router
# ===========================================================================
api_router = APIRouter(prefix="/api/imessage", tags=["imessage"])


@api_router.post(
    "/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("loan_officer", "processor", "admin", "ai_agent"))],
)
async def send_message(
    payload: SendMessageRequest,
    user: UserDep,
    db: DbDep,
    svc: SvcDep,
) -> SendMessageResponse:
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    try:
        return await svc.send(
            db,
            organization_id=org_id,
            seat_user_id=user.id,
            request=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.post(
    "/tapbacks",
    response_model=ConversationMessage,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("loan_officer", "processor", "admin"))],
)
async def send_tapback(
    payload: TapbackRequest,
    user: UserDep,
    db: DbDep,
    svc: SvcDep,
) -> ConversationMessage:
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    try:
        return await svc.send_tapback(
            db, organization_id=org_id, seat_user_id=user.id, request=payload
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.get(
    "/contacts/{contact_id}/thread",
    response_model=ConversationThread,
)
async def get_thread(
    contact_id: int,
    user: UserDep,
    db: DbDep,
    svc: SvcDep,
    limit: int = 200,
) -> ConversationThread:
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    try:
        return await svc.get_thread(
            db, organization_id=org_id, contact_id=contact_id, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class DetectRequest(BaseModel):
    handle: str
    force: bool = False
    line_id: UUID | None = None


@api_router.post(
    "/detect-imessage",
    response_model=IMessageDetectionResult,
    dependencies=[Depends(require_role("loan_officer", "processor", "admin", "ai_agent"))],
)
async def detect_imessage(
    payload: DetectRequest,
    user: UserDep,
    db: DbDep,
    svc: SvcDep,
) -> IMessageDetectionResult:
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    return await svc.detect_imessage(
        db,
        organization_id=org_id,
        handle=payload.handle,
        force=payload.force,
        line_id=payload.line_id,
    )


class TypingRequest(BaseModel):
    contact_id: UUID
    on: bool = True


@api_router.post(
    "/typing",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("loan_officer", "processor", "admin"))],
)
async def typing(
    payload: TypingRequest,
    user: UserDep,
    db: DbDep,
    svc: SvcDep,
) -> None:
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    thread = await svc.get_thread(db, organization_id=org_id, contact_id=payload.contact_id)
    if not thread.chat_guid:
        # No prior chat — typing is a no-op until first send establishes guid
        return
    line = db.execute(select(IMessageLine).where(IMessageLine.id == thread.line_id)).scalar_one_or_none()
    if line is None:
        raise HTTPException(status_code=404, detail="line not found")
    client = svc._client_for(line)  # ok for typing — no DB write
    if payload.on:
        await client.start_typing(thread.chat_guid)
    else:
        await client.stop_typing(thread.chat_guid)


# ---- Lines management (admin-only) ---------------------------------------
class LineListItem(BaseModel):
    id: UUID
    label: str
    handle: str
    enabled: bool
    last_ping_at: str | None
    last_ping_status: str | None


@api_router.get(
    "/lines",
    response_model=list[LineListItem],
    dependencies=[Depends(require_role("admin"))],
)
async def list_lines(user: UserDep, db: DbDep) -> list[LineListItem]:
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    rows = db.scalars(
        select(IMessageLine).where(IMessageLine.organization_id == org_id)
    ).all()
    return [
        LineListItem(
            id=r.id,
            label=r.label,
            handle=r.handle,
            enabled=r.enabled,
            last_ping_at=r.last_ping_at.isoformat() if r.last_ping_at else None,
            last_ping_status=r.last_ping_status,
        )
        for r in rows
    ]


# ===========================================================================
# Public webhook router
# ===========================================================================
webhook_router = APIRouter(prefix="/webhooks/imessage", tags=["imessage-webhooks"])


@webhook_router.post(
    "/{token}/{line_id}",
    status_code=status.HTTP_200_OK,
)
async def receive_webhook(
    request: Request,
    db: DbDep,
    svc: SvcDep,
    token: str = Path(...),
    line_id: UUID = Path(...),
) -> dict:
    """
    BlueBubbles POSTs every subscribed event here.

    Auth strategy:
      - Path token must match IMESSAGE_WEBHOOK_URL_SECRET (rotates per deploy).
      - line_id is required and must exist + be enabled. We only run
        side-effects against that line's tenant.
      - Cloudflare Access in front of /webhooks/imessage/* is recommended
        with an inbound-only policy that requires a CF-Access-Client-Id
        configured into the BB webhook config.
    """
    settings = get_imessage_settings()
    if not hmac.compare_digest(token, settings.webhook_url_secret):
        # Don't 401 — that gives an oracle. Treat as 200 + no-op to keep
        # BB's retry queue healthy and return immediately.
        logger.warning("imessage.webhook.bad_token")
        return {"ok": False}

    line = get_line_for_webhook(db, line_id=line_id)
    if line is None or not line.enabled:
        logger.warning("imessage.webhook.unknown_line", extra={"line_id": str(line_id)})
        return {"ok": False}

    body = await request.json()
    try:
        event = BBWebhookEvent.model_validate(body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("imessage.webhook.unparseable", extra={"err": str(exc)})
        return {"ok": False}

    try:
        await svc.ingest_event(db, line=line, event=event, raw_body=body)
    except Exception:
        logger.exception("imessage.webhook.ingest_failed", extra={"line_id": str(line_id), "type": event.type})
        return {"ok": False}
    return {"ok": True}


@webhook_router.post(
    "/{token}/{line_id}/heartbeat",
    status_code=status.HTTP_200_OK,
)
async def heartbeat(
    db: DbDep,
    token: str = Path(...),
    line_id: UUID = Path(...),
) -> dict:
    """Mac-side cron POSTs here with its self-ping result every 60s."""
    settings = get_imessage_settings()
    if not hmac.compare_digest(token, settings.webhook_url_secret):
        return {"ok": False}
    line = get_line_for_webhook(db, line_id=line_id)
    if line is None:
        return {"ok": False}
    from datetime import datetime, timezone
    line.last_ping_at = datetime.now(timezone.utc)
    line.last_ping_status = "ok"
    db.flush()
    return {"ok": True}
