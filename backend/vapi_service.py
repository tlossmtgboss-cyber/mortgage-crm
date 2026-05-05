"""
Vapi AI Service - API Client and Business Logic
Handles all Vapi API interactions and CRM integration
Enhanced with AI Receptionist SMS capabilities
"""
import hmac
import hashlib
import httpx
import os
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from vapi_models import VapiCall, VapiCallNote, VapiAssistant, VapiPhoneNumber
from ai_receptionist_dashboard_models import AIReceptionistActivity, AIReceptionistConversation
import logging
import uuid

logger = logging.getLogger(__name__)

# Call Intelligence Integration
try:
    from services.call_intelligence.integration import (
        handle_vapi_call_ended,
        CallIntelligenceIntegration,
    )
    CALL_INTELLIGENCE_ENABLED = True
except ImportError:
    CALL_INTELLIGENCE_ENABLED = False
    handle_vapi_call_ended = None


# =============================================================================
# AI RECEPTIONIST SMS SERVICE
# =============================================================================

class AIReceptionistSMSService:
    """
    SMS service for AI Receptionist follow-ups and two-way messaging.

    Features:
    - Post-call SMS follow-ups (appointment confirmations, summaries)
    - Calendly link delivery via SMS
    - Two-way SMS handling with AI-powered responses
    """

    def __init__(self, db: Session):
        self.db = db
        self._sms_client = None
        self._calendly_link = os.getenv("CALENDLY_LINK", "https://calendly.com/timloss/discovery-call")
        self._business_name = os.getenv("BUSINESS_NAME", "CMG Home Loans")
        self._lo_name = os.getenv("LO_NAME", "Tim")

    def _get_sms_client(self):
        """Lazy load SMS client (Telnyx)."""
        if self._sms_client is None:
            try:
                from integrations.sms_service import get_sms_client
                self._sms_client = get_sms_client(db=self.db)
            except Exception as e:
                logger.error(f"Failed to initialize SMS client: {e}")
                return None
        return self._sms_client

    # Backward-compatible alias
    _get_twilio_client = _get_sms_client

    async def send_post_call_followup(
        self,
        phone_number: str,
        caller_name: Optional[str],
        call_summary: Optional[str],
        appointment_scheduled: bool = False,
        appointment_time: Optional[str] = None,
        include_calendly: bool = False
    ) -> Dict[str, Any]:
        """
        Send post-call SMS follow-up to caller.

        Args:
            phone_number: Caller's phone number (E.164 format)
            caller_name: Caller's name if known
            call_summary: Brief summary of the call
            appointment_scheduled: Whether an appointment was scheduled
            appointment_time: Scheduled appointment time if any
            include_calendly: Whether to include Calendly link

        Returns:
            Result dict with success status and message SID
        """
        # TCPA compliance gate — check DNC, consent, and contact hours
        try:
            from services.sms_compliance import check_sms_consent
            can_send, reason = check_sms_consent(phone_number, db=self.db)
            if not can_send:
                logger.warning("Post-call followup SMS blocked by compliance for %s: %s", phone_number[-4:], reason)
                return {"success": False, "error": f"Compliance block: {reason}"}
        except Exception as e:
            logger.error("SMS compliance check failed for %s: %s — blocking send (fail-closed)", phone_number[-4:], e)
            return {"success": False, "error": "Compliance check unavailable"}

        client = self._get_sms_client()
        if not client:
            return {"success": False, "error": "SMS service unavailable"}

        # Build personalized message
        greeting = f"Hi {caller_name}!" if caller_name else "Hi!"

        if appointment_scheduled and appointment_time:
            # Appointment confirmation message
            message = f"""{greeting} Thanks for calling {self._business_name}. Your appointment is confirmed for {appointment_time}. We look forward to speaking with you!

If you need to reschedule: {self._calendly_link}

Questions? Reply to this text or call us back.
- {self._lo_name} at {self._business_name}"""
        elif include_calendly:
            # Follow-up with Calendly link
            message = f"""{greeting} Thanks for calling {self._business_name}! Here's the link to schedule a consultation at your convenience:

{self._calendly_link}

We're looking forward to helping you with your mortgage needs!
- {self._lo_name} at {self._business_name}"""
        else:
            # General follow-up
            message = f"""{greeting} Thanks for calling {self._business_name}! We appreciate you reaching out.

If you'd like to schedule a time to discuss your mortgage needs, here's our booking link:
{self._calendly_link}

Or just reply to this text with any questions!
- {self._lo_name} at {self._business_name}"""

        try:
            send_result = client.send_sms(
                to_phone=phone_number,
                message=message
            )
            message_sid = send_result.get("message_id") if isinstance(send_result, dict) else send_result

            if send_result.get("success") if isinstance(send_result, dict) else message_sid:
                # Log to activity feed
                await self._log_sms_activity(
                    phone_number=phone_number,
                    caller_name=caller_name,
                    message_type="post_call_followup",
                    message_content=message,
                    message_sid=message_sid
                )

                logger.info(f"Post-call SMS sent. SID: {message_sid}")
                return {
                    "success": True,
                    "message_sid": message_sid,
                    "message_type": "post_call_followup"
                }
            else:
                return {"success": False, "error": "Failed to send SMS"}

        except Exception as e:
            logger.error(f"Error sending post-call SMS: {e}")
            return {"success": False, "error": "Internal server error"}

    async def send_calendly_link(
        self,
        phone_number: str,
        caller_name: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send Calendly booking link via SMS.

        Args:
            phone_number: Recipient phone number
            caller_name: Optional name for personalization
            context: Optional context (e.g., "pre-approval", "refinance")

        Returns:
            Result dict with success status
        """
        # TCPA compliance gate — check DNC, consent, and contact hours
        try:
            from services.sms_compliance import check_sms_consent
            can_send, reason = check_sms_consent(phone_number, db=self.db)
            if not can_send:
                logger.warning("Calendly SMS blocked by compliance for %s: %s", phone_number[-4:], reason)
                return {"success": False, "error": f"Compliance block: {reason}"}
        except Exception as e:
            logger.error("SMS compliance check failed for %s: %s — blocking send (fail-closed)", phone_number[-4:], e)
            return {"success": False, "error": "Compliance check unavailable"}

        client = self._get_sms_client()
        if not client:
            return {"success": False, "error": "SMS service unavailable"}

        greeting = f"Hi {caller_name}!" if caller_name else "Hi!"

        if context:
            message = f"""{greeting} Here's the link to schedule your {context} consultation:

{self._calendly_link}

Pick a time that works best for you. We're looking forward to it!
- {self._lo_name} at {self._business_name}"""
        else:
            message = f"""{greeting} Here's the link to schedule your consultation:

{self._calendly_link}

Pick a time that works best for you!
- {self._lo_name} at {self._business_name}"""

        try:
            send_result = client.send_sms(
                to_phone=phone_number,
                message=message
            )
            message_sid = send_result.get("message_id") if isinstance(send_result, dict) else send_result

            if send_result.get("success") if isinstance(send_result, dict) else message_sid:
                await self._log_sms_activity(
                    phone_number=phone_number,
                    caller_name=caller_name,
                    message_type="calendly_link",
                    message_content=message,
                    message_sid=message_sid
                )

                logger.info(f"Calendly link SMS sent. SID: {message_sid}")
                return {
                    "success": True,
                    "message_sid": message_sid,
                    "calendly_link": self._calendly_link
                }
            else:
                return {"success": False, "error": "Failed to send SMS"}

        except Exception as e:
            logger.error(f"Error sending Calendly SMS: {e}")
            return {"success": False, "error": "Internal server error"}

    async def send_appointment_confirmation(
        self,
        phone_number: str,
        caller_name: Optional[str],
        appointment_time: str,
        appointment_type: str = "consultation"
    ) -> Dict[str, Any]:
        """
        Send appointment confirmation SMS.

        Args:
            phone_number: Recipient phone number
            caller_name: Caller's name
            appointment_time: Formatted appointment time
            appointment_type: Type of appointment (consultation, pre-approval, etc.)

        Returns:
            Result dict with success status
        """
        client = self._get_sms_client()
        if not client:
            return {"success": False, "error": "SMS service unavailable"}

        greeting = f"Hi {caller_name}!" if caller_name else "Hi!"

        message = f"""{greeting} Your {appointment_type} is confirmed!

Date/Time: {appointment_time}

Need to reschedule? {self._calendly_link}

We'll call you at this number at the scheduled time.
- {self._lo_name} at {self._business_name}"""

        try:
            send_result = client.send_sms(
                to_phone=phone_number,
                message=message
            )
            message_sid = send_result.get("message_id") if isinstance(send_result, dict) else send_result

            if send_result.get("success") if isinstance(send_result, dict) else message_sid:
                await self._log_sms_activity(
                    phone_number=phone_number,
                    caller_name=caller_name,
                    message_type="appointment_confirmation",
                    message_content=message,
                    message_sid=message_sid
                )

                return {
                    "success": True,
                    "message_sid": message_sid,
                    "appointment_time": appointment_time
                }
            else:
                return {"success": False, "error": "Failed to send SMS"}

        except Exception as e:
            logger.error(f"Error sending appointment confirmation SMS: {e}")
            return {"success": False, "error": "Internal server error"}

    async def handle_inbound_sms(
        self,
        from_number: str,
        message_body: str,
        to_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle inbound SMS with AI-powered response.

        This integrates with the existing SMS Intelligence system for
        AI analysis and generates appropriate responses for the AI
        receptionist context.

        Args:
            from_number: Sender's phone number
            message_body: SMS content
            to_number: Number the SMS was sent to

        Returns:
            Result dict with response and analysis
        """
        try:
            # Check for opt-out keywords first
            opt_out_keywords = ["stop", "unsubscribe", "cancel", "quit", "end"]
            if message_body.strip().lower() in opt_out_keywords:
                return {
                    "success": True,
                    "is_opt_out": True,
                    "response": None,
                    "action": "opt_out_processed"
                }

            # Look up lead/contact
            lead = await self._find_lead_by_phone(from_number)

            # Analyze the message
            analysis = await self._analyze_sms_intent(message_body, lead)

            # Generate response based on intent
            response = await self._generate_ai_response(
                message_body=message_body,
                lead=lead,
                intent=analysis.get("intent"),
                sentiment=analysis.get("sentiment")
            )

            # Send response if we have one
            if response and response.get("should_respond"):
                client = self._get_sms_client()
                if client:
                    _result = client.send_sms(
                        to_phone=from_number,
                        message=response.get("message")
                    )
                    message_sid = _result.get("message_id") if isinstance(_result, dict) else _result

                    # Log the activity
                    await self._log_sms_activity(
                        phone_number=from_number,
                        caller_name=lead.name if lead else None,
                        message_type="auto_response",
                        message_content=response.get("message"),
                        message_sid=message_sid,
                        inbound_message=message_body
                    )

            return {
                "success": True,
                "lead_found": lead is not None,
                "lead_id": lead.id if lead else None,
                "analysis": analysis,
                "response_sent": response.get("should_respond", False),
                "response": response
            }

        except Exception as e:
            logger.error(f"Error handling inbound SMS: {e}")
            return {"success": False, "error": "Internal server error"}

    async def _find_lead_by_phone(self, phone_number: str):
        """Find lead by phone number."""
        try:
            from database.models import Lead
            from sqlalchemy import or_

            # Clean phone number
            cleaned = ''.join(filter(str.isdigit, phone_number))
            if len(cleaned) >= 10:
                cleaned = cleaned[-10:]

            lead = self.db.query(Lead).filter(
                or_(
                    Lead.phone == phone_number,
                    Lead.phone.contains(cleaned)
                )
            ).first()

            return lead
        except Exception as e:
            logger.error(f"Error finding lead: {e}")
            return None

    async def _analyze_sms_intent(
        self,
        message_body: str,
        lead = None
    ) -> Dict[str, Any]:
        """
        Analyze SMS intent for AI receptionist context.

        Returns intent classification relevant to mortgage inquiries.
        """
        message_lower = message_body.lower()

        # Intent patterns for mortgage context
        import re
        def _has_word(text, words):
            """Match whole words only to avoid false positives (e.g. 'erate' matching 'rate')."""
            return any(re.search(r'\b' + re.escape(w) + r'\b', text) for w in words)

        if _has_word(message_lower, ["rate", "rates", "interest", "apr"]):
            intent = "rate_inquiry"
            urgency = "medium"
        elif _has_word(message_lower, ["schedule", "appointment", "meet", "call"]):
            intent = "appointment_request"
            urgency = "high"
        elif _has_word(message_lower, ["refinance", "refi", "lower payment"]):
            intent = "refinance_inquiry"
            urgency = "medium"
        elif _has_word(message_lower, ["pre-approval", "preapproval", "qualify", "approved"]):
            intent = "preapproval_inquiry"
            urgency = "high"
        elif _has_word(message_lower, ["document", "paperwork", "upload", "send"]):
            intent = "document_inquiry"
            urgency = "medium"
        elif _has_word(message_lower, ["status", "update", "where", "loan"]):
            intent = "status_inquiry"
            urgency = "medium"
        elif any(word in message_lower for word in ["yes", "ok", "sure", "great", "sounds good"]):
            intent = "affirmative"
            urgency = "low"
        elif any(word in message_lower for word in ["no", "not interested", "later"]):
            intent = "negative"
            urgency = "low"
        elif any(word in message_lower for word in ["help", "question", "?"]):
            intent = "general_inquiry"
            urgency = "medium"
        else:
            intent = "unknown"
            urgency = "low"

        # Simple sentiment detection
        positive_words = ["thanks", "great", "excellent", "good", "happy", "appreciate"]
        negative_words = ["frustrated", "angry", "upset", "bad", "terrible", "disappointed"]

        if any(word in message_lower for word in positive_words):
            sentiment = "positive"
        elif any(word in message_lower for word in negative_words):
            sentiment = "negative"
        else:
            sentiment = "neutral"

        return {
            "intent": intent,
            "urgency": urgency,
            "sentiment": sentiment,
            "requires_human": intent in ["status_inquiry", "document_inquiry"] or sentiment == "negative"
        }

    async def _generate_ai_response(
        self,
        message_body: str,
        lead,
        intent: str,
        sentiment: str
    ) -> Dict[str, Any]:
        """
        Generate AI-powered response for the SMS.

        Returns response dict with message and whether to send it.
        """
        # Determine if we should auto-respond
        # Don't auto-respond to complex inquiries that need human attention
        auto_respond_intents = [
            "appointment_request", "rate_inquiry", "refinance_inquiry",
            "preapproval_inquiry", "affirmative", "general_inquiry"
        ]

        if intent not in auto_respond_intents:
            return {
                "should_respond": False,
                "reason": "requires_human_response",
                "intent": intent
            }

        # Generate response based on intent
        greeting = f"Hi {lead.first_name}!" if lead and lead.first_name else "Hi!"

        if intent == "appointment_request":
            message = f"""{greeting} I'd love to help you schedule a time to talk. Here's our booking link:

{self._calendly_link}

Pick a time that works for you!"""

        elif intent == "rate_inquiry":
            message = f"""{greeting} Rates change daily and depend on your specific situation. Want to schedule a quick call to discuss your options?

{self._calendly_link}"""

        elif intent == "refinance_inquiry":
            message = f"""{greeting} Great timing to look into refinancing! I can help you see if it makes sense. Schedule a quick chat:

{self._calendly_link}"""

        elif intent == "preapproval_inquiry":
            message = f"""{greeting} Getting pre-approved is a great first step! It usually takes about 24 hours. Let's get you started:

{self._calendly_link}"""

        elif intent == "affirmative":
            message = f"""{greeting} Great! Here's the link to schedule your consultation:

{self._calendly_link}

Looking forward to it!"""

        else:  # general_inquiry
            message = f"""{greeting} Thanks for reaching out! I'm here to help. Want to schedule a quick call to discuss your needs?

{self._calendly_link}

Or reply with your question and I'll get back to you!"""

        return {
            "should_respond": True,
            "message": message,
            "intent": intent
        }

    async def _log_sms_activity(
        self,
        phone_number: str,
        caller_name: Optional[str],
        message_type: str,
        message_content: str,
        message_sid: Optional[str] = None,
        inbound_message: Optional[str] = None
    ):
        """Log SMS activity to AI Receptionist dashboard."""
        try:
            activity = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                client_phone=phone_number,
                client_name=caller_name,
                action_type=f"sms_{message_type}",
                channel='sms',
                message_in=inbound_message or "",
                message_out=message_content,
                confidence_score=0.95,
                outcome_status='success',
                extra_data={
                    'message_sid': message_sid,
                    'message_type': message_type,
                    'calendly_link': self._calendly_link if 'calendly' in message_content.lower() else None
                }
            )
            self.db.add(activity)
            self.db.commit()
        except Exception as e:
            logger.error(f"Error logging SMS activity: {e}")
            # Don't fail the main operation


