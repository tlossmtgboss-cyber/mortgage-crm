"""
Provider-Agnostic Click-to-Call Service

Implements whisper+bridge calling for the chat state machine.
Uses Telnyx as the telephony provider.

PRODUCTION FLOW:
1. User clicks "Call Now" in chat (frontend shows "Calling your phone...")
2. System calls the BORROWER first
3. Borrower hears greeting + DTMF prompt
4. If borrower presses 1: Put in conference with hold music, trigger LO call
5. LO hears whisper context, presses 1 to connect
6. Both parties bridged and talking
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Determine which provider to use
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "telnyx").lower()

# Configuration
BASE_URL = os.getenv("BASE_URL", "https://app.perenniaai.com")
DEFAULT_LO_NAME = os.getenv("DEFAULT_LO_NAME", "Tim")


def get_telephony_client():
    """Get the Telnyx telephony client"""
    return _get_telnyx_client()


def _get_telnyx_client():
    """Get Telnyx client if credentials are configured"""
    api_key = os.getenv("TELNYX_API_KEY")
    if not api_key:
        logger.warning("Telnyx credentials not configured")
        return None
    try:
        from telnyx import Telnyx
        return Telnyx(api_key=api_key)
    except ImportError:
        logger.warning("Telnyx SDK not installed")
        return None


def get_from_number() -> Optional[str]:
    """Get the caller ID phone number for Telnyx"""
    return os.getenv("TELNYX_PHONE_NUMBER")


class VoiceResponseBuilder:
    """
    Provider-agnostic voice response builder.

    Generates TeXML responses for Telnyx.
    """

    def __init__(self):
        self._response = None
        self._current_gather = None

        from telephony.providers.telnyx.texml import TeXMLResponse
        self._response = TeXMLResponse()

    def say(self, text: str, voice: str = "Polly.Joanna") -> "VoiceResponseBuilder":
        """Add speech to response"""
        self._response.say(text, voice=voice)
        return self

    def gather(
        self,
        num_digits: int = 1,
        action: str = None,
        timeout: int = 10,
        input_type: str = "dtmf"
    ) -> "VoiceResponseBuilder":
        """Start a gather for DTMF input"""
        self._current_gather = self._response.gather(
            input_type=input_type,
            action=action,
            num_digits=num_digits,
            timeout=timeout
        )
        return self

    def gather_say(self, text: str, voice: str = "Polly.Joanna") -> "VoiceResponseBuilder":
        """Add speech inside current gather"""
        if self._current_gather:
            self._current_gather.say(text, voice=voice)
        return self

    def end_gather(self) -> "VoiceResponseBuilder":
        """End the current gather context"""
        if hasattr(self._current_gather, 'end_gather'):
            self._current_gather.end_gather()
        self._current_gather = None
        return self

    def dial_conference(
        self,
        name: str,
        start_on_enter: bool = True,
        end_on_exit: bool = True,
        wait_url: str = None,
        record: str = None,
        status_callback: str = None
    ) -> "VoiceResponseBuilder":
        """Dial into a conference"""
        self._response.conference(
            name=name,
            start_conference_on_enter=start_on_enter,
            end_conference_on_exit=end_on_exit,
            wait_url=wait_url,
            record=record,
            status_callback=status_callback
        )
        return self

    def redirect(self, url: str) -> "VoiceResponseBuilder":
        """Redirect to another URL"""
        self._response.redirect(url)
        return self

    def hangup(self) -> "VoiceResponseBuilder":
        """Hang up the call"""
        self._response.hangup()
        return self

    def to_xml(self) -> str:
        """Generate the XML response"""
        return self._response.to_xml()


class ClickToCallService:
    """
    Provider-agnostic click-to-call service.

    Manages click-to-call functionality with whisper+bridge.
    Uses Telnyx as the telephony provider.
    """

    def __init__(self, db: Session):
        self.db = db
        self.client = get_telephony_client()
        self.provider = TELEPHONY_PROVIDER
        self.from_number = get_from_number()

    def initiate_call(self, call_request_id: UUID) -> Dict[str, Any]:
        """
        Initiate click-to-call for a call request.
        """
        from chat_state_machine_models import CallRequest, CallStatus

        if not self.client:
            return {
                "success": False,
                "error": f"{self.provider.capitalize()} not configured",
                "status": CallStatus.FAILED.value
            }

        # Get call request
        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            return {
                "success": False,
                "error": "Call request not found",
                "status": CallStatus.FAILED.value
            }

        # Get LO phone number
        lo_phone = self._get_lo_phone(call_request.loan_officer_id)
        if not lo_phone:
            return {
                "success": False,
                "error": "Loan officer phone not configured",
                "status": CallStatus.FAILED.value
            }

        # Update status to connecting
        call_request.status = CallStatus.CONNECTING.value
        call_request.initiated_at = datetime.now(timezone.utc)
        self.db.commit()

        try:
            # Call the borrower first via Telnyx
            call_sid = self._initiate_telnyx_call(
                call_request.caller_phone,
                call_request_id
            )

            call_request.twilio_call_sid = call_sid  # Legacy column name — stores Telnyx call control ID
            self.db.commit()

            logger.info(f"Initiated call to borrower: {call_sid} via {self.provider}")

            return {
                "success": True,
                "call_sid": call_sid,
                "status": CallStatus.CONNECTING.value,
                "provider": self.provider,
                "message": "Calling your phone now..."
            }

        except Exception as e:
            logger.error(f"Failed to initiate call: {e}")
            call_request.status = CallStatus.FAILED.value
            self.db.commit()

            return {
                "success": False,
                "error": "Internal server error",
                "status": CallStatus.FAILED.value
            }

    def _initiate_telnyx_call(self, to_phone: str, call_request_id: UUID) -> str:
        """Initiate call via Telnyx"""
        connection_id = os.getenv("TELNYX_CONNECTION_ID")

        call = self.client.calls.create(
            connection_id=connection_id,
            to=to_phone,
            from_=self.from_number,
            webhook_url=f"{BASE_URL}/api/v1/telnyx/borrower-answered/{call_request_id}",
            webhook_url_method="POST",
            timeout_secs=30,
        )
        return call.data.call_control_id

    def generate_borrower_twiml(self, call_request_id: UUID) -> str:
        """Generate TeXML for when borrower answers."""
        from chat_state_machine_models import CallRequest

        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            response = VoiceResponseBuilder()
            response.say("Sorry, we couldn't connect your call. Please try again.")
            return response.to_xml()

        lo_name = self._get_lo_name(call_request.loan_officer_id) or DEFAULT_LO_NAME
        borrower_name = call_request.caller_name or "there"

        response = VoiceResponseBuilder()

        greeting = (
            f"Hi {borrower_name}! {lo_name} from Perennia Mortgage is ready "
            f"to speak with you about your mortgage options."
        )

        response.gather(
            num_digits=1,
            action=f"{BASE_URL}/api/v1/telnyx/borrower-response/{call_request_id}",
            timeout=10
        )
        response.gather_say(greeting)
        response.gather_say("Press 1 to connect now, or press 2 to schedule for a better time.")
        response.end_gather()

        response.say("I didn't catch that.")
        response.redirect(
            f"{BASE_URL}/api/v1/telnyx/borrower-answered/{call_request_id}"
        )

        return response.to_xml()

    def generate_borrower_response_twiml(self, call_request_id: UUID, digits: str) -> str:
        """Handle borrower's DTMF response."""
        from chat_state_machine_models import CallRequest, CallStatus

        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            response = VoiceResponseBuilder()
            response.say("Sorry, there was an error.")
            return response.to_xml()

        conference_name = f"chat_call_{call_request_id}"
        response = VoiceResponseBuilder()

        if digits == "1":
            response.say("Great! Please hold while we connect you. This will just take a moment.")

            response.dial_conference(
                name=conference_name,
                start_on_enter=False,
                end_on_exit=True,
                status_callback=f"{BASE_URL}/api/v1/telnyx/conference-status/{call_request_id}"
            )

            # Trigger call to LO
            self._trigger_lo_call(call_request)

        elif digits == "2":
            response.say(
                "No problem! You can schedule a call at a time that works better for you "
                "through our chat. We look forward to speaking with you soon. Goodbye!"
            )
            response.hangup()

            call_request.status = CallStatus.CANCELLED.value
            call_request.outcome = "borrower_requested_schedule"
            call_request.ended_at = datetime.now(timezone.utc)
            self.db.commit()

        else:
            response.say("Sorry, I didn't understand that.")
            response.redirect(
                f"{BASE_URL}/api/v1/telnyx/borrower-answered/{call_request_id}"
            )

        return response.to_xml()

    def _trigger_lo_call(self, call_request):
        """Trigger call to loan officer."""
        from chat_state_machine_models import CallRequest

        if not self.client:
            logger.error("Telephony client not configured")
            return

        lo_phone = self._get_lo_phone(call_request.loan_officer_id)
        if not lo_phone:
            logger.error(f"No phone for LO {call_request.loan_officer_id}")
            self._notify_borrower_lo_unavailable(call_request, "no_phone")
            return

        try:
            connection_id = os.getenv("TELNYX_CONNECTION_ID")
            lo_call = self.client.calls.create(
                connection_id=connection_id,
                to=lo_phone,
                from_=self.from_number,
                webhook_url=f"{BASE_URL}/api/v1/telnyx/lo-answered/{call_request.id}",
                webhook_url_method="POST",
                timeout_secs=30,
            )
            logger.info(f"Calling LO via Telnyx: {lo_call.data.call_control_id}")

        except Exception as e:
            logger.error(f"Failed to call LO: {e}")
            self._notify_borrower_lo_unavailable(call_request, "call_failed")

    def generate_lo_twiml(self, call_request_id: UUID) -> str:
        """Generate TeXML for when LO answers."""
        from chat_state_machine_models import CallRequest

        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            response = VoiceResponseBuilder()
            response.say("Sorry, there was an error.", voice="Polly.Matthew")
            return response.to_xml()

        response = VoiceResponseBuilder()
        whisper = self._build_enhanced_whisper(call_request)

        response.gather(
            num_digits=1,
            action=f"{BASE_URL}/api/v1/telnyx/lo-response/{call_request_id}",
            timeout=15
        )
        response.gather_say(whisper, voice="Polly.Matthew")
        response.gather_say("Press 1 to connect now.", voice="Polly.Matthew")
        response.end_gather()

        response.say("The caller is waiting. Press 1 to connect.", voice="Polly.Matthew")
        response.redirect(
            f"{BASE_URL}/api/v1/telnyx/lo-answered/{call_request_id}"
        )

        return response.to_xml()

    def _build_enhanced_whisper(self, call_request) -> str:
        """Build a rich whisper message with conversation context."""
        parts = []

        caller_name = call_request.caller_name or "A website visitor"
        parts.append(f"Incoming call from {caller_name}.")

        if call_request.intent_summary:
            parts.append(call_request.intent_summary)
        else:
            signals = call_request.intent_signals_snapshot or []
            signal_map = {s.get('signal'): s.get('value') for s in signals if s.get('signal')}

            if 'goal' in signal_map:
                parts.append(f"Interested in {signal_map['goal']}.")
            if 'price' in signal_map:
                parts.append(f"Budget around {signal_map['price']}.")
            if 'timeline' in signal_map:
                parts.append(f"Timeline: {signal_map['timeline']}.")

        session = call_request.session
        if session:
            parts.append(f"Intent score: {session.intent_score} out of 100.")
            if session.urgency == 'high':
                parts.append("High urgency detected.")

        return " ".join(parts) if parts else "Incoming call from website visitor."

    def generate_lo_response_twiml(self, call_request_id: UUID, digits: str) -> str:
        """Handle LO's response to whisper prompt."""
        from chat_state_machine_models import CallRequest, CallStatus

        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            response = VoiceResponseBuilder()
            response.say("Sorry, there was an error.", voice="Polly.Matthew")
            return response.to_xml()

        conference_name = f"chat_call_{call_request_id}"
        response = VoiceResponseBuilder()

        if digits == "1":
            response.say("Connecting you now.", voice="Polly.Matthew")

            response.dial_conference(
                name=conference_name,
                start_on_enter=True,
                end_on_exit=True,
                record="record-from-start"
            )

            call_request.status = CallStatus.IN_PROGRESS.value
            call_request.connected_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(f"LO connected to call {call_request_id}")

        else:
            response.say(
                "Call declined. The caller will be offered scheduling options.",
                voice="Polly.Matthew"
            )
            response.hangup()

            call_request.status = CallStatus.CANCELLED.value
            call_request.outcome = "lo_declined"
            call_request.ended_at = datetime.now(timezone.utc)
            self.db.commit()

            self._notify_borrower_lo_unavailable(call_request, "declined")
            logger.info(f"LO declined call {call_request_id}")

        return response.to_xml()

    def handle_call_status(
        self,
        call_request_id: UUID,
        call_status: str,
        call_duration: Optional[int] = None,
    ):
        """Handle call status callback from Telnyx"""
        from chat_state_machine_models import CallRequest, CallStatus

        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            return

        # Map status strings from Telnyx
        status_mapping = {
            "completed": CallStatus.COMPLETED.value,
            "busy": CallStatus.NO_ANSWER.value,
            "no-answer": CallStatus.NO_ANSWER.value,
            "failed": CallStatus.FAILED.value,
            "canceled": CallStatus.CANCELLED.value,
            # Telnyx statuses
            "hangup": CallStatus.COMPLETED.value,
            "call_rejected": CallStatus.NO_ANSWER.value,
            "timeout": CallStatus.NO_ANSWER.value,
        }

        if call_status in status_mapping:
            call_request.status = status_mapping[call_status]
            call_request.ended_at = datetime.now(timezone.utc)

            if call_duration:
                call_request.call_duration_seconds = call_duration

        self.db.commit()

    def _get_lo_phone(self, loan_officer_id: Optional[int]) -> Optional[str]:
        """Get loan officer's phone number"""
        if not loan_officer_id:
            return None

        result = self.db.execute(text("""
            SELECT phone FROM users WHERE id = :lo_id
        """), {"lo_id": loan_officer_id}).first()

        return result.phone if result else None

    def _get_lo_name(self, loan_officer_id: Optional[int]) -> Optional[str]:
        """Get loan officer's name for personalization"""
        if not loan_officer_id:
            return None

        result = self.db.execute(text("""
            SELECT full_name FROM users WHERE id = :lo_id
        """), {"lo_id": loan_officer_id}).first()

        if result and result.full_name:
            return result.full_name.split()[0]  # Return first name
        return None

    def _notify_borrower_lo_unavailable(self, call_request, reason: str):
        """Send SMS notification to borrower when LO is unavailable."""
        try:
            from integrations.sms_service import get_sms_client

            borrower_phone = call_request.caller_phone
            borrower_name = call_request.caller_name or "there"
            lo_name = self._get_lo_name(call_request.loan_officer_id) or DEFAULT_LO_NAME

            if not borrower_phone:
                logger.warning(f"No phone to notify borrower for call {call_request.id}")
                return

            first_name = borrower_name.split()[0] if borrower_name != "there" else "there"

            if reason == "declined":
                message = (
                    f"Hi {first_name}, {lo_name} is currently with another client. "
                    f"We'll reach out shortly to schedule a convenient time to talk."
                )
            elif reason == "call_failed":
                message = (
                    f"Hi {first_name}, we couldn't complete your call with {lo_name}. "
                    f"We'll contact you shortly to schedule a callback."
                )
            else:
                message = (
                    f"Hi {first_name}, {lo_name} is temporarily unavailable. "
                    f"We'll reach out soon to schedule a time that works for you."
                )

            sms_client = get_sms_client()
            sms_client.send_sms(borrower_phone, message)

            logger.info(f"Sent unavailability SMS to {borrower_phone}")

        except Exception as e:
            logger.error(f"Failed to send unavailability SMS: {e}")
