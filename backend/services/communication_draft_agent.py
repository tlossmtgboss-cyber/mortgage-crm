"""
CommunicationDraftAgent (Domain 2 — Unified Communications)

AI-powered service that reads inbound messages on a loan file and
generates suggested replies using Anthropic Claude.

Features:
    - generate_draft()     — synchronous draft for a specific inbound message
    - auto_draft_inbound() — background hook called when new inbound arrives
                             (targets < 5 second turnaround)

Drafts are stored in ``FileCommunication.ai_draft_response`` with status
tracking via ``FileCommunication.ai_draft_status``.

Usage:
    from services.communication_draft_agent import CommunicationDraftAgent

    agent = CommunicationDraftAgent()
    result = await agent.generate_draft(file_id=123, message_id=456, db=session)
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANTHROPIC_MODEL = "claude-sonnet-4-6"
MAX_CONTEXT_MESSAGES = 20  # Previous messages to include for context
AUTO_DRAFT_TARGET_SECONDS = 5


# ---------------------------------------------------------------------------
# CommunicationDraftAgent
# ---------------------------------------------------------------------------

class CommunicationDraftAgent:
    """Generates AI-drafted replies for inbound communications on a loan file."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._client = None

    # -- lazy client init ---------------------------------------------------

    def _get_client(self):
        """Return a cached Anthropic client, created on first use."""
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    # -- public API ---------------------------------------------------------

    async def generate_draft(
        self,
        file_id: int,
        message_id: int,
        db: Session,
    ) -> Dict[str, Any]:
        """Generate a suggested reply for a specific inbound message.

        Args:
            file_id: Loan file (``loans.id``) that owns the communication.
            message_id: ``FileCommunication.id`` of the inbound message.
            db: Active SQLAlchemy session (RLS-aware).

        Returns:
            dict with keys: suggested_reply, confidence_score, tone_analysis,
            ai_draft_status.
        """
        from database.models.file_communication import FileCommunication

        # 1. Load the target inbound message
        message = db.query(FileCommunication).filter(
            FileCommunication.id == message_id,
            FileCommunication.file_id == file_id,
        ).first()

        if not message:
            raise ValueError(f"FileCommunication {message_id} not found for file {file_id}")

        # 2. Load loan context
        loan_context = self._load_loan_context(file_id, db)

        # 3. Load recent conversation history for context
        recent_messages = (
            db.query(FileCommunication)
            .filter(
                FileCommunication.file_id == file_id,
            )
            .order_by(FileCommunication.created_at.desc())
            .limit(MAX_CONTEXT_MESSAGES)
            .all()
        )
        # Reverse so oldest is first in the prompt
        recent_messages = list(reversed(recent_messages))

        # 4. Build the prompt and call Claude
        result = self._call_claude(
            inbound_message=message,
            loan_context=loan_context,
            conversation_history=recent_messages,
        )

        # 5. Persist the draft on the FileCommunication row
        message.ai_draft_response = result["suggested_reply"]
        message.ai_draft_status = "pending"
        db.commit()

        result["ai_draft_status"] = "pending"
        return result

    async def auto_draft_inbound(
        self,
        file_id: int,
        communication: Any,
        db: Session,
    ) -> None:
        """Background hook: generate a draft when a new inbound message arrives.

        Called by inbound webhook handlers. Targets < 5-second turnaround so
        the LO sees a suggested reply almost immediately.

        Args:
            file_id: Loan file ID.
            communication: The newly created ``FileCommunication`` instance
                           (must already be committed / have an id).
            db: Active SQLAlchemy session.
        """
        start = time.monotonic()
        try:
            result = await self.generate_draft(
                file_id=file_id,
                message_id=communication.id,
                db=db,
            )
            elapsed = time.monotonic() - start
            if elapsed > AUTO_DRAFT_TARGET_SECONDS:
                logger.warning(
                    "Auto-draft for message %s took %.1fs (target %ds)",
                    communication.id, elapsed, AUTO_DRAFT_TARGET_SECONDS,
                )
            else:
                logger.info(
                    "Auto-draft for message %s completed in %.1fs",
                    communication.id, elapsed,
                )
        except Exception as e:
            logger.exception(
                "Auto-draft failed for file %s message %s: %s",
                file_id, communication.id, e,
            )

    # -- internal helpers ---------------------------------------------------

    def _load_loan_context(self, file_id: int, db: Session) -> Dict[str, Any]:
        """Load relevant loan and lead data for prompt context."""
        from database.models.lead_loan import Loan, Lead

        loan = db.query(Loan).filter(Loan.id == file_id).first()
        if not loan:
            return {"file_id": file_id, "status": "loan_not_found"}

        context: Dict[str, Any] = {
            "file_id": file_id,
            "loan_number": getattr(loan, "loan_number", None),
            "borrower_name": getattr(loan, "borrower_name", None),
            "loan_type": getattr(loan, "loan_type", None),
            "loan_amount": str(getattr(loan, "loan_amount", "")) if getattr(loan, "loan_amount", None) else None,
            "stage": getattr(loan, "stage", None),
            "property_address": getattr(loan, "property_address", None),
            "closing_date": str(getattr(loan, "closing_date", "")) if getattr(loan, "closing_date", None) else None,
        }

        # Attach lead info if available
        lead_id = getattr(loan, "lead_id", None)
        if lead_id:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                context["lead_name"] = getattr(lead, "name", None)
                context["lead_email"] = getattr(lead, "email", None)
                context["lead_phone"] = getattr(lead, "phone", None)
                context["lead_stage"] = getattr(lead, "stage", None)

        return context

    def _build_conversation_text(self, messages) -> str:
        """Format recent conversation history for the prompt."""
        lines = []
        for msg in messages:
            direction_label = "INBOUND" if msg.direction == "inbound" else "OUTBOUND"
            channel_label = (msg.channel or "unknown").upper()
            timestamp = msg.created_at.isoformat() if msg.created_at else ""
            subject_line = f" | Subject: {msg.subject}" if msg.subject else ""
            lines.append(
                f"[{timestamp}] {direction_label} ({channel_label}){subject_line}\n"
                f"From: {msg.from_party} -> To: {msg.to_party}\n"
                f"{msg.body or ''}\n"
            )
        return "\n---\n".join(lines)

    def _call_claude(
        self,
        inbound_message,
        loan_context: Dict[str, Any],
        conversation_history: list,
    ) -> Dict[str, Any]:
        """Call Anthropic Claude to generate the draft reply.

        Returns dict with suggested_reply, confidence_score, tone_analysis.
        """
        conversation_text = self._build_conversation_text(conversation_history)
        loan_json = json.dumps(
            {k: v for k, v in loan_context.items() if v is not None},
            indent=2,
        )

        system_prompt = (
            "You are an AI assistant for a mortgage loan officer using Perennia AI. "
            "Your job is to draft a professional reply to an inbound message from a "
            "borrower, real-estate agent, processor, or other party on a mortgage file.\n\n"
            "Guidelines:\n"
            "- Be warm but professional. Mirror the formality level of the sender.\n"
            "- Reference specific loan details when relevant.\n"
            "- If documents are requested, list them clearly.\n"
            "- Never disclose sensitive financial data (SSN, full account numbers).\n"
            "- Keep replies concise — 1-3 short paragraphs max.\n"
            "- Match the channel: SMS replies should be shorter than email replies.\n\n"
            "Respond ONLY with valid JSON containing exactly these keys:\n"
            '  "suggested_reply": string (the draft message body),\n'
            '  "confidence_score": number 0.0-1.0 (how confident you are in the draft),\n'
            '  "tone_analysis": string (one of: professional, casual, empathetic, urgent, informational)\n'
        )

        user_prompt = (
            f"## Loan File Context\n{loan_json}\n\n"
            f"## Recent Conversation History\n{conversation_text}\n\n"
            f"## Message to Reply To\n"
            f"Channel: {inbound_message.channel}\n"
            f"From: {inbound_message.from_party}\n"
            f"Subject: {inbound_message.subject or 'N/A'}\n"
            f"Body:\n{inbound_message.body}\n\n"
            "Generate a draft reply as JSON."
        )

        from services.llm_gateway import llm_gateway
        llm_result = llm_gateway.complete_sync(
            intent="email",
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens_override=1024,
        )

        # Parse the response
        raw_text = llm_result.text

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            # Remove opening fence (possibly ```json)
            first_newline = raw_text.index("\n")
            raw_text = raw_text[first_newline + 1:]
            # Remove closing fence
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("Claude returned non-JSON response, using raw text as reply")
            parsed = {
                "suggested_reply": raw_text,
                "confidence_score": 0.5,
                "tone_analysis": "informational",
            }

        return {
            "suggested_reply": parsed.get("suggested_reply", raw_text),
            "confidence_score": float(parsed.get("confidence_score", 0.7)),
            "tone_analysis": parsed.get("tone_analysis", "professional"),
        }
