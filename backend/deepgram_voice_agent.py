"""
Deepgram Voice Agent API Integration
All-in-one voice agent using Deepgram's Voice Agent API
Handles STT, LLM, and TTS in a single WebSocket connection
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import json
import asyncio
import base64
import os
from typing import Optional, Dict, Any
import uuid

# Database imports
from database import get_db
from utils.websocket_auth import authenticate_websocket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice-agent", tags=["voice-agent"])

# Configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# White-label voice assistant name — configurable per deployment/tenant (H-1)
DEFAULT_VOICE_ASSISTANT_NAME = os.getenv("VOICE_ASSISTANT_NAME", "Aria")

# Voice agent system prompt — uses {assistant_name} and {business_name} placeholders for white-label
VOICE_AGENT_PROMPT_TEMPLATE = """You are {assistant_name}, an AI assistant for mortgage loan officers at {business_name}.

You are warm, friendly, and professional. Keep responses concise — under 50 words when possible.

You can help with:
- Answering questions about leads, loans, and pipeline
- Discussing scheduling options and availability
- Composing text messages and emails (which the LO can review and send)
- Planning tasks and follow-ups
- Providing mortgage rate and market information

IMPORTANT: You are a conversational assistant. You can discuss and plan actions, but
you cannot directly send messages, book appointments, or modify CRM data. When the
loan officer wants to take an action, confirm what they'd like to do and let them
know it will be queued for execution through the voice assistant app.

If unsure about something, say so. Don't make up loan details or rates."""


def get_voice_agent_prompt(assistant_name: Optional[str] = None, business_name: str = "{business_name}") -> str:
    """Get the voice agent system prompt with configurable assistant and business names.

    Args:
        assistant_name: Override assistant name. Defaults to DEFAULT_VOICE_ASSISTANT_NAME.
        business_name: Business name to insert. Defaults to '{business_name}' placeholder
                       for downstream formatting by the voice agent session.
    """
    name = assistant_name or DEFAULT_VOICE_ASSISTANT_NAME
    return VOICE_AGENT_PROMPT_TEMPLATE.format(assistant_name=name, business_name=business_name)


