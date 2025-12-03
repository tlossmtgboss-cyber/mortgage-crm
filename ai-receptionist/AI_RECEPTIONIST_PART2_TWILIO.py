"""
================================================================================
PERENNIA AI - CONVERSATION ENGINE
================================================================================
Part 2: Twilio Voice Integration

Real-time voice handling with:
- Inbound call webhooks
- WebSocket audio streaming
- DTMF handling
- Call control (transfer, hold, conference)
- Recording management

================================================================================
"""

import os
import json
import asyncio
import logging
import base64
import hmac
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode

# Web framework imports
try:
    from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import PlainTextResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

try:
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.voice_response import VoiceResponse, Gather, Say, Dial, Stream
    from twilio.request_validator import RequestValidator
    HAS_TWILIO = True
except ImportError:
    HAS_TWILIO = False

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class TwilioConfig:
    """Twilio configuration"""
    account_sid: str = None
    auth_token: str = None
    phone_number: str = None  # Your Twilio phone number

    # Webhook URLs (set these to your server)
    base_url: str = None  # e.g., "https://your-domain.com"
    voice_webhook_path: str = "/voice/inbound"
    status_callback_path: str = "/voice/status"
    stream_path: str = "/voice/stream"

    # Voice settings
    voice_name: str = "Polly.Joanna"  # AWS Polly voice
    language: str = "en-US"

    # Timeouts
    speech_timeout: int = 3  # Seconds of silence before processing
    gather_timeout: int = 10  # Max seconds to wait for input

    # Recording
    record_calls: bool = True
    transcribe_recordings: bool = True

    def __post_init__(self):
        self.account_sid = self.account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = self.auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = self.phone_number or os.getenv("TWILIO_PHONE_NUMBER")
        self.base_url = self.base_url or os.getenv("TWILIO_WEBHOOK_BASE_URL")

    @property
    def voice_webhook_url(self) -> str:
        return f"{self.base_url}{self.voice_webhook_path}"

    @property
    def status_callback_url(self) -> str:
        return f"{self.base_url}{self.status_callback_path}"

    @property
    def stream_url(self) -> str:
        # WebSocket URL
        ws_base = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_base}{self.stream_path}"


# =============================================================================
# CALL STATE
# =============================================================================

class CallStatus(str, Enum):
    """Twilio call statuses"""
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    BUSY = "busy"
    FAILED = "failed"
    NO_ANSWER = "no-answer"
    CANCELED = "canceled"


@dataclass
class CallContext:
    """Context for an active call"""
    call_sid: str
    from_number: str
    to_number: str
    direction: str  # "inbound" or "outbound"

    # State
    status: CallStatus = CallStatus.QUEUED
    started_at: datetime = None
    answered_at: datetime = None
    ended_at: datetime = None

    # Streaming
    stream_sid: Optional[str] = None
    is_streaming: bool = False

    # Recording
    recording_sid: Optional[str] = None
    recording_url: Optional[str] = None

    # Transfer
    parent_call_sid: Optional[str] = None
    child_call_sid: Optional[str] = None
    conference_sid: Optional[str] = None

    # DTMF
    dtmf_digits: str = ""

    # Caller ID info
    caller_name: Optional[str] = None
    caller_city: Optional[str] = None
    caller_state: Optional[str] = None


# =============================================================================
# TWILIO VOICE HANDLER
# =============================================================================