class VapiService:
    """Service for Vapi AI API interactions"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("VAPI_API_KEY")
        self.base_url = "https://api.vapi.ai"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def create_assistant(
        self,
        name: str,
        first_message: str,
        system_prompt: str,
        voice_id: str = "b7d50908-b17c-442d-ad8d-810c63997ed9",
        model: str = "gpt-4",
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new Vapi assistant"""
        async with httpx.AsyncClient() as client:
            payload = {
                "name": name,
                "model": {
                    "provider": "openai",
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt
                        }
                    ]
                },
                "voice": {
                    "provider": "cartesia",
                    "voiceId": voice_id
                },
                "firstMessage": first_message,
                **kwargs
            }

            response = await client.post(
                f"{self.base_url}/assistant",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def get_call(self, call_id: str) -> Dict[str, Any]:
        """Retrieve call details from Vapi"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/call/{call_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def list_calls(
        self,
        limit: int = 100,
        assistant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all calls"""
        async with httpx.AsyncClient() as client:
            params = {"limit": limit}
            if assistant_id:
                params["assistantId"] = assistant_id

            response = await client.get(
                f"{self.base_url}/call",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()

    async def create_phone_call(
        self,
        assistant_id: str,
        customer_number: str,
        customer_name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Initiate outbound call"""
        async with httpx.AsyncClient() as client:
            payload = {
                "assistantId": assistant_id,
                "customer": {
                    "number": customer_number,
                }
            }
            if customer_name:
                payload["customer"]["name"] = customer_name

            payload.update(kwargs)

            response = await client.post(
                f"{self.base_url}/call/phone",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def transfer_call(
        self,
        call_id: str,
        destination_number: str,
        whisper_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transfer an active call to another phone number
        Uses Vapi's transfer functionality with optional whisper
        """
        async with httpx.AsyncClient() as client:
            payload = {
                "destinationNumber": destination_number,
            }

            if whisper_message:
                payload["whisperMessage"] = whisper_message

            response = await client.post(
                f"{self.base_url}/call/{call_id}/transfer",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()


class VapiCRMIntegration:
    """Integrate Vapi calls with CRM data"""

    def __init__(self, db: Session):
        self.db = db
        self.vapi = VapiService()

    @staticmethod
    def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
        """
        Verify Vapi webhook signature using HMAC-SHA256.
        Returns False if no secret is configured (fail closed).

        NOTE: Prefer using ``middleware.webhook_verification.require_vapi_webhook``
        as a FastAPI dependency for new routes.  This static method is retained
        for backward compatibility with code that calls it directly.
        """
        secret = os.getenv("VAPI_WEBHOOK_SECRET")
        if not secret:
            logger.error(
                "VAPI_WEBHOOK_SECRET not configured — rejecting webhook. "
                "Set this env var to the secret from your Vapi dashboard."
            )
            return False

        if not signature_header:
            logger.warning("Missing X-Vapi-Signature header on webhook request")
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            payload_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature_header)

    async def process_call_webhook(self, webhook_data: Dict[str, Any]) -> Optional[VapiCall]:
        """
        Process incoming Vapi webhook and create/update call record
        Webhook types: assistant-request, status-update, end-of-call-report, etc.
        """
        message_type = webhook_data.get("message", {}).get("type")

        if message_type == "end-of-call-report":
            return await self._process_end_of_call(webhook_data)
        elif message_type == "status-update":
            return await self._process_status_update(webhook_data)
        elif message_type == "transcript":
            return await self._process_transcript(webhook_data)

        return None

    async def _process_end_of_call(self, data: Dict[str, Any]) -> VapiCall:
        """Process end-of-call report and extract insights"""
        call_data = data.get("message", {}).get("call", {})
        call_id = call_data.get("id")

        # Check if call already exists
        vapi_call = self.db.query(VapiCall).filter(
            VapiCall.vapi_call_id == call_id
        ).first()

        if not vapi_call:
            vapi_call = VapiCall(vapi_call_id=call_id)
            self.db.add(vapi_call)

        # Update call details
        vapi_call.phone_number = call_data.get("customer", {}).get("number")
        vapi_call.caller_name = call_data.get("customer", {}).get("name")
        vapi_call.status = call_data.get("status")
        vapi_call.started_at = self._parse_datetime(call_data.get("startedAt"))
        vapi_call.ended_at = self._parse_datetime(call_data.get("endedAt"))
        vapi_call.duration = call_data.get("duration")
        vapi_call.recording_url = call_data.get("recordingUrl")
        vapi_call.stereo_recording_url = call_data.get("stereoRecordingUrl")
        vapi_call.recording_status = "available" if call_data.get("recordingUrl") else "none"
        vapi_call.vapi_raw_data = call_data

        # Extract transcript
        transcript_parts = []
        for message in call_data.get("messages", []):
            role = message.get("role")
            content = message.get("content") or message.get("message", "")
            if content:
                transcript_parts.append(f"{role.upper()}: {content}")

        vapi_call.transcript = "\n".join(transcript_parts)
        vapi_call.transcript_status = "completed" if transcript_parts else "none"

        # Extract analysis from Vapi's analysis
        analysis = call_data.get("analysis", {})
        vapi_call.summary = analysis.get("summary")
        vapi_call.sentiment = self._extract_sentiment(analysis)

        # Auto-create lead if new phone number
        if vapi_call.phone_number and not vapi_call.lead_id:
            await self._create_or_update_lead(vapi_call)

        # Extract action items
        await self._extract_action_items(vapi_call, call_data)

        # Log to AI Receptionist Dashboard tables
        await self._log_to_dashboard(vapi_call, call_data)

        # Sync status back to VoicemailDrop if this was a voicemail drop call
        await self._sync_voicemail_drop_status(call_data, vapi_call)

        self.db.commit()
        self.db.refresh(vapi_call)

        # Process through Call Intelligence if enabled and transcript available
        if CALL_INTELLIGENCE_ENABLED and handle_vapi_call_ended and vapi_call.transcript:
            await self._process_call_intelligence(vapi_call, call_data)

        # Send post-call SMS follow-up
        await self._send_post_call_sms(vapi_call, call_data)

        return vapi_call

    async def _sync_voicemail_drop_status(
        self, call_data: Dict[str, Any], vapi_call: VapiCall
    ) -> None:
        """
        Sync call outcome back to VoicemailDrop record.

        When a voicemail drop call completes, Vapi sends the end-of-call webhook.
        This method reads the voicemail_drop_id from call metadata and updates
        the VoicemailDrop record with the final status, duration, and cost.
        """
        try:
            metadata = call_data.get("metadata", {})
            voicemail_drop_id = metadata.get("voicemail_drop_id")

            if not voicemail_drop_id or metadata.get("type") != "voicemail_drop":
                return  # Not a voicemail drop call

            from database.models import VoicemailDrop, VoicemailEvent

            try:
                drop_id_int = int(voicemail_drop_id)
            except (ValueError, TypeError):
                logger.warning(f"Malformed voicemail_drop_id in webhook: {voicemail_drop_id!r}")
                return

            drop = self.db.query(VoicemailDrop).filter(
                VoicemailDrop.id == drop_id_int
            ).first()

            if not drop:
                logger.warning(f"VoicemailDrop {voicemail_drop_id} not found for webhook sync")
                return

            # Determine final status from Vapi call data
            call_status = call_data.get("status", "")
            ended_reason = call_data.get("endedReason", "")

            # Map Vapi outcomes to VoicemailDrop status
            if ended_reason in ("voicemail", "machine-detected"):
                drop.status = "delivered"
                drop.delivered_at = datetime.now(timezone.utc)
            elif ended_reason in ("customer-answered", "assistant-ended"):
                # Human picked up — the AI delivered the message live
                drop.status = "human_answered"
                drop.delivered_at = datetime.now(timezone.utc)
            elif ended_reason in (
                "customer-busy", "customer-did-not-answer",
                "no-answer", "busy",
            ):
                drop.status = "no_voicemail"
            elif ended_reason in (
                "error", "phone-call-provider-error",
                "customer-did-not-give-microphone-permission",
            ):
                drop.status = "failed"
                drop.error_message = f"Call failed: {ended_reason}"
            elif call_status == "ended":
                # Generic ended — check if voicemail detection was triggered
                analysis = call_data.get("analysis", {})
                success_eval = analysis.get("successEvaluation")
                if success_eval is True or str(success_eval).lower() == "true":
                    drop.status = "delivered"
                    drop.delivered_at = datetime.now(timezone.utc)
                else:
                    drop.status = "failed"
                    drop.error_message = f"Call ended without confirmed delivery (successEvaluation={success_eval})"
            else:
                drop.status = "failed"
                drop.error_message = f"Unknown outcome: {call_status}/{ended_reason}"

            # Update call metadata
            if vapi_call.duration:
                drop.call_duration = vapi_call.duration
            cost = call_data.get("cost")
            if cost is not None:
                drop.call_cost = float(cost)

            # Create event for the status change
            event = VoicemailEvent(
                voicemail_drop_id=drop.id,
                event_type=drop.status,
                event_data={
                    "vapi_call_id": call_data.get("id"),
                    "ended_reason": ended_reason,
                    "duration": vapi_call.duration,
                    "cost": cost,
                }
            )
            self.db.add(event)

            logger.info(
                f"VoicemailDrop {voicemail_drop_id} synced: "
                f"status={drop.status}, reason={ended_reason}"
            )

        except Exception as e:
            logger.error(f"Error syncing voicemail drop status: {e}", exc_info=True)
            # Don't raise — this shouldn't block the main webhook processing

    async def _send_post_call_sms(self, vapi_call: VapiCall, call_data: Dict[str, Any]) -> None:
        """
        Send post-call SMS follow-up to caller.

        Determines the appropriate follow-up based on call outcome:
        - Appointment scheduled -> Send confirmation
        - Calendly mentioned -> Send Calendly link
        - General call -> Send thank you + Calendly
        """
        try:
            # Check if SMS follow-ups are enabled
            if not os.getenv("ENABLE_POST_CALL_SMS", "true").lower() == "true":
                logger.debug("Post-call SMS disabled")
                return

            # Don't send SMS for very short calls (likely missed/dropped)
            if vapi_call.duration and vapi_call.duration < 15:
                logger.debug(f"Skipping SMS for short call ({vapi_call.duration}s)")
                return

            # Don't send SMS for outbound calls (we initiated)
            if vapi_call.direction == "outbound":
                logger.debug("Skipping SMS for outbound call")
                return

            # Check if phone number is valid
            if not vapi_call.phone_number:
                logger.debug("No phone number for SMS follow-up")
                return

            # --- TCPA Consent Check ---
            # Only send SMS if we have consent from the lead/contact
            try:
                from routes.voicemail_drop_routes import check_dnc_status, check_calling_hours
                is_blocked, _ = check_dnc_status(vapi_call.phone_number, self.db)
                if is_blocked:
                    logger.info("Post-call SMS blocked by DNC")
                    return
                is_allowed, _ = check_calling_hours(vapi_call.phone_number)
                if not is_allowed:
                    logger.info("Post-call SMS blocked by calling hours")
                    return
            except ImportError:
                logger.warning("Could not import TCPA checks for post-call SMS")

            sms_service = AIReceptionistSMSService(self.db)

            # Analyze call content to determine follow-up type
            analysis = call_data.get("analysis", {})
            structured_data = analysis.get("structuredData", {})
            transcript = vapi_call.transcript or ""
            transcript_lower = transcript.lower()

            # Check if appointment was scheduled during the call
            appointment_scheduled = (
                structured_data.get("appointmentScheduled", False) or
                "appointment" in transcript_lower and any(
                    phrase in transcript_lower
                    for phrase in ["scheduled", "booked", "confirmed", "set up"]
                )
            )

            # Check if Calendly was mentioned
            calendly_mentioned = "calendly" in transcript_lower or "booking link" in transcript_lower

            # Get appointment time if scheduled
            appointment_time = structured_data.get("appointmentTime")

            # Send appropriate follow-up
            if appointment_scheduled:
                await sms_service.send_post_call_followup(
                    phone_number=vapi_call.phone_number,
                    caller_name=vapi_call.caller_name,
                    call_summary=vapi_call.summary,
                    appointment_scheduled=True,
                    appointment_time=appointment_time,
                    include_calendly=True
                )
            elif calendly_mentioned:
                # They asked about scheduling - send the Calendly link
                await sms_service.send_calendly_link(
                    phone_number=vapi_call.phone_number,
                    caller_name=vapi_call.caller_name
                )
            else:
                # General call - send thank you with Calendly
                await sms_service.send_post_call_followup(
                    phone_number=vapi_call.phone_number,
                    caller_name=vapi_call.caller_name,
                    call_summary=vapi_call.summary,
                    appointment_scheduled=False,
                    include_calendly=True
                )

            logger.info("Post-call SMS sent")

        except Exception as e:
            # Don't fail the whole process if SMS fails
            logger.error(f"Error sending post-call SMS: {e}")

    async def _process_call_intelligence(self, vapi_call: VapiCall, call_data: Dict[str, Any]) -> None:
        """
        Process call through Call Intelligence for structured data extraction.

        Extracts:
        - Borrower identity information
        - Property details
        - Employment/income data
        - Financial assets/liabilities
        - Compliance declarations
        - Loan intent/preferences

        Then runs Application Engine audit if loan_id is associated.
        """
        try:
            logger.info(f"Processing call {vapi_call.vapi_call_id} through Call Intelligence")

            # Build call_data format expected by integration
            vapi_format_data = {
                "messages": call_data.get("messages", []),
                "assistant": {
                    "id": call_data.get("assistantId"),
                    "metadata": {
                        "loan_id": vapi_call.loan_id,
                        "organization_id": getattr(vapi_call, 'organization_id', None) or 1,
                    }
                },
                "duration": vapi_call.duration,
            }

            # Call the integration handler
            ci_result = await handle_vapi_call_ended(
                db=self.db,
                call_id=vapi_call.vapi_call_id,
                call_data=vapi_format_data,
            )

            if ci_result.get("success"):
                logger.info(
                    f"Call Intelligence processed {vapi_call.vapi_call_id}: "
                    f"{ci_result.get('extractions_count', 0)} extractions, "
                    f"{ci_result.get('tasks_created', 0)} tasks created"
                )

                # Update VapiCall with CI processing status
                vapi_call.ci_processed = True
                vapi_call.ci_extractions_count = ci_result.get('extractions_count', 0)
                vapi_call.ci_tasks_created = ci_result.get('tasks_created', 0)
                self.db.commit()
            else:
                logger.warning(
                    f"Call Intelligence processing failed for {vapi_call.vapi_call_id}: "
                    f"{ci_result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            # Don't fail the whole process if CI fails
            logger.exception(f"Call Intelligence error for {vapi_call.vapi_call_id}: {e}")

    async def _process_status_update(self, data: Dict[str, Any]) -> Optional[VapiCall]:
        """Process real-time status updates"""
        call_data = data.get("message", {})
        call_id = call_data.get("call", {}).get("id")
        status = call_data.get("status")

        vapi_call = self.db.query(VapiCall).filter(
            VapiCall.vapi_call_id == call_id
        ).first()

        if vapi_call:
            vapi_call.status = status
            self.db.commit()
            self.db.refresh(vapi_call)

        return vapi_call

    async def _process_transcript(self, data: Dict[str, Any]) -> None:
        """Process real-time transcript updates"""
        # Can be used for live transcription display
        pass

    async def _create_or_update_lead(self, vapi_call: VapiCall) -> None:
        """Create or update lead from call data"""
        try:
            from database.models import Lead

            # Check if lead exists with this phone number
            lead = self.db.query(Lead).filter(
                Lead.phone == vapi_call.phone_number
            ).first()

            was_new_lead = False
            if not lead:
                # Create new lead
                lead = Lead(
                    first_name=vapi_call.caller_name or "Unknown",
                    phone=vapi_call.phone_number,
                    source="vapi_call",
                    status="new"
                )
                self.db.add(lead)
                self.db.flush()

                from services.client_file_service import ensure_client_file
                ensure_client_file(self.db, lead)

                was_new_lead = True

            vapi_call.lead_id = lead.id

            # Log new lead creation to dashboard
            if was_new_lead:
                lead_activity = AIReceptionistActivity(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now(),
                    client_phone=vapi_call.phone_number,
                    client_name=vapi_call.caller_name,
                    action_type='lead_captured',
                    channel='voice',
                    message_in="New lead identified from call",
                    message_out=f"Lead created: {vapi_call.caller_name or vapi_call.phone_number}",
                    confidence_score=0.9,
                    outcome_status='success',
                    extra_data={
                        'lead_id': lead.id,
                        'vapi_call_id': vapi_call.vapi_call_id,
                        'source': 'vapi_call'
                    }
                )
                self.db.add(lead_activity)

        except Exception as e:
            logger.error(f"Error creating/updating lead: {e}")

    async def _extract_action_items(self, vapi_call: VapiCall, call_data: Dict) -> None:
        """Extract action items from call analysis"""
        analysis = call_data.get("analysis", {})

        # Vapi's structured data extraction
        structured_data = analysis.get("structuredData", {})
        action_items = structured_data.get("actionItems", [])

        for item in action_items:
            note = VapiCallNote(
                call_id=vapi_call.id,
                note_type="action_item",
                content=item.get("description"),
                priority=item.get("priority", "medium")
            )
            self.db.add(note)

        # Extract appointment requests
        summary = vapi_call.summary or ""
        if "appointment" in summary.lower():
            note = VapiCallNote(
                call_id=vapi_call.id,
                note_type="appointment_request",
                content="Customer requested appointment scheduling",
                priority="high"
            )
            self.db.add(note)

    async def _log_to_dashboard(self, vapi_call: VapiCall, call_data: Dict) -> None:
        """Log call to AI Receptionist Dashboard tables"""
        try:
            # Create conversation record
            conversation = AIReceptionistConversation(
                id=str(uuid.uuid4()),
                started_at=vapi_call.started_at,
                ended_at=vapi_call.ended_at,
                duration_seconds=vapi_call.duration,
                client_phone=vapi_call.phone_number,
                client_name=vapi_call.caller_name,
                channel='voice',
                full_transcript=vapi_call.transcript or "",
                summary=vapi_call.summary or "",
                sentiment=vapi_call.sentiment or "neutral",
                ai_confidence=0.9,  # Default high confidence for VAPI calls
                outcome_status='completed' if vapi_call.status == 'ended' else 'failed',
                recording_url=vapi_call.recording_url,
                extra_data={
                    'vapi_call_id': vapi_call.vapi_call_id,
                    'analysis': call_data.get('analysis', {})
                }
            )
            self.db.add(conversation)
            self.db.flush()  # Get the conversation ID

            # Create activity feed record
            # Determine action type based on call direction
            action_type = 'outbound_call' if vapi_call.direction == 'outbound' else 'incoming_call'
            message_prefix = "Outbound call to" if vapi_call.direction == 'outbound' else "Incoming call from"

            activity = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=vapi_call.ended_at or datetime.now(),
                client_phone=vapi_call.phone_number,
                client_name=vapi_call.caller_name,
                action_type=action_type,
                channel='voice',
                message_in=f"{message_prefix} {vapi_call.caller_name or vapi_call.phone_number}",
                message_out=vapi_call.summary or "Call completed",
                confidence_score=0.9,
                outcome_status='success' if vapi_call.status == 'ended' else 'failed',
                conversation_id=conversation.id,
                transcript_url=vapi_call.recording_url,
                extra_data={
                    'vapi_call_id': vapi_call.vapi_call_id,
                    'duration': vapi_call.duration,
                    'sentiment': vapi_call.sentiment
                }
            )
            self.db.add(activity)

            logger.info(f"Logged call {vapi_call.vapi_call_id} to dashboard")

        except Exception as e:
            logger.error(f"Error logging to dashboard: {e}")
            # Don't fail the whole process if dashboard logging fails

    def _extract_sentiment(self, analysis: Dict) -> str:
        """Extract sentiment from Vapi analysis"""
        sentiment_score = analysis.get("sentiment", 0)
        if sentiment_score > 0.3:
            return "positive"
        elif sentiment_score < -0.3:
            return "negative"
        return "neutral"

    def _parse_datetime(self, dt_string: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string"""
        if not dt_string:
            return None
        try:
            return datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning(f"Error parsing datetime string '{dt_string}': {e}")
            return None

    async def create_outbound_call(
        self,
        lead_id: int,
        assistant_id: str,
        purpose: str = "follow_up"
    ) -> VapiCall:
        """Initiate outbound call to a lead"""
        try:
            from database.models import Lead

            lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead or not lead.phone:
                raise ValueError("Lead not found or has no phone number")

            # Create call via Vapi API
            call_response = await self.vapi.create_phone_call(
                assistant_id=assistant_id,
                customer_number=lead.phone,
                customer_name=f"{lead.first_name} {lead.last_name}",
                metadata={"lead_id": lead_id, "purpose": purpose}
            )

            # Create call record
            vapi_call = VapiCall(
                vapi_call_id=call_response.get("id"),
                phone_number=lead.phone,
                caller_name=f"{lead.first_name} {lead.last_name}",
                direction="outbound",
                status="initiated",
                lead_id=lead_id,
                vapi_raw_data=call_response
            )

            self.db.add(vapi_call)
            self.db.commit()
            self.db.refresh(vapi_call)

            return vapi_call

        except Exception as e:
            logger.error(f"Error creating outbound call: {e}")
            raise

    async def identify_caller(self, phone_number: str) -> Dict[str, Any]:
        """
        Comprehensive caller identification and routing recommendation
        Returns: caller type, loan status, assigned team members, routing suggestion
        """
        try:
            from database.models import Lead
            from vapi_models import StaffAvailability

            # Clean and format phone number
            cleaned_phone = ''.join(filter(str.isdigit, phone_number))
            if len(cleaned_phone) >= 10:
                cleaned_phone = cleaned_phone[-10:]  # Last 10 digits

            # 1. Check for existing lead
            lead = self.db.query(Lead).filter(
                Lead.phone.ilike(f"%{cleaned_phone}")
            ).first()

            # 2. Check for active loans (if you have a Loan model)
            # For now, we'll check lead stage
            if lead:
                # Determine caller type based on lead stage
                caller_type = "new_lead"
                if lead.stage in ["Application Started", "Application Complete", "Pre-Approved"]:
                    caller_type = "active_loan"
                elif lead.stage in ["Prospect", "Attempted Contact"]:
                    caller_type = "prospect"
                else:
                    caller_type = "existing_client"

                # Get assigned team members
                production_assistant = None
                if lead.owner_id:
                    # Check if owner is a PA or LO
                    owner_availability = self.db.query(StaffAvailability).filter(
                        StaffAvailability.user_id == lead.owner_id
                    ).first()

                    if owner_availability:
                        production_assistant = {
                            "user_id": owner_availability.user_id,
                            "role": owner_availability.role,
                            "phone": owner_availability.primary_phone,
                            "available": owner_availability.available_for_calls,
                            "status": owner_availability.status
                        }

                return {
                    "found": True,
                    "caller_type": caller_type,
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "lead_stage": lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage),
                    "lead_source": lead.source,
                    "assigned_owner_id": lead.owner_id,
                    "production_assistant": production_assistant,
                    "routing_recommendation": "transfer_to_production_assistant",
                    "context": f"Existing {caller_type}: {lead.name}, Stage: {lead.stage}"
                }
            else:
                # New caller - no existing record
                return {
                    "found": False,
                    "caller_type": "new_prospect",
                    "routing_recommendation": "collect_info_and_transfer_to_pa",
                    "context": "New caller - no existing record found"
                }

        except Exception as e:
            logger.error(f"Error identifying caller: {e}")
            return {
                "found": False,
                "error": "Internal server error",
                "caller_type": "unknown",
                "routing_recommendation": "transfer_to_production_assistant"
            }

    async def transfer_call_with_whisper(
        self,
        vapi_call_id: str,
        recipient_user_id: int,
        recipient_role: str,
        whisper_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute call transfer with whisper message to recipient
        Creates routing log and handles transfer via Vapi API
        """
        try:
            from database.models import User
            from vapi_models import CallRoutingLog, StaffAvailability, VapiCall

            # 1. Get recipient's availability and phone number
            staff = self.db.query(StaffAvailability).filter(
                StaffAvailability.user_id == recipient_user_id
            ).first()

            if not staff:
                # Fallback: get user info directly
                user = self.db.query(User).filter(User.id == recipient_user_id).first()
                if not user:
                    return {
                        "success": False,
                        "reason": "recipient_not_found",
                        "fallback_action": "create_task"
                    }

                # Check if user has phone in metadata
                recipient_phone = user.user_metadata.get("phone") if user.user_metadata else None
                if not recipient_phone:
                    return {
                        "success": False,
                        "reason": "no_phone_number",
                        "fallback_action": "create_task"
                    }

                staff_available = True
                staff_status = "unknown"
            else:
                recipient_phone = staff.primary_phone
                staff_available = staff.available_for_calls and staff.status == 'available'
                staff_status = staff.status

            # 2. Check availability
            if not staff_available:
                return {
                    "success": False,
                    "reason": "recipient_unavailable",
                    "status": staff_status,
                    "fallback_action": "offer_voicemail_or_schedule"
                }

            # 3. Format whisper message
            whisper_message = f"""Transferring call from {whisper_data.get('caller_name', 'Unknown')} at {whisper_data.get('caller_phone', 'Unknown number')}.
Reason: {whisper_data.get('reason', 'General inquiry')}.
Status: {whisper_data.get('caller_type', 'Unknown')}.
{whisper_data.get('additional_context', '')}"""

            # 4. Get or create VapiCall record
            vapi_call = self.db.query(VapiCall).filter(
                VapiCall.vapi_call_id == vapi_call_id
            ).first()

            call_db_id = vapi_call.id if vapi_call else None

            # 5. Log routing decision
            routing_log = CallRoutingLog(
                call_id=call_db_id,
                vapi_call_id=vapi_call_id,
                routing_decision=f"transfer_to_{recipient_role}",
                caller_type=whisper_data.get('caller_type'),
                routed_to_user_id=recipient_user_id,
                routed_to_role=recipient_role,
                routed_to_phone=recipient_phone,
                whisper_message=whisper_message,
                caller_phone=whisper_data.get('caller_phone'),
                caller_name=whisper_data.get('caller_name'),
                call_reason=whisper_data.get('reason'),
                urgency_level=whisper_data.get('urgency_level', 'medium')
            )
            self.db.add(routing_log)
            self.db.flush()

            # 6. Execute Vapi transfer with whisper
            try:
                vapi_response = await self.vapi.transfer_call(
                    call_id=vapi_call_id,
                    destination_number=recipient_phone,
                    whisper_message=whisper_message
                )

                # Update routing log with success
                routing_log.transfer_successful = True
                self.db.commit()

                # Update staff call count
                if staff:
                    staff.current_call_count += 1
                    staff.last_call_at = datetime.now(timezone.utc)
                    self.db.commit()

                return {
                    "success": True,
                    "transferred_to": f"{recipient_role} (User ID: {recipient_user_id})",
                    "transfer_id": vapi_response.get('id'),
                    "routing_log_id": routing_log.id
                }

            except Exception as transfer_error:
                # Log transfer failure
                routing_log.transfer_successful = False
                routing_log.transfer_error = str(transfer_error)
                self.db.commit()

                logger.error(f"Transfer failed: {transfer_error}")
                return {
                    "success": False,
                    "reason": "transfer_failed",
                    "error": str(transfer_error),
                    "fallback_action": "create_task"
                }

        except Exception as e:
            logger.error(f"Error in transfer_call_with_whisper: {e}")
            self.db.rollback()
            return {
                "success": False,
                "reason": "system_error",
                "error": "Internal server error"
            }
