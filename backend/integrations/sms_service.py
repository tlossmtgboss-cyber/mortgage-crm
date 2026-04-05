"""
SMS Service - Comprehensive Mortgage SMS Orchestrator
Integrated with Compliance Gate, Rate Limiter, Scheduler, and Analytics.
"""
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from .sms_compliance_gate import check_sms_compliance, handle_inbound_keyword
from .sms_rate_limiter import check_rate_limit, record_send_attempt
from .sms_scheduler import schedule_sms
from .sms_key_vault import get_active_telnyx_config
from .sms_delivery_tracker import record_message_sent
from .sms_template_engine import render_builtin

logger = logging.getLogger(__name__)


class SMSClient:
    """Enterprise-grade SMS Client with built-in compliance and routing."""

    def __init__(self, db: Session = None, user_id: Optional[int] = None):
        self.db = db
        self.user_id = user_id
        self.provider = "telnyx"
        self.enabled = False

        # Load credentials: prefer DB-stored (per-user), fall back to env vars
        config = get_active_telnyx_config(db, user_id=user_id) if db else {}
        self._api_key = config.get("api_key") or os.getenv("TELNYX_API_KEY", "")
        self.from_number = config.get("phone_number") or os.getenv("TELNYX_PHONE_NUMBER", "")
        self.profile_id = config.get("messaging_profile_id") or os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

        if self._api_key and self.from_number:
            self.enabled = True
        else:
            logger.warning("SMS Client initialized without full credentials")

    async def send_sms(
        self,
        to_phone: str,
        message: str,
        lead_id: Optional[int] = None,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        bypass_compliance: bool = False,
        schedule_at: Optional[datetime] = None,
        media_urls: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Send SMS/MMS with full compliance and rate limiting stack.
        Pass media_urls (list of public URLs) to send MMS via Telnyx.
        """
        if not self.enabled:
            return {"success": False, "error": "Client not configured"}

        # Use instance user_id as fallback
        user_id = user_id or self.user_id

        # 1. Compliance Gate (TCPA/DNC/Quiet Hours) — tenant-scoped
        if not bypass_compliance and self.db:
            compliance = check_sms_compliance(
                self.db, to_phone, message,
                lead_id=lead_id, user_id=user_id,
                organization_id=organization_id,
            )
            if not compliance.allowed:
                return {"success": False, "error": f"Compliance Block: {compliance.reason}"}

        # 2. Rate Limiting
        if self.db:
            rate_allowed, rate_reason = check_rate_limit(self.db, to_phone, user_id=user_id, lead_id=lead_id)
            if not rate_allowed:
                return {"success": False, "error": f"Rate limit: {rate_reason}"}

        # 3. Scheduling
        if schedule_at and self.db:
            job_id = schedule_sms(self.db, to_phone, message, schedule_at, lead_id)
            return {"success": True, "status": "scheduled", "job_id": job_id}

        # 4. Actual Transmission (via Telnyx)
        try:
            import requests
            payload = {
                "from": self.from_number,
                "to": to_phone,
                "text": message,
                "messaging_profile_id": self.profile_id,
            }
            # MMS: include media URLs for Telnyx to fetch and attach
            if media_urls:
                payload["media_urls"] = media_urls

            response = requests.post(
                "https://api.telnyx.com/v2/messages",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10
            )

            if response.status_code in (200, 201, 202):
                data = response.json()
                msg_id = data.get("data", {}).get("id")

                # 5. Delivery Tracking & Rate limit recording
                if self.db:
                    record_message_sent(
                        self.db, msg_id, to_phone, self.from_number,
                        message, lead_id=lead_id, user_id=user_id,
                    )
                    record_send_attempt(self.db, to_phone, user_id=user_id, lead_id=lead_id)

                return {"success": True, "message_id": msg_id}
            else:
                # Sanitize error — don't leak Telnyx response details to caller
                logger.error(f"Telnyx send failed ({response.status_code}): {response.text[:200]}")
                return {"success": False, "error": "SMS delivery failed"}

        except Exception as e:
            logger.error(f"Transmission error: {e}")
            return {"success": False, "error": "SMS transmission error"}

    async def send_templated_sms(
        self,
        to_phone: str,
        template_name: str,
        context: Dict[str, Any],
        lead_id: Optional[int] = None,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
    ):
        """Render a built-in mortgage template and send."""
        message = render_builtin(template_name, context)
        if not message:
            return {"success": False, "error": f"Template '{template_name}' not found"}
        return await self.send_sms(
            to_phone, message, lead_id=lead_id,
            user_id=user_id, organization_id=organization_id,
        )

# Global helper
async def send_quick_sms(to: str, msg: str, db: Session, user_id: Optional[int] = None):
    client = SMSClient(db, user_id=user_id)
    return await client.send_sms(to, msg)


def get_sms_client(db: Session = None, user_id: Optional[int] = None) -> SMSClient:
    """Factory function to create SMS client with proper configuration."""
    return SMSClient(db=db, user_id=user_id)


def check_sms_configuration() -> Dict[str, Any]:
    """Check SMS configuration and return diagnostic information."""
    api_key = os.getenv("TELNYX_API_KEY", "")
    phone_number = os.getenv("TELNYX_PHONE_NUMBER", "")
    messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")
    
    issues = []
    if not api_key:
        issues.append("TELNYX_API_KEY environment variable not set")
    if not phone_number:
        issues.append("TELNYX_PHONE_NUMBER environment variable not set")
    if not messaging_profile_id:
        issues.append("TELNYX_MESSAGING_PROFILE_ID environment variable not set")
    
    return {
        "enabled": len(issues) == 0,
        "api_key_set": bool(api_key),
        "phone_number": phone_number if phone_number else "Not set",
        "messaging_profile_set": bool(messaging_profile_id),
        "issues": issues,
        "setup_instructions": [
            "1. Sign up at https://telnyx.com/sign-up",
            "2. Get API key from https://portal.telnyx.com/#/app/api-keys",
            "3. Purchase a phone number in your Telnyx portal",
            "4. Create a messaging profile in https://portal.telnyx.com/#/app/messaging",
            "5. Update your .env file with the credentials"
        ] if issues else []
    }


class SMSTemplates:
    """Common SMS message templates for mortgage CRM workflows."""
    
    @staticmethod
    def welcome_message(client_name: str, loan_officer_name: str) -> str:
        return f"Hi {client_name}! Welcome to our mortgage process. I'm {loan_officer_name} and I'll be helping you every step of the way. Feel free to reply with any questions!"
    
    @staticmethod
    def document_request(client_name: str, documents: str) -> str:
        return f"Hi {client_name}, we need the following documents for your loan: {documents}. Please upload them to your secure portal or reply to this message. Thanks!"
    
    @staticmethod
    def status_update(client_name: str, status: str) -> str:
        return f"Hi {client_name}, your loan status has been updated to: {status}. We'll keep you informed of any changes. Contact us with questions!"
    
    @staticmethod
    def appointment_reminder(client_name: str, appointment_time: str) -> str:
        return f"Hi {client_name}, reminder: You have an appointment scheduled for {appointment_time}. Reply CONFIRM to confirm or RESCHEDULE if you need to change it."
    
    @staticmethod
    def task_created(client_name: str, task_description: str) -> str:
        return f"Hi {client_name}, we've created a new task for you: {task_description}. Check your portal for details or reply with questions."
    
    @staticmethod
    def closing_congratulations(client_name: str) -> str:
        return f"Congratulations {client_name}! Your loan has been funded and you're now a homeowner! Thank you for choosing us for your mortgage needs."
