"""
Mobile Voice Agent Routes
Real-time voice conversation for Perennia mobile app via WebSocket
Uses Deepgram for streaming STT and ElevenLabs for streaming TTS
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import json
import asyncio
import base64
import os
import time
import httpx
from typing import Optional, Dict, Any, AsyncGenerator, List, TYPE_CHECKING
from collections import defaultdict
import uuid

if TYPE_CHECKING:
    from database.models import User

# Database and auth imports
from database import get_db
from utils.websocket_auth import authenticate_websocket, get_user_id_from_websocket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mobile-voice", tags=["mobile-voice"])

# Configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Google Cloud TTS settings
GOOGLE_TTS_ENABLED = os.getenv("GOOGLE_TTS_ENABLED", "false").lower() == "true"
GOOGLE_TTS_VOICE = os.getenv("GOOGLE_TTS_VOICE", "en-US-Neural2-C")
GOOGLE_TTS_LANGUAGE = os.getenv("GOOGLE_TTS_LANGUAGE", "en-US")

# Voice settings
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel - warm female voice
TTS_MODEL = os.getenv("TTS_MODEL", "eleven_turbo_v2_5")  # Fast model for low latency

# WebSocket idle timeout (30 minutes)
WS_IDLE_TIMEOUT_SECONDS = 30 * 60
# Idle check interval (60 seconds)
WS_IDLE_CHECK_INTERVAL = 60
# Max audio chunk size (1 MB)
MAX_AUDIO_CHUNK_BYTES = 1_048_576

# TTS rate limiter: in-memory tracking per user
_tts_rate_limit: Dict[int, List[float]] = defaultdict(list)
TTS_RATE_LIMIT_MAX = 30  # max requests
TTS_RATE_LIMIT_WINDOW = 60  # per 60 seconds


def _check_tts_rate_limit(user_id: int) -> bool:
    """Return True if rate limit exceeded. Prunes stale entries."""
    now = time.monotonic()
    cutoff = now - TTS_RATE_LIMIT_WINDOW
    timestamps = _tts_rate_limit[user_id]
    # Prune old entries
    _tts_rate_limit[user_id] = [t for t in timestamps if t > cutoff]
    if len(_tts_rate_limit[user_id]) >= TTS_RATE_LIMIT_MAX:
        return True
    _tts_rate_limit[user_id].append(now)
    return False


# White-label voice assistant name — configurable per deployment/tenant (H-1)
DEFAULT_VOICE_ASSISTANT_NAME = os.getenv("VOICE_ASSISTANT_NAME", "Aria")

# Voice assistant system prompt — uses {assistant_name} placeholder for white-label support
VOICE_ASSISTANT_PROMPT_TEMPLATE = """You are {assistant_name}, a warm and professional AI assistant for mortgage loan officers.
You help them manage their pipeline, follow up with leads, schedule appointments, and answer questions.

Voice conversation guidelines:
- Keep responses concise and conversational (under 50 words when possible)
- Use natural speech patterns with appropriate pauses
- Be warm, friendly, and professional
- When asked to perform actions (send texts, schedule appointments, etc.), confirm what you're doing
- If you need to look something up, say "Let me check that for you"
- Ask clarifying questions when needed rather than making assumptions