class DeepgramVoiceAgentSession:
    """
    Manages a voice conversation session using Deepgram's Voice Agent API.
    Acts as a proxy between the mobile client and Deepgram.
    """

    def __init__(self, client_ws: WebSocket, user_id: str, db: Session):
        self.client_ws = client_ws
        self.user_id = user_id
        self.db = db
        self.session_id = str(uuid.uuid4())
        self.is_active = True
        self.deepgram_ws = None

    async def start(self):
        """Initialize the voice agent session"""
        logger.info(f"[VoiceAgent] Starting session {self.session_id} for user {self.user_id}")

        try:
            # Connect to Deepgram Voice Agent API
            await self._connect_deepgram()

            # Send session started to client
            await self._send_to_client("session_started", {
                "session_id": self.session_id,
                "provider": "deepgram_voice_agent"
            })

        except Exception as e:
            logger.error(f"[VoiceAgent] Failed to start session: {e}")
            await self._send_to_client("error", {"message": "Internal server error"})
            raise

    async def _connect_deepgram(self):
        """Connect to Deepgram Voice Agent WebSocket"""
        import websockets

        # Deepgram Voice Agent WebSocket URL (correct endpoint)
        url = "wss://agent.deepgram.com/v1/agent/converse"

        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}"
        }

        logger.info("[VoiceAgent] Connecting to Deepgram Voice Agent API...")
        # websockets v10+ uses additional_headers instead of extra_headers
        self.deepgram_ws = await websockets.connect(url, additional_headers=headers)
        logger.info("[VoiceAgent] Connected to Deepgram Voice Agent API")

        # Configure the agent
        config = {
            "type": "SettingsConfiguration",
            "audio": {
                "input": {
                    "encoding": "linear16",
                    "sample_rate": 16000
                },
                "output": {
                    "encoding": "linear16",
                    "sample_rate": 16000,
                    "container": "none"
                }
            },
            "agent": {
                "listen": {
                    "model": "nova-2"
                },
                "think": {
                    "provider": {
                        "type": "anthropic"
                    },
                    "model": "claude-haiku-4-5-20251001",
                    "instructions": get_voice_agent_prompt()
                },
                "speak": {
                    "model": "aura-asteria-en"
                }
            }
        }

        await self.deepgram_ws.send(json.dumps(config))
        logger.info("[VoiceAgent] Sent configuration to Deepgram")

        # Start listening for Deepgram responses
        asyncio.create_task(self._listen_deepgram())

    async def _listen_deepgram(self):
        """Listen for messages from Deepgram and forward to client"""
        try:
            async for message in self.deepgram_ws:
                if not self.is_active:
                    break

                # Check if binary (audio) or text (JSON)
                if isinstance(message, bytes):
                    # Audio data - send to client
                    await self._send_to_client("audio", {
                        "data": base64.b64encode(message).decode("utf-8"),
                        "format": "linear16",
                        "sample_rate": 16000
                    })
                else:
                    # JSON message
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type", "")

                        logger.debug(f"[VoiceAgent] Deepgram message: {msg_type}")

                        if msg_type == "Welcome":
                            logger.info("[VoiceAgent] Deepgram welcome received")

                        elif msg_type == "SettingsApplied":
                            logger.info("[VoiceAgent] Settings applied, ready for audio")
                            await self._send_to_client("ready", {})

                        elif msg_type == "ConversationText":
                            # Transcription or response text
                            role = data.get("role", "")
                            content = data.get("content", "")

                            if role == "user":
                                await self._send_to_client("transcript", {
                                    "text": content,
                                    "is_final": True
                                })
                            elif role == "assistant":
                                await self._send_to_client("response_text", {
                                    "text": content
                                })

                        elif msg_type == "UserStartedSpeaking":
                            await self._send_to_client("user_speaking", {})

                        elif msg_type == "AgentThinking":
                            await self._send_to_client("processing", {})

                        elif msg_type == "AgentStartedSpeaking":
                            await self._send_to_client("speaking", {})

                        elif msg_type == "AgentAudioDone":
                            await self._send_to_client("speech_complete", {})

                        elif msg_type == "Error":
                            error_msg = data.get("message", "Unknown error")
                            logger.error(f"[VoiceAgent] Deepgram error: {error_msg}")
                            await self._send_to_client("error", {"message": error_msg})

                    except json.JSONDecodeError:
                        logger.warning(f"[VoiceAgent] Could not parse message: {message[:100]}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"[VoiceAgent] Deepgram connection closed: {e}")
        except Exception as e:
            logger.error(f"[VoiceAgent] Error in Deepgram listener: {e}")
        finally:
            self.is_active = False

    async def handle_client_message(self, message: Dict[str, Any]):
        """Handle incoming message from mobile client"""
        msg_type = message.get("type", "")

        if msg_type == "audio":
            # Forward audio to Deepgram
            audio_data = message.get("data", "")
            if audio_data and self.deepgram_ws:
                audio_bytes = base64.b64decode(audio_data)

                # Strip WAV header if present
                if len(audio_bytes) > 44 and audio_bytes[:4] == b'RIFF':
                    audio_bytes = audio_bytes[44:]

                await self.deepgram_ws.send(audio_bytes)
                logger.debug(f"[VoiceAgent] Forwarded {len(audio_bytes)} bytes to Deepgram")

        elif msg_type == "text_input":
            # Send text directly (for testing or fallback)
            text = message.get("text", "")
            if text and self.deepgram_ws:
                inject_msg = {
                    "type": "InjectAgentMessage",
                    "message": text
                }
                await self.deepgram_ws.send(json.dumps(inject_msg))

        elif msg_type == "interrupt":
            # Interrupt the agent
            if self.deepgram_ws:
                interrupt_msg = {"type": "ClearPlayback"}
                await self.deepgram_ws.send(json.dumps(interrupt_msg))

        elif msg_type == "ping":
            await self._send_to_client("pong", {})

    async def _send_to_client(self, event_type: str, data: Dict[str, Any]):
        """Send event to mobile client"""
        try:
            await self.client_ws.send_json({
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **data
            })
        except Exception as e:
            logger.error(f"[VoiceAgent] Error sending to client: {e}")

    async def close(self):
        """Close the session"""
        self.is_active = False

        if self.deepgram_ws:
            try:
                await self.deepgram_ws.close()
            except Exception as e:
                logger.exception(f"Failed to close Deepgram WebSocket (may already be closed): {e}")

        logger.info(f"[VoiceAgent] Session {self.session_id} closed")


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws")
async def voice_agent_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for Deepgram Voice Agent.

    This proxies between the mobile app and Deepgram's Voice Agent API,
    providing a unified STT + LLM + TTS solution.

    Message Types (Client -> Server):
    - {"type": "audio", "data": "<base64-audio>"}
    - {"type": "text_input", "text": "..."}
    - {"type": "interrupt"}
    - {"type": "ping"}

    Message Types (Server -> Client):
    - {"type": "session_started", "session_id": "..."}
    - {"type": "ready"}
    - {"type": "transcript", "text": "...", "is_final": bool}
    - {"type": "user_speaking"}
    - {"type": "processing"}
    - {"type": "speaking"}
    - {"type": "response_text", "text": "..."}
    - {"type": "audio", "data": "<base64-audio>", "format": "linear16"}
    - {"type": "speech_complete"}
    - {"type": "error", "message": "..."}
    - {"type": "pong"}
    """
    logger.info(f"[VoiceAgent] WebSocket connection from {websocket.client}")

    session = None

    try:
        await websocket.accept()
        logger.info("[VoiceAgent] WebSocket accepted")

        # Authenticate user from token (query param, header, or protocol)
        auth_user, auth_error = authenticate_websocket(websocket, db)

        if auth_user:
            user_id = auth_user.email
            logger.info(f"[VoiceAgent] Authenticated user ID: {auth_user.id}")
        else:
            logger.warning(f"[VoiceAgent] Auth failed: {auth_error}")
            await websocket.close(code=4001, reason="Authentication required")
            return

        # Create and start session
        session = DeepgramVoiceAgentSession(websocket, user_id, db)
        await session.start()

        # Main message loop
        while session.is_active:
            try:
                message = await websocket.receive_json()
                await session.handle_client_message(message)
            except WebSocketDisconnect:
                logger.info("[VoiceAgent] Client disconnected")
                break

    except Exception as e:
        logger.error(f"[VoiceAgent] Error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Internal server error"
            })
        except Exception as e:
            logger.exception(f"Failed to send error message to WebSocket client (may have disconnected): {e}")

    finally:
        if session:
            await session.close()


@router.get("/status")
async def get_voice_agent_status():
    """Get voice agent status"""
    return {
        "enabled": bool(DEEPGRAM_API_KEY),
        "provider": "deepgram_voice_agent",
        "features": {
            "stt": "nova-2",
            "llm": "claude-haiku-4-5",
            "tts": "aura-asteria-en"
        }
    }
