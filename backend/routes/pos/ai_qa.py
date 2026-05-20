"""Borrower-facing AI Q&A routes (Aria).

All endpoints scope to the borrower's own application. Aria cannot answer
questions about another borrower's loan — the application is resolved via
the same PURL-token helper as every other POS route.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from database import get_db
from middleware.purl_auth import (
    PURLAuthContext,
    check_purl_rate_limit,
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
    dependencies=[Depends(check_purl_rate_limit)],
)


def get_ai_qa_service() -> AIQAService:
    return AIQAService()


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------


# TODO(perf): Add SSE streaming to eliminate the 2-8s spinner on every
# question. The agent_chat_routes.py SSE pattern (StreamingResponse with
# async generator) can be adapted here. Requires BorrowerApplicationAgent
# to expose a streaming interface (async yield partial content chunks).
# Until then, this endpoint blocks for the full agent response.

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
    _logger = logger

    from ._helpers import resolve_application_direct

    # The pure sync ORM lookup must not block the event loop. Push it to the
    # threadpool — Session is thread-confined, but as long as a single thread
    # owns each call site we're safe.
    loop = asyncio.get_running_loop()

    def _resolve_sync() -> POSApplication:
        return resolve_application_direct(
            body.application_id,
            purl_ctx=purl_ctx,
            db=db,
        )

    application = await loop.run_in_executor(None, _resolve_sync)

    if application.status != "draft":
        raise HTTPException(
            status.HTTP_410_GONE,
            detail="Application is no longer accepting Aria queries (already submitted).",
        )

    # service.ask interleaves sync ORM with an awaited LLM call internally,
    # so it must stay on the loop. The route's own commit/rollback is the only
    # piece we can safely lift into the threadpool here.
    try:
        result = await service.ask(
            db,
            application=application,
            question=body.message,
            context_message_ids=body.context_message_ids,
            current_step=body.current_step,
            ctx=ctx,
        )
        await loop.run_in_executor(None, db.commit)
    except Exception as exc:
        await loop.run_in_executor(None, db.rollback)
        _logger.exception("Aria ask failed: %s", exc)
        from datetime import datetime as _dt, timezone as _tz
        return AskResponse(
            message_id=0,
            application_id=body.application_id,
            content=(
                "I'm having a little trouble connecting right now. "
                "Let me loop in your loan officer so nothing slips through the cracks. "
                "In the meantime, feel free to keep filling out your application!"
            ),
            sources=[],
            follow_ups=["What documents do I still need?", "Can I schedule a call?"],
            latency_ms=0,
            confidence="escalate",
            escalation_recommended=True,
            escalation_reason=f"Agent error: {type(exc).__name__}",
            created_at=_dt.now(_tz.utc),
        )

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
        structured_output=result.get("structured_output"),
        meeting_offered=result.get("meeting_offered", False),
        meeting_details=result.get("meeting_details"),
        created_at=result["created_at"],
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@router.get(
    "/applications/{application_id}/context",
    summary="Get borrower name and LO info for personalized Aria greeting",
)
def get_aria_context(
    application: POSApplication = Depends(resolve_application_for_borrower),
    purl_ctx: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db),
):
    from models.purl import PURLContact
    from database.models.core import User

    contact = db.query(PURLContact).filter(PURLContact.id == purl_ctx.contact_id).first()
    borrower_name = contact.first_name if contact else None

    lo_name = None
    lo_user_id = None
    lo_phone = None
    lo_email = None
    try:
        from database.models.lead_loan import Loan
        if application.loan_id:
            loan = db.query(Loan).filter(Loan.id == application.loan_id).first()
            if loan and getattr(loan, "user_id", None):
                lo = db.query(User).filter(User.id == loan.user_id).first()
                if lo:
                    lo_name = f"{lo.first_name or ''} {lo.last_name or ''}".strip() or None
                    lo_user_id = lo.id
                    lo_phone = getattr(lo, "phone", None)
                    lo_email = getattr(lo, "email", None)
        if not lo_name:
            lo = (
                db.query(User)
                .filter(User.organization_id == purl_ctx.organization_id)
                .filter(User.role.in_(["admin", "lo", "loan_officer"]))
                .order_by(User.id)
                .first()
            )
            if lo:
                lo_name = f"{lo.first_name or ''} {lo.last_name or ''}".strip() or None
                lo_user_id = lo.id
                lo_phone = getattr(lo, "phone", None)
                lo_email = getattr(lo, "email", None)
    except Exception as e:
        logger.warning(
            "Failed to load LO context for app %s: %s",
            application.id, e, exc_info=True,
        )
        # Intentionally fall through with null LO fields — a missing LO
        # lookup shouldn't 500 the borrower's greeting request.

    return {
        "borrower_name": borrower_name,
        "lo_name": lo_name,
        "lo_user_id": lo_user_id,
        "lo_phone": lo_phone,
        "lo_email": lo_email,
        "completion_pct": application.completion_pct,
        "current_step": application.current_step,
    }


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
