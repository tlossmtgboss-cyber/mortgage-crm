"""
================================================================================
PERENNIA AI - AUDIO PROCESSOR
================================================================================
Speech-to-Text & Text-to-Speech Processing

Real-time audio processing with:
- Deepgram for speech-to-text (streaming)
- ElevenLabs for natural text-to-speech
- Whisper (OpenAI) fallback for STT
- Audio format conversion utilities (mu-law/PCM)
- Voice Activity Detection

Integrates with:
- voice_routes.py: WebSocket streaming
- telnyx_voice_service.py: Call handling

================================================================================
"""

from __future__ import annotations

import os
import io
import json
import asyncio
import logging
import base64
import struct
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, AsyncIterator, Callable, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager
from functools import wraps

logger = logging.getLogger(__name__)


# =============================================================================
# OPTIONAL IMPORTS WITH GRACEFUL FALLBACKS
# =============================================================================

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    logger.warning("httpx not installed - HTTP-based STT/TTS will be unavailable")

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    logger.warning("websockets not installed - streaming STT will be unavailable")

try:
    from openai import OpenAI, AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    logger.warning("openai not installed - Whisper STT and OpenAI TTS unavailable")


# =============================================================================
# METRICS AND MONITORING
# =============================================================================

@dataclass
class AudioMetrics:
    """Track audio processing metrics for monitoring."""

    total_stt_requests: int = 0
    total_tts_requests: int = 0
    stt_errors: int = 0
    tts_errors: int = 0
    total_audio_bytes_processed: int = 0
    total_stt_latency_ms: float = 0.0
    total_tts_latency_ms: float = 0.0

    def record_stt(self, latency_ms: float, audio_bytes: int, success: bool = True):
        """Record STT request metrics."""
        self.total_stt_requests += 1
        self.total_audio_bytes_processed += audio_bytes
        self.total_stt_latency_ms += latency_ms
        if not success:
            self.stt_errors += 1

    def record_tts(self, latency_ms: float, success: bool = True):
        """Record TTS request metrics."""
        self.total_tts_requests += 1
        self.total_tts_latency_ms += latency_ms
        if not success:
            self.tts_errors += 1

    @property
    def avg_stt_latency(self) -> float:
        """Average STT latency in milliseconds."""
        if self.total_stt_requests == 0:
            return 0.0
        return self.total_stt_latency_ms / self.total_stt_requests

    @property
    def avg_tts_latency(self) -> float:
        """Average TTS latency in milliseconds."""
        if self.total_tts_requests == 0:
            return 0.0
        return self.total_tts_latency_ms / self.total_tts_requests

    @property
    def stt_success_rate(self) -> float:
        """STT success rate as percentage."""
        if self.total_stt_requests == 0:
            return 100.0
        return ((self.total_stt_requests - self.stt_errors) / self.total_stt_requests) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Export metrics as dictionary."""
        return {
            "stt": {
                "total_requests": self.total_stt_requests,
                "errors": self.stt_errors,
                "success_rate": round(self.stt_success_rate, 2),
                "avg_latency_ms": round(self.avg_stt_latency, 2),
            },
            "tts": {
                "total_requests": self.total_tts_requests,
                "errors": self.tts_errors,
                "avg_latency_ms": round(self.avg_tts_latency, 2),
            },
            "total_audio_bytes": self.total_audio_bytes_processed,
        }


# Global metrics instance
_metrics = AudioMetrics()


def get_audio_metrics() -> AudioMetrics:
    """Get global audio metrics instance."""
    return _metrics


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class STTConfig:
    """Speech-to-text configuration."""

    provider: str = "deepgram"  # deepgram, whisper, azure

    # Deepgram settings
    deepgram_api_key: Optional[str] = None
    deepgram_model: str = "nova-2"

    # OpenAI Whisper settings
    openai_api_key: Optional[str] = None
    whisper_model: str = "whisper-1"

    # Azure settings
    azure_key: Optional[str] = None
    azure_region: str = "eastus"

    # Common settings
    language: str = "en-US"
    punctuate: bool = True
    profanity_filter: bool = False
    smart_format: bool = True

    # Streaming settings
    interim_results: bool = True
    endpointing: int = 300  # ms of silence to detect end of speech
    vad_events: bool = True  # Voice activity detection

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 0.5  # seconds
    timeout: float = 30.0  # seconds

    def __post_init__(self):
        """Load from environment if not explicitly set."""
        self.deepgram_api_key = self.deepgram_api_key or os.getenv("DEEPGRAM_API_KEY")
        self.openai_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
        self.azure_key = self.azure_key or os.getenv("AZURE_SPEECH_KEY")
        self.azure_region = self.azure_region or os.getenv("AZURE_SPEECH_REGION", "eastus")

    def validate(self) -> List[str]:
        """Validate configuration and return list of issues."""
        issues = []

        if self.provider == "deepgram" and not self.deepgram_api_key:
            issues.append("Deepgram API key not configured")
        elif self.provider == "whisper" and not self.openai_api_key:
            issues.append("OpenAI API key not configured for Whisper")
        elif self.provider == "azure" and not self.azure_key:
            issues.append("Azure Speech key not configured")

        return issues


@dataclass
class TTSConfig:
    """Text-to-speech configuration.

    Human-like voice optimization:
    - Lower stability (0.3-0.4) = more natural variation in tone
    - Higher similarity_boost (0.8-0.9) = preserves voice character
    - Style parameter (0.3-0.5) = adds emotional expression
    - Speaker boost = better projection and clarity
    """

    provider: str = "elevenlabs"  # elevenlabs, azure, openai

    # ElevenLabs settings - optimized for natural, human-like speech
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel - warm female voice
    elevenlabs_model: str = "eleven_turbo_v2_5"  # Latest model - most natural sounding

    # OpenAI TTS settings
    openai_api_key: Optional[str] = None
    openai_voice: str = "nova"  # alloy, echo, fable, onyx, nova, shimmer
    openai_model: str = "tts-1-hd"  # HD model for better quality

    # Azure settings
    azure_key: Optional[str] = None
    azure_region: str = "eastus"
    azure_voice: str = "en-US-JennyNeural"

    # Common settings
    output_format: str = "mulaw"  # mp3, wav, pcm, mulaw (best for telephony)
    sample_rate: int = 8000  # 8000 for telephony, 16000/24000 for high quality

    # Voice customization - tuned for human-like speech
    stability: float = 0.35  # Lower = more expressive, natural variation (was 0.5)
    similarity_boost: float = 0.85  # Higher preserves voice character (was 0.75)
    style: float = 0.4  # Adds emotional expression (new parameter)
    use_speaker_boost: bool = True  # Better projection and clarity (new parameter)
    speaking_rate: float = 1.0  # Speed multiplier

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 0.5
    timeout: float = 30.0

    def __post_init__(self):
        """Load from environment if not explicitly set."""
        self.elevenlabs_api_key = self.elevenlabs_api_key or os.getenv("ELEVENLABS_API_KEY")
        self.openai_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
        self.azure_key = self.azure_key or os.getenv("AZURE_SPEECH_KEY")

    def validate(self) -> List[str]:
        """Validate configuration and return list of issues."""
        issues = []

        if self.provider == "elevenlabs" and not self.elevenlabs_api_key:
            issues.append("ElevenLabs API key not configured")
        elif self.provider == "openai" and not self.openai_api_key:
            issues.append("OpenAI API key not configured for TTS")
        elif self.provider == "azure" and not self.azure_key:
            issues.append("Azure Speech key not configured")

        return issues


# =============================================================================
# AUDIO FORMATS AND CONVERSION
# =============================================================================

class AudioFormat(str, Enum):
    """Supported audio formats."""
    PCM_16 = "pcm_16"  # 16-bit PCM
    MULAW = "mulaw"  # 8-bit mu-law (telephony)
    MP3 = "mp3"
    WAV = "wav"
    OGG = "ogg"


# Pre-compute mu-law decode table for performance
_MULAW_DECODE_TABLE: List[int] = []
for i in range(256):
    sign = 1 if i < 128 else -1
    position = (~i if sign == 1 else i) & 0x7F
    decoded = sign * (((position & 0x0F) << 3) + 132) << ((position & 0x70) >> 4)
    _MULAW_DECODE_TABLE.append(decoded)


def convert_mulaw_to_pcm(mulaw_data: bytes) -> bytes:
    """
    Convert mu-law encoded audio to 16-bit PCM.

    Args:
        mulaw_data: Raw mu-law audio bytes

    Returns:
        16-bit PCM audio bytes
    """
    pcm_data = bytearray(len(mulaw_data) * 2)

    for i, byte in enumerate(mulaw_data):
        sample = _MULAW_DECODE_TABLE[byte]
        struct.pack_into('<h', pcm_data, i * 2, sample)

    return bytes(pcm_data)


def convert_pcm_to_mulaw(pcm_data: bytes) -> bytes:
    """
    Convert 16-bit PCM to mu-law encoded audio.

    Args:
        pcm_data: 16-bit PCM audio bytes

    Returns:
        Mu-law encoded audio bytes
    """
    MULAW_MAX = 0x1FFF
    MULAW_BIAS = 33

    def encode_sample(sample: int) -> int:
        sign = 0x00 if sample >= 0 else 0x80
        sample = min(abs(sample), MULAW_MAX)
        sample += MULAW_BIAS

        exponent = 7
        for exp_mask in [0x4000, 0x2000, 0x1000, 0x0800, 0x0400, 0x0200, 0x0100]:
            if sample & exp_mask:
                break
            exponent -= 1

        mantissa = (sample >> (exponent + 3)) & 0x0F
        return ~(sign | (exponent << 4) | mantissa) & 0xFF

    mulaw_data = bytearray(len(pcm_data) // 2)

    for i in range(0, len(pcm_data), 2):
        sample = struct.unpack('<h', pcm_data[i:i+2])[0]
        mulaw_data[i // 2] = encode_sample(sample)

    return bytes(mulaw_data)


def create_wav_header(
    sample_rate: int = 8000,
    bits_per_sample: int = 16,
    channels: int = 1,
    data_size: int = 0,
) -> bytes:
    """
    Create WAV file header.

    Args:
        sample_rate: Audio sample rate
        bits_per_sample: Bits per audio sample
        channels: Number of audio channels
        data_size: Size of audio data in bytes

    Returns:
        44-byte WAV header
    """
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,  # Subchunk1Size
        1,   # AudioFormat (PCM)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size,
    )
    return header


def audio_to_base64(audio_data: bytes) -> str:
    """Encode audio bytes to base64 string."""
    return base64.b64encode(audio_data).decode('utf-8')


def base64_to_audio(base64_data: str) -> bytes:
    """Decode base64 string to audio bytes."""
    return base64.b64decode(base64_data)


# =============================================================================
# RETRY DECORATOR
# =============================================================================

def with_retry(max_retries: int = 3, delay: float = 0.5, backoff: float = 2.0):
    """
    Retry decorator for async functions.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay on each retry
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries + 1} attempts: {e}")

            raise last_exception
        return wrapper
    return decorator