You have access to the CRM system and can:
- Look up leads and contacts
- Check pipeline status
- Schedule appointments
- Send text messages
- Create tasks and follow-ups
- Provide loan and market information"""


def get_voice_assistant_name(organization_id: Optional[int] = None) -> str:
    """Get the voice assistant name, potentially per-organization.

    Currently returns the global default. In the future, this can be extended
    to look up per-org branding from the database.
    """
    # TODO: Look up org-specific assistant name from organization settings table
    return DEFAULT_VOICE_ASSISTANT_NAME


def get_voice_assistant_prompt(assistant_name: Optional[str] = None) -> str:
    """Get the voice assistant system prompt with the configured name."""
    name = assistant_name or DEFAULT_VOICE_ASSISTANT_NAME
    return VOICE_ASSISTANT_PROMPT_TEMPLATE.format(assistant_name=name)


class DeepgramSTTClient:
    """Streaming Speech-to-Text using Deepgram"""

    def __init__(self):
        self.api_key = DEEPGRAM_API_KEY
        self.websocket = None
        self.transcript_callback = None

    async def connect(self, on_transcript):
        """Connect to Deepgram streaming API"""
        import websockets

        self.transcript_callback = on_transcript

        url = "wss://api.deepgram.com/v1/listen"
        params = {
            "encoding": "linear16",
            "sample_rate": "16000",
            "channels": "1",
            "model": "nova-2",
            "language": "en-US",
            "smart_format": "true",
            "punctuate": "true",
            "interim_results": "true",
            "endpointing": "300",  # 300ms silence triggers end of speech
            "vad_events": "true",
        }

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_string}"

        headers = {
            "Authorization": f"Token {self.api_key}"
        }

        self.websocket = await websockets.connect(full_url, extra_headers=headers)
        logger.info("[DeepgramSTT] Connected to Deepgram streaming API")

        # Start listener
        asyncio.create_task(self._listen())

    async def _listen(self):
        """Listen for Deepgram responses"""
        try:
            async for message in self.websocket:
                data = json.loads(message)

                if data.get("type") == "Results":
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])

                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        confidence = alternatives[0].get("confidence", 0)
                        is_final = data.get("is_final", False)

                        if transcript and self.transcript_callback:
                            await self.transcript_callback({
                                "text": transcript,
                                "is_final": is_final,
                                "confidence": confidence
                            })

                elif data.get("type") == "SpeechStarted":
                    logger.debug("[DeepgramSTT] Speech started")

        except Exception as e:
            logger.error(f"[DeepgramSTT] Error in listener: {e}")

    async def send_audio(self, audio_bytes: bytes):
        """Send audio data to Deepgram"""
        if self.websocket:
            logger.debug(f"[DeepgramSTT] Sending {len(audio_bytes)} bytes to Deepgram")
            await self.websocket.send(audio_bytes)
        else:
            logger.warning("[DeepgramSTT] Cannot send audio - websocket not connected")

    async def close(self):
        """Close the Deepgram connection"""
        if self.websocket:
            await self.websocket.close()
            logger.info("[DeepgramSTT] Connection closed")


class ElevenLabsTTSClient:
    """Streaming Text-to-Speech using ElevenLabs"""

    DEFAULT_VOICE_SETTINGS = {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.5,
        "use_speaker_boost": True
    }

    def __init__(self, voice_id: str = ELEVENLABS_VOICE_ID, voice_settings: dict = None):
        self.api_key = ELEVENLABS_API_KEY
        self.voice_id = voice_id
        self.model_id = TTS_MODEL
        self.voice_settings = voice_settings or self.DEFAULT_VOICE_SETTINGS

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Stream audio synthesis from ElevenLabs"""
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": self.voice_settings,
            "optimize_streaming_latency": 3  # Optimize for low latency
        }

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, json=payload, headers=headers, timeout=30.0) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"[ElevenLabsTTS] Error: {response.status_code} - {error_text}")
                    return

                async for chunk in response.aiter_bytes(chunk_size=4096):
                    yield chunk

    async def synthesize(self, text: str) -> bytes:
        """Synthesize full audio (non-streaming)"""
        chunks = []
        async for chunk in self.synthesize_stream(text):
            chunks.append(chunk)
        return b"".join(chunks)


class OpenAITTSClient:
    """Fallback TTS using OpenAI"""

    def __init__(self, voice: str = "nova"):
        self.api_key = OPENAI_API_KEY
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        """Synthesize audio using OpenAI TTS"""
        url = "https://api.openai.com/v1/audio/speech"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "tts-1-hd",  # HD model for natural-sounding voice
            "input": text,
            "voice": self.voice,
            "response_format": "mp3",
            "speed": 1.0
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)

            if response.status_code != 200:
                logger.error(f"[OpenAITTS] Error: {response.status_code}")
                return b""

            return response.content


class GoogleTTSClient:
    """Text-to-Speech using Google Cloud TTS"""

    def __init__(self, voice_name: str = GOOGLE_TTS_VOICE, language_code: str = GOOGLE_TTS_LANGUAGE):
        self.voice_name = voice_name
        self.language_code = language_code
        self._service = None

    def _get_service(self):
        """Lazy load the Google TTS service"""
        if self._service is None:
            try:
                from integrations.google_tts_service import get_tts_service
                self._service = get_tts_service()
            except Exception as e:
                logger.error(f"[GoogleTTS] Failed to initialize service: {e}")
                raise
        return self._service

    async def synthesize(self, text: str) -> bytes:
        """Synthesize audio using Google Cloud TTS"""
        try:
            service = self._get_service()
            # Run sync call in thread pool to avoid blocking
            import asyncio
            loop = asyncio.get_event_loop()
            audio_content = await loop.run_in_executor(
                None,
                lambda: service.synthesize_speech(
                    text=text,
                    language_code=self.language_code,
                    voice_name=self.voice_name,
                    audio_encoding="MP3",
                    speaking_rate=1.0,
                    pitch=0.0
                )
            )
            if audio_content:
                logger.info(f"[GoogleTTS] Synthesized {len(audio_content)} bytes")
                return audio_content
            return b""
        except Exception as e:
            logger.error(f"[GoogleTTS] Error: {e}")
            return b""

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Google TTS doesn't support streaming, so return full audio as single chunk"""
        audio = await self.synthesize(text)
        if audio:
            yield audio


