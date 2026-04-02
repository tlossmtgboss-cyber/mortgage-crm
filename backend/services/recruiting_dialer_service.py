"""
Provider-Agnostic Recruiting Dialer Service

Integrates telephony calling for the recruiting platform.
Uses Telnyx as the telephony provider.

FLOW:
1. Recruiter clicks "Call" on candidate
2. System calls RECRUITER first (so they're ready)
3. Recruiter hears whisper context + Press 1 to connect
4. Recruiter presses 1 → System dials candidate
5. Candidate answers → Both connected
6. Call recorded for training/compliance
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Determine which provider to use
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "telnyx").lower()
BASE_URL = os.getenv("BASE_URL", "https://app.perenniaai.com")


@dataclass
class RecruitingCallResult:
    """Result of initiating a recruiting call"""
    success: bool
    call_id: Optional[str] = None
    call_sid: Optional[str] = None
    status: str = "initiated"
    message: str = ""
    error: Optional[str] = None
    provider: str = TELEPHONY_PROVIDER


def get_telephony_client():
    """Get the appropriate telephony client based on provider"""
    if TELEPHONY_PROVIDER == "telnyx":
        api_key = os.getenv("TELNYX_API_KEY")
        if not api_key:
            return None
        try:
            from telnyx import Telnyx
            return Telnyx(api_key=api_key)
        except ImportError:
            return None
    else:
        logger.warning("TELEPHONY_PROVIDER is not 'telnyx' — only Telnyx is supported, returning None")
        return None


def get_from_number() -> Optional[str]:
    """Get the caller ID phone number for the current provider"""
    if TELEPHONY_PROVIDER == "telnyx":
        return os.getenv("TELNYX_PHONE_NUMBER")
    else:
        return os.getenv("TELNYX_PHONE_NUMBER")


class VoiceResponseBuilder:
    """Provider-agnostic voice response builder for TwiML/TeXML"""

    def __init__(self):
        self._response = None
        self._current_gather = None
        self._current_dial = None

        from telephony.providers.telnyx.texml import TeXMLResponse
        self._response = TeXMLResponse()

    def say(self, text: str, voice: str = "Polly.Matthew") -> "VoiceResponseBuilder":
        self._response.say(text, voice=voice)
        return self

    def gather(self, num_digits: int = 1, action: str = None, timeout: int = 10) -> "VoiceResponseBuilder":
        self._current_gather = self._response.gather(
            input_type="dtmf",
            action=action,
            num_digits=num_digits,
            timeout=timeout
        )
        return self

    def gather_say(self, text: str, voice: str = "Polly.Matthew") -> "VoiceResponseBuilder":
        if self._current_gather:
            self._current_gather.say(text, voice=voice)
        return self

    def end_gather(self) -> "VoiceResponseBuilder":
        if hasattr(self._current_gather, 'end_gather'):
            self._current_gather.end_gather()
        self._current_gather = None
        return self

    def dial(
        self,
        number: str,
        caller_id: str = None,
        timeout: int = 30,
        record: str = None,
        action: str = None,
        recording_callback: str = None,
        status_callback: str = None,
    ) -> "VoiceResponseBuilder":
        dial_ctx = self._response.dial(
            caller_id=caller_id,
            timeout=timeout,
            record=record,
            action=action,
            recording_status_callback=recording_callback
        )
        dial_ctx.number(number, status_callback=status_callback)
        dial_ctx.end_dial()
        return self

    def redirect(self, url: str) -> "VoiceResponseBuilder":
        self._response.redirect(url)
        return self

    def hangup(self) -> "VoiceResponseBuilder":
        self._response.hangup()
        return self

    def to_xml(self) -> str:
        return self._response.to_xml()


class RecruitingDialerService:
    """
    Provider-agnostic recruiting dialer service.

    Uses a "recruiter-first" model where we call the recruiter,
    play context whisper, then connect to candidate on confirmation.
    """

    def __init__(self, db_session, organization_id: Optional[int] = None):
        self.db = db_session
        self.client = get_telephony_client()
        self.provider = TELEPHONY_PROVIDER
        self.from_number = get_from_number()
        self.organization_id = organization_id

    def initiate_call(
        self,
        call_id: str,
        candidate_id: int,
        caller_user_id: int,
        candidate_phone: str,
        candidate_name: str,
        whisper_context: str,
    ) -> RecruitingCallResult:
        """
        Initiate a click-to-call to a candidate.
        """
        if not self.client:
            return RecruitingCallResult(
                success=False,
                call_id=call_id,
                status="failed",
                error=f"{self.provider.capitalize()} not configured",
                message=f"{self.provider.capitalize()} credentials not configured"
            )

        if not self.from_number:
            return RecruitingCallResult(
                success=False,
                call_id=call_id,
                status="failed",
                error=f"{self.provider.upper()}_PHONE_NUMBER not configured",
                message="Phone number not configured"
            )

        # Get recruiter's phone number
        recruiter_phone = self._get_user_phone(caller_user_id, organization_id=self.organization_id)
        if not recruiter_phone:
            return RecruitingCallResult(
                success=False,
                call_id=call_id,
                status="failed",
                error="Recruiter has no phone number configured",
                message="Please configure your phone number in settings"
            )

        # Format phone numbers
        candidate_phone_formatted = self._format_phone(candidate_phone)
        recruiter_phone_formatted = self._format_phone(recruiter_phone)

        if not candidate_phone_formatted:
            return RecruitingCallResult(
                success=False,
                call_id=call_id,
                status="failed",
                error="Invalid candidate phone number",
                message="Candidate phone number is invalid"
            )

        try:
            # Call the RECRUITER first via Telnyx
            call_sid = self._initiate_telnyx_call(
                recruiter_phone_formatted, call_id
            )

            self._update_call_record(call_id, {
                "twilio_call_sid": call_sid,  # Legacy column name — stores Telnyx call control ID
                "status": "calling_recruiter",
                "phone_from": self.from_number,
                "phone_to": candidate_phone_formatted,
            })

            logger.info(f"Recruiting call initiated: {call_sid} for candidate {candidate_id} via {self.provider}")

            return RecruitingCallResult(
                success=True,
                call_id=call_id,
                call_sid=call_sid,
                status="calling_recruiter",
                message=f"Calling your phone now. You'll hear context about {candidate_name} before connecting.",
                provider=self.provider
            )

        except Exception as e:
            logger.error(f"Failed to initiate recruiting call: {e}")
            self._update_call_record(call_id, {"status": "failed"})

            return RecruitingCallResult(
                success=False,
                call_id=call_id,
                status="failed",
                error=str(e),
                message=f"Failed to initiate call: {str(e)}"
            )

    def _initiate_telnyx_call(self, to_phone: str, call_id: str) -> str:
        """Initiate call via Telnyx"""
        connection_id = os.getenv("TELNYX_CONNECTION_ID")

        call = self.client.calls.create(
            connection_id=connection_id,
            to=to_phone,
            from_=self.from_number,
            webhook_url=f"{BASE_URL}/api/v1/recruiting/dialer/telnyx/recruiter-answered/{call_id}",
            webhook_url_method="POST",
            timeout_secs=30,
            record="record-from-answer",
        )
        return call.data.call_control_id

    def generate_recruiter_twiml(self, call_id: str) -> str:
        """Generate TeXML for when recruiter answers."""
        call_record = self._get_call_record(call_id, organization_id=self.organization_id)

        if not call_record:
            response = VoiceResponseBuilder()
            response.say("Sorry, there was an error with this call.")
            response.hangup()
            return response.to_xml()

        response = VoiceResponseBuilder()

        whisper = call_record.get("whisper_context", "")
        if not whisper:
            whisper = "Calling candidate. Press 1 to connect."

        webhook_prefix = "telnyx"

        response.gather(
            num_digits=1,
            action=f"{BASE_URL}/api/v1/recruiting/dialer/{webhook_prefix}/recruiter-response/{call_id}",
            timeout=10
        )
        response.gather_say(whisper)
        response.gather_say("Press 1 to connect now, or hang up to cancel.")
        response.end_gather()

        response.say("I didn't catch that.")
        response.redirect(f"{BASE_URL}/api/v1/recruiting/dialer/{webhook_prefix}/recruiter-answered/{call_id}")

        return response.to_xml()

    def generate_recruiter_response_twiml(self, call_id: str, digits: str) -> str:
        """Handle recruiter's DTMF response."""
        call_record = self._get_call_record(call_id, organization_id=self.organization_id)

        if not call_record:
            response = VoiceResponseBuilder()
            response.say("Sorry, there was an error.")
            response.hangup()
            return response.to_xml()

        response = VoiceResponseBuilder()
        webhook_prefix = "telnyx"

        if digits == "1":
            candidate_phone = call_record.get("phone_to")

            if not candidate_phone:
                response.say("Sorry, candidate phone number not found.")
                response.hangup()
                return response.to_xml()

            response.say("Connecting you now. Please hold.")

            response.dial(
                number=candidate_phone,
                caller_id=self.from_number,
                timeout=30,
                record="record-from-answer-dual",
                action=f"{BASE_URL}/api/v1/recruiting/dialer/{webhook_prefix}/call-complete/{call_id}",
                recording_callback=f"{BASE_URL}/api/v1/recruiting/dialer/{webhook_prefix}/recording/{call_id}",
                status_callback=f"{BASE_URL}/api/v1/recruiting/dialer/{webhook_prefix}/candidate-status/{call_id}"
            )

            self._update_call_record(call_id, {"status": "connecting_candidate"})

        else:
            response.say("Call cancelled. Goodbye.")
            response.hangup()
            self._update_call_record(call_id, {
                "status": "cancelled",
                "outcome": "recruiter_cancelled",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })

        return response.to_xml()

    def generate_call_complete_twiml(self, call_id: str, dial_status: str) -> str:
        """Handle call completion after candidate leg ends."""
        response = VoiceResponseBuilder()

        status_messages = {
            "completed": "Call completed. Thank you.",
            "busy": "The candidate's line was busy.",
            "no-answer": "The candidate did not answer.",
            "failed": "The call could not be completed.",
            "canceled": "The call was cancelled.",
        }

        message = status_messages.get(dial_status, "Call ended.")
        response.say(message)
        response.hangup()

        outcome_map = {
            "completed": "connected",
            "busy": "busy",
            "no-answer": "no_answer",
            "failed": "failed",
            "canceled": "cancelled",
        }

        self._update_call_record(call_id, {
            "status": "completed",
            "outcome": outcome_map.get(dial_status, dial_status),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        return response.to_xml()

    def handle_status_callback(
        self,
        call_id: str,
        call_status: str,
        call_duration: Optional[int] = None,
    ):
        """Handle call status callback"""
        updates = {"last_status": call_status}

        if call_status in ["completed", "busy", "no-answer", "failed", "canceled", "hangup"]:
            updates["status"] = "completed"
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()

        if call_duration:
            updates["duration_seconds"] = call_duration

        self._update_call_record(call_id, updates)

    def handle_recording_callback(
        self,
        call_id: str,
        recording_url: str,
        recording_duration: Optional[int] = None,
    ):
        """Handle recording status callback"""
        self._update_call_record(call_id, {
            "recording_url": recording_url,
            "recording_duration": recording_duration,
        })
        logger.info(f"Recording saved for call {call_id}: {recording_url}")

    def _get_user_phone(self, user_id: int, organization_id: Optional[int] = None) -> Optional[str]:
        """Get user's phone number from database with optional org isolation."""
        try:
            org_filter = ""
            params = {"user_id": user_id}
            if organization_id:
                org_filter = "AND organization_id = :org_id"
                params["org_id"] = organization_id

            sql = "SELECT phone FROM users WHERE id = :user_id"
            if org_filter:
                sql += " " + org_filter
            result = self.db.execute(text(sql), params).first()
            return result.phone if result else None
        except Exception as e:
            logger.error(f"Error getting user phone: {e}")
            return None

    def _format_phone(self, phone: str) -> Optional[str]:
        """Format phone number to E.164"""
        if not phone:
            return None

        digits = ''.join(filter(str.isdigit, phone))

        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith('1'):
            return f"+{digits}"
        elif len(digits) > 11 and phone.startswith('+'):
            return phone

        return None

    def _get_call_record(self, call_id: str, organization_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get call record from database with optional org isolation."""
        try:
            org_filter = ""
            params = {"call_id": call_id}
            if organization_id:
                org_filter = "AND rc.organization_id = :org_id"
                params["org_id"] = organization_id

            sql = "SELECT rc.* FROM recruiting_calls rc JOIN mm_candidates c ON c.id = rc.candidate_id WHERE rc.id = :call_id"
            if org_filter:
                sql += " " + org_filter
            result = self.db.execute(text(sql), params).first()

            if result:
                return dict(result._mapping)
            return None
        except Exception as e:
            logger.error(f"Error getting call record: {e}")
            return None

    # Allowlist of columns that can be updated on recruiting_calls
    _ALLOWED_UPDATE_COLUMNS = {
        "twilio_call_sid", "status", "phone_from", "phone_to", "outcome",
        "completed_at", "last_status", "duration_seconds", "recording_url",
        "recording_duration",
    }

    def _update_call_record(self, call_id: str, updates: Dict[str, Any]):
        """Update call record in database"""
        try:
            # Validate column names against allowlist
            safe_updates = {k: v for k, v in updates.items() if k in self._ALLOWED_UPDATE_COLUMNS}
            if not safe_updates:
                return
            set_clauses = ", ".join([f"{k} = :{k}" for k in safe_updates.keys()])
            params = {"call_id": call_id, **safe_updates}

            sql = "UPDATE recruiting_calls SET " + set_clauses + ", updated_at = NOW() WHERE id = :call_id"
            self.db.execute(text(sql), params)
            self.db.commit()
        except Exception as e:
            logger.error(f"Error updating call record: {e}")
            try:
                self.db.rollback()
            except Exception:
                pass


def get_recruiting_dialer_service(db_session, organization_id: Optional[int] = None) -> RecruitingDialerService:
    """Factory function to create a RecruitingDialerService instance.

    This replaces the deleted legacy recruiting telephony service.
    The RecruitingDialerService uses Telnyx as the telephony provider.
    """
    return RecruitingDialerService(db_session, organization_id=organization_id)


# Backward-compatible alias for code that imported get_recruiting_twilio_service
get_recruiting_twilio_service = get_recruiting_dialer_service
