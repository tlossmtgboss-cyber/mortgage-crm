"""
===============================================================================
PERENNIA AI RECEPTIONIST - PART 3: AUDIO PROCESSING
===============================================================================
Audio processing for speech-to-text and text-to-speech.

Features:
- Deepgram STT integration
- ElevenLabs TTS integration
- Real-time audio streaming
- Audio format conversion
===============================================================================
"""

import os
import asyncio
import base64
import json
import logging
from typing import Optional, Dict, Any, Callable, AsyncGenerator
from dataclasses import dataclass
import aiohttp

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class AudioConfig:
    """Audio processing configuration."""
    # Deepgram STT
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"
    stt_language: str = "en-US"

    # ElevenLabs TTS
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel
    elevenlabs_model: str = "eleven_turbo_v2"

    # Audio settings
    sample_rate: int = 8000  # Twilio uses 8kHz
    encoding: str = "mulaw"  # Twilio uses mu-law

    @classmethod
    def from_env(cls) -> "AudioConfig":
        """Load from environment variables."""
        return cls(
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
        )

    def has_deepgram(self) -> bool:
        return bool(self.deepgram_api_key)

    def has_elevenlabs(self) -> bool:
        return bool(self.elevenlabs_api_key)


# =============================================================================
# SPEECH TO TEXT (STT)
# =============================================================================

class DeepgramSTT:
    """
    Deepgram Speech-to-Text integration.

    Supports:
    - Real-time streaming transcription
    - Batch transcription
    - Phone call audio (8kHz mu-law)
    """

    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig.from_env()

        if not self.config.has_deepgram():
            logger.warning("Deepgram API key not set - STT will not work")

        self.base_url = "https://api.deepgram.com/v1"
        self.ws_url = "wss://api.deepgram.com/v1/listen"

    def _get_headers(self) -> Dict[str, str]:
        """Get API headers."""
        return {
            "Authorization": f"Token {self.config.deepgram_api_key}",
            "Content-Type": "audio/wav",
        }

    async def transcribe_audio(
        self,
        audio_data: bytes,
        encoding: str = "mulaw",
        sample_rate: int = 8000,
    ) -> Dict[str, Any]:
        """
        Transcribe audio data.

        Args:
            audio_data: Raw audio bytes
            encoding: Audio encoding (mulaw, linear16, etc.)
            sample_rate: Sample rate in Hz

        Returns:
            Transcription result
        """
        if not self.config.has_deepgram():
            return {"error": "Deepgram not configured"}

        params = {
            "model": self.config.deepgram_model,
            "language": self.config.stt_language,
            "encoding": encoding,
            "sample_rate": sample_rate,
            "punctuate": "true",
            "smart_format": "true",
        }

        url = f"{self.base_url}/listen?" + "&".join(f"{k}={v}" for k, v in params.items())

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=audio_data,
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        transcript = result.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]
                        return {
                            "transcript": transcript.get("transcript", ""),
                            "confidence": transcript.get("confidence", 0),
                            "words": transcript.get("words", []),
                        }
                    else:
                        error = await response.text()
                        logger.error(f"Deepgram error: {error}")
                        return {"error": error}

        except Exception as e:
            logger.error(f"STT error: {e}")
            return {"error": str(e)}

    async def stream_transcription(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        on_transcript: Callable[[str, float], None],
        encoding: str = "mulaw",
        sample_rate: int = 8000,
    ):
        """
        Stream audio for real-time transcription.

        Args:
            audio_stream: Async generator yielding audio chunks
            on_transcript: Callback for transcript updates
            encoding: Audio encoding
            sample_rate: Sample rate
        """
        if not self.config.has_deepgram():
            logger.error("Deepgram not configured for streaming")
            return

        params = {
            "model": self.config.deepgram_model,
            "language": self.config.stt_language,
            "encoding": encoding,
            "sample_rate": str(sample_rate),
            "punctuate": "true",
            "interim_results": "true",
            "endpointing": "300",
        }

        ws_url = f"{self.ws_url}?" + "&".join(f"{k}={v}" for k, v in params.items())

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    ws_url,
                    headers={"Authorization": f"Token {self.config.deepgram_api_key}"},
                ) as ws:
                    # Start receive task
                    async def receive_transcripts():
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                if "channel" in data:
                                    alt = data["channel"]["alternatives"][0]
                                    transcript = alt.get("transcript", "")
                                    confidence = alt.get("confidence", 0)
                                    is_final = data.get("is_final", False)

                                    if transcript and is_final:
                                        on_transcript(transcript, confidence)

                    receive_task = asyncio.create_task(receive_transcripts())

                    # Send audio chunks
                    async for chunk in audio_stream:
                        await ws.send_bytes(chunk)

                    # Signal end of audio
                    await ws.send_json({"type": "CloseStream"})

                    # Wait for remaining transcripts
                    await asyncio.wait_for(receive_task, timeout=5.0)

        except Exception as e:
            logger.error(f"Streaming STT error: {e}")


