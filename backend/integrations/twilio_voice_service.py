"""
Twilio Voice Integration with OpenAI Realtime API
Handles AI receptionist calls: answer, make calls, transfer
"""
import os
import logging
import json
from typing import Optional, Dict, List
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial
import openai

logger = logging.getLogger(__name__)


class TwilioVoiceClient:
    """Twilio Voice client for AI receptionist"""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")

        # Check if we have credentials
        has_credentials = self.account_sid and self.auth_token and self.from_number

        if has_credentials:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                logger.info("Twilio Voice initialized successfully")
                self.enabled = True
            except Exception as e:
                self.client = None
                self.enabled = False
                logger.error(f"Failed to initialize Twilio Voice: {e}")
        else:
            self.client = None
            self.enabled = False
            logger.warning("Twilio Voice credentials not configured")

        # Initialize OpenAI if available
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
            self.openai_enabled = True
        else:
            self.openai_enabled = False
            logger.warning("OpenAI API key not configured")

    def create_greeting_response(self, business_name: str = "our office") -> VoiceResponse:
        """
        Create initial greeting TwiML response
        This connects to OpenAI Realtime API for AI conversation
        """
        response = VoiceResponse()

        # Start with a greeting
        response.say(
            f"Thank you for calling {business_name}. Please wait while I connect you to our AI assistant.",
            voice='Polly.Joanna'
        )

        # Connect to OpenAI Realtime API via WebSocket
        # This uses Twilio Media Streams to pipe audio to OpenAI
        # Use PRODUCTION_DOMAIN if available, fallback to RAILWAY_PUBLIC_DOMAIN
        domain = os.getenv('PRODUCTION_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN', 'localhost')
        connect = response.connect()
        connect.stream(
            url=f"wss://{domain}/api/v1/voice/ws/voice-stream",
            track='both_tracks'
        )

        return response

    def create_voicemail_response(self) -> VoiceResponse:
        """Create voicemail TwiML response"""
        response = VoiceResponse()

        response.say(
            "Please leave a message after the beep. Press the star key when finished.",
            voice='Polly.Joanna'
        )

        response.record(
            max_length=120,
            finish_on_key='*',
            transcribe=True,
            transcribe_callback='/api/v1/voice/voicemail-transcription'
        )

        response.say("Thank you for your message. We'll call you back soon.", voice='Polly.Joanna')

        return response

    def create_transfer_response(self, to_number: str, caller_name: str = "a caller") -> VoiceResponse:
        """Create call transfer TwiML response"""
        response = VoiceResponse()

        response.say(
            f"Transferring you to a team member now. Please hold.",
            voice='Polly.Joanna'
        )

        dial = Dial(
            caller_id=self.from_number,
            timeout=30,
            action='/api/v1/voice/transfer-status'
        )
        dial.number(to_number)
        response.append(dial)

        # If transfer fails
        response.say(
            "Sorry, we couldn't reach that person. Let me take a message for you.",
            voice='Polly.Joanna'
        )
        response.redirect('/api/v1/voice/voicemail')

        return response

    async def make_outbound_call(
        self,
        to_number: str,
        script: Optional[str] = None,
        callback_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Make an outbound AI call
        Returns call SID if successful
        """
        if not self.enabled:
            logger.warning("Twilio Voice not enabled, cannot make call")
            return None

        try:
            # Ensure phone number is in E.164 format
            if not to_number.startswith("+"):
                to_number = f"+1{to_number}"

            # Create TwiML for the call
            twiml_url = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/api/v1/voice/outbound-script"
            if callback_url:
                twiml_url += f"?callback={callback_url}"
            if script:
                twiml_url += f"&script_id={script}"

            call = self.client.calls.create(
                to=to_number,
                from_=self.from_number,
                url=twiml_url,
                status_callback=callback_url or f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/api/v1/voice/call-status",
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                record=True,
                recording_status_callback=f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/api/v1/voice/recording-ready"
            )

            logger.info(f"Outbound call initiated. SID: {call.sid}")
            return call.sid

        except TwilioRestException as e:
            logger.error(f"Twilio error making call: {e}")
            return None
        except Exception as e:
            logger.error(f"Error making call: {e}")
            return None

    async def get_call_status(self, call_sid: str) -> Optional[Dict]:
        """Get status of a call"""
        if not self.enabled:
            return None

        try:
            call = self.client.calls(call_sid).fetch()

            return {
                "sid": call.sid,
                "status": call.status,
                "to": call.to,
                "from": call.from_,
                "duration": call.duration,
                "start_time": call.start_time,
                "end_time": call.end_time,
                "direction": call.direction,
                "price": call.price,
                "answered_by": call.answered_by
            }

        except TwilioRestException as e:
            logger.error(f"Error fetching call status: {e}")
            return None

    async def get_call_recording(self, recording_sid: str) -> Optional[str]:
        """Get URL for call recording"""
        if not self.enabled:
            return None

        try:
            recording = self.client.recordings(recording_sid).fetch()
            base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}"
            return f"{base_url}/Recordings/{recording.sid}.mp3"

        except TwilioRestException as e:
            logger.error(f"Error fetching recording: {e}")
            return None

    async def get_call_transcription(self, transcription_sid: str) -> Optional[str]:
        """Get transcription text"""
        if not self.enabled:
            return None

        try:
            transcription = self.client.transcriptions(transcription_sid).fetch()
            return transcription.transcription_text

        except TwilioRestException as e:
            logger.error(f"Error fetching transcription: {e}")
            return None

    async def transfer_call(
        self,
        call_sid: str,
        to_number: str,
        reason: Optional[str] = None
    ) -> bool:
        """Transfer an active call to another number"""
        if not self.enabled:
            return False

        try:
            # Update the call with new TwiML that transfers it
            transfer_url = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/api/v1/voice/transfer?to={to_number}"
            if reason:
                transfer_url += f"&reason={reason}"

            call = self.client.calls(call_sid).update(url=transfer_url)

            logger.info(f"Call {call_sid} transferred to {to_number}")
            return True

        except TwilioRestException as e:
            logger.error(f"Error transferring call: {e}")
            return False

    async def hangup_call(self, call_sid: str) -> bool:
        """Hang up an active call"""
        if not self.enabled:
            return False

        try:
            self.client.calls(call_sid).update(status='completed')
            logger.info(f"Call {call_sid} hung up")
            return True

        except TwilioRestException as e:
            logger.error(f"Error hanging up call: {e}")
            return False


class AIReceptionistConfig:
    """Configuration for AI receptionist behavior"""

    def __init__(self):
        self.business_name = os.getenv("BUSINESS_NAME", "CMG Home Loans")
        self.business_hours = {
            "start": "09:00",
            "end": "17:00",
            "timezone": "America/Los_Angeles"
        }

        # AI personality and instructions
        self.system_prompt = """You are a friendly and professional AI receptionist for {business_name}, a mortgage lending company.

Your responsibilities:
1. Greet callers warmly and ask how you can help
2. Qualify leads by asking about:
   - Type of loan they're interested in (purchase, refinance, cash-out)
   - Property type and estimated value
   - Employment status and income level
   - Credit score range (if comfortable sharing)
   - Timeline/urgency
3. Schedule appointments with loan officers
4. Answer common questions about:
   - Current mortgage rates
   - Required documents
   - Loan process timeline
   - Types of loan programs offered
5. Transfer to a human for:
   - Urgent matters
   - Specific loan officer requests
   - Complex situations you can't handle
6. Take detailed messages when team members are unavailable

Tone: Professional but friendly, patient, empathetic
Always: Get caller's name and phone number early in the conversation
Never: Make promises about rates or approval without human verification
"""

        # Call routing rules
        self.routing_rules = {
            "hot_lead": {
                "priority": "high",
                "transfer_to": os.getenv("LOAN_OFFICER_PHONE"),
                "criteria": ["purchase", "refinance", "ready_now", "good_credit"]
            },
            "appointment": {
                "action": "schedule",
                "available_slots": True
            },
            "general_inquiry": {
                "action": "answer_questions",
                "escalate_if": ["angry", "confused", "requests_human"]
            }
        }


# Global instances
voice_client = TwilioVoiceClient()
ai_config = AIReceptionistConfig()
