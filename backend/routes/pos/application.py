"""Borrower-facing application routes.

All endpoints require a PURL token. The application is auto-scoped to the
authenticated contact_id — no borrower can read or modify another's draft.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from database import get_db
from middleware.purl_auth import (
    PURLAuthContext,
    check_purl_rate_limit,
    require_purl_token,
    require_purl_write_scope,
)

from sqlalchemy import select
from database.models.pos import POSApplication, POSApplicationPII, POSSectionKey
from schemas.pos.application import (
    ApplicationResponse,
    ApplicationSubmitRequest,
    ApplicationSubmitResponse,
    SectionResponse,
    SectionUpdateRequest,
)
from services.pos.application_service import (
    ApplicationService,
    ApplicationStateError,
    AuditContext,
)

from ._helpers import (
    application_to_response_dict,
    build_audit_context,
    get_application_service,
    resolve_application_for_borrower,
    resolve_application_for_borrower_write,
)


router = APIRouter(
    prefix="/api/v1/pos/applications",
    tags=["POS - Application"],
    dependencies=[Depends(check_purl_rate_limit)],
)


# ---------------------------------------------------------------------------
# Start / fetch
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=ApplicationResponse,
    summary="Get the borrower's active application (creating one if needed)",
)
def get_or_start_my_application(
    loan_id: int | None = Query(None),
    source_channel: str | None = Query(None),
    purl_ctx: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    ctx: AuditContext = Depends(build_audit_context),
) -> ApplicationResponse:
    """Return the borrower's in-progress draft, creating one on first call."""
    application = service.get_or_create_for_loan(
        db,
        organization_id=purl_ctx.organization_id,
        workspace_id=purl_ctx.workspace_id,
        contact_id=purl_ctx.contact_id,
        loan_id=loan_id,
        source_channel=source_channel,
        ctx=ctx,
    )
    db.commit()
    application = db.execute(
        select(POSApplication)
        .where(POSApplication.id == application.id)
        .options(
            selectinload(POSApplication.sections),
            selectinload(POSApplication.pii),
        )
    ).scalar_one()

    return ApplicationResponse(**application_to_response_dict(application))


@router.get(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Fetch a specific application by ID",
)
def get_application(
    application: POSApplication = Depends(resolve_application_for_borrower),
) -> ApplicationResponse:
    return ApplicationResponse(**application_to_response_dict(application))


# ---------------------------------------------------------------------------
# Section CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/sections/{section_key}",
    response_model=SectionResponse,
    summary="Get a single section's data",
)
def get_section(
    section_key: str,
    application: POSApplication = Depends(resolve_application_for_borrower),
) -> SectionResponse:
    if section_key not in POSSectionKey.ALL_VALID:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown section")

    section = next(
        (s for s in application.sections if s.section_key == section_key),
        None,
    )
    pii_flags = _safe_pii_flags(application.pii)

    if section is None:
        return SectionResponse(
            section_key=section_key,  # type: ignore[arg-type]
            data={},
            is_complete=False,
            completed_at=None,
            updated_at=application.updated_at,
            **pii_flags,
        )

    return SectionResponse(
        section_key=section.section_key,  # type: ignore[arg-type]
        data=section.data or {},
        is_complete=section.is_complete,
        completed_at=section.completed_at,
        updated_at=section.updated_at,
        **pii_flags,
    )