# =============================================================================
# SPEECH-TO-TEXT PROVIDERS
# =============================================================================

class STTProvider(ABC):
    """Abstract base class for STT providers."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes, format: AudioFormat = AudioFormat.PCM_16) -> str:
        """Transcribe audio to text (batch)."""
        pass

    @abstractmethod
    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        on_transcript: Callable[[str, bool], None],
    ) -> None:
        """Stream transcription with callbacks."""
        pass

    async def close(self) -> None:
        """Clean up resources."""
        pass


class DeepgramSTT(STTProvider):
    """
    Deepgram speech-to-text provider.

    Features:
    - Real-time streaming transcription
    - Low latency (~300ms)
    - Speaker diarization
    - Custom vocabulary
    """

    def __init__(self, config: STTConfig):
        self.config = config
        self.api_key = config.deepgram_api_key
        self._client: Optional[httpx.AsyncClient] = None

        if not self.api_key:
            raise ValueError("Deepgram API key not configured")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if not HAS_HTTPX:
            raise ImportError("httpx not installed")

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    @with_retry(max_retries=3, delay=0.5)
    async def transcribe(
        self,
        audio_data: bytes,
        format: AudioFormat = AudioFormat.PCM_16,
    ) -> str:
        """Transcribe audio file."""
        start_time = time.time()

        try:
            # Convert mulaw to PCM if needed
            if format == AudioFormat.MULAW:
                audio_data = convert_mulaw_to_pcm(audio_data)

            url = "https://api.deepgram.com/v1/listen"
            params = {
                "model": self.config.deepgram_model,
                "language": self.config.language,
                "punctuate": str(self.config.punctuate).lower(),
                "smart_format": str(self.config.smart_format).lower(),
            }

            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "audio/wav",
            }

            # Wrap in WAV header
            wav_data = create_wav_header(data_size=len(audio_data)) + audio_data

            client = await self._get_client()
            response = await client.post(
                url,
                params=params,
                headers=headers,
                content=wav_data,
            )
            response.raise_for_status()

            result = response.json()
            transcript = result["results"]["channels"][0]["alternatives"][0]["transcript"]

            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_stt(latency_ms, len(audio_data), success=True)

            return transcript

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_stt(latency_ms, len(audio_data), success=False)
            raise

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        on_transcript: Callable[[str, bool], None],
    ) -> None:
        """
        Stream audio and get real-time transcription.

        Args:
            audio_stream: Async iterator yielding audio chunks
            on_transcript: Callback(text, is_final) for each transcript
        """
        if not HAS_WEBSOCKETS:
            raise ImportError("websockets not installed")

        url = "wss://api.deepgram.com/v1/listen"
        params = {
            "model": self.config.deepgram_model,
            "language": self.config.language,
            "punctuate": str(self.config.punctuate).lower(),
            "interim_results": str(self.config.interim_results).lower(),
            "endpointing": str(self.config.endpointing),
            "vad_events": str(self.config.vad_events).lower(),
            "encoding": "linear16",
            "sample_rate": "8000",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query_string}"

        headers = {"Authorization": f"Token {self.api_key}"}

        async with websockets.connect(full_url, extra_headers=headers) as ws:
            receiver_task = None

            async def receive():
                try:
                    async for message in ws:
                        data = json.loads(message)

                        if data.get("type") == "Results":
                            channel = data.get("channel", {})
                            alternatives = channel.get("alternatives", [{}])
                            transcript = alternatives[0].get("transcript", "")
                            is_final = data.get("is_final", False)

                            if transcript:
                                on_transcript(transcript, is_final)

                        elif data.get("type") == "SpeechStarted":
                            logger.debug("Speech started")

                        elif data.get("type") == "UtteranceEnd":
                            logger.debug("Utterance ended")

                except websockets.ConnectionClosed:
                    logger.debug("Deepgram WebSocket closed")

            receiver_task = asyncio.create_task(receive())

            try:
                async for chunk in audio_stream:
                    await ws.send(chunk)

                # Signal end of stream
                await ws.send(json.dumps({"type": "CloseStream"}))

                # Wait for final results
                await asyncio.sleep(0.5)

            finally:
                if receiver_task:
                    receiver_task.cancel()
                    try:
                        await receiver_task
                    except asyncio.CancelledError:
                        pass

    async def close(self) -> None:
        """Clean up HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