class TwilioVoiceHandler:
    """
    Handles Twilio voice webhooks and call control.

    This class manages:
    - Inbound call handling
    - TwiML generation
    - Call transfers
    - Recording
    - WebSocket streaming setup
    """

    def __init__(
        self,
        config: TwilioConfig = None,
        conversation_handler: Callable = None,
    ):
        self.config = config or TwilioConfig()
        self.conversation_handler = conversation_handler

        if HAS_TWILIO and self.config.account_sid:
            self.client = TwilioClient(
                self.config.account_sid,
                self.config.auth_token,
            )
            self.validator = RequestValidator(self.config.auth_token)
        else:
            self.client = None
            self.validator = None

        # Track active calls
        self.active_calls: Dict[str, CallContext] = {}

    def validate_request(self, url: str, params: dict, signature: str) -> bool:
        """Validate that request came from Twilio"""
        if not self.validator:
            logger.warning("No validator configured - skipping validation")
            return True
        return self.validator.validate(url, params, signature)

    def create_call_context(self, params: dict) -> CallContext:
        """Create CallContext from webhook parameters"""
        return CallContext(
            call_sid=params.get("CallSid"),
            from_number=params.get("From"),
            to_number=params.get("To"),
            direction=params.get("Direction", "inbound"),
            caller_name=params.get("CallerName"),
            caller_city=params.get("FromCity"),
            caller_state=params.get("FromState"),
            started_at=datetime.now(),
        )

    # -------------------------------------------------------------------------
    # TwiML Generation
    # -------------------------------------------------------------------------

    def generate_greeting_twiml(
        self,
        greeting: str,
        gather_speech: bool = True,
        stream_audio: bool = False,
    ) -> str:
        """
        Generate TwiML for initial call handling.

        Args:
            greeting: Text to speak to caller
            gather_speech: Whether to gather speech input
            stream_audio: Whether to enable WebSocket streaming
        """
        response = VoiceResponse()

        # Start recording if configured
        if self.config.record_calls:
            response.record(
                timeout=0,
                transcribe=self.config.transcribe_recordings,
                play_beep=False,
                recording_status_callback=f"{self.config.base_url}/voice/recording-status",
            )

        if stream_audio:
            # Use bidirectional streaming for real-time STT/TTS
            start = Stream(
                url=self.config.stream_url,
                track="both_tracks",  # Capture both inbound and outbound audio
            )
            start.parameter(name="CallSid", value="{{CallSid}}")
            response.append(start)

            # Say greeting while stream is active
            response.say(greeting, voice=self.config.voice_name, language=self.config.language)

            # Pause to keep connection open
            response.pause(length=3600)  # 1 hour max

        elif gather_speech:
            # Use Gather for speech recognition
            gather = Gather(
                input="speech",
                action=f"{self.config.base_url}/voice/process-speech",
                method="POST",
                language=self.config.language,
                speech_timeout=str(self.config.speech_timeout),
                timeout=self.config.gather_timeout,
                profanity_filter=False,
            )
            gather.say(greeting, voice=self.config.voice_name, language=self.config.language)
            response.append(gather)

            # If no input, prompt again
            response.redirect(f"{self.config.base_url}/voice/no-input")

        else:
            # Simple say without gathering
            response.say(greeting, voice=self.config.voice_name, language=self.config.language)

        return str(response)

    def generate_response_twiml(
        self,
        message: str,
        gather_speech: bool = True,
        action_url: str = None,
    ) -> str:
        """Generate TwiML for a response in the conversation"""
        response = VoiceResponse()

        if gather_speech:
            gather = Gather(
                input="speech",
                action=action_url or f"{self.config.base_url}/voice/process-speech",
                method="POST",
                language=self.config.language,
                speech_timeout=str(self.config.speech_timeout),
                timeout=self.config.gather_timeout,
                profanity_filter=False,
            )
            gather.say(message, voice=self.config.voice_name, language=self.config.language)
            response.append(gather)

            # Fallback if no speech
            response.say(
                "I didn't catch that. Could you please repeat?",
                voice=self.config.voice_name,
            )
            response.redirect(f"{self.config.base_url}/voice/retry")
        else:
            response.say(message, voice=self.config.voice_name, language=self.config.language)

        return str(response)

    def generate_transfer_twiml(
        self,
        target_number: str,
        announce_message: str = None,
        warm_transfer: bool = True,
        caller_id: str = None,
    ) -> str:
        """Generate TwiML for call transfer"""
        response = VoiceResponse()

        if announce_message:
            response.say(announce_message, voice=self.config.voice_name)

        dial = Dial(
            caller_id=caller_id or self.config.phone_number,
            action=f"{self.config.base_url}/voice/transfer-complete",
            timeout=30,
        )

        if warm_transfer:
            # Use conference for warm transfer
            dial.conference(
                "WarmTransfer",
                beep=False,
                start_conference_on_enter=True,
                end_conference_on_exit=True,
                wait_url="http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical",
            )
        else:
            # Direct dial
            dial.number(target_number)

        response.append(dial)
        return str(response)

    def generate_hold_twiml(
        self,
        hold_message: str = "Please hold while I look into this.",
        music_url: str = None,
        max_seconds: int = 300,
    ) -> str:
        """Generate TwiML to put caller on hold"""
        response = VoiceResponse()

        response.say(hold_message, voice=self.config.voice_name)

        if music_url:
            response.play(music_url, loop=0)
        else:
            # Default hold music
            response.play(
                "http://twimlets.com/holdmusic?Bucket=com.twilio.music.ambient",
                loop=0,
            )

        return str(response)

    def generate_voicemail_twiml(
        self,
        prompt: str = "Please leave a message after the beep.",
        max_length: int = 120,
    ) -> str:
        """Generate TwiML for voicemail recording"""
        response = VoiceResponse()

        response.say(prompt, voice=self.config.voice_name)
        response.record(
            max_length=max_length,
            action=f"{self.config.base_url}/voice/voicemail-complete",
            transcribe=True,
            transcribe_callback=f"{self.config.base_url}/voice/voicemail-transcription",
            play_beep=True,
        )

        # If they hang up or timeout
        response.say(
            "Thank you for your message. Goodbye!",
            voice=self.config.voice_name,
        )
        response.hangup()

        return str(response)

    def generate_goodbye_twiml(
        self,
        message: str = "Thank you for calling. Have a great day!",
    ) -> str:
        """Generate TwiML to end the call"""
        response = VoiceResponse()
        response.say(message, voice=self.config.voice_name)
        response.hangup()
        return str(response)

    def generate_dtmf_menu_twiml(
        self,
        prompt: str,
        options: Dict[str, str],
        timeout: int = 10,
    ) -> str:
        """Generate TwiML for DTMF menu"""
        response = VoiceResponse()

        gather = Gather(
            input="dtmf speech",
            action=f"{self.config.base_url}/voice/process-dtmf",
            method="POST",
            timeout=timeout,
            num_digits=1,
        )
        gather.say(prompt, voice=self.config.voice_name)
        response.append(gather)

        # Repeat if no input
        response.redirect(f"{self.config.base_url}/voice/menu")

        return str(response)

    # -------------------------------------------------------------------------
    # Call Control (using Twilio REST API)
    # -------------------------------------------------------------------------

    async def update_call(
        self,
        call_sid: str,
        twiml: str = None,
        url: str = None,
        status: str = None,
    ) -> bool:
        """Update an in-progress call with new TwiML"""
        if not self.client:
            logger.error("Twilio client not configured")
            return False

        try:
            update_params = {}
            if twiml:
                update_params["twiml"] = twiml
            if url:
                update_params["url"] = url
            if status:
                update_params["status"] = status

            self.client.calls(call_sid).update(**update_params)
            return True
        except Exception as e:
            logger.error(f"Failed to update call {call_sid}: {e}")
            return False

    async def transfer_call(
        self,
        call_sid: str,
        target_number: str,
        warm: bool = True,
        announce: str = None,
    ) -> bool:
        """Transfer a call to another number"""
        twiml = self.generate_transfer_twiml(
            target_number=target_number,
            announce_message=announce,
            warm_transfer=warm,
        )
        return await self.update_call(call_sid, twiml=twiml)

    async def put_on_hold(
        self,
        call_sid: str,
        message: str = None,
    ) -> bool:
        """Put a call on hold"""
        twiml = self.generate_hold_twiml(hold_message=message or "Please hold.")
        return await self.update_call(call_sid, twiml=twiml)

    async def resume_call(
        self,
        call_sid: str,
        message: str,
    ) -> bool:
        """Resume a call from hold with a message"""
        twiml = self.generate_response_twiml(message)
        return await self.update_call(call_sid, twiml=twiml)

    async def end_call(
        self,
        call_sid: str,
        message: str = None,
    ) -> bool:
        """End a call gracefully"""
        if message:
            twiml = self.generate_goodbye_twiml(message)
            return await self.update_call(call_sid, twiml=twiml)
        return await self.update_call(call_sid, status="completed")

    async def send_to_voicemail(
        self,
        call_sid: str,
        prompt: str = None,
    ) -> bool:
        """Send caller to voicemail"""
        twiml = self.generate_voicemail_twiml(prompt=prompt or "Please leave a message.")
        return await self.update_call(call_sid, twiml=twiml)

    # -------------------------------------------------------------------------
    # Outbound Calls
    # -------------------------------------------------------------------------

    async def make_call(
        self,
        to_number: str,
        twiml: str = None,
        url: str = None,
        caller_id: str = None,
        status_callback: str = None,
        record: bool = None,
    ) -> Optional[str]:
        """
        Initiate an outbound call.

        Returns:
            Call SID if successful, None otherwise
        """
        if not self.client:
            logger.error("Twilio client not configured")
            return None

        try:
            call_params = {
                "to": to_number,
                "from_": caller_id or self.config.phone_number,
                "status_callback": status_callback or self.config.status_callback_url,
                "status_callback_event": ["initiated", "ringing", "answered", "completed"],
            }

            if twiml:
                call_params["twiml"] = twiml
            elif url:
                call_params["url"] = url
            else:
                call_params["url"] = f"{self.config.base_url}/voice/outbound-answer"

            if record is not None:
                call_params["record"] = record
            elif self.config.record_calls:
                call_params["record"] = True

            call = self.client.calls.create(**call_params)

            # Track the call
            self.active_calls[call.sid] = CallContext(
                call_sid=call.sid,
                from_number=caller_id or self.config.phone_number,
                to_number=to_number,
                direction="outbound",
                started_at=datetime.now(),
            )

            return call.sid

        except Exception as e:
            logger.error(f"Failed to make call to {to_number}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Recording Management
    # -------------------------------------------------------------------------

    async def get_recording(self, recording_sid: str) -> Optional[Dict]:
        """Get recording details"""
        if not self.client:
            return None

        try:
            recording = self.client.recordings(recording_sid).fetch()
            return {
                "sid": recording.sid,
                "call_sid": recording.call_sid,
                "duration": recording.duration,
                "url": f"https://api.twilio.com{recording.uri.replace('.json', '.mp3')}",
                "status": recording.status,
            }
        except Exception as e:
            logger.error(f"Failed to get recording {recording_sid}: {e}")
            return None

    async def delete_recording(self, recording_sid: str) -> bool:
        """Delete a recording"""
        if not self.client:
            return False

        try:
            self.client.recordings(recording_sid).delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete recording {recording_sid}: {e}")
            return False


# =============================================================================
# WEBSOCKET AUDIO STREAMER
# =============================================================================

class AudioStreamHandler:
    """
    Handles bidirectional audio streaming over WebSocket.

    This enables real-time speech-to-text and text-to-speech
    without the latency of webhook-based gather/say.
    """

    def __init__(
        self,
        stt_handler: Callable = None,  # Speech-to-text callback
        tts_handler: Callable = None,  # Text-to-speech callback
    ):
        self.stt_handler = stt_handler
        self.tts_handler = tts_handler
        self.active_streams: Dict[str, dict] = {}

    async def handle_stream(
        self,
        websocket: "WebSocket",
        call_sid: str,
    ):
        """
        Handle a WebSocket audio stream from Twilio.

        Twilio sends media events with base64-encoded audio.
        We process it through STT, get response, and send back TTS audio.
        """
        stream_id = None
        audio_buffer = bytearray()

        try:
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)
                event = data.get("event")

                if event == "connected":
                    logger.info(f"Stream connected for call {call_sid}")

                elif event == "start":
                    stream_id = data["streamSid"]
                    self.active_streams[stream_id] = {
                        "call_sid": call_sid,
                        "started_at": datetime.now(),
                        "audio_format": data["start"]["mediaFormat"],
                    }
                    logger.info(f"Stream started: {stream_id}")

                elif event == "media":
                    # Incoming audio from caller
                    payload = data["media"]["payload"]
                    audio_chunk = base64.b64decode(payload)
                    audio_buffer.extend(audio_chunk)

                    # Process when we have enough audio (e.g., 100ms chunks)
                    if len(audio_buffer) >= 1600:  # ~100ms at 8kHz mulaw
                        if self.stt_handler:
                            text = await self.stt_handler(bytes(audio_buffer))
                            if text:
                                # Got transcription, process it
                                await self._process_transcription(
                                    websocket, stream_id, call_sid, text
                                )
                        audio_buffer.clear()

                elif event == "mark":
                    # TTS playback completed
                    mark_name = data["mark"]["name"]
                    logger.debug(f"Mark reached: {mark_name}")

                elif event == "stop":
                    logger.info(f"Stream stopped: {stream_id}")
                    break

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for call {call_sid}")

        except Exception as e:
            logger.error(f"Stream error: {e}")

        finally:
            if stream_id and stream_id in self.active_streams:
                del self.active_streams[stream_id]

    async def _process_transcription(
        self,
        websocket: "WebSocket",
        stream_id: str,
        call_sid: str,
        text: str,
    ):
        """Process transcribed text and send response audio"""
        # This would call the conversation engine and get response
        # Then convert to audio and send back
        pass

    async def send_audio(
        self,
        websocket: "WebSocket",
        stream_id: str,
        audio_data: bytes,
        mark: str = None,
    ):
        """Send audio back to the caller"""
        # Twilio expects base64-encoded mulaw audio
        payload = base64.b64encode(audio_data).decode("utf-8")

        message = {
            "event": "media",
            "streamSid": stream_id,
            "media": {
                "payload": payload,
            },
        }
        await websocket.send_text(json.dumps(message))

        # Send mark to know when playback completes
        if mark:
            mark_message = {
                "event": "mark",
                "streamSid": stream_id,
                "mark": {"name": mark},
            }
            await websocket.send_text(json.dumps(mark_message))

    async def clear_audio(self, websocket: "WebSocket", stream_id: str):
        """Clear any pending audio (for barge-in)"""
        message = {
            "event": "clear",
            "streamSid": stream_id,
        }
        await websocket.send_text(json.dumps(message))


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

