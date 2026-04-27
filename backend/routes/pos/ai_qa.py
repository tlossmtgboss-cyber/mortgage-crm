"""Borrower-facing AI Q&A routes (Aria).

All endpoints scope to the borrower's own application. Aria cannot answer
questions about another borrower's loan — the application is resolved via
the same PURL-token helper as every other POS route.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.purl_auth import (
    PURLAuthContext,
    require_purl_token,
    require_purl_write_scope,
)

from database.models.pos import POSApplication
from schemas.pos.ai_qa import (
    AskRequest,
    AskResponse,
    QAHistoryResponse,
    QAMessageResponse,
    Source,
)
from services.pos.ai_qa_service import AIQAService
from services.pos.application_service import AuditContext

from ._helpers import (
    build_audit_context,
    resolve_application_for_borrower,
    resolve_application_for_borrower_write,
)


router = APIRouter(
    prefix="/api/v1/pos/ai-qa",
    tags=["POS - AI Q&A"],
)


def get_ai_qa_service() -> AIQAService:
    return AIQAService()


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask Aria a question (loan-aware, with agency-guideline citations)",
)
async def ask_aria(
    body: AskRequest,
    purl_ctx: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db),
    ctx: AuditContext = Depends(build_audit_context),
    service: AIQAService = Depends(get_ai_qa_service),
) -> AskResponse:
    """Single-turn Q&A. Persists both the borrower turn and Aria's response."""
    from ._helpers import resolve_application_direct

    application = resolve_application_direct(
        body.application_id,
        purl_ctx=purl_ctx,
        db=db,
    )

    if application.status != "draft":
        # Aria is a draft-time helper. Once submitted, the borrower goes
        # through their LO. Returning 410 (Gone) gives the frontend a clear
        # signal to swap the chat panel for a "message Sarah" CTA.
        raise HTTPException(
            status.HTTP_410_GONE,
            detail="Application is no longer accepting Aria queries (already submitted).",
        )

    result = await service.ask(
        db,
        application=application,
        question=body.message,
        context_message_ids=body.context_message_ids,
        current_step=body.current_step,
        ctx=ctx,
    )
    db.commit()

    return AskResponse(
        message_id=result["message_id"],
        application_id=result["application_id"],
        content=result["content"],
        sources=[Source(**s) if isinstance(s, dict) else s for s in result.get("sources") or []],
        follow_ups=result.get("follow_ups") or [],
        latency_ms=result["latency_ms"],
        confidence=result["confidence"],
        escalation_recommended=result["escalation_recommended"],
        escalation_reason=result.get("escalation_reason"),
        created_at=result["created_at"],
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@router.get(
    "/applications/{application_id}/history",
    response_model=QAHistoryResponse,
    summary="Get Aria conversation history for an application",
)
def get_history(
    limit: int = Query(50, ge=1, le=200),
    application: POSApplication = Depends(resolve_application_for_borrower),
    db: Session = Depends(get_db),
    service: AIQAService = Depends(get_ai_qa_service),
) -> QAHistoryResponse:
    messages = service.get_history(
        db,
        application_id=application.id,
        limit=limit,
    )
    return QAHistoryResponse(
        application_id=application.id,
        messages=[
            QAMessageResponse(
                id=m.id,
                role=m.role,  # type: ignore[arg-type]
                content=m.content,
                sources=[Source(**s) for s in (m.sources or [])] if m.sources else None,
                follow_ups=m.follow_ups or None,
                confidence=m.confidence,
                created_at=m.created_at,
            )
            for m in messages
        ],
        total=len(messages),
    )
