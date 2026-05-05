"""
Live Session Runner — The Pipeline Glue

Connects: Audio chunks → Deepgram STT → Unified Extraction → WS events to frontend

This is the missing wiring between:
  - recording_consent_routes.py (ws_manager, WebSocket endpoint)
  - stt_fallback_service.py (Deepgram/AssemblyAI connection)
  - unified_extractor.py (single-call extraction across all domains)
  - Frontend WebSocket (expects agent_update events with message/value/confidence)
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")

AGENT_DOMAIN_MAP = {
    "identity": "identity",
    "property_info": "property",
    "employment": "employment",
    "financial": "financial",
    "compliance": "compliance",
    "intent": "intent",
}


class LiveSessionRunner:
    """
    Manages a single live CI session's real-time pipeline.

    Lifecycle:
      1. start() — connect to Deepgram, begin listening
      2. feed_audio(bytes) — pipe audio chunks to STT
      3. (internal) on_transcript — run extraction, emit WS events
      4. stop() — disconnect STT, cleanup
    """

    def __init__(self, session_id: str, ws_manager: Any):
        self.session_id = session_id
        self.ws_manager = ws_manager
        self._stt = None
        self._extractor = None
        self._transcript_buffer: List[str] = []
        self._last_extraction_at: float = 0
        self._extraction_interval = 5.0
        self._running = False
        self._extraction_lock = asyncio.Lock()
        self._pending_extraction: Optional[asyncio.Task] = None

    async def start(self):
        from .llm_client import create_llm_client
        from .unified_extractor import UnifiedExtractionEngine

        llm_client = create_llm_client()
        self._extractor = UnifiedExtractionEngine(llm_client)
        self._running = True

        if DEEPGRAM_API_KEY:
            from .stt_fallback_service import STTFallbackService
            self._stt = STTFallbackService(
                deepgram_key=DEEPGRAM_API_KEY,
                assemblyai_key=ASSEMBLYAI_API_KEY or None,
                on_transcript=self._on_stt_transcript,
                on_status_change=self._on_stt_status,
            )
            try:
                await self._stt.connect(self.session_id)
                logger.info(f"[LiveCI] STT connected for session {self.session_id}")
            except Exception as e:
                logger.error(f"[LiveCI] STT connect failed: {e}")
                self._stt = None

        await self.ws_manager.send(self.session_id, {
            "event": "agent_update",
            "agent_type": "transcription",
            "status": "active",
            "message": "Listening for speech...",
            "field_count": 0,
        })

    async def feed_audio(self, audio_bytes: bytes):
        if self._stt and self._running:
            try:
                await self._stt.send_audio(audio_bytes)
            except Exception as e:
                logger.error(f"[LiveCI] send_audio error: {e}")

    async def feed_transcript_text(self, text: str, is_final: bool = True):
        """For browser-mode: accept text transcripts directly (no audio)."""
        if not self._running:
            return
        self._transcript_buffer.append(text)

        await self.ws_manager.send(self.session_id, {
            "event": "agent_update",
            "agent_type": "transcription",
            "status": "active",
            "message": text[:100],
            "field_count": 0,
        })

        if is_final:
            await self._maybe_extract()

    async def stop(self):
        self._running = False
        if self._pending_extraction:
            self._pending_extraction.cancel()
        if self._stt:
            try:
                await self._stt.disconnect()
            except Exception:
                pass
            self._stt = None

        if self._transcript_buffer:
            await self._run_extraction(force=True)

        logger.info(f"[LiveCI] Session {self.session_id} stopped")

    async def _on_stt_transcript(self, session_id: str, result: Dict):
        if not self._running:
            return

        text = result.get("text", "") or result.get("transcript", "")
        is_final = result.get("is_final", True)

        if not text.strip():
            return

        self._transcript_buffer.append(text)

        await self.ws_manager.send(self.session_id, {
            "event": "agent_update",
            "agent_type": "transcription",
            "status": "active",
            "message": text[:100],
            "field_count": len(self._transcript_buffer),
        })

        if is_final:
            await self._maybe_extract()

    async def _on_stt_status(self, session_id: str, status, provider: str):
        status_str = status.value if hasattr(status, 'value') else str(status)
        logger.info(f"[LiveCI] STT status: {status_str} ({provider})")

    async def _maybe_extract(self):
        now = time.time()
        if now - self._last_extraction_at < self._extraction_interval:
            return
        if self._extraction_lock.locked():
            return

        self._pending_extraction = asyncio.create_task(self._run_extraction())

    async def _run_extraction(self, force: bool = False):
        if not self._extractor or not self._transcript_buffer:
            return

        async with self._extraction_lock:
            transcript_text = "\n".join(self._transcript_buffer)
            self._last_extraction_at = time.time()

        if not transcript_text.strip():
            return

        from .data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text=transcript_text,
                start_time=0.0,
                end_time=0.0,
            )
        ]

        for agent_type in ["identity", "property", "financial", "employment", "compliance", "intent"]:
            await self.ws_manager.send(self.session_id, {
                "event": "agent_update",
                "agent_type": agent_type,
                "status": "processing",
                "message": "Analyzing transcript...",
                "field_count": 0,
            })

        try:
            result = await self._extractor.extract_all(
                call_id=self.session_id,
                segments=segments,
            )

            for domain_attr, agent_type in AGENT_DOMAIN_MAP.items():
                domain_data = getattr(result, domain_attr, {})
                field_count = len(domain_data)

                if field_count > 0:
                    for field_name, extracted in domain_data.items():
                        await self.ws_manager.send(self.session_id, {
                            "event": "agent_update",
                            "agent_type": agent_type,
                            "status": "complete",
                            "message": field_name.replace("_", " "),
                            "value": str(extracted.value) if extracted.value else None,
                            "confidence": extracted.confidence,
                            "field_name": field_name,
                            "field_count": field_count,
                        })
                else:
                    await self.ws_manager.send(self.session_id, {
                        "event": "agent_update",
                        "agent_type": agent_type,
                        "status": "complete",
                        "message": "No new data detected",
                        "field_count": 0,
                    })

            logger.info(
                f"[LiveCI] Extraction complete: {result.total_extractions} fields, "
                f"{result.processing_time_ms}ms"
            )

        except Exception as e:
            logger.exception(f"[LiveCI] Extraction failed: {e}")
            await self.ws_manager.send(self.session_id, {
                "event": "agent_error",
                "agent_type": "system",
                "status": "error",
                "message": f"Extraction error: {str(e)[:100]}",
            })


_active_sessions: Dict[str, LiveSessionRunner] = {}


async def activate_live_session(session_id: str, ws_manager: Any) -> LiveSessionRunner:
    if session_id in _active_sessions:
        return _active_sessions[session_id]

    runner = LiveSessionRunner(session_id, ws_manager)
    await runner.start()
    _active_sessions[session_id] = runner
    return runner


async def stop_live_session(session_id: str):
    runner = _active_sessions.pop(session_id, None)
    if runner:
        await runner.stop()


def get_live_session(session_id: str) -> Optional[LiveSessionRunner]:
    return _active_sessions.get(session_id)