def create_voice_router(
    voice_handler: TwilioVoiceHandler,
    conversation_engine: Any = None,
) -> "FastAPI":
    """
    Create FastAPI router with all voice endpoints.

    Endpoints:
    - POST /voice/inbound - Initial call webhook
    - POST /voice/process-speech - Speech recognition result
    - POST /voice/status - Call status updates
    - POST /voice/recording-status - Recording callbacks
    - WS /voice/stream - Audio streaming
    """
    if not HAS_FASTAPI:
        raise ImportError("FastAPI not installed")

    from fastapi import APIRouter
    router = APIRouter(prefix="/voice", tags=["voice"])

    @router.post("/inbound")
    async def handle_inbound_call(request: Request):
        """Handle incoming call"""
        form_data = await request.form()
        params = dict(form_data)

        # Validate request
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)

        if not voice_handler.validate_request(url, params, signature):
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Create call context
        call_context = voice_handler.create_call_context(params)
        voice_handler.active_calls[call_context.call_sid] = call_context

        # Start conversation
        if conversation_engine:
            state, greeting = await conversation_engine.start_conversation(
                call_sid=call_context.call_sid,
                caller_phone=call_context.from_number,
                caller_id_name=call_context.caller_name,
            )
        else:
            greeting = "Thank you for calling. How may I help you today?"

        # Generate TwiML
        twiml = voice_handler.generate_greeting_twiml(
            greeting=greeting,
            gather_speech=True,
        )

        return Response(content=twiml, media_type="application/xml")

    @router.post("/process-speech")
    async def process_speech(request: Request):
        """Process speech recognition result"""
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid")
        speech_result = params.get("SpeechResult", "")
        confidence = params.get("Confidence", "0")

        logger.info(f"Speech result for {call_sid}: {speech_result} ({confidence})")

        # Process through conversation engine
        if conversation_engine and speech_result:
            response_text = await conversation_engine.process_input(
                call_sid=call_sid,
                caller_input=speech_result,
            )
        else:
            response_text = "I'm sorry, I didn't catch that. Could you please repeat?"

        # Generate response TwiML
        twiml = voice_handler.generate_response_twiml(
            message=response_text,
            gather_speech=True,
        )

        return Response(content=twiml, media_type="application/xml")

    @router.post("/no-input")
    async def handle_no_input(request: Request):
        """Handle timeout with no speech input"""
        form_data = await request.form()
        call_sid = dict(form_data).get("CallSid")

        twiml = voice_handler.generate_response_twiml(
            message="I'm still here. How can I help you?",
            gather_speech=True,
        )

        return Response(content=twiml, media_type="application/xml")

    @router.post("/status")
    async def call_status_callback(request: Request):
        """Handle call status updates"""
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid")
        status = params.get("CallStatus")

        logger.info(f"Call {call_sid} status: {status}")

        # Update call context
        if call_sid in voice_handler.active_calls:
            context = voice_handler.active_calls[call_sid]
            context.status = CallStatus(status) if status in CallStatus.__members__.values() else context.status

            if status == "in-progress":
                context.answered_at = datetime.now()
            elif status in ["completed", "busy", "failed", "no-answer", "canceled"]:
                context.ended_at = datetime.now()

                # End conversation
                if conversation_engine:
                    await conversation_engine.end_conversation(call_sid, reason=status)

        return PlainTextResponse("OK")

    @router.post("/recording-status")
    async def recording_status_callback(request: Request):
        """Handle recording status updates"""
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid")
        recording_sid = params.get("RecordingSid")
        recording_url = params.get("RecordingUrl")
        recording_status = params.get("RecordingStatus")

        logger.info(f"Recording {recording_sid} for call {call_sid}: {recording_status}")

        # Update call context
        if call_sid in voice_handler.active_calls:
            context = voice_handler.active_calls[call_sid]
            context.recording_sid = recording_sid
            context.recording_url = recording_url

        return PlainTextResponse("OK")

    @router.post("/transfer-complete")
    async def transfer_complete(request: Request):
        """Handle transfer completion"""
        form_data = await request.form()
        params = dict(form_data)

        dial_status = params.get("DialCallStatus")

        if dial_status in ["completed", "answered"]:
            # Transfer successful
            return Response(content="", media_type="application/xml")
        else:
            # Transfer failed, return to receptionist
            twiml = voice_handler.generate_response_twiml(
                message="I'm sorry, I wasn't able to connect that call. Is there something else I can help you with?",
                gather_speech=True,
            )
            return Response(content=twiml, media_type="application/xml")

    @router.post("/voicemail-complete")
    async def voicemail_complete(request: Request):
        """Handle voicemail recording completion"""
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid")
        recording_url = params.get("RecordingUrl")
        recording_duration = params.get("RecordingDuration")

        logger.info(f"Voicemail recorded for {call_sid}: {recording_duration}s")

        # Mark message left in conversation
        if conversation_engine:
            state = conversation_engine.get_conversation_state(call_sid)
            if state:
                state.message_left = True

        twiml = voice_handler.generate_goodbye_twiml(
            "Thank you for your message. Someone will get back to you shortly. Goodbye!"
        )

        return Response(content=twiml, media_type="application/xml")

    @router.websocket("/stream")
    async def audio_stream(websocket: WebSocket):
        """Handle bidirectional audio streaming"""
        await websocket.accept()

        # Get call SID from initial message
        initial = await websocket.receive_text()
        data = json.loads(initial)

        if data.get("event") == "connected":
            call_sid = data.get("start", {}).get("callSid")

            # Create stream handler
            stream_handler = AudioStreamHandler()
            await stream_handler.handle_stream(websocket, call_sid)

    return router


