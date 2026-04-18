"""
SMS Service - Comprehensive Mortgage SMS Orchestrator
Integrated with Compliance Gate, Rate Limiter, Scheduler, and Analytics.
"""
import os
import re
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

from telephony.phone_utils import normalize_phone as _to_e164

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
        # Clean session after credential lookup (sms_credentials table may not exist)
        if db:
            try:
                db.rollback()
            except Exception:
                pass
        self._api_key = config.get("api_key") or os.getenv("TELNYX_API_KEY", "")
        self.from_number = config.get("phone_number") or os.getenv("TELNYX_PHONE_NUMBER", "")
        self.profile_id = config.get("messaging_profile_id") or os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

        if self._api_key and self.from_number:
            self.enabled = True
        else:
            logger.warning(
                "SMS Client not configured: api_key=%s from=%s",
                bool(self._api_key), self.from_number or "(empty)",
            )

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

        # Normalize to E.164 — Telnyx rejects raw formats like "(925) 389-6782"
        normalized_phone = _to_e164(to_phone)
        if not normalized_phone:
            return {"success": False, "error": f"Invalid phone number: {to_phone}"}

        # Use instance user_id as fallback
        user_id = user_id or self.user_id

        # 1. Compliance Gate (TCPA/DNC/Quiet Hours) — tenant-scoped
        # Consent proof fields — populated by the compliance gate when consent passes
        consent_record_id = None
        consent_verified_at = None
        consent_method = None

        if bypass_compliance:
            logger.warning(
                "SMS compliance BYPASSED for %s by user %s (lead_id=%s)",
                normalized_phone[-4:] if normalized_phone else "????",
                user_id,
                lead_id,
            )
        if not bypass_compliance and self.db:
            compliance = check_sms_compliance(
                self.db, normalized_phone, message,
                lead_id=lead_id, user_id=user_id,
                organization_id=organization_id,
            )
            if not compliance.allowed:
                return {"success": False, "error": f"Compliance Block: {compliance.reason}"}
            # Capture consent proof from the compliance gate result
            consent_record_id = compliance.consent_record_id
            consent_verified_at = compliance.consent_verified_at
            consent_method = compliance.consent_method

        # Recover session if compliance queries left it dirty (missing tables)
        if self.db:
            try:
                self.db.rollback()
            except Exception:
                pass

        # 2. Rate Limiting
        if self.db:
            rate_allowed, rate_reason = check_rate_limit(self.db, normalized_phone, user_id=user_id, lead_id=lead_id)
            if not rate_allowed:
                return {"success": False, "error": f"Rate limit: {rate_reason}"}

        # 3. Scheduling
        if schedule_at and self.db:
            job_id = schedule_sms(self.db, normalized_phone, message, schedule_at, lead_id)
            return {"success": True, "status": "scheduled", "job_id": job_id}

        # 4. Actual Transmission via centralized SMS chokepoint
        #    Compliance already checked above, so bypass in the chokepoint
        #    to avoid double-checking (the chokepoint still appends STOP footer).
        try:
            from telephony.sms import send_sms_verified

            result = send_sms_verified(
                to=normalized_phone,
                from_=self.from_number,
                text=message,
                messaging_profile_id=self.profile_id or None,
                media_urls=media_urls,
                api_key=self._api_key,
                bypass_compliance=True,  # Already checked above in step 1
                user_id=user_id,
                lead_id=lead_id,
                organization_id=organization_id,
            )

            if result.get("status") == "sent":
                msg_id = result.get("id")

                # 5. Delivery Tracking & Rate limit recording (with TCPA consent proof)
                if self.db:
                    record_message_sent(
                        self.db, msg_id, to_phone, self.from_number,
                        message, lead_id=lead_id, user_id=user_id,
                        consent_record_id=consent_record_id,
                        consent_verified_at=consent_verified_at,
                        consent_method=consent_method,
                    )
                    record_send_attempt(self.db, to_phone, user_id=user_id, lead_id=lead_id)

                return {"success": True, "message_id": msg_id}
            else:
                reason = result.get("reason", "SMS delivery failed")
                logger.error(f"SMS send blocked/failed: {reason}")
                return {"success": False, "error": reason}

        except Exception as e:
            logger.error(f"Transmission error to {normalized_phone}: {e}", exc_info=True)
            return {"success": False, "error": f"SMS transmission error: {e}"}

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
