"""
===============================================================================
PERENNIA AI RECEPTIONIST - PART 2: TWILIO VOICE INTEGRATION
===============================================================================
Twilio voice integration for handling phone calls.

Features:
- Inbound call handling with TwiML
- Outbound call initiation
- Call transfer and conferencing
- Voicemail handling
- Call recording management
===============================================================================
"""

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class TwilioConfig:
    """Twilio configuration."""
    account_sid: str
    auth_token: str
    phone_number: str
    webhook_base_url: str
    voice_url: Optional[str] = None
    status_callback_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> "TwilioConfig":
        """Load configuration from environment variables."""
        base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "")

        return cls(
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            phone_number=os.getenv("TWILIO_PHONE_NUMBER", ""),
            webhook_base_url=base_url,
            voice_url=f"{base_url}/voice/inbound",
            status_callback_url=f"{base_url}/voice/status",
        )

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return all([
            self.account_sid,
            self.auth_token,
            self.phone_number,
            self.webhook_base_url,
        ])


# =============================================================================
# TWILIO VOICE CLIENT
# =============================================================================

class TwilioVoiceClient:
    """
    Twilio voice client for handling phone calls.

    Provides methods for:
    - Generating TwiML responses
    - Making outbound calls
    - Transferring calls
    - Recording management
    """

    def __init__(self, config: Optional[TwilioConfig] = None):
        self.config = config or TwilioConfig.from_env()

        if not self.config.is_valid():
            logger.warning("Twilio configuration incomplete - some features may not work")

        # Initialize Twilio client
        self._init_client()

    def _init_client(self):
        """Initialize the Twilio client."""
        try:
            from twilio.rest import Client
            from twilio.twiml.voice_response import VoiceResponse

            if self.config.account_sid and self.config.auth_token:
                self.client = Client(
                    self.config.account_sid,
                    self.config.auth_token
                )
                logger.info("Twilio client initialized")
            else:
                self.client = None
                logger.warning("Twilio client not initialized - missing credentials")

            self.VoiceResponse = VoiceResponse

        except ImportError:
            logger.error("Twilio package not installed. Run: pip install twilio")
            raise

    # =========================================================================
    # TwiML GENERATION
    # =========================================================================

    def create_greeting_response(
        self,
        company_name: str = "Perennia Mortgage",
        gather_speech: bool = True,
    ) -> str:
        """
        Create TwiML for initial greeting.

        Args:
            company_name: Company name for greeting
            gather_speech: Whether to gather speech input

        Returns:
            TwiML string
        """
        response = self.VoiceResponse()

        # Initial greeting
        greeting = f"Thank you for calling {company_name}. My name is Alex, your AI assistant."

        if gather_speech:
            # Gather speech input
            gather = response.gather(
                input="speech",
                action=f"{self.config.webhook_base_url}/voice/process-speech",
                method="POST",
                language="en-US",
                speech_timeout="auto",
                speech_model="phone_call",
            )
            gather.say(
                f"{greeting} How can I help you today?",
                voice="Polly.Joanna",
            )

            # Fallback if no input
            response.say(
                "I didn't catch that. Let me transfer you to a representative.",
                voice="Polly.Joanna",
            )
            response.redirect(f"{self.config.webhook_base_url}/voice/transfer")
        else:
            response.say(greeting, voice="Polly.Joanna")

        return str(response)

    def create_gather_response(
        self,
        prompt: str,
        action_url: Optional[str] = None,
        timeout: int = 5,
    ) -> str:
        """
        Create TwiML to gather speech input.

        Args:
            prompt: Text to speak before gathering
            action_url: URL to send gathered input
            timeout: Speech timeout in seconds

        Returns:
            TwiML string
        """
        response = self.VoiceResponse()

        gather = response.gather(
            input="speech",
            action=action_url or f"{self.config.webhook_base_url}/voice/process-speech",
            method="POST",
            language="en-US",
            speech_timeout=str(timeout),
            speech_model="phone_call",
        )
        gather.say(prompt, voice="Polly.Joanna")

        # Fallback
        response.say("I didn't hear anything.", voice="Polly.Joanna")
        response.redirect(f"{self.config.webhook_base_url}/voice/retry")

        return str(response)

    def create_say_response(
        self,
        text: str,
        gather_after: bool = True,
        end_call: bool = False,
    ) -> str:
        """
        Create TwiML to say something.

        Args:
            text: Text to speak
            gather_after: Whether to gather speech after speaking
            end_call: Whether to end call after speaking

        Returns:
            TwiML string
        """
        response = self.VoiceResponse()

        if gather_after and not end_call:
            gather = response.gather(
                input="speech",
                action=f"{self.config.webhook_base_url}/voice/process-speech",
                method="POST",
                language="en-US",
                speech_timeout="auto",
                speech_model="phone_call",
            )
            gather.say(text, voice="Polly.Joanna")
        else:
            response.say(text, voice="Polly.Joanna")

        if end_call:
            response.hangup()

        return str(response)

    def create_transfer_response(
        self,
        transfer_to: str,
        announcement: Optional[str] = None,
    ) -> str:
        """
        Create TwiML to transfer a call.

        Args:
            transfer_to: Phone number or SIP address to transfer to
            announcement: Optional announcement before transfer

        Returns:
            TwiML string
        """
        response = self.VoiceResponse()

        if announcement:
            response.say(announcement, voice="Polly.Joanna")

        # Dial with options
        dial = response.dial(
            caller_id=self.config.phone_number,
            action=f"{self.config.webhook_base_url}/voice/transfer-complete",
            timeout=30,
        )
        dial.number(
            transfer_to,
            status_callback=f"{self.config.webhook_base_url}/voice/dial-status",
            status_callback_event="initiated ringing answered completed",
        )

        # If transfer fails
        response.say(
            "I'm sorry, the transfer was unsuccessful. Please try again later.",
            voice="Polly.Joanna",
        )
        response.hangup()

        return str(response)

    def create_voicemail_response(
        self,
        greeting: Optional[str] = None,
    ) -> str:
        """
        Create TwiML for voicemail.

        Args:
            greeting: Custom voicemail greeting

        Returns:
            TwiML string
        """
        response = self.VoiceResponse()

        default_greeting = (
            "I'm sorry, all of our representatives are currently busy. "
            "Please leave a message after the beep and we'll get back to you as soon as possible."
        )

        response.say(greeting or default_greeting, voice="Polly.Joanna")

        response.record(
            action=f"{self.config.webhook_base_url}/voice/voicemail-complete",
            max_length=120,
            transcribe=True,
            transcribe_callback=f"{self.config.webhook_base_url}/voice/transcription",
            play_beep=True,
        )

        response.say("We didn't receive your message. Goodbye.", voice="Polly.Joanna")
        response.hangup()

        return str(response)

    def create_hold_response(
        self,
        message: Optional[str] = None,
        music_url: Optional[str] = None,
        timeout: int = 60,
    ) -> str:
        """
        Create TwiML for hold.

        Args:
            message: Hold message
            music_url: URL to hold music
            timeout: Maximum hold time in seconds

        Returns:
            TwiML string
        """
        response = self.VoiceResponse()

        if message:
            response.say(message, voice="Polly.Joanna")

        if music_url:
            response.play(music_url, loop=0)
        else:
            # Default hold music
            response.play(
                "https://api.twilio.com/cowbell.mp3",
                loop=10
            )

        response.redirect(f"{self.config.webhook_base_url}/voice/hold-timeout")

        return str(response)

    def create_stream_response(
        self,
        stream_url: str,
    ) -> str:
        """
        Create TwiML for bidirectional audio streaming.

        Args:
            stream_url: WebSocket URL for streaming

        Returns:
            TwiML string
        """
        response = self.VoiceResponse()

        response.say(
            "Connecting you now. Please wait.",
            voice="Polly.Joanna"
        )

        # Start bidirectional stream
        connect = response.connect()
        connect.stream(
            url=stream_url,
            track="both_tracks",
        )

        return str(response)

    # =========================================================================
    # OUTBOUND CALLS
    # =========================================================================

    def make_call(
        self,
        to: str,
        twiml_url: Optional[str] = None,
        twiml: Optional[str] = None,
        status_callback: Optional[str] = None,
        record: bool = False,
    ) -> Dict[str, Any]:
        """
        Make an outbound call.

        Args:
            to: Phone number to call
            twiml_url: URL returning TwiML
            twiml: Inline TwiML
            status_callback: URL for status updates
            record: Whether to record the call

        Returns:
            Call details
        """
        if not self.client:
            return {"error": "Twilio client not initialized"}

        try:
            call_params = {
                "to": to,
                "from_": self.config.phone_number,
                "status_callback": status_callback or self.config.status_callback_url,
                "status_callback_event": ["initiated", "ringing", "answered", "completed"],
                "status_callback_method": "POST",
                "record": record,
            }

            if twiml:
                call_params["twiml"] = twiml
            elif twiml_url:
                call_params["url"] = twiml_url
            else:
                call_params["url"] = f"{self.config.webhook_base_url}/voice/outbound-script"

            call = self.client.calls.create(**call_params)

            logger.info(f"Initiated call {call.sid} to {to}")

            return {
                "call_sid": call.sid,
                "to": to,
                "from": self.config.phone_number,
                "status": call.status,
            }

        except Exception as e:
            logger.error(f"Failed to make call: {e}")
            return {"error": str(e)}

    def get_call(self, call_sid: str) -> Dict[str, Any]:
        """Get call details."""
        if not self.client:
            return {"error": "Twilio client not initialized"}

        try:
            call = self.client.calls(call_sid).fetch()
            return {
                "call_sid": call.sid,
                "to": call.to,
                "from": call.from_,
                "status": call.status,
                "direction": call.direction,
                "duration": call.duration,
                "start_time": str(call.start_time) if call.start_time else None,
                "end_time": str(call.end_time) if call.end_time else None,
            }
        except Exception as e:
            logger.error(f"Failed to get call {call_sid}: {e}")
            return {"error": str(e)}

    def update_call(
        self,
        call_sid: str,
        twiml: Optional[str] = None,
        twiml_url: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an in-progress call.

        Args:
            call_sid: Call SID
            twiml: New TwiML to execute
            twiml_url: URL returning new TwiML
            status: New status (completed to hang up)

        Returns:
            Updated call details
        """
        if not self.client:
            return {"error": "Twilio client not initialized"}

        try:
            update_params = {}

            if twiml:
                update_params["twiml"] = twiml
            elif twiml_url:
                update_params["url"] = twiml_url

            if status:
                update_params["status"] = status

            call = self.client.calls(call_sid).update(**update_params)

            return {
                "call_sid": call.sid,
                "status": call.status,
            }

        except Exception as e:
            logger.error(f"Failed to update call {call_sid}: {e}")
            return {"error": str(e)}

    def end_call(self, call_sid: str) -> Dict[str, Any]:
        """End an in-progress call."""
        return self.update_call(call_sid, status="completed")

    # =========================================================================
    # RECORDINGS
    # =========================================================================

    def get_recordings(
        self,
        call_sid: Optional[str] = None,
        limit: int = 20,
    ) -> list:
        """Get call recordings."""
        if not self.client:
            return []

        try:
            params = {"limit": limit}
            if call_sid:
                params["call_sid"] = call_sid

            recordings = self.client.recordings.list(**params)

            return [
                {
                    "recording_sid": r.sid,
                    "call_sid": r.call_sid,
                    "duration": r.duration,
                    "status": r.status,
                    "url": f"https://api.twilio.com{r.uri.replace('.json', '.mp3')}",
                }
                for r in recordings
            ]

        except Exception as e:
            logger.error(f"Failed to get recordings: {e}")
            return []

    def delete_recording(self, recording_sid: str) -> bool:
        """Delete a recording."""
        if not self.client:
            return False

        try:
            self.client.recordings(recording_sid).delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete recording {recording_sid}: {e}")
            return False


# =============================================================================
# AI VOICE CONFIG
# =============================================================================

@dataclass
class AIVoiceConfig:
    """AI voice configuration."""
    business_name: str = "Perennia Mortgage"
    ai_name: str = "Alex"
    voice: str = "Polly.Joanna"  # AWS Polly voice
    language: str = "en-US"
    speech_timeout: int = 5
    max_call_duration: int = 600  # 10 minutes

    @classmethod
    def from_env(cls) -> "AIVoiceConfig":
        """Load from environment."""
        return cls(
            business_name=os.getenv("BUSINESS_NAME", "Perennia Mortgage"),
            ai_name=os.getenv("AI_NAME", "Alex"),
            voice=os.getenv("AI_VOICE", "Polly.Joanna"),
        )


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

# Global instances
_voice_client: Optional[TwilioVoiceClient] = None
_ai_config: Optional[AIVoiceConfig] = None


def get_voice_client() -> TwilioVoiceClient:
    """Get or create the Twilio voice client."""
    global _voice_client
    if _voice_client is None:
        _voice_client = TwilioVoiceClient()
    return _voice_client


def get_ai_config() -> AIVoiceConfig:
    """Get or create the AI config."""
    global _ai_config
    if _ai_config is None:
        _ai_config = AIVoiceConfig.from_env()
    return _ai_config


# Convenience aliases
voice_client = property(lambda self: get_voice_client())
ai_config = property(lambda self: get_ai_config())