class AriaVoiceAgent:
    """Voice agent that processes user speech and generates responses"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.conversation_history = []
        self.session_id = str(uuid.uuid4())

    async def process_user_message(self, transcript: str, db: Session) -> str:
        """Process user message and generate AI response using AI orchestrator with full tool access"""
        # Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": transcript
        })

        import traceback
        try:
            # Use the AIAgentService which connects to the full LangGraph orchestrator
            # This gives the voice agent access to all 160+ tools including:
            # - Pipeline analysis (bottlenecks, metrics, aging)
            # - Lead management (scoring, follow-ups, outreach)
            # - Document tracking
            # - Email/SMS sending
            # - Calendar scheduling
            # - Pre-approval letter generation
            # - And much more
            from agents.service import AIAgentService
            from database.models import User
            from sqlalchemy import text

            logger.info(f"[AriaVoiceAgent] Processing via orchestrator: '{transcript}' for user {self.user_id}")

            # Look up real User model from database
            current_user = db.query(User).filter(User.email == self.user_id).first()

            if not current_user:
                logger.warning(
                    f"[AriaVoiceAgent] Real User model not found for email={self.user_id}, falling back to mock"
                )

                # Fallback: try raw query for basic info, build a mock
                user_result = db.execute(
                    text("SELECT id, email, role, first_name, last_name FROM users WHERE email = :email"),
                    {"email": self.user_id}
                ).fetchone()

                class _FallbackUser:
                    def __init__(self, id, email, role, first_name, last_name):
                        self.id = id
                        self.email = email
                        self.role = role or "loan_officer"
                        self.first_name = first_name
                        self.last_name = last_name

                    @property
                    def name(self):
                        if self.first_name and self.last_name:
                            return f"{self.first_name} {self.last_name}"
                        return self.first_name or self.last_name or ""

                if user_result:
                    current_user = _FallbackUser(
                        id=user_result[0],
                        email=user_result[1],
                        role=user_result[2],
                        first_name=user_result[3] or "",
                        last_name=user_result[4] or ""
                    )
                else:
                    logger.warning(
                        f"[AriaVoiceAgent] No user record at all for email={self.user_id}, using stub"
                    )
                    current_user = _FallbackUser(
                        id=1,
                        email=self.user_id,
                        role="loan_officer",
                        first_name="User",
                        last_name=""
                    )

            # Initialize the AI service with database and user context
            service = AIAgentService(
                db=db,
                current_user=current_user,
                autonomous_mode=True  # Allow auto-execution of low-risk actions
            )

            # Process through the full orchestrator (intent classification -> tool execution -> response)
            result = await service.process_message(
                message=transcript,
                conversation_history=self.conversation_history[-10:],  # Keep last 5 exchanges for context
                return_structured=False
            )

            logger.info(f"[AriaVoiceAgent] Orchestrator result keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")

            # Extract response from result
            if isinstance(result, dict):
                response = result.get("response") or result.get("message") or result.get("text", "")
                if not response:
                    # Try to extract from nested structure
                    response = str(result)
            else:
                response = str(result)

            if not response:
                response = "I processed your request but couldn't generate a response. Could you try rephrasing?"

            logger.info(f"[AriaVoiceAgent] Orchestrator response: {response[:200]}...")

        except Exception as e:
            logger.error(f"[AriaVoiceAgent] Error calling orchestrator: {e}")
            logger.error(f"[AriaVoiceAgent] Traceback: {traceback.format_exc()}")

            # Fallback to simple Anthropic call for voice (without tools)
            try:
                from anthropic import Anthropic
                client = Anthropic()

                # Simple direct response for voice
                voice_messages = self.conversation_history[-6:]  # Keep last 3 exchanges

                assistant_name = get_voice_assistant_name()
                ai_response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=200,
                    system=f"""You are {assistant_name}, a helpful mortgage assistant. Keep responses brief (under 50 words) and conversational for voice. Be warm and professional.

Note: I'm currently unable to access the CRM system. Please let the user know that database features are temporarily unavailable and suggest they try again shortly.""",
                    messages=voice_messages
                )
                response = ai_response.content[0].text
                logger.info(f"[AriaVoiceAgent] Fallback response: {response}")
            except Exception as fallback_error:
                logger.error(f"[AriaVoiceAgent] Fallback also failed: {fallback_error}")
                response = "Sorry, I'm having trouble connecting to the system right now. Please try again in a moment."

        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })

        # Truncate for voice - keep responses under 200 characters for faster TTS
        if len(response) > 300:
            # Find a natural break point
            sentences = response.split('. ')
            truncated = ""
            for sentence in sentences:
                if len(truncated) + len(sentence) < 250:
                    truncated += sentence + ". "
                else:
                    break
            response = truncated.strip() or response[:250] + "..."

        return response


