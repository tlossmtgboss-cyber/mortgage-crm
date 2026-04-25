"""
aria/tools/communication_tools.py
Perennia AI — Communication Bridge for Aria

Bridges Aria task executor to existing SMS (Telnyx), email (Microsoft Graph/SendGrid),
and calendar services.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sa_text

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

            from_phone = os.environ.get("TELNYX_FROM_NUMBER", "")
            messaging_profile = os.environ.get(
                "TELNYX_MESSAGING_PROFILE_ID",
                ""
            )

            _org_id_int = int(org_id) if org_id else None
            result = await sms_service.send_sms_with_retry(
                to_phone=to_phone,
                from_phone=from_phone,
                message=message,
                messaging_profile_id=messaging_profile,
                organization_id=_org_id_int,
                workflow_id=None,
                metadata={"source": "aria", "user_id": str(from_user.get("id", ""))},
            )

            # Record in sms_panel_messages so it appears in SMS Archive tab
            try:
                from database import SessionLocal
                db = SessionLocal()
                try:
                    panel_id = str(uuid.uuid4())
                    db.execute(sa_text("""
                        INSERT INTO sms_panel_messages
                            (id, phone, organization_id, direction, body,
                             sender_name, sender_role, status,
                             media_urls, telnyx_message_id, created_at)
                        VALUES
                            (:id, :phone, :org_id, 'outbound', :body,
                             'Aria', 'ai_assistant', 'sent',
                             '[]'::jsonb, :telnyx_id, NOW())
                        ON CONFLICT (id) DO NOTHING
                    """), {
                        "id": panel_id,
                        "phone": to_phone,
                        "org_id": _org_id_int,
                        "body": message[:2000],
                        "telnyx_id": result.get("message_id", ""),
                    })
                    db.commit()
                except Exception as e:
                    logger.warning(f"Failed to write Aria SMS to panel_messages: {e}")
                    db.rollback()
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"Could not open DB session for panel_messages: {e}")

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
        """Schedule a call by creating a task and notifying the contact via SMS."""
        try:
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

            sms_sent = False
            contact_phone = with_contact.get("phone")
            if contact_phone:
                try:
                    lo_name = lo.get("full_name", "your loan officer")
                    contact_name = with_contact.get("name", "")
                    sms_body = (
                        f"Hi {contact_name}, {lo_name} would like to schedule a call"
                        + (f" on {date} at {time}" if date and time else "")
                        + (f" regarding {topic}" if topic else "")
                        + ". Please let me know if that works for you!"
                        + f" — {lo_name}"
                    )
                    await self.send_sms(
                        to_phone=contact_phone,
                        from_user=lo,
                        message=sms_body,
                        org_id=str(lo.get("organization_id", "")),
                    )
                    sms_sent = True
                except Exception as sms_err:
                    logger.warning(f"Could not send scheduling SMS to {contact_phone}: {sms_err}")

            return {
                "datetime": f"{date} {time}",
                "duration_minutes": duration_minutes,
                "with": with_contact["name"],
                "task_id": task.get("id"),
                "calendar_link": None,
                "sms_sent": sms_sent,
                "note": "SMS sent to coordinate timing." if sms_sent else "Task created but could not reach contact via SMS.",
            }
        except Exception as e:
            logger.error(f"Aria schedule call failed: {e}", exc_info=True)
            raise ValueError(f"Failed to schedule call: {e}")