class WhisperSTT(STTProvider):
    """
    OpenAI Whisper speech-to-text provider.

    Features:
    - High accuracy
    - Multi-language support
    - Good for batch processing
    """

    def __init__(self, config: STTConfig):
        self.config = config

        if not HAS_OPENAI:
            raise ImportError("openai not installed")

        self.client = AsyncOpenAI(api_key=config.openai_api_key)

    @with_retry(max_retries=3, delay=0.5)
    async def transcribe(
        self,
        audio_data: bytes,
        format: AudioFormat = AudioFormat.PCM_16,
    ) -> str:
        """Transcribe audio using Whisper API."""
        start_time = time.time()

        try:
            # Convert to WAV format
            if format == AudioFormat.MULAW:
                audio_data = convert_mulaw_to_pcm(audio_data)

            wav_data = create_wav_header(data_size=len(audio_data)) + audio_data

            # Create file-like object
            audio_file = io.BytesIO(wav_data)
            audio_file.name = "audio.wav"

            # Call API
            response = await self.client.audio.transcriptions.create(
                model=self.config.whisper_model,
                file=audio_file,
                language=self.config.language.split("-")[0],
            )

            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_stt(latency_ms, len(audio_data), success=True)

            return response.text

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_stt(latency_ms, len(audio_data), success=False)
            raise

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        on_transcript: Callable[[str, bool], None],
    ) -> None:
        """
        Whisper doesn't support true streaming, so we buffer and transcribe.
        Transcribes every ~2 seconds of audio.
        """
        buffer = bytearray()
        CHUNK_SIZE = 16000  # ~2 seconds at 8kHz

        async for chunk in audio_stream:
            buffer.extend(chunk)

            if len(buffer) >= CHUNK_SIZE:
                transcript = await self.transcribe(bytes(buffer), AudioFormat.PCM_16)
                if transcript:
                    on_transcript(transcript, True)
                buffer.clear()

        # Final transcription
        if buffer:
            transcript = await self.transcribe(bytes(buffer), AudioFormat.PCM_16)
            if transcript:
                on_transcript(transcript, True)


