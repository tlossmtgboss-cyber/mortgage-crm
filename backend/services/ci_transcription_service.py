"""
Conversation Intelligence - Transcription Service

Handles transcription of call recordings using multiple providers:
- Deepgram (primary)
- AssemblyAI (backup)
- OpenAI Whisper (fallback)

Features:
- Speaker diarization
- Sentiment per segment
- Word-level timing
- Real-time transcription support
"""

import os
import json
import asyncio
import aiohttp
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class TranscriptionProvider(str, Enum):
    DEEPGRAM = "deepgram"
    ASSEMBLYAI = "assemblyai"
    WHISPER = "whisper"


@dataclass
class TranscriptionConfig:
    """Configuration for transcription."""
    provider: TranscriptionProvider = TranscriptionProvider.DEEPGRAM
    language: str = "en"
    enable_diarization: bool = True
    enable_punctuation: bool = True
    enable_word_timestamps: bool = True
    enable_sentiment: bool = True
    num_speakers: Optional[int] = 2  # None for auto-detect


@dataclass
class TranscriptionSegment:
    """A speaker-diarized segment of transcription."""
    segment_index: int
    speaker: str  # agent, customer, unknown
    speaker_label: str  # SPEAKER_0, SPEAKER_1, etc.
    start_time_ms: int
    end_time_ms: int
    text: str
    confidence: float
    words: Optional[List[Dict]] = None
    sentiment: Optional[str] = None


