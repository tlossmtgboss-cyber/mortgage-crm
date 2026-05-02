"""
FastAPI router for team chat — wired under /api/v1/clients/{id}/team-chat.
Adapted from the lo_surface package for Perennia's import conventions.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db


def get_current_user_dep():
    from auth.dependencies import get_current_user
    return get_current_user


def get_redis():
    from services.redis_service import get_redis_client
    return get_redis_client()


def _get_models():
    from database.models.team_chat import TeamChatReactionEmoji
    return TeamChatReactionEmoji


def _get_service():
    from services.team_chat import TeamChatService
    return TeamChatService


router = APIRouter(tags=["team-chat"])


# ─────────────────────────────────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────────────────────────────────


class _Attachment(BaseModel):
    kind: str = Field(..., pattern="^document_upload$")
    document_upload_id: uuid.UUID


class SendMessageBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)
    mentioned_user_ids: list[int] = Field(default_factory=list)
    attachments: list[_Attachment] = Field(default_factory=list)


class EditMessageBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)


class ReactBody(BaseModel):
    emoji: Any  # TeamChatReactionEmoji loaded lazily


class MarkReadBody(BaseModel):
    last_read_message_id: uuid.UUID


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _svc(db: Session, redis: Any) -> Any:
    TeamChatService = _get_service()
    return TeamChatService(db, redis=redis)


def _own_message_or_403(svc: Any, message_id: uuid.UUID, user_id: int) -> None:
    from database.models.team_chat import TeamChatMessage
    msg = svc.session.get(TeamChatMessage, message_id)
    if msg is None:
        raise HTTPException(404, "message not found")
    if msg.author_user_id != user_id:
        raise HTTPException(403, "not your message")


# ─────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────


@router.get("/clients/{client_file_id}/team-chat/messages")
def list_messages(
    client_file_id: uuid.UUID,
    before: Optional[datetime] = Query(None),
    limit: int = Query(80, ge=1, le=200),
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> list[dict]:
    svc = _svc(db, redis)
    try:
        return svc.list_messages(
            org_id=user.organization_id,
            client_file_id=client_file_id,
            actor_user_id=user.id,
            before=before,
            limit=limit,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.post(
    "/clients/{client_file_id}/team-chat/messages",
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    client_file_id: uuid.UUID,
    body: SendMessageBody,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> dict:
    svc = _svc(db, redis)
    try:
        msg = svc.post_human_message(
            org_id=user.organization_id,
            client_file_id=client_file_id,
            author_user_id=user.id,
            body=body.body,
            mentioned_user_ids=body.mentioned_user_ids,
            attachments=[a.model_dump() for a in body.attachments],
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return svc._serialize_message(
        msg, actor_user_id=user.id, reactions_by_emoji={}, users_by_id={}
    )


@router.patch("/clients/{client_file_id}/team-chat/messages/{message_id}")
def edit_message(
    client_file_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: EditMessageBody,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> dict:
    svc = _svc(db, redis)
    try:
        msg = svc.edit_message(
            message_id=message_id,
            actor_user_id=user.id,
            body=payload.body,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    db.commit()
    return svc._serialize_message(
        msg, actor_user_id=user.id, reactions_by_emoji={}, users_by_id={}
    )


@router.delete(
    "/clients/{client_file_id}/team-chat/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_message(
    client_file_id: uuid.UUID,
    message_id: uuid.UUID,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> None:
    svc = _svc(db, redis)
    try:
        svc.delete_message(message_id=message_id, actor_user_id=user.id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    db.commit()


@router.post("/clients/{client_file_id}/team-chat/messages/{message_id}/pin")
def pin_message(
    client_file_id: uuid.UUID,
    message_id: uuid.UUID,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> dict:
    svc = _svc(db, redis)
    msg = svc.pin(message_id=message_id)
    db.commit()
    return svc._serialize_message(
        msg, actor_user_id=user.id, reactions_by_emoji={}, users_by_id={}
    )


@router.post("/clients/{client_file_id}/team-chat/messages/{message_id}/unpin")
def unpin_message(
    client_file_id: uuid.UUID,
    message_id: uuid.UUID,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> dict:
    svc = _svc(db, redis)
    msg = svc.unpin(message_id=message_id)
    db.commit()
    return svc._serialize_message(
        msg, actor_user_id=user.id, reactions_by_emoji={}, users_by_id={}
    )


@router.get("/clients/{client_file_id}/team-chat/pinned")
def get_pinned(
    client_file_id: uuid.UUID,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> Optional[dict]:
    svc = _svc(db, redis)
    return svc.get_pinned(
        org_id=user.organization_id,
        client_file_id=client_file_id,
        actor_user_id=user.id,
    )


@router.post(
    "/clients/{client_file_id}/team-chat/messages/{message_id}/reactions",
    status_code=status.HTTP_201_CREATED,
)
def react(
    client_file_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ReactBody,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> dict:
    svc = _svc(db, redis)
    r = svc.react(
        message_id=message_id,
        user_id=user.id,
        emoji=payload.emoji,
        org_id=user.organization_id,
    )
    db.commit()
    return {
        "id": str(r.id),
        "message_id": str(r.message_id),
        "user_id": str(r.user_id),
        "emoji": r.emoji.value,
    }


@router.delete(
    "/clients/{client_file_id}/team-chat/messages/{message_id}/reactions/{emoji}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unreact(
    client_file_id: uuid.UUID,
    message_id: uuid.UUID,
    emoji: str,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> None:
    TeamChatReactionEmoji = _get_models()
    svc = _svc(db, redis)
    svc.unreact(message_id=message_id, user_id=user.id, emoji=TeamChatReactionEmoji(emoji))
    db.commit()


@router.get("/clients/{client_file_id}/team-chat/members")
def list_members(
    client_file_id: uuid.UUID,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> list[dict]:
    svc = _svc(db, redis)
    return svc.list_members(org_id=user.organization_id, client_file_id=client_file_id)


@router.post("/clients/{client_file_id}/team-chat/read")
def mark_read(
    client_file_id: uuid.UUID,
    payload: MarkReadBody,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> dict:
    svc = _svc(db, redis)
    result = svc.mark_read(
        org_id=user.organization_id,
        client_file_id=client_file_id,
        user_id=user.id,
        last_read_message_id=payload.last_read_message_id,
    )
    db.commit()
    return result


@router.get("/clients/{client_file_id}/team-chat/unread")
def unread_count(
    client_file_id: uuid.UUID,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> dict:
    svc = _svc(db, redis)
    return svc.unread_count(
        org_id=user.organization_id,
        client_file_id=client_file_id,
        user_id=user.id,
    )


@router.post(
    "/clients/{client_file_id}/team-chat/typing",
    status_code=status.HTTP_204_NO_CONTENT,
)
def set_typing(
    client_file_id: uuid.UUID,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> None:
    svc = _svc(db, redis)
    svc.set_typing(
        org_id=user.organization_id, client_file_id=client_file_id, user_id=user.id
    )


@router.get("/clients/{client_file_id}/team-chat/typing")
def get_typing(
    client_file_id: uuid.UUID,
    user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> dict:
    svc = _svc(db, redis)
    return svc.get_typing(
        org_id=user.organization_id, client_file_id=client_file_id
    )
