# =============================================================================
# PERENNIA AI — Call Intelligence: Transcript Processor
# Extracted from orchestrator_service.py (91KB → 4 modules)
#
# This module handles:
#   - Deepgram WebSocket connection lifecycle
#   - STT provider abstraction (Deepgram primary, fallback providers)
#   - Transcript chunk normalization
#   - Speaker diarization mapping
#   - PII redaction before storage
#   - Transcript accumulation and search
# =============================================================================

import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, List, AsyncGenerator
from uuid import uuid4

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


PII_PATTERNS = {
    "ssn": (re.compile(r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b'), "[REDACTED_SSN]"),
    "ssn_verbal": (
        re.compile(r'\b(?:social|social security)\s+(?:is|number)?\s*\d[\d\s]{7,}\d\b', re.I),
        "[REDACTED_SSN]"
    ),
    "credit_card": (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), "[REDACTED_CC]"),
    "dob_verbal": (
        re.compile(
            r'\b(?:born|birthday|date of birth|dob)\s+(?:is|was)?\s*'
            r'(?:january|february|march|april|may|june|july|august|september|october|november|december)'
            r'\s+\d{1,2},?\s+\d{4}\b',
            re.I,
        ),
        "[REDACTED_DOB]",
    ),
    "bank_account": (
        re.compile(r'\b(?:account|routing)\s+(?:number|#)?\s*\d{8,17}\b', re.I),
        "[REDACTED_ACCOUNT]"
    ),
}


class TranscriptChunk:
    """Normalized transcript chunk from any STT provider."""

    def __init__(
        self,
        chunk_id: str,
        session_id: str,
        sequence: int,
        text: str,
        speaker: str,
        start_time_ms: int,
        end_time_ms: int,
        confidence: float,
        is_final: bool,
        raw_text: str,
    ):
        self.chunk_id = chunk_id
        self.session_id = session_id
        self.sequence = sequence
        self.text = text
        self.speaker = speaker
        self.start_time_ms = start_time_ms
        self.end_time_ms = end_time_ms
        self.confidence = confidence
        self.is_final = is_final
        self.raw_text = raw_text

    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "text": self.text,
            "speaker": self.speaker,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "confidence": self.confidence,
            "is_final": self.is_final,
        }