# =============================================================================
# TEXT TO SPEECH (TTS)
# =============================================================================

class ElevenLabsTTS:
    """
    ElevenLabs Text-to-Speech integration.

    Supports:
    - High-quality voice synthesis
    - Streaming audio generation
    - Multiple voice options
    """

    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig.from_env()

        if not self.config.has_elevenlabs():
            logger.warning("ElevenLabs API key not set - using fallback TTS")

        self.base_url = "https://api.elevenlabs.io/v1"

    def _get_headers(self) -> Dict[str, str]:
        """Get API headers."""
        return {
            "xi-api-key": self.config.elevenlabs_api_key,
            "Content-Type": "application/json",
        }

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        output_format: str = "mp3_44100_128",
    ) -> Optional[bytes]:
        """
        Synthesize speech from text.

        Args:
            text: Text to synthesize
            voice_id: ElevenLabs voice ID
            output_format: Output audio format

        Returns:
            Audio bytes or None on error
        """
        if not self.config.has_elevenlabs():
            logger.warning("ElevenLabs not configured")
            return None

        voice = voice_id or self.config.elevenlabs_voice_id
        url = f"{self.base_url}/text-to-speech/{voice}"

        payload = {
            "text": text,
            "model_id": self.config.elevenlabs_model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        params = {"output_format": output_format}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    params=params,
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        error = await response.text()
                        logger.error(f"ElevenLabs error: {error}")
                        return None

        except Exception as e:
            logger.error(f"TTS error: {e}")
            return None

    async def stream_synthesis(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesized speech.

        Args:
            text: Text to synthesize
            voice_id: Voice ID

        Yields:
            Audio chunks
        """
        if not self.config.has_elevenlabs():
            return

        voice = voice_id or self.config.elevenlabs_voice_id
        url = f"{self.base_url}/text-to-speech/{voice}/stream"

        payload = {
            "text": text,
            "model_id": self.config.elevenlabs_model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 200:
                        async for chunk in response.content.iter_chunked(4096):
                            yield chunk
                    else:
                        logger.error(f"ElevenLabs streaming error: {response.status}")

        except Exception as e:
            logger.error(f"TTS streaming error: {e}")

    async def get_voices(self) -> list:
        """Get available voices."""
        if not self.config.has_elevenlabs():
            return []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/voices",
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return [
                            {
                                "voice_id": v["voice_id"],
                                "name": v["name"],
                                "category": v.get("category", ""),
                            }
                            for v in data.get("voices", [])
                        ]
                    return []

        except Exception as e:
            logger.error(f"Get voices error: {e}")
            return []


# =============================================================================
# AUDIO UTILITIES
# =============================================================================

class AudioConverter:
    """Audio format conversion utilities."""

    @staticmethod
    def mulaw_to_pcm(mulaw_data: bytes) -> bytes:
        """Convert mu-law to PCM."""
        import audioop
        return audioop.ulaw2lin(mulaw_data, 2)

    @staticmethod
    def pcm_to_mulaw(pcm_data: bytes) -> bytes:
        """Convert PCM to mu-law."""
        import audioop
        return audioop.lin2ulaw(pcm_data, 2)

    @staticmethod
    def base64_decode(data: str) -> bytes:
        """Decode base64 audio."""
        return base64.b64decode(data)

    @staticmethod
    def base64_encode(data: bytes) -> str:
        """Encode audio to base64."""
        return base64.b64encode(data).decode("utf-8")

    @staticmethod
    async def convert_mp3_to_mulaw(mp3_data: bytes) -> bytes:
        """Convert MP3 to mu-law for Twilio."""
        try:
            from pydub import AudioSegment
            import io

            # Load MP3
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))

            # Convert to 8kHz mono
            audio = audio.set_frame_rate(8000).set_channels(1)

            # Export as raw PCM
            pcm_data = audio.raw_data

            # Convert to mu-law
            import audioop
            return audioop.lin2ulaw(pcm_data, audio.sample_width)

        except ImportError:
            logger.error("pydub not installed. Run: pip install pydub")
            return b""
        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
            return b""


# =============================================================================
# TWILIO MEDIA STREAM HANDLER
# =============================================================================

class TwilioMediaStreamHandler:
    """
    Handle Twilio Media Streams for real-time audio.

    Twilio Media Streams send audio via WebSocket in this format:
    - 8kHz sample rate
    - mu-law encoding
    - Base64 encoded chunks
    """

    def __init__(
        self,
        stt: Optional[DeepgramSTT] = None,
        tts: Optional[ElevenLabsTTS] = None,
    ):
        self.stt = stt or DeepgramSTT()
        self.tts = tts or ElevenLabsTTS()
        self.converter = AudioConverter()

        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.audio_buffer: list = []

    async def handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle incoming Twilio Media Stream message.

        Args:
            message: Twilio WebSocket message

        Returns:
            Response message or None
        """
        event = message.get("event")

        if event == "connected":
            logger.info("Media stream connected")
            return None

        elif event == "start":
            self.stream_sid = message.get("streamSid")
            self.call_sid = message.get("start", {}).get("callSid")
            logger.info(f"Media stream started: {self.stream_sid}")
            return None

        elif event == "media":
            # Decode audio
            payload = message.get("media", {}).get("payload", "")
            audio_chunk = self.converter.base64_decode(payload)
            self.audio_buffer.append(audio_chunk)
            return None

        elif event == "stop":
            logger.info("Media stream stopped")
            # Process buffered audio
            if self.audio_buffer:
                full_audio = b"".join(self.audio_buffer)
                result = await self.stt.transcribe_audio(full_audio)
                self.audio_buffer = []
                return result
            return None

        return None

    def create_audio_message(self, audio_data: bytes) -> Dict[str, Any]:
        """
        Create a message to send audio back to Twilio.

        Args:
            audio_data: mu-law audio bytes

        Returns:
            Twilio media message
        """
        return {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": self.converter.base64_encode(audio_data),
            },
        }

    async def send_speech(
        self,
        websocket,
        text: str,
    ):
        """
        Synthesize and send speech through the media stream.

        Args:
            websocket: WebSocket connection
            text: Text to speak
        """
        # Generate speech
        mp3_audio = await self.tts.synthesize(text)
        if not mp3_audio:
            logger.error("Failed to synthesize speech")
            return

        # Convert to mu-law
        mulaw_audio = await self.converter.convert_mp3_to_mulaw(mp3_audio)

        # Send in chunks
        chunk_size = 640  # ~80ms of audio at 8kHz
        for i in range(0, len(mulaw_audio), chunk_size):
            chunk = mulaw_audio[i:i + chunk_size]
            message = self.create_audio_message(chunk)
            await websocket.send_json(message)

            # Small delay to match real-time playback
            await asyncio.sleep(0.08)


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_stt(config: Optional[AudioConfig] = None) -> DeepgramSTT:
    """Create STT instance."""
    return DeepgramSTT(config)


def create_tts(config: Optional[AudioConfig] = None) -> ElevenLabsTTS:
    """Create TTS instance."""
    return ElevenLabsTTS(config)


def create_stream_handler(
    stt: Optional[DeepgramSTT] = None,
    tts: Optional[ElevenLabsTTS] = None,
) -> TwilioMediaStreamHandler:
    """Create media stream handler."""
    return TwilioMediaStreamHandler(stt, tts)
