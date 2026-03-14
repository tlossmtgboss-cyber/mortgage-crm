"""
SMS Service - A+ Comprehensive Mortgage SMS Orchestrator
Integrated with Compliance Gate, Rate Limiter, Scheduler, and Analytics.
"""
import os
import logging
import asyncio
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from sqlalchemy.orm import Session

# Import A+ Modules
from .sms_compliance_gate import check_sms_compliance, handle_inbound_keyword
from .sms_rate_limiter import check_rate_limit
from .sms_scheduler import schedule_sms
from .sms_key_vault import get_decrypted_key
from .sms_delivery_tracker import track_delivery
from .sms_analytics import log_sms_event
from .sms_template_engine import render_template

logger = logging.getLogger(__name__)

class SMSClient:
    """Enterprise-grade SMS Client with built-in compliance and routing."""
    
    def __init__(self, db: Session = None):
        self.db = db
        self.provider = "telnyx"
        self.enabled = False
        
        # Load credentials from secure key vault
        self._api_key = get_decrypted_key("TELNYX_API_KEY")
        self.from_number = os.getenv("TELNYX_PHONE_NUMBER", "")
        self.profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")
        
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
        bypass_compliance: bool = False,
        schedule_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Send SMS with full compliance and rate limiting stack.
        """
        if not self.enabled:
            return {"success": False, "error": "Client not configured"}

        # 1. Compliance Gate (TCPA/DNC/Quiet Hours)
        if not bypass_compliance:
            compliance = check_sms_compliance(
                self.db, to_phone, message, lead_id=lead_id, user_id=user_id
            )
            if not compliance.allowed:
                log_sms_event(self.db, to_phone, "blocked", compliance.reason, lead_id)
                return {"success": False, "error": f"Compliance Block: {compliance.reason}"}

        # 2. Rate Limiting
        if not check_rate_limit(self.db, to_phone):
            return {"success": False, "error": "Rate limit exceeded for this recipient"}

        # 3. Scheduling
        if schedule_at:
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
                
                # 5. Delivery Tracking & Analytics
                track_delivery(self.db, msg_id, to_phone, lead_id)
                log_sms_event(self.db, to_phone, "sent", "Success", lead_id)
                
                return {"success": True, "message_id": msg_id}
            else:
                error = response.text[:200]
                log_sms_event(self.db, to_phone, "failed", error, lead_id)
                return {"success": False, "error": error}
                
        except Exception as e:
            logger.error(f"Transmission error: {e}")
            return {"success": False, "error": str(e)}

    async def send_templated_sms(
        self,
        to_phone: str,
        template_name: str,
        context: Dict[str, Any],
        lead_id: Optional[int] = None
    ):
        """Render a mortgage template and send."""
        message = render_template(template_name, context)
        return await self.send_sms(to_phone, message, lead_id=lead_id)

# Global helper
async def send_quick_sms(to: str, msg: str, db: Session):
    client = SMSClient(db)
    return await client.send_sms(to, msg)