class MobileVoiceSession:
    """Manages a mobile voice conversation session"""

    def __init__(self, websocket: WebSocket, user_id: str, db: Session):
        self.websocket = websocket
        self.user_id = user_id
        self.db = db
        self.session_id = str(uuid.uuid4())
        self.is_active = True

        # Voice components
        self.stt_client = None
        self.tts_client = None
        self.voice_agent = AriaVoiceAgent(user_id)

        # State
        self.is_listening = False
        self.is_speaking = False
        self.pending_transcript = ""
        self.silence_timer = None
        self.last_message_time = time.monotonic()
        self._idle_check_task: Optional[asyncio.Task] = None

    async def start(self):
        """Initialize the voice session"""
        logger.info(f"[MobileVoiceSession] Starting session {self.session_id} for user {self.user_id}")

        # Initialize TTS client - priority: Google (if enabled) > ElevenLabs > OpenAI
        if GOOGLE_TTS_ENABLED:
            try:
                self.tts_client = GoogleTTSClient()
                logger.info(f"[MobileVoiceSession] Using Google Cloud TTS (voice: {GOOGLE_TTS_VOICE})")
            except Exception as e:
                logger.warning(f"[MobileVoiceSession] Google TTS failed to init: {e}, falling back")
                if ELEVENLABS_API_KEY:
                    self.tts_client = ElevenLabsTTSClient()
                    logger.info("[MobileVoiceSession] Fallback to ElevenLabs TTS")
                else:
                    self.tts_client = OpenAITTSClient()
                    logger.info("[MobileVoiceSession] Fallback to OpenAI TTS")
        elif ELEVENLABS_API_KEY:
            self.tts_client = ElevenLabsTTSClient()
            logger.info("[MobileVoiceSession] Using ElevenLabs TTS")
        else:
            self.tts_client = OpenAITTSClient()
            logger.info("[MobileVoiceSession] Using OpenAI TTS (fallback)")

        # NOTE: Deepgram STT is initialized lazily when start_listening is called
        # This prevents Deepgram timeout errors since the connection is only opened
        # when the mobile app is ready to send audio
        logger.info(f"[MobileVoiceSession] Deepgram STT configured: {bool(DEEPGRAM_API_KEY)} (will connect on start_listening)")

        # Send welcome message
        await self._send_event("session_started", {
            "session_id": self.session_id,
            "stt_enabled": bool(DEEPGRAM_API_KEY),
            "tts_enabled": bool(ELEVENLABS_API_KEY or OPENAI_API_KEY)
        })

        # Start idle timeout background check
        self._idle_check_task = asyncio.create_task(self._idle_timeout_loop())

        # Play greeting - keep it casual and short
        greeting = "Hey! What's up?"
        await self._speak(greeting)

    async def _idle_timeout_loop(self):
        """Background task: close WebSocket if idle for WS_IDLE_TIMEOUT_SECONDS."""
        try:
            while self.is_active:
                await asyncio.sleep(WS_IDLE_CHECK_INTERVAL)
                if not self.is_active:
                    break
                elapsed = time.monotonic() - self.last_message_time
                if elapsed >= WS_IDLE_TIMEOUT_SECONDS:
                    logger.info(
                        f"[MobileVoiceSession] Session {self.session_id} idle for "
                        f"{elapsed:.0f}s, closing"
                    )
                    await self._send_event("error", {
                        "message": "Connection closed due to inactivity"
                    })
                    try:
                        await self.websocket.close(code=4002, reason="Idle timeout")
                    except Exception:
                        pass
                    self.is_active = False
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[MobileVoiceSession] Idle check error: {e}")

    async def _on_transcript(self, result: Dict[str, Any]):
        """Handle incoming transcript from STT"""
        text = result.get("text", "")
        is_final = result.get("is_final", False)

        if not text:
            return

        # Send interim results to client
        await self._send_event("transcript", {
            "text": text,
            "is_final": is_final
        })

        if is_final and text.strip():
            self.pending_transcript = ""

            # Stop listening while processing
            self.is_listening = False
            await self._send_event("processing", {"text": text})

            # Process with AI and respond
            response = await self.voice_agent.process_user_message(text, self.db)
            await self._speak(response)

            # Resume listening
            self.is_listening = True
            await self._send_event("listening", {})
        else:
            # Accumulate interim transcript
            self.pending_transcript = text

    async def _speak(self, text: str):
        """Speak text using TTS"""
        self.is_speaking = True
        await self._send_event("speaking", {"text": text})

        try:
            if isinstance(self.tts_client, (ElevenLabsTTSClient, GoogleTTSClient)):
                # Stream audio chunks (Google TTS returns single chunk)
                async for chunk in self.tts_client.synthesize_stream(text):
                    if not self.is_active:
                        break
                    # Send audio chunk as base64
                    await self._send_event("audio", {
                        "data": base64.b64encode(chunk).decode("utf-8"),
                        "format": "mp3"
                    })
            else:
                # Non-streaming fallback (OpenAI)
                audio = await self.tts_client.synthesize(text)
                await self._send_event("audio", {
                    "data": base64.b64encode(audio).decode("utf-8"),
                    "format": "mp3"
                })

        except Exception as e:
            logger.error(f"[MobileVoiceSession] TTS error: {e}")

        finally:
            self.is_speaking = False
            await self._send_event("speech_complete", {})

    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming WebSocket message from mobile client"""
        # Track activity for idle timeout
        self.last_message_time = time.monotonic()

        msg_type = message.get("type", "")

        if msg_type == "audio":
            # Incoming audio from mobile app
            audio_data = message.get("data", "")
            if audio_data and self.stt_client:
                # Validate chunk size before decoding
                # Base64 is ~4/3 the size of raw bytes; check encoded length as proxy
                if len(audio_data) > MAX_AUDIO_CHUNK_BYTES * 4 // 3 + 4:
                    logger.warning(
                        f"[MobileVoiceSession] Audio chunk too large: "
                        f"{len(audio_data)} base64 chars, rejecting"
                    )
                    await self._send_event("error", {
                        "message": "Audio chunk exceeds 1 MB limit"
                    })
                    return

                audio_bytes = base64.b64decode(audio_data)

                if len(audio_bytes) > MAX_AUDIO_CHUNK_BYTES:
                    logger.warning(
                        f"[MobileVoiceSession] Audio chunk too large: "
                        f"{len(audio_bytes)} bytes, rejecting"
                    )
                    await self._send_event("error", {
                        "message": "Audio chunk exceeds 1 MB limit"
                    })
                    return
                logger.info(f"[MobileVoiceSession] Received audio: {len(audio_bytes)} bytes")

                # Strip WAV header if present (first 44 bytes for standard WAV)
                # WAV files start with "RIFF"
                if len(audio_bytes) > 44 and audio_bytes[:4] == b'RIFF':
                    logger.info("[MobileVoiceSession] Stripping WAV header from audio")
                    audio_bytes = audio_bytes[44:]  # Skip WAV header

                await self.stt_client.send_audio(audio_bytes)
            elif not self.stt_client:
                logger.warning("[MobileVoiceSession] Received audio but STT client not initialized")

        elif msg_type == "start_listening":
            self.is_listening = True

            # Lazily connect to Deepgram only when we're ready to listen
            # This prevents timeout errors from Deepgram expecting audio too soon
            if DEEPGRAM_API_KEY and not self.stt_client:
                logger.info("[MobileVoiceSession] Lazily connecting to Deepgram STT...")
                self.stt_client = DeepgramSTTClient()
                await self.stt_client.connect(self._on_transcript)
                logger.info("[MobileVoiceSession] Deepgram STT connected (lazy init)")

            await self._send_event("listening", {})

        elif msg_type == "stop_listening":
            self.is_listening = False
            # Process any pending transcript
            if self.pending_transcript.strip():
                text = self.pending_transcript
                self.pending_transcript = ""
                response = await self.voice_agent.process_user_message(text, self.db)
                await self._speak(response)

        elif msg_type == "interrupt":
            # User interrupted - stop speaking
            self.is_speaking = False
            await self._send_event("interrupted", {})

        elif msg_type == "text_input":
            # Text input fallback
            text = message.get("text", "")
            if text:
                response = await self.voice_agent.process_user_message(text, self.db)
                await self._speak(response)

        elif msg_type == "ping":
            await self._send_event("pong", {})

    async def _send_event(self, event_type: str, data: Dict[str, Any]):
        """Send event to WebSocket client"""
        try:
            await self.websocket.send_json({
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **data
            })
        except Exception as e:
            logger.error(f"[MobileVoiceSession] Error sending event: {e}")

    async def close(self):
        """Close the voice session"""
        self.is_active = False

        if self._idle_check_task and not self._idle_check_task.done():
            self._idle_check_task.cancel()

        if self.stt_client:
            await self.stt_client.close()

        logger.info(f"[MobileVoiceSession] Session {self.session_id} closed")


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws/voice")
async def mobile_voice_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time voice conversation with the voice assistant.

    Protocol:
    - Client sends audio chunks as base64-encoded data
    - Server streams back AI response audio
    - Both sides can interrupt the conversation

    Authentication:
    - Token in URL query param, Authorization header, or Sec-WebSocket-Protocol (existing)
    - OR first message: {"type": "auth", "token": "jwt_token_here"} (new, 10s timeout)

    Message Types (Client -> Server):
    - {"type": "auth", "token": "jwt_token_here"} (first message only, if no URL token)
    - {"type": "audio", "data": "<base64-audio>"} (max 1 MB decoded)
    - {"type": "start_listening"}
    - {"type": "stop_listening"}
    - {"type": "interrupt"}
    - {"type": "text_input", "text": "..."}
    - {"type": "ping"}

    Message Types (Server -> Client):
    - {"type": "session_started", "session_id": "..."}
    - {"type": "listening"}
    - {"type": "transcript", "text": "...", "is_final": bool}
    - {"type": "processing", "text": "..."}
    - {"type": "speaking", "text": "..."}
    - {"type": "audio", "data": "<base64-audio>", "format": "mp3"}
    - {"type": "speech_complete"}
    - {"type": "interrupted"}
    - {"type": "error", "message": "..."}
    - {"type": "pong"}
    """
    logger.info(f"[MobileVoice] WebSocket connection attempt from {websocket.client}")

    session = None
    try:
        await websocket.accept()
        logger.info("[MobileVoice] WebSocket accepted")

        # --- Authentication: URL params/headers first, fall back to first-message auth ---
        auth_user, auth_error = authenticate_websocket(websocket, db)

        if auth_user:
            user_id = auth_user.email
            logger.info(f"[MobileVoice] Authenticated via URL/header, user ID: {auth_user.id}")
        else:
            # No token in URL/headers — wait for first message auth
            logger.info("[MobileVoice] No URL token, waiting for first-message auth")
            try:
                first_msg = await asyncio.wait_for(
                    websocket.receive_json(), timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("[MobileVoice] First-message auth timed out (10s)")
                await websocket.close(code=4001, reason="Authentication timeout")
                return
            except Exception as recv_err:
                logger.warning(f"[MobileVoice] Error receiving first message: {recv_err}")
                await websocket.close(code=4001, reason="Authentication required")
                return

            if isinstance(first_msg, dict) and first_msg.get("type") == "auth":
                token = first_msg.get("token", "")
                if not token:
                    logger.warning("[MobileVoice] Auth message missing token field")
                    await websocket.close(code=4001, reason="Token missing in auth message")
                    return

                # Decode and look up user using same auth path
                from utils.websocket_auth import decode_jwt_token, lookup_user_by_id, lookup_user_by_email
                payload = decode_jwt_token(token)
                if not payload:
                    logger.warning("[MobileVoice] First-message token invalid")
                    await websocket.close(code=4001, reason="Invalid authentication token")
                    return

                auth_user = None
                uid = payload.get("user_id")
                email = payload.get("sub")
                if uid:
                    try:
                        auth_user = lookup_user_by_id(db, int(uid))
                    except (ValueError, TypeError):
                        pass
                if not auth_user and email:
                    auth_user = lookup_user_by_email(db, email)

                if not auth_user:
                    logger.warning("[MobileVoice] First-message auth: user not found")
                    await websocket.close(code=4001, reason="User not found")
                    return

                user_id = auth_user.email
                logger.info(f"[MobileVoice] Authenticated via first-message, user ID: {auth_user.id}")
            else:
                logger.warning(f"[MobileVoice] First message not auth type: {first_msg.get('type') if isinstance(first_msg, dict) else 'non-dict'}")
                await websocket.close(code=4001, reason="Authentication required")
                return

        # Create voice session
        session = MobileVoiceSession(websocket, user_id, db)
        await session.start()

        # Main message loop
        try:
            while session.is_active:
                message = await websocket.receive_json()
                # Skip auth messages after initial auth (idempotent)
                if isinstance(message, dict) and message.get("type") == "auth":
                    continue
                await session.handle_message(message)

        except WebSocketDisconnect:
            logger.info("[MobileVoice] Client disconnected")

    except Exception as e:
        logger.error(f"[MobileVoice] Error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Internal server error"
            })
        except Exception as send_err:
            logger.warning(f"Error sending error to WebSocket client: {send_err}")

    finally:
        if session:
            try:
                await session.close()
            except Exception as e:
                logger.warning(f"Error closing voice session: {e}")