@dataclass
class TranscriptionResult:
    """Complete transcription result."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    provider: str = "deepgram"
    provider_job_id: Optional[str] = None
    full_text: str = ""
    segments: List[TranscriptionSegment] = field(default_factory=list)
    confidence_score: float = 0.0
    language: str = "en"
    word_count: int = 0
    duration_seconds: float = 0.0
    processing_time_ms: int = 0
    cost_cents: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# DEEPGRAM PROVIDER
# =============================================================================

class DeepgramTranscriber:
    """Transcription using Deepgram API."""

    BASE_URL = "https://api.deepgram.com/v1"

    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            logger.warning("DEEPGRAM_API_KEY not set")

    async def transcribe_url(
        self,
        audio_url: str,
        config: TranscriptionConfig
    ) -> TranscriptionResult:
        """Transcribe audio from URL."""
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY not configured")

        start_time = datetime.now()

        # Build query parameters
        params = {
            "model": "nova-2",
            "language": config.language,
            "punctuate": str(config.enable_punctuation).lower(),
            "diarize": str(config.enable_diarization).lower(),
            "utterances": "true",
            "smart_format": "true",
        }

        if config.enable_word_timestamps:
            params["words"] = "true"

        if config.num_speakers:
            params["diarize_version"] = "2"
            # Can't specify exact number, but helps with accuracy

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json"
        }

        body = {"url": audio_url}

        async with aiohttp.ClientSession() as session:
            url = f"{self.BASE_URL}/listen?" + "&".join(f"{k}={v}" for k, v in params.items())

            async with session.post(url, headers=headers, json=body) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Deepgram API error: {response.status} - {error_text}")

                result = await response.json()

        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        return self._parse_response(result, processing_time)

    async def transcribe_file(
        self,
        audio_data: bytes,
        config: TranscriptionConfig,
        mime_type: str = "audio/mp3"
    ) -> TranscriptionResult:
        """Transcribe audio from file bytes."""
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY not configured")

        start_time = datetime.now()

        params = {
            "model": "nova-2",
            "language": config.language,
            "punctuate": str(config.enable_punctuation).lower(),
            "diarize": str(config.enable_diarization).lower(),
            "utterances": "true",
            "smart_format": "true",
        }

        if config.enable_word_timestamps:
            params["words"] = "true"

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": mime_type
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.BASE_URL}/listen?" + "&".join(f"{k}={v}" for k, v in params.items())

            async with session.post(url, headers=headers, data=audio_data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Deepgram API error: {response.status} - {error_text}")

                result = await response.json()

        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        return self._parse_response(result, processing_time)

    def _parse_response(self, response: Dict, processing_time: int) -> TranscriptionResult:
        """Parse Deepgram response into TranscriptionResult."""
        results = response.get("results", {})
        channels = results.get("channels", [{}])
        channel = channels[0] if channels else {}
        alternatives = channel.get("alternatives", [{}])
        alternative = alternatives[0] if alternatives else {}

        # Full transcript
        full_text = alternative.get("transcript", "")

        # Parse utterances (speaker-diarized segments)
        segments = []
        utterances = results.get("utterances", [])

        for idx, utt in enumerate(utterances):
            speaker_label = f"SPEAKER_{utt.get('speaker', 0)}"
            # Try to identify agent vs customer (typically speaker 0 is caller on inbound)
            speaker = "customer" if utt.get("speaker", 0) == 0 else "agent"

            # Get words for this utterance
            words = None
            if "words" in alternative:
                all_words = alternative["words"]
                utt_start = utt.get("start", 0)
                utt_end = utt.get("end", 0)
                words = [
                    {
                        "word": w.get("word", ""),
                        "start_ms": int(w.get("start", 0) * 1000),
                        "end_ms": int(w.get("end", 0) * 1000),
                        "confidence": w.get("confidence", 0)
                    }
                    for w in all_words
                    if utt_start <= w.get("start", 0) <= utt_end
                ]

            segment = TranscriptionSegment(
                segment_index=idx,
                speaker=speaker,
                speaker_label=speaker_label,
                start_time_ms=int(utt.get("start", 0) * 1000),
                end_time_ms=int(utt.get("end", 0) * 1000),
                text=utt.get("transcript", ""),
                confidence=utt.get("confidence", 0),
                words=words
            )
            segments.append(segment)

        # Calculate overall confidence
        confidence = alternative.get("confidence", 0)

        # Get metadata
        metadata = response.get("metadata", {})
        duration = metadata.get("duration", 0)

        return TranscriptionResult(
            provider="deepgram",
            provider_job_id=metadata.get("request_id"),
            full_text=full_text,
            segments=segments,
            confidence_score=confidence,
            language=metadata.get("language", "en"),
            word_count=len(full_text.split()),
            duration_seconds=duration,
            processing_time_ms=processing_time,
            metadata={
                "model": metadata.get("model", ""),
                "channels": metadata.get("channels", 1)
            }
        )


# =============================================================================
# ASSEMBLYAI PROVIDER
# =============================================================================

class AssemblyAITranscriber:
    """Transcription using AssemblyAI API."""

    BASE_URL = "https://api.assemblyai.com/v2"

    def __init__(self):
        self.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        if not self.api_key:
            logger.warning("ASSEMBLYAI_API_KEY not set")

    async def transcribe_url(
        self,
        audio_url: str,
        config: TranscriptionConfig
    ) -> TranscriptionResult:
        """Transcribe audio from URL."""
        if not self.api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not configured")

        start_time = datetime.now()

        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }

        # Submit transcription job
        body = {
            "audio_url": audio_url,
            "language_code": config.language,
            "punctuate": config.enable_punctuation,
            "format_text": True,
            "speaker_labels": config.enable_diarization,
            "word_boost": ["mortgage", "refinance", "loan", "rate", "APR", "closing"],
        }

        if config.enable_sentiment:
            body["sentiment_analysis"] = True

        if config.num_speakers:
            body["speakers_expected"] = config.num_speakers

        async with aiohttp.ClientSession() as session:
            # Submit job
            async with session.post(
                f"{self.BASE_URL}/transcript",
                headers=headers,
                json=body
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"AssemblyAI API error: {response.status} - {error_text}")

                submit_result = await response.json()
                transcript_id = submit_result.get("id")

            # Poll for completion
            result = await self._poll_for_completion(session, headers, transcript_id)

        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        return self._parse_response(result, processing_time)

    async def _poll_for_completion(
        self,
        session: aiohttp.ClientSession,
        headers: Dict,
        transcript_id: str,
        max_wait_seconds: int = 300
    ) -> Dict:
        """Poll for transcription completion."""
        poll_interval = 3
        elapsed = 0

        while elapsed < max_wait_seconds:
            async with session.get(
                f"{self.BASE_URL}/transcript/{transcript_id}",
                headers=headers
            ) as response:
                result = await response.json()
                status = result.get("status")

                if status == "completed":
                    return result
                elif status == "error":
                    raise Exception(f"AssemblyAI transcription failed: {result.get('error')}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise Exception(f"AssemblyAI transcription timed out after {max_wait_seconds}s")

    def _parse_response(self, response: Dict, processing_time: int) -> TranscriptionResult:
        """Parse AssemblyAI response into TranscriptionResult."""
        full_text = response.get("text", "")

        # Parse utterances
        segments = []
        utterances = response.get("utterances", [])

        for idx, utt in enumerate(utterances):
            speaker_label = utt.get("speaker", "A")
            # AssemblyAI uses A, B, etc.
            speaker = "customer" if speaker_label == "A" else "agent"

            # Get words for this utterance
            words = [
                {
                    "word": w.get("text", ""),
                    "start_ms": w.get("start", 0),
                    "end_ms": w.get("end", 0),
                    "confidence": w.get("confidence", 0)
                }
                for w in utt.get("words", [])
            ]

            segment = TranscriptionSegment(
                segment_index=idx,
                speaker=speaker,
                speaker_label=f"SPEAKER_{speaker_label}",
                start_time_ms=utt.get("start", 0),
                end_time_ms=utt.get("end", 0),
                text=utt.get("text", ""),
                confidence=utt.get("confidence", 0),
                words=words if words else None
            )
            segments.append(segment)

        # Get sentiment if available
        sentiment_results = response.get("sentiment_analysis_results", [])
        if sentiment_results:
            for seg in segments:
                # Find matching sentiment
                for sent in sentiment_results:
                    if sent.get("start", 0) <= seg.start_time_ms <= sent.get("end", 0):
                        seg.sentiment = sent.get("sentiment")
                        break

        return TranscriptionResult(
            provider="assemblyai",
            provider_job_id=response.get("id"),
            full_text=full_text,
            segments=segments,
            confidence_score=response.get("confidence", 0),
            language=response.get("language_code", "en"),
            word_count=len(full_text.split()) if full_text else 0,
            duration_seconds=response.get("audio_duration", 0) / 1000,
            processing_time_ms=processing_time,
            metadata={
                "audio_url": response.get("audio_url"),
                "status": response.get("status")
            }
        )


# =============================================================================
# WHISPER PROVIDER (via OpenAI)
# =============================================================================

class WhisperTranscriber:
    """Transcription using OpenAI Whisper API."""

    BASE_URL = "https://api.openai.com/v1"

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set for Whisper")

    async def transcribe_file(
        self,
        audio_data: bytes,
        config: TranscriptionConfig,
        filename: str = "audio.mp3"
    ) -> TranscriptionResult:
        """Transcribe audio file using Whisper."""
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not configured for Whisper")

        start_time = datetime.now()

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        # Whisper endpoint uses multipart form
        form_data = aiohttp.FormData()
        form_data.add_field(
            "file",
            audio_data,
            filename=filename,
            content_type="audio/mpeg"
        )
        form_data.add_field("model", "whisper-1")
        form_data.add_field("language", config.language)
        form_data.add_field("response_format", "verbose_json")

        if config.enable_word_timestamps:
            form_data.add_field("timestamp_granularities[]", "word")
            form_data.add_field("timestamp_granularities[]", "segment")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.BASE_URL}/audio/transcriptions",
                headers=headers,
                data=form_data
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Whisper API error: {response.status} - {error_text}")

                result = await response.json()

        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        return self._parse_response(result, processing_time)

    def _parse_response(self, response: Dict, processing_time: int) -> TranscriptionResult:
        """Parse Whisper response into TranscriptionResult."""
        full_text = response.get("text", "")

        # Whisper doesn't have speaker diarization, so we create a single segment
        segments = []
        whisper_segments = response.get("segments", [])

        for idx, seg in enumerate(whisper_segments):
            words = None
            if "words" in response:
                words = [
                    {
                        "word": w.get("word", ""),
                        "start_ms": int(w.get("start", 0) * 1000),
                        "end_ms": int(w.get("end", 0) * 1000),
                        "confidence": 0.9  # Whisper doesn't provide per-word confidence
                    }
                    for w in response.get("words", [])
                    if seg.get("start", 0) <= w.get("start", 0) <= seg.get("end", 0)
                ]

            segment = TranscriptionSegment(
                segment_index=idx,
                speaker="unknown",  # Whisper doesn't diarize
                speaker_label="SPEAKER_UNKNOWN",
                start_time_ms=int(seg.get("start", 0) * 1000),
                end_time_ms=int(seg.get("end", 0) * 1000),
                text=seg.get("text", ""),
                confidence=0.9,
                words=words
            )
            segments.append(segment)

        return TranscriptionResult(
            provider="whisper",
            full_text=full_text,
            segments=segments,
            confidence_score=0.9,  # Whisper doesn't provide overall confidence
            language=response.get("language", "en"),
            word_count=len(full_text.split()) if full_text else 0,
            duration_seconds=response.get("duration", 0),
            processing_time_ms=processing_time,
            metadata={
                "task": response.get("task", "transcribe")
            }
        )


# =============================================================================
# UNIFIED TRANSCRIPTION SERVICE
# =============================================================================

class TranscriptionService:
    """
    Unified transcription service with provider fallback.

    Usage:
        service = TranscriptionService()
        result = await service.transcribe_url("https://example.com/audio.mp3")
    """

    def __init__(self, primary_provider: TranscriptionProvider = TranscriptionProvider.DEEPGRAM):
        self.primary_provider = primary_provider
        self.deepgram = DeepgramTranscriber()
        self.assemblyai = AssemblyAITranscriber()
        self.whisper = WhisperTranscriber()

    async def transcribe_url(
        self,
        audio_url: str,
        config: Optional[TranscriptionConfig] = None,
        fallback: bool = True
    ) -> TranscriptionResult:
        """
        Transcribe audio from URL.

        Args:
            audio_url: URL of audio file
            config: Transcription configuration
            fallback: Whether to try backup providers on failure

        Returns:
            TranscriptionResult
        """
        config = config or TranscriptionConfig()
        providers = self._get_provider_order(fallback)

        last_error = None
        for provider in providers:
            try:
                if provider == TranscriptionProvider.DEEPGRAM:
                    return await self.deepgram.transcribe_url(audio_url, config)
                elif provider == TranscriptionProvider.ASSEMBLYAI:
                    return await self.assemblyai.transcribe_url(audio_url, config)
                # Whisper doesn't support URL transcription directly
            except Exception as e:
                logger.warning(f"Transcription failed with {provider}: {e}")
                last_error = e
                continue

        raise Exception(f"All transcription providers failed. Last error: {last_error}")

    async def transcribe_file(
        self,
        audio_data: bytes,
        config: Optional[TranscriptionConfig] = None,
        mime_type: str = "audio/mp3",
        fallback: bool = True
    ) -> TranscriptionResult:
        """
        Transcribe audio from file bytes.

        Args:
            audio_data: Audio file bytes
            config: Transcription configuration
            mime_type: MIME type of audio
            fallback: Whether to try backup providers on failure

        Returns:
            TranscriptionResult
        """
        config = config or TranscriptionConfig()
        providers = self._get_provider_order(fallback)

        last_error = None
        for provider in providers:
            try:
                if provider == TranscriptionProvider.DEEPGRAM:
                    return await self.deepgram.transcribe_file(audio_data, config, mime_type)
                elif provider == TranscriptionProvider.WHISPER:
                    return await self.whisper.transcribe_file(audio_data, config)
                # AssemblyAI requires URL, so skip for file upload
            except Exception as e:
                logger.warning(f"Transcription failed with {provider}: {e}")
                last_error = e
                continue

        raise Exception(f"All transcription providers failed. Last error: {last_error}")

    def _get_provider_order(self, include_fallback: bool) -> List[TranscriptionProvider]:
        """Get ordered list of providers to try."""
        if self.primary_provider == TranscriptionProvider.DEEPGRAM:
            order = [TranscriptionProvider.DEEPGRAM, TranscriptionProvider.ASSEMBLYAI, TranscriptionProvider.WHISPER]
        elif self.primary_provider == TranscriptionProvider.ASSEMBLYAI:
            order = [TranscriptionProvider.ASSEMBLYAI, TranscriptionProvider.DEEPGRAM, TranscriptionProvider.WHISPER]
        else:
            order = [TranscriptionProvider.WHISPER, TranscriptionProvider.DEEPGRAM, TranscriptionProvider.ASSEMBLYAI]

        return order if include_fallback else [self.primary_provider]

    def identify_speakers(
        self,
        result: TranscriptionResult,
        agent_name: Optional[str] = None,
        customer_phone: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Post-process transcription to better identify speakers.

        Uses heuristics like:
        - First speaker on inbound calls is usually customer
        - Agent typically uses company name, NMLS ID
        - Customer typically asks questions about rates, process
        """
        agent_indicators = [
            "thank you for calling",
            "how may i help",
            "my name is",
            "nmls",
            "let me pull up",
            "i can help you with",
        ]

        customer_indicators = [
            "i'm calling about",
            "i need",
            "what are your rates",
            "how much",
            "i want to",
            "can you tell me",
        ]

        for segment in result.segments:
            text_lower = segment.text.lower()

            agent_score = sum(1 for ind in agent_indicators if ind in text_lower)
            customer_score = sum(1 for ind in customer_indicators if ind in text_lower)

            if agent_score > customer_score:
                segment.speaker = "agent"
            elif customer_score > agent_score:
                segment.speaker = "customer"
            # Keep original if tied

        return result


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_transcript_for_display(result: TranscriptionResult) -> str:
    """Format transcription for human-readable display."""
    lines = []
    for seg in result.segments:
        timestamp = f"[{seg.start_time_ms // 1000}s]"
        speaker = seg.speaker.upper()
        lines.append(f"{timestamp} {speaker}: {seg.text}")
    return "\n".join(lines)


def get_speaker_talk_times(result: TranscriptionResult) -> Dict[str, int]:
    """Calculate total talk time per speaker in seconds."""
    talk_times = {}
    for seg in result.segments:
        duration = (seg.end_time_ms - seg.start_time_ms) // 1000
        talk_times[seg.speaker] = talk_times.get(seg.speaker, 0) + duration
    return talk_times


def get_transcript_service() -> TranscriptionService:
    """Get singleton transcription service."""
    return TranscriptionService()
