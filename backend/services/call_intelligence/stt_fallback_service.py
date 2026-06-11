# =============================================================================
# PERENNIA AI — Call Intelligence: STT Fallback Service
# Addresses audit finding: Deepgram is single point of failure
#
# Strategy:
#   1. PRIMARY: Deepgram Nova-2 (real-time streaming)
#   2. FALLBACK: AssemblyAI (real-time streaming, auto-switch on Deepgram failure)
#   3. DEGRADED: Record audio, transcribe post-call (if both streaming STT fail)
#
# The LO is never left with a dead CI session. At minimum, audio is captured
# and transcribed after the call with full agent processing applied post-call.
# =============================================================================

import logging
import asyncio
import json
import time
from enum import Enum
from typing import Optional, Dict, Any, Callable, Awaitable
from uuid import uuid4

import httpx
import websockets

logger = logging.getLogger(__name__)


class STTProvider(str, Enum):
    DEEPGRAM = "deepgram"
    ASSEMBLYAI = "assemblyai"
    DEGRADED = "degraded"


class STTStatus(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    DEGRADED = "degraded"


class STTFallbackService:
    """
    Manages STT provider connections with automatic failover.

    Usage:
        stt = STTFallbackService(
            deepgram_key="...",
            assemblyai_key="...",
            on_transcript=my_handler,
        )
        await stt.connect(session_id)
        await stt.send_audio(audio_bytes)
        await stt.disconnect()
    """

    def __init__(
        self,
        deepgram_key: str,
        assemblyai_key: Optional[str] = None,
        on_transcript: Optional[Callable[[str, Dict], Awaitable[None]]] = None,
        on_status_change: Optional[Callable[[str, STTStatus, str], Awaitable[None]]] = None,
        max_reconnect_attempts: int = 3,
        reconnect_delay_seconds: float = 2.0,
    ):
        self.deepgram_key = deepgram_key
        self.assemblyai_key = assemblyai_key
        self.on_transcript = on_transcript
        self.on_status_change = on_status_change
        self.max_reconnect = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay_seconds

        self._ws = None
        self._provider: STTProvider = STTProvider.DEEPGRAM
        self._status: STTStatus = STTStatus.CONNECTING
        self._session_id: Optional[str] = None
        self._reconnect_count = 0
        self._audio_buffer: list = []
        self._receive_task: Optional[asyncio.Task] = None
        self._sample_rate: int = 16000
        # Audio arriving while CONNECTING/RECONNECTING — flushed on connect
        # instead of silently dropped.
        self._pending_chunks: list = []

    @property
    def provider(self) -> STTProvider:
        return self._provider

    @property
    def status(self) -> STTStatus:
        return self._status

    # -----------------------------------------------------------------
    # Connection Lifecycle
    # -----------------------------------------------------------------

    async def connect(
        self,
        session_id: str,
        model: str = "nova-2",
        language: str = "en-US",
        enable_diarization: bool = True,
        sample_rate: int = 16000,
    ) -> bool:
        self._session_id = session_id
        self._reconnect_count = 0
        self._sample_rate = sample_rate

        if self.deepgram_key:
            success = await self._connect_deepgram(model, language, enable_diarization)
            if success:
                return True

        if self.assemblyai_key:
            logger.warning(f"Session {session_id}: Deepgram failed, trying AssemblyAI")
            success = await self._connect_assemblyai(language)
            if success:
                return True

        logger.error(f"Session {session_id}: All STT providers failed. Entering degraded mode.")
        await self._enter_degraded_mode()
        return True

    async def send_audio(self, audio_data: bytes):
        if self._status == STTStatus.DEGRADED:
            self._audio_buffer.append(audio_data)
            return

        if self._ws and self._status == STTStatus.CONNECTED:
            try:
                await self._ws.send(audio_data)
            except Exception as e:
                logger.error(f"STT send error: {e}")
                await self._handle_disconnect()
            return

        # CONNECTING / RECONNECTING — hold a few seconds of audio instead of
        # dropping the start of the conversation; flushed on connect.
        if len(self._pending_chunks) < 200:
            self._pending_chunks.append(audio_data)

    async def disconnect(self) -> Optional[str]:
        audio_file = None

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            try:
                if self._provider == STTProvider.DEEPGRAM:
                    await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:
                pass

        if self._status == STTStatus.DEGRADED and self._audio_buffer:
            audio_file = await self._save_audio_buffer()

        self._ws = None
        self._status = STTStatus.FAILED
        self._audio_buffer.clear()

        return audio_file

    # -----------------------------------------------------------------
    # Deepgram Connection
    # -----------------------------------------------------------------

    async def _connect_deepgram(
        self, model: str, language: str, diarization: bool
    ) -> bool:
        # encoding/sample_rate/channels are REQUIRED for raw PCM16 — Deepgram
        # only auto-detects containerized audio (WAV/Opus/MP3). Without them
        # the stream is undecodable and returns zero Results.
        params = (
            f"model={model}&language={language}&smart_format=true"
            f"&punctuate=true&utterances=true&interim_results=true"
            f"&encoding=linear16&sample_rate={self._sample_rate}&channels=1"
        )
        if diarization:
            params += "&diarize=true"

        url = f"wss://api.deepgram.com/v1/listen?{params}"

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    extra_headers={"Authorization": f"Token {self.deepgram_key}"},
                    ping_interval=20,
                    ping_timeout=10,
                ),
                timeout=10.0,
            )

            self._provider = STTProvider.DEEPGRAM
            await self._set_status(STTStatus.CONNECTED)
            self._receive_task = asyncio.create_task(self._receive_deepgram())

            logger.info(f"Session {self._session_id}: Deepgram connected ({model})")
            return True

        except Exception as e:
            logger.error(f"Deepgram connection failed: {e}")
            return False

    async def _receive_deepgram(self):
        try:
            async for message in self._ws:
                data = json.loads(message)

                if data.get("type") == "Results":
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])
                    if alternatives and alternatives[0].get("transcript", "").strip():
                        if self.on_transcript:
                            await self.on_transcript(self._session_id, data)

        except websockets.ConnectionClosed as e:
            logger.warning(f"Deepgram WebSocket closed: {e}")
            await self._handle_disconnect()
        except Exception as e:
            logger.error(f"Deepgram receive error: {e}")
            await self._handle_disconnect()

    # -----------------------------------------------------------------
    # AssemblyAI Connection
    # -----------------------------------------------------------------

    async def _connect_assemblyai(self, language: str) -> bool:
        url = "wss://api.assemblyai.com/v2/realtime/ws"

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    extra_headers={"Authorization": self.assemblyai_key},
                    ping_interval=20,
                ),
                timeout=10.0,
            )

            await self._ws.send(json.dumps({
                "sample_rate": self._sample_rate,
                "word_boost": [
                    "mortgage", "refinance", "FHA", "VA", "USDA",
                    "pre-approval", "down payment", "closing costs",
                    "DTI", "appraisal", "escrow",
                ],
            }))

            self._provider = STTProvider.ASSEMBLYAI
            await self._set_status(STTStatus.CONNECTED)
            self._receive_task = asyncio.create_task(self._receive_assemblyai())

            logger.info(f"Session {self._session_id}: AssemblyAI connected (fallback)")
            return True

        except Exception as e:
            logger.error(f"AssemblyAI connection failed: {e}")
            return False

    async def _receive_assemblyai(self):
        try:
            async for message in self._ws:
                data = json.loads(message)
                msg_type = data.get("message_type")

                if msg_type in ("PartialTranscript", "FinalTranscript"):
                    text = data.get("text", "").strip()
                    if text and self.on_transcript:
                        normalized = {
                            "type": "Results",
                            "is_final": msg_type == "FinalTranscript",
                            "channel": {
                                "alternatives": [{
                                    "transcript": text,
                                    "confidence": data.get("confidence", 0.0),
                                    "words": data.get("words", []),
                                }]
                            },
                            "_source": "assemblyai",
                        }
                        await self.on_transcript(self._session_id, normalized)

        except websockets.ConnectionClosed:
            await self._handle_disconnect()
        except Exception as e:
            logger.error(f"AssemblyAI receive error: {e}")
            await self._handle_disconnect()

    # -----------------------------------------------------------------
    # Degraded Mode
    # -----------------------------------------------------------------

    async def _enter_degraded_mode(self):
        self._provider = STTProvider.DEGRADED
        await self._set_status(STTStatus.DEGRADED)
        self._audio_buffer = []

        logger.warning(
            f"Session {self._session_id}: Degraded mode — recording audio only"
        )

    async def _save_audio_buffer(self) -> str:
        import wave
        import tempfile
        import os

        filepath = os.path.join(
            tempfile.gettempdir(),
            f"ci-audio-{self._session_id}.wav",
        )

        audio_data = b"".join(self._audio_buffer)

        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(audio_data)

        size_mb = len(audio_data) / (1024 * 1024)
        logger.info(
            f"Session {self._session_id}: Audio buffer saved "
            f"({size_mb:.1f} MB) to {filepath}"
        )

        return filepath

    async def transcribe_post_call(
        self, audio_filepath: str
    ) -> Optional[Dict]:
        if self.deepgram_key:
            try:
                with open(audio_filepath, "rb") as f:
                    audio_data = f.read()

                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        "https://api.deepgram.com/v1/listen?"
                        "model=nova-2&smart_format=true&diarize=true&utterances=true",
                        headers={
                            "Authorization": f"Token {self.deepgram_key}",
                            "Content-Type": "audio/wav",
                        },
                        content=audio_data,
                    )
                    if response.status_code == 200:
                        return response.json()

            except Exception as e:
                logger.error(f"Deepgram batch transcription failed: {e}")

        if self.assemblyai_key:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    with open(audio_filepath, "rb") as f:
                        upload = await client.post(
                            "https://api.assemblyai.com/v2/upload",
                            headers={"Authorization": self.assemblyai_key},
                            content=f.read(),
                        )
                    upload_url = upload.json().get("upload_url")

                    resp = await client.post(
                        "https://api.assemblyai.com/v2/transcript",
                        headers={"Authorization": self.assemblyai_key},
                        json={
                            "audio_url": upload_url,
                            "speaker_labels": True,
                            "language_code": "en_us",
                        },
                    )
                    transcript_id = resp.json().get("id")

                    for _ in range(60):
                        await asyncio.sleep(5)
                        status_resp = await client.get(
                            f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                            headers={"Authorization": self.assemblyai_key},
                        )
                        result = status_resp.json()
                        if result.get("status") == "completed":
                            return result
                        if result.get("status") == "error":
                            raise Exception(result.get("error"))

            except Exception as e:
                logger.error(f"AssemblyAI batch transcription failed: {e}")

        return None

    # -----------------------------------------------------------------
    # Reconnection
    # -----------------------------------------------------------------

    async def _handle_disconnect(self):
        if self._reconnect_count >= self.max_reconnect:
            if self._provider == STTProvider.DEEPGRAM and self.assemblyai_key:
                logger.warning("Deepgram retries exhausted. Switching to AssemblyAI.")
                self._reconnect_count = 0
                success = await self._connect_assemblyai("en-US")
                if success:
                    return

            await self._enter_degraded_mode()
            return

        self._reconnect_count += 1
        await self._set_status(STTStatus.RECONNECTING)

        logger.info(
            f"STT reconnecting ({self._provider}): "
            f"attempt {self._reconnect_count}/{self.max_reconnect}"
        )

        await asyncio.sleep(self.reconnect_delay * self._reconnect_count)

        if self._provider == STTProvider.DEEPGRAM:
            success = await self._connect_deepgram("nova-2", "en-US", True)
        elif self._provider == STTProvider.ASSEMBLYAI:
            success = await self._connect_assemblyai("en-US")
        else:
            success = False

        if not success:
            await self._handle_disconnect()

    # -----------------------------------------------------------------
    # Status Management
    # -----------------------------------------------------------------

    async def _set_status(self, status: STTStatus):
        old = self._status
        self._status = status

        # Flush audio buffered while the provider socket was connecting.
        if status == STTStatus.CONNECTED and self._pending_chunks and self._ws:
            queued, self._pending_chunks = self._pending_chunks, []
            try:
                for chunk in queued:
                    await self._ws.send(chunk)
                logger.info(f"STT flushed {len(queued)} buffered audio chunks")
            except Exception as e:
                logger.error(f"STT flush error: {e}")

        if self.on_status_change and self._session_id:
            await self.on_status_change(
                self._session_id, status, self._provider
            )

        logger.info(
            f"STT status: {old.value} → {status.value} "
            f"(provider: {self._provider.value})"
        )
