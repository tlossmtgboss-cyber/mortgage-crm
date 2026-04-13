"""
aria/tools/communication_tools.py
Perennia AI — Communication Bridge for Aria

Bridges Aria task executor to existing SMS (Telnyx), email (Microsoft Graph/SendGrid),
and calendar services.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CommunicationTools:

    async def send_sms(
        self, to_phone: str, from_user: Dict,
        message: str, org_id: str,
    ) -> Dict:
        """Send SMS via Telnyx using the existing SMS retry service."""
        try:
            from services.sms_retry_service import SMSRetryService
            sms_service = SMSRetryService()

            from_phone = os.environ.get("TELNYX_FROM_NUMBER", "+18438838956")
            messaging_profile = os.environ.get(
                "TELNYX_MESSAGING_PROFILE_ID",
                "40019bed-2fa1-4407-a0c6-fe4c6b222c93"
            )

            result = await sms_service.send_sms_with_retry(
                to_phone=to_phone,
                from_phone=from_phone,
                message=message,
                messaging_profile_id=messaging_profile,
                organization_id=org_id,
                workflow_id=None,
                metadata={"source": "aria", "user_id": str(from_user.get("id", ""))},
            )

            return {
                "message_id": result.get("message_id", ""),
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "status": "sent",
            }
        except Exception as e:
            logger.error(f"Aria SMS send failed: {e}", exc_info=True)
            raise ValueError(f"Failed to send SMS: {e}")

    async def send_email(
        self, to_email: str, to_name: str,
        from_user: Dict, subject: str, body: str,
        attachments: Optional[List[Dict]] = None,
        cc: Optional[str] = None,
    ) -> Dict:
        """Send email via the existing email delivery service."""
        try:
            from services.email_delivery_service import EmailDeliveryService
            email_service = EmailDeliveryService()

            result = await email_service.send_email(
                to=to_email,
                subject=subject,
                text_body=body,
                from_email=from_user.get("email"),
                from_name=from_user.get("full_name"),
                cc=cc,
                attachments=[
                    {
                        "filename": att["filename"],
                        "content": att["content"],
                        "content_type": att.get("content_type", "application/octet-stream"),
                    }
                    for att in (attachments or [])
                ] if attachments else None,
                organization_id=from_user.get("organization_id"),
                user_id=str(from_user.get("id", "")),
            )

            return {
                "message_id": getattr(result, "message_id", "") or "",
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "status": "sent" if getattr(result, "success", False) else "failed",
                "provider": getattr(result, "provider", "unknown"),
            }
        except Exception as e:
            logger.error(f"Aria email send failed: {e}", exc_info=True)
            raise ValueError(f"Failed to send email: {e}")

    async def schedule_call(
        self, with_contact: Dict, lo: Dict,
        date: str, time: str,
        duration_minutes: int = 30,
        topic: str = "",
    ) -> Dict:
        """Schedule a call by creating a calendar event and task."""
        try:
            # Create a task for the call as a reliable fallback
            from aria.tools.pipeline_tools import PipelineTools
            pipe = PipelineTools()

            task = await pipe.create_task(
                description=f"Call {with_contact['name']}" + (f" — {topic}" if topic else ""),
                due_date=date,
                assigned_to=str(lo["id"]),
                borrower_id=str(with_contact["id"]) if with_contact.get("type") == "borrower" else None,
                created_by=str(lo["id"]),
                org_id=str(lo.get("organization_id", "")),
            )

            return {
                "datetime": f"{date} {time}",
                "duration_minutes": duration_minutes,
                "with": with_contact["name"],
                "task_id": task.get("id"),
                "calendar_link": None,
            }
        except Exception as e:
            logger.error(f"Aria schedule call failed: {e}", exc_info=True)
            raise ValueError(f"Failed to schedule call: {e}")
