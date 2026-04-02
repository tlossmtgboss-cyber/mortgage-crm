"""
Streaming Extraction for Call Intelligence

Real-time extraction during active calls with incremental updates.
Supports WebSocket-compatible event streaming for live UI updates.

Features:
- Process transcript chunks as they arrive
- Emit partial extraction events
- Accumulate context across chunks
- Final consolidation when call ends
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .llm_client import BaseLLMClient

from .data_contracts import (
    ExtractedValue,
    TranscriptSegment,
    SpeakerRole,
)
from .unified_extractor import UnifiedExtractionEngine, FIELD_TO_DOMAIN
from .pii_utils import sanitize_source_text

logger = logging.getLogger(__name__)


# =============================================================================
# Event Types
# =============================================================================

class ExtractionEventType(str, Enum):
    """Types of extraction events."""
    SESSION_STARTED = "session_started"
    CHUNK_RECEIVED = "chunk_received"
    EXTRACTION_PARTIAL = "extraction_partial"
    EXTRACTION_CONFIRMED = "extraction_confirmed"
    EXTRACTION_UPDATED = "extraction_updated"
    SESSION_ENDED = "session_ended"
    ERROR = "error"


@dataclass
class TranscriptChunk:
    """A chunk of transcript received during streaming."""
    speaker: SpeakerRole
    text: str
    timestamp: float
    chunk_index: int
    is_final: bool = False  # True if this is final text for this utterance


@dataclass
class PartialExtraction:
    """A partial extraction with provisional confidence."""
    field_name: str
    value: Any
    confidence: float
    source_text: str
    domain: str
    is_confirmed: bool = False  # True after full context available


@dataclass
class ExtractionEvent:
    """Event emitted during streaming extraction."""
    event_type: ExtractionEventType
    call_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize for WebSocket transmission."""
        return json.dumps({
            "event": self.event_type.value,
            "call_id": self.call_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        })


@dataclass
class StreamingSession:
    """Active streaming session state."""
    call_id: str
    loan_id: Optional[int]
    organization_id: Optional[int]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Accumulated transcript
    segments: List[TranscriptSegment] = field(default_factory=list)
    raw_text: str = ""

    # Partial extractions
    extractions: Dict[str, PartialExtraction] = field(default_factory=dict)

    # Processing state
    last_extraction_time: Optional[datetime] = None
    chunk_count: int = 0
    is_active: bool = True


# =============================================================================
# Configuration
# =============================================================================

# Minimum interval between extraction attempts (seconds)
MIN_EXTRACTION_INTERVAL = 5.0

# Minimum new text before triggering extraction (characters)
MIN_TEXT_FOR_EXTRACTION = 200

# Confidence threshold for "confirmed" extractions
CONFIRMATION_THRESHOLD = 85.0


