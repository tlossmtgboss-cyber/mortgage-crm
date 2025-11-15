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
import logging

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
