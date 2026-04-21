"""
Perennia AI — URLA LiveKit Entrypoint
=====================================
Drop-in LiveKit Agents worker entrypoint for the dedicated URLA voice agent.

Run with:
    python -m urla.entrypoint  dev
    python -m urla.entrypoint  start  # production

Required env vars:
    LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
    DEEPGRAM_API_KEY
    CARTESIA_API_KEY
    OPENAI_API_KEY   (or ANTHROPIC_API_KEY for Claude)
    REDIS_URL
    BYTEPRO_API_BASE_URL, BYTEPRO_API_KEY
    URLA_TENANT_ID                  (defaults to 'perennia' if unset)
    URLA_DEFAULT_LO_*               (see code)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from livekit import agents
from livekit.agents import AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import deepgram, cartesia, silero
try:
    from livekit.plugins import anthropic as lk_anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    from livekit.plugins import openai
    _HAS_ANTHROPIC = False

from .agent import URLAAgent
from .models import CallTranscriptEntry
from .state import URLAStateManager
from .bytepro_adapter import LoanOfficer
from .prompts import GREETING_NEW_CALLER, GREETING_RETURNING_CALLER_TEMPLATE


logger = logging.getLogger("urla.entrypoint")

MAX_REDIS_RETRIES = 3
INACTIVITY_TIMEOUT = int(os.getenv("URLA_INACTIVITY_TIMEOUT_SECONDS", "300"))


# ---------------------------------------------------------------------------
# Helpers to pull per-call context from the LiveKit SIP dispatch metadata.
# Perennia's telephony layer (Telnyx -> LiveKit SIP trunk) forwards caller
# phone + assigned LO in the SIP headers / job metadata.
# ---------------------------------------------------------------------------

def _extract_caller_phone(ctx: JobContext) -> str:
    """
    Extract caller phone from the first SIP participant identity.
    Falls back to metadata if your SIP integration passes it there.
    """
    # LiveKit SIP sets participant.identity to the caller SIP URI or number
    for p in ctx.room.remote_participants.values():
        identity = p.identity or ""
        # Common formats: "sip:+18435551212@trunk", "+18435551212"
        if identity.startswith("sip:"):
            identity = identity[4:].split("@")[0]
        if identity.startswith("+"):
            return identity
    # Fallback: metadata
    meta = ctx.job.metadata or ""
    if meta.startswith("+"):
        return meta
    return os.getenv("URLA_TEST_CALLER_PHONE", "+10000000000")


def _loan_officer_from_env() -> LoanOfficer:
    """
    Default loan officer for unrouted calls. In production, look up the LO by
    caller phone (e.g. by CRM record) before constructing the URLAAgent.
    """
    return LoanOfficer(
        name=os.getenv("URLA_DEFAULT_LO_NAME", "Perennia Loan Team"),
        nmlsr_id=os.getenv("URLA_DEFAULT_LO_NMLSR", "0000000"),
        email=os.getenv("URLA_DEFAULT_LO_EMAIL", "loans@perennia.ai"),
        phone=os.getenv("URLA_DEFAULT_LO_PHONE", "+18005551212"),
        organization_name=os.getenv("URLA_ORG_NAME", "Perennia AI"),
        organization_nmlsr_id=os.getenv("URLA_ORG_NMLSR", "0000000"),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def urla_entrypoint(ctx: JobContext) -> None:
    """
    LiveKit job entrypoint for the URLA voice agent.
    Registered via WorkerOptions(entrypoint_fnc=urla_entrypoint).
    """
    logger.info("URLA session starting", extra={"room": ctx.room.name})

    await ctx.connect()

    # Start call recording for compliance (C2)
    recording_egress_id = None
    try:
        from livekit.api import LiveKitAPI, RoomCompositeEgressRequest
        lk_api = LiveKitAPI()
        egress_response = await lk_api.egress.start_room_composite_egress(
            RoomCompositeEgressRequest(
                room_name=ctx.room.name,
                audio_only=True,
                file_outputs=[{
                    "file_type": "OGG",
                    "filepath": f"urla-recordings/{ctx.room.name}.ogg",
                }],
            )
        )
        recording_egress_id = egress_response.egress_id
        logger.info("Recording started", extra={"egress_id": recording_egress_id})
    except Exception as e:
        logger.warning("Could not start recording", extra={"error": str(e)})

    # Pull per-call context
    tenant_id = os.getenv("URLA_TENANT_ID", "perennia")
    caller_phone = _extract_caller_phone(ctx)
    loan_officer = _loan_officer_from_env()

    # Build LLM (C6 — prefer Claude, fall back to OpenAI)
    if _HAS_ANTHROPIC:
        llm = lk_anthropic.LLM(
            model=os.getenv("URLA_LLM_MODEL", "claude-sonnet-4-6"),
            temperature=0.2,
        )
    else:
        llm = openai.LLM(
            model=os.getenv("URLA_LLM_MODEL", "gpt-4o"),
            temperature=0.2,
        )

    # Build session first (STT/LLM/TTS don't need Redis)
    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="en",
            interim_results=True,
            smart_format=True,
            punctuate=True,
        ),
        llm=llm,
        tts=cartesia.TTS(
            model="sonic-3",
            voice=os.getenv("URLA_TTS_VOICE", "a0e99841-438c-4a64-b679-ae501e7d6091"),
        ),
        vad=silero.VAD.load(),
    )

    # Connect Redis state with retry logic (C8)
    state = URLAStateManager()
    for attempt in range(1, MAX_REDIS_RETRIES + 1):
        try:
            await state.connect()
            break
        except Exception as e:
            logger.error("Redis connection failed", extra={"attempt": attempt, "error": str(e)})
            if attempt == MAX_REDIS_RETRIES:
                # Session exists, so we can inform the caller before bailing
                await session.start(room=ctx.room, agent=None)
                await session.say(
                    "I'm sorry, we're experiencing technical difficulties right now. "
                    "Please try calling back in a few minutes, or press zero for a human agent."
                )
                return
            await asyncio.sleep(2 ** attempt)

    # Build agent (needs state connected)
    agent = URLAAgent(
        tenant_id=tenant_id,
        caller_phone=caller_phone,
        state=state,
        loan_officer=loan_officer,
    )

    # Graceful shutdown: close Redis on room disconnect
    async def _on_shutdown():
        logger.info("URLA session ending", extra={"room": ctx.room.name})
        try:
            await state.close()
        except Exception as e:
            logger.warning("Error closing state", extra={"error": str(e)})

    ctx.add_shutdown_callback(_on_shutdown)

    # Start the session
    await session.start(room=ctx.room, agent=agent)

    # Transcript capture callback (C3)
    async def _on_transcription(segments, participant, agent_ref=agent, state_ref=state, tenant=tenant_id):
        """Capture transcription segments for compliance audit trail."""
        if not agent_ref._active_loan_id:
            return
        try:
            app = await state_ref.load_application(tenant, agent_ref._active_loan_id)
            if app:
                for seg in segments:
                    if seg.final and seg.text.strip():
                        speaker = "borrower" if participant and not participant.is_agent else "agent"
                        app.transcript.append(CallTranscriptEntry(
                            speaker=speaker,
                            text=seg.text.strip(),
                            timestamp=datetime.now(timezone.utc),
                        ))
                await state_ref.save_application(app)
        except Exception as e:
            logger.warning("Transcript capture error", extra={"error": str(e)})

    session.on("transcription_received", _on_transcription)

    # Start inactivity watchdog (I7)
    asyncio.create_task(_inactivity_watchdog(agent, state, tenant_id))

    # Decide greeting: resume or new
    existing = await state.get_active_application(tenant_id, caller_phone)
    if existing:
        primary = existing.primary_borrower()
        name = (
            primary.section_1a.first_name
            if primary and primary.section_1a and primary.section_1a.first_name
            else "there"
        )
        last_section = existing.current_section.replace("PAUSED:", "").replace("_", " ").title()
        greeting = GREETING_RETURNING_CALLER_TEMPLATE.format(
            name=name, last_section=last_section
        )
        # Pre-load the session so the agent knows which app to operate on
        agent._active_loan_id = existing.loan_id
    else:
        greeting = GREETING_NEW_CALLER

    await session.say(greeting, allow_interruptions=True)


# ---------------------------------------------------------------------------
# Inactivity watchdog (I7)
# ---------------------------------------------------------------------------

async def _inactivity_watchdog(
    agent_ref: URLAAgent,
    state_ref: URLAStateManager,
    tenant_id: str,
    timeout: int = INACTIVITY_TIMEOUT,
) -> None:
    """Auto-pause application after extended silence."""
    last_activity = time.monotonic()

    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        if time.monotonic() - last_activity > timeout:
            if agent_ref._active_loan_id:
                try:
                    app = await state_ref.load_application(tenant_id, agent_ref._active_loan_id)
                    if app and not app.is_finalized:
                        await state_ref.pause(app)
                        logger.info("Auto-paused due to inactivity", extra={"loan_id": app.loan_id})
                except Exception:
                    pass
            break


# ---------------------------------------------------------------------------
# Health check (I16)
# ---------------------------------------------------------------------------

async def _health_check() -> dict:
    """Basic health probe for orchestrator/k8s."""
    health = {"status": "ok", "redis": False}
    try:
        state = URLAStateManager()
        await state.connect()
        await state.redis.ping()
        health["redis"] = True
        await state.close()
    except Exception:
        health["status"] = "degraded"
    return health


# ---------------------------------------------------------------------------
# Worker options — register entrypoint and run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("URLA_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=urla_entrypoint,
            # Route calls to this worker via a dedicated LiveKit dispatch rule
            # or SIP trunk bound to agent_name="urla-agent"
            agent_name=os.getenv("URLA_AGENT_NAME", "urla-agent"),
        )
    )
