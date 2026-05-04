"""Pydantic schemas for Aria — the borrower-facing AI Q&A assistant."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


class Source(BaseModel):
    """A citation accompanying an Aria response."""

    type: Literal["loan_file", "guideline", "perennia_doc"]
    label: str = Field(
        ...,
        max_length=200,
        description="Display label, e.g. 'FNMA Selling Guide B3-4.3-04'.",
    )
    anchor: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Optional deep-link anchor — for guidelines, an URL or section ID; "
            "for loan_file, a path like 'sections.assets.checking_balance'."
        ),
    )


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    """Body for POST /api/v1/pos/ai-qa/ask."""

    application_id: UUID
    message: str = Field(..., min_length=1, max_length=2000)

    # Conversation continuity — if the frontend supplies the last few message
    # IDs, the service threads them into the prompt context. Otherwise the
    # latest 10 messages from this application's history are used.
    context_message_ids: list[int] | None = Field(default=None, max_length=20)

    # Optional client-side hint about the borrower's current step. Helps Aria
    # tailor "what's next" answers.
    current_step: str | None = Field(default=None, max_length=32)


class AskResponse(BaseModel):
    """Response for an Aria turn."""

    message_id: int
    application_id: UUID

    role: Literal["aria"] = "aria"
    content: str  # Markdown-formatted answer

    sources: list[Source] = Field(default_factory=list)
    follow_ups: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Suggested follow-up questions for the borrower to tap.",
    )

    # Telemetry exposed back to the frontend (used to render "Aria is thinking…"
    # smoothing if needed, plus debugging).
    latency_ms: int
    confidence: Literal["high", "medium", "low", "escalate"]
    escalation_recommended: bool = False
    escalation_reason: str | None = None

    structured_output: dict | None = Field(
        default=None,
        description="Structured JSON output from the agent (intent, risk level, flags, etc.)",
    )
    meeting_offered: bool = Field(
        default=False,
        description="True if the agent offered a meeting with the LO this turn.",
    )
    meeting_details: dict | None = Field(
        default=None,
        description="Calendar slot time, LO name, and confirmation when a meeting is booked.",
    )

    created_at: datetime


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class QAMessageResponse(BaseModel):
    """One message in the Aria history list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["borrower", "aria"]
    content: str
    sources: list[Source] | None = None
    follow_ups: list[str] | None = None
    confidence: str | None = None
    created_at: datetime


class QAHistoryResponse(BaseModel):
    """Response for GET /api/v1/pos/ai-qa/history."""

    application_id: UUID
    messages: list[QAMessageResponse]
    total: int
