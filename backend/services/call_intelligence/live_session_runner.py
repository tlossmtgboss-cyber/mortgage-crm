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

    def __init__(self, session_id: str, ws_manager: Any, sample_rate: int = 16000):
        self.session_id = session_id
        self.ws_manager = ws_manager
        self.sample_rate = sample_rate
        self._stt = None
        self._extractor = None
        self._transcript_buffer: List[str] = []
        self._last_extraction_at: float = 0
        self._extraction_interval = 5.0
        self._running = False
        self._extraction_lock = asyncio.Lock()
        self._pending_extraction: Optional[asyncio.Task] = None
        # Audio arriving before the STT socket is up — flushed in start().
        self._early_audio: List[bytes] = []
        # Pipeline diagnostics, surfaced in the /stop response so failures
        # are visible from the device without server log access.
        self.stats: Dict[str, Any] = {
            "deepgram_key_present": bool(DEEPGRAM_API_KEY),
            "audio_chunks_received": 0,
            "audio_bytes_received": 0,
            "early_buffered": 0,
            "stt_provider": None,
            "stt_status": None,
            "transcript_lines": 0,
        }

    async def start(self):
        self._running = True

        # Extraction is optional — a failed LLM client init (missing key,
        # SDK issue) must not take down live transcription with it.
        try:
            from .llm_client import create_llm_client
            from .unified_extractor import UnifiedExtractionEngine
            llm_client = create_llm_client()
            self._extractor = UnifiedExtractionEngine(llm_client)
        except Exception as e:
            logger.error(f"[LiveCI] Extractor init failed (transcription continues): {e}")
            self.stats["extractor_error"] = str(e)[:200]
            self._extractor = None

        if DEEPGRAM_API_KEY:
            from .stt_fallback_service import STTFallbackService
            self._stt = STTFallbackService(
                deepgram_key=DEEPGRAM_API_KEY,
                assemblyai_key=ASSEMBLYAI_API_KEY or None,
                on_transcript=self._on_stt_transcript,
                on_status_change=self._on_stt_status,
            )
            try:
                await self._stt.connect(self.session_id, sample_rate=self.sample_rate)
                logger.info(f"[LiveCI] STT connected for session {self.session_id}")
            except Exception as e:
                logger.error(f"[LiveCI] STT connect failed: {e}")
                self._stt = None
        else:
            logger.error(
                f"[LiveCI] DEEPGRAM_API_KEY not set — no live transcription "
                f"for session {self.session_id}"
            )

        if self._stt and self._early_audio:
            queued, self._early_audio = self._early_audio, []
            for chunk in queued:
                try:
                    await self._stt.send_audio(chunk)
                except Exception:
                    break
            logger.info(f"[LiveCI] Flushed {len(queued)} early audio chunks")

        await self.ws_manager.send(self.session_id, {
            "event": "agent_update",
            "agent_type": "transcription",
            "status": "active",
            "message": "Listening for speech...",
            "field_count": 0,
        })

    async def feed_audio(self, audio_bytes: bytes):
        self.stats["audio_chunks_received"] += 1
        self.stats["audio_bytes_received"] += len(audio_bytes)
        if self._stt and self._running:
            try:
                await self._stt.send_audio(audio_bytes)
            except Exception as e:
                logger.error(f"[LiveCI] send_audio error: {e}")
        elif not self._stt and len(self._early_audio) < 200:
            # start() hasn't finished connecting STT yet — hold the audio.
            self._early_audio.append(audio_bytes)
            self.stats["early_buffered"] += 1

    async def feed_transcript_text(self, text: str, is_final: bool = True):
        """For browser-mode: accept text transcripts directly (no audio)."""
        if not self._running:
            return
        self._transcript_buffer.append(text)

        await self._emit_transcript_line(text, is_final)
        await self.ws_manager.send(self.session_id, {
            "event": "agent_update",
            "agent_type": "transcription",
            "status": "active",
            "message": text[:100],
            "field_count": 0,
        })

        if is_final:
            await self._maybe_extract()

    async def _emit_transcript_line(self, text: str, is_final: bool, speaker: str = "borrower"):
        """The frontend's transcript pane only renders 'transcript_line' events."""
        await self.ws_manager.send(self.session_id, {
            "event": "transcript_line",
            "id": str(uuid4()),
            "text": text,
            "speaker": speaker,
            "is_final": is_final,
            "timestamp": time.time(),
        })

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

        # Deepgram (and the normalized AssemblyAI payload) nest the text at
        # channel.alternatives[0].transcript — there is no top-level "text".
        alternatives = (result.get("channel") or {}).get("alternatives") or [{}]
        text = alternatives[0].get("transcript", "") or result.get("text", "")
        is_final = result.get("is_final", True)

        if not text.strip():
            return

        self.stats["transcript_lines"] += 1
        if is_final:
            self._transcript_buffer.append(text)

        await self._emit_transcript_line(text, is_final)
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
        provider_str = provider.value if hasattr(provider, 'value') else str(provider)
        self.stats["stt_status"] = status_str
        self.stats["stt_provider"] = provider_str
        logger.info(f"[LiveCI] STT status: {status_str} ({provider_str})")

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


async def activate_live_session(
    session_id: str, ws_manager: Any, sample_rate: int = 16000
) -> LiveSessionRunner:
    if session_id in _active_sessions:
        return _active_sessions[session_id]

    # Register BEFORE start(): the STT connect can take seconds, and audio
    # arriving in that window must reach the runner's early buffer rather
    # than being dropped by get_live_session() returning None.
    runner = LiveSessionRunner(session_id, ws_manager, sample_rate=sample_rate)
    _active_sessions[session_id] = runner
    try:
        await runner.start()
    except Exception:
        _active_sessions.pop(session_id, None)
        raise
    return runner


async def stop_live_session(session_id: str):
    runner = _active_sessions.pop(session_id, None)
    if runner:
        await runner.stop()


def get_live_session(session_id: str) -> Optional[LiveSessionRunner]:
    return _active_sessions.get(session_id)
