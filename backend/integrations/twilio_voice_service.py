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
        Connects directly to Sam (OpenAI Realtime API) - Sam will greet the caller
        """
        response = VoiceResponse()

        # Connect directly to Sam via OpenAI Realtime API
        # Sam will greet the caller with his AI voice
        domain = os.getenv('PRODUCTION_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN', 'localhost')
        logger.info(f"Connecting to WebSocket at: wss://{domain}/api/v1/voice/ws/voice-stream")

        connect = response.connect()
        stream = connect.stream(
            url=f"wss://{domain}/api/v1/voice/ws/voice-stream"
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

        # AI personality and instructions - optimized for natural voice conversation
        self.system_prompt = """You are Sam, a warm and knowledgeable mortgage assistant at {business_name}.

## VOICE CONVERSATION STYLE
- Speak naturally like a real person on the phone - use contractions, casual phrasing
- Keep responses SHORT (1-3 sentences max) - this is a phone call, not an email
- Use verbal acknowledgments: "Got it", "Sure thing", "Absolutely", "I hear you"
- Pause naturally with phrases like "Let me think..." or "One moment..."
- If interrupted, stop immediately and listen - don't talk over the caller
- Match the caller's energy - if they're excited, be enthusiastic; if concerned, be reassuring

## CONVERSATION FLOW
1. After greeting, ask ONE question at a time - never multiple questions
2. Listen for their answer, acknowledge it, then ask the next relevant question
3. If they go off-topic, gently guide back: "That's a great point. Just to make sure I can help you best..."
4. Summarize what you've learned before transferring or ending: "So just to confirm..."

## LEAD QUALIFICATION (ask naturally, not like a checklist)
- "What brings you in today - looking to buy, refinance, or something else?"
- "Do you have a property in mind, or still looking?"
- "What's your ideal timeline for this?"
- "And what name should I put this under?"

## WHAT YOU CAN HELP WITH
- Current rate ranges (general, not specific quotes)
- Loan process overview and timeline
- Document requirements
- Scheduling appointments with loan officers
- Taking messages and arranging callbacks

## WHEN TO TRANSFER TO A HUMAN
- Caller explicitly asks for a person
- Complex financial situations you can't address
- Complaints or frustrated callers
- Existing clients with account-specific questions

## BOUNDARIES
- Don't quote specific rates or guarantee approvals
- Don't give tax or legal advice
- If unsure, say "Let me connect you with a loan officer who can give you the exact details"

Remember: You're having a PHONE CONVERSATION. Be human, be helpful, be brief.
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