class StreamingExtractor:
    """
    Real-time extraction during active calls.

    Usage:
        extractor = StreamingExtractor(llm_client)

        # Start session
        session = await extractor.start_session(call_id, loan_id, org_id)

        # Process chunks as they arrive
        async for event in extractor.process_chunk(call_id, chunk):
            # Send event to WebSocket client
            await websocket.send(event.to_json())

        # End session and get final results
        final = await extractor.end_session(call_id)
    """

    def __init__(self, llm_client: "BaseLLMClient"):
        """
        Initialize streaming extractor.

        Args:
            llm_client: LLM client for extraction
        """
        if llm_client is None:
            raise ValueError("StreamingExtractor requires an LLM client")

        self.llm_client = llm_client
        self._unified_extractor = UnifiedExtractionEngine(llm_client)

        # Active sessions
        self._sessions: Dict[str, StreamingSession] = {}

        # Event queues for each session
        self._event_queues: Dict[str, asyncio.Queue] = {}

    async def start_session(
        self,
        call_id: str,
        loan_id: Optional[int] = None,
        organization_id: Optional[int] = None,
    ) -> StreamingSession:
        """
        Start a new streaming session.

        Args:
            call_id: Unique call identifier
            loan_id: Associated loan ID
            organization_id: Organization ID

        Returns:
            New StreamingSession
        """
        if call_id in self._sessions:
            logger.warning(f"Session {call_id} already exists, ending old session")
            await self.end_session(call_id)

        session = StreamingSession(
            call_id=call_id,
            loan_id=loan_id,
            organization_id=organization_id,
        )

        self._sessions[call_id] = session
        self._event_queues[call_id] = asyncio.Queue()

        # Emit session started event
        await self._emit_event(call_id, ExtractionEvent(
            event_type=ExtractionEventType.SESSION_STARTED,
            call_id=call_id,
            data={
                "loan_id": loan_id,
                "organization_id": organization_id,
            },
        ))

        logger.info(f"Started streaming session: {call_id}")

        return session

    async def process_chunk(
        self,
        call_id: str,
        chunk: TranscriptChunk,
    ) -> AsyncGenerator[ExtractionEvent, None]:
        """
        Process a transcript chunk and emit extraction events.

        Args:
            call_id: Call identifier
            chunk: Transcript chunk to process

        Yields:
            ExtractionEvent objects for UI updates
        """
        session = self._sessions.get(call_id)
        if not session or not session.is_active:
            yield ExtractionEvent(
                event_type=ExtractionEventType.ERROR,
                call_id=call_id,
                data={"error": "No active session"},
            )
            return

        # Add chunk to session
        segment = TranscriptSegment(
            speaker=chunk.speaker,
            text=chunk.text,
            index=chunk.chunk_index,
            start_time=chunk.timestamp,
        )
        session.segments.append(segment)
        session.raw_text += f" {chunk.text}"
        session.chunk_count += 1

        # Emit chunk received
        yield ExtractionEvent(
            event_type=ExtractionEventType.CHUNK_RECEIVED,
            call_id=call_id,
            data={
                "chunk_index": chunk.chunk_index,
                "speaker": chunk.speaker.value,
                "text_length": len(chunk.text),
                "total_length": len(session.raw_text),
            },
        )

        # Check if we should run extraction
        should_extract = self._should_extract(session)

        if should_extract:
            async for event in self._run_extraction(session):
                yield event

    async def get_stream(
        self,
        call_id: str,
    ) -> AsyncGenerator[ExtractionEvent, None]:
        """
        Get WebSocket-compatible event stream for a session.

        Args:
            call_id: Call identifier

        Yields:
            ExtractionEvent objects
        """
        queue = self._event_queues.get(call_id)
        if not queue:
            yield ExtractionEvent(
                event_type=ExtractionEventType.ERROR,
                call_id=call_id,
                data={"error": "No active session"},
            )
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield event

                # Stop if session ended
                if event.event_type == ExtractionEventType.SESSION_ENDED:
                    break

            except asyncio.TimeoutError:
                # Emit heartbeat or continue
                continue

    async def end_session(
        self,
        call_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        End streaming session and return final extractions.

        Args:
            call_id: Call identifier

        Returns:
            Final extraction results
        """
        session = self._sessions.get(call_id)
        if not session:
            return None

        session.is_active = False

        # Run final extraction with full context
        final_result = None
        if session.segments:
            try:
                unified_result = await self._unified_extractor.extract_all(
                    call_id=call_id,
                    segments=session.segments,
                )

                final_result = {
                    "call_id": call_id,
                    "total_extractions": unified_result.total_extractions,
                    "high_confidence_count": unified_result.high_confidence_count,
                    "identity": {k: v.value for k, v in unified_result.identity.items()},
                    "property": {k: v.value for k, v in unified_result.property_info.items()},
                    "employment": {k: v.value for k, v in unified_result.employment.items()},
                    "financial": {k: v.value for k, v in unified_result.financial.items()},
                    "compliance": {k: v.value for k, v in unified_result.compliance.items()},
                    "intent": {k: v.value for k, v in unified_result.intent.items()},
                }

            except Exception as e:
                logger.exception(f"Final extraction failed for {call_id}: {e}")
                final_result = {
                    "call_id": call_id,
                    "error": "Internal server error",
                    "partial_extractions": {
                        k: {"value": v.value, "confidence": v.confidence}
                        for k, v in session.extractions.items()
                    },
                }

        # Emit session ended event
        await self._emit_event(call_id, ExtractionEvent(
            event_type=ExtractionEventType.SESSION_ENDED,
            call_id=call_id,
            data=final_result or {},
        ))

        # Cleanup
        del self._sessions[call_id]
        if call_id in self._event_queues:
            del self._event_queues[call_id]

        logger.info(f"Ended streaming session: {call_id}")

        return final_result

    def get_session_status(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get current session status."""
        session = self._sessions.get(call_id)
        if not session:
            return None

        return {
            "call_id": call_id,
            "is_active": session.is_active,
            "chunk_count": session.chunk_count,
            "text_length": len(session.raw_text),
            "extraction_count": len(session.extractions),
            "confirmed_count": sum(
                1 for e in session.extractions.values() if e.is_confirmed
            ),
            "created_at": session.created_at.isoformat(),
        }

    def _should_extract(self, session: StreamingSession) -> bool:
        """Determine if we should run extraction on current state."""
        # Don't extract too frequently
        if session.last_extraction_time:
            elapsed = (datetime.now(timezone.utc) - session.last_extraction_time).total_seconds()
            if elapsed < MIN_EXTRACTION_INTERVAL:
                return False

        # Need minimum text
        if len(session.raw_text) < MIN_TEXT_FOR_EXTRACTION:
            return False

        return True

    async def _run_extraction(
        self,
        session: StreamingSession,
    ) -> AsyncGenerator[ExtractionEvent, None]:
        """Run extraction on current session state."""
        session.last_extraction_time = datetime.now(timezone.utc)

        try:
            # Use unified extractor
            result = await self._unified_extractor.extract_all(
                call_id=session.call_id,
                segments=session.segments,
            )

            # Process each domain
            for domain_name, domain_extractions in [
                ("identity", result.identity),
                ("property", result.property_info),
                ("employment", result.employment),
                ("financial", result.financial),
                ("compliance", result.compliance),
                ("intent", result.intent),
            ]:
                for field_name, extracted in domain_extractions.items():
                    existing = session.extractions.get(field_name)

                    # Create partial extraction
                    partial = PartialExtraction(
                        field_name=field_name,
                        value=extracted.value,
                        confidence=extracted.confidence,
                        source_text=extracted.source_text,
                        domain=domain_name,
                        is_confirmed=extracted.confidence >= CONFIRMATION_THRESHOLD,
                    )

                    if not existing:
                        # New extraction
                        session.extractions[field_name] = partial
                        yield ExtractionEvent(
                            event_type=ExtractionEventType.EXTRACTION_PARTIAL,
                            call_id=session.call_id,
                            data={
                                "field_name": field_name,
                                "value": extracted.value,
                                "confidence": extracted.confidence,
                                "domain": domain_name,
                                "is_confirmed": partial.is_confirmed,
                            },
                        )

                    elif existing.value != extracted.value:
                        # Value changed
                        session.extractions[field_name] = partial
                        yield ExtractionEvent(
                            event_type=ExtractionEventType.EXTRACTION_UPDATED,
                            call_id=session.call_id,
                            data={
                                "field_name": field_name,
                                "old_value": existing.value,
                                "new_value": extracted.value,
                                "confidence": extracted.confidence,
                                "domain": domain_name,
                            },
                        )

                    elif not existing.is_confirmed and partial.is_confirmed:
                        # Confidence increased to confirmed
                        session.extractions[field_name] = partial
                        yield ExtractionEvent(
                            event_type=ExtractionEventType.EXTRACTION_CONFIRMED,
                            call_id=session.call_id,
                            data={
                                "field_name": field_name,
                                "value": extracted.value,
                                "confidence": extracted.confidence,
                                "domain": domain_name,
                            },
                        )

        except Exception as e:
            logger.warning(f"Streaming extraction failed for {session.call_id}: {e}")
            yield ExtractionEvent(
                event_type=ExtractionEventType.ERROR,
                call_id=session.call_id,
                data={"error": "Internal server error"},
            )

    async def _emit_event(self, call_id: str, event: ExtractionEvent) -> None:
        """Emit event to session queue."""
        queue = self._event_queues.get(call_id)
        if queue:
            await queue.put(event)


# =============================================================================
# Factory
# =============================================================================

def create_streaming_extractor(llm_client: "BaseLLMClient") -> StreamingExtractor:
    """
    Create streaming extractor instance.

    Args:
        llm_client: LLM client (required)

    Returns:
        Configured StreamingExtractor
    """
    return StreamingExtractor(llm_client)