@router.patch(
    "/{application_id}/sections/{section_key}",
    response_model=SectionResponse,
    summary="Upsert a section's data (autosave)",
)
def update_section(
    section_key: str,
    body: SectionUpdateRequest,
    application: POSApplication = Depends(resolve_application_for_borrower_write),
    db: Session = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    ctx: AuditContext = Depends(build_audit_context),
) -> SectionResponse:
    if section_key not in POSSectionKey.ALL_VALID:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown section")

    # Lift PII fields out of `data` if this is the personal section — they're
    # stored encrypted in pos_application_pii, never in the JSONB blob.
    pii_kwargs: dict = {}
    if section_key == POSSectionKey.PERSONAL:
        if body.ssn is not None:
            pii_kwargs["ssn"] = body.ssn
        if body.co_ssn is not None:
            pii_kwargs["co_ssn"] = body.co_ssn
        if body.dob is not None:
            pii_kwargs["dob"] = body.dob
        if body.co_dob is not None:
            pii_kwargs["co_dob"] = body.co_dob

    try:
        section = service.upsert_section(
            db,
            application=application,
            section_key=section_key,
            data=body.data,
            mark_complete=body.mark_complete,
            expected_updated_at=body.expected_updated_at,
            ctx=ctx,
        )
        if pii_kwargs:
            service.upsert_pii(db, application=application, **pii_kwargs)
    except ApplicationStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    db.refresh(application)

    pii_flags = _safe_pii_flags(application.pii)
    app_meta = ApplicationResponse(**application_to_response_dict(application))
    return SectionResponse(
        section_key=section.section_key,  # type: ignore[arg-type]
        data=section.data or {},
        is_complete=section.is_complete,
        completed_at=section.completed_at,
        updated_at=section.updated_at,
        **pii_flags,
        application=app_meta,
    )


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


@router.post(
    "/{application_id}/submit",
    response_model=ApplicationSubmitResponse,
    summary="Submit the application (transitions draft → submitted)",
)
async def submit_application(
    body: ApplicationSubmitRequest,
    application: POSApplication = Depends(resolve_application_for_borrower_write),
    db: Session = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    ctx: AuditContext = Depends(build_audit_context),
) -> ApplicationSubmitResponse:
    try:
        submitted = await service.submit(
            db,
            application=application,
            appointment_id=body.appointment_id,
            acknowledged_certifications=body.acknowledged_certifications,
            ctx=ctx,
        )
    except ApplicationStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    db.refresh(submitted)

    confirmation = _build_confirmation_number(submitted)
    next_steps = _next_steps_for_borrower(submitted)

    return ApplicationSubmitResponse(
        id=submitted.id,
        status=submitted.status,
        submitted_at=submitted.submitted_at or datetime.now(timezone.utc),
        submitted_appointment_id=submitted.submitted_appointment_id,
        confirmation_number=confirmation,
        next_steps=next_steps,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_pii_flags(pii) -> dict:
    """Extract PII presence flags without crashing on missing columns."""
    try:
        return {
            "has_ssn": bool(pii and pii.ssn_encrypted),
            "has_co_ssn": bool(pii and pii.co_ssn_encrypted),
            "has_dob": bool(pii and (getattr(pii, "dob_encrypted", None) or getattr(pii, "dob", None))),
        }
    except Exception:
        return {"has_ssn": False, "has_co_ssn": False, "has_dob": False}


def _build_confirmation_number(app: POSApplication) -> str:
    """Build a human-friendly confirmation number.

    Uses the loan_id when available (matches Perennia's existing PRN-YYYY-NNNNN
    pattern); falls back to a UUID-derived suffix for prequal-only flows.
    """
    submitted_year = (app.submitted_at or datetime.now(timezone.utc)).year
    if app.loan_id is not None:
        return f"PRN-{submitted_year}-{app.loan_id:05d}"
    suffix = str(app.id).split("-")[0].upper()
    return f"PRN-{submitted_year}-{suffix}"


def _next_steps_for_borrower(app: POSApplication) -> list[str]:
    return [
        "Your loan officer will email you a copy of your application within the hour",
        "You'll receive your Loan Estimate within 3 business days",
        "We'll begin verifying your assets and pulling your credit report",
        (
            f"Your review meeting is confirmed — see calendar invite "
            f"(appointment #{app.submitted_appointment_id})"
            if app.submitted_appointment_id
            else "Schedule your application review from the Team tab"
        ),
    ]
