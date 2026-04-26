"""
================================================================================
PERENNIA AI - CALL HANDLER
================================================================================
Integration layer between AudioProcessor and voice_routes.py

Provides:
- TelnyxStreamHandler: Process Telnyx WebSocket media streams
- RealtimeConversation: Manage full conversation flow
- CallContext: Track call state and metadata

Integrates with:
- audio_processor.py: STT/TTS processing
- voice_routes.py: WebSocket endpoints
- telnyx_voice_service.py: Telnyx API calls

================================================================================
"""

from __future__ import annotations

import os
import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, List, Callable, Any, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager

# OpenAI for AI-powered responses
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False

from .audio_processor import (
    AudioProcessor,
    STTConfig,
    TTSConfig,
    VoiceActivityDetector,
    convert_mulaw_to_pcm,
    convert_pcm_to_mulaw,
    audio_to_base64,
    base64_to_audio,
    get_audio_metrics,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CALL STATE MANAGEMENT
# =============================================================================

class CallState(str, Enum):
    """Call lifecycle states."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    GREETING = "greeting"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    TRANSFERRING = "transferring"
    ENDING = "ending"
    ENDED = "ended"
    ERROR = "error"


class CallDirection(str, Enum):
    """Call direction."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class CallContext:
    """
    Track call state, metadata, and conversation history.

    Maintains all information about an active call.
    """

    call_sid: str
    stream_sid: Optional[str] = None
    direction: CallDirection = CallDirection.INBOUND
    state: CallState = CallState.CONNECTING

    # Caller info
    caller_number: Optional[str] = None
    called_number: Optional[str] = None
    caller_name: Optional[str] = None

    # Lead/contact info (populated as conversation progresses)
    lead_id: Optional[str] = None
    lead_data: Dict[str, Any] = field(default_factory=dict)

    # Conversation history
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    intent: Optional[str] = None
    sentiment: str = "neutral"

    # Timing
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Audio state
    audio_buffer: bytearray = field(default_factory=bytearray)
    is_speaking: bool = False
    is_ai_speaking: bool = False

    # Metrics
    total_turns: int = 0
    avg_confidence: float = 0.85
    stt_errors: int = 0
    tts_errors: int = 0

    def add_message(self, role: str, content: str) -> None:
        """Add message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.total_turns += 1
        self.last_activity = datetime.now(timezone.utc)

    def get_duration_seconds(self) -> int:
        """Get call duration in seconds."""
        end = self.end_time or datetime.now(timezone.utc)
        return int((end - self.start_time).total_seconds())

    def to_dict(self) -> Dict[str, Any]:
        """Export context as dictionary."""
        return {
            "call_sid": self.call_sid,
            "stream_sid": self.stream_sid,
            "direction": self.direction.value,
            "state": self.state.value,
            "caller_number": self.caller_number,
            "called_number": self.called_number,
            "caller_name": self.caller_name,
            "lead_id": self.lead_id,
            "lead_data": self.lead_data,
            "conversation_history": self.conversation_history,
            "intent": self.intent,
            "sentiment": self.sentiment,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.get_duration_seconds(),
            "total_turns": self.total_turns,
            "avg_confidence": self.avg_confidence,
        }


# =============================================================================
# TELNYX STREAM HANDLER
# =============================================================================

class TelnyxStreamHandler:
    """
    Handle Telnyx Media Stream WebSocket messages.

    Processes incoming audio, manages state, and sends responses.
    """

    def __init__(
        self,
        audio_processor: AudioProcessor,
        on_transcript: Optional[Callable[[str, CallContext], Any]] = None,
        on_response: Optional[Callable[[str, CallContext], Any]] = None,
        on_state_change: Optional[Callable[[CallState, CallContext], Any]] = None,
    ):
        self.processor = audio_processor
        self.on_transcript = on_transcript
        self.on_response = on_response
        self.on_state_change = on_state_change

        self.context: Optional[CallContext] = None
        self.vad = VoiceActivityDetector()
        self._transcript_buffer: List[str] = []
        self._is_streaming_stt = False

        # Initialize OpenAI client for AI-powered responses
        self._openai_client = None
        self._openai_enabled = False
        if OPENAI_AVAILABLE:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                try:
                    self._openai_client = OpenAI(api_key=api_key)
                    self._openai_enabled = True
                    logger.info("OpenAI enabled for AI receptionist responses")
                except Exception as e:
                    logger.warning(f"Failed to initialize OpenAI: {e}")

        # AI receptionist configuration
        self._receptionist_name = os.getenv("AI_RECEPTIONIST_NAME", "Aria")
        self._business_name = os.getenv("BUSINESS_NAME", "CMG Home Loans")
        self._lo_name = os.getenv("LO_NAME", "a loan officer")

    async def handle_message(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Handle incoming WebSocket message from Telnyx.

        Args:
            message: JSON message from Telnyx

        Returns:
            Optional response message to send back
        """
        try:
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                return await self._handle_start(data)
            elif event == "media":
                return await self._handle_media(data)
            elif event == "stop":
                return await self._handle_stop(data)
            elif event == "mark":
                return await self._handle_mark(data)
            elif event == "connected":
                logger.info("Telnyx stream connected")
                return None
            else:
                logger.debug(f"Unknown Telnyx event: {event}")
                return None

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from Telnyx: {e}")
            return None
        except Exception as e:
            logger.error(f"Error handling Telnyx message: {e}")
            return None

    async def _handle_start(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle stream start event."""
        start_data = data.get("start", {})

        self.context = CallContext(
            call_sid=start_data.get("callSid", str(uuid.uuid4())),
            stream_sid=start_data.get("streamSid"),
            caller_number=start_data.get("customParameters", {}).get("From"),
            called_number=start_data.get("customParameters", {}).get("To"),
            state=CallState.CONNECTED,
        )

        logger.info(
            f"Call started: {self.context.call_sid} "
            f"from {self.context.caller_number}"
        )

        await self._set_state(CallState.GREETING)

        # Return greeting audio
        return await self._generate_greeting()

    async def _handle_media(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle media (audio) event."""
        if not self.context:
            return None

        media = data.get("media", {})
        payload = media.get("payload")

        if not payload:
            return None

        # Decode base64 audio (mu-law)
        audio_data = base64_to_audio(payload)

        # Convert to PCM for VAD
        pcm_data = convert_mulaw_to_pcm(audio_data)

        # Check voice activity
        vad_result = self.vad.process_chunk(pcm_data)

        # Don't process while AI is speaking (prevent echo)
        if self.context.is_ai_speaking:
            return None

        # Handle speech events
        if vad_result["speech_started"]:
            self.context.is_speaking = True
            self._transcript_buffer.clear()
            await self._set_state(CallState.LISTENING)

        if vad_result["is_speaking"]:
            # Buffer audio for transcription
            self.context.audio_buffer.extend(audio_data)

        if vad_result["speech_ended"]:
            self.context.is_speaking = False
            return await self._process_speech()

        return None

    async def _handle_stop(self, data: Dict[str, Any]) -> None:
        """Handle stream stop event."""
        if self.context:
            self.context.state = CallState.ENDED
            self.context.end_time = datetime.now(timezone.utc)

            logger.info(
                f"Call ended: {self.context.call_sid} "
                f"duration: {self.context.get_duration_seconds()}s"
            )

            await self._set_state(CallState.ENDED)

    async def _handle_mark(self, data: Dict[str, Any]) -> None:
        """Handle mark event (audio playback completed)."""
        mark_name = data.get("mark", {}).get("name")

        if mark_name == "ai_response_end":
            if self.context:
                self.context.is_ai_speaking = False
                await self._set_state(CallState.LISTENING)

    async def _process_speech(self) -> Optional[Dict[str, Any]]:
        """Process buffered speech audio."""
        if not self.context or not self.context.audio_buffer:
            return None

        await self._set_state(CallState.PROCESSING)

        try:
            # Transcribe the buffered audio
            transcript = await self.processor.transcribe_telephony_audio(
                bytes(self.context.audio_buffer)
            )

            self.context.audio_buffer.clear()

            if not transcript or not transcript.strip():
                await self._set_state(CallState.LISTENING)
                return None

            # Add to conversation history
            self.context.add_message("user", transcript)

            logger.info(f"Transcript: {transcript}")

            # Callback for external processing
            if self.on_transcript:
                await self.on_transcript(transcript, self.context)

            # Generate response
            return await self._generate_response(transcript)

        except Exception as e:
            logger.error(f"Error processing speech: {e}")
            self.context.stt_errors += 1
            await self._set_state(CallState.LISTENING)
            return None

    async def _generate_greeting(self) -> Optional[Dict[str, Any]]:
        """Generate initial greeting audio."""
        if not self.context:
            return None

        greeting = self._get_greeting_text()

        try:
            audio = await self.processor.synthesize_for_telephony(greeting)
            self.context.add_message("assistant", greeting)
            self.context.is_ai_speaking = True

            return self._create_media_response(audio)

        except Exception as e:
            logger.error(f"Error generating greeting: {e}")
            self.context.tts_errors += 1
            return None

    async def _generate_response(self, transcript: str) -> Optional[Dict[str, Any]]:
        """Generate response to user speech."""
        if not self.context:
            return None

        await self._set_state(CallState.SPEAKING)

        # Get response text (this would integrate with conversation engine)
        response_text = await self._get_response_text(transcript)

        if not response_text:
            await self._set_state(CallState.LISTENING)
            return None

        try:
            audio = await self.processor.synthesize_for_telephony(response_text)
            self.context.add_message("assistant", response_text)
            self.context.is_ai_speaking = True

            if self.on_response:
                await self.on_response(response_text, self.context)

            return self._create_media_response(audio)

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            self.context.tts_errors += 1
            await self._set_state(CallState.LISTENING)
            return None

    def _create_media_response(self, audio: bytes) -> Dict[str, Any]:
        """Create Telnyx media message with audio."""
        return {
            "event": "media",
            "streamSid": self.context.stream_sid if self.context else None,
            "media": {
                "payload": audio_to_base64(audio),
            },
            "mark": {
                "name": "ai_response_end",
            },
        }

    def _get_greeting_text(self) -> str:
        """Get greeting text based on config."""
        business_name = os.getenv("BUSINESS_NAME", "CMG Home Loans")
        return (
            f"Hi, this is Aria with {business_name}. "
            "How can I help you today?"
        )

    def _build_receptionist_system_prompt(self) -> str:
        """Build system prompt for AI receptionist phone conversations."""
        return f"""You are {self._receptionist_name}, a friendly and professional AI receptionist for {self._business_name}, a mortgage company.

## YOUR ROLE
You answer phone calls and help callers with mortgage-related questions. You're warm, conversational, and helpful.

## VOICE CONVERSATION GUIDELINES
- Keep responses SHORT (1-3 sentences max) - this is a phone call, not an email
- Be conversational and natural - use contractions, speak like a real person
- Ask ONE question at a time
- Listen actively and respond to what the caller actually said
- Don't repeat information they've already given you

## WHAT YOU CAN DO
- Answer general questions about mortgages, rates, loan types, and the home buying process
- Explain different loan programs (conventional, FHA, VA, USDA, jumbo)
- Discuss refinancing options and when it makes sense
- Schedule appointments or callbacks with {self._lo_name}
- Transfer to a human loan officer when requested

## WHAT YOU CANNOT DO
- Quote specific interest rates (they change daily and depend on many factors)
- Guarantee loan approval or specific terms
- Provide legal or tax advice
- Access caller's personal loan information

## TRANSFER REQUESTS
If someone asks to speak with a human, agent, or loan officer, say:
"Of course, let me transfer you to one of our loan officers. Please hold for just a moment."

## ENDING CALLS
If someone says goodbye or thanks you, respond warmly and briefly:
"Thank you for calling! Have a great day!"

Remember: You're on a phone call. Be brief, natural, and helpful."""

    async def _get_response_text(self, transcript: str) -> str:
        """
        Get AI-powered response text for transcript.

        Uses OpenAI GPT for intelligent responses with keyword-based fallback.
        """
        # Try OpenAI first for intelligent responses
        if self._openai_enabled and self._openai_client and self.context:
            try:
                # Build messages from conversation history
                messages = [{"role": "system", "content": self._build_receptionist_system_prompt()}]

                # Add conversation history (last 10 turns for context)
                for msg in self.context.conversation_history[-10:]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

                # Add current user message
                messages.append({"role": "user", "content": transcript})

                # Call OpenAI
                response = self._openai_client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=messages,
                    max_tokens=150,  # Keep responses short for phone
                    temperature=0.7,
                )

                ai_response = response.choices[0].message.content.strip()
                logger.info(f"AI response generated: {ai_response[:50]}...")
                return ai_response

            except Exception as e:
                logger.error(f"OpenAI response generation failed: {e}")
                # Fall through to keyword-based fallback

        # Fallback: Simple keyword-based responses
        return self._get_fallback_response(transcript)

    def _get_fallback_response(self, transcript: str) -> str:
        """Keyword-based fallback responses when AI is unavailable."""
        transcript_lower = transcript.lower()

        if any(word in transcript_lower for word in ["rate", "rates", "interest"]):
            return (
                "Great question about rates! They depend on your credit score "
                "and down payment. Would you like me to connect you with "
                f"{self._lo_name} for a personalized quote?"
            )

        if any(word in transcript_lower for word in ["refinance", "refi"]):
            return (
                "I'd be happy to help with refinancing. Do you know your "
                "current rate and loan balance? That helps us see if it makes sense."
            )

        if any(word in transcript_lower for word in ["appointment", "schedule", "meet", "call back"]):
            return (
                "Absolutely, I can help schedule that. "
                "What day works best for you?"
            )

        if any(word in transcript_lower for word in ["human", "person", "agent", "transfer", "speak to"]):
            return (
                "Of course, let me transfer you to one of our loan officers. "
                "Please hold for just a moment."
            )

        if any(word in transcript_lower for word in ["bye", "goodbye", "thank"]):
            return "Thank you for calling! Have a great day!"

        if any(word in transcript_lower for word in ["buy", "purchase", "house", "home"]):
            return (
                "That's exciting! Are you just starting to look, or have you "
                "already found a home you're interested in?"
            )

        if any(word in transcript_lower for word in ["pre-approval", "preapproval", "pre-qualify", "prequalify"]):
            return (
                "Getting pre-approved is a great first step! It usually takes "
                "about 24 hours. Would you like me to schedule a call to get started?"
            )

        if any(word in transcript_lower for word in ["down payment", "downpayment"]):
            return (
                "Down payments can vary from 3% to 20% depending on the loan type. "
                "Do you have a target amount in mind?"
            )

        # Default response
        return (
            "I'd love to help with that. Could you tell me a bit more about "
            "what you're looking for?"
        )

    async def _set_state(self, state: CallState) -> None:
        """Update call state and trigger callback."""
        if self.context:
            self.context.state = state

            if self.on_state_change:
                await self.on_state_change(state, self.context)


# =============================================================================
# REALTIME CONVERSATION MANAGER
# =============================================================================

class RealtimeConversation:
    """
    Manage a full real-time conversation.

    Coordinates between Telnyx WebSocket, audio processor, and
    conversation engine.
    """

    def __init__(
        self,
        websocket: Any,  # FastAPI WebSocket
        audio_processor: Optional[AudioProcessor] = None,
        conversation_engine: Optional[Callable[[str, CallContext], str]] = None,
    ):
        self.websocket = websocket
        self.processor = audio_processor or AudioProcessor()
        self.conversation_engine = conversation_engine

        self.handler = TelnyxStreamHandler(
            self.processor,
            on_transcript=self._on_transcript,
            on_response=self._on_response,
            on_state_change=self._on_state_change,
        )

        self._running = False

    async def run(self) -> CallContext:
        """
        Run the conversation loop.

        Returns:
            CallContext with full conversation data
        """
        self._running = True

        try:
            async for message in self.websocket.iter_text():
                if not self._running:
                    break

                response = await self.handler.handle_message(message)

                if response:
                    await self.websocket.send_json(response)

        except Exception as e:
            logger.error(f"Conversation error: {e}")

        finally:
            self._running = False

        return self.handler.context

    async def stop(self) -> None:
        """Stop the conversation."""
        self._running = False

    async def send_audio(self, audio: bytes) -> None:
        """Send audio to caller."""
        if self.handler.context:
            message = self.handler._create_media_response(audio)
            await self.websocket.send_json(message)

    async def _on_transcript(self, transcript: str, context: CallContext) -> None:
        """Handle new transcript."""
        logger.debug(f"Transcript: {transcript}")

        # Could trigger external processing here
        # e.g., extract lead info, update CRM, etc.

    async def _on_response(self, response: str, context: CallContext) -> None:
        """Handle AI response."""
        logger.debug(f"Response: {response}")

    async def _on_state_change(self, state: CallState, context: CallContext) -> None:
        """Handle state changes."""
        logger.debug(f"State: {state.value}")


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

@asynccontextmanager
async def create_call_handler(
    websocket: Any,
    stt_provider: str = "deepgram",
    tts_provider: str = "elevenlabs",
) -> AsyncIterator[RealtimeConversation]:
    """
    Create call handler as async context manager.

    Args:
        websocket: FastAPI WebSocket connection
        stt_provider: STT provider name
        tts_provider: TTS provider name

    Yields:
        Configured RealtimeConversation instance
    """
    processor = AudioProcessor(
        stt_config=STTConfig(provider=stt_provider),
        tts_config=TTSConfig(provider=tts_provider),
    )

    conversation = RealtimeConversation(
        websocket=websocket,
        audio_processor=processor,
    )

    try:
        yield conversation
    finally:
        await processor.close()


# =============================================================================
# INTEGRATION WITH VOICE_ROUTES.PY
# =============================================================================

async def handle_voice_stream_websocket(
    websocket: Any,
    db_session: Any,
) -> Dict[str, Any]:
    """
    Handle voice stream WebSocket - integrates with voice_routes.py.

    This function can be called from voice_routes.py to handle the
    WebSocket connection using the new audio processor.

    Args:
        websocket: FastAPI WebSocket
        db_session: Database session for saving call data

    Returns:
        Call summary dictionary
    """
    async with create_call_handler(websocket) as conversation:
        context = await conversation.run()

        # Return summary for saving to database
        return context.to_dict() if context else {}
