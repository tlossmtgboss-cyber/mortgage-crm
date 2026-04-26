"""
Perennia AI — URLA Call Intelligence Service
=============================================
Orchestrates post-call analysis of URLA voice agent sessions.

Triggered after finalize_urla succeeds. Produces:
  1. Call quality & compliance score
  2. LO kickoff briefing
  3. Auto-generated CRM tasks
  4. Call notes (LLM-generated summary)

The analysis pipeline runs asynchronously — the caller doesn't wait for it.
Results are persisted on the URLAApplication record in Redis and optionally
pushed to the CRM database.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from .models import CallNotes, CallTranscriptEntry, URLAApplication

logger = logging.getLogger("urla.call_intelligence")


from .call_scoring import URLACallScore, score_urla_call
from .lo_briefing import LOBriefing, generate_lo_briefing
from .task_generator import URLATask, generate_urla_tasks


# =========================================================================
# RESULT MODEL
# =========================================================================

class URLACallIntelligenceResult(BaseModel):
    """Complete output of the post-call analysis pipeline."""
    loan_id: str
    tenant_id: str
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    score: URLACallScore
    briefing: LOBriefing
    tasks: List[URLATask]
    call_notes: CallNotes


# =========================================================================
# LLM-BASED CALL NOTES GENERATION
# =========================================================================

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_MODEL = "claude-sonnet-4-6"
_ANTHROPIC_MAX_TOKENS = 2048

_CALL_NOTES_SYSTEM_PROMPT = """\
You are a senior mortgage loan analyst at Perennia AI. You are reviewing the \
transcript and structured data from an AI-assisted URLA 1003 application \
intake call.

Produce a concise briefing for the loan officer who will handle this file. \
Your output MUST be valid JSON matching this schema exactly:

{
  "executive_summary": "<2-3 sentence overview of the call and application>",
  "borrower_profile": "<1 paragraph: who is this borrower, employment, credit posture>",
  "loan_snapshot": "<1 paragraph: loan purpose, amount, property, LTV estimate if possible>",
  "red_flags": ["<list of potential issues the LO should investigate>"],
  "stated_concerns": ["<things the borrower explicitly worried about or asked>"],
  "recommended_talking_points": ["<topics the LO should cover in kickoff call>"]
}

Guidelines:
- Be specific. Use names, numbers, and dollar amounts from the data.
- red_flags: include gaps in employment, large unexplained deposits, \
  declarations answers that need follow-up, missing sections, \
  inconsistencies between stated income and loan amount.
- If the transcript is empty or minimal, note that and base analysis on \
  structured data only.
- Do NOT fabricate information. If data is missing, say so.
- Output ONLY the JSON object. No markdown, no commentary.\
"""


def _build_call_notes_user_prompt(app: URLAApplication) -> str:
    """Assemble the user-turn content for the call notes LLM request."""

    parts: List[str] = []

    # -- Transcript --
    if app.transcript:
        parts.append("## CALL TRANSCRIPT\n")
        for entry in app.transcript:
            ts = entry.timestamp.strftime("%H:%M:%S") if entry.timestamp else ""
            parts.append(f"[{ts}] {entry.speaker.upper()}: {entry.text}")
        parts.append("")
    else:
        parts.append("## CALL TRANSCRIPT\n(No transcript recorded)\n")

    # -- Structured application data (serialized, excluding PII-heavy fields) --
    app_data = app.model_dump(
        mode="json",
        exclude_none=True,
        exclude={
            "transcript": True,  # already included above
            "call_notes": True,  # we're generating this
        },
    )
    # Strip SSN from serialized output for the LLM — it doesn't need it
    _redact_ssn(app_data)

    parts.append("## STRUCTURED APPLICATION DATA\n")
    parts.append(json.dumps(app_data, indent=2, default=str))

    return "\n".join(parts)


def _redact_ssn(data: Any) -> None:
    """Recursively redact SSN fields in a dict/list structure (in-place)."""
    if isinstance(data, dict):
        for key in list(data.keys()):
            if key == "ssn" and isinstance(data[key], str):
                data[key] = "***-**-" + data[key][-4:] if len(data[key]) >= 4 else "REDACTED"
            else:
                _redact_ssn(data[key])
    elif isinstance(data, list):
        for item in data:
            _redact_ssn(item)


async def _generate_call_notes_via_llm(
    app: URLAApplication,
) -> CallNotes:
    """
    Call the Anthropic Messages API directly via httpx to produce
    LLM-generated call notes from the transcript and application data.

    Falls back to a minimal, data-only CallNotes if the API call fails.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set — returning data-only call notes"
        )
        return _build_fallback_call_notes(app)

    user_prompt = _build_call_notes_user_prompt(app)

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": _ANTHROPIC_MODEL,
        "max_tokens": _ANTHROPIC_MAX_TOKENS,
        "system": _CALL_NOTES_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _ANTHROPIC_API_URL,
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()

        body = resp.json()
        # Extract text from the first content block
        content_blocks = body.get("content", [])
        raw_text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                raw_text = block["text"]
                break

        if not raw_text:
            logger.error("Claude returned empty content for call notes")
            return _build_fallback_call_notes(app)

        notes_data = json.loads(raw_text)
        return CallNotes(
            executive_summary=notes_data.get("executive_summary", ""),
            borrower_profile=notes_data.get("borrower_profile", ""),
            loan_snapshot=notes_data.get("loan_snapshot", ""),
            red_flags=notes_data.get("red_flags", []),
            stated_concerns=notes_data.get("stated_concerns", []),
            recommended_talking_points=notes_data.get(
                "recommended_talking_points", []
            ),
            generated_at=datetime.now(timezone.utc),
        )

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Anthropic API HTTP error during call notes generation",
            extra={
                "status_code": exc.response.status_code,
                "loan_id": app.loan_id,
                "response_body": exc.response.text[:500],
            },
        )
        return _build_fallback_call_notes(app)

    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse Claude response as JSON for call notes",
            extra={"loan_id": app.loan_id, "error": str(exc)},
        )
        return _build_fallback_call_notes(app)

    except Exception as exc:
        logger.exception(
            "Unexpected error generating call notes via LLM",
            extra={"loan_id": app.loan_id},
        )
        return _build_fallback_call_notes(app)


