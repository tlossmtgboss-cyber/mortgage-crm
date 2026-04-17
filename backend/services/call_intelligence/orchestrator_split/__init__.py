# =============================================================================
# PERENNIA AI — Call Intelligence: Orchestrator (Refactored)
#
# Previously: orchestrator_service.py (91,804 bytes / ~3,000 lines)
# Now: 4 focused modules with a thin coordinator
#
# Module Breakdown:
#   session_manager.py       — Session lifecycle, state machine, config
#   agent_router.py          — Agent dispatch (unified/parallel), error isolation
#   transcript_processor.py  — STT normalization, PII redaction, persistence
#   extraction_validator.py  — Per-domain validation, hallucination detection
#
# External dependencies:
#   stt_fallback_service.py  — Deepgram/AssemblyAI/degraded mode
#   recording_consent_service.py — Consent gate (from consent-gate-v2)
#
# This __init__.py provides the CallIntelligenceOrchestrator class that
# wires everything together — same external interface as the old monolith,
# but delegating to focused modules internally.
# =============================================================================

from .session_manager import SessionManager, SessionConfig, SessionStatus
from .agent_router import AgentRouter, AgentResult, AgentStatus, AgentType
from .transcript_processor import TranscriptProcessor, TranscriptChunk
from .extraction_validator import ExtractionValidator

__all__ = [
    "CallIntelligenceOrchestrator",
    "SessionManager",
    "SessionConfig",
    "SessionStatus",
    "AgentRouter",
    "AgentResult",
    "AgentStatus",
    "AgentType",
    "TranscriptProcessor",
    "TranscriptChunk",
    "ExtractionValidator",
]


class CallIntelligenceOrchestrator:
    """
    Thin coordinator that wires the split modules together.
    Drop-in replacement for the old monolithic orchestrator_service.py.

    Usage:
        orch = CallIntelligenceOrchestrator(db=db, llm_client=client, ws=ws_mgr)

        # Create session
        session = await orch.create_session(...)

        # Process incoming audio
        chunk = orch.transcript.normalize_deepgram(session_id, dg_result)
        chunk = await orch.transcript.process_chunk(chunk)
        results = await orch.agents.dispatch_chunk(session_id, chunk.to_dict(), agents)

        # Complete session
        await orch.sessions.complete_session(session_id, duration)
    """

    def __init__(self, db, llm_client=None, ws_manager=None):
        self.sessions = SessionManager(db)
        self.agents = AgentRouter(db, llm_client, ws_manager)
        self.transcript = TranscriptProcessor(db, ws_manager)
        self.validator = ExtractionValidator()
        self._db = db

    async def create_session(self, **kwargs):
        return await self.sessions.create_session(**kwargs)

    async def process_stt_result(
        self,
        session_id: str,
        stt_result: dict,
        provider: str = "deepgram",
        enabled_agents: list = None,
        extraction_mode: str = "unified",
    ):
        if provider == "deepgram":
            chunk = self.transcript.normalize_deepgram(session_id, stt_result)
        elif provider == "assemblyai":
            chunk = self.transcript.normalize_assemblyai(session_id, stt_result)
        else:
            return None

        if not chunk:
            return None

        chunk = await self.transcript.process_chunk(chunk)

        if chunk.is_final and enabled_agents:
            results = await self.agents.dispatch_chunk(
                session_id,
                chunk.to_dict(),
                enabled_agents,
                extraction_mode,
            )
            return {"chunk": chunk, "agent_results": results}

        return {"chunk": chunk, "agent_results": None}

    async def end_session(self, session_id: str, duration: int = None):
        await self.sessions.begin_post_call_processing(session_id)

        transcript = await self.transcript.get_full_transcript(session_id)

        self.transcript.cleanup_session(session_id)

        await self.sessions.complete_session(session_id, duration)

        return {"transcript_length": len(transcript)}