# =============================================================================
# HTTP Endpoints for Voice Status and Configuration
# =============================================================================

@router.get("/status")
async def get_voice_status():
    """Get voice service status"""
    # Determine active TTS provider based on priority
    if GOOGLE_TTS_ENABLED:
        tts_provider = "google"
        tts_voice = GOOGLE_TTS_VOICE
    elif ELEVENLABS_API_KEY:
        tts_provider = "elevenlabs"
        tts_voice = ELEVENLABS_VOICE_ID
    elif OPENAI_API_KEY:
        tts_provider = "openai"
        tts_voice = "nova"
    else:
        tts_provider = "none"
        tts_voice = None

    return {
        "stt": {
            "provider": "deepgram" if DEEPGRAM_API_KEY else "none",
            "enabled": bool(DEEPGRAM_API_KEY)
        },
        "tts": {
            "provider": tts_provider,
            "enabled": tts_provider != "none",
            "voice_id": tts_voice,
            "available_providers": {
                "google": GOOGLE_TTS_ENABLED,
                "elevenlabs": bool(ELEVENLABS_API_KEY),
                "openai": bool(OPENAI_API_KEY)
            }
        },
        "llm": {
            "provider": "anthropic" if ANTHROPIC_API_KEY else ("openai" if OPENAI_API_KEY else "none"),
            "enabled": bool(ANTHROPIC_API_KEY or OPENAI_API_KEY)
        }
    }


