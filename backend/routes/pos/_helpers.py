"""Shared helpers for POS routes.

Pattern matches the existing `backend/routes/scheduler/_helpers.py`:
  - One module per cross-cutting concern
  - Pure functions where possible
  - Auth context resolution lives here so it's easy to audit
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.purl_auth import (
    PURLAuthContext,
    require_purl_token,
    require_purl_write_scope,
)

from database.models.pos import POSApplication
from services.pos.application_service import (
    ApplicationNotFoundError,
    ApplicationService,
    AuditContext,
)


# ---------------------------------------------------------------------------
# Service singletons (FastAPI Depends)
# ---------------------------------------------------------------------------


def get_application_service() -> ApplicationService:
    return ApplicationService()


# ---------------------------------------------------------------------------
# Audit context (per-request)
# ---------------------------------------------------------------------------


def build_audit_context(
    request: Request,
    purl_ctx: PURLAuthContext = Depends(require_purl_token),
) -> AuditContext:
    """Stamp every borrower action with IP and User-Agent for compliance."""
    # M2 fix: Use request.client.host (set by reverse proxy) as authoritative
    # source. X-Forwarded-For is trivially spoofable and must not be used for
    # audit trail IP addresses. Matches the pattern in start.py:_client_ip().
    client = request.client
    ip = client.host if client else None
    return AuditContext(
        actor_type="borrower",
        actor_id=purl_ctx.contact_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )


# ---------------------------------------------------------------------------
# Application resolution (the hot path that prevents cross-borrower access)
# ---------------------------------------------------------------------------


def resolve_application_for_borrower(
    application_id: UUID,
    purl_ctx: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
) -> POSApplication:
    """Fetch an application or 404 — never reveal cross-borrower existence.

    Use this as a Depends() in any route that takes application_id in the path.
    """
    try:
        return service.get_for_borrower(
            db,
            application_id=application_id,
            contact_id=purl_ctx.contact_id,
        )
    except ApplicationNotFoundError as exc:
        # Intentional 404 (not 403) — a 403 leaks the fact that the
        # application exists. Borrowers should see "not found" whether the
        # row truly doesn't exist or belongs to a different contact.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        ) from exc


def resolve_application_for_borrower_write(
    application_id: UUID,
    purl_ctx: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
) -> POSApplication:
    """Same as `resolve_application_for_borrower` but requires WRITE scope."""
    try:
        return service.get_for_borrower(
            db,
            application_id=application_id,
            contact_id=purl_ctx.contact_id,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        ) from exc


def resolve_application_direct(
    application_id: UUID,
    *,
    purl_ctx: PURLAuthContext,
    db: Session,
) -> POSApplication:
    """Direct (non-Depends) application resolver for body-driven routes.

    Used by holds, bookings, and AI Q&A where the application_id comes from
    the request body rather than the URL path.
    """
    service = ApplicationService()
    try:
        return service.get_for_borrower(
            db,
            application_id=application_id,
            contact_id=purl_ctx.contact_id,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        ) from exc


# ---------------------------------------------------------------------------
# Name formatting
# ---------------------------------------------------------------------------


def full_name(first: str | None, last: str | None) -> str:
    """Best-effort display name from first/last parts.

    Used by calendar, team, and calendar_service to avoid duplicating
    the same formatting logic.
    """
    return f"{first or ''} {last or ''}".strip() or "Unknown"


# ---------------------------------------------------------------------------
# Section response shaping
# ---------------------------------------------------------------------------


def application_to_response_dict(application: POSApplication) -> dict:
    """Build the dict consumed by ApplicationResponse Pydantic model.

    Centralizes the "never expose raw PII" rule.
    """
    sections_complete = {
        s.section_key: s.is_complete for s in application.sections
    }
    pii = application.pii
    try:
        has_ssn = bool(pii and pii.ssn_encrypted)
        has_co_ssn = bool(pii and pii.co_ssn_encrypted)
        has_dob = bool(pii and (getattr(pii, "dob_encrypted", None) or getattr(pii, "dob", None)))
    except Exception:
        has_ssn = has_co_ssn = has_dob = False
    return {
        "id": application.id,
        "loan_id": application.loan_id,
        "status": application.status,
        "current_step": application.current_step,
        "completion_pct": application.completion_pct,
        "submitted_at": application.submitted_at,
        "submitted_appointment_id": application.submitted_appointment_id,
        "created_at": application.created_at,
        "updated_at": application.updated_at,
        "sections_complete": sections_complete,
        "has_ssn": has_ssn,
        "has_co_ssn": has_co_ssn,
        "has_dob": has_dob,
    }
