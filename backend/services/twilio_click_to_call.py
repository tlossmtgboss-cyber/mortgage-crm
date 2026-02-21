"""
Twilio Click-to-Call Service - Production Version

Implements whisper+bridge calling for the chat state machine:

CORRECT PRODUCTION FLOW:
1. User clicks "Call Now" in chat (frontend shows "Calling your phone...")
2. System calls the BORROWER first
3. Borrower hears: "Hi [Name]! Tim from Perennia Mortgage is ready to speak with you.
   Press 1 to connect now, or press 2 to schedule for later."
4. If borrower presses 1:
   - Put borrower in conference with hold music
   - System calls Tim (LO)
5. Tim hears whisper: "Incoming call from [Name]. They're interested in [summary].
   Intent score: [X]. Press 1 to connect."
6. Tim presses 1, joins conference
7. Both parties bridged and talking

KEY FEATURES:
- Borrower-first calling (user doesn't wait for LO to answer)
- Whisper context for LO (no cold calls)
- DTMF confirmation from both parties
- Graceful fallback to scheduling if LO unavailable
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Dial, Say, Gather
from sqlalchemy.orm import Session

from chat_state_machine_models import CallRequest, ChatSession, CallStatus
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
TWILIO_PHONE_NUMBER = (os.getenv("TWILIO_PHONE_NUMBER") or "").strip()
BASE_URL = os.getenv("BASE_URL", "https://app.perenniaai.com")

# Default LO name (should be fetched from DB in production)
DEFAULT_LO_NAME = os.getenv("DEFAULT_LO_NAME", "Tim")


# =============================================================================
# TWILIO CLIENT
# =============================================================================

def get_twilio_client() -> Optional[Client]:
    """Get Twilio client if credentials are configured"""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN]):
        logger.warning("Twilio credentials not configured")
        return None
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# =============================================================================
# CLICK-TO-CALL SERVICE
# =============================================================================

class ClickToCallService:
    """
    Manages click-to-call functionality with whisper+bridge.

    PRODUCTION FLOW:
    1. initiate_call() - Starts the process, calls BORROWER first
    2. borrower_answered_callback() - Borrower answers, hears greeting + DTMF prompt
    3. borrower presses 1 → put in conference, trigger LO call
    4. lo_answered_callback() - LO answers, hears whisper context
    5. LO presses 1 → joins conference
    6. Both parties connected and talking
    """

    def __init__(self, db: Session):
        self.db = db
        self.client = get_twilio_client()

    def initiate_call(self, call_request_id: UUID) -> Dict[str, Any]:
        """
        Initiate click-to-call for a call request.

        1. Update call request status
        2. Call the BORROWER'S phone first
        3. On answer, prompt for confirmation
        4. If confirmed, create conference and call LO

        Returns status info for frontend polling
        """
        if not self.client:
            return {
                "success": False,
                "error": "Twilio not configured",
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
            # Call the borrower FIRST (they clicked the button, so call them immediately)
            borrower_call = self.client.calls.create(
                to=call_request.caller_phone,
                from_=TWILIO_PHONE_NUMBER,
                url=f"{BASE_URL}/api/v1/twilio/borrower-answered/{call_request_id}",
                status_callback=f"{BASE_URL}/api/v1/twilio/call-status/{call_request_id}",
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                status_callback_method="POST",
                timeout=30,  # 30 second timeout
            )

            # Store the call SID
            call_request.twilio_call_sid = borrower_call.sid
            self.db.commit()

            logger.info(f"Initiated call to borrower: {borrower_call.sid}")

            return {
                "success": True,
                "call_sid": borrower_call.sid,
                "status": CallStatus.CONNECTING.value,
                "message": "Calling your phone now..."
            }

        except SQLAlchemyError as e:
            logger.error(f"Failed to initiate call: {e}")
            call_request.status = CallStatus.FAILED.value
            self.db.commit()

            return {
                "success": False,
                "error": "Internal server error",
                "status": CallStatus.FAILED.value
            }

    def generate_borrower_twiml(self, call_request_id: UUID) -> str:
        """
        Generate TwiML for when BORROWER answers.

        Enhanced flow with DTMF confirmation:
        1. Personalized greeting with LO name
        2. Prompt to confirm (press 1) or schedule (press 2)
        3. If 1: Join conference, trigger LO call
        4. If 2: Offer scheduling options
        """
        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            response = VoiceResponse()
            response.say("Sorry, we couldn't connect your call. Please try again.", voice="Polly.Joanna")
            return str(response)

        # Get LO name for personalization
        lo_name = self._get_lo_name(call_request.loan_officer_id) or DEFAULT_LO_NAME
        borrower_name = call_request.caller_name or "there"

        response = VoiceResponse()

        # Personalized greeting
        greeting = f"Hi {borrower_name}! {lo_name} from Perennia Mortgage is ready to speak with you about your mortgage options."

        # Create gather for DTMF input
        gather = response.gather(
            num_digits=1,
            action=f"{BASE_URL}/api/v1/twilio/borrower-response/{call_request_id}",
            timeout=10,
            input="dtmf",
        )
        gather.say(greeting, voice="Polly.Joanna")
        gather.say("Press 1 to connect now, or press 2 to schedule for a better time.", voice="Polly.Joanna")

        # If no input, retry once
        response.say("I didn't catch that.", voice="Polly.Joanna")
        response.redirect(f"{BASE_URL}/api/v1/twilio/borrower-answered/{call_request_id}")

        return str(response)

    def generate_borrower_response_twiml(self, call_request_id: UUID, digits: str) -> str:
        """
        Handle borrower's DTMF response.

        1 = Connect now → Join conference, trigger LO call
        2 = Schedule later → Thank and hang up (scheduling handled in chat)
        """
        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            response = VoiceResponse()
            response.say("Sorry, there was an error.", voice="Polly.Joanna")
            return str(response)

        conference_name = f"chat_call_{call_request_id}"
        response = VoiceResponse()

        if digits == "1":
            # Borrower wants to connect now
            response.say("Great! Please hold while we connect you. This will just take a moment.", voice="Polly.Joanna")

            # Put borrower in conference with hold music
            dial = Dial()
            dial.conference(
                conference_name,
                start_conference_on_enter=False,  # Wait for LO to start
                end_conference_on_exit=True,
                wait_url="http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical",
                status_callback=f"{BASE_URL}/api/v1/twilio/conference-status/{call_request_id}",
                status_callback_event="join leave",
            )
            response.append(dial)

            # Trigger call to LO
            self._trigger_lo_call(call_request)

        elif digits == "2":
            # Borrower wants to schedule
            response.say(
                "No problem! You can schedule a call at a time that works better for you "
                "through our chat. We look forward to speaking with you soon. Goodbye!",
                voice="Polly.Joanna"
            )
            response.hangup()

            # Update status - borrower requested scheduling
            call_request.status = CallStatus.CANCELLED.value
            call_request.outcome = "borrower_requested_schedule"
            call_request.ended_at = datetime.now(timezone.utc)
            self.db.commit()

        else:
            # Invalid input - retry
            response.say("Sorry, I didn't understand that.", voice="Polly.Joanna")
            response.redirect(f"{BASE_URL}/api/v1/twilio/borrower-answered/{call_request_id}")

        return str(response)

    def _trigger_lo_call(self, call_request: CallRequest):
        """
        Trigger call to loan officer.

        Called after borrower confirms they want to connect.
        """
        if not self.client:
            logger.error("Twilio client not configured")
            return

        lo_phone = self._get_lo_phone(call_request.loan_officer_id)
        if not lo_phone:
            logger.error(f"No phone for LO {call_request.loan_officer_id}")
            # Notify borrower that LO is unavailable
            self._notify_borrower_lo_unavailable(call_request, "no_phone")
            return

        try:
            lo_call = self.client.calls.create(
                to=lo_phone,
                from_=TWILIO_PHONE_NUMBER,
                url=f"{BASE_URL}/api/v1/twilio/lo-answered/{call_request.id}",
                status_callback=f"{BASE_URL}/api/v1/twilio/lo-call-status/{call_request.id}",
                status_callback_event=["answered", "completed", "no-answer", "busy", "failed"],
                status_callback_method="POST",
                timeout=30,  # 30 second timeout for LO to answer
            )

            logger.info(f"Calling LO: {lo_call.sid}")

        except Exception as e:
            logger.error(f"Failed to call LO: {e}")
            # Notify borrower that LO is unavailable, offer scheduling
            self._notify_borrower_lo_unavailable(call_request, "call_failed")

    def generate_lo_twiml(self, call_request_id: UUID) -> str:
        """
        Generate TwiML for when LO answers.

        Enhanced whisper with full context:
        1. Caller name and intent summary
        2. Key signals detected (price, timeline, etc.)
        3. Intent score and urgency level
        4. DTMF prompt to accept
        """
        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            response = VoiceResponse()
            response.say("Sorry, there was an error.", voice="Polly.Matthew")
            return str(response)

        conference_name = f"chat_call_{call_request_id}"

        response = VoiceResponse()

        # Build enhanced whisper message
        whisper = self._build_enhanced_whisper(call_request)

        # Create gather for DTMF input
        gather = response.gather(
            num_digits=1,
            action=f"{BASE_URL}/api/v1/twilio/lo-response/{call_request_id}",
            timeout=15,
            input="dtmf",
        )

        # Play whisper message
        gather.say(whisper, voice="Polly.Matthew")
        gather.say("Press 1 to connect now.", voice="Polly.Matthew")

        # If no input, repeat once
        response.say("The caller is waiting. Press 1 to connect.", voice="Polly.Matthew")
        response.redirect(f"{BASE_URL}/api/v1/twilio/lo-answered/{call_request_id}")

        return str(response)

    def _build_enhanced_whisper(self, call_request: CallRequest) -> str:
        """
        Build a rich whisper message with conversation context.

        Gives LO full context before accepting the call.
        """
        parts = []

        # Caller identification
        caller_name = call_request.caller_name or "A website visitor"
        parts.append(f"Incoming call from {caller_name}.")

        # Intent summary
        if call_request.intent_summary:
            parts.append(call_request.intent_summary)
        else:
            # Build from signals snapshot
            signals = call_request.intent_signals_snapshot or []
            signal_map = {s.get('signal'): s.get('value') for s in signals if s.get('signal')}

            if 'goal' in signal_map:
                parts.append(f"Interested in {signal_map['goal']}.")
            if 'price' in signal_map:
                parts.append(f"Budget around {signal_map['price']}.")
            if 'timeline' in signal_map:
                parts.append(f"Timeline: {signal_map['timeline']}.")
            if 'loan_type' in signal_map:
                parts.append(f"Asking about {signal_map['loan_type']}.")

        # Get session for more context
        session = call_request.session
        if session:
            parts.append(f"Intent score: {session.intent_score} out of 100.")
            if session.urgency == 'high':
                parts.append("High urgency detected.")

        return " ".join(parts) if parts else "Incoming call from website visitor."

    def generate_lo_response_twiml(self, call_request_id: UUID, digits: str) -> str:
        """
        Handle LO's response to whisper prompt.

        1 = Accept call, join conference → conversation begins
        Any other = Decline → borrower notified, offered scheduling
        """
        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            response = VoiceResponse()
            response.say("Sorry, there was an error.", voice="Polly.Matthew")
            return str(response)

        conference_name = f"chat_call_{call_request_id}"

        response = VoiceResponse()

        if digits == "1":
            # Accept - join conference
            response.say("Connecting you now.", voice="Polly.Matthew")

            dial = Dial()
            dial.conference(
                conference_name,
                start_conference_on_enter=True,  # Start conference when LO joins
                end_conference_on_exit=True,
                record="record-from-start",  # Optional: record for quality/training
            )
            response.append(dial)

            # Update status
            call_request.status = CallStatus.IN_PROGRESS.value
            call_request.connected_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(f"LO connected to call {call_request_id}")

        else:
            # Decline
            response.say(
                "Call declined. The caller will be offered scheduling options.",
                voice="Polly.Matthew"
            )
            response.hangup()

            # Update status
            call_request.status = CallStatus.CANCELLED.value
            call_request.outcome = "lo_declined"
            call_request.ended_at = datetime.now(timezone.utc)
            self.db.commit()

            # Notify borrower that LO is unavailable via SMS
            # Frontend also polls call status for UI updates
            self._notify_borrower_lo_unavailable(call_request, "declined")

            logger.info(f"LO declined call {call_request_id}")

        return str(response)

    def handle_call_status(
        self,
        call_request_id: UUID,
        call_status: str,
        call_duration: Optional[int] = None,
    ):
        """Handle Twilio call status callback"""
        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            return

        status_mapping = {
            "completed": CallStatus.COMPLETED.value,
            "busy": CallStatus.NO_ANSWER.value,
            "no-answer": CallStatus.NO_ANSWER.value,
            "failed": CallStatus.FAILED.value,
            "canceled": CallStatus.CANCELLED.value,
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

        from sqlalchemy import text
        result = self.db.execute(text("""
            SELECT phone FROM users WHERE id = :lo_id
        """), {"lo_id": loan_officer_id}).first()

        return result.phone if result else None

    def _get_lo_name(self, loan_officer_id: Optional[int]) -> Optional[str]:
        """Get loan officer's name for personalization"""
        if not loan_officer_id:
            return None

        from sqlalchemy import text
        result = self.db.execute(text("""
            SELECT full_name, COALESCE(SPLIT_PART(full_name, ' ', 1), full_name) as first_name
            FROM users WHERE id = :lo_id
        """), {"lo_id": loan_officer_id}).first()

        if result:
            # Return first name for friendlier greeting
            return result.first_name or result.full_name

        return None

    def _notify_borrower_lo_unavailable(self, call_request: CallRequest, reason: str):
        """
        Send SMS notification to borrower when LO is unavailable.

        Informs the borrower and offers scheduling as an alternative.
        """
        try:
            from services.notification_service import notification_service

            borrower_phone = call_request.caller_phone
            borrower_name = call_request.caller_name or "there"
            lo_name = self._get_lo_name(call_request.loan_officer_id) or DEFAULT_LO_NAME

            if not borrower_phone:
                logger.warning(f"No phone to notify borrower for call {call_request.id}")
                return

            # Build message based on reason
            if reason == "declined":
                message = (
                    f"Hi {borrower_name.split()[0] if borrower_name != 'there' else 'there'}, "
                    f"{lo_name} is currently with another client. "
                    f"We'll reach out shortly to schedule a convenient time to talk. "
                    f"Reply STOP to opt out."
                )
            elif reason == "call_failed":
                message = (
                    f"Hi {borrower_name.split()[0] if borrower_name != 'there' else 'there'}, "
                    f"we couldn't complete your call with {lo_name} at this time. "
                    f"We'll contact you shortly to schedule a callback. "
                    f"Reply STOP to opt out."
                )
            else:  # no_phone, no_answer, etc.
                message = (
                    f"Hi {borrower_name.split()[0] if borrower_name != 'there' else 'there'}, "
                    f"{lo_name} is temporarily unavailable. "
                    f"We'll reach out soon to schedule a time that works for you. "
                    f"Reply STOP to opt out."
                )

            result = notification_service.send_sms(to_phone=borrower_phone, message=message)

            if result.get("success"):
                logger.info(f"LO unavailable SMS sent to {borrower_phone} for call {call_request.id}")
            else:
                logger.warning(f"Failed to send LO unavailable SMS: {result.get('error')}")

        except Exception as e:
            logger.error(f"Error sending LO unavailable notification: {e}")

    def handle_lo_unavailable(self, call_request_id: UUID, reason: str = "no_answer"):
        """
        Handle case when LO doesn't answer or declines.

        Updates call status and session so frontend can offer scheduling.
        """
        call_request = self.db.query(CallRequest).filter(
            CallRequest.id == call_request_id
        ).first()

        if not call_request:
            return

        call_request.status = CallStatus.NO_ANSWER.value
        call_request.outcome = f"lo_{reason}"
        call_request.ended_at = datetime.now(timezone.utc)

        # Mark that scheduling should be offered
        if call_request.session:
            # The frontend can check this via call status polling
            pass

        self.db.commit()

        logger.info(f"LO unavailable for call {call_request_id}: {reason}")