@router.post("/tts/synthesize")
async def synthesize_text(request: Request):
    """
    HTTP endpoint for text-to-speech synthesis.
    Returns audio as base64-encoded mp3.
    Requires authentication (JWT or API key).
    Supports voice_id and provider parameters for voice selection.
    """
    # Auth check — require valid JWT or API key
    from auth.dependencies import get_current_user_flexible
    try:
        current_user = await get_current_user_flexible(request)
        if not current_user:
            raise HTTPException(401, "Authentication required")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Authentication required")

    # Rate limit: 30 requests/minute per user
    if _check_tts_rate_limit(current_user.id):
        logger.warning(f"[TTS] Rate limit exceeded for user {current_user.id}")
        raise HTTPException(429, "Rate limit exceeded — max 30 requests per minute")

    data = await request.json()
    text = data.get("text", "")
    voice_id = data.get("voice_id")  # e.g., "en-US-Neural2-C"
    provider = data.get("provider")  # e.g., "google", "elevenlabs", "openai"
    voice_settings = data.get("voice_settings")  # e.g., {stability, similarity_boost, style}

    if not text:
        raise HTTPException(400, "Text is required")

    if len(text) > 3000:
        raise HTTPException(400, "Text too long (max 3000 characters)")

    try:
        # If provider is specified, use that provider with the voice_id
        if provider == "google" and GOOGLE_TTS_ENABLED:
            tts = GoogleTTSClient(voice_name=voice_id or GOOGLE_TTS_VOICE)
            audio = await tts.synthesize(text)
        elif provider == "elevenlabs" and ELEVENLABS_API_KEY:
            tts = ElevenLabsTTSClient(voice_id=voice_id or ELEVENLABS_VOICE_ID, voice_settings=voice_settings)
            audio = await tts.synthesize(text)
        elif provider == "openai" and OPENAI_API_KEY:
            tts = OpenAITTSClient(voice=voice_id or "nova")
            audio = await tts.synthesize(text)
        # Fallback to default priority if no provider specified
        elif GOOGLE_TTS_ENABLED:
            tts = GoogleTTSClient(voice_name=voice_id if voice_id and voice_id.startswith("en-US") else GOOGLE_TTS_VOICE)
            audio = await tts.synthesize(text)
        elif ELEVENLABS_API_KEY:
            tts = ElevenLabsTTSClient(voice_id=voice_id or ELEVENLABS_VOICE_ID, voice_settings=voice_settings)
            audio = await tts.synthesize(text)
        elif OPENAI_API_KEY:
            tts = OpenAITTSClient(voice=voice_id or "nova")
            audio = await tts.synthesize(text)
        else:
            raise HTTPException(500, "No TTS provider configured")

        logger.info(f"[TTS] Synthesized with provider={provider}, voice_id={voice_id}")

        return {
            "audio": base64.b64encode(audio).decode("utf-8"),
            "format": "mp3"
        }

    except Exception as e:
        logger.error(f"[TTS] Error: {e}")
        raise HTTPException(500, "TTS synthesis failed")