# =============================================================================
# TEXT-TO-SPEECH PROVIDERS
# =============================================================================

class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Convert text to audio."""
        pass

    @abstractmethod
    async def stream_synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Stream audio synthesis for low latency."""
        pass

    async def close(self) -> None:
        """Clean up resources."""
        pass


class ElevenLabsTTS(TTSProvider):
    """
    ElevenLabs text-to-speech provider.

    Features:
    - Ultra-realistic voices
    - Voice cloning
    - Streaming support
    - Emotion control
    """

    # Voice ID mapping for convenience
    VOICES = {
        "rachel": "21m00Tcm4TlvDq8ikWAM",  # Warm female
        "adam": "pNInz6obpgDQGcFmaJgB",    # Deep male
        "antoni": "ErXwobaYiN019PkySvjV",  # Friendly male
        "bella": "EXAVITQu4vr4xnSDxMaL",   # Soft female
        "domi": "AZnzlk1XvdvUeBnXmlld",    # Strong female
        "elli": "MF3mGyEYCl7XYWbV9V6O",    # Young female
        "josh": "TxGEqnHWrfWFTfGW9XjX",    # Young male
        "sam": "yoZ06aMxZJJ28mfd3POQ",     # Narrator male
    }

    def __init__(self, config: TTSConfig):
        self.config = config
        self.api_key = config.elevenlabs_api_key
        self._client: Optional[httpx.AsyncClient] = None

        if not self.api_key:
            raise ValueError("ElevenLabs API key not configured")

        self.base_url = "https://api.elevenlabs.io/v1"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if not HAS_HTTPX:
            raise ImportError("httpx not installed")

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    def _get_voice_id(self, voice: Optional[str] = None) -> str:
        """Resolve voice name to ID."""
        voice = voice or self.config.elevenlabs_voice_id
        return self.VOICES.get(voice.lower(), voice)

    @with_retry(max_retries=3, delay=0.5)
    async def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """Synthesize speech from text."""
        start_time = time.time()

        try:
            voice_id = self._get_voice_id(voice)
            url = f"{self.base_url}/text-to-speech/{voice_id}"

            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
            }

            # Map output format
            output_format_map = {
                "mp3": "mp3_44100_128",
                "pcm": "pcm_16000",
                "mulaw": "ulaw_8000",
            }
            output_format = output_format_map.get(
                self.config.output_format, "ulaw_8000"
            )

            data = {
                "text": text,
                "model_id": self.config.elevenlabs_model,
                "voice_settings": {
                    "stability": self.config.stability,
                    "similarity_boost": self.config.similarity_boost,
                    "style": getattr(self.config, 'style', 0.4),
                    "use_speaker_boost": getattr(self.config, 'use_speaker_boost', True),
                },
            }

            client = await self._get_client()
            response = await client.post(
                url,
                headers=headers,
                json=data,
                params={"output_format": output_format},
            )
            response.raise_for_status()

            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_tts(latency_ms, success=True)

            return response.content

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_tts(latency_ms, success=False)
            raise

    async def stream_synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> AsyncIterator[bytes]:
        """Stream audio synthesis for low latency."""
        if not HAS_HTTPX:
            raise ImportError("httpx not installed")

        voice_id = self._get_voice_id(voice)
        url = f"{self.base_url}/text-to-speech/{voice_id}/stream"

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        data = {
            "text": text,
            "model_id": self.config.elevenlabs_model,
            "voice_settings": {
                "stability": self.config.stability,
                "similarity_boost": self.config.similarity_boost,
                "style": getattr(self.config, 'style', 0.4),
                "use_speaker_boost": getattr(self.config, 'use_speaker_boost', True),
            },
        }

        client = await self._get_client()
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=data,
            params={"output_format": "ulaw_8000"},
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(chunk_size=1024):
                yield chunk

    async def get_voices(self) -> List[Dict[str, Any]]:
        """Get available voices."""
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/voices",
            headers={"xi-api-key": self.api_key},
        )
        response.raise_for_status()
        return response.json()["voices"]

    async def close(self) -> None:
        """Clean up HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


class OpenAITTS(TTSProvider):
    """
    OpenAI text-to-speech provider.

    Features:
    - Simple API
    - Good quality
    - Multiple voices
    """

    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def __init__(self, config: TTSConfig):
        self.config = config

        if not HAS_OPENAI:
            raise ImportError("openai not installed")

        self.client = AsyncOpenAI(api_key=config.openai_api_key)

    @with_retry(max_retries=3, delay=0.5)
    async def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """Synthesize speech from text."""
        start_time = time.time()

        try:
            voice = voice or self.config.openai_voice

            response = await self.client.audio.speech.create(
                model=self.config.openai_model,
                voice=voice,
                input=text,
                response_format="mp3",
                speed=self.config.speaking_rate,
            )

            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_tts(latency_ms, success=True)

            return response.content

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_tts(latency_ms, success=False)
            raise

    async def stream_synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> AsyncIterator[bytes]:
        """Stream audio synthesis."""
        # OpenAI doesn't truly stream, so yield in chunks
        content = await self.synthesize(text, voice)
        chunk_size = 1024

        for i in range(0, len(content), chunk_size):
            yield content[i:i + chunk_size]


# =============================================================================
# VOICE ACTIVITY DETECTION
# =============================================================================

class VoiceActivityDetector:
    """
    Voice activity detection for handling pauses and interruptions.

    Detects when speech starts and ends based on audio energy levels.
    """

    def __init__(
        self,
        energy_threshold: float = 0.02,
        silence_duration: float = 0.5,  # seconds
        speech_duration: float = 0.1,    # seconds
        sample_rate: int = 8000,
    ):
        self.energy_threshold = energy_threshold
        self.silence_samples = int(silence_duration * sample_rate)
        self.speech_samples = int(speech_duration * sample_rate)
        self.sample_rate = sample_rate

        self.is_speaking = False
        self.silent_samples = 0
        self.speech_samples_count = 0
        self._energy_history: List[float] = []
        self._max_history = 100

    def process_chunk(self, audio_chunk: bytes) -> Dict[str, Any]:
        """
        Process audio chunk and detect voice activity.

        Args:
            audio_chunk: 16-bit PCM audio data

        Returns:
            Dict with 'is_speaking', 'speech_started', 'speech_ended', 'energy'
        """
        if len(audio_chunk) < 2:
            return {
                "is_speaking": self.is_speaking,
                "speech_started": False,
                "speech_ended": False,
                "energy": 0.0,
            }

        # Calculate energy (RMS)
        num_samples = len(audio_chunk) // 2
        samples = struct.unpack(f'<{num_samples}h', audio_chunk)

        energy = sum(s**2 for s in samples) / num_samples
        energy = (energy ** 0.5) / 32768  # Normalize to 0-1

        # Track energy history for adaptive threshold
        self._energy_history.append(energy)
        if len(self._energy_history) > self._max_history:
            self._energy_history.pop(0)

        result = {
            "is_speaking": self.is_speaking,
            "speech_started": False,
            "speech_ended": False,
            "energy": energy,
        }

        if energy > self.energy_threshold:
            self.speech_samples_count += num_samples
            self.silent_samples = 0

            if not self.is_speaking and self.speech_samples_count >= self.speech_samples:
                self.is_speaking = True
                result["speech_started"] = True
        else:
            self.silent_samples += num_samples
            self.speech_samples_count = 0

            if self.is_speaking and self.silent_samples >= self.silence_samples:
                self.is_speaking = False
                result["speech_ended"] = True

        result["is_speaking"] = self.is_speaking
        return result

    def reset(self) -> None:
        """Reset detector state."""
        self.is_speaking = False
        self.silent_samples = 0
        self.speech_samples_count = 0
        self._energy_history.clear()

    @property
    def avg_energy(self) -> float:
        """Get average energy from history."""
        if not self._energy_history:
            return 0.0
        return sum(self._energy_history) / len(self._energy_history)


# =============================================================================
# UNIFIED AUDIO PROCESSOR
# =============================================================================

class AudioProcessor:
    """
    Unified audio processor combining STT and TTS.

    Handles the full audio pipeline:
    1. Receive audio from telephony provider (mu-law)
    2. Convert to format for STT
    3. Get transcription
    4. Process through conversation engine
    5. Synthesize response
    6. Convert back to mu-law for telephony
    """

    def __init__(
        self,
        stt_config: Optional[STTConfig] = None,
        tts_config: Optional[TTSConfig] = None,
    ):
        self.stt_config = stt_config or STTConfig()
        self.tts_config = tts_config or TTSConfig()

        # Validate configs
        stt_issues = self.stt_config.validate()
        tts_issues = self.tts_config.validate()

        if stt_issues:
            logger.warning(f"STT config issues: {stt_issues}")
        if tts_issues:
            logger.warning(f"TTS config issues: {tts_issues}")

        # Initialize providers lazily
        self._stt: Optional[STTProvider] = None
        self._tts: Optional[TTSProvider] = None
        self._vad = VoiceActivityDetector()

    @property
    def stt(self) -> STTProvider:
        """Get or create STT provider."""
        if self._stt is None:
            self._stt = self._create_stt_provider()
        return self._stt

    @property
    def tts(self) -> TTSProvider:
        """Get or create TTS provider."""
        if self._tts is None:
            self._tts = self._create_tts_provider()
        return self._tts

    @property
    def vad(self) -> VoiceActivityDetector:
        """Get voice activity detector."""
        return self._vad

    def _create_stt_provider(self) -> STTProvider:
        """Create STT provider based on config."""
        if self.stt_config.provider == "deepgram":
            return DeepgramSTT(self.stt_config)
        elif self.stt_config.provider == "whisper":
            return WhisperSTT(self.stt_config)
        else:
            raise ValueError(f"Unknown STT provider: {self.stt_config.provider}")

    def _create_tts_provider(self) -> TTSProvider:
        """Create TTS provider based on config."""
        if self.tts_config.provider == "elevenlabs":
            return ElevenLabsTTS(self.tts_config)
        elif self.tts_config.provider == "openai":
            return OpenAITTS(self.tts_config)
        else:
            raise ValueError(f"Unknown TTS provider: {self.tts_config.provider}")

    async def transcribe_audio(self, mulaw_audio: bytes) -> str:
        """
        Transcribe audio from telephony provider (mu-law format).

        Args:
            mulaw_audio: Mu-law encoded audio from telephony provider

        Returns:
            Transcribed text
        """
        pcm_audio = convert_mulaw_to_pcm(mulaw_audio)
        return await self.stt.transcribe(pcm_audio, AudioFormat.PCM_16)

    async def synthesize_for_telephony(self, text: str) -> bytes:
        """
        Synthesize speech and return in telephony format (mu-law).

        Args:
            text: Text to synthesize

        Returns:
            Mu-law encoded audio for telephony
        """
        audio = await self.tts.synthesize(text)

        # If already mu-law, return as-is
        if self.tts_config.output_format == "mulaw":
            return audio

        # Otherwise would need conversion (not implemented for MP3)
        return audio

    async def stream_synthesize_for_telephony(self, text: str) -> AsyncIterator[bytes]:
        """
        Stream synthesized speech in telephony format.

        Args:
            text: Text to synthesize

        Yields:
            Audio chunks in mu-law format
        """
        async for chunk in self.tts.stream_synthesize(text):
            yield chunk

    async def process_realtime(
        self,
        audio_stream: AsyncIterator[bytes],
        on_response: Callable[[bytes], Any],
        conversation_handler: Callable[[str], str],
    ) -> None:
        """
        Process audio stream in real-time.

        Args:
            audio_stream: Incoming audio chunks (mu-law from telephony provider)
            on_response: Callback to send response audio
            conversation_handler: Function that takes transcript and returns response text
        """
        transcript_buffer: List[str] = []

        def on_transcript(text: str, is_final: bool):
            if is_final and text:
                transcript_buffer.append(text)

        # Convert mu-law to PCM for STT
        async def converted_stream():
            async for chunk in audio_stream:
                yield convert_mulaw_to_pcm(chunk)

        # Start STT streaming
        await self.stt.stream_transcribe(
            converted_stream(),
            on_transcript,
        )

        # Process accumulated transcript
        full_transcript = " ".join(transcript_buffer)
        if full_transcript:
            # Get response from conversation engine
            response_text = conversation_handler(full_transcript)

            # Synthesize and send
            async for audio_chunk in self.tts.stream_synthesize(response_text):
                await on_response(audio_chunk)

    def get_metrics(self) -> Dict[str, Any]:
        """Get audio processing metrics."""
        return _metrics.to_dict()

    async def close(self) -> None:
        """Clean up all resources."""
        if self._stt:
            await self._stt.close()
            self._stt = None

        if self._tts:
            await self._tts.close()
            self._tts = None


@asynccontextmanager
async def create_audio_processor(
    stt_provider: str = "deepgram",
    tts_provider: str = "elevenlabs",
    **kwargs,
) -> AsyncIterator[AudioProcessor]:
    """
    Create configured audio processor as async context manager.

    Args:
        stt_provider: "deepgram" or "whisper"
        tts_provider: "elevenlabs" or "openai"
        **kwargs: Additional configuration options

    Yields:
        Configured AudioProcessor instance

    Example:
        async with create_audio_processor() as processor:
            text = await processor.transcribe_audio(audio_data)
    """
    stt_config = STTConfig(provider=stt_provider, **{
        k: v for k, v in kwargs.items()
        if k in STTConfig.__dataclass_fields__
    })
    tts_config = TTSConfig(provider=tts_provider, **{
        k: v for k, v in kwargs.items()
        if k in TTSConfig.__dataclass_fields__
    })

    processor = AudioProcessor(stt_config=stt_config, tts_config=tts_config)

    try:
        yield processor
    finally:
        await processor.close()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def transcribe_audio(
    audio_data: bytes,
    format: AudioFormat = AudioFormat.MULAW,
    provider: str = "deepgram",
) -> str:
    """
    Convenience function to transcribe audio.

    Args:
        audio_data: Audio bytes
        format: Audio format
        provider: STT provider name

    Returns:
        Transcribed text
    """
    async with create_audio_processor(stt_provider=provider) as processor:
        if format == AudioFormat.MULAW:
            return await processor.transcribe_audio(audio_data)
        return await processor.stt.transcribe(audio_data, format)


async def synthesize_speech(
    text: str,
    provider: str = "elevenlabs",
    voice: Optional[str] = None,
) -> bytes:
    """
    Convenience function to synthesize speech.

    Args:
        text: Text to synthesize
        provider: TTS provider name
        voice: Voice name or ID

    Returns:
        Audio bytes
    """
    async with create_audio_processor(tts_provider=provider) as processor:
        if hasattr(processor.tts, 'synthesize'):
            return await processor.tts.synthesize(text, voice)
        return await processor.tts.synthesize(text)


# =============================================================================
# CLI / TESTING
# =============================================================================

if __name__ == "__main__":
    import sys

    async def demo():
        print("=" * 60)
        print("Perennia AI - Audio Processor Demo")
        print("=" * 60)

        # Check dependencies
        print("\nDependency check:")
        print(f"  httpx: {'✓' if HAS_HTTPX else '✗'}")
        print(f"  websockets: {'✓' if HAS_WEBSOCKETS else '✗'}")
        print(f"  openai: {'✓' if HAS_OPENAI else '✗'}")

        # Check config
        stt_config = STTConfig()
        tts_config = TTSConfig()

        print("\nConfiguration:")
        print(f"  STT provider: {stt_config.provider}")
        print(f"  TTS provider: {tts_config.provider}")
        print(f"  Deepgram key: {'✓' if stt_config.deepgram_api_key else '✗'}")
        print(f"  ElevenLabs key: {'✓' if tts_config.elevenlabs_api_key else '✗'}")

        stt_issues = stt_config.validate()
        tts_issues = tts_config.validate()

        if stt_issues or tts_issues:
            print("\n⚠️ Configuration issues:")
            for issue in stt_issues + tts_issues:
                print(f"  - {issue}")
            return

        # Test TTS
        print("\n" + "-" * 40)
        print("Testing TTS...")

        try:
            async with create_audio_processor() as processor:
                audio = await processor.tts.synthesize(
                    "Hello! Thank you for calling The Tim Loss Team. How can I help you today?"
                )
                print(f"✓ Generated {len(audio)} bytes of audio")

                # Save to file
                with open("test_output.mp3", "wb") as f:
                    f.write(audio)
                print("✓ Saved to test_output.mp3")

                # Show metrics
                print("\nMetrics:")
                metrics = processor.get_metrics()
                print(f"  TTS requests: {metrics['tts']['total_requests']}")
                print(f"  TTS latency: {metrics['tts']['avg_latency_ms']:.0f}ms")

        except Exception as e:
            print(f"✗ TTS Error: {e}")

        print("\n" + "=" * 60)
        print("Demo complete!")

    asyncio.run(demo())