# =============================================================================
# TWILIO WEBHOOK ROUTES
# =============================================================================

def create_twilio_routes():
    """Create FastAPI routes for Twilio webhooks"""
    from fastapi import APIRouter, Form, Depends
    from database import get_db

    router = APIRouter(prefix="/api/v1/twilio", tags=["Twilio Webhooks"])

    @router.post("/borrower-answered/{call_request_id}")
    async def borrower_answered(
        call_request_id: UUID,
        db: Session = Depends(get_db),
    ):
        """
        Webhook called when borrower answers.

        Plays greeting and prompts for DTMF confirmation.
        """
        from fastapi.responses import Response

        service = ClickToCallService(db)
        twiml = service.generate_borrower_twiml(call_request_id)

        return Response(content=twiml, media_type="application/xml")

    @router.post("/borrower-response/{call_request_id}")
    async def borrower_response(
        call_request_id: UUID,
        Digits: str = Form(""),
        db: Session = Depends(get_db),
    ):
        """
        Webhook for borrower's DTMF response.

        1 = Connect now → Join conference, trigger LO call
        2 = Schedule later → Thank and hang up
        """
        from fastapi.responses import Response

        service = ClickToCallService(db)
        twiml = service.generate_borrower_response_twiml(call_request_id, Digits)

        return Response(content=twiml, media_type="application/xml")

    @router.post("/lo-answered/{call_request_id}")
    async def lo_answered(
        call_request_id: UUID,
        db: Session = Depends(get_db),
    ):
        """
        Webhook called when LO answers.

        Plays whisper context and prompts for DTMF confirmation.
        """
        from fastapi.responses import Response

        service = ClickToCallService(db)
        twiml = service.generate_lo_twiml(call_request_id)

        return Response(content=twiml, media_type="application/xml")

    @router.post("/lo-response/{call_request_id}")
    async def lo_response(
        call_request_id: UUID,
        Digits: str = Form(""),
        db: Session = Depends(get_db),
    ):
        """
        Webhook for LO's DTMF response.

        1 = Accept → Join conference, conversation begins
        Other = Decline → Borrower offered scheduling
        """
        from fastapi.responses import Response

        service = ClickToCallService(db)
        twiml = service.generate_lo_response_twiml(call_request_id, Digits)

        return Response(content=twiml, media_type="application/xml")

    @router.post("/call-status/{call_request_id}")
    async def call_status(
        call_request_id: UUID,
        CallStatus: str = Form(""),
        CallDuration: Optional[int] = Form(None),
        db: Session = Depends(get_db),
    ):
        """Webhook for borrower call status updates"""
        service = ClickToCallService(db)
        service.handle_call_status(call_request_id, CallStatus, CallDuration)

        return {"received": True}

    @router.post("/lo-call-status/{call_request_id}")
    async def lo_call_status(
        call_request_id: UUID,
        CallStatus: str = Form(""),
        CallDuration: Optional[int] = Form(None),
        db: Session = Depends(get_db),
    ):
        """
        Webhook for LO call status updates.

        Handles no-answer/busy/failed to offer borrower scheduling.
        """
        service = ClickToCallService(db)

        # Handle LO not answering
        if CallStatus in ["no-answer", "busy", "failed"]:
            service.handle_lo_unavailable(call_request_id, CallStatus)
        else:
            service.handle_call_status(call_request_id, CallStatus, CallDuration)

        return {"received": True}

    @router.post("/conference-status/{call_request_id}")
    async def conference_status(
        call_request_id: UUID,
        StatusCallbackEvent: str = Form(""),
        FriendlyName: str = Form(""),
        db: Session = Depends(get_db),
    ):
        """Webhook for conference status updates"""
        logger.info(f"Conference {call_request_id} ({FriendlyName}): {StatusCallbackEvent}")

        # Track when conference ends for call duration
        if StatusCallbackEvent == "conference-end":
            call_request = db.query(CallRequest).filter(
                CallRequest.id == call_request_id
            ).first()
            if call_request and call_request.connected_at:
                duration = int((datetime.now(timezone.utc) - call_request.connected_at).total_seconds())
                call_request.call_duration_seconds = duration
                call_request.status = CallStatus.COMPLETED.value
                call_request.ended_at = datetime.now(timezone.utc)
                db.commit()

        return {"received": True}

    @router.post("/initiate/{call_request_id}")
    async def initiate_call(
        call_request_id: UUID,
        db: Session = Depends(get_db),
    ):
        """
        Endpoint to initiate a click-to-call.

        Called by frontend when user clicks "Call Now" CTA.
        """
        service = ClickToCallService(db)
        result = service.initiate_call(call_request_id)

        if not result.get("success"):
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=result.get("error"))

        return result

    return router


# Export the router factory
twilio_router = create_twilio_routes()
