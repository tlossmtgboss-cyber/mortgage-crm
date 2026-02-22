"""
Input Formats for Call Intelligence Service

Defines standard formats for audio sources, transcription services,
and document inputs to enable flexible integration with various
audio/transcription providers.

Supported Audio Sources:
- Telnyx (recordings)
- Vonage/Nexmo
- Amazon Connect
- Direct file upload (wav, mp3, m4a)
- Pre-transcribed text

Supported Transcription Services:
- Deepgram
- AssemblyAI
- AWS Transcribe
- Google Speech-to-Text
- OpenAI Whisper

Usage:
    from services.call_intelligence.input_formats import (
        AudioSource,
        TranscriptionConfig,
        DocumentInput,
        parse_audio_source,
    )

    # Create audio source from Telnyx
    source = AudioSource(
        provider="telnyx",
        recording_url="https://api.telnyx.com/recordings/...",
        call_sid="call_control_123...",
    )

    # Configure transcription
    config = TranscriptionConfig(
        provider="deepgram",
        language="en-US",
        enable_diarization=True,
    )
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class AudioProvider(str, Enum):
    """Supported audio/telephony providers."""
    TELNYX = "telnyx"
    VONAGE = "vonage"
    AMAZON_CONNECT = "amazon_connect"
    RINGCENTRAL = "ringcentral"
    FIVE9 = "five9"
    GENESYS = "genesys"
    DIRECT_UPLOAD = "direct_upload"
    WEBHOOK = "webhook"  # Generic webhook with audio URL


class TranscriptionProvider(str, Enum):
    """Supported transcription services."""
    DEEPGRAM = "deepgram"
    ASSEMBLYAI = "assemblyai"
    AWS_TRANSCRIBE = "aws_transcribe"
    GOOGLE_STT = "google_stt"
    OPENAI_WHISPER = "openai_whisper"
    AZURE_SPEECH = "azure_speech"
    PRE_TRANSCRIBED = "pre_transcribed"  # Already has transcript


class AudioFormat(str, Enum):
    """Supported audio file formats."""
    WAV = "wav"
    MP3 = "mp3"
    M4A = "m4a"
    OGG = "ogg"
    FLAC = "flac"
    WEBM = "webm"
    RAW = "raw"  # Raw PCM audio


class DocumentType(str, Enum):
    """Types of mortgage documents."""
    PAYSTUB = "paystub"
    W2 = "w2"
    TAX_RETURN = "tax_return"
    BANK_STATEMENT = "bank_statement"
    DRIVERS_LICENSE = "drivers_license"
    PURCHASE_CONTRACT = "purchase_contract"
    APPRAISAL = "appraisal"
    GIFT_LETTER = "gift_letter"
    EMPLOYMENT_LETTER = "employment_letter"
    OTHER = "other"


# =============================================================================
# Audio Source
# =============================================================================

@dataclass
class AudioSource:
    """
    Represents an audio source for transcription.

    Attributes:
        provider: Audio/telephony provider (telnyx, vonage, etc.)
        recording_url: URL to fetch the audio recording
        call_sid: Provider-specific call identifier
        recording_sid: Provider-specific recording identifier
        audio_format: Format of the audio file
        duration_seconds: Duration of the recording in seconds
        sample_rate: Audio sample rate in Hz
        channels: Number of audio channels (1=mono, 2=stereo)
        metadata: Additional provider-specific metadata
    """
    provider: str  # AudioProvider value
    recording_url: Optional[str] = None
    call_sid: Optional[str] = None
    recording_sid: Optional[str] = None
    audio_format: str = "wav"  # AudioFormat value
    duration_seconds: Optional[int] = None
    sample_rate: int = 8000  # Default telephony sample rate
    channels: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Authentication for fetching recording
    auth_type: Optional[str] = None  # "basic", "bearer", "api_key"
    auth_credentials: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "recording_url": self.recording_url,
            "call_sid": self.call_sid,
            "recording_sid": self.recording_sid,
            "audio_format": self.audio_format,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "metadata": self.metadata,
        }

    @classmethod
    def from_telnyx(
        cls,
        recording_url: str,
        call_sid: str,
        recording_sid: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> "AudioSource":
        """Create AudioSource from Telnyx recording."""
        auth_credentials = None
        if api_key:
            auth_credentials = {
                "api_key": api_key,
            }

        return cls(
            provider=AudioProvider.TELNYX.value,
            recording_url=recording_url,
            call_sid=call_sid,
            recording_sid=recording_sid,
            audio_format="wav",
            sample_rate=8000,  # Telnyx default
            auth_type="bearer" if auth_credentials else None,
            auth_credentials=auth_credentials,
            metadata=kwargs,
        )

    @classmethod
    def from_vonage(
        cls,
        recording_url: str,
        conversation_uuid: str,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> "AudioSource":
        """Create AudioSource from Vonage/Nexmo recording."""
        auth_credentials = None
        if api_key:
            auth_credentials = {"api_key": api_key}

        return cls(
            provider=AudioProvider.VONAGE.value,
            recording_url=recording_url,
            call_sid=conversation_uuid,
            audio_format="mp3",
            sample_rate=16000,  # Vonage default
            auth_type="bearer" if auth_credentials else None,
            auth_credentials=auth_credentials,
            metadata=kwargs,
        )

    @classmethod
    def from_amazon_connect(
        cls,
        s3_uri: str,
        contact_id: str,
        **kwargs,
    ) -> "AudioSource":
        """Create AudioSource from Amazon Connect recording in S3."""
        return cls(
            provider=AudioProvider.AMAZON_CONNECT.value,
            recording_url=s3_uri,
            call_sid=contact_id,
            audio_format="wav",
            sample_rate=8000,
            metadata={
                "s3_uri": s3_uri,
                **kwargs,
            },
        )

    @classmethod
    def from_direct_upload(
        cls,
        file_path: str,
        audio_format: str = "wav",
        **kwargs,
    ) -> "AudioSource":
        """Create AudioSource from direct file upload."""
        return cls(
            provider=AudioProvider.DIRECT_UPLOAD.value,
            recording_url=f"file://{file_path}",
            audio_format=audio_format,
            metadata=kwargs,
        )


# =============================================================================
# Transcription Configuration
# =============================================================================

@dataclass
class TranscriptionConfig:
    """
    Configuration for transcription service.

    Attributes:
        provider: Transcription service provider
        language: Language code (e.g., "en-US")
        enable_diarization: Separate speakers in transcript
        enable_punctuation: Add punctuation to transcript
        enable_word_timestamps: Include timestamps for each word
        custom_vocabulary: Domain-specific terms (mortgage jargon)
        redact_pii: Redact PII in transcript (provider-side)
        model: Specific model to use (if applicable)
    """
    provider: str = "deepgram"  # TranscriptionProvider value
    language: str = "en-US"
    enable_diarization: bool = True
    enable_punctuation: bool = True
    enable_word_timestamps: bool = False
    custom_vocabulary: List[str] = field(default_factory=list)
    redact_pii: bool = False  # Let our service handle PII for more control
    model: Optional[str] = None

    # Provider-specific API credentials
    api_key: Optional[str] = None

    # Rate limiting
    max_retries: int = 3
    timeout_seconds: int = 300

    def __post_init__(self):
        """Set default vocabulary for mortgage domain."""
        if not self.custom_vocabulary:
            self.custom_vocabulary = [
                # Loan types
                "FHA", "VA", "USDA", "conventional", "jumbo",
                # Mortgage terms
                "DTI", "LTV", "PMI", "PITI", "escrow",
                "preapproval", "prequalification", "underwriting",
                "closing costs", "earnest money", "appraisal",
                # Financial terms
                "W-2", "1099", "paystub", "bank statement",
                "401k", "IRA", "asset", "liability",
                # Property terms
                "condo", "townhouse", "single-family", "HOA",
                # Compliance
                "TRID", "RESPA", "TILA", "NMLS",
            ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "language": self.language,
            "enable_diarization": self.enable_diarization,
            "enable_punctuation": self.enable_punctuation,
            "enable_word_timestamps": self.enable_word_timestamps,
            "custom_vocabulary_count": len(self.custom_vocabulary),
            "redact_pii": self.redact_pii,
            "model": self.model,
        }

    @classmethod
    def for_deepgram(
        cls,
        api_key: Optional[str] = None,
        model: str = "nova-2",
        **kwargs,
    ) -> "TranscriptionConfig":
        """Create config optimized for Deepgram."""
        return cls(
            provider=TranscriptionProvider.DEEPGRAM.value,
            api_key=api_key,
            model=model,
            enable_diarization=True,
            enable_punctuation=True,
            **kwargs,
        )

    @classmethod
    def for_assemblyai(
        cls,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> "TranscriptionConfig":
        """Create config optimized for AssemblyAI."""
        return cls(
            provider=TranscriptionProvider.ASSEMBLYAI.value,
            api_key=api_key,
            enable_diarization=True,
            enable_punctuation=True,
            **kwargs,
        )

    @classmethod
    def for_whisper(
        cls,
        api_key: Optional[str] = None,
        model: str = "whisper-1",
        **kwargs,
    ) -> "TranscriptionConfig":
        """Create config for OpenAI Whisper."""
        return cls(
            provider=TranscriptionProvider.OPENAI_WHISPER.value,
            api_key=api_key,
            model=model,
            enable_diarization=False,  # Whisper doesn't support diarization
            enable_punctuation=True,
            **kwargs,
        )


# =============================================================================
# Transcription Result
# =============================================================================

@dataclass
class TranscriptWord:
    """A single word with timing information."""
    word: str
    start_time: float  # seconds
    end_time: float  # seconds
    confidence: float  # 0-1
    speaker: Optional[int] = None  # Speaker ID from diarization


@dataclass
class TranscriptUtterance:
    """A speaker utterance (sentence/paragraph)."""
    text: str
    speaker: Optional[int] = None
    start_time: float = 0.0
    end_time: float = 0.0
    confidence: float = 1.0
    words: List[TranscriptWord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "speaker": self.speaker,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "confidence": self.confidence,
        }


@dataclass
class TranscriptionResult:
    """
    Result from transcription service.

    Can be converted to CallIntelligenceRequest format.
    """
    text: str  # Full transcript text
    utterances: List[TranscriptUtterance] = field(default_factory=list)
    language: str = "en-US"
    duration_seconds: float = 0.0
    confidence: float = 1.0
    provider: str = "unknown"

    # Speaker information from diarization
    speaker_count: int = 0
    speaker_labels: Dict[int, str] = field(default_factory=dict)

    # Metadata
    transcription_time_ms: int = 0
    audio_url: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None

    def to_formatted_transcript(self) -> str:
        """
        Convert to formatted transcript string.

        Format: "Speaker A: Hello...\nSpeaker B: Hi..."
        """
        if not self.utterances:
            return self.text

        lines = []
        for utterance in self.utterances:
            speaker_label = self.speaker_labels.get(
                utterance.speaker,
                f"Speaker {utterance.speaker or 'Unknown'}"
            )
            lines.append(f"{speaker_label}: {utterance.text}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "utterances": [u.to_dict() for u in self.utterances],
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "confidence": self.confidence,
            "provider": self.provider,
            "speaker_count": self.speaker_count,
        }


# =============================================================================
# Document Input
# =============================================================================

@dataclass
class DocumentInput:
    """
    Input document for extraction (paystubs, W-2s, bank statements, etc.).

    Future: Can be extended for document OCR and extraction.
    """
    document_type: str  # DocumentType value
    file_url: Optional[str] = None
    file_path: Optional[str] = None
    file_content: Optional[bytes] = None
    mime_type: str = "application/pdf"
    filename: Optional[str] = None

    # For linking to loan
    loan_id: Optional[int] = None
    borrower_id: Optional[int] = None

    # Document metadata
    document_date: Optional[datetime] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "file_url": self.file_url,
            "mime_type": self.mime_type,
            "filename": self.filename,
            "loan_id": self.loan_id,
            "document_date": self.document_date.isoformat() if self.document_date else None,
            "metadata": self.metadata,
        }


# =============================================================================
# Webhook Payload Parsers
# =============================================================================

def parse_telnyx_webhook(payload: Dict[str, Any]) -> AudioSource:
    """
    Parse Telnyx recording webhook payload.

    Telnyx sends webhooks when recordings are completed.
    Supports both TeXML (TwiML-compatible) and native Telnyx payload formats.
    """
    return AudioSource.from_telnyx(
        recording_url=payload.get("RecordingUrl") or payload.get("recording_url"),
        call_sid=payload.get("CallSid") or payload.get("call_control_id"),
        recording_sid=payload.get("RecordingSid") or payload.get("recording_id"),
        duration_seconds=int(payload.get("RecordingDuration", 0) or payload.get("duration", 0)),
        metadata={
            "from": payload.get("From") or payload.get("from"),
            "to": payload.get("To") or payload.get("to"),
            "direction": payload.get("Direction") or payload.get("direction"),
            "status": payload.get("RecordingStatus") or payload.get("status"),
        },
    )


def parse_vonage_webhook(payload: Dict[str, Any]) -> AudioSource:
    """Parse Vonage/Nexmo recording webhook payload."""
    return AudioSource.from_vonage(
        recording_url=payload.get("recording_url"),
        conversation_uuid=payload.get("conversation_uuid"),
        duration_seconds=int(payload.get("duration", 0)),
        metadata={
            "from": payload.get("from"),
            "to": payload.get("to"),
            "status": payload.get("status"),
        },
    )


def parse_generic_webhook(
    payload: Dict[str, Any],
    url_field: str = "recording_url",
    call_id_field: str = "call_id",
) -> AudioSource:
    """
    Parse generic webhook payload.

    For custom integrations that don't match standard providers.
    """
    return AudioSource(
        provider=AudioProvider.WEBHOOK.value,
        recording_url=payload.get(url_field),
        call_sid=payload.get(call_id_field),
        duration_seconds=payload.get("duration"),
        metadata=payload,
    )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Enums
    "AudioProvider",
    "TranscriptionProvider",
    "AudioFormat",
    "DocumentType",
    # Data classes
    "AudioSource",
    "TranscriptionConfig",
    "TranscriptWord",
    "TranscriptUtterance",
    "TranscriptionResult",
    "DocumentInput",
    # Parsers
    "parse_telnyx_webhook",
    "parse_vonage_webhook",
    "parse_generic_webhook",
]
