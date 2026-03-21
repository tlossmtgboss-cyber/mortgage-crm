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
    ) -> Dict[str, Any]:
        """
        Send SMS with full compliance and rate limiting stack.
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
                "messaging_profile_id": self.profile_id
            }

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
