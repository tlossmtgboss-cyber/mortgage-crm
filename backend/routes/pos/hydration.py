"""
POS Hydration Routes
====================
Machine-to-machine endpoint for the URLA voice agent to push collected
application data into POS PostgreSQL tables.

Auth: CRM_API_KEY as Bearer token (same pattern as voice-complete).
CSRF exempt via the Bearer token bypass in csrf_protection middleware.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from database.models import Organization
from database.models.pos import POSApplication
from services.pos.urla_hydration_service import URLAHydrationService
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select


logger = logging.getLogger("pos.hydration.routes")

router = APIRouter(
    prefix="/api/v1/pos",
    tags=["POS - Hydration"],
)


# ---------------------------------------------------------------------------
# Auth — API key check for machine-to-machine calls
# ---------------------------------------------------------------------------

def _verify_crm_api_key(authorization: str = Header(...)) -> None:
    """
    Verify the CRM_API_KEY from the Authorization header.

    The URLA voice agent sends: Authorization: Bearer <CRM_API_KEY>
    This matches the pattern used by the voice-complete endpoint.
    """
    expected_key = os.getenv("CRM_API_KEY", "")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hydration endpoint not configured (CRM_API_KEY missing)",
        )

    # Parse "Bearer <token>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    import secrets
    if not secrets.compare_digest(parts[1], expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class HydrateFromVoiceRequest(BaseModel):
    """Request body for POST /api/v1/pos/hydrate-from-voice."""
    urla_loan_id: str = Field(
        ...,
        description="URLA loan_id from the voice agent's Redis state (e.g. URLA-ABC12345)",
    )
    urla_data: dict[str, Any] = Field(
        ...,
        description="Full URLAApplication.model_dump() payload",
    )
    organization_id: int
    workspace_id: int
    contact_id: int = Field(
        ...,
        description="Lead/Contact ID in the CRM",
    )
    loan_id: Optional[int] = Field(
        default=None,
        description="CRM loan ID to link, if available",
    )


class HydrateFromVoiceResponse(BaseModel):
    """Response body for POST /api/v1/pos/hydrate-from-voice."""
    status: str
    pos_application_id: str
    sections_hydrated: int
    completion_pct: int
    message: str
    deduplicated: bool = False


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/hydrate-from-voice",
    response_model=HydrateFromVoiceResponse,
    summary="Hydrate POS tables from URLA voice agent data",
    description=(
        "Called by the URLA voice agent after finalization. Maps the "
        "URLAApplication data into pos_applications, pos_application_sections, "
        "and pos_application_pii so the borrower can see their data in the "
        "self-service portal."
    ),
)
def hydrate_from_voice(
    body: HydrateFromVoiceRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _auth: None = Depends(_verify_crm_api_key),
) -> HydrateFromVoiceResponse:
    # ------------------------------------------------------------------
    # C2 FIX: Validate organization_id exists (prevent forged org injection)
    # ------------------------------------------------------------------
    org = db.query(Organization).filter(Organization.id == body.organization_id).first()
    if not org:
        raise HTTPException(status_code=400, detail="Invalid organization_id")

    source_ip = request.client.host if request.client else "unknown"
    logger.info(
        "Hydration request received",
        extra={
            "organization_id": body.organization_id,
            "source_ip": source_ip,
            "urla_loan_id": body.urla_loan_id,
            "contact_id": body.contact_id,
        },
    )

    # ------------------------------------------------------------------
    # H1 FIX: Idempotency — check for existing application by source_channel
    # ------------------------------------------------------------------
    voice_source_channel = f"voice:{body.urla_loan_id}"
    existing = db.query(POSApplication).filter(
        POSApplication.source_channel == voice_source_channel,
    ).first()
    if existing:
        logger.info(
            "Duplicate hydration request — returning existing application",
            extra={
                "pos_application_id": str(existing.id),
                "urla_loan_id": body.urla_loan_id,
                "source_ip": source_ip,
            },
        )
        sections_hydrated = len([s for s in existing.sections if s.data])
        return HydrateFromVoiceResponse(
            status="ok",
            pos_application_id=str(existing.id),
            sections_hydrated=sections_hydrated,
            completion_pct=existing.completion_pct,
            message=f"Existing application for URLA {body.urla_loan_id}",
            deduplicated=True,
        )

    service = URLAHydrationService()

    try:
        app = service.hydrate_from_urla(
            session=db,
            urla_data=body.urla_data,
            organization_id=body.organization_id,
            workspace_id=body.workspace_id,
            contact_id=body.contact_id,
            loan_id=body.loan_id,
            urla_loan_id=body.urla_loan_id,
        )
        db.commit()
        db.refresh(app)

        sections_hydrated = len([s for s in app.sections if s.data])

        logger.info(
            "POS hydration complete",
            extra={
                "pos_application_id": str(app.id),
                "urla_loan_id": body.urla_loan_id,
                "contact_id": body.contact_id,
                "sections": sections_hydrated,
                "source_ip": source_ip,
            },
        )

        return HydrateFromVoiceResponse(
            status="ok",
            pos_application_id=str(app.id),
            sections_hydrated=sections_hydrated,
            completion_pct=app.completion_pct,
            message=f"Hydrated {sections_hydrated} sections from URLA {body.urla_loan_id}",
        )

    # ------------------------------------------------------------------
    # M2 FIX: Suppress internal details in 500 responses
    # ------------------------------------------------------------------
    except Exception as e:
        logger.exception(
            "POS hydration failed",
            extra={
                "urla_loan_id": body.urla_loan_id,
                "contact_id": body.contact_id,
                "source_ip": source_ip,
            },
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Application hydration failed. Check server logs.",
        ) from e