def _build_fallback_call_notes(app: URLAApplication) -> CallNotes:
    """
    Deterministic call notes built from structured data alone —
    no LLM required. Used when the API key is missing or the call fails.
    """
    primary = app.primary_borrower()

    # Borrower name
    name = "Unknown borrower"
    if primary and primary.section_1a:
        first = primary.section_1a.first_name or ""
        last = primary.section_1a.last_name or ""
        name = f"{first} {last}".strip() or "Unknown borrower"

    # Loan details
    loan_purpose = "unknown purpose"
    loan_amount = "unknown amount"
    if app.section_4 and app.section_4.section_4a:
        s4a = app.section_4.section_4a
        if s4a.loan_purpose:
            loan_purpose = s4a.loan_purpose.lower().replace("_", " ")
        if s4a.loan_amount:
            loan_amount = f"${s4a.loan_amount:,.0f}"

    # Employment
    employment = "Employment information not collected"
    if primary and primary.section_1b and primary.section_1b.employer_name:
        employer = primary.section_1b.employer_name
        title = primary.section_1b.position_title or "unspecified role"
        employment = f"Employed at {employer} as {title}"

    # Completeness
    completed = app.completed_sections
    total_sections = 17
    pct = int((len(completed) / total_sections) * 100) if total_sections else 0

    # Red flags from structured data
    red_flags: List[str] = []
    if primary and primary.section_5:
        if primary.section_5.section_5b:
            s5b = primary.section_5.section_5b
            if s5b.declared_bankruptcy_last_7_years:
                types = ", ".join(s5b.bankruptcy_types or ["unspecified"])
                red_flags.append(f"Bankruptcy in last 7 years ({types})")
            if s5b.outstanding_judgments:
                red_flags.append("Outstanding judgments reported")
            if s5b.currently_delinquent_on_federal_debt:
                red_flags.append("Currently delinquent on federal debt")
            if s5b.foreclosed_last_7_years:
                red_flags.append("Foreclosure in last 7 years")
            if s5b.short_sale_or_pre_foreclosure_last_7_years:
                red_flags.append("Short sale / pre-foreclosure in last 7 years")
        if primary.section_5.section_5a:
            s5a = primary.section_5.section_5a
            if s5a.borrowing_money_for_transaction:
                red_flags.append(
                    "Borrower is borrowing money for this transaction"
                )
            if s5a.family_business_relationship_with_seller:
                red_flags.append(
                    "Family or business relationship with seller"
                )

    if pct < 80:
        red_flags.append(
            f"Application only {pct}% complete — missing sections may "
            f"require follow-up"
        )

    return CallNotes(
        executive_summary=(
            f"URLA intake call completed for {name}. "
            f"Loan purpose: {loan_purpose}, amount: {loan_amount}. "
            f"Application {pct}% complete with "
            f"{len(completed)}/{total_sections} sections captured."
        ),
        borrower_profile=(
            f"{name}. {employment}. "
            f"Citizenship: {_safe_citizenship(primary)}. "
            f"Marital status: {_safe_marital(primary)}."
        ),
        loan_snapshot=(
            f"Purpose: {loan_purpose}. Requested amount: {loan_amount}. "
            f"Property: {_safe_property_address(app)}. "
            f"Occupancy: {_safe_occupancy(app)}."
        ),
        red_flags=red_flags,
        stated_concerns=[],
        recommended_talking_points=[
            "Review and verify all application data in BytePro",
            "Discuss loan program options and rate lock strategy",
            "Confirm documentation requirements and timeline",
        ],
        generated_at=datetime.now(timezone.utc),
    )


