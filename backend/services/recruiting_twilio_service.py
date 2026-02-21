"""
Recruiting Twilio Dialer Service

Integrates Twilio calling for the recruiting platform:
- Click-to-call for candidates
- Whisper context before connection
- Call recording
- Status tracking and webhooks

FLOW:
1. Recruiter clicks "Call" on candidate
2. System calls RECRUITER first (so they're ready)
3. Recruiter hears whisper: "Calling [Name] from [Company]. Production: $X. Press 1 to connect."
4. Recruiter presses 1 → System dials candidate
5. Candidate answers → Both connected
6. Call recorded for training/compliance
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Dial, Gather
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
TWILIO_PHONE_NUMBER = (os.getenv("TWILIO_PHONE_NUMBER") or "").strip()
BASE_URL = os.getenv("BASE_URL", "https://app.perenniaai.com")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RecruitingCallResult:
    """Result of initiating a recruiting call"""
    success: bool
    call_id: Optional[str] = None
    call_sid: Optional[str] = None
    status: str = "initiated"
    message: str = ""
    error: Optional[str] = None


# =============================================================================
# TWILIO CLIENT
# =============================================================================

def get_twilio_client() -> Optional[Client]:
    """Get Twilio client if credentials are configured"""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN]):
        logger.warning("Twilio credentials not configured for recruiting dialer")
        return None
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# =============================================================================
# RECRUITING TWILIO SERVICE
# =============================================================================

class RecruitingTwilioService:
    """
    Manages Twilio calling for recruiting candidates.

    Uses a "recruiter-first" model where we call the recruiter,
    play context whisper, then connect to candidate on confirmation.
    """

    def __init__(self, db_session):
        self.db = db_session
        self.client = get_twilio_client()

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

        1. Get recruiter's phone number
        2. Call recruiter first
        3. Play whisper context
        4. On confirmation, dial candidate

        Args:
            call_id: UUID of the call record
            candidate_id: ID of candidate being called
            caller_user_id: ID of recruiter making the call
            candidate_phone: Candidate's phone number
            candidate_name: Candidate's name for display
            whisper_context: Context to whisper to recruiter

        Returns:
            RecruitingCallResult with status
        """
        if not self.client:
            return RecruitingCallResult(
                success=False,
                call_id=call_id,
                status="failed",
                error="Twilio not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.",
                message="Twilio credentials not configured"
            )

        if not TWILIO_PHONE_NUMBER:
            return RecruitingCallResult(
                success=False,
                call_id=call_id,
                status="failed",
                error="TWILIO_PHONE_NUMBER not configured",
                message="Twilio phone number not configured"
            )

        # Get recruiter's phone number
        recruiter_phone = self._get_user_phone(caller_user_id)
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
            # Call the RECRUITER first
            # When they answer, TwiML will play whisper and prompt for confirmation
            call = self.client.calls.create(
                to=recruiter_phone_formatted,
                from_=TWILIO_PHONE_NUMBER,
                url=f"{BASE_URL}/api/v1/recruiting/dialer/twilio/recruiter-answered/{call_id}",
                status_callback=f"{BASE_URL}/api/v1/recruiting/dialer/twilio/status/{call_id}",
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                status_callback_method="POST",
                timeout=30,
                record=True,
                recording_status_callback=f"{BASE_URL}/api/v1/recruiting/dialer/twilio/recording/{call_id}",
                recording_status_callback_event=["completed"],
            )

            # Update call record with Twilio SID
            self._update_call_record(call_id, {
                "twilio_call_sid": call.sid,
                "status": "calling_recruiter",
                "phone_from": TWILIO_PHONE_NUMBER,
                "phone_to": candidate_phone_formatted,
            })

            logger.info(f"Recruiting call initiated: {call.sid} for candidate {candidate_id}")

            return RecruitingCallResult(
                success=True,
                call_id=call_id,
                call_sid=call.sid,
                status="calling_recruiter",
                message=f"Calling your phone now. You'll hear context about {candidate_name} before connecting."
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

    def generate_recruiter_twiml(self, call_id: str) -> str:
        """
        Generate TwiML for when recruiter answers.

        Plays whisper context and prompts for confirmation before connecting.
        """
        call_record = self._get_call_record(call_id)

        if not call_record:
            response = VoiceResponse()
            response.say("Sorry, there was an error with this call.", voice="Polly.Matthew")
            response.hangup()
            return str(response)

        response = VoiceResponse()

        # Build whisper message
        whisper = call_record.get("whisper_context", "")
        if not whisper:
            whisper = f"Calling candidate. Press 1 to connect."

        # Create gather for DTMF input
        gather = response.gather(
            num_digits=1,
            action=f"{BASE_URL}/api/v1/recruiting/dialer/twilio/recruiter-response/{call_id}",
            timeout=10,
            input="dtmf",
        )
        gather.say(whisper, voice="Polly.Matthew")
        gather.say("Press 1 to connect now, or hang up to cancel.", voice="Polly.Matthew")

        # If no input, retry once
        response.say("I didn't catch that.", voice="Polly.Matthew")
        response.redirect(f"{BASE_URL}/api/v1/recruiting/dialer/twilio/recruiter-answered/{call_id}")

        return str(response)

    def generate_recruiter_response_twiml(self, call_id: str, digits: str) -> str:
        """
        Handle recruiter's DTMF response.

        1 = Connect to candidate
        Other = Cancel
        """
        call_record = self._get_call_record(call_id)

        if not call_record:
            response = VoiceResponse()
            response.say("Sorry, there was an error.", voice="Polly.Matthew")
            response.hangup()
            return str(response)

        response = VoiceResponse()

        if digits == "1":
            # Connect to candidate
            candidate_phone = call_record.get("phone_to")

            if not candidate_phone:
                response.say("Sorry, candidate phone number not found.", voice="Polly.Matthew")
                response.hangup()
                return str(response)

            response.say("Connecting you now. Please hold.", voice="Polly.Matthew")

            # Dial the candidate
            dial = response.dial(
                caller_id=TWILIO_PHONE_NUMBER,
                timeout=30,
                record="record-from-answer-dual",  # Record both legs
                recording_status_callback=f"{BASE_URL}/api/v1/recruiting/dialer/twilio/recording/{call_id}",
                action=f"{BASE_URL}/api/v1/recruiting/dialer/twilio/call-complete/{call_id}",
            )
            dial.number(
                candidate_phone,
                status_callback=f"{BASE_URL}/api/v1/recruiting/dialer/twilio/candidate-status/{call_id}",
                status_callback_event="initiated ringing answered completed",
            )

            # Update status
            self._update_call_record(call_id, {"status": "connecting_candidate"})

        else:
            # Cancel call
            response.say("Call cancelled. Goodbye.", voice="Polly.Matthew")
            response.hangup()
            self._update_call_record(call_id, {
                "status": "cancelled",
                "outcome": "recruiter_cancelled",
                "completed_at": datetime.utcnow().isoformat(),
            })

        return str(response)

    def generate_call_complete_twiml(self, call_id: str, dial_status: str) -> str:
        """
        Handle call completion after candidate leg ends.
        """
        response = VoiceResponse()

        # Map Twilio dial status to our outcome
        outcome_map = {
            "completed": "answered",
            "answered": "answered",
            "busy": "busy",
            "no-answer": "no_answer",
            "failed": "failed",
            "canceled": "cancelled",
        }

        outcome = outcome_map.get(dial_status, dial_status)

        self._update_call_record(call_id, {
            "status": "completed",
            "outcome": outcome,
            "completed_at": datetime.utcnow().isoformat(),
        })

        if outcome == "answered":
            response.say("Call ended. Thank you.", voice="Polly.Matthew")
        elif outcome in ["busy", "no_answer"]:
            response.say(f"Candidate {outcome.replace('_', ' ')}. Call ended.", voice="Polly.Matthew")
        else:
            response.say("Call ended.", voice="Polly.Matthew")

        response.hangup()
        return str(response)

    def handle_status_callback(
        self,
        call_id: str,
        call_status: str,
        call_duration: Optional[int] = None,
        call_sid: Optional[str] = None,
    ):
        """Handle Twilio status callback"""
        status_map = {
            "initiated": "initiated",
            "ringing": "ringing",
            "in-progress": "in_progress",
            "answered": "in_progress",
            "completed": "completed",
            "busy": "completed",
            "no-answer": "completed",
            "failed": "failed",
            "canceled": "cancelled",
        }

        updates = {"status": status_map.get(call_status, call_status)}

        if call_duration:
            updates["duration_seconds"] = call_duration

        if call_status in ["completed", "busy", "no-answer", "failed", "canceled"]:
            updates["completed_at"] = datetime.utcnow().isoformat()
            if call_status != "completed":
                updates["outcome"] = call_status.replace("-", "_")

        self._update_call_record(call_id, updates)

        logger.info(f"Recruiting call {call_id} status: {call_status}")

    def handle_recording_callback(
        self,
        call_id: str,
        recording_url: str,
        recording_sid: str,
        recording_duration: int,
    ):
        """Handle recording completion callback"""
        self._update_call_record(call_id, {
            "recording_url": recording_url,
            "recording_sid": recording_sid,
            "duration_seconds": recording_duration,
        })

        logger.info(f"Recruiting call {call_id} recording saved: {recording_sid}")

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_user_phone(self, user_id: int) -> Optional[str]:
        """Get user's phone number from database"""
        try:
            result = self.db.execute(
                text("SELECT phone FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )
            row = result.fetchone()
            return row.phone if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error getting user phone: {e}")
            return None

    def _get_call_record(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get call record from database"""
        try:
            result = self.db.execute(
                text("""
                    SELECT id, candidate_id, caller_user_id, direction,
                           phone_from, phone_to, whisper_context,
                           duration_seconds, status, outcome, notes,
                           recording_url, called_at, completed_at,
                           twilio_call_sid
                    FROM recruiting_call_history
                    WHERE id = :call_id
                """),
                {"call_id": call_id}
            )
            row = result.fetchone()
            if row:
                return {
                    "id": row.id,
                    "candidate_id": row.candidate_id,
                    "caller_user_id": row.caller_user_id,
                    "direction": row.direction,
                    "phone_from": row.phone_from,
                    "phone_to": row.phone_to,
                    "whisper_context": row.whisper_context,
                    "duration_seconds": row.duration_seconds,
                    "status": row.status,
                    "outcome": row.outcome,
                    "notes": row.notes,
                    "recording_url": row.recording_url,
                    "twilio_call_sid": getattr(row, 'twilio_call_sid', None),
                }
            return None
        except Exception as e:
            logger.error(f"Error getting call record: {e}")
            return None

    def _update_call_record(self, call_id: str, updates: Dict[str, Any]):
        """Update call record in database"""
        try:
            # Build SET clause dynamically
            set_parts = []
            params = {"call_id": call_id}

            for key, value in updates.items():
                set_parts.append(f"{key} = :{key}")
                params[key] = value

            if not set_parts:
                return

            query = f"UPDATE recruiting_call_history SET {', '.join(set_parts)} WHERE id = :call_id"
            self.db.execute(text(query), params)
            self.db.commit()

        except SQLAlchemyError as e:
            logger.error(f"Error updating call record: {e}")
            self.db.rollback()

    def _format_phone(self, phone: str) -> Optional[str]:
        """Format phone number to E.164 format"""
        if not phone:
            return None

        # Remove all non-numeric characters
        digits = ''.join(c for c in phone if c.isdigit())

        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        elif len(digits) > 10:
            return f"+{digits}"

        return None


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_service_instance = None


def get_recruiting_twilio_service(db_session) -> RecruitingTwilioService:
    """Get recruiting Twilio service instance"""
    return RecruitingTwilioService(db_session)
