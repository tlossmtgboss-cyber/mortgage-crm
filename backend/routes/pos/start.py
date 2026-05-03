"""Public POS start endpoint — no auth required.

Creates a guest workspace + contact + PURL token so a new borrower can
begin an application without a magic link.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from models.purl import (
    ContactType,
    PURLContact,
    PURLWorkspace,
    TokenScope,
    WorkspaceStatus,
)
from services.purl_token_service import PURLTokenService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pos", tags=["POS - Public Start"])


class StartRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(None, max_length=20)


class StartResponse(BaseModel):
    token: str
    workspace_slug: str
    redirect_url: str


DEFAULT_ORG_ID = 1


@router.post(
    "/start",
    response_model=StartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new loan application (public, no auth)",
)
def start_application(
    body: StartRequest,
    db: Session = Depends(get_db),
):
    slug = f"{body.first_name.lower()}-{body.last_name.lower()}-{uuid.uuid4().hex[:8]}"
    display_name = f"{body.first_name} {body.last_name}"

    workspace = PURLWorkspace(
        organization_id=DEFAULT_ORG_ID,
        slug=slug,
        status=WorkspaceStatus.APPLICATION.value,
        display_name=display_name,
        source="pos_public_start",
        application_at=datetime.now(timezone.utc),
    )
    db.add(workspace)
    db.flush()

    contact = PURLContact(
        organization_id=DEFAULT_ORG_ID,
        workspace_id=workspace.id,
        contact_type=ContactType.BORROWER.value,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        phone=body.phone,
    )
    db.add(contact)
    db.flush()

    token_service = PURLTokenService(db)
    _token_id, full_token = token_service.create_token(
        organization_id=DEFAULT_ORG_ID,
        workspace_id=workspace.id,
        scope=TokenScope.WRITE,
        contact_id=contact.id,
        expires_in_days=90,
    )

    redirect_url = f"https://app.perenniaai.com/pos?token={full_token}"

    return StartResponse(
        token=full_token,
        workspace_slug=slug,
        redirect_url=redirect_url,
    )