def _safe_citizenship(borrower: Optional[Any]) -> str:
    if borrower and borrower.section_1a and borrower.section_1a.citizenship:
        return borrower.section_1a.citizenship.replace("_", " ").title()
    return "not collected"


def _safe_marital(borrower: Optional[Any]) -> str:
    if borrower and borrower.section_1a and borrower.section_1a.marital_status:
        return borrower.section_1a.marital_status.replace("_", " ").title()
    return "not collected"


def _safe_property_address(app: URLAApplication) -> str:
    if app.section_4 and app.section_4.section_4a:
        addr = app.section_4.section_4a.subject_property_address
        if addr:
            return f"{addr.city}, {addr.state} {addr.zip_code}"
    return "not specified"


def _safe_occupancy(app: URLAApplication) -> str:
    if app.section_4 and app.section_4.section_4a:
        occ = app.section_4.section_4a.occupancy
        if occ:
            return occ.replace("_", " ").title()
    return "not specified"


# =========================================================================
# MAIN ORCHESTRATOR
# =========================================================================

async def analyze_call(
    app: URLAApplication,
    tenant_id: str,
) -> URLACallIntelligenceResult:
    """
    Main entry point for post-call intelligence.

    Runs the full analysis pipeline in sequence:
      1. LLM-generated call notes (transcript + structured data -> Claude)
      2. Call quality & compliance scoring
      3. LO kickoff briefing
      4. Auto-generated CRM tasks

    Steps 2-4 may depend on the call notes from step 1, so they run after
    it completes. Steps 2, 3, and 4 are independent of each other and run
    concurrently.

    Returns a URLACallIntelligenceResult with all artifacts.
    """
    logger.info(
        "Starting post-call intelligence analysis",
        extra={"loan_id": app.loan_id, "tenant_id": tenant_id},
    )

    # Step 1: Generate call notes via LLM (other steps can use these)
    call_notes = await _generate_call_notes_via_llm(app)

    logger.info(
        "Call notes generated",
        extra={
            "loan_id": app.loan_id,
            "red_flags_count": len(call_notes.red_flags),
        },
    )

    # Steps 2-4: Run concurrently since they are independent
    # Real modules may be sync — wrap with asyncio.to_thread if needed
    import inspect

    _score_coro = (
        score_urla_call(app)
        if inspect.iscoroutinefunction(score_urla_call)
        else asyncio.to_thread(score_urla_call, app)
    )
    score_task = asyncio.create_task(
        _score_coro,
        name=f"score:{app.loan_id}",
    )

    _briefing_coro = (
        generate_lo_briefing(app)
        if inspect.iscoroutinefunction(generate_lo_briefing)
        else asyncio.to_thread(generate_lo_briefing, app)
    )
    briefing_task = asyncio.create_task(
        _briefing_coro,
        name=f"briefing:{app.loan_id}",
    )

    _tasks_coro = (
        generate_urla_tasks(app)
        if inspect.iscoroutinefunction(generate_urla_tasks)
        else asyncio.to_thread(generate_urla_tasks, app)
    )
    tasks_task = asyncio.create_task(
        _tasks_coro,
        name=f"tasks:{app.loan_id}",
    )

    score, briefing, tasks = await asyncio.gather(
        score_task, briefing_task, tasks_task
    )

    logger.info(
        "Post-call intelligence analysis complete",
        extra={
            "loan_id": app.loan_id,
            "score": getattr(score, "overall_score", getattr(score, "overall", 0.0)),
            "task_count": len(tasks),
        },
    )

    return URLACallIntelligenceResult(
        loan_id=app.loan_id,
        tenant_id=tenant_id,
        score=score,
        briefing=briefing,
        tasks=tasks,
        call_notes=call_notes,
    )


# =========================================================================
# PERSISTENCE — Write results back to the URLAApplication in Redis
# =========================================================================

