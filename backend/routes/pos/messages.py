"""Borrower-facing message routes for the POS portal.

Messages are sent from the lending team (LO, processor, UW) and displayed
in the borrower's portal inbox. Borrowers can read messages and mark them
read, but cannot compose new messages from this endpoint (replies go through
the CRM-side team chat).

Auth: PURL token — borrower must own the application.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from database import get_db
from database.models.pos import POSApplication, POSBorrowerMessage
from middleware.purl_auth import check_purl_rate_limit

from ._helpers import (
    resolve_application_for_borrower,
    resolve_application_for_borrower_write,
)

logger = logging.getLogger("pos.messages.routes")

router = APIRouter(
    prefix="/api/v1/pos/applications",
    tags=["POS - Messages"],
    dependencies=[Depends(check_purl_rate_limit)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BorrowerMessageResponse(BaseModel):
    id: int
    sender_name: str
    sender_role: str
    content: str
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BorrowerMessageCounts(BaseModel):
    total: int = 0
    unread: int = 0


class BorrowerMessageListResponse(BaseModel):
    application_id: str
    messages: list[BorrowerMessageResponse]
    counts: BorrowerMessageCounts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg_to_response(msg: POSBorrowerMessage) -> BorrowerMessageResponse:
    return BorrowerMessageResponse(
        id=msg.id,
        sender_name=msg.sender_name,
        sender_role=msg.sender_role or "Loan Officer",
        content=msg.content,
        is_read=msg.read_at is not None,
        created_at=msg.created_at,
        read_at=msg.read_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/messages",
    response_model=BorrowerMessageListResponse,
    summary="List messages for this application",
)
def list_messages(
    application: POSApplication = Depends(resolve_application_for_borrower),
    db: Session = Depends(get_db),
) -> BorrowerMessageListResponse:
    app_id = str(application.id)

    messages = (
        db.query(POSBorrowerMessage)
        .filter(POSBorrowerMessage.application_id == application.id)
        .order_by(POSBorrowerMessage.created_at.desc())
        .all()
    )

    total = len(messages)
    unread = sum(1 for m in messages if m.read_at is None)

    return BorrowerMessageListResponse(
        application_id=app_id,
        messages=[_msg_to_response(m) for m in messages],
        counts=BorrowerMessageCounts(total=total, unread=unread),
    )


@router.patch(
    "/{application_id}/messages/{message_id}/read",
    response_model=BorrowerMessageResponse,
    summary="Mark a message as read",
)
def mark_message_read(
    message_id: int,
    application: POSApplication = Depends(resolve_application_for_borrower_write),
    db: Session = Depends(get_db),
) -> BorrowerMessageResponse:
    msg = (
        db.query(POSBorrowerMessage)
        .filter(
            POSBorrowerMessage.id == message_id,
            POSBorrowerMessage.application_id == application.id,
        )
        .first()
    )

    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    if msg.read_at is None:
        msg.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(msg)

    return _msg_to_response(msg)


@router.patch(
    "/{application_id}/messages/read-all",
    response_model=BorrowerMessageListResponse,
    summary="Mark all messages as read",
)
def mark_all_read(
    application: POSApplication = Depends(resolve_application_for_borrower_write),
    db: Session = Depends(get_db),
) -> BorrowerMessageListResponse:
    app_id = str(application.id)
    now = datetime.now(timezone.utc)

    db.query(POSBorrowerMessage).filter(
        POSBorrowerMessage.application_id == application.id,
        POSBorrowerMessage.read_at.is_(None),
    ).update({"read_at": now}, synchronize_session="fetch")
    db.commit()

    messages = (
        db.query(POSBorrowerMessage)
        .filter(POSBorrowerMessage.application_id == application.id)
        .order_by(POSBorrowerMessage.created_at.desc())
        .all()
    )

    return BorrowerMessageListResponse(
        application_id=app_id,
        messages=[_msg_to_response(m) for m in messages],
        counts=BorrowerMessageCounts(total=len(messages), unread=0),
    )