@router.get("/voices")
async def list_available_voices():
    """List available TTS voices"""
    voices = []

    # Google Cloud TTS voices (Neural2 are highest quality)
    if GOOGLE_TTS_ENABLED:
        voices.extend([
            {"id": "en-US-Neural2-C", "name": "Neural2-C", "provider": "google", "description": "Female, warm and professional", "language": "en-US"},
            {"id": "en-US-Neural2-D", "name": "Neural2-D", "provider": "google", "description": "Male, deep and authoritative", "language": "en-US"},
            {"id": "en-US-Neural2-E", "name": "Neural2-E", "provider": "google", "description": "Female, soft and friendly", "language": "en-US"},
            {"id": "en-US-Neural2-F", "name": "Neural2-F", "provider": "google", "description": "Female, expressive", "language": "en-US"},
            {"id": "en-US-Neural2-G", "name": "Neural2-G", "provider": "google", "description": "Female, casual", "language": "en-US"},
            {"id": "en-US-Neural2-H", "name": "Neural2-H", "provider": "google", "description": "Female, warm", "language": "en-US"},
            {"id": "en-US-Neural2-I", "name": "Neural2-I", "provider": "google", "description": "Male, casual", "language": "en-US"},
            {"id": "en-US-Neural2-J", "name": "Neural2-J", "provider": "google", "description": "Male, conversational", "language": "en-US"},
            {"id": "en-US-Studio-O", "name": "Studio-O", "provider": "google", "description": "Female, studio quality", "language": "en-US"},
            {"id": "en-US-Studio-Q", "name": "Studio-Q", "provider": "google", "description": "Male, studio quality", "language": "en-US"},
        ])

    if ELEVENLABS_API_KEY:
        # ElevenLabs voices
        voices.extend([
            {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "provider": "elevenlabs", "description": "Warm, professional female voice"},
            {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "provider": "elevenlabs", "description": "Soft, friendly female voice"},
            {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "provider": "elevenlabs", "description": "Deep, authoritative male voice"},
            {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "provider": "elevenlabs", "description": "Natural, conversational male voice"},
        ])

    if OPENAI_API_KEY:
        # OpenAI voices
        voices.extend([
            {"id": "nova", "name": "Nova", "provider": "openai", "description": "Warm, friendly female voice"},
            {"id": "alloy", "name": "Alloy", "provider": "openai", "description": "Neutral, professional voice"},
            {"id": "echo", "name": "Echo", "provider": "openai", "description": "Soft, calm male voice"},
            {"id": "shimmer", "name": "Shimmer", "provider": "openai", "description": "Clear, expressive female voice"},
        ])

    return {"voices": voices}