async def _persist_results(
    app: URLAApplication,
    result: URLACallIntelligenceResult,
) -> None:
    """
    Write call notes back to the URLAApplication record in Redis.

    The URLAStateManager is imported here (not at module level) to avoid
    a circular import — state.py imports models.py, and models.py is
    imported at the top of this file.
    """
    from .state import URLAStateManager

    try:
        state = URLAStateManager()
        await state.connect()

        # Persist LLM-generated call notes on the application record
        app.call_notes = result.call_notes
        await state.save_application(app)

        logger.info(
            "Call intelligence results persisted to Redis",
            extra={"loan_id": app.loan_id},
        )
    except Exception as exc:
        logger.exception(
            "Failed to persist call intelligence results",
            extra={"loan_id": app.loan_id},
        )
    finally:
        try:
            await state.close()
        except Exception:
            pass


# =========================================================================
# CRM INTEGRATION — Optionally push tasks to the CRM database
# =========================================================================

async def _push_tasks_to_crm(
    result: URLACallIntelligenceResult,
) -> None:
    """
    Push auto-generated tasks to the CRM task table.

    Uses a lazy import of the CRM database session to avoid coupling
    the URLA agent package to the main backend at import time. If the
    CRM is not reachable (e.g., running in standalone LiveKit worker mode),
    this is a no-op.
    """
    try:
        from database import get_db
        from database.models import Task as CRMTask
    except ImportError:
        logger.debug(
            "CRM database not available — skipping task push "
            "(standalone worker mode)"
        )
        return

    if not result.tasks:
        return

    try:
        db_gen = get_db()
        db = next(db_gen)
        try:
            for task in result.tasks:
                crm_task = CRMTask(
                    title=task.title,
                    description=task.description,
                    priority=task.priority,
                    status="pending",
                    category=task.category,
                    loan_id=result.loan_id,
                    tenant_id=result.tenant_id,
                )
                db.add(crm_task)
            db.commit()
            logger.info(
                "Pushed %d tasks to CRM",
                len(result.tasks),
                extra={"loan_id": result.loan_id},
            )
        except Exception as exc:
            db.rollback()
            logger.exception(
                "Failed to push tasks to CRM",
                extra={"loan_id": result.loan_id},
            )
        finally:
            try:
                next(db_gen, None)
            except StopIteration:
                pass
    except Exception as exc:
        logger.exception(
            "Failed to obtain CRM database session",
            extra={"loan_id": result.loan_id},
        )


# =========================================================================
# INTEGRATION HOOK — Fire-and-forget from finalize_urla
# =========================================================================

async def _run_post_finalize_pipeline(
    app: URLAApplication,
    tenant_id: str,
) -> None:
    """
    Full post-finalize pipeline: analyze -> persist -> push to CRM.

    This is the target of the background asyncio.Task created by
    trigger_post_finalize_analysis(). Exceptions are caught and logged
    rather than propagated, since the caller (finalize_urla) does not
    await this coroutine.
    """
    try:
        result = await analyze_call(app, tenant_id)

        # Persist call notes on the Redis application record
        await _persist_results(app, result)

        # Push generated tasks to CRM (no-op if DB unavailable)
        await _push_tasks_to_crm(result)

        logger.info(
            "Post-finalize intelligence pipeline complete",
            extra={
                "loan_id": app.loan_id,
                "score": getattr(result.score, "overall_score", 0.0),
                "task_count": len(result.tasks),
                "red_flags": len(result.call_notes.red_flags),
            },
        )

    except Exception as exc:
        logger.exception(
            "Post-finalize intelligence pipeline failed",
            extra={"loan_id": app.loan_id, "tenant_id": tenant_id},
        )


def trigger_post_finalize_analysis(
    app: URLAApplication,
    tenant_id: str,
) -> asyncio.Task:
    """
    Create a background asyncio.Task to run the full post-finalize
    intelligence pipeline.

    Call this from finalize_urla after BytePro push succeeds:

        from .call_intelligence import trigger_post_finalize_analysis
        trigger_post_finalize_analysis(app, tenant_id)

    The task runs in the current event loop. The caller does NOT need
    to await it — results are persisted asynchronously.

    Returns the Task handle so the caller can optionally await or cancel it.
    """
    task = asyncio.create_task(
        _run_post_finalize_pipeline(app, tenant_id),
        name=f"urla-call-intel:{app.loan_id}",
    )
    # Log if the background task fails (shields the caller from exceptions)
    task.add_done_callback(_on_task_done)
    return task


def _on_task_done(task: asyncio.Task) -> None:
    """Callback to log unhandled exceptions from the background analysis task."""
    if task.cancelled():
        logger.warning(
            "Call intelligence task cancelled: %s", task.get_name()
        )
        return

    exc = task.exception()
    if exc is not None:
        logger.error(
            "Call intelligence task failed: %s — %s",
            task.get_name(),
            exc,
            exc_info=exc,
        )