# =============================================================================
# COMPLETE SERVER SETUP
# =============================================================================

def create_voice_server(
    conversation_engine: Any = None,
    twilio_config: TwilioConfig = None,
) -> "FastAPI":
    """
    Create complete FastAPI server with voice endpoints.

    Usage:
        from AI_RECEPTIONIST_PART2_TWILIO import create_voice_server

        app = create_voice_server(conversation_engine=my_engine)

        # Run with: uvicorn module:app --host 0.0.0.0 --port 8000
    """
    if not HAS_FASTAPI:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")

    app = FastAPI(
        title="Perennia AI Receptionist",
        description="AI-powered voice receptionist with Twilio integration",
        version="1.0.0",
    )

    # Create handlers
    config = twilio_config or TwilioConfig()
    voice_handler = TwilioVoiceHandler(
        config=config,
        conversation_handler=conversation_engine,
    )

    # Add voice routes
    router = create_voice_router(voice_handler, conversation_engine)
    app.include_router(router)

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "ai-receptionist"}

    return app


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Example: Create voice handler and generate TwiML
    config = TwilioConfig(
        base_url="https://your-domain.ngrok.io",
    )

    handler = TwilioVoiceHandler(config=config)

    # Generate greeting TwiML
    twiml = handler.generate_greeting_twiml(
        greeting="Thank you for calling Perennia Mortgage. This is Sarah, how may I help you today?",
        gather_speech=True,
    )

    print("Generated TwiML:")
    print(twiml)
