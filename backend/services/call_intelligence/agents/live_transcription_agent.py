"""
Live Transcription Agent

Real-time speech-to-text agent that integrates with Deepgram STT for
word-level timestamps during live mortgage calls. Streams transcript
chunks via callback, maintains a running transcript buffer in memory,
and flushes to the database periodically.

This agent runs in parallel with other live call agents during every
active call session.

Architecture:
    - Receives raw audio frames or pre-transcribed chunks from Deepgram
    - Produces word-level timestamped transcript segments
    - Buffers segments and flushes to DB every FLUSH_INTERVAL_SECONDS
    - Notifies downstream agents (sentiment, objection, compliance, coaching)
      via the on_transcript_chunk callback
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WordTimestamp:
    """A single word with its timing information from Deepgram."""
    word: str
    start: float  # seconds from call start
    end: float
    confidence: float = 1.0
    speaker: Optional[int] = None  # Deepgram diarisation speaker index


@dataclass
class TranscriptChunk:
    """An accumulated utterance chunk ready for downstream processing."""
    chunk_id: str
    text: str
    speaker: str  # "lo" or "borrower" or "unknown"
    words: List[WordTimestamp]
    start_time: float
    end_time: float
    is_final: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLUSH_INTERVAL_SECONDS = 15.0  # How often to persist transcript to DB
MAX_BUFFER_CHUNKS = 200  # Safety cap to prevent unbounded memory growth
DEEPGRAM_MODEL = "nova-2"  # Deepgram model for mortgage domain
DEEPGRAM_LANGUAGE = "en-US"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class LiveTranscriptionAgent:
    """Real-time Deepgram STT integration for live mortgage calls.

    Processes incoming audio/transcript data, produces word-level timestamped
    chunks, buffers them in memory, and flushes to the database periodically.
    Downstream agents receive chunks via the on_chunk callback.

    Usage:
        agent = LiveTranscriptionAgent(db=session)
        agent.on_chunk = my_callback  # async def my_callback(chunk: TranscriptChunk)
        result = await agent.process(transcript_chunk, call_context)
    """

    def __init__(self, db: Session = None):
        self.db = db
        self._buffer: List[TranscriptChunk] = []
        self._full_transcript: List[TranscriptChunk] = []
        self._last_flush_time: float = time.monotonic()
        self._chunk_counter: int = 0
        self._call_id: Optional[str] = None
        self._is_active: bool = False

        # Callback for downstream agents — set externally
        self.on_chunk: Optional[
            Callable[[TranscriptChunk], Coroutine[Any, Any, None]]
        ] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, transcript_chunk: str, call_context: dict) -> dict:
        """Process a raw transcript chunk from the STT stream.

        Args:
            transcript_chunk: The text content (may be interim or final).
            call_context: Dict with keys like call_id, speaker, is_final,
                          words (list of word-level dicts from Deepgram),
                          start_time, end_time.

        Returns:
            Dict with transcript_chunk info, buffer_size, total_chunks,
            and whether a DB flush occurred.
        """
        try:
            if not self._is_active:
                self._call_id = call_context.get("call_id", str(uuid.uuid4()))
                self._is_active = True
                logger.info(
                    "LiveTranscriptionAgent started for call %s", self._call_id
                )

            # Build word timestamps from Deepgram payload
            words = self._parse_words(call_context.get("words", []))

            # Determine speaker
            speaker = self._resolve_speaker(call_context)

            self._chunk_counter += 1
            chunk = TranscriptChunk(
                chunk_id=f"{self._call_id}_{self._chunk_counter}",
                text=transcript_chunk.strip(),
                speaker=speaker,
                words=words,
                start_time=call_context.get("start_time", 0.0),
                end_time=call_context.get("end_time", 0.0),
                is_final=call_context.get("is_final", True),
            )

            # Only buffer final utterances (skip interim partials)
            if chunk.is_final and chunk.text:
                self._buffer.append(chunk)
                self._full_transcript.append(chunk)

                # Safety cap
                if len(self._buffer) > MAX_BUFFER_CHUNKS:
                    logger.warning(
                        "Buffer exceeded %d chunks, forcing flush",
                        MAX_BUFFER_CHUNKS,
                    )
                    await self._flush_to_db()

            # Notify downstream agents
            if self.on_chunk and chunk.is_final and chunk.text:
                try:
                    await self.on_chunk(chunk)
                except Exception as e:
                    logger.error(
                        "on_chunk callback failed: %s", e, exc_info=True
                    )

            # Periodic flush
            flushed = False
            elapsed = time.monotonic() - self._last_flush_time
            if elapsed >= FLUSH_INTERVAL_SECONDS and self._buffer:
                await self._flush_to_db()
                flushed = True

            return {
                "agent": "live_transcription",
                "call_id": self._call_id,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "speaker": chunk.speaker,
                "word_count": len(chunk.words),
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "is_final": chunk.is_final,
                "buffer_size": len(self._buffer),
                "total_chunks": len(self._full_transcript),
                "flushed_to_db": flushed,
            }

        except Exception as e:
            logger.error(
                "LiveTranscriptionAgent.process failed: %s", e, exc_info=True
            )
            return {
                "agent": "live_transcription",
                "error": str(e),
                "call_id": self._call_id,
                "buffer_size": len(self._buffer),
                "total_chunks": len(self._full_transcript),
            }

    async def finalize(self) -> dict:
        """Flush remaining buffer and return the full transcript.

        Should be called when the call ends.
        """
        try:
            if self._buffer:
                await self._flush_to_db()

            full_text = "\n".join(
                f"[{c.speaker}] {c.text}" for c in self._full_transcript
            )
            logger.info(
                "LiveTranscriptionAgent finalized call %s — %d chunks",
                self._call_id,
                len(self._full_transcript),
            )
            self._is_active = False

            return {
                "agent": "live_transcription",
                "call_id": self._call_id,
                "total_chunks": len(self._full_transcript),
                "full_transcript": full_text,
                "finalized": True,
            }
        except Exception as e:
            logger.error(
                "LiveTranscriptionAgent.finalize failed: %s", e, exc_info=True
            )
            return {
                "agent": "live_transcription",
                "error": str(e),
                "finalized": False,
            }

    def get_running_transcript(self) -> str:
        """Return the full transcript assembled so far."""
        return "\n".join(
            f"[{c.speaker}] {c.text}" for c in self._full_transcript
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_words(self, raw_words: list) -> List[WordTimestamp]:
        """Parse Deepgram word-level timing data."""
        words: List[WordTimestamp] = []
        for w in raw_words:
            try:
                words.append(
                    WordTimestamp(
                        word=w.get("word", w.get("punctuated_word", "")),
                        start=float(w.get("start", 0.0)),
                        end=float(w.get("end", 0.0)),
                        confidence=float(w.get("confidence", 1.0)),
                        speaker=w.get("speaker"),
                    )
                )
            except (TypeError, ValueError) as e:
                logger.debug("Skipping malformed word entry: %s", e)
        return words

    def _resolve_speaker(self, call_context: dict) -> str:
        """Determine speaker label from call context."""
        speaker = call_context.get("speaker", "unknown")
        if isinstance(speaker, int):
            # Deepgram diarisation index — 0 is typically the LO (caller)
            return "lo" if speaker == 0 else "borrower"
        if isinstance(speaker, str):
            normalized = speaker.lower().strip()
            if normalized in ("lo", "loan_officer", "agent"):
                return "lo"
            if normalized in ("borrower", "customer", "client", "lead"):
                return "borrower"
        return "unknown"

    async def _flush_to_db(self) -> None:
        """Persist buffered chunks to the database."""
        if not self._buffer:
            return

        chunks_to_flush = list(self._buffer)
        self._buffer.clear()
        self._last_flush_time = time.monotonic()

        if not self.db:
            logger.debug(
                "No DB session — skipping flush of %d chunks",
                len(chunks_to_flush),
            )
            return

        try:
            # Store as a JSON-serialisable batch in the call_transcripts table
            # (or whichever model the caller has wired up).  We keep this
            # intentionally lightweight — the route layer owns the exact model.
            from database.models import CallTranscript  # noqa: lazy import

            for chunk in chunks_to_flush:
                record = CallTranscript(
                    call_id=self._call_id,
                    chunk_index=int(chunk.chunk_id.rsplit("_", 1)[-1]),
                    speaker=chunk.speaker,
                    text=chunk.text,
                    start_time=chunk.start_time,
                    end_time=chunk.end_time,
                    word_timestamps=[
                        {
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "confidence": w.confidence,
                        }
                        for w in chunk.words
                    ],
                    created_at=chunk.created_at,
                )
                self.db.add(record)

            self.db.commit()
            logger.debug(
                "Flushed %d transcript chunks to DB for call %s",
                len(chunks_to_flush),
                self._call_id,
            )
        except Exception as e:
            logger.error(
                "DB flush failed for call %s: %s", self._call_id, e,
                exc_info=True,
            )
            try:
                self.db.rollback()
            except Exception:
                pass