class TranscriptProcessor:
    """
    Processes incoming STT results into normalized, PII-redacted transcript chunks.
    Provider-agnostic: accepts results from Deepgram, AssemblyAI, or any STT.
    """

    def __init__(self, db: AsyncSession, ws_manager: Any = None):
        self.db = db
        self.ws_manager = ws_manager
        self._sequence_counters: Dict[str, int] = {}
        self._speaker_map: Dict[str, Dict[int, str]] = {}

    # -----------------------------------------------------------------
    # Normalize from STT providers
    # -----------------------------------------------------------------

    def normalize_deepgram(
        self, session_id: str, dg_result: Dict
    ) -> Optional[TranscriptChunk]:
        channel = dg_result.get("channel", {})
        alternatives = channel.get("alternatives", [])
        if not alternatives:
            return None

        alt = alternatives[0]
        text = alt.get("transcript", "").strip()
        if not text:
            return None

        words = alt.get("words", [])
        start_ms = int(words[0]["start"] * 1000) if words else 0
        end_ms = int(words[-1]["end"] * 1000) if words else 0

        speaker_id = words[0].get("speaker", 0) if words else 0
        speaker = self._resolve_speaker(session_id, speaker_id)

        seq = self._next_sequence(session_id)
        raw_text = text
        redacted_text = self._redact_pii(text)

        return TranscriptChunk(
            chunk_id=str(uuid4()),
            session_id=session_id,
            sequence=seq,
            text=redacted_text,
            speaker=speaker,
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            confidence=alt.get("confidence", 0.0),
            is_final=dg_result.get("is_final", False),
            raw_text=raw_text,
        )

    def normalize_assemblyai(
        self, session_id: str, aai_result: Dict
    ) -> Optional[TranscriptChunk]:
        text = aai_result.get("text", "").strip()
        if not text:
            return None

        seq = self._next_sequence(session_id)
        raw_text = text
        redacted_text = self._redact_pii(text)

        return TranscriptChunk(
            chunk_id=str(uuid4()),
            session_id=session_id,
            sequence=seq,
            text=redacted_text,
            speaker=self._resolve_speaker(
                session_id, aai_result.get("speaker", "A")
            ),
            start_time_ms=aai_result.get("audio_start", 0),
            end_time_ms=aai_result.get("audio_end", 0),
            confidence=aai_result.get("confidence", 0.0),
            is_final=aai_result.get("message_type") == "FinalTranscript",
            raw_text=raw_text,
        )

    # -----------------------------------------------------------------
    # Processing Pipeline
    # -----------------------------------------------------------------

    async def process_chunk(
        self, chunk: TranscriptChunk
    ) -> TranscriptChunk:
        await self._persist_chunk(chunk)

        if self.ws_manager:
            await self.ws_manager.send(chunk.session_id, {
                "event": "transcript_chunk",
                "data": chunk.to_dict(),
            })

        return chunk

    async def get_full_transcript(
        self, session_id: str, include_speakers: bool = True
    ) -> str:
        result = await self.db.execute(
            sa_text("""
                SELECT text, speaker FROM transcript_chunks
                WHERE session_id = :sid AND is_final = true
                ORDER BY sequence
            """),
            {"sid": session_id},
        )
        rows = result.fetchall()

        if include_speakers:
            return "\n".join(
                f"[{r.speaker}]: {r.text}" for r in rows
            )
        return " ".join(r.text for r in rows)

    async def get_transcript_window(
        self, session_id: str, last_n_chunks: int = 20
    ) -> List[Dict]:
        result = await self.db.execute(
            sa_text("""
                SELECT chunk_id, text, speaker, start_time_ms, end_time_ms, confidence
                FROM transcript_chunks
                WHERE session_id = :sid AND is_final = true
                ORDER BY sequence DESC
                LIMIT :n
            """),
            {"sid": session_id, "n": last_n_chunks},
        )
        rows = result.fetchall()
        return [dict(r._mapping) for r in reversed(rows)]

    # -----------------------------------------------------------------
    # PII Redaction
    # -----------------------------------------------------------------

    def _redact_pii(self, text: str) -> str:
        redacted = text
        for pattern_name, (pattern, replacement) in PII_PATTERNS.items():
            redacted = pattern.sub(replacement, redacted)
        return redacted

    # -----------------------------------------------------------------
    # Speaker Resolution
    # -----------------------------------------------------------------

    def set_speaker_map(self, session_id: str, mapping: Dict[int, str]):
        self._speaker_map[session_id] = mapping

    def _resolve_speaker(self, session_id: str, speaker_id: Any) -> str:
        mapping = self._speaker_map.get(session_id, {})

        if isinstance(speaker_id, int):
            return mapping.get(speaker_id, f"speaker_{speaker_id}")
        if isinstance(speaker_id, str):
            idx = ord(speaker_id) - ord("A") if len(speaker_id) == 1 else 0
            return mapping.get(idx, f"speaker_{speaker_id}")

        return "unknown"

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    def _next_sequence(self, session_id: str) -> int:
        seq = self._sequence_counters.get(session_id, 0) + 1
        self._sequence_counters[session_id] = seq
        return seq

    async def _persist_chunk(self, chunk: TranscriptChunk):
        await self.db.execute(
            sa_text("""
                INSERT INTO transcript_chunks (
                    id, session_id, sequence, text, speaker,
                    start_time_ms, end_time_ms, confidence, is_final,
                    created_at
                ) VALUES (
                    :id, :sid, :seq, :text, :speaker,
                    :start, :end, :conf, :final,
                    NOW()
                )
                ON CONFLICT (session_id, sequence) DO UPDATE
                SET text = :text, is_final = :final
            """),
            {
                "id": chunk.chunk_id,
                "sid": chunk.session_id,
                "seq": chunk.sequence,
                "text": chunk.text,
                "speaker": chunk.speaker,
                "start": chunk.start_time_ms,
                "end": chunk.end_time_ms,
                "conf": chunk.confidence,
                "final": chunk.is_final,
            },
        )
        await self.db.commit()

    def cleanup_session(self, session_id: str):
        self._sequence_counters.pop(session_id, None)
        self._speaker_map.pop(session_id, None)
