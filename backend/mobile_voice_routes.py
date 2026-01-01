"""
Mobile Voice Agent Routes
Real-time voice conversation for Perennia mobile app via WebSocket
Uses Deepgram for streaming STT and ElevenLabs for streaming TTS
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import json
import asyncio
import base64
import os
import httpx
from typing import Optional, Dict, Any, AsyncGenerator
import uuid

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

# Voice settings
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel - warm female voice
TTS_MODEL = os.getenv("TTS_MODEL", "eleven_turbo_v2_5")  # Fast model for low latency

# Aria system prompt for voice interactions
ARIA_VOICE_PROMPT = """You are Aria, a warm and professional AI assistant for mortgage loan officers.
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

    def __init__(self, voice_id: str = ELEVENLABS_VOICE_ID):
        self.api_key = ELEVENLABS_API_KEY
        self.voice_id = voice_id
        self.model_id = TTS_MODEL

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
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.5,
                "use_speaker_boost": True
            },
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
            "model": "tts-1",  # Fast model for low latency
            "input": text,
            "voice": self.voice,
            "response_format": "mp3",
            "speed": 1.05
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)

            if response.status_code != 200:
                logger.error(f"[OpenAITTS] Error: {response.status_code}")
                return b""

            return response.content


class AriaVoiceAgent:
    """Voice agent that processes user speech and generates responses"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.conversation_history = []
        self.session_id = str(uuid.uuid4())

    async def process_user_message(self, transcript: str, db: Session) -> str:
        """Process user message and generate AI response"""
        # Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": transcript
        })

        # Import LangGraph chat handler
        import traceback
        try:
            from ai_command_routes import langgraph_chat_handler

            logger.info(f"[AriaVoiceAgent] Processing: '{transcript}' for user {self.user_id}")

            # Call the existing LangGraph handler
            result = await langgraph_chat_handler(
                message=transcript,
                user_email=self.user_id,
                db=db
            )

            logger.info(f"[AriaVoiceAgent] LangGraph result: {result}")
            response = result.get("response", "I'm having trouble processing that. Could you try again?")

        except Exception as e:
            logger.error(f"[AriaVoiceAgent] Error calling LangGraph: {e}")
            logger.error(f"[AriaVoiceAgent] Traceback: {traceback.format_exc()}")
            # Fallback to simple Anthropic call for voice
            try:
                from anthropic import Anthropic
                client = Anthropic()

                # Simple direct response for voice
                voice_messages = [{"role": "user", "content": transcript}]
                if self.conversation_history:
                    voice_messages = self.conversation_history[-6:] + voice_messages  # Keep last 3 exchanges

                ai_response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=150,
                    system="""You are Aria, a helpful mortgage assistant. Keep responses brief (under 50 words) and conversational for voice. Be warm and professional.""",
                    messages=voice_messages
                )
                response = ai_response.content[0].text
                logger.info(f"[AriaVoiceAgent] Fallback response: {response}")
            except Exception as fallback_error:
                logger.error(f"[AriaVoiceAgent] Fallback also failed: {fallback_error}")
                response = "Sorry, I'm having trouble right now. Try again in a moment."

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

    async def start(self):
        """Initialize the voice session"""
        logger.info(f"[MobileVoiceSession] Starting session {self.session_id} for user {self.user_id}")

        # Initialize TTS client
        if ELEVENLABS_API_KEY:
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

        # Play greeting - keep it casual and short
        greeting = "Hey! What's up?"
        await self._speak(greeting)

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
            if isinstance(self.tts_client, ElevenLabsTTSClient):
                # Stream audio chunks
                async for chunk in self.tts_client.synthesize_stream(text):
                    if not self.is_active:
                        break
                    # Send audio chunk as base64
                    await self._send_event("audio", {
                        "data": base64.b64encode(chunk).decode("utf-8"),
                        "format": "mp3"
                    })
            else:
                # Non-streaming fallback
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
        msg_type = message.get("type", "")

        if msg_type == "audio":
            # Incoming audio from mobile app
            audio_data = message.get("data", "")
            if audio_data and self.stt_client:
                audio_bytes = base64.b64decode(audio_data)
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
    WebSocket endpoint for real-time voice conversation with Aria.

    Protocol:
    - Client sends audio chunks as base64-encoded data
    - Server streams back AI response audio
    - Both sides can interrupt the conversation

    Message Types (Client -> Server):
    - {"type": "audio", "data": "<base64-audio>"}
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

    try:
        await websocket.accept()
        logger.info("[MobileVoice] WebSocket accepted")

        # Authenticate user from token (query param, header, or protocol)
        auth_user, auth_error = authenticate_websocket(websocket, db, require_auth=False)

        if auth_user:
            user_id = auth_user.email
            logger.info(f"[MobileVoice] Authenticated user: {user_id} (ID: {auth_user.id})")
        else:
            user_id = "admin@perenniaai.com"  # Fallback for backwards compatibility
            logger.warning(f"[MobileVoice] Auth failed ({auth_error}), using fallback user")

        # Create voice session
        session = MobileVoiceSession(websocket, user_id, db)
        await session.start()

        # Main message loop
        try:
            while True:
                message = await websocket.receive_json()
                await session.handle_message(message)

        except WebSocketDisconnect:
            logger.info("[MobileVoice] Client disconnected")

    except Exception as e:
        logger.error(f"[MobileVoice] Error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass

    finally:
        try:
            await session.close()
        except:
            pass


# =============================================================================
# HTTP Endpoints for Voice Status and Configuration
# =============================================================================

@router.get("/status")
async def get_voice_status():
    """Get voice service status"""
    return {
        "stt": {
            "provider": "deepgram" if DEEPGRAM_API_KEY else "none",
            "enabled": bool(DEEPGRAM_API_KEY)
        },
        "tts": {
            "provider": "elevenlabs" if ELEVENLABS_API_KEY else ("openai" if OPENAI_API_KEY else "none"),
            "enabled": bool(ELEVENLABS_API_KEY or OPENAI_API_KEY),
            "voice_id": ELEVENLABS_VOICE_ID if ELEVENLABS_API_KEY else "nova"
        },
        "llm": {
            "provider": "anthropic" if ANTHROPIC_API_KEY else ("openai" if OPENAI_API_KEY else "none"),
            "enabled": bool(ANTHROPIC_API_KEY or OPENAI_API_KEY)
        }
    }


@router.post("/tts/synthesize")
async def synthesize_text(request: dict):
    """
    HTTP endpoint for text-to-speech synthesis.
    Returns audio as base64-encoded mp3.
    """
    text = request.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")

    if len(text) > 500:
        raise HTTPException(400, "Text too long (max 500 characters)")

    try:
        if ELEVENLABS_API_KEY:
            tts = ElevenLabsTTSClient()
            audio = await tts.synthesize(text)
        elif OPENAI_API_KEY:
            tts = OpenAITTSClient()
            audio = await tts.synthesize(text)
        else:
            raise HTTPException(500, "No TTS provider configured")

        return {
            "audio": base64.b64encode(audio).decode("utf-8"),
            "format": "mp3"
        }

    except Exception as e:
        logger.error(f"[TTS] Error: {e}")
        raise HTTPException(500, f"TTS synthesis failed: {str(e)}")


@router.get("/voices")
async def list_available_voices():
    """List available TTS voices"""
    voices = []

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