# =============================================================================
# User Voice Preference Endpoints
# =============================================================================

async def get_current_user_lazy(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current user with lazy import to avoid circular import issues"""
    from auth.dependencies import get_current_user
    return await get_current_user(request, db)


@router.get("/user-voice-preference")
async def get_user_voice_preference(
    current_user: "User" = Depends(get_current_user_lazy),
    db: Session = Depends(get_db)
):
    """Get user's saved voice preference for voice assistant conversations"""
    try:
        # Check user_settings table for tts_voice and tts_provider
        result = db.execute(
            text("""
                SELECT setting_key, setting_value
                FROM user_settings
                WHERE user_id = :user_id AND setting_key IN ('tts_voice', 'tts_provider')
            """),
            {"user_id": current_user.id}
        )

        settings = {row[0]: row[1] for row in result.fetchall()}

        return {
            "voice_id": settings.get("tts_voice"),
            "provider": settings.get("tts_provider"),
            "has_preference": bool(settings.get("tts_voice"))
        }
    except Exception as e:
        logger.error(f"[VoicePreference] Error getting preference: {e}")
        return {
            "voice_id": None,
            "provider": None,
            "has_preference": False
        }


@router.put("/user-voice-preference")
async def save_user_voice_preference(
    request: dict,
    current_user: "User" = Depends(get_current_user_lazy),
    db: Session = Depends(get_db)
):
    """Save user's voice preference for voice assistant conversations"""
    voice_id = request.get("voice_id")
    provider = request.get("provider")

    if not voice_id or not provider:
        raise HTTPException(400, "voice_id and provider are required")

    # Validate provider
    valid_providers = ["google", "elevenlabs", "openai"]
    if provider not in valid_providers:
        raise HTTPException(400, f"Invalid provider. Must be one of: {', '.join(valid_providers)}")

    try:
        # Upsert tts_voice setting
        db.execute(
            text("""
                INSERT INTO user_settings (user_id, setting_key, setting_value, created_at, updated_at)
                VALUES (:user_id, 'tts_voice', :voice_id, NOW(), NOW())
                ON CONFLICT (user_id, setting_key)
                DO UPDATE SET setting_value = :voice_id, updated_at = NOW()
            """),
            {"user_id": current_user.id, "voice_id": voice_id}
        )

        # Upsert tts_provider setting
        db.execute(
            text("""
                INSERT INTO user_settings (user_id, setting_key, setting_value, created_at, updated_at)
                VALUES (:user_id, 'tts_provider', :provider, NOW(), NOW())
                ON CONFLICT (user_id, setting_key)
                DO UPDATE SET setting_value = :provider, updated_at = NOW()
            """),
            {"user_id": current_user.id, "provider": provider}
        )

        db.commit()

        logger.info(f"[VoicePreference] Saved preference for user {current_user.id}: {provider}/{voice_id}")

        return {
            "success": True,
            "voice_id": voice_id,
            "provider": provider,
            "message": "Voice preference saved successfully"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"[VoicePreference] Error saving preference: {e}")
        raise HTTPException(500, "Failed to save voice preference")
