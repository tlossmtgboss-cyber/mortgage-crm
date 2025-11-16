"""
Vapi AI Service - API Client and Business Logic
Handles all Vapi API interactions and CRM integration
"""
import httpx
import os
from typing import Optional, Dict, List, Any
from datetime import datetime
from sqlalchemy.orm import Session
from vapi_models import VapiCall, VapiCallNote, VapiAssistant, VapiPhoneNumber
from ai_receptionist_dashboard_models import AIReceptionistActivity, AIReceptionistConversation
import logging
import uuid

logger = logging.getLogger(__name__)


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
        voice_id: str = "jennifer-playht",
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
                    "provider": "playht",
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
        vapi_call.vapi_raw_data = call_data

        # Extract transcript
        transcript_parts = []
        for message in call_data.get("messages", []):
            role = message.get("role")
            content = message.get("content") or message.get("message", "")
            if content:
                transcript_parts.append(f"{role.upper()}: {content}")

        vapi_call.transcript = "\n".join(transcript_parts)

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

        self.db.commit()
        self.db.refresh(vapi_call)

        return vapi_call

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
            from main import Lead  # Import your CRM Lead model

            # Check if lead exists with this phone number
            lead = self.db.query(Lead).filter(
                Lead.phone == vapi_call.phone_number
            ).first()

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

            vapi_call.lead_id = lead.id

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
            activity = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=vapi_call.ended_at or datetime.now(),
                client_phone=vapi_call.phone_number,
                client_name=vapi_call.caller_name,
                action_type='incoming_call',
                channel='voice',
                message_in=f"Incoming call from {vapi_call.caller_name or vapi_call.phone_number}",
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
        except:
            return None

    async def create_outbound_call(
        self,
        lead_id: int,
        assistant_id: str,
        purpose: str = "follow_up"
    ) -> VapiCall:
        """Initiate outbound call to a lead"""
        try:
            from main import Lead

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
            from main import Lead
            from vapi_models import StaffAvailability

            # Clean and format phone number
            cleaned_phone = ''.join(filter(str.isdigit, phone_number))
            if len(cleaned_phone) >= 10:
                cleaned_phone = cleaned_phone[-10:]  # Last 10 digits

            # 1. Check for existing lead
            lead = self.db.query(Lead).filter(
                Lead.phone.contains(cleaned_phone)
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
                "error": str(e),
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
            from main import User
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
                    staff.last_call_at = datetime.utcnow()
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
                "error": str(e)
            }
