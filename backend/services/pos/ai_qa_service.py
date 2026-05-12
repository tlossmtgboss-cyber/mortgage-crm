"""AI Q&A service — Aria's borrower-side brain.

Orchestrates:
  - Loan-file retrieval (the borrower's own draft + linked loan record)
  - BorrowerApplicationAgent for guideline citations + structured output
  - Conversation history retrieval for thread continuity
  - Confidence scoring and escalation to LO when uncertain

The service NEVER returns information about another borrower's loan file.
The retrieval step is hard-scoped by application_id, and that ID has already
been validated against purl_ctx.contact_id at the route layer.
"""
from __future__ import annotations

import logging
import time as _time
from typing import Any
from uuid import UUID

import nh3

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from database.models.pos import (
    AIQAConfidence,
    POSAIQAMessage,
    POSApplication,
    POSAuditEvent,
)
from database.models.lead_loan import Loan

from .application_service import ApplicationService, AuditContext


logger = logging.getLogger(__name__)


# Number of recent messages to thread into the prompt by default.
DEFAULT_HISTORY_DEPTH = 10


class AIQAService:
    """Aria — borrower-scoped Q&A over loan file + agency guidelines."""

    def __init__(
        self,
        guidelines_agent: Any | None = None,
        application_service: ApplicationService | None = None,
    ) -> None:
        self._guidelines_agent = guidelines_agent or _resolve_guidelines_agent()
        self._app_service = application_service or ApplicationService()

    # ----- public API --------------------------------------------------------

    async def ask(
        self,
        session: Session,
        *,
        application: POSApplication,
        question: str,
        context_message_ids: list[int] | None = None,
        current_step: str | None = None,
        ctx: AuditContext,
    ) -> dict[str, Any]:
        """Answer the borrower's question with loan-aware grounding."""
        started = _time.monotonic()

        # M3 fix: Sanitize borrower question before storage to prevent stored
        # XSS. Strip all HTML tags — plain text only.
        question = nh3.clean(question, tags=set(), attributes={})

        # 1. Persist the borrower's turn.
        borrower_msg = POSAIQAMessage(
            application_id=application.id,
            role="borrower",
            content=question,
        )
        session.add(borrower_msg)
        session.flush()

        # 2. Build context for the agent.
        loan_context = self._retrieve_loan_context(session, application)
        history = self._retrieve_history(
            session, application_id=application.id, ids=context_message_ids
        )

        # 3. Call the borrower application agent.
        agent_response = await self._call_guidelines_agent(
            question=question,
            loan_context=loan_context,
            history=history,
            current_step=current_step,
            organization_id=getattr(application, 'organization_id', None),
            contact_id=getattr(application, 'contact_id', None),
            application_id=str(application.id),
        )

        # 4. Score confidence and decide whether to escalate.
        confidence = self._score_confidence(agent_response)
        escalate = confidence == AIQAConfidence.ESCALATE

        # 5. Persist the Aria turn.
        latency_ms = int((_time.monotonic() - started) * 1000)
        aria_msg = POSAIQAMessage(
            application_id=application.id,
            role="aria",
            content=agent_response["content"],
            sources=agent_response.get("sources") or [],
            follow_ups=agent_response.get("follow_ups") or [],
            latency_ms=latency_ms,
            tokens_used=agent_response.get("tokens_used"),
            confidence=confidence,
        )
        session.add(aria_msg)
        aria_msg.structured_output = agent_response.get("structured_output")
        session.flush()

        # 6. Audit (no question content — privacy; just metadata).
        self._app_service._write_audit(  # noqa: SLF001
            session,
            application_id=application.id,
            ctx=ctx,
            event_type=POSAuditEvent.AI_QA_ASKED,
            delta={
                "borrower_message_id": borrower_msg.id,
                "aria_message_id": aria_msg.id,
                "confidence": confidence,
                "latency_ms": latency_ms,
                "source_count": len(aria_msg.sources or []),
                "escalation_recommended": escalate,
            },
        )

        return {
            "message_id": aria_msg.id,
            "application_id": application.id,
            "content": aria_msg.content,
            "sources": aria_msg.sources or [],
            "follow_ups": aria_msg.follow_ups or [],
            "latency_ms": latency_ms,
            "confidence": confidence,
            "escalation_recommended": escalate,
            "escalation_reason": agent_response.get("escalation_reason"),
            "created_at": aria_msg.created_at,
            "structured_output": agent_response.get("structured_output"),
            "meeting_offered": agent_response.get("meeting_offered", False),
            "meeting_details": agent_response.get("meeting_details"),
        }

    def get_history(
        self,
        session: Session,
        *,
        application_id: UUID,
        limit: int = 50,
    ) -> list[POSAIQAMessage]:
        stmt = (
            select(POSAIQAMessage)
            .where(POSAIQAMessage.application_id == application_id)
            .order_by(POSAIQAMessage.created_at.asc())
            .limit(limit)
        )
        result = session.execute(stmt)
        return list(result.scalars().all())

    # ----- internals ---------------------------------------------------------

    def _retrieve_loan_context(
        self,
        session: Session,
        application: POSApplication,
    ) -> dict[str, Any]:
        """Build the loan-file context blob to ground the agent.

        Includes the borrower's draft sections (without raw PII), plus the
        linked Loan record's high-level fields if present. NEVER includes
        SSN — the agent doesn't need it and it's a leak risk.
        """
        sections_blob = {
            s.section_key: s.data or {}
            for s in application.sections
        }

        loan_blob: dict[str, Any] = {}
        if application.loan_id is not None:
            loan = session.get(Loan, application.loan_id)
            if loan is not None:
                # Pull a minimal set of fields. Don't blanket-serialize the
                # Loan model — tenant-specific columns may contain LO notes
                # or pricing strategy that shouldn't be exposed to the agent.
                loan_blob = {
                    "id": loan.id,
                    "purpose": getattr(loan, "loan_purpose", None),
                    "loan_amount": _decimal_to_float(getattr(loan, "loan_amount", None)),
                    "purchase_price": _decimal_to_float(getattr(loan, "purchase_price", None)),
                    "ltv": _decimal_to_float(getattr(loan, "ltv", None)),
                    "occupancy": getattr(loan, "occupancy_type", None),
                    "property_type": getattr(loan, "property_type", None),
                    "status": getattr(loan, "status", None),
                }

        return {
            "application_id": str(application.id),
            "completion_pct": application.completion_pct,
            "current_step": application.current_step,
            "sections": sections_blob,
            "loan": loan_blob,
            "presence_flags": {
                "has_ssn": bool(application.pii and application.pii.ssn_encrypted),
                "has_co_ssn": bool(application.pii and application.pii.co_ssn_encrypted),
                "has_dob": bool(application.pii and application.pii.dob),
            },
        }

    def _retrieve_history(
        self,
        session: Session,
        *,
        application_id: UUID,
        ids: list[int] | None,
    ) -> list[dict[str, Any]]:
        """Pull recent turns to thread into the agent prompt."""
        if ids:
            stmt = (
                select(POSAIQAMessage)
                .where(POSAIQAMessage.application_id == application_id)
                .where(POSAIQAMessage.id.in_(ids))
                .order_by(POSAIQAMessage.created_at.asc())
            )
        else:
            stmt = (
                select(POSAIQAMessage)
                .where(POSAIQAMessage.application_id == application_id)
                .order_by(desc(POSAIQAMessage.created_at))
                .limit(DEFAULT_HISTORY_DEPTH)
            )

        result = session.execute(stmt)
        rows = list(result.scalars().all())
        # We over-fetched in reverse for the no-ids branch; flip it back.
        if not ids:
            rows.reverse()

        return [
            {
                "role": r.role,
                "content": r.content,
                "sources": r.sources,
            }
            for r in rows
        ]

    async def _call_guidelines_agent(
        self,
        *,
        question: str,
        loan_context: dict,
        history: list,
        current_step: str | None,
        organization_id: int | None = None,
        contact_id: int | None = None,
        application_id: str | None = None,
    ) -> dict:
        if self._guidelines_agent is None:
            logger.warning("BorrowerApplicationAgent unavailable; returning deflection")
            return _deflection_response(question)

        try:
            return await self._guidelines_agent.answer(
                question=question,
                loan_context=loan_context,
                history=history,
                current_step=current_step,
                organization_id=organization_id,
                contact_id=contact_id,
                application_id=application_id,
            )
        except Exception as exc:
            logger.exception("BorrowerApplicationAgent raised; deflecting: %s", exc)
            return _deflection_response(
                question,
                escalation_reason=f"Agent error: {type(exc).__name__}",
            )

    @staticmethod
    def _score_confidence(agent_response: dict[str, Any]) -> str:
        """Map the agent response onto an AIQAConfidence value.

        Heuristics:
          - If the agent says it can't answer → ESCALATE
          - If sources list is empty → LOW
          - If 1 source → MEDIUM
          - If 2+ sources → HIGH
        """
        if agent_response.get("escalation_reason"):
            return AIQAConfidence.ESCALATE

        sources = agent_response.get("sources") or []
        if len(sources) >= 2:
            return AIQAConfidence.HIGH
        if len(sources) == 1:
            return AIQAConfidence.MEDIUM
        return AIQAConfidence.LOW


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_guidelines_agent():
    try:
        from services.pos.borrower_application_agent import BorrowerApplicationAgent
        return BorrowerApplicationAgent()
    except Exception as e:
        logger.warning("Could not load BorrowerApplicationAgent: %s", e)
        return None


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _deflection_response(
    question: str,
    *,
    escalation_reason: str | None = None,
) -> dict[str, Any]:
    """Produce a graceful response when the agent isn't available."""
    return {
        "content": (
            "I want to make sure I give you an accurate answer on this one. "
            "Let me loop in your loan officer — they'll follow up shortly. "
            "In the meantime, is there something else I can help with?"
        ),
        "sources": [],
        "follow_ups": [
            "What documents do I still owe?",
            "When will I close?",
            "Connect me with my loan officer",
        ],
        "tokens_used": None,
        "escalation_reason": escalation_reason or "agent_unavailable",
    }
